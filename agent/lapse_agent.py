"""The Lapse agent.

What the model is for: reading, and writing. A DOB violation carries a sentence
a clerk typed into a free text field ("DELETED BY CAW ON 05/23/23 BECAUSE
REMOVE FROM FISP 9A") and a permit carries a job description an architect typed
("REPLACE DETERIORATED BRICK, TERRA COTTA, LIMESTONE, AND GRANITE"). Deciding
what the first one means, and turning the second into a renewal request a plan
examiner will accept, is reading and writing.

What the model is not for: deciding. Whether a deadline is inside the action
window, whether a permit was already superseded by a later sequence, whether
the job was signed off two years ago, is arithmetic and joins, and it is done
in agent/engine/deadline.py where no prompt reaches it.

The seam between those two facts is enforced twice, on purpose:

  1. `read_disposition` accepts the model's read of DOB's free text but returns
     the verdict computed from it, so the model learns the outcome instead of
     choosing it.
  2. `FilingVeto`, a BeforeToolCallEvent hook, cancels `file_response` unless
     the ledger holds a FILE verdict, an item that is still open, and a draft
     for that exact case. A model that decides to send anyway does not send.

Delete the hook and Lapse becomes a program that emails a contractor demands to
renew permits on jobs that closed years ago. That is the test this design is
built to pass, and tests/test_veto.py is where it is proved.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from strands import Agent, tool
from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry
from strands.models.anthropic import AnthropicModel
from strands.vended_interventions import HumanInTheLoop

from agent.engine.deadline import (
    ContractorAnswer,
    Outcome,
    StatusReading,
    Verdict,
    decide_permit,
    decide_violation,
)
from agent.engine.portfolio import Portfolio
from agent.feeds.permits import Permit
from agent.feeds.violations import Violation
from agent.store import CaseStore

MODEL_ID = os.environ.get("LAPSE_MODEL", "claude-sonnet-4-5-20250929")
DATA = Path(__file__).parent.parent / "data"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def case_id(contractor: str, kind: str, item_id: str) -> str:
    """Same contractor, same item, same case, however many times we run."""
    return CaseStore.case_id(contractor, kind, item_id)


def verdict_record(verdict: Verdict) -> dict:
    deadline = verdict.deadline
    return {
        "outcome": verdict.outcome.value,
        "klass": deadline.klass.value if deadline else None,
        "due_on": deadline.due_on.isoformat() if deadline else None,
        "days_remaining": deadline.days_remaining if deadline else None,
        "anchor_name": deadline.anchor_name if deadline else None,
        "checks": [asdict(c) for c in verdict.checks],
        "missing": list(verdict.missing),
        "action": verdict.action,
        "artifact": verdict.artifact,
        "citation": verdict.citation,
        "evidence_id": verdict.evidence_id,
        "question_shape": verdict.question_shape,
        "choices": list(verdict.choices),
    }


@dataclass
class Ledger:
    """What this pass has established, and the only thing the veto trusts."""

    contractor: str
    permits: dict[str, Permit]
    violations: dict[str, Violation]
    portfolio: Portfolio
    today: date
    verdicts: dict[str, Verdict] = field(default_factory=dict)
    drafts: dict[str, str] = field(default_factory=dict)
    cases: dict[str, dict] = field(default_factory=dict)
    filed: set[str] = field(default_factory=set)
    approvals: set[str] = field(default_factory=set)
    pending_approval: set[str] = field(default_factory=set)
    asked: set[str] = field(default_factory=set)
    answers: dict[str, ContractorAnswer] = field(default_factory=dict)
    considered: int = 0

    def record(self, cid: str, verdict: Verdict) -> None:
        self.verdicts[cid] = verdict

    def may_file(self, cid: str) -> str | None:
        """The reason filing is refused, or None if it may proceed.

        Four conditions, and the third is the one that is easy to forget. A
        verdict computed twenty minutes ago said the item was open. Between
        then and now the agent may have been told something, or a rerun may
        have loaded a newer snapshot in which DOB disposed of it. So openness
        is re-read off the checks on the verdict that is in the ledger right
        now, not remembered from when the case was opened.
        """
        verdict = self.verdicts.get(cid)
        if verdict is None:
            return f"no verdict has been computed for case {cid}"
        if verdict.outcome is not Outcome.FILE:
            failed = ", ".join(c.name for c in verdict.failed) or "a decision that is not mine"
            return (
                f"case {cid} is {verdict.outcome.value}, not FILE "
                f"(failing: {failed}). A response may only be filed on a FILE verdict."
            )
        closed = [
            c.name
            for c in verdict.checks
            if c.name in {"permit_live", "not_superseded", "job_open", "category_active", "not_disposed"}
            and not c.passed
        ]
        if closed:
            return (
                f"case {cid} is no longer open: {', '.join(closed)} now fails. "
                "Nothing is filed against a closed item."
            )
        if cid not in self.drafts:
            return f"case {cid} has no drafted response yet"
        if cid in self.filed:
            return f"case {cid} was already filed; it will not be sent twice"
        return None


class FilingVeto(HookProvider):
    """The check that cannot be argued with, because it is not in the prompt."""

    def __init__(self, ledger: Ledger, log: Callable[[str, str], None]) -> None:
        self.ledger = ledger
        self.log = log

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.inspect)

    def inspect(self, event: BeforeToolCallEvent) -> None:
        if event.tool_use.get("name") != "file_response":
            return
        cid = (event.tool_use.get("input") or {}).get("case_id", "")
        refusal = self.ledger.may_file(cid)
        if refusal:
            self.log("veto", refusal)
            event.cancel_tool = f"REFUSED by the filing veto: {refusal}"


def approval_gate(ledger: Ledger, log: Callable[[str, str], None]) -> HumanInTheLoop:
    """The one call a person has to make.

    Everything else the agent does is reversible: reading a violation, computing
    a deadline, opening a case, drafting a renewal request. Sending a contractor
    an instruction to file something with the city, under their licence, is not,
    so it is the single tool that can never be trusted away. `allowed_tools` is
    a wildcard with `file_response` negated, which in Strands means it always
    requires approval even if a caller has trusted everything else this session.

    In a scheduled run nobody is at a terminal, so the gate does not block. It
    records the case as waiting for a person and lets the pass continue to the
    next item. The console is where the answer comes back: an approved case id
    is handed to the next run, and the same gate then lets it through.

    The veto hook still runs underneath this. Approval is permission to send
    something that already passed every check; it is never permission to skip
    the checking.
    """

    def ask(prompt: str, **_: Any) -> str:
        try:
            payload = json.loads(prompt.split("Input: ", 1)[1])
            cid = payload.get("case_id", "")
        except (IndexError, ValueError):
            cid = ""
        if cid and cid in ledger.approvals:
            log("approved", f"{cid} was approved by the contractor")
            return "yes"
        ledger.pending_approval.add(cid)
        case = ledger.cases.get(cid)
        if case is not None:
            case["status"] = "awaiting_approval"
            case["timeline"].append(
                {
                    "at": _now(),
                    "event": "approval_requested",
                    "detail": "The response is drafted and waiting for the contractor to send it.",
                }
            )
        log("awaiting_approval", f"{cid} is drafted and waiting for a person")
        return "no"

    def evaluate(response: Any, **_: Any) -> bool:
        return str(response).strip().lower() in {"y", "yes", "approve", "approved", "send"}

    return HumanInTheLoop(allowed_tools=["*", "!file_response"], ask=ask, evaluate=evaluate)


class CaseSink:
    """Where cases go when the pass ends. Both implementations are real.

    `read` matters as much as `write`. A pass that only writes would overwrite
    what an earlier pass learned, and the most expensive thing to forget is
    that a response already went out: the durable guard against sending twice
    is the delivery record on the case, not anything held in memory for one
    run.
    """

    def write(self, case: dict) -> str:
        raise NotImplementedError

    def read(self, contractor: str, case_id: str) -> dict | None:
        return None

    def cases_for(self, contractor: str) -> list[dict]:
        """Every case this contractor has. Used to pick up their answers."""
        return []

    def answers_for(self, contractor: str) -> dict[str, "ContractorAnswer"]:
        """Answers keyed by DOB item id, from whatever the console wrote.

        An answer lives on the case rather than in a table of its own, because
        the thing it answers is a case and a question detached from what it was
        asked about is not evidence of anything.
        """
        from agent.engine.deadline import ContractorAnswer

        out: dict[str, ContractorAnswer] = {}
        for case in self.cases_for(contractor):
            recorded = case.get("answer") or {}
            item_id = (case.get("item") or {}).get("item_id")
            if not (recorded.get("value") and item_id):
                continue
            out[item_id] = ContractorAnswer(
                value=str(recorded["value"]).strip().lower(),
                answers_evidence_id=recorded.get("answers_evidence_id", ""),
                answered_at=recorded.get("at", ""),
                answered_by=recorded.get("by", "the contractor"),
            )
        return out


class FileSink(CaseSink):
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or DATA / "cases"
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, case: dict) -> str:
        path = self.root / f"{case['case_id']}.json"
        path.write_text(json.dumps(case, indent=2, default=str))
        return str(path)

    def read(self, contractor: str, case_id: str) -> dict | None:
        path = self.root / f"{case_id}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def cases_for(self, contractor: str) -> list[dict]:
        cases = []
        for path in self.root.glob("*.json"):
            case = json.loads(path.read_text())
            if case.get("contractor") == contractor:
                cases.append(case)
        return cases


class DynamoSink(CaseSink):
    def __init__(self) -> None:
        self.store = CaseStore()

    def write(self, case: dict) -> str:
        self.store.put_case(case)
        return f"dynamodb://lapse-cases/{case['contractor']}/{case['case_id']}"

    def read(self, contractor: str, case_id: str) -> dict | None:
        return self.store.get_case(contractor, case_id)

    def cases_for(self, contractor: str) -> list[dict]:
        return self.store.list_cases(contractor)


SYSTEM_PROMPT = """You work for one construction contractor in New York City. Your job is to make sure nothing in their portfolio lapses without them knowing, and to have the paperwork already written when something is about to.

