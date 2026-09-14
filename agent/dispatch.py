"""Sending the response, for real, and never claiming more than happened.

There is one honest thing to say about where a DOB filing goes: it goes into
DOB NOW, by a licensed person, under their own login. No agent can file it and
this one does not pretend to. What Lapse sends is the artifact that filing
needs: the drafted renewal request or the correction narrative, the evidence
the deadline engine checked, the citation the deadline came from, and the BIS
link a person can open to confirm every word of it. It goes to the filing desk,
which is whoever at the contractor actually logs in.

The sending account is in the SES sandbox: delivery is refused to any address
that is not itself a verified identity. That restriction is on the recipient.
The FROM address has a separate, unconditional rule that sandbox and production
both enforce, that SES will never send a message whose FromEmailAddress is not
a verified identity or a verified domain. There is no address, simulator
included, that skips that check.

Three things can happen to a response, and the case record says which:

    direct                 the filing desk is a verified identity, or the
                           account has left the sandbox: it was delivered there
    held_for_verification  the filing desk is not reachable yet but the
                           operator desk is: delivered there instead, text
                           unaltered, with the true intended recipient stamped
                           into the body and into a header
    simulated              neither is reachable: the send was proven against
                           AWS's own mailbox simulator rather than claiming a
                           delivery that could not have happened

`intended` always names the party the response is actually for, never the
address it settled for and never the sender. If `to` and `intended` and the
FROM address ever collapse onto one value, the delivery record has stopped
saying anything and `_assert_not_a_loop` raises rather than let that be
written to a case.

Verified-ness and sandbox state are read from the SES API on every call, never
hardcoded, so the day production access is granted this same code starts
delivering to any filing desk with no edit.

A case that already carries `delivery.message_id` is never sent again. Sending
the same renewal request twice is not a retry, it is an agent spamming the
person it works for, so the guard runs before any AWS call is made.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

# getava.xyz is the domain verified with SES by Easy DKIM over DNS. LAPSE_SENDER
# overrides it; this is only the default, and whether it is actually usable is
# decided live in _sender_identity rather than assumed here.
DEFAULT_SENDER = "lapse@getava.xyz"

SIMULATOR_SUCCESS = "success@simulator.amazonses.com"
DATA = Path(__file__).parent.parent / "data"


class DeliveryLoop(RuntimeError):
    """The agent was about to send a response to itself."""


def _desks() -> tuple[str, str]:
    """Who the response is for, and where it goes if they cannot be reached.

    Read from data/contractor.json, which is the same record the rest of Lapse
    reads the contractor from, so dispatch never keeps its own idea of who it
    works for. Environment overrides exist because a deployed Lambda is
    configured, not edited.
    """
    blob = json.loads((DATA / "contractor.json").read_text())
    filing = os.environ.get("LAPSE_FILING_DESK") or blob["filing_desk"]["email"]
    operator = os.environ.get("LAPSE_OPERATOR_DESK") or blob["operator_desk"]["email"]
    return filing, operator


def _assert_not_a_loop(*, sender: str, recipient: str, intended: str) -> None:
    """A delivery record that names the sender as the recipient proves nothing.

    Sending to the address the mail came from is the failure mode that looks
    exactly like success: a real API call, a real MessageId, a real inbox, and
    a case record that tells a reader the response reached somebody when it
    reached the program that wrote it. The simulator is the one legitimate
    exception, because it is explicitly labelled as having reached nobody.
    """
    if intended.lower() == sender.lower():
        raise DeliveryLoop(
            f"intended recipient {intended} is the sending identity; a response "
            "addressed to Lapse itself is not a delivery"
        )
    if recipient.lower() == sender.lower() and recipient != SIMULATOR_SUCCESS:
        raise DeliveryLoop(
            f"recipient {recipient} is the sending identity; refusing to record "
            "a send to ourselves as a delivery"
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _client() -> Any:
    return boto3.client("sesv2", region_name=REGION)


def _production_access(client: Any) -> bool:
    return bool(client.get_account().get("ProductionAccessEnabled"))


def _is_verified(client: Any, email: str) -> bool:
    if not email:
        return False
    try:
        resp = client.get_email_identity(EmailIdentity=email)
    except client.exceptions.NotFoundException:
        return False
    return bool(resp.get("VerifiedForSendingStatus"))


def _identity_ok(client: Any, address: str) -> bool:
    """True if SES will accept `address`, as sender or as sandbox recipient.

    Either the exact address is a verified EMAIL_ADDRESS identity, or its
    domain is a verified DOMAIN identity. A verified domain covers every
    local-part at it, which is the point of verifying a domain rather than
    every mailbox on it one at a time.
    """
    if _is_verified(client, address):
        return True
    domain = address.rsplit("@", 1)[-1] if "@" in address else ""
    return bool(domain) and _is_verified(client, domain)


def _sender_identity(client: Any) -> str:
    candidate = os.environ.get("LAPSE_SENDER", DEFAULT_SENDER)
    if _identity_ok(client, candidate):
        return candidate
    for identity in client.list_email_identities().get("EmailIdentities", []):
        if identity.get("VerificationStatus") != "SUCCESS":
            continue
        if identity.get("IdentityType") == "EMAIL_ADDRESS" and identity.get("SendingEnabled", True):
            return identity["IdentityName"]
        if identity.get("IdentityType") == "DOMAIN":
            return f"lapse@{identity['IdentityName']}"
    raise RuntimeError(
        "no verified SES sending identity (address or domain) in this account and region; "
        "verify one with `aws sesv2 create-email-identity --email-identity <addr-or-domain>`"
    )


def resolve_delivery(
    *,
    filing_desk: str,
    operator_desk: str | None,
    production: bool,
    desk_verified: bool,
    operator_verified: bool,
) -> tuple[str, str, str]:
    """The recipient/mode/reason decision, pure and offline-testable.

    Everything that can change the answer is read from SES before this runs, so
    this is exactly the part a credential-free test should exercise instead of
    a real send. `filing_desk` is the intended recipient in all three branches
    and is never substituted for the address that was actually reachable.
    """
    if production or desk_verified:
        reason = (
            f"SES account has left the sandbox; delivering to the filing desk at {filing_desk}"
            if production
            else f"{filing_desk} is a verified identity in this account; delivering there"
        )
        return filing_desk, "direct", reason
    if operator_desk and operator_verified:
        reason = (
            f"SES account is in the sandbox and the filing desk {filing_desk} is not a "
            f"verified identity, so this was routed to the operator desk {operator_desk} "
            "instead, unaltered, for a person to forward. The filing desk has not "
            "received it"
        )
        return operator_desk, "held_for_verification", reason
    reason = (
        f"SES account is in the sandbox and neither the filing desk {filing_desk} nor "
        "the operator desk is a verified identity, so this send was proven against the "
        "AWS SES mailbox simulator instead of a real inbox. Nothing reached anybody"
    )
    return SIMULATOR_SUCCESS, "simulated", reason


def _subject(case: dict) -> str:
    verdict = case.get("verdict") or {}
    item = case.get("item") or {}
    klass = (verdict.get("klass") or "").upper()
    due = verdict.get("due_on") or "no date"
    if item.get("kind") == "permit":
        what = f"permit {item.get('permit_type')} on job {item.get('job')}/{item.get('job_doc')}"
    else:
        what = f"violation {item.get('number')}"
    return f"[{klass}] {what} due {due}, {item.get('address', '')}"[:200]


def _evidence_block(case: dict) -> str:
    verdict = case.get("verdict") or {}
    lines = ["What was checked before this was drafted:"]
    for check in verdict.get("checks") or []:
        mark = "PASS" if check.get("passed") else "FAIL"
        lines.append(f"  [{mark}] {check.get('name', '')}: {check.get('detail', '')}")
    if verdict.get("citation"):
        lines += ["", f"The deadline comes from: {verdict['citation']}"]
    item = case.get("item") or {}
    if item.get("url"):
        lines.append(f"Check it yourself at DOB BIS: {item['url']}")
    if item.get("source"):
        lines.append(f"Record read from: {item['source']}")
    return "\n".join(lines)


def _body(case: dict, *, mode: str, recipient: str, filing_desk: str) -> str:
    parts = [case.get("draft_text") or "", "", _evidence_block(case)]
    parts += [
        "",
        "Lapse cannot file this and this is not addressed to the city. DOB NOW "
        "takes a filing from a licensed person signed in under their own login, "
        "and for most job types from a registered filing representative. There is "
        "no API and no delegated path that would let an agent file on somebody's "
        "behalf. So this is the text and the evidence for that filing, ready to "
        "go, and the filing itself is yours.",
    ]
    if mode == "held_for_verification":
        parts += [
            "",
            f"This response is for {filing_desk}, the filing desk on this "
            "contractor's record. The Lapse sending account is in the Amazon SES "
            "sandbox, which only delivers to verified addresses, so until that "
            f"address is verified this is being routed to {recipient} for a person "
            "to forward. The filing desk has not received it.",
        ]
    elif mode == "simulated":
        parts += [
            "",
            f"This response is for {filing_desk}, the filing desk on this "
            "contractor's record, but the Lapse sending account is in the Amazon SES "
            "sandbox and neither that address nor the operator desk is verified, so "
            f"this send was proven against the AWS mailbox simulator ({recipient}) "
            "instead of a real inbox. Nothing has reached anybody yet.",
        ]
    return "\n".join(parts)


def send_response(case: dict, *, to: str | None = None, dry_run: bool = False) -> dict:
    """Send `case["draft_text"]` to the filing desk, honestly.

    Returns the `delivery` dict to attach to the case. Idempotent: if
    `case["delivery"]["message_id"]` is already set, that same dict comes back
    unchanged and no AWS call is made. `dry_run=True` runs every check and
    builds the message but skips `send_email`, returning `message_id: None`.
    """
    existing = case.get("delivery") or {}
    if existing.get("message_id"):
        return existing

    if not case.get("draft_text"):
        raise ValueError(f"case {case.get('case_id')} has no draft_text to send")

    client = _client()
    sender = _sender_identity(client)
    configured_desk, operator_desk = _desks()
    filing_desk = to or configured_desk

    recipient, mode, reason = resolve_delivery(
        filing_desk=filing_desk,
        operator_desk=operator_desk,
        production=_production_access(client),
        desk_verified=_identity_ok(client, filing_desk),
        operator_verified=_identity_ok(client, operator_desk),
    )
    _assert_not_a_loop(sender=sender, recipient=recipient, intended=filing_desk)

    message_id = None
    if not dry_run:
        try:
            resp = client.send_email(
                FromEmailAddress=sender,
                Destination={"ToAddresses": [recipient]},
                ReplyToAddresses=[sender],
                Content={
                    "Simple": {
                        "Subject": {"Data": _subject(case), "Charset": "UTF-8"},
                        "Body": {
                            "Text": {
                                "Data": _body(
                                    case, mode=mode, recipient=recipient, filing_desk=filing_desk
                                ),
                                "Charset": "UTF-8",
                            }
                        },
                        "Headers": [
                            {
                                "Name": "X-Lapse-Evidence-Id",
                                "Value": (case.get("verdict") or {}).get("evidence_id", ""),
                            },
                            {"Name": "X-Lapse-Filing-Desk", "Value": filing_desk},
                        ],
                    }
                },
            )
        except ClientError as exc:
            raise RuntimeError(
                f"SES rejected the response for case {case.get('case_id')}: {exc}"
            ) from exc
        message_id = resp["MessageId"]

    delivery = {
        "mode": mode,
        "to": recipient,
        "intended": filing_desk,
        "message_id": message_id,
        "reason": reason,
        "sent_at": _now(),
    }
    case["delivery"] = delivery
    return delivery
