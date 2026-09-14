"""One contractor's obligations, assembled from three DOB datasets.

The join is the product. Nothing in NYC Open Data answers "what does this
business have to do this month", because the three datasets are keyed
differently on purpose:

    permits     keyed by permittee business name    what this business is licensed to do
    filings     keyed by job number                 whether that job is still open
    violations  keyed by BIN                        what is outstanding at that building

A permit names its BIN and its job number, so the permit list is the bridge.
Walk it once and a business name turns into a set of buildings, and the set of
buildings turns into a list of open violations that nobody attached to the
contractor because the city does not attach them to contractors.

The contractor here is a real business and their filings are public. See the
README for which one, and why a made-up portfolio would have been a worse
demonstration than a real one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from agent.feeds import jobs as job_feed
from agent.feeds import permits as permit_feed
from agent.feeds import violations as violation_feed
from agent.feeds.jobs import Job
from agent.feeds.permits import Permit
from agent.feeds.violations import Violation

DATA = Path(__file__).parent.parent.parent / "data"

CONTRACTOR = "VARSITY PLBG AND HTG INC"
# How far back a lapsed permit is still worth surfacing. Past this it is
# archaeology, not a deadline.
LOOKBACK_DAYS = 120
# How far ahead to load. Wider than the 30 day action window so the console can
# show what is coming without a second fetch.
HORIZON_DAYS = 240
# Violations older than this at a building are a records problem rather than
# something a contractor working there this month can act on. Two years covers
# two full boiler cycles and one full retaining wall window, which is as far
# back as a live obligation reaches.
VIOLATION_SINCE_DAYS = 730


@dataclass(frozen=True)
class Portfolio:
    contractor: str
    permits: tuple[Permit, ...]
    jobs: dict[tuple[str, str], Job]
    violations: tuple[Violation, ...]
    as_of: date
    source: str

    @property
    def bins(self) -> tuple[str, ...]:
        return tuple(sorted({p.bin for p in self.permits if p.bin}))

    @property
    def live_bins(self) -> tuple[str, ...]:
        """Buildings this contractor is actually working in right now.

        A violation belongs to the building and, in most classes, to its owner
        rather than to the contractor. It matters to a contractor for one
        reason: an open violation at a site they hold a permit on can stop
        their job, and several of the classes in this data literally say so
        ("BOROUGH COMMISSIONER HAS ORDERED ALL WORK STOPPED UNDER PERMIT ...").
        That reason evaporates once the permit is superseded or the job is
        signed off, so the violation list is scoped to the buildings where a
        live permit sits, not to every building the contractor has ever been
        in. Without this the queue fills with other people's paperwork.
        """
        out = set()
        for permit in self.permits:
            if permit.superseded_by or not permit.bin:
                continue
            job = self.job_for(permit)
            if job is not None and (job.is_terminal or job.is_stopped):
                continue
            out.add(permit.bin)
        return tuple(sorted(out))

    @property
    def sites(self) -> tuple[str, ...]:
        return tuple(sorted({p.address for p in self.permits if p.address}))

    def job_for(self, permit: Permit) -> Job | None:
        found = self.jobs.get((permit.job, permit.job_doc))
        if found is not None:
            return found
        # A permit's job doc and its filing's doc number disagree on a minority
        # of records, because a permit can be pulled against a subsequent
        # amendment. Falling back to any filing on the same job number is
        # better than reporting the job unknown, and the check text says which
        # filing was used so the fallback is visible rather than silent.
        for (job_number, _), job in self.jobs.items():
            if job_number == permit.job:
                return job
        return None

    def violations_at(self, bin_number: str) -> tuple[Violation, ...]:
        return tuple(v for v in self.violations if v.bin == bin_number)


def fetch(
    contractor: str = CONTRACTOR,
    *,
    today: date | None = None,
    lookback: int = LOOKBACK_DAYS,
    horizon: int = HORIZON_DAYS,
) -> Portfolio:
    """Live. Three round trips to NYC Open Data, no cache, no key."""
    today = today or date.today()
    permits = permit_feed.fetch_portfolio(
        contractor,
        window_start=today - timedelta(days=lookback),
        window_end=today + timedelta(days=horizon),
    )
    filings = job_feed.fetch_for_jobs([p.job for p in permits])
    scoped = Portfolio(
        contractor=contractor,
        permits=tuple(permits),
        jobs=filings,
        violations=(),
        as_of=today,
        source="live NYC Open Data",
    )
    open_violations = violation_feed.fetch_for_bins(
        list(scoped.live_bins), since=today - timedelta(days=VIOLATION_SINCE_DAYS)
    )
    return Portfolio(
        contractor=contractor,
        permits=scoped.permits,
        jobs=filings,
        violations=tuple(open_violations),
        as_of=today,
        source="live NYC Open Data",
    )


def load_snapshot(*, today: date | None = None) -> Portfolio:
    """The same portfolio from the captured responses in data/.

    Those files are real Socrata responses written by `scripts/capture.py`,
    each stamped with the exact `$where` that produced it. They exist so the
    suite runs from a clean clone with no network and no credentials, not to
    stand in for the live feed during a run.
    """
    permit_blob = json.loads((DATA / "permits_varsity.json").read_text())
    violation_blob = json.loads((DATA / "violations_varsity.json").read_text())
    job_blob = json.loads((DATA / "jobs_varsity.json").read_text())

    captured = datetime.strptime(permit_blob["captured_at"], "%Y-%m-%d").date()
    permits = permit_feed.collapse(
        [
            p
            for p in (permit_feed.parse(r) for r in permit_blob["rows"])
            if p.status in permit_feed.LIVE_STATUSES
        ]
    )
    filings = job_feed.newest_per_filing([job_feed.parse(r) for r in job_blob["rows"]])
    scoped = Portfolio(
        contractor=permit_blob["permittee"],
        permits=tuple(permits),
        jobs=filings,
        violations=(),
        as_of=today or captured,
        source="",
    )
    live = set(scoped.live_bins)
    horizon = (today or captured).replace(year=(today or captured).year - 2)
    parsed_violations = [violation_feed.parse(r) for r in violation_blob["rows"]]
    # The captured file holds the full response the query returned. Scoping to
    # live buildings and to the two year horizon happens here rather than by
    # editing the capture, so what is on disk stays exactly what NYC returned.
    kept = tuple(
        v
        for v in parsed_violations
        if v.bin in live and (v.issued_on is None or v.issued_on >= horizon)
    )
    return Portfolio(
        contractor=permit_blob["permittee"],
        permits=tuple(permits),
        jobs=filings,
        violations=kept,
        as_of=today or captured,
        source=f"captured NYC Open Data responses, {permit_blob['captured_at']}",
    )
