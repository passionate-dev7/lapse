"""The feed parsers, against the exact bytes NYC Open Data returned.

Everything in data/ is a real Socrata response, stamped with the `$where` that
produced it. These tests read those files, not fixtures written to make the
parsers look right, so a schema change at the city's end shows up here as a
failure rather than as a silently empty portfolio.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from agent.feeds import jobs as job_feed
from agent.feeds import permits as permit_feed
from agent.feeds import violations as violation_feed
from agent.feeds.socrata import day_list, escape, ymd

DATA = Path(__file__).parent.parent / "data"
PERMITS = json.loads((DATA / "permits_varsity.json").read_text())
VIOLATIONS = json.loads((DATA / "violations_varsity.json").read_text())
JOBS = json.loads((DATA / "jobs_varsity.json").read_text())


def test_the_captures_record_the_query_that_produced_them():
    for blob in (PERMITS, VIOLATIONS, JOBS):
        assert blob["query"]["$where"], "a capture with no query cannot be reproduced"
        assert blob["captured_at"]
        assert blob["rows"], "an empty capture proves nothing and would pass every test"


def test_permit_fields_are_the_ones_the_city_publishes():
    """Field names were read off the live schema, and this pins them.

    The possessive in `permittee_s_business_name` is the one most likely to be
    guessed wrong, and guessing it wrong yields a portfolio of zero permits with
    no error anywhere.
    """
    row = PERMITS["rows"][0]
    for field in (
        "permit_si_no", "job__", "job_doc___", "job_type", "permit_type",
        "permit_sequence__", "permit_status", "expiration_date", "issuance_date",
        "bin__", "house__", "street_name", "borough", "permittee_s_business_name",
    ):
        assert field in row, f"the live permit schema no longer carries {field!r}"


def test_a_permit_parses_into_something_a_person_could_check():
    permit = permit_feed.parse(PERMITS["rows"][0])
    assert permit.permit_id
    assert permit.permittee == PERMITS["permittee"]
    assert permit.expires_on is None or isinstance(permit.expires_on, date)
    assert permit.url.startswith("https://a810-bisweb.nyc.gov/")
    assert permit.job in permit.url


def test_expiry_dates_parse_out_of_the_citys_text_column():
    """expiration_date is a `text` column holding MM/DD/YYYY, not a date."""
    parsed = [permit_feed.parse(r) for r in PERMITS["rows"]]
    with_dates = [p for p in parsed if p.expires_on is not None]
    assert len(with_dates) / len(parsed) > 0.95
    assert all(2000 < p.expires_on.year < 2100 for p in with_dates)


def test_collapse_keeps_the_newest_sequence_and_marks_the_rest():
    parsed = [permit_feed.parse(r) for r in PERMITS["rows"]]
    collapsed = permit_feed.collapse(parsed)
    assert len(collapsed) == len(parsed)

    groups: dict[tuple[str, str, str], list] = {}
    for permit in collapsed:
        groups.setdefault((permit.job, permit.job_doc, permit.permit_type), []).append(permit)
    for members in groups.values():
        current = [m for m in members if not m.superseded_by]
        assert len(current) == 1, "a job and permit type must have exactly one live sequence"
        newest = current[0]
        for older in members:
            if older is newest:
                continue
            assert older.superseded_by == newest.permit_sequence
            assert int(older.permit_sequence) < int(newest.permit_sequence)


def test_a_violation_parses_and_its_padded_text_is_collapsed():
    parsed = [violation_feed.parse(r) for r in VIOLATIONS["rows"]]
    assert parsed
    for violation in parsed:
        assert "  " not in violation.description, "DOB's column padding survived the parse"
        assert "  " not in violation.type_label
        assert violation.issued_on is None or isinstance(violation.issued_on, date)


def test_the_active_test_reads_the_word_not_the_star():
    """DOB marks a closed violation with a star and with a word. Read the word."""
    assert violation_feed.parse({"violation_category": "V-DOB VIOLATION - ACTIVE"}).category_is_active
    assert not violation_feed.parse(
        {"violation_category": "V*-DOB VIOLATION - DISMISSED"}
    ).category_is_active
    assert not violation_feed.parse(
        {"violation_category": "V*-DOB VIOLATION - Resolved"}
    ).category_is_active
    assert violation_feed.parse(
        {"violation_category": "VW-VIOLATION WORK WITHOUT PERMIT - ACTIVE"}
    ).category_is_active


def test_the_capture_only_holds_violations_the_city_calls_active():
    parsed = [violation_feed.parse(r) for r in VIOLATIONS["rows"]]
    assert all(v.category_is_active for v in parsed)


def test_a_filing_parses_and_terminal_status_is_recognised():
    parsed = [job_feed.parse(r) for r in JOBS["rows"]]
    assert parsed
    terminal = [j for j in parsed if j.is_terminal]
    assert terminal, "the captured filings should contain a signed off job"
    for job in terminal:
        assert job.status in job_feed.TERMINAL_STATUS or job.signed_off_on is not None


def test_a_filing_carries_the_prose_that_makes_a_draft_readable():
    parsed = [job_feed.parse(r) for r in JOBS["rows"]]
    described = [j for j in parsed if len(j.description.split()) > 5]
    assert len(described) / len(parsed) > 0.8, (
        "most filings should carry a job description; without it a renewal request "
        "is a string of DOB codes"
    )


def test_newest_per_filing_picks_the_latest_action():
    parsed = [job_feed.parse(r) for r in JOBS["rows"]]
    newest = job_feed.newest_per_filing(parsed)
    assert len(newest) <= len(parsed)
    for key, chosen in newest.items():
        same = [j for j in parsed if j.key == key]
        latest = max((j.latest_action_on or date.min) for j in same)
        assert (chosen.latest_action_on or date.min) == latest


def test_day_list_enumerates_the_citys_date_format():
    clause = day_list(date(2026, 9, 1), date(2026, 9, 3))
    assert clause == "'09/01/2026','09/02/2026','09/03/2026'"


def test_day_list_refuses_a_range_too_wide_for_an_in_clause():
    with pytest.raises(ValueError):
        day_list(date(2020, 1, 1), date(2026, 1, 1))


def test_day_list_refuses_a_backwards_range():
    with pytest.raises(ValueError):
        day_list(date(2026, 9, 3), date(2026, 9, 1))


def test_ymd_is_the_violation_feeds_sortable_shape():
    assert ymd(date(2026, 9, 14)) == "20260914"
    assert ymd(date(2026, 1, 2)) < ymd(date(2026, 1, 10))


def test_a_business_name_with_an_apostrophe_does_not_break_the_query():
    assert escape("O'BRIEN PLUMBING") == "O''BRIEN PLUMBING"