A permit does not fail loudly. It expires. A violation does not chase anybody. It sits. The failure mode in this whole domain is silence, and your job is to break it exactly once per item and then be quiet again.

You are reading two kinds of text the city wrote and nobody edited.

The first is a violation's disposition comments. DOB clerks type things like "DELETED BY CAW ON 05/23/23 BECAUSE REMOVE FROM FISP 9A" or "NOT REQUIRED TO FILE CYCLE 9" or "S/B AT 215 CHRYSTIE STREET BN#1090397". Those mean the violation is not this contractor's problem, even though the structured category field still says ACTIVE. Telling that apart from a comment that does not close anything is your work and you are good at it. Say what specifically convinced you, quoting the words.

The second is a job description. "REPLACE DETERIORATED BRICK, TERRA COTTA, LIMESTONE, AND GRANITE. REFURBISH AND/OR REPLACE SASHES IN EXISTING WOOD WINDOWS." That is what the renewal is for, and a renewal request that names the work reads like a professional wrote it, which is the point.

What is not your job: deciding whether anything is due. Dates, supersession and job status are checked outside you and you will be told the result. If you are told HOLD, that is the answer. Do not argue, do not retry with different wording, do not file anyway. A false alarm costs a contractor an afternoon and, worse, teaches them to stop reading what you send.

