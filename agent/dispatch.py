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

Two things can happen to a response, and the case record says which:

    direct      the filing desk is a verified identity, or the account has
                left the sandbox: it was delivered there
    simulated   it is not: the send was proven against AWS's own mailbox
                simulator rather than claiming a delivery that could not have
                happened

Verified-ness and sandbox state are read from the SES API on every call, never
hardcoded, so the day production access is granted this same code starts
delivering to any filing desk with no edit.

A case that already carries `delivery.message_id` is never sent again. Sending
the same renewal request twice is not a retry, it is an agent spamming the
person it works for, so the guard runs before any AWS call is made.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

# getava.xyz is the domain verified with SES by Easy DKIM over DNS. LAPSE_SENDER
# overrides it; this is only the default, and whether it is actually usable is
# decided live in _sender_identity rather than assumed here.
DEFAULT_SENDER = "lapse@getava.xyz"
DEFAULT_FILING_DESK = "lapse@getava.xyz"

SIMULATOR_SUCCESS = "success@simulator.amazonses.com"


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
    *, filing_desk: str, production: bool, desk_verified: bool
) -> tuple[str, str, str]:
    """The recipient/mode/reason decision, pure and offline-testable.

    Everything that can change the answer is read from SES before this runs, so
    this is exactly the part a credential-free test should exercise instead of
    a real send.
    """
    if production or desk_verified:
        reason = (
            "SES account has left the sandbox; delivering to the filing desk"
            if production
            else f"{filing_desk} is a verified identity in this account; delivering there"
        )
        return filing_desk, "direct", reason
    reason = (
        f"SES account is in the sandbox and {filing_desk} is not a verified identity, "
        "so this send was proven against the AWS SES mailbox simulator instead of a "
        "real inbox. Nothing reached the filing desk"
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
        "Lapse cannot file this. DOB NOW takes a filing from a licensed person "
        "under their own login and nothing else, so this is the text and the "
        "evidence for that filing, ready to go, and the filing itself is yours.",
    ]
    if mode == "simulated":
        parts += [
            "",
            f"This message is addressed to {filing_desk}, but the Lapse sending "
            "account is in the Amazon SES sandbox and that address is not a verified "
            f"identity, so this send was proven against the AWS mailbox simulator "
            f"({recipient}) instead of a real inbox. Nothing has reached the filing "
            "desk yet.",
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
    filing_desk = to or os.environ.get("LAPSE_FILING_DESK") or DEFAULT_FILING_DESK

    recipient, mode, reason = resolve_delivery(
        filing_desk=filing_desk,
        production=_production_access(client),
        desk_verified=_identity_ok(client, filing_desk),
    )

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
