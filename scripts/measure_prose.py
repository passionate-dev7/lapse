"""What a keyword list gets wrong about DOB's free text, counted.

The claim this program rests on is that some violations DOB still categorises
ACTIVE have already been closed in a sentence a clerk typed, and that telling
which is reading rather than matching. This script is the measurement behind
that claim, so it is a number rather than an opinion:

    .venv/bin/python -m scripts.measure_prose

It pulls every ACTIVE violation carrying a disposition comment, runs the
shallow keyword check in agent/engine/deadline.py over it, and prints what that
check catches, what it misses, and the misses themselves. The misses are the
model's job description.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date

from agent.engine.deadline import outstanding_by_text
from agent.feeds import violations as violation_feed
from agent.feeds.socrata import rows, ymd


def main() -> int:
    today = date.today()
    since = date(today.year - 5, today.month, today.day)
    where = (
        f"violation_category like '%ACTIVE%' AND issue_date >= '{ymd(since)}' "
        "AND disposition_comments IS NOT NULL"
    )
    raw = rows(violation_feed.DOB_VIOLATIONS, where, order="issue_date DESC, isn_dob_bis_viol")
    parsed = [violation_feed.parse(r) for r in raw]

    caught = [v for v in parsed if not outstanding_by_text(v.disposition_comments).passed]
    missed = [v for v in parsed if outstanding_by_text(v.disposition_comments).passed]

    print(f"\nViolations categorised ACTIVE since {since} carrying a disposition comment: {len(parsed)}")
    print(f"  the keyword check calls closed: {len(caught)}")
    print(f"  the keyword check leaves open:  {len(missed)}")
    print(f"\n$where={where}\n")

    print("What the keyword check leaves open, which is what the model has to read:")
    shapes = Counter()
    for violation in missed:
        head = " ".join(violation.disposition_comments.split()[:4]).upper()
        shapes[head] += 1
    for shape, n in shapes.most_common(20):
        example = next(
            v.disposition_comments
            for v in missed
            if " ".join(v.disposition_comments.split()[:4]).upper() == shape
        )
        print(f"  {n:>4}  {example[:120]}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
