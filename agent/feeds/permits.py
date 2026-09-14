"""DOB Permit Issuance, dataset ipu4-2q9a.

One row is one issuance event, not one permit. The same permit appears again
every time it is renewed, with `permit_sequence__` incremented and a new
`expiration_date`, and the old rows stay. A reader that treats every row as a
live permit will tell a contractor that a permit renewed four times is four
permits about to lapse, three of which were replaced months ago.

So `fetch_portfolio` collapses rows onto the permit they describe, keyed by
(job, job doc, permit type), and keeps only the highest `permit_sequence__`.
The rows it dropped are not discarded: each surviving permit carries
`superseded_by`, the sequence that replaced it if one exists, because the
deadline engine has to be able to say "this looks expired and it is, and here
is the sequence that already replaced it" rather than raising an alarm.

Field names here were read off the live schema, not guessed. The permittee's
business name is `permittee_s_business_name`, with the possessive `s`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from agent.feeds.socrata import Dataset, day_list, escape, rows

DOB_PERMITS = Dataset("ipu4-2q9a", "DOB Permit Issuance")

# The statuses that mean a permit is a live obligation. Everything else
# (REVOKED, IN PROCESS, SUSPENDED) is a permit that is not currently authorising
# work, so its expiry date is not a deadline anybody has to meet.
LIVE_STATUSES = frozenset({"ISSUED", "RE-ISSUED"})


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = raw.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class Permit:
    permit_id: str
    job: str
    job_doc: str
    job_type: str
    permit_type: str
    permit_subtype: str
    permit_sequence: str
    work_type: str
    status: str
    filing_status: str
    issued_on: date | None
    expires_on: date | None
    bin: str
    house: str
    street: str
    borough: str
    permittee: str
    owner: str
    self_cert: str
    superseded_by: str = ""

    @property
    def address(self) -> str:
        return f"{self.house} {self.street}, {self.borough}".strip()

    @property
    def label(self) -> str:
        return f"job {self.job}/{self.job_doc} permit {self.permit_type} seq {self.permit_sequence}"

    @property
    def url(self) -> str:
        """The public BIS page for this job, so a claim can be checked by hand."""
        return (
            "https://a810-bisweb.nyc.gov/bisweb/JobsQueryByNumberServlet"
            f"?requestid=1&passjobnumber={self.job}&passdocnumber={self.job_doc}"
        )

    def to_dict(self) -> dict:
        return {
            "kind": "permit",
            "item_id": self.permit_id,
            "job": self.job,
            "job_doc": self.job_doc,
            "job_type": self.job_type,
            "permit_type": self.permit_type,
            "permit_subtype": self.permit_subtype,
            "permit_sequence": self.permit_sequence,
            "work_type": self.work_type,
            "status": self.status,
            "filing_status": self.filing_status,
            "issued_on": self.issued_on.isoformat() if self.issued_on else None,
            "expires_on": self.expires_on.isoformat() if self.expires_on else None,
            "bin": self.bin,
            "address": self.address,
            "permittee": self.permittee,
            "owner": self.owner,
            "self_cert": self.self_cert,
            "superseded_by": self.superseded_by,
            "url": self.url,
            "source": DOB_PERMITS.human_url,
        }


def parse(row: dict) -> Permit:
    return Permit(
        permit_id=row.get("permit_si_no") or "",
        job=row.get("job__") or "",
        job_doc=row.get("job_doc___") or "",
        job_type=row.get("job_type") or "",
        permit_type=row.get("permit_type") or "",
        permit_subtype=row.get("permit_subtype") or "",
        permit_sequence=row.get("permit_sequence__") or "",
        work_type=row.get("work_type") or "",
        status=(row.get("permit_status") or "").upper(),
        filing_status=(row.get("filing_status") or "").upper(),
        issued_on=_parse_date(row.get("issuance_date")),
        expires_on=_parse_date(row.get("expiration_date")),
        bin=row.get("bin__") or "",
        house=row.get("house__") or "",
        street=row.get("street_name") or "",
        borough=row.get("borough") or "",
        permittee=row.get("permittee_s_business_name") or "",
        owner=row.get("owner_s_business_name") or "",
        self_cert=row.get("self_cert") or "",
    )


def collapse(parsed: list[Permit]) -> list[Permit]:
    """One entry per permit, the newest sequence, with what replaced the rest.

    `permit_sequence__` is a zero-padded string in the source ("01" .. "12"), so
    it is compared as an integer here. A row whose sequence will not parse is
    kept as sequence 0 rather than dropped, because losing a live permit is a
    worse failure than ranking one oddly.
    """

    def seq(permit: Permit) -> int:
        try:
            return int(permit.permit_sequence)
        except (TypeError, ValueError):
            return 0

    groups: dict[tuple[str, str, str], list[Permit]] = {}
    for permit in parsed:
        groups.setdefault((permit.job, permit.job_doc, permit.permit_type), []).append(permit)

    out: list[Permit] = []
    for members in groups.values():
        members.sort(key=seq)
        newest = members[-1]
        for older in members[:-1]:
            if seq(older) < seq(newest):
                out.append(
                    Permit(**{**older.__dict__, "superseded_by": newest.permit_sequence})
                )
        out.append(newest)
    out.sort(key=lambda p: (p.expires_on or date.max, p.job, p.permit_type))
    return out


def fetch_portfolio(
    permittee: str, *, window_start: date, window_end: date
) -> list[Permit]:
    """Every permit this business holds whose expiry falls in the window.

    The window is enumerated day by day because `expiration_date` is a text
    column holding MM/DD/YYYY; see agent/feeds/socrata.py for why a range
    comparison on it would be wrong rather than merely slow.
    """
    where = (
        f"permittee_s_business_name='{escape(permittee)}' "
        f"AND expiration_date in ({day_list(window_start, window_end)})"
    )
    raw = rows(DOB_PERMITS, where, order="issuance_date DESC, permit_si_no")
    parsed = [parse(r) for r in raw]
    live = [p for p in parsed if p.status in LIVE_STATUSES]
    return collapse(live)


def count_expired_between(start: date, end: date, *, live_only: bool = True) -> int:
    """How many permits city-wide carry an expiry date inside the window."""
    from agent.feeds.socrata import count

    where = f"expiration_date in ({day_list(start, end)})"
    if live_only:
        where += " AND permit_status='ISSUED'"
    return count(DOB_PERMITS, where)
