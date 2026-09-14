"""The part of Lapse that decides.

The model never returns a verdict. It reads free text into a `StatusReading`
and it writes drafts. Everything that follows is arithmetic on dates and joins
on identifiers, so an alarm can always be explained by naming the checks that
passed and the values they passed on.

Three outcomes, and the middle one is the product:

    FILE    every check passed, the deadline is inside the action window, and
            the rulebook names one specific filing -> a response may be drafted
            and, once a person approves it, sent
    DECIDE  the arithmetic is sound but a fact only the contractor holds
            changes which action is correct -> interrupt them, once, with that
            one question
    HOLD    nothing is due, or the item is already closed -> say nothing, ever

Four deadline classes, on one axis, days remaining until the action is due:

    lapsed    < 0     the date has passed
    critical  0..7    inside a week
    due       8..30   inside a month
    clear     > 30    not yet anybody's problem

The asymmetry that makes this worth writing: HOLD is the common case and it has
to be loud in the code and silent in the product. A contractor who gets told
about every permit in their portfolio stops reading, and then the one that
mattered goes past too. Every HOLD in here is a notification that was correctly
not sent.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from agent.engine.rulebook import Rule, permit_rule, violation_rule
from agent.feeds.jobs import Job
from agent.feeds.permits import LIVE_STATUSES, Permit
from agent.feeds.violations import Violation

CRITICAL_DAYS = 7
DUE_DAYS = 30


class Klass(str, Enum):
    LAPSED = "lapsed"
    CRITICAL = "critical"
    DUE = "due"
    CLEAR = "clear"


class Outcome(str, Enum):
    FILE = "FILE"
    DECIDE = "DECIDE"
    HOLD = "HOLD"


def classify(days_remaining: int) -> Klass:
    if days_remaining < 0:
        return Klass.LAPSED
    if days_remaining <= CRITICAL_DAYS:
        return Klass.CRITICAL
    if days_remaining <= DUE_DAYS:
        return Klass.DUE
    return Klass.CLEAR


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str

    def __str__(self) -> str:
        return f"{'pass' if self.passed else 'FAIL'} {self.name}: {self.detail}"


@dataclass(frozen=True)
class Deadline:
    anchor: date
    anchor_name: str
    due_on: date
    days_remaining: int
    klass: Klass

    def __str__(self) -> str:
        when = (
            f"{abs(self.days_remaining)} days ago"
            if self.days_remaining < 0
            else f"in {self.days_remaining} days"
        )
        return f"{self.due_on} ({when}), class {self.klass.value}"


@dataclass(frozen=True)
class StatusReading:
    """The model's read on whether DOB's own free text says this is still open.

    581 of the 165,001 DOB violations issued in the last five years and still
    categorised ACTIVE carry a `disposition_comments` that says otherwise: "DELETED BY CAW
    ON 05/23/23 BECAUSE REMOVE FROM FISP 9A", "NOT REQUIRED TO FILE CYCLE 9",
    "S/B AT 215 CHRYSTIE STREET BN#1090397". The structured field says open.
    The sentence a clerk typed says it was deleted, or that it belongs to a
    different building. Telling those apart is reading, and it is the one
    judgment here a person makes better than a keyword list.

    This reading may only replace `outstanding_by_text`, the soft lexical
    check. It can never touch the category, the disposition date, the class
    thresholds or the arithmetic. The model is allowed to say "DOB already
    withdrew this"; it is never allowed to say "file it anyway, the date does
    not matter".
    """

    still_open: bool
    confidence: float
    reason: str
    read_by: str

    MIN_CONFIDENCE = 0.7

    @property
    def usable(self) -> bool:
        return self.confidence >= self.MIN_CONFIDENCE


@dataclass(frozen=True)
class Verdict:
    outcome: Outcome
    checks: tuple[Check, ...]
    kind: str
    item_id: str
    label: str
    address: str
    deadline: Deadline | None = None
    action: str = ""
    artifact: str = ""
    citation: str = ""
    rule_key: str = ""
    missing: tuple[str, ...] = ()

    @property
    def passed(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.passed)

    @property
    def failed(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if not c.passed)

    @property
    def klass(self) -> Klass | None:
        return self.deadline.klass if self.deadline else None

    @property
    def evidence_id(self) -> str:
        """Identifies exactly which decision a filed response rests on.

        The kind, the identifier, the class and the outcome are not enough on
        their own. Two passes a month apart against different DOB data can land
        on the same four values while resting on different facts, and an id
        that cannot tell those apart is a label, not evidence. So the checks
        that produced the verdict, their names, their pass or fail, and the
        values they passed on, are hashed into it. Change what the city
        published and the id changes with it.
        """
        klass = self.deadline.klass.value if self.deadline else "none"
        basis = "|".join(f"{c.name}={c.passed}:{c.detail}" for c in self.checks)
        if self.deadline:
            basis += f"|due={self.deadline.due_on}|days={self.deadline.days_remaining}"
        digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:10]
        return f"{self.kind}:{self.item_id}:{klass}:{self.outcome.value}:{digest}"


# DOB clerks write disposition comments in a small number of shapes. These are
# the ones that appear verbatim in the live dataset, not invented phrasings;
# `scripts/measure_prose.py` counts how many of the 581 each one catches and how
# many it misses, which is the number that justifies reading them with a model.
_CLOSED_PHRASES = (
    "deleted by",
    "dismissed",
    "issued in error",
    "entered in error",
    "violation withdrawn",
)


def outstanding_by_text(comments: str) -> Check:
    """The soft check, done with a keyword list, for when no model has read it.

    Deliberately shallow. It catches the literal "DELETED BY" prefix and little
    else, which is the point: what it misses is the measurement of what the
    model is for.
    """
    text = (comments or "").lower()
    if not text:
        return Check(
            "outstanding_by_text",
            True,
            "DOB recorded no disposition comment, so nothing contradicts the open status",
        )
    hit = next((p for p in _CLOSED_PHRASES if p in text), None)
    if hit:
        return Check(
            "outstanding_by_text",
            False,
            f"DOB's own comment says this was closed ({hit!r}): {comments[:160]}",
        )
    return Check(
        "outstanding_by_text",
        True,
        f"comment does not say it was closed: {comments[:160]}",
    )


def _reading_check(reading: StatusReading) -> Check:
    return Check(
        f"outstanding_by_text[{reading.read_by}]",
        reading.still_open,
        f"{reading.reason} (confidence {reading.confidence:.2f})",
    )


def _superseded_check(permit: Permit) -> Check:
    if permit.superseded_by:
        return Check(
            "not_superseded",
            False,
            f"sequence {permit.permit_sequence} was replaced by sequence "
            f"{permit.superseded_by} on the same job and permit type",
        )
    return Check(
        "not_superseded",
        True,
        f"sequence {permit.permit_sequence} is the newest issued for "
        f"job {permit.job}/{permit.job_doc} permit type {permit.permit_type}",
    )


def _job_check(permit: Permit, job: Job | None) -> Check:
    if job is None:
        return Check(
            "job_open",
            False,
            f"no DOB filing record found for job {permit.job}/{permit.job_doc}, "
            "so whether the job is still open cannot be read from the data",
        )
    if job.is_terminal:
        when = job.signed_off_on or job.latest_action_on
        return Check(
            "job_open",
            False,
            f"job {permit.job}/{permit.job_doc} is {job.status_text}"
            + (f" as of {when}" if when else ""),
        )
    if job.is_stopped:
        return Check(
            "job_open",
            False,
            f"job {permit.job}/{permit.job_doc} is {job.status_text or 'withdrawn'}",
        )
    return Check(
        "job_open",
        True,
        f"job {permit.job}/{permit.job_doc} is {job.status_text}",
    )


def _result(
    outcome: Outcome,
    checks: list[Check],
    *,
    kind: str,
    item_id: str,
    label: str,
    address: str,
    deadline: Deadline | None = None,
    rule: Rule | None = None,
    missing: tuple[str, ...] = (),
) -> Verdict:
    return Verdict(
        outcome=outcome,
        checks=tuple(checks),
        kind=kind,
        item_id=item_id,
        label=label,
        address=address,
        deadline=deadline,
        action=rule.action if rule else "",
        artifact=rule.artifact if rule else "",
        citation=rule.citation if rule else "",
        rule_key=rule.key if rule else "",
        missing=missing,
    )


def decide_permit(permit: Permit, job: Job | None, *, today: date) -> Verdict:
    """A permit's verdict. Entirely arithmetic and joins; no prose is read.

    There is no soft check here on purpose. A permit issuance row carries no
    sentence anybody wrote, only codes and dates, so there is nothing for a
    model to be better at than a comparison. The model's work on a permit is
    the renewal request, written from the job's description, and it happens
    after this function has already decided whether one is owed.
    """
    kind, item_id = "permit", permit.permit_id or permit.label
    label, address = permit.label, permit.address
    checks: list[Check] = []

    live = permit.status in LIVE_STATUSES
    checks.append(
        Check(
            "permit_live",
            live,
            f"permit status is {permit.status or 'blank'}"
            + ("" if live else ", so it is not authorising work and its date is not a deadline"),
        )
    )
    if not live:
        return _result(Outcome.HOLD, checks, kind=kind, item_id=item_id, label=label, address=address)

    checks.append(_superseded_check(permit))
    if permit.superseded_by:
        return _result(Outcome.HOLD, checks, kind=kind, item_id=item_id, label=label, address=address)

    known = permit.expires_on is not None
    checks.append(
        Check(
            "expiry_known",
            known,
            f"expiration date reads {permit.expires_on}"
            if known
            else "expiration_date is blank or unparseable, so no deadline can be computed",
        )
    )
    if not known:
        return _result(
            Outcome.DECIDE,
            checks,
            kind=kind,
            item_id=item_id,
            label=label,
            address=address,
            missing=(f"the expiry date DOB printed on permit {permit.label}",),
        )

    job_check = _job_check(permit, job)
    checks.append(job_check)
    if not job_check.passed:
        if job is None:
            return _result(
                Outcome.DECIDE,
                checks,
                kind=kind,
                item_id=item_id,
                label=label,
                address=address,
                missing=(
                    f"whether job {permit.job}/{permit.job_doc} at {permit.address} is still open",
                ),
            )
        if job.is_stopped:
            return _result(
                Outcome.DECIDE,
                checks,
                kind=kind,
                item_id=item_id,
                label=label,
                address=address,
                missing=(
                    f"whether the {job.status_text or 'withdrawal'} on job "
                    f"{permit.job}/{permit.job_doc} has been lifted",
                ),
            )
        return _result(Outcome.HOLD, checks, kind=kind, item_id=item_id, label=label, address=address)

    expires_on = permit.expires_on
    days = (expires_on - today).days
    deadline = Deadline(
        anchor=expires_on,
        anchor_name="permit expiry",
        due_on=expires_on,
        days_remaining=days,
        klass=classify(days),
    )

    rule = permit_rule(permit.permit_type)
    has_rule = rule is not None
    checks.append(
        Check(
            "renewal_path_known",
            has_rule,
            f"{rule.label}: {rule.action}"
            if rule
            else f"the rulebook has no renewal path recorded for permit type {permit.permit_type!r}",
        )
    )
    if rule is None:
        return _result(
            Outcome.DECIDE,
            checks,
            kind=kind,
            item_id=item_id,
            label=label,
            address=address,
            deadline=deadline,
            missing=(
                f"which DOB filing renews a {permit.permit_type} permit; "
                "the rulebook does not carry one with a citation",
            ),
        )

    in_window = deadline.klass is not Klass.CLEAR
    checks.append(
        Check(
            "within_action_window",
            in_window,
            f"{deadline} against a {DUE_DAYS} day action window",
        )
    )
    if not in_window:
        return _result(
            Outcome.HOLD,
            checks,
            kind=kind,
            item_id=item_id,
            label=label,
            address=address,
            deadline=deadline,
            rule=rule,
        )

    if deadline.klass is Klass.LAPSED:
        # A lapsed permit is never a filing this agent can draft on its own,
        # and the reason is in DOB's own rule rather than in caution. 1 RCNY
        # 102-04(a)(2) bars the renewal until the unpermitted work penalty is
        # paid, and 102-04(d)(6) waives that penalty where the permit expired
        # and no work was performed after it. Which of those applies turns on
        # one fact that exists only on the site, and no dataset holds it. So
        # the engine stops here and puts the question to the person who knows.
        grace = rule.grace_days
        renewable = grace is not None and abs(days) <= grace
        checks.append(
            Check(
                "renewable_after_lapse",
                renewable,
                f"lapsed {abs(days)} days ago against a "
                f"{grace if grace is not None else 'not published'} day renewal window",
            )
        )
        if not renewable:
            return _result(
                Outcome.DECIDE,
                checks,
                kind=kind,
                item_id=item_id,
                label=label,
                address=address,
                deadline=deadline,
                rule=rule,
                missing=(
                    f"whether job {permit.job}/{permit.job_doc} at {permit.address} "
                    f"is still live. The permit lapsed {abs(days)} days ago, past the "
                    "window in which DOB will renew rather than make you file again",
                ),
            )
        return _result(
            Outcome.DECIDE,
            checks,
            kind=kind,
            item_id=item_id,
            label=label,
            address=address,
            deadline=deadline,
            rule=rule,
            missing=(
                rule.lapsed_question
                or (
                    f"whether any work was done at {permit.address} after this permit "
                    "expired, because DOB will not renew it until the unpermitted work "
                    "penalty is paid or waived"
                ),
            ),
        )

    return _result(
        Outcome.FILE,
        checks,
        kind=kind,
        item_id=item_id,
        label=label,
        address=address,
        deadline=deadline,
        rule=rule,
    )


def decide_violation(
    violation: Violation, *, today: date, reading: StatusReading | None = None
) -> Verdict:
    """A violation's verdict. One soft check, and the model may replace it."""
    kind, item_id = "violation", violation.violation_id or violation.number
    label = f"{violation.type_code} {violation.number}"
    address = violation.address
    checks: list[Check] = []

    active = violation.category_is_active
    checks.append(
        Check(
            "category_active",
            active,
            f"DOB categorises this as {violation.category!r}",
        )
    )
    if not active:
        return _result(Outcome.HOLD, checks, kind=kind, item_id=item_id, label=label, address=address)

    disposed = violation.disposition_date is not None
    checks.append(
        Check(
            "not_disposed",
            not disposed,
            f"DOB recorded a disposition on {violation.disposition_date}"
            if disposed
            else "DOB has recorded no disposition date",
        )
    )
    if disposed:
        return _result(Outcome.HOLD, checks, kind=kind, item_id=item_id, label=label, address=address)

    known = violation.issued_on is not None
    checks.append(
        Check(
            "issue_date_known",
            known,
            f"issued {violation.issued_on}"
            if known
            else "issue_date is blank or unparseable, so no response clock can be started",
        )
    )
    if not known:
        return _result(
            Outcome.DECIDE,
            checks,
            kind=kind,
            item_id=item_id,
            label=label,
            address=address,
            missing=(f"the date DOB issued violation {violation.number}",),
        )

    text_check = (
        _reading_check(reading)
        if reading is not None and reading.usable
        else outstanding_by_text(violation.disposition_comments)
    )
    checks.append(text_check)
    if not text_check.passed:
        return _result(Outcome.HOLD, checks, kind=kind, item_id=item_id, label=label, address=address)

    rule = violation_rule(violation.type_code)
    has_rule = rule is not None
    checks.append(
        Check(
            "cure_path_known",
            has_rule,
            f"{rule.label}: {rule.action}"
            if rule
            else f"the rulebook has no cure path recorded for violation type {violation.type_code!r}",
        )
    )
    if rule is None:
        return _result(
            Outcome.DECIDE,
            checks,
            kind=kind,
            item_id=item_id,
            label=label,
            address=address,
            missing=(
                f"which DOB filing closes a type {violation.type_code} violation; "
                "the rulebook does not carry one with a citation",
            ),
        )

    # Whose obligation this is. A violation attaches to a building, and for the
    # periodic filing classes the city names the owner, not whoever happens to
    # hold a permit there: Admin Code 28-303.7 says "the owner shall file" the
    # annual boiler report, 28-305.4.2 says "Owners of retaining walls ... shall
    # comply". Surfacing those to a plumbing contractor would be handing them
    # somebody else's paperwork, and a queue full of somebody else's paperwork
    # is a queue nobody opens.
    mine = rule.respondent != "owner"
    checks.append(
        Check(
            "contractor_is_respondent",
            mine,
            f"the city names the {rule.respondent} on a {rule.label}"
            + (f": {rule.respondent_quote}" if rule.respondent_quote else ""),
        )
    )
    if not mine:
        return _result(
            Outcome.HOLD,
            checks,
            kind=kind,
            item_id=item_id,
            label=label,
            address=address,
            rule=rule,
        )

    if rule.window_days is None:
        return _result(
            Outcome.DECIDE,
            checks,
            kind=kind,
            item_id=item_id,
            label=label,
            address=address,
            rule=rule,
            missing=(
                f"when a {rule.label} response is due. DOB publishes the cure path "
                f"({rule.artifact}) but no deadline this engine could find, so the "
                "clock on this one is yours to set",
            ),
        )

    issued_on = violation.issued_on
    due_on = issued_on + timedelta(days=rule.window_days)
    days = (due_on - today).days
    deadline = Deadline(
        anchor=issued_on,
        anchor_name="violation issued",
        due_on=due_on,
        days_remaining=days,
        klass=classify(days),
    )

    in_window = deadline.klass is not Klass.CLEAR
    checks.append(
        Check(
            "within_action_window",
            in_window,
            f"{deadline}, from a {rule.window_days} day response window",
        )
    )
    if not in_window:
        return _result(
            Outcome.HOLD,
            checks,
            kind=kind,
            item_id=item_id,
            label=label,
            address=address,
            deadline=deadline,
            rule=rule,
        )

    if deadline.klass is Klass.LAPSED and rule.default_days is not None:
        overdue = abs(days)
        before_default = overdue <= rule.default_days
        checks.append(
            Check(
                "before_default",
                before_default,
                f"{overdue} days past the response date against a "
                f"{rule.default_days} day window before a default is entered",
            )
        )
        if not before_default:
            return _result(
                Outcome.DECIDE,
                checks,
                kind=kind,
                item_id=item_id,
                label=label,
                address=address,
                deadline=deadline,
                rule=rule,
                missing=(
                    f"how you want to handle violation {violation.number}. It is "
                    f"{overdue} days past its response date, so a penalty is already "
                    "in play and curing, contesting or paying are all still open to "
                    "you. That call is yours, not mine",
                ),
            )

    return _result(
        Outcome.FILE,
        checks,
        kind=kind,
        item_id=item_id,
        label=label,
        address=address,
        deadline=deadline,
        rule=rule,
    )
