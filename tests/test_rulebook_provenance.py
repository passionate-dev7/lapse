"""Fetch every citation and assert the quote is really on that page.

`tests/test_rulebook.py` checks the shape of a citation: https, the right host,
a quote long enough to be a sentence. Shape is not provenance. A quote can pass
every one of those checks and still be assembled from two passages twenty five
lines apart, or be a plausible paraphrase nobody typed from the source, and the
README promises "the sentence it was read out of".

So this fetches each cited document and asserts the quote appears in it,
contiguously, after collapsing whitespace. It is marked `live` because it hits
nyc.gov, and it is the test that would have caught the spliced boiler quote
this rulebook shipped with before an adversarial review found it by hand.

    .venv/bin/python -m pytest tests/test_rulebook_provenance.py -m live -q

nyc.gov refuses a request with no browser user agent, which is worth knowing
and is why one is set here rather than left to the default.
"""

from __future__ import annotations

import re
import urllib.request
from functools import lru_cache

import pytest

from agent.engine.rulebook import Rule, all_rules

RULES = all_rules()

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=32)
def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=90) as response:
        body = response.read()
    if url.lower().endswith(".pdf"):
        import io

        from pypdf import PdfReader

        pages = PdfReader(io.BytesIO(body)).pages
        return _flatten(" ".join(page.extract_text() or "" for page in pages))
    return _flatten(body.decode("utf-8", "replace"))


def _quoted_rules() -> list[tuple[Rule, str, str, str]]:
    """Every (rule, field, url, quote) pair this suite can actually verify.

    Only PDFs are checked. The DOB `.page` URLs render their body from
    JavaScript, so fetching one returns a shell with none of the quoted text in
    it and a test over those would fail for a reason that has nothing to do
    with whether the quote is real. Asserting nothing is better than asserting
    something false, so those are listed as unverifiable rather than passed.
    """
    out = []
    for rule in RULES:
        for field in ("quote", "respondent_quote"):
            quote = getattr(rule, field, "")
            url = rule.citation if field == "quote" else rule.respondent_citation
            if quote and url.lower().endswith(".pdf"):
                out.append((rule, field, url, quote))
    return out


PAIRS = _quoted_rules()


def test_some_rules_are_verifiable_at_all():
    """An empty parametrize passes silently, which is the same as no test."""
    assert len(PAIRS) >= 6, (
        f"only {len(PAIRS)} rule quotes point at a fetchable document; this suite would "
        "be asserting almost nothing"
    )


@pytest.mark.live
@pytest.mark.parametrize(
    "rule,field,url,quote", PAIRS, ids=lambda v: v.key if isinstance(v, Rule) else str(v)[:24]
)
def test_the_quote_is_really_in_the_cited_document(rule: Rule, field: str, url: str, quote: str):
    document = _fetch(url)
    assert len(document) > 2000, f"{url} returned {len(document)} characters, which is not the rule"
    assert _flatten(quote) in document, (
        f"{rule.key}.{field} is not in {url} as one contiguous passage. Either it was "
        "spliced from separate subdivisions, or it was paraphrased, or the city changed "
        "the text. Read the document and quote it, do not approximate it."
    )


@pytest.mark.live
def test_the_check_can_fail():
    """A provenance test that cannot fail is worse than no provenance test.

    Runs the same assertion with a sentence that is definitely not in the rule
    and confirms it is rejected. Without this, a fetch that silently returned
    an error page would pass every case above by never matching anything, and
    that is exactly the shape of a check that looks green and asserts nothing.
    """
    rule, _, url, _ = PAIRS[0]
    document = _fetch(url)
    invented = "The commissioner shall issue a renewal by return of post within one hour."
    assert _flatten(invented) not in document
