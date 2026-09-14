"""DOB Job Application Filings, dataset ic3t-wcy2.

This is the source that decides whether an expired permit is an emergency or a
non-event, and it is the reason Lapse does not shout at a contractor about
every permit that has run past its date.

A permit expiring is not the failure. A permit expiring *while the job is still
open* is. The permit issuance dataset cannot tell the difference: it carries an
expiry date and nothing about whether anybody still needs to be on that site.
The filings dataset carries `job_status`, and two of its sixteen values are
terminal:

    X  SIGNED OFF   1,681,785 rows
    U  COMPLETED       49,774 rows

A permit that lapsed on a job that reached X or U is a closed-out job with a
stale date attached. Raising that as a deadline is the noise that makes a
contractor stop reading their alerts, which is the way a real one gets missed.

It also carries `job_description`, the only free prose anywhere in this
pipeline that describes the work itself:

    "REPLACE DETERIORATED BRICK, TERRA COTTA, LIMESTONE, AND GRANITE.
     REFURBISH AND/OR REPLACE SASHES IN EXISTING WOOD WINDOWS."

A renewal request written from `job_type=A2, permit_type=PL, work_type=OT` is
unreadable. A renewal request written from that sentence is a renewal request.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from agent.feeds.socrata import Dataset, rows

DOB_JOBS = Dataset("ic3t-wcy2", "DOB Job Application Filings")

# job_status values that mean nobody is still working under this filing.
# Verified against the live taxonomy, see the module docstring.
TERMINAL_STATUS = {"X": "SIGNED OFF", "U": "COMPLETED"}
# Filed and withdrawn, or suspended by DOB. Also not a live deadline, but for a
# different reason, so it is named separately rather than lumped in.
STOPPED_STATUS = {"3": "SUSPENDED"}


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def _squash(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


@dataclass(frozen=True)
class Job:
    job: str
    doc: str
    job_type: str
    status: str
    status_text: str
    description: str
    latest_action_on: date | None
    signed_off_on: date | None
    fully_permitted_on: date | None
    initial_cost: str
    building_type: str
    existing_occupancy: str
    proposed_occupancy: str
    landmarked: str
    applicant: str
    withdrawn: bool

    @property
    def key(self) -> tuple[str, str]:
        return (self.job, self.doc)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUS or self.signed_off_on is not None

    @property
    def is_stopped(self) -> bool:
        return self.status in STOPPED_STATUS or self.withdrawn

    def to_dict(self) -> dict:
        return {
            "job": self.job,
            "doc": self.doc,
            "job_type": self.job_type,
            "status": self.status,
            "status_text": self.status_text,
            "description": self.description,
            "latest_action_on": (
                self.latest_action_on.isoformat() if self.latest_action_on else None
            ),
            "signed_off_on": self.signed_off_on.isoformat() if self.signed_off_on else None,
            "initial_cost": self.initial_cost,
            "building_type": self.building_type,
            "landmarked": self.landmarked,
            "applicant": self.applicant,
            "source": DOB_JOBS.human_url,
        }


def parse(row: dict) -> Job:
    first = _squash(row.get("applicant_s_first_name"))
    last = _squash(row.get("applicant_s_last_name"))
    return Job(
        job=row.get("job__") or "",
        doc=row.get("doc__") or "",
        job_type=row.get("job_type") or "",
        status=(row.get("job_status") or "").strip().upper(),
        status_text=_squash(row.get("job_status_descrp")),
        description=_squash(row.get("job_description")),
        latest_action_on=_parse_date(row.get("latest_action_date")),
        signed_off_on=_parse_date(row.get("signoff_date")),
        fully_permitted_on=_parse_date(row.get("fully_permitted")),
        initial_cost=_squash(row.get("initial_cost")),
        building_type=_squash(row.get("building_type")),
        existing_occupancy=_squash(row.get("existing_occupancy")),
        proposed_occupancy=_squash(row.get("proposed_occupancy")),
        landmarked=_squash(row.get("landmarked")),
        applicant=f"{first} {last}".strip(),
        withdrawn=_squash(row.get("withdrawal_flag")) not in ("", "0"),
    )


def newest_per_filing(parsed: list[Job]) -> dict[tuple[str, str], Job]:
    """One Job per (job number, doc number), the most recently acted on.

    The dataset holds a row per action taken on a filing, so the same job and
    doc appears once per status transition. Only the newest describes where the
    filing stands now.
    """
    best: dict[tuple[str, str], Job] = {}
    for job in parsed:
        current = best.get(job.key)
        if current is None:
            best[job.key] = job
            continue
        mine = job.latest_action_on or date.min
        theirs = current.latest_action_on or date.min
        # A terminal status wins a tie: a filing that has been signed off does
        # not go back to open because another row shares its action date.
        if mine > theirs or (mine == theirs and job.is_terminal and not current.is_terminal):
            best[job.key] = job
    return best


def fetch_for_jobs(job_numbers: list[str]) -> dict[tuple[str, str], Job]:
    unique = sorted({j for j in job_numbers if j})
    if not unique:
        return {}
    collected: list[Job] = []
    for start in range(0, len(unique), 150):
        batch = unique[start : start + 150]
        listed = ",".join(f"'{j}'" for j in batch)
        collected.extend(
            parse(r)
            for r in rows(
                DOB_JOBS, f"job__ in ({listed})", order="latest_action_date DESC, job_s1_no"
            )
        )
    return newest_per_filing(collected)
