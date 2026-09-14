"""The type boundary around DynamoDB, and the key that stops two items colliding.

`agent/store.py` is the only module that talks to DynamoDB, and its job at the
edges is to make sure nothing boto3-shaped leaks out and nothing Python-shaped
leaks in. Both directions matter: a Decimal that escapes reaches the console as
something `JSON.stringify` cannot render, and a `date` that goes in unconverted
is rejected by DynamoDB at write time, in a Lambda, at seven in the morning.

Nothing here needs a credential. The table calls are exercised for real by the
deployed Lambda, whose invoke output is in the README.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from agent.store import CaseStore, ItemStore, _from_dynamo, _to_dynamo


def test_a_date_becomes_a_string_on_the_way_in():
    """A verdict carries real dates. DynamoDB has no date type."""
    assert _to_dynamo(date(2026, 9, 15)) == "2026-09-15"
    assert _to_dynamo({"due_on": date(2026, 9, 15)}) == {"due_on": "2026-09-15"}
    assert _to_dynamo([date(2026, 1, 2)]) == ["2026-01-02"]


def test_a_float_becomes_a_decimal_on_the_way_in():
    """The model's confidence is a float and boto3 refuses floats outright."""
    assert _to_dynamo(0.85) == Decimal("0.85")
    assert _to_dynamo({"confidence": 0.7}) == {"confidence": Decimal("0.7")}


def test_a_dataclass_becomes_a_plain_dict():
    @dataclass
    class Check:
        name: str
        passed: bool

    assert _to_dynamo(Check("job_open", True)) == {"name": "job_open", "passed": True}


def test_a_decimal_comes_back_as_a_number_the_console_can_render():
    assert _from_dynamo(Decimal("7")) == 7
    assert isinstance(_from_dynamo(Decimal("7")), int)
    assert _from_dynamo(Decimal("0.85")) == 0.85
    assert _from_dynamo(Decimal("-3")) == -3


def test_a_whole_case_survives_the_round_trip_as_json():
    """The shape the console actually receives, asserted end to end."""
    case = {
        "contractor": "VARSITY PLBG AND HTG INC",
        "case_id": "0123456789abcdef",
        "verdict": {
            "klass": "critical",
            "due_on": date(2026, 9, 15),
            "days_remaining": 1,
            "checks": [{"name": "job_open", "passed": True, "detail": "PERMIT ISSUED"}],
        },
        "timeline": [{"at": "2026-09-14T12:00:00+00:00", "event": "opened"}],
    }
    out = _from_dynamo(_to_dynamo(case))
    json.dumps(out)
    assert out["verdict"]["due_on"] == "2026-09-15"
    assert out["verdict"]["days_remaining"] == 1
    assert out["verdict"]["checks"][0]["passed"] is True


def test_a_permit_and_a_violation_can_never_collide_on_an_identifier():
    """DOB's two identifiers are bare integers from different sequences.

    `permit_si_no` and `isn_dob_bis_viol` are both plain numbers, so nothing
    stops them being equal. Without the kind prefix, a permit could overwrite a
    violation's last seen state and a pass would report the wrong thing changed.
    """
    assert ItemStore.item_key("permit", "2817783") != ItemStore.item_key("violation", "2817783")
    assert ItemStore.item_key("permit", "2817783") == "permit#2817783"


def test_a_case_id_is_stable_and_scoped_to_one_contractor():
    a = CaseStore.case_id("VARSITY PLBG AND HTG INC", "permit", "3993515")
    assert a == CaseStore.case_id("VARSITY PLBG AND HTG INC", "permit", "3993515")
    assert len(a) == 16
    assert a != CaseStore.case_id("OTHER PLUMBING LLC", "permit", "3993515")
    assert a != CaseStore.case_id("VARSITY PLBG AND HTG INC", "violation", "3993515")


def test_the_table_names_are_the_ones_that_were_actually_provisioned():
    """A rename here silently writes a whole pass into a table nobody reads."""
    from agent.store import CASES_TABLE, ITEMS_TABLE

    assert CASES_TABLE == "lapse-cases"
    assert ITEMS_TABLE == "lapse-permits"
