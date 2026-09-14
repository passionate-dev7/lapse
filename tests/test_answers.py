"""The other half of the loop: a question, answered, resolving into a filing.

A DECIDE that can never become anything is a dead end wearing the costume of a
decision. These tests take the real lapsed permits in the captured portfolio,
answer the question the engine put to the contractor, and assert the verdict
moves, that it moves for a cited reason, and that an answer cannot do anything
it was not asked to do.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from agent.engine.deadline import (
    ContractorAnswer,
    Klass,
    Outcome,
    decide_permit,
)
from agent.engine.portfolio import load_snapshot
from agent.engine.rulebook import lapsed_answers

TODAY = date(2026, 9, 14)
PORTFOLIO = load_snapshot(today=TODAY)


def _a_lapsed_permit():
    for permit in PORTFOLIO.permits:
        job = PORTFOLIO.job_for(permit)
        verdict = decide_permit(permit, job, today=TODAY)
        if verdict.outcome is Outcome.DECIDE and verdict.klass is Klass.LAPSED:
            return permit, job, verdict
    raise AssertionError("the captured portfolio has no lapsed permit awaiting an answer")


def _answer(verdict, value: str, *, evidence_id: str | None = None) -> ContractorAnswer:
    return ContractorAnswer(
        value=value,
        answers_evidence_id=evidence_id if evidence_id is not None else verdict.evidence_id,
        answered_at="2026-09-14T14:00:00+00:00",
        answered_by="the contractor",
    )


def test_the_question_exists_before_it_can_be_answered():
    _, _, verdict = _a_lapsed_permit()
    assert verdict.outcome is Outcome.DECIDE
    assert verdict.missing and len(verdict.missing[0].split()) > 10


def test_no_work_after_expiry_becomes_a_clean_renewal():
    """1 RCNY 102-04(d)(6) waives the penalty, so the renewal is just a renewal."""
    permit, job, asked = _a_lapsed_permit()
    resolved = decide_permit(permit, job, today=TODAY, answer=_answer(asked, "no"))

    assert resolved.outcome is Outcome.FILE
    assert not resolved.missing, "a resolved case must stop asking"
    assert "waives" in resolved.action
    assert resolved.citation.startswith("https://")
    assert resolved.citation == lapsed_answers()["citation"]
    assert any(c.name.startswith("answered_by[") for c in resolved.checks)


def test_work_after_expiry_puts_the_penalty_first():
    """1 RCNY 102-04(a)(2) bars the renewal until the penalty is paid.

    Both answers produce a filing, and that is correct. What changes is what
    the contractor is told to do first, and getting that order wrong means
    filing a renewal DOB will not issue.
    """
    permit, job, asked = _a_lapsed_permit()
    resolved = decide_permit(permit, job, today=TODAY, answer=_answer(asked, "yes"))

    assert resolved.outcome is Outcome.FILE
    assert "before DOB will issue the renewal" in resolved.action
    assert "Do not file the renewal first" in resolved.action


def test_the_two_answers_do_not_produce_the_same_instruction():
    """If both branches said the same thing, the question was theatre."""
    permit, job, asked = _a_lapsed_permit()
    yes = decide_permit(permit, job, today=TODAY, answer=_answer(asked, "yes"))
    no = decide_permit(permit, job, today=TODAY, answer=_answer(asked, "no"))
    assert yes.action != no.action
    assert yes.evidence_id != no.evidence_id


def test_an_answer_to_a_different_reading_does_not_carry_over():
    """The guard that stops a stale answer resolving a changed situation.

    An evidence id hashes the checks the verdict rested on. If DOB's record
    moved between the question and the answer, the answer was given about
    something else, and applying it would file against facts nobody agreed to.
    """
    permit, job, asked = _a_lapsed_permit()
    stale = _answer(asked, "no", evidence_id="permit:0:lapsed:DECIDE:deadbeef01")
    verdict = decide_permit(permit, job, today=TODAY, answer=stale)

    assert verdict.outcome is Outcome.DECIDE
    assert verdict.missing
    failed = {c.name for c in verdict.failed}
    assert "answer_still_applies" in failed, "a superseded answer must be visible, not silent"


def test_a_meaningless_answer_changes_nothing():
    permit, job, asked = _a_lapsed_permit()
    for value in ("", "maybe", "YES please", "1"):
        verdict = decide_permit(permit, job, today=TODAY, answer=_answer(asked, value))
        assert verdict.outcome is Outcome.DECIDE


def test_an_answer_cannot_resurrect_a_permit_the_checks_closed():
    """An answer supplies one fact. It is not a veto override.

    On a permit whose job DOB signed off, the structured checks fail long
    before the lapsed branch is reached, so the answer is never consulted. If
    that ever stopped being true, a contractor could answer their way past a
    closed job.
    """
    closed = [
        (p, PORTFOLIO.job_for(p))
        for p in PORTFOLIO.permits
        if decide_permit(p, PORTFOLIO.job_for(p), today=TODAY).outcome is Outcome.HOLD
    ]
    assert closed, "the captured portfolio should contain a held permit"
    permit, job = closed[0]
    before = decide_permit(permit, job, today=TODAY)
    after = decide_permit(
        permit,
        job,
        today=TODAY,
        answer=_answer(before, "no"),
    )
    assert after.outcome is Outcome.HOLD
    assert not any(c.name.startswith("answered_by[") for c in after.checks)


def test_an_answer_cannot_reach_a_permit_that_has_not_lapsed():
    """The answer is only consulted inside the lapsed branch.

    A permit due in three days needs a renewal, not a question about whether
    work continued past a date that has not arrived. Feeding an answer to one
    must not change what it says.
    """
    candidates = [
        p
        for p in PORTFOLIO.permits
        if decide_permit(p, PORTFOLIO.job_for(p), today=TODAY).outcome is Outcome.FILE
    ]
    assert candidates
    permit = candidates[0]
    job = PORTFOLIO.job_for(permit)
    before = decide_permit(permit, job, today=TODAY)
    after = decide_permit(permit, job, today=TODAY, answer=_answer(before, "yes"))
    assert after.action == before.action
    assert not any(c.name.startswith("answered_by[") for c in after.checks)


def test_the_pass_counts_how_many_answers_it_applied():
    """A number the console can show, so an answer visibly did something."""
    from agent.lapse_agent import case_id
    from agent.run import triage

    permit, job, asked = _a_lapsed_permit()
    item_id = permit.permit_id or permit.label
    plain = triage(PORTFOLIO, today=TODAY)
    answered = triage(PORTFOLIO, today=TODAY, answers={item_id: _answer(asked, "no")})

    before = sum(1 for _, _, v in plain if v.outcome is Outcome.FILE)
    after = sum(1 for _, _, v in answered if v.outcome is Outcome.FILE)
    assert after == before + 1, "answering one question should move exactly one item"
    assert case_id(PORTFOLIO.contractor, "permit", item_id)


def test_the_rulebook_refuses_an_uncited_answer_branch():
    """Both branches change what a contractor is told, so both need a source."""
    answers = lapsed_answers()
    for branch in ("yes", "no"):
        assert len(answers[branch]["quote"].split()) >= 12
        assert len(answers[branch]["action"].split()) >= 10
    assert answers["citation"].endswith(".pdf")
