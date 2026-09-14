"""One unattended pass over a contractor's portfolio.

This is what the scheduler invokes. Nobody is watching it, so it prints one
JSON object per line and it never asks a question it could answer itself.

The pass runs in two stages and the order is the whole cost argument. Stage one
is the deadline engine over every permit and every violation, which is pure
arithmetic, costs nothing, and ends in HOLD for most of them. Stage two hands
only the survivors to the model. On the portfolio in the README that is 238
items down to a few dozen, so the model reads the ones where reading changes
something and never sees the 200 that a date comparison already settled.

The filter is safe in the one direction that matters. Stage one's text check is
a shallow keyword list that errs towards leaving things open, so an item it
passes forward can still be closed by the model's read in stage two. An item it
holds was held on structured fields, not on prose.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from typing import Iterable

from agent.engine.deadline import Outcome, Verdict, decide_permit, decide_violation
from agent.engine.portfolio import CONTRACTOR, Portfolio, fetch, load_snapshot
from agent.lapse_agent import CaseSink, DynamoSink, FileSink, build_agent, case_id, verdict_record


def _emit(**payload) -> None:
    print(json.dumps(payload, default=str), flush=True)


def triage(portfolio: Portfolio, *, today: date) -> list[tuple[str, str, Verdict]]:
    """Every item in the portfolio, with the engine's verdict, in urgency order.

    Sorted so a reader sees the worst first: FILE before DECIDE before HOLD,
    then by days remaining. A lapsed permit and a violation due in three days
    interleave correctly because both carry the same deadline shape.
    """
    out: list[tuple[str, str, Verdict]] = []
    for permit in portfolio.permits:
        verdict = decide_permit(permit, portfolio.job_for(permit), today=today)
        out.append(("permit", permit.permit_id or permit.label, verdict))
    for violation in portfolio.violations:
        verdict = decide_violation(violation, today=today)
        out.append(("violation", violation.violation_id or violation.number, verdict))

    order = {Outcome.FILE: 0, Outcome.DECIDE: 1, Outcome.HOLD: 2}
    out.sort(
        key=lambda t: (
            order[t[2].outcome],
            t[2].deadline.days_remaining if t[2].deadline else 10**6,
        )
    )
    return out


def summarise(triaged: Iterable[tuple[str, str, Verdict]]) -> dict:
    counts: dict[str, int] = {}
    classes: dict[str, int] = {}
    for kind, _, verdict in triaged:
        counts[verdict.outcome.value] = counts.get(verdict.outcome.value, 0) + 1
        counts[kind] = counts.get(kind, 0) + 1
        if verdict.deadline:
            key = verdict.deadline.klass.value
            classes[key] = classes.get(key, 0) + 1
    return {"outcomes": counts, "classes": classes}


def _record_type(only: str | None, approvals: set[str] | None) -> str:
    """A sweep and a single approval are not the same kind of event.

    The console reads the newest `run` record to say how much of the portfolio
    the last pass covered. A pass aimed at one approved case screens the same
    235 items but opens one, so filing it as a `run` makes the console report a
    sweep that opened one case. It is a different event and it gets a different
    record_type, which the console ignores for headline numbers.
    """
    return "approval" if (only or approvals) else "run"


def record_run(contractor: str, counts: dict, *, sink: CaseSink, record_type: str = "run") -> None:
    """Write down what the pass actually covered.

    Without this the console can only count the cases it can see, which makes
    it report "screened 37 items" after a pass that screened 238. The number a
    person reads has to come from the run, not from its leftovers.

    It shares the cases table under a `run#` sort key rather than getting a
    table of its own: the console already has read access to exactly one table,
    and widening that to report throughput is a bad trade.
    """
    from datetime import timezone

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sink.write(
        {
            "contractor": contractor,
            "case_id": f"run#{now}",
            "record_type": record_type,
            "status": "run_summary" if record_type == "run" else "approval_summary",
            "finished_at": now,
            "created_at": now,
            "updated_at": now,
            "timeline": [{"at": now, "event": "run_finished", "detail": json.dumps(counts)}],
            **counts,
        }
    )


def run(
    *,
    live: bool,
    sink: CaseSink,
    today: date | None = None,
    with_model: bool = True,
    limit: int | None = None,
    only: str | None = None,
    contractor: str = CONTRACTOR,
    approvals: set[str] | None = None,
) -> dict:
    portfolio = fetch(contractor, today=today) if live else load_snapshot(today=today)
    as_of = today or portfolio.as_of

    _emit(
        event="run_started",
        contractor=portfolio.contractor,
        permits=len(portfolio.permits),
        violations=len(portfolio.violations),
        jobs=len(portfolio.jobs),
        sites=len(portfolio.sites),
        bins=len(portfolio.bins),
        as_of=as_of.isoformat(),
        source=portfolio.source,
    )

    triaged = triage(portfolio, today=as_of)
    stats = summarise(triaged)
    _emit(event="triage", **stats)

    actionable = [(k, i, v) for k, i, v in triaged if v.outcome is not Outcome.HOLD]
    if only:
        actionable = [t for t in actionable if t[1] == only]
    if limit is not None:
        actionable = actionable[:limit]

    for kind, item_id, verdict in triaged:
        if verdict.outcome is Outcome.HOLD:
            _emit(
                event="hold",
                kind=kind,
                item=item_id,
                label=verdict.label,
                address=verdict.address,
                why=next((str(c) for c in verdict.failed), "nothing is due yet"),
            )

    counts = {
        "permits_screened": len(portfolio.permits),
        "violations_screened": len(portfolio.violations),
        "items_screened": len(triaged),
        "held": sum(1 for _, _, v in triaged if v.outcome is Outcome.HOLD),
        "engine_file": sum(1 for _, _, v in triaged if v.outcome is Outcome.FILE),
        "engine_decide": sum(1 for _, _, v in triaged if v.outcome is Outcome.DECIDE),
        "classes": stats["classes"],
        "source": portfolio.source,
        "as_of": as_of.isoformat(),
    }

    if not with_model:
        for kind, item_id, verdict in actionable:
            _emit(
                event="actionable",
                kind=kind,
                item=item_id,
                label=verdict.label,
                address=verdict.address,
                outcome=verdict.outcome.value,
                klass=verdict.deadline.klass.value if verdict.deadline else None,
                due_on=verdict.deadline.due_on.isoformat() if verdict.deadline else None,
                days=verdict.deadline.days_remaining if verdict.deadline else None,
                action=verdict.action,
                artifact=verdict.artifact,
                citation=verdict.citation,
                missing=list(verdict.missing),
            )
        counts.update({"cases_opened": 0, "drafted": 0, "filed": 0, "vetoed": 0, "asked": 0})
        record_run(portfolio.contractor, counts, sink=sink, record_type=_record_type(only, approvals))
        _emit(event="run_finished", **counts)
        return counts

    agent, ledger, events = build_agent(
        portfolio, sink=sink, approvals=approvals, today=as_of
    )

    # One item per turn. A single prompt carrying 238 items would spend its
    # context on the 200 the engine already settled, and a stall on one item
    # would take the rest of the portfolio down with it.
    for kind, item_id, verdict in actionable:
        if kind == "permit":
            instruction = (
                f"Check permit {item_id} and finish it. It is {verdict.label} at "
                f"{verdict.address}."
            )
        else:
            instruction = (
                f"Check violation {item_id} and finish it. It is {verdict.label} at "
                f"{verdict.address}. Read its disposition comments before you judge it."
            )
        agent(instruction)

    counts.update(
        {
            "considered": ledger.considered,
            "cases_opened": len(ledger.cases),
            "drafted": len(ledger.drafts),
            "awaiting_approval": len(ledger.pending_approval),
            "needs_decision": len(ledger.asked),
            "filed": len(ledger.filed),
            "vetoed": sum(1 for e in events if e["event"] == "veto"),
            "agent_held": sum(
                1
                for cid, v in ledger.verdicts.items()
                if v.outcome is Outcome.HOLD
            ),
        }
    )
    record_run(portfolio.contractor, counts, sink=sink, record_type=_record_type(only, approvals))
    _emit(event="run_finished", **counts)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one Lapse pass over a contractor's DOB portfolio."
    )
    parser.add_argument(
        "--live", action="store_true", help="fetch NYC Open Data instead of the captured snapshot"
    )
    parser.add_argument(
        "--engine-only",
        action="store_true",
        help="run the deadline engine and stop, without calling the model",
    )
    parser.add_argument("--dynamo", action="store_true", help="persist cases to DynamoDB")
    parser.add_argument("--limit", type=int, help="cap how many actionable items reach the model")
    parser.add_argument("--only", help="restrict the pass to one DOB item id")
    parser.add_argument("--contractor", default=CONTRACTOR, help="permittee business name")
    parser.add_argument("--today", help="evaluate deadlines as of this ISO date")
    parser.add_argument(
        "--approve",
        action="append",
        default=[],
        help="a case id the contractor has approved; may be repeated",
    )
    args = parser.parse_args()

    sink: CaseSink = DynamoSink() if args.dynamo else FileSink()
    summary = run(
        live=args.live,
        sink=sink,
        today=date.fromisoformat(args.today) if args.today else None,
        with_model=not args.engine_only,
        limit=args.limit,
        only=args.only,
        contractor=args.contractor,
        approvals=set(args.approve),
    )
    return 0 if summary["items_screened"] else 1


if __name__ == "__main__":
    sys.exit(main())
