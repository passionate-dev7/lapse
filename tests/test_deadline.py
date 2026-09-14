"""The deadline engine, against the DOB records the city actually publishes.

Every fixture is a row out of data/, captured by scripts/capture.py from NYC
Open Data. Nothing here is invented, which matters because the failures this
engine exists to prevent are all shaped like a real record that a naive reader
mistakes for something else: a renewal sequence that looks like a lapse, a
signed-off job that looks like an emergency, an ACTIVE category on a violation
DOB already deleted.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from agent.engine.deadline import (
    CRITICAL_DAYS,
    DUE_DAYS,
    Klass,
    Outcome,
    StatusReading,
    classify,
    decide_permit,
    decide_violation,
    outstanding_by_text,
)
from agent.engine.portfolio import load_snapshot

TODAY = date(2026, 9, 14)
PORTFOLIO = load_snapshot(today=TODAY)


def test_the_snapshot_is_a_real_portfolio():
    assert PORTFOLIO.contractor == "VARSITY PLBG AND HTG INC"
    assert len(PORTFOLIO.permits) > 100
    assert len(PORTFOLIO.violations) > 10
    assert len(PORTFOLIO.jobs) > 100
    assert all(p.permittee == PORTFOLIO.contractor for p in PORTFOLIO.permits)


def test_the_classes_partition_the_day_axis():
    assert classify(-1) is Klass.LAPSED
    assert classify(0) is Klass.CRITICAL
    assert classify(CRITICAL_DAYS) is Klass.CRITICAL
    assert classify(CRITICAL_DAYS + 1) is Klass.DUE
    assert classify(DUE_DAYS) is Klass.DUE
    assert classify(DUE_DAYS + 1) is Klass.CLEAR


def test_a_superseded_permit_is_silent():
    """The single most common false alarm in this dataset.

    The permit issuance feed holds one row per issuance, so a permit renewed
    four times appears four times with four expiry dates, three of them in the
    past. A reader that treats each row as a live permit reports three
    emergencies that were handled months ago.
    """
    superseded = [p for p in PORTFOLIO.permits if p.superseded_by]
    assert superseded, "the captured portfolio should contain renewed permits"
    for permit in superseded:
        verdict = decide_permit(permit, PORTFOLIO.job_for(permit), today=TODAY)
        assert verdict.outcome is Outcome.HOLD
        failed = {c.name for c in verdict.failed}
        assert "not_superseded" in failed
        assert permit.superseded_by in next(
            c.detail for c in verdict.checks if c.name == "not_superseded"
        )


def test_a_signed_off_job_is_silent_even_when_the_permit_expired():
    """An expired permit on a closed job is paperwork, not a deadline.

    This is the check that needs the third dataset. The permit feed cannot tell
    the difference; the filings feed carries job_status, and X (SIGNED OFF) or
    U (COMPLETED) settles it.
    """
    found = 0
    for permit in PORTFOLIO.permits:
        job = PORTFOLIO.job_for(permit)
        if job is None or not job.is_terminal or permit.superseded_by:
            continue
        if permit.expires_on is None or permit.expires_on >= TODAY:
            continue
        found += 1
        verdict = decide_permit(permit, job, today=TODAY)
        assert verdict.outcome is Outcome.HOLD, (
            f"permit {permit.label} lapsed on a {job.status_text} job and was not held"
        )
        assert "job_open" in {c.name for c in verdict.failed}
    assert found, "the captured portfolio should contain a lapsed permit on a closed job"


def test_a_lapsed_permit_on_an_open_job_asks_rather_than_drafts():
    """DOB's own rule makes this a question, not a filing.

    1 RCNY 102-04(a)(2) bars the renewal until the unpermitted work penalty is
    paid, and (d)(6) waives that penalty where no work was done after expiry.
    Which applies is a fact about the site, so the engine stops and asks.
    """
    asked = 0
    for permit in PORTFOLIO.permits:
        job = PORTFOLIO.job_for(permit)
        if permit.superseded_by or job is None or job.is_terminal or job.is_stopped:
            continue
        if permit.expires_on is None or permit.expires_on >= TODAY:
            continue
        verdict = decide_permit(permit, job, today=TODAY)
        assert verdict.outcome is Outcome.DECIDE
        assert verdict.deadline.klass is Klass.LAPSED
        assert verdict.missing, "a DECIDE must carry the question that settles it"
        asked += 1
    assert asked, "the captured portfolio should contain a lapsed permit on an open job"


def test_a_permit_inside_the_window_on_an_open_job_is_drafted():
    drafted = 0
    for permit in PORTFOLIO.permits:
        job = PORTFOLIO.job_for(permit)
        if permit.superseded_by or job is None or job.is_terminal or job.is_stopped:
            continue
        if permit.expires_on is None:
            continue
        days = (permit.expires_on - TODAY).days
        if not 0 <= days <= DUE_DAYS:
            continue
        verdict = decide_permit(permit, job, today=TODAY)
        assert verdict.outcome is Outcome.FILE
        assert verdict.citation.startswith("https://")
        assert verdict.action and verdict.artifact
        drafted += 1
    assert drafted, "the captured portfolio should contain a permit inside the action window"


def test_a_permit_outside_the_window_is_silent():
    for permit in PORTFOLIO.permits:
        job = PORTFOLIO.job_for(permit)
        if permit.superseded_by or job is None or job.is_terminal or job.is_stopped:
            continue
        if permit.expires_on is None or (permit.expires_on - TODAY).days <= DUE_DAYS:
            continue
        verdict = decide_permit(permit, job, today=TODAY)
        assert verdict.outcome is Outcome.HOLD
        assert "within_action_window" in {c.name for c in verdict.failed}


def test_most_of_the_portfolio_is_silence():
    """The product's load-bearing property, asserted as a number.

    If the engine ever starts surfacing most of a portfolio it has stopped
    being useful, because a contractor who is told about everything reads
    nothing. This is a regression test on that, not a vanity metric.
    """
    from agent.run import triage

    triaged = triage(PORTFOLIO, today=TODAY)
    held = sum(1 for _, _, v in triaged if v.outcome is Outcome.HOLD)
    assert held / len(triaged) > 0.6, (
        f"only {held} of {len(triaged)} items were held; the queue is too noisy to read"
    )


def test_an_owner_obligation_is_not_handed_to_a_contractor():
    """Admin Code 28-303.7 names the owner on a boiler filing, not the plumber.

    Without this check a plumbing contractor's queue fills with the building
    owner's annual boiler and facade filings, which they cannot file and are
    not liable for.
    """
    from agent.engine.rulebook import violation_rule

    held = 0
    for violation in PORTFOLIO.violations:
        rule = violation_rule(violation.type_code)
        if rule is None or rule.respondent != "owner":
            continue
        verdict = decide_violation(violation, today=TODAY)
        assert verdict.outcome is Outcome.HOLD
        assert "contractor_is_respondent" in {c.name for c in verdict.failed}
        held += 1
    assert held, "the captured portfolio should contain an owner obligation"


def test_a_disposed_violation_is_silent():
    disposed = [v for v in PORTFOLIO.violations if v.disposition_date is not None]
    for violation in disposed:
        verdict = decide_violation(violation, today=TODAY)
        assert verdict.outcome is Outcome.HOLD


def test_the_keyword_check_reads_dobs_own_closure_language():
    """These strings are verbatim from the live dataset, not written for a test."""
    assert not outstanding_by_text(
        "DELETED BY CAW ON 05/23/23 BECAUSE REMOVE FROM FISP 9A"
    ).passed
    assert not outstanding_by_text("CIANOW CRM Violation Dismissed").passed
    assert not outstanding_by_text("DELETED BY CAW ON 03/05/24 BECAUSE ISSUED IN ERROR").passed
    assert outstanding_by_text("").passed
    assert outstanding_by_text("L2 ISSUED 04/12/25").passed


def test_the_model_may_close_a_violation_the_keyword_check_leaves_open():
    """The seam, exercised.

    A comment the keyword list does not recognise leaves the violation open. A
    confident read that says DOB withdrew it closes the case. This is the only
    thing the model is allowed to move.
    """
    open_ones = [
        v
        for v in PORTFOLIO.violations
        if decide_violation(v, today=TODAY).outcome is not Outcome.HOLD
    ]
    assert open_ones, "need a violation the engine currently leaves open"
    violation = open_ones[0]

    closed = decide_violation(
        violation,
        today=TODAY,
        reading=StatusReading(
            still_open=False,
            confidence=0.95,
            reason="the comment says DOB reassigned this to a different BIN",
            read_by="test",
        ),
    )
    assert closed.outcome is Outcome.HOLD
    assert any(c.name.startswith("outstanding_by_text[") for c in closed.checks)


def test_an_unconfident_read_is_ignored():
    """Below the confidence floor the model's read does not count at all."""
    open_ones = [
        v
        for v in PORTFOLIO.violations
        if decide_violation(v, today=TODAY).outcome is not Outcome.HOLD
    ]
    violation = open_ones[0]
    before = decide_violation(violation, today=TODAY)
    after = decide_violation(
        violation,
        today=TODAY,
        reading=StatusReading(
            still_open=False, confidence=0.4, reason="not sure", read_by="test"
        ),
    )
    assert after.outcome is before.outcome
    assert not any(c.name.startswith("outstanding_by_text[") for c in after.checks)


