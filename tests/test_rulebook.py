"""A rule nobody can check is a rule this program will not act on.

Every deadline Lapse computes comes out of data/rulebook.json, and this file is
what stops that becoming a place to park a number somebody half remembered. A
rule with no https source, or with a quote too short to be a sentence, fails the
suite. Adding an uncited rule breaks the build, which is the point.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from agent.engine.rulebook import RULEBOOK, Rule, RulebookError, all_rules, meta

RULES = all_rules()
RAW = json.loads(RULEBOOK.read_text())


def test_the_rulebook_is_not_empty():
    assert len(RULES) >= 15
    assert any(r.applies_to == "permit" for r in RULES)
    assert any(r.applies_to == "violation" for r in RULES)


@pytest.mark.parametrize("rule", RULES, ids=lambda r: f"{r.applies_to}:{r.key}")
def test_every_rule_carries_a_working_shaped_citation(rule: Rule):
    parsed = urlparse(rule.citation)
    assert parsed.scheme == "https", f"{rule.key} cites {rule.citation!r}, which is not https"
    assert parsed.netloc, f"{rule.key} cites a URL with no host"
    assert parsed.netloc.endswith(("nyc.gov", "amlegal.com")), (
        f"{rule.key} cites {parsed.netloc}, which is not the city or its code publisher"
    )


@pytest.mark.parametrize("rule", RULES, ids=lambda r: f"{r.applies_to}:{r.key}")
def test_every_rule_carries_the_sentence_it_was_read_out_of(rule: Rule):
    assert len(rule.quote.split()) >= 12, (
        f"{rule.key} quotes {rule.quote!r}, which is too short to be the sentence a "
        "reader could find on that page"
    )


@pytest.mark.parametrize("rule", RULES, ids=lambda r: f"{r.applies_to}:{r.key}")
def test_every_rule_names_an_action_and_an_artifact(rule: Rule):
    assert len(rule.action.split()) >= 8, f"{rule.key} does not say what to actually do"
    assert rule.artifact, f"{rule.key} does not name the filing that closes it"


@pytest.mark.parametrize("rule", RULES, ids=lambda r: f"{r.applies_to}:{r.key}")
def test_a_day_count_is_a_day_count(rule: Rule):
    for field in ("window_days", "grace_days", "default_days"):
        value = getattr(rule, field)
        if value is None:
            continue
        assert isinstance(value, int) and value >= 0, f"{rule.key}.{field} is {value!r}"
        assert value <= 3650, f"{rule.key}.{field} is {value}, which is not a deadline"


@pytest.mark.parametrize(
    "rule", [r for r in RULES if r.applies_to == "permit"], ids=lambda r: r.key
)
def test_every_permit_rule_carries_the_question_a_lapse_raises(rule: Rule):
    """A lapsed permit always ends in a question, so the question has to exist."""
    assert len(rule.lapsed_question.split()) >= 10, (
        f"permit rule {rule.key} has no question to put to the contractor when it lapses"
    )


@pytest.mark.parametrize(
    "rule", [r for r in RULES if r.applies_to == "violation"], ids=lambda r: r.key
)
def test_every_violation_rule_names_whose_obligation_it_is(rule: Rule):
    assert rule.respondent in ("owner", "contractor", "either"), (
        f"{rule.key} names respondent {rule.respondent!r}"
    )
    if rule.respondent == "owner":
        assert rule.respondent_quote, (
            f"{rule.key} takes an item off a contractor's queue on the grounds that the "
            "city names the owner, so it has to quote where the city says that"
        )
        assert urlparse(rule.respondent_citation).scheme == "https"


def test_the_rulebook_records_the_conflicts_it_could_not_resolve():
    """Two published NYC sources disagree about permit renewal. Say so.

    Silently picking one and writing it into an engine is how a wrong number
    survives a rewrite. The conflicts are recorded in the file and read here so
    deleting them fails the build.
    """
    conflicts = meta().get("known_conflicts", [])
    assert len(conflicts) >= 2
    assert any("28-105" in c for c in conflicts)


def test_a_rule_with_no_source_is_rejected_at_load():
    """The loader's own refusal, exercised.

    A validator nobody ever proves can reject something is decoration. This
    hands the loader a rule missing its citation and asserts it refuses.
    """
    from agent.engine.rulebook import _coerce

    with pytest.raises(RulebookError) as raised:
        _coerce(
            {
                "key": "XX",
                "label": "Invented rule",
                "action": "do something the city never asked for",
                "artifact": "a form that does not exist",
            },
            "violation",
        )
    assert "citation" in str(raised.value)


def test_the_keys_match_the_codes_the_city_actually_uses():
    """Guards against a rule keyed on a code that appears in no DOB record.

    The permit type codes are the seven that appear in the live permit feed and
    the violation type codes are read off the live violation feed. A key that
    matches nothing is a rule that can never fire, which is worse than a missing
    rule because it looks like coverage.
    """
    live_permit_types = {"EW", "PL", "AL", "NB", "EQ", "FO", "DM"}
    live_violation_codes = {
        "C", "E", "LBLVIO", "HBLVIO", "FISPNRF", "RWNRF", "LL1081",
        "AEUHAZ1", "P", "B", "UB", "Z",
    }
    for rule in RULES:
        known = live_permit_types if rule.applies_to == "permit" else live_violation_codes
        assert rule.key in known, (
            f"{rule.applies_to} rule {rule.key!r} is keyed on a code that does not appear "
            "in the live DOB datasets"
        )


def test_the_engine_can_find_every_rule_by_its_key():
    from agent.engine.rulebook import permit_rule, violation_rule

    for rule in RULES:
        found = permit_rule(rule.key) if rule.applies_to == "permit" else violation_rule(rule.key)
        assert found is not None and found.key == rule.key
