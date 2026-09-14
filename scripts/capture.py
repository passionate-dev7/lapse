"""Freeze a real portfolio to data/ so the suite runs with no network.

Every fixture in this repo is a real response from NYC Open Data, captured by
this script and stamped with the query that produced it. Nothing in data/ was
typed by hand. Rerun it to refresh:

    .venv/bin/python -m scripts.capture
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from agent.engine.portfolio import CONTRACTOR, HORIZON_DAYS, LOOKBACK_DAYS, VIOLATION_SINCE_DAYS
from agent.feeds import permits as permit_feed
from agent.feeds import jobs as job_feed
from agent.feeds import violations as violation_feed
from agent.feeds.socrata import day_list, escape, rows, ymd

DATA = Path(__file__).parent.parent / "data"


def main() -> int:
    today = date.today()
    start = today - timedelta(days=LOOKBACK_DAYS)
    end = today + timedelta(days=HORIZON_DAYS)

    permit_where = (
        f"permittee_s_business_name='{escape(CONTRACTOR)}' "
        f"AND expiration_date in ({day_list(start, end)})"
    )
    permit_rows = rows(
        permit_feed.DOB_PERMITS, permit_where, order="issuance_date DESC, permit_si_no"
    )
    (DATA / "permits_varsity.json").write_text(
        json.dumps(
            {
                "captured_at": today.isoformat(),
                "dataset": permit_feed.DOB_PERMITS.resource,
                "dataset_name": permit_feed.DOB_PERMITS.name,
                "query": {"$where": permit_where, "$order": "issuance_date DESC, permit_si_no"},
                "permittee": CONTRACTOR,
                "window": {"start": start.isoformat(), "end": end.isoformat()},
                "rows": permit_rows,
            },
            indent=2,
        )
    )
    print(f"permits: {len(permit_rows)} rows")

    parsed = permit_feed.collapse(
        [p for p in (permit_feed.parse(r) for r in permit_rows) if p.status in permit_feed.LIVE_STATUSES]
    )
    bins = sorted({p.bin for p in parsed if p.bin})
    since = today - timedelta(days=VIOLATION_SINCE_DAYS)
    bin_list = ",".join(f"'{b}'" for b in bins)
    violation_where = (
        f"bin in ({bin_list}) AND violation_category like '%ACTIVE%' "
        f"AND issue_date >= '{ymd(since)}'"
    )
    violation_rows = rows(
        violation_feed.DOB_VIOLATIONS,
        violation_where,
        order="issue_date DESC, isn_dob_bis_viol",
    )
    (DATA / "violations_varsity.json").write_text(
        json.dumps(
            {
                "captured_at": today.isoformat(),
                "dataset": violation_feed.DOB_VIOLATIONS.resource,
                "dataset_name": violation_feed.DOB_VIOLATIONS.name,
                "query": {"$where": violation_where, "$order": "issue_date DESC, isn_dob_bis_viol"},
                "bins": bins,
                "since": since.isoformat(),
                "rows": violation_rows,
            },
            indent=2,
        )
    )
    print(f"violations: {len(violation_rows)} rows over {len(bins)} bins")

    job_numbers = sorted({p.job for p in parsed if p.job})
    listed = ",".join(f"'{j}'" for j in job_numbers)
    job_where = f"job__ in ({listed})"
    job_rows = rows(job_feed.DOB_JOBS, job_where, order="latest_action_date DESC, job_s1_no")
    (DATA / "jobs_varsity.json").write_text(
        json.dumps(
            {
                "captured_at": today.isoformat(),
                "dataset": job_feed.DOB_JOBS.resource,
                "dataset_name": job_feed.DOB_JOBS.name,
                "query": {"$where": job_where, "$order": "latest_action_date DESC, job_s1_no"},
                "jobs": job_numbers,
                "rows": job_rows,
            },
            indent=2,
        )
    )
    print(f"job filings: {len(job_rows)} rows over {len(job_numbers)} job numbers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
