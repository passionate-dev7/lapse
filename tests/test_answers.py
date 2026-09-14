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


# --- the date questions ----------------------------------------------------
# The violation classes where DOB publishes a cure path and no deadline. The
# engine refuses to invent one, so the contractor names the date and from then
# on it runs through the same four classes as anything else.


def _a_dateless_violation():
    from agent.engine.deadline import decide_violation

    for violation in PORTFOLIO.violations:
        verdict = decide_violation(violation, today=TODAY)
        if verdict.outcome is Outcome.DECIDE and verdict.question_shape == "date":
            return violation, verdict
    raise AssertionError("the captured portfolio has no violation awaiting a date")


def test_a_dateless_violation_asks_for_a_date_and_offers_no_choices():
    _, verdict = _a_dateless_violation()
    assert verdict.question_shape == "date"
    assert verdict.choices == (), "a date question has no buttons to press"
    assert verdict.deadline is None, "there is no clock until they set one"


def test_a_date_the_contractor_sets_becomes_the_deadline():
    from agent.engine.deadline import decide_violation

    violation, asked = _a_dateless_violation()
    chosen = TODAY + timedelta(days=10)
    resolved = decide_violation(violation, today=TODAY, answer=_answer(asked, chosen.isoformat()))

    assert resolved.outcome is Outcome.FILE
    assert resolved.deadline is not None
    assert resolved.deadline.due_on == chosen
    assert resolved.deadline.days_remaining == 10
    assert resolved.deadline.klass is Klass.DUE
    assert resolved.deadline.anchor_name == "the date you set"
    assert any(c.name.startswith("response_date_set_by[") for c in resolved.checks)


def test_a_date_far_enough_out_goes_quiet_again():
    """The product working, not the product failing.

    A contractor who says they will respond in three months should hear nothing
    for two of them. Anything else trains them to stop reading.
    """
    from agent.engine.deadline import decide_violation

    violation, asked = _a_dateless_violation()
    far = TODAY + timedelta(days=90)
    resolved = decide_violation(violation, today=TODAY, answer=_answer(asked, far.isoformat()))

    assert resolved.outcome is Outcome.HOLD
    assert resolved.deadline.klass is Klass.CLEAR
    assert resolved.deadline.due_on == far


def test_the_date_they_set_escalates_on_its_own():
    from agent.engine.deadline import decide_violation

    violation, asked = _a_dateless_violation()
    target = TODAY + timedelta(days=90)
    answer = _answer(asked, target.isoformat())

    seen = {}
    for offset in (0, 65, 85, 91):
        when = TODAY + timedelta(days=offset)
        # The answer was given against the verdict as of TODAY, so it has to be
        # re-scoped to each later reading the way the console would.
        current = decide_violation(violation, today=when)
        scoped = _answer(current, target.isoformat())
        verdict = decide_violation(violation, today=when, answer=scoped)
        seen[offset] = verdict.klass.value if verdict.klass else None

    assert seen[0] == "clear"
    assert seen[65] == "due"
    assert seen[85] == "critical"
    assert seen[91] == "lapsed"


def test_a_date_already_past_is_refused_visibly():
    from agent.engine.deadline import decide_violation

    violation, asked = _a_dateless_violation()
    verdict = decide_violation(
        violation, today=TODAY, answer=_answer(asked, (TODAY - timedelta(days=1)).isoformat())
    )
    assert verdict.outcome is Outcome.DECIDE
    assert "response_date_is_a_future_date" in {c.name for c in verdict.failed}


def test_something_that_is_not_a_date_is_refused():
    from agent.engine.deadline import decide_violation

    violation, asked = _a_dateless_violation()
    for value in ("soon", "next month", "2026-13-45", ""):
        verdict = decide_violation(violation, today=TODAY, answer=_answer(asked, value))
        assert verdict.outcome is Outcome.DECIDE, f"{value!r} was accepted as a date"


# --- the shape contract the console reads ----------------------------------


def test_every_decide_declares_a_shape_and_every_other_outcome_declares_none():
    """The console renders an affordance off this, so it has to be total."""
    from agent.run import triage

    for kind, item_id, verdict in triage(PORTFOLIO, today=TODAY):
        if verdict.outcome is Outcome.DECIDE:
            assert verdict.question_shape in ("yes_no", "date", "open"), (
                f"{kind} {item_id} asks a question of no known shape"
            )
            if verdict.question_shape == "yes_no":
                assert len(verdict.choices) == 2
                assert {c["value"] for c in verdict.choices} == {"yes", "no"}
                assert all(len(c["label"].split()) >= 4 for c in verdict.choices)
            else:
                assert verdict.choices == (), "only a yes or no question has choices"
        else:
            assert verdict.question_shape == "none"
            assert verdict.choices == ()


def test_the_choices_are_the_citys_words_not_the_consoles():
    from agent.run import triage

    answers = lapsed_answers()
    labels = {answers["no"]["label"], answers["yes"]["label"]}
    shaped = [
        v
        for _, _, v in triage(PORTFOLIO, today=TODAY)
        if v.question_shape == "yes_no"
    ]
    assert shaped, "the captured portfolio should contain a yes or no question"
    for verdict in shaped:
        assert {c["label"] for c in verdict.choices} == labels


def test_both_question_shapes_actually_occur_in_a_real_portfolio():
    """Otherwise one branch is untested against anything real."""
    from agent.run import triage

    shapes = {v.question_shape for _, _, v in triage(PORTFOLIO, today=TODAY)}
    assert "yes_no" in shapes and "date" in shapes