def test_the_model_cannot_reopen_what_the_structured_fields_closed():
    """The read only ever closes. It can never argue a closed item back open.

    A model that says still_open=True on a violation DOB categorised DISMISSED
    must not move it, because `category_active` fails before the soft check is
    ever consulted.
    """
    closed = [v for v in PORTFOLIO.violations if not v.category_is_active]
    if not closed:
        pytest.skip("the captured portfolio holds only ACTIVE violations by construction")
    verdict = decide_violation(
        closed[0],
        today=TODAY,
        reading=StatusReading(
            still_open=True, confidence=0.99, reason="I think it is open", read_by="test"
        ),
    )
    assert verdict.outcome is Outcome.HOLD


def test_every_verdict_explains_itself():
    from agent.run import triage

    for kind, item_id, verdict in triage(PORTFOLIO, today=TODAY):
        assert verdict.checks, f"{kind} {item_id} produced a verdict with no checks"
        assert verdict.item_id, "a verdict with no item id cannot be traced to a record"
        if verdict.outcome is Outcome.FILE:
            assert verdict.citation.startswith("https://"), (
                f"{kind} {item_id} was drafted against a rule with no source"
            )
        if verdict.outcome is Outcome.DECIDE:
            assert verdict.missing, f"{kind} {item_id} asks the contractor nothing"


