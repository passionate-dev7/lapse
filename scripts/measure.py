"""Every number in the README, measured against the live city datasets.

Nothing in this repo's documentation is a number somebody remembered. Run this
and the README's opening paragraph is what comes out:

    .venv/bin/python -m scripts.measure

Each line prints the count and the exact SoQL that produced it, so a reader can
paste the query into NYC Open Data and get the same answer.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from agent.engine.portfolio import CONTRACTOR, HORIZON_DAYS, LOOKBACK_DAYS
from agent.feeds import jobs as job_feed
from agent.feeds import permits as permit_feed
from agent.feeds import violations as violation_feed
from agent.feeds.socrata import count, day_list, escape, rows, select, ymd


def show(label: str, value, query: str) -> dict:
    print(f"{value:>10}  {label}")
    print(f"            $where={query}")
    return {"label": label, "value": value, "where": query}


def main() -> int:
    today = date.today()
    measured: list[dict] = []

    print(f"\nMeasured {today.isoformat()} against live NYC Open Data.\n")
    print("DOB Permit Issuance, ipu4-2q9a")
    print("-" * 78)

    lapsed_start, lapsed_end = today - timedelta(days=30), today - timedelta(days=1)
    where = f"expiration_date in ({day_list(lapsed_start, lapsed_end)}) AND permit_status='ISSUED'"
    n_lapsed = count(permit_feed.DOB_PERMITS, where)
    measured.append(
        show(
            f"permits with ISSUED status whose expiry fell between "
            f"{lapsed_start} and {lapsed_end}",
            n_lapsed,
            f"expiration_date in (<the 30 days {lapsed_start}..{lapsed_end}>) "
            f"AND permit_status='ISSUED'",
        )
    )

    soon_end = today + timedelta(days=7)
    where = f"expiration_date in ({day_list(today, soon_end)}) AND permit_status='ISSUED'"
    n_soon = count(permit_feed.DOB_PERMITS, where)
    measured.append(
        show(
            f"permits expiring in the next seven days, {today} to {soon_end}",
            n_soon,
            f"expiration_date in (<{today}..{soon_end}>) AND permit_status='ISSUED'",
        )
    )

    # Of the permits that just lapsed, how many sit on a job DOB has not signed
    # off. That is the number that matters: an expired permit on a closed job is
    # paperwork, an expired permit on an open job is unpermitted work.
    lapsed_rows = rows(
        permit_feed.DOB_PERMITS,
        f"expiration_date in ({day_list(lapsed_start, lapsed_end)}) AND permit_status='ISSUED'",
        order="permit_si_no",
    )
    lapsed_permits = permit_feed.collapse([permit_feed.parse(r) for r in lapsed_rows])
    current = [p for p in lapsed_permits if not p.superseded_by]
    print(
        f"{len(current):>10}  of those, after collapsing renewal sequences onto the permit "
        f"they renew"
    )
    measured.append(
        {
            "label": "lapsed permits after collapsing renewal sequences",
            "value": len(current),
            "where": "computed in agent/feeds/permits.py::collapse over the rows above",
        }
    )

    filings = job_feed.fetch_for_jobs([p.job for p in current])
    still_open = [
        p
        for p in current
        if (filings.get((p.job, p.job_doc)) or next(
            (j for (jn, _), j in filings.items() if jn == p.job), None
        ))
        is not None
        and not (
            filings.get((p.job, p.job_doc))
            or next((j for (jn, _), j in filings.items() if jn == p.job))
        ).is_terminal
    ]
    print(
        f"{len(still_open):>10}  of those, on a job DOB has NOT signed off or completed "
        f"(ic3t-wcy2 job_status not in X, U)"
    )
    measured.append(
        {
            "label": "lapsed permits on jobs DOB has not signed off",
            "value": len(still_open),
            "where": "join to ic3t-wcy2 on job__, job_status not in ('X','U')",
        }
    )

    print("\nDOB Violations, 3h2n-5cm9")
    print("-" * 78)

    since = date(today.year - 5, today.month, today.day)
    where = f"violation_category like '%ACTIVE%' AND issue_date >= '{ymd(since)}'"
    n_active = count(violation_feed.DOB_VIOLATIONS, where)
    measured.append(
        show(f"violations still categorised ACTIVE, issued since {since}", n_active, where)
    )

    prose_where = (
        f"violation_category like '%ACTIVE%' AND issue_date >= '{ymd(since)}' "
        "AND disposition_comments IS NOT NULL"
    )
    n_prose = count(violation_feed.DOB_VIOLATIONS, prose_where)
    measured.append(
        show(
            "of those, ones whose free text says something about disposition",
            n_prose,
            prose_where,
        )
    )

    print(f"\nThe portfolio: {CONTRACTOR}")
    print("-" * 78)

    portfolio_permits = permit_feed.fetch_portfolio(
        CONTRACTOR,
        window_start=today - timedelta(days=LOOKBACK_DAYS),
        window_end=today + timedelta(days=HORIZON_DAYS),
    )
    live = [p for p in portfolio_permits if not p.superseded_by]
    bins = sorted({p.bin for p in live if p.bin})
    print(f"{len(portfolio_permits):>10}  permits in the window, after collapsing sequences")
    print(f"{len(live):>10}  of those not already superseded by a later sequence")
    print(f"{len(bins):>10}  distinct buildings (BIN) those permits sit in")
    print(f"{len(sorted({p.address for p in live})):>10}  distinct addresses")

    open_violations = violation_feed.fetch_for_bins(bins, since=since)
    print(f"{len(open_violations):>10}  open violations at those buildings since {since}")

    types = {}
    for violation in open_violations:
        types[violation.type_code] = types.get(violation.type_code, 0) + 1
    print(f"            by type: {json.dumps(dict(sorted(types.items())))}")

    measured += [
        {
            "label": f"permits in {CONTRACTOR}'s window",
            "value": len(portfolio_permits),
            "where": f"permittee_s_business_name='{escape(CONTRACTOR)}' AND expiration_date in (<window>)",
        },
        {
            "label": "open violations at those buildings",
            "value": len(open_violations),
            "where": f"bin in (<{len(bins)} bins>) AND violation_category like '%ACTIVE%' AND issue_date >= '{ymd(since)}'",
        },
    ]

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
