"""What the city actually requires, and where it says so.

Every deadline Lapse computes traces back to a rule in `data/rulebook.json`,
and every rule in that file carries the URL it was read from and the sentence
it was read out of. That is not documentation, it is enforced:
`tests/test_rulebook.py` fails the suite if any rule carries a citation that is
not an https URL or a quote shorter than a sentence. A rule nobody can check is
a rule this program will not act on.

The file is data, not code, for two reasons. A rulebook changes when the city
changes its mind, which is more often than this program changes. And the shape
generalises: the permit type keys are DOB's, but a contractor in Chicago or
Los Angeles swaps the file rather than the engine.

Three numbers per rule, and they mean different things:

    window_days   how long after the anchor date the published action is due.
                  None means the city publishes the cure path but no deadline,
                  and the engine then refuses to invent one: the item goes to
                  DECIDE with "the clock on this one is yours to set".
    grace_days    for permits, how long after expiry the same renewal is still
                  available. None means renewal after expiry is not a published
                  path, so a lapsed permit becomes a question rather than a
                  filing.
    default_days  how long past the response date before the city enters a
                  default and a penalty attaches. Past that point Lapse stops
                  drafting and asks, because cure, contest and pay are all
                  still open and choosing between them is the contractor's
                  call, not an agent's.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

RULEBOOK = Path(__file__).parent.parent.parent / "data" / "rulebook.json"


@dataclass(frozen=True)
class Rule:
    key: str
    applies_to: str
    label: str
    action: str
    artifact: str
    window_days: int | None
    grace_days: int | None
    default_days: int | None
    citation: str
    quote: str
    lapsed_question: str = ""
    respondent: str = "either"
    respondent_citation: str = ""
    respondent_quote: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "applies_to": self.applies_to,
            "label": self.label,
            "action": self.action,
            "artifact": self.artifact,
            "window_days": self.window_days,
            "grace_days": self.grace_days,
            "default_days": self.default_days,
            "lapsed_question": self.lapsed_question,
            "respondent": self.respondent,
            "respondent_citation": self.respondent_citation,
            "respondent_quote": self.respondent_quote,
            "citation": self.citation,
            "quote": self.quote,
        }


class RulebookError(RuntimeError):
    pass


def _coerce(entry: dict, applies_to: str) -> Rule:
    missing = [f for f in ("key", "label", "action", "artifact", "citation", "quote") if not entry.get(f)]
    if missing:
        raise RulebookError(
            f"{applies_to} rule {entry.get('key', '?')!r} is missing {missing}; "
            "a rule with no source is not a rule this program will act on"
        )
    return Rule(
        key=entry["key"],
        applies_to=applies_to,
        label=entry["label"],
        action=entry["action"],
        artifact=entry["artifact"],
        window_days=entry.get("window_days"),
        grace_days=entry.get("grace_days"),
        default_days=entry.get("default_days"),
        citation=entry["citation"],
        quote=entry["quote"],
        lapsed_question=entry.get("lapsed_question", ""),
        respondent=entry.get("respondent", "either"),
        respondent_citation=entry.get("respondent_citation", ""),
        respondent_quote=entry.get("respondent_quote", ""),
    )


@lru_cache(maxsize=1)
def load() -> tuple[dict[str, Rule], dict[str, Rule], dict]:
    blob = json.loads(RULEBOOK.read_text())
    permits = {e["key"]: _coerce(e, "permit") for e in blob.get("permits", [])}
    violations = {e["key"]: _coerce(e, "violation") for e in blob.get("violations", [])}
    if not permits or not violations:
        raise RulebookError("the rulebook has no permit rules or no violation rules")
    return permits, violations, blob.get("meta", {})


def permit_rule(permit_type: str) -> Rule | None:
    permits, _, _ = load()
    return permits.get((permit_type or "").strip().upper())


def violation_rule(type_code: str) -> Rule | None:
    _, violations, _ = load()
    return violations.get((type_code or "").strip().upper())


def all_rules() -> tuple[Rule, ...]:
    permits, violations, _ = load()
    return tuple(permits.values()) + tuple(violations.values())


def meta() -> dict:
    return load()[2]