def test_the_evidence_id_names_the_exact_decision():
    from agent.run import triage

    ids = {v.evidence_id for _, _, v in triage(PORTFOLIO, today=TODAY)}
    assert len(ids) == len(triage(PORTFOLIO, today=TODAY))


def test_moving_the_clock_moves_the_class_and_nothing_else():
    """The same permit, evaluated a week later, escalates without changing facts."""
    candidates = [
        p
        for p in PORTFOLIO.permits
        if not p.superseded_by
        and p.expires_on
        and (p.expires_on - TODAY).days > DUE_DAYS
        and (job := PORTFOLIO.job_for(p)) is not None
        and not job.is_terminal
        and not job.is_stopped
    ]
    assert candidates, "need a permit that is clear today"
    permit = min(candidates, key=lambda p: p.expires_on)
    job = PORTFOLIO.job_for(permit)

    today_verdict = decide_permit(permit, job, today=TODAY)
    assert today_verdict.outcome is Outcome.HOLD

    later = permit.expires_on - timedelta(days=3)
    later_verdict = decide_permit(permit, job, today=later)
    assert later_verdict.outcome is Outcome.FILE
    assert later_verdict.deadline.klass is Klass.CRITICAL
    assert later_verdict.deadline.due_on == today_verdict.deadline.due_on
