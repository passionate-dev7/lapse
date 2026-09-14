"""Where a response actually went, and never claiming more than that.

The three-way decision in `resolve_delivery` is pure, so it can be exercised
with no credential and no network. The real send is marked `live` because it
consumes SES quota and returns a real MessageId.

The property under test is not "did it send". It is "does the case record say
what really happened". A console that renders "filed" over a message that went
to the AWS mailbox simulator is a console that lies to a contractor about
whether their permit is safe.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from agent.dispatch import (
    SIMULATOR_SUCCESS,
    DeliveryLoop,
    _assert_not_a_loop,
    _body,
    _desks,
    _subject,
    resolve_delivery,
    send_response,
)

SENDER = "lapse@getava.xyz"
DESK = "filing-desk@getava.xyz"
OPERATOR = "lapse-operator@getava.xyz"


def _case() -> dict:
    """A case in exactly the shape agent/lapse_agent.py writes them."""
    return {
        "contractor": "VARSITY PLBG AND HTG INC",
        "case_id": "0123456789abcdef",
        "kind": "permit",
        "status": "awaiting_approval",
        "item": {
            "kind": "permit",
            "item_id": "3993515",
            "job": "104213922",
            "job_doc": "03",
            "permit_type": "PL",
            "address": "240 SECOND AVENUE, MANHATTAN",
            "url": "https://a810-bisweb.nyc.gov/bisweb/JobsQueryByNumberServlet?requestid=1&passjobnumber=104213922&passdocnumber=03",
            "source": "https://data.cityofnewyork.us/d/ipu4-2q9a",
        },
        "verdict": {
            "outcome": "FILE",
            "klass": "critical",
            "due_on": "2026-09-15",
            "evidence_id": "permit:3993515:critical:FILE",
            "citation": "https://www.nyc.gov/site/buildings/property-or-business-owner/permit-renewal.page",
            "checks": [
                {"name": "permit_live", "passed": True, "detail": "permit status is ISSUED"},
                {"name": "job_open", "passed": True, "detail": "job is PERMIT ISSUED"},
            ],
        },
        "draft_text": "Job 104213922 permit PL expires September 15, 2026. Renew it in eFiling.",
    }


def test_the_filing_desk_is_read_from_the_contractor_record():
    """Dispatch never keeps its own idea of who it works for."""
    filing, operator = _desks()
    assert "@" in filing and "@" in operator
    assert filing != operator, (
        "the filing desk and the fallback must be different addresses, or the "
        "held_for_verification mode cannot mean anything"
    )
    assert filing != SENDER, "the response must not be addressed to the sender"


def test_a_verified_desk_is_a_direct_delivery():
    to, mode, reason = resolve_delivery(
        filing_desk=DESK, operator_desk=OPERATOR, production=False,
        desk_verified=True, operator_verified=True,
    )
    assert to == DESK and mode == "direct"
    assert "verified identity" in reason


def test_production_access_delivers_directly_to_anything():
    to, mode, reason = resolve_delivery(
        filing_desk="office@somecontractor.example", operator_desk=OPERATOR,
        production=True, desk_verified=False, operator_verified=True,
    )
    assert to == "office@somecontractor.example" and mode == "direct"
    assert "left the sandbox" in reason


def test_an_unreachable_desk_falls_back_to_the_operator_and_says_so():
    """The text is unaltered and `intended` still names the real target."""
    to, mode, reason = resolve_delivery(
        filing_desk="office@somecontractor.example", operator_desk=OPERATOR,
        production=False, desk_verified=False, operator_verified=True,
    )
    assert to == OPERATOR and mode == "held_for_verification"
    assert "office@somecontractor.example" in reason
    assert "has not received it" in reason


def test_neither_reachable_is_proven_against_the_simulator():
    """Not a failure, and not a lie either. It says nothing arrived."""
    to, mode, reason = resolve_delivery(
        filing_desk="office@somecontractor.example", operator_desk=OPERATOR,
        production=False, desk_verified=False, operator_verified=False,
    )
    assert to == SIMULATOR_SUCCESS and mode == "simulated"
    assert "Nothing reached anybody" in reason


def test_a_response_addressed_to_ourselves_is_refused():
    """The failure that looks exactly like success.

    A real send to our own sending identity returns a real MessageId and writes
    a delivery record that tells a reader the response reached somebody. It
    reached the program that wrote it. That is worse than an error, because an
    error is visible.
    """
    with pytest.raises(DeliveryLoop) as raised:
        _assert_not_a_loop(sender=SENDER, recipient=SENDER, intended=SENDER)
    assert "is not a delivery" in str(raised.value)

    with pytest.raises(DeliveryLoop):
        _assert_not_a_loop(sender=SENDER, recipient=SENDER, intended=DESK)

    # The simulator is the one legitimate case, because it is labelled as
    # having reached nobody rather than passed off as a delivery.
    _assert_not_a_loop(sender=SENDER, recipient=SIMULATOR_SUCCESS, intended=DESK)
    _assert_not_a_loop(sender=SENDER, recipient=DESK, intended=DESK)


def test_a_simulated_body_says_so_in_the_message_itself():
    """The honesty has to survive the message being forwarded out of context."""
    body = _body(_case(), mode="simulated", recipient=SIMULATOR_SUCCESS, filing_desk=DESK)
    assert "mailbox simulator" in body
    assert "Nothing has reached anybody yet." in body


def test_a_held_body_names_who_it_was_actually_for():
    body = _body(_case(), mode="held_for_verification", recipient=OPERATOR, filing_desk=DESK)
    assert DESK in body
    assert OPERATOR in body
    assert "The filing desk has not received it." in body


def test_a_direct_body_does_not_apologise_for_a_send_that_worked():
    body = _body(_case(), mode="direct", recipient=DESK, filing_desk=DESK)
    assert "simulator" not in body
    assert "has not received it" not in body


def test_every_body_says_this_is_not_addressed_to_the_city():
    """The claim that would lose the category if it were ever implied.

    DOB NOW takes a filing from a licensed person signed in under their own
    login. An agent cannot file, and a message that lets a reader think it did
    is the overreach worth guarding in a test rather than in a docstring.
    """
    for mode, recipient in (
        ("direct", DESK),
        ("held_for_verification", OPERATOR),
        ("simulated", SIMULATOR_SUCCESS),
    ):
        body = _body(_case(), mode=mode, recipient=recipient, filing_desk=DESK)
        assert "Lapse cannot file this and this is not addressed to the city." in body
        assert "the filing itself is yours" in body


def test_the_body_carries_the_evidence_and_the_links_to_check_it():
    body = _body(_case(), mode="direct", recipient=DESK, filing_desk=DESK)
    assert "[PASS] permit_live" in body
    assert "a810-bisweb.nyc.gov" in body, "a person has to be able to check the record by hand"
    assert "data.cityofnewyork.us" in body
    assert "nyc.gov/site/buildings" in body, "the deadline's source has to travel with it"


def test_the_subject_carries_the_urgency_and_the_address():
    subject = _subject(_case())
    assert subject.startswith("[CRITICAL]")
    assert "2026-09-15" in subject
    assert "240 SECOND AVENUE" in subject
    assert len(subject) <= 200


def test_a_case_already_sent_is_never_sent_again():
    """The guard runs before any AWS client is built, so this needs no credential."""
    case = _case()
    case["delivery"] = {"mode": "direct", "to": DESK, "message_id": "sent-already"}
    assert send_response(case)["message_id"] == "sent-already"


def test_a_case_with_no_draft_is_refused_before_anything_is_built():
    case = _case()
    case["draft_text"] = None
    with pytest.raises(ValueError) as raised:
        send_response(case)
    assert "no draft_text" in str(raised.value)


@pytest.mark.live
def test_a_real_send_returns_a_real_message_id():
    """Consumes SES quota. The MessageId is real and so is the mode."""
    case = _case()
    delivery = send_response(case)
    assert delivery["message_id"], "SES accepted nothing"
    assert delivery["mode"] in ("direct", "simulated")
    assert delivery["intended"]
    assert delivery["sent_at"]