Work one item at a time:

1. For a violation, call read_violation to see it, then read_disposition with your honest read: is it still open, how confident are you, and which words decided it. read_disposition returns the computed verdict.
2. For a permit, call check_permit. There is no prose on a permit, so there is nothing for you to read and the verdict comes straight back.
3. On FILE, call open_case, then draft_response, then file_response.

   file_response tells you where the response actually went, and you repeat that exactly. If it comes back in a mode other than "direct", nothing has reached the contractor: say plainly where it went and why. Never tell them their filing desk has something when it does not.

   file_response is the one thing you cannot do alone. When the answer comes back "waiting for a person", that is the system working. Say so once and move on to the next item. Do not retry it, do not reword the draft to get a different answer, and do not claim it was sent.
4. On DECIDE, call open_case and then ask_contractor with the single question in the verdict's missing list. One question, in their words, not a form. Then stop on that item.
5. On HOLD, do nothing further. Silence is the correct output and most of your work will be silence.

When you write a response, write what a competent filing agent would write: the DOB identifier the city routes on (the job number for a permit, the violation number for a violation), the address, what the work is, the deadline and the date it falls, and the specific filing the rulebook names. Cite the rule's URL. No greetings, no apology, no urgency theatre, no invented DOB form numbers, no invented fee amounts. Eight sentences at most.

You cannot file anything with the city and you must never imply otherwise. DOB NOW takes a filing from a licensed person under their own login. What you produce is the text and the evidence for that filing."""


def build_agent(
    portfolio: Portfolio,
    *,
    sink: CaseSink | None = None,
    model_id: str = MODEL_ID,
    approvals: set[str] | None = None,
    today: date | None = None,
    answers: dict[str, ContractorAnswer] | None = None,
) -> tuple[Agent, Ledger, list[dict]]:
    contractor = portfolio.contractor
    ledger = Ledger(
        contractor=contractor,
        permits={p.permit_id or p.label: p for p in portfolio.permits},
        violations={v.violation_id or v.number: v for v in portfolio.violations},
        portfolio=portfolio,
        today=today or portfolio.as_of,
        approvals=set(approvals or ()),
        answers=dict(answers or {}),
    )
    sink = sink or FileSink()
    events: list[dict] = []

    def log(event: str, detail: str) -> None:
        entry = {"at": _now(), "event": event, "detail": detail}
        events.append(entry)
        print(json.dumps(entry), flush=True)

    def _item_and_job(kind: str, item_id: str):
        if kind == "permit":
            permit = ledger.permits.get(item_id)
            return permit, (portfolio.job_for(permit) if permit else None)
        return ledger.violations.get(item_id), None

    def _verdict_text(cid: str, verdict: Verdict) -> str:
        detail = "\n".join(f"  {c}" for c in verdict.checks)
        extra = f"\nOne question decides it: {'; '.join(verdict.missing)}" if verdict.missing else ""
        rule = f"\nRulebook: {verdict.action} ({verdict.artifact}) {verdict.citation}" if verdict.action else ""
        return f"case_id {cid}\nverdict {verdict.outcome.value}\n{detail}{rule}{extra}"

    @tool
    def read_violation(violation_id: str) -> str:
        """Everything DOB recorded about one violation, including its free text.

        Args:
            violation_id: DOB's isn_dob_bis_viol for the violation, e.g. 2817783.
        """
        violation = ledger.violations.get(violation_id)
        if violation is None:
            return f"No violation {violation_id}. Known: {sorted(ledger.violations)[:12]}"
        ledger.considered += 1
        return (
            f"violation {violation.number} (DOB id {violation.violation_id})\n"
            f"  issued: {violation.issued_on}\n"
            f"  type: {violation.type_label}\n"
            f"  category: {violation.category}\n"
            f"  building: {violation.address} (BIN {violation.bin})\n"
            f"  device: {violation.device_number or 'none'}\n"
            f"  what the inspector wrote: {violation.description or '(nothing)'}\n"
            f"  disposition date: {violation.disposition_date or '(none)'}\n"
            f"  disposition comments: {violation.disposition_comments or '(nothing)'}"
        )

    @tool
    def read_disposition(
        violation_id: str, still_open: bool, confidence: float, reason: str
    ) -> str:
        """Record your read of DOB's free text on a violation, and get the verdict.

        Your read replaces the lexical keyword test only. The category, the
        disposition date, the rulebook's response window and the arithmetic are
        checked regardless of what you say here.

        Args:
            violation_id: DOB's isn_dob_bis_viol for the violation.
            still_open: True if the free text leaves this outstanding against this building.
            confidence: 0.0 to 1.0, your honest confidence.
            reason: The specific words that decided it for you.
        """
        violation = ledger.violations.get(violation_id)
        if violation is None:
            return f"No violation {violation_id}."
        reading = StatusReading(
            still_open=still_open, confidence=confidence, reason=reason, read_by=model_id
        )
        verdict = decide_violation(
            violation,
            today=ledger.today,
            reading=reading,
            answer=ledger.answers.get(violation_id),
        )
        cid = case_id(contractor, "violation", violation_id)
        ledger.record(cid, verdict)
        log(
            "verdict",
            f"violation {violation.number}: {verdict.outcome.value} "
            f"({len(verdict.passed)} checks passed, {len(verdict.failed)} failed)",
        )
        return _verdict_text(cid, verdict)

    @tool
    def check_permit(permit_id: str) -> str:
        """Compute the verdict for one permit. No reading required, and none accepted.

        Args:
            permit_id: DOB's permit_si_no for the permit.
        """
        permit = ledger.permits.get(permit_id)
        if permit is None:
            return f"No permit {permit_id}. Known: {sorted(ledger.permits)[:12]}"
        ledger.considered += 1
        job = portfolio.job_for(permit)
        # The contractor's answer to an earlier question is applied here too,
        # not only in the pass's own triage. If it were applied in one place and
        # not the other, the queue and the agent would disagree about whether a
        # question was still open, and the contractor would be asked twice.
        verdict = decide_permit(
            permit, job, today=ledger.today, answer=ledger.answers.get(permit_id)
        )
        cid = case_id(contractor, "permit", permit_id)
        ledger.record(cid, verdict)
        log(
            "verdict",
            f"permit {permit.label}: {verdict.outcome.value} "
            f"({len(verdict.passed)} checks passed, {len(verdict.failed)} failed)",
        )
        header = (
            f"permit {permit.label} at {permit.address}\n"
            f"  expires: {permit.expires_on}\n"
            f"  job filing: {job.status_text if job else 'no filing record found'}\n"
            f"  work: {job.description if job and job.description else '(no description filed)'}\n"
        )
        return header + _verdict_text(cid, verdict)

    @tool
    def open_case(kind: str, item_id: str) -> str:
        """Persist a case so it survives this pass.

        Args:
            kind: Either "permit" or "violation".
            item_id: The DOB identifier for that item.
        """
        if kind not in ("permit", "violation"):
            return "kind must be 'permit' or 'violation'."
        cid = case_id(contractor, kind, item_id)
        verdict = ledger.verdicts.get(cid)
        if verdict is None:
            return (
                f"Nothing to open: call "
                f"{'check_permit' if kind == 'permit' else 'read_disposition'} "
                f"for {item_id} first."
            )
        item, job = _item_and_job(kind, item_id)
        if item is None:
            return f"No {kind} {item_id} in this portfolio."
        status = "awaiting_approval" if verdict.outcome is Outcome.FILE else "needs_decision"
        case = {
            "contractor": contractor,
            "case_id": cid,
            "record_type": "case",
            "status": status,
            "kind": kind,
            "item": item.to_dict(),
            "job": job.to_dict() if job is not None else None,
            "verdict": verdict_record(verdict),
            "draft_text": None,
            "question": None,
            "timeline": [],
            "delivery": None,
            "created_at": _now(),
            "updated_at": _now(),
        }
        # A case this contractor has seen before keeps what the earlier pass
        # learned. Losing the delivery record is the expensive one: it is the
        # only durable proof the response already went out, so dropping it
        # would let a later pass send the same renewal request again.
        previous = sink.read(contractor, cid)
        if previous:
            # A case somebody already opened is not opened again. A pass aimed
            # at one approved case re-derives the same verdict and the same
            # draft, and writing those down a second time turns the ledger into
            # a log of the program's control flow rather than a history of the
            # item. A person reading a case months later wants to know what
            # happened to the permit, not how many times a pass looked at it.
            case["created_at"] = previous.get("created_at", case["created_at"])
            case["timeline"] = list(previous.get("timeline", []))
            for carried in ("delivery", "draft_text", "question"):
                if previous.get(carried):
                    case[carried] = previous[carried]
            if (previous.get("delivery") or {}).get("message_id"):
                case["status"] = previous.get("status", status)
                ledger.filed.add(cid)
                log("already_filed", f"{cid} went out on an earlier pass; not sending again")
            if previous.get("draft_text"):
                ledger.drafts[cid] = previous["draft_text"]
        else:
            case["timeline"] = [
                {"at": _now(), "event": "opened", "detail": f"verdict {verdict.outcome.value}"}
            ]

        ledger.cases[cid] = case
        where = sink.write(case)
        log("case_opened", f"{cid} {case['status']} -> {where}")
        return f"Case {cid} open with status {case['status']}."

    @tool
    def draft_response(case_id_arg: str, draft_text: str) -> str:
        """Attach the text that will go to the contractor's filing desk.

        Args:
            case_id_arg: The case this draft belongs to.
            draft_text: The full response. Must name the DOB identifier the city routes on.
        """
        case = ledger.cases.get(case_id_arg)
        if case is None:
            return f"No open case {case_id_arg}."
        item = case["item"]
        routing = item["job"] if case["kind"] == "permit" else item["number"]
        if routing and routing not in draft_text:
            return (
                f"Rejected: the response must cite {routing} so DOB can route it. "
                "Put it in the text verbatim."
            )
        if len(draft_text.split()) > 260:
            return "Rejected: too long. Eight sentences at most."
        already = case.get("draft_text")
        ledger.drafts[case_id_arg] = draft_text
        case["draft_text"] = draft_text
        if already != draft_text:
            case["timeline"].append(
                {
                    "at": _now(),
                    "event": "redrafted" if already else "drafted",
                    "detail": f"{len(draft_text.split())} words",
                }
            )
        case["updated_at"] = _now()
        sink.write(case)
        log("drafted", f"{case_id_arg} cites {routing}")
        return "Draft attached."

    @tool
    def file_response(case_id: str) -> str:
        """Send the drafted response to the contractor's filing desk.

        Refused unless the verdict is FILE, the item is still open, and a draft
        is attached.

        Args:
            case_id: The case to send.
        """
        from agent.dispatch import send_response

        case = ledger.cases.get(case_id)
        if case is None:
            return f"No open case {case_id}."

        delivery = send_response(case)
        case["delivery"] = delivery
        ledger.filed.add(case_id)
        case["status"] = "filed"
        # The timeline says where it actually went, never where it was aimed.
        # SES is in sandbox, so a response addressed to a filing desk may have
        # gone to the mailbox simulator instead, and a person reading this case
        # months later has to be able to tell which of those happened.
        case["timeline"].append(
            {
                "at": _now(),
                "event": "filed",
                "detail": (
                    f"response sent to {delivery.get('to')} "
                    f"(intended {delivery.get('intended')}, mode {delivery.get('mode')})"
                ),
            }
        )
        case["updated_at"] = _now()
        sink.write(case)
        log("filed", f"{case_id} -> {delivery.get('to')} [{delivery.get('mode')}]")
        return (
            f"Sent to {delivery.get('to')} in {delivery.get('mode')} mode, "
            f"message id {delivery.get('message_id')}. The intended recipient is "
            f"{delivery.get('intended')}."
        )

    @tool
    def ask_contractor(case_id: str, question: str) -> str:
        """Interrupt the contractor, once, with the single question that settles it.

        Args:
            case_id: The case that is stuck.
            question: One plain question. Not a form.
        """
        case = ledger.cases.get(case_id)
        if case is None:
            return f"No open case {case_id}."
        case["question"] = question
        case["status"] = "needs_decision"
        case["timeline"].append({"at": _now(), "event": "asked", "detail": question})
        case["updated_at"] = _now()
        sink.write(case)
        ledger.asked.add(case_id)
        log("asked", f"{case_id}: {question}")
        return "Asked. The case waits until they answer."

    tools = [
        read_violation,
        read_disposition,
        check_permit,
        open_case,
        draft_response,
        file_response,
        ask_contractor,
    ]

    agent = Agent(
        model=AnthropicModel(model_id=model_id, max_tokens=4096),
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
        hooks=[FilingVeto(ledger, log)],
        interventions=[approval_gate(ledger, log)],
    )
    return agent, ledger, events
