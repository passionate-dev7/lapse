"""DOB Violations, dataset 3h2n-5cm9.

A violation is attached to a building, by BIN, not to a contractor. That is the
join Lapse makes: the permits say which buildings this business is working in,
and the violations say what is outstanding at those buildings. A contractor
looking at a job does not get told about the open violation on the same lot
unless somebody looks it up.

Two fields decide whether a violation is still outstanding and they disagree
often enough that both have to be read:

    `violation_category`   ends in ACTIVE, DISMISSED or Resolved. Structured,
                           and the one the deadline engine trusts.
    `disposition_comments` free text an inspector typed. This is where a
                           violation that is still categorised ACTIVE turns out
                           to have been complied with, or where a compliance
                           says it was rejected. Reading it is the model's job.

`issue_date` is a text column in YYYYMMDD, so string comparison is date
comparison here and a range filter is safe. `disposition_date` is text in the
same shape, and is empty on an outstanding violation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from agent.feeds.socrata import Dataset, rows, ymd

DOB_VIOLATIONS = Dataset("3h2n-5cm9", "DOB Violations")

BORO_NAMES = {
    "1": "MANHATTAN",
    "2": "BRONX",
    "3": "BROOKLYN",
    "4": "QUEENS",
    "5": "STATEN ISLAND",
}


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = raw.strip()
    if not re.fullmatch(r"\d{8}", text):
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def _squash(text: str | None) -> str:
    """DOB pads its free text to a fixed column width. Collapse it once, here."""
    return re.sub(r"\s+", " ", (text or "")).strip()


@dataclass(frozen=True)
class Violation:
    violation_id: str
    number: str
    violation_number: str
    ecb_number: str
    issued_on: date | None
    type_code: str
    type_label: str
    category: str
    bin: str
    block: str
    lot: str
    boro: str
    house: str
    street: str
    description: str
    disposition_date: date | None
    disposition_comments: str
    device_number: str

    @property
    def address(self) -> str:
        return f"{self.house} {self.street}, {BORO_NAMES.get(self.boro, self.boro)}".strip()

    @property
    def category_is_active(self) -> bool:
        """The structured status. DOB spells the closed ones two different ways.

        Every category in this dataset reads like "V-DOB VIOLATION - ACTIVE" or
        "V*-DOB VIOLATION - DISMISSED" or "V*-DOB VIOLATION - Resolved". The
        star is DOB's own marker for a closed one, and the word after the dash
        agrees with it, so this reads the word and does not rely on the star.
        """
        return self.category.upper().rstrip().endswith("ACTIVE")

    @property
    def url(self) -> str:
        return (
            "https://a810-bisweb.nyc.gov/bisweb/ActionsByLocationServlet"
            f"?requestid=1&allbin={self.bin}"
        )

    def to_dict(self) -> dict:
        return {
            "kind": "violation",
            "item_id": self.violation_id,
            "number": self.number,
            "violation_number": self.violation_number,
            "ecb_number": self.ecb_number,
            "issued_on": self.issued_on.isoformat() if self.issued_on else None,
            "type_code": self.type_code,
            "type_label": self.type_label,
            "category": self.category,
            "bin": self.bin,
            "address": self.address,
            "description": self.description,
            "disposition_date": (
                self.disposition_date.isoformat() if self.disposition_date else None
            ),
            "disposition_comments": self.disposition_comments,
            "device_number": self.device_number,
            "url": self.url,
            "source": DOB_VIOLATIONS.human_url,
        }


def parse(row: dict) -> Violation:
    label = _squash(row.get("violation_type"))
    return Violation(
        violation_id=row.get("isn_dob_bis_viol") or "",
        number=row.get("number") or "",
        violation_number=row.get("violation_number") or "",
        ecb_number=(row.get("ecb_number") or "").strip(),
        issued_on=_parse_date(row.get("issue_date")),
        type_code=(row.get("violation_type_code") or "").strip().upper(),
        type_label=label,
        category=_squash(row.get("violation_category")),
        bin=row.get("bin") or "",
        block=row.get("block") or "",
        lot=row.get("lot") or "",
        boro=row.get("boro") or "",
        house=_squash(row.get("house_number")),
        street=_squash(row.get("street")),
        description=_squash(row.get("description")),
        disposition_date=_parse_date(row.get("disposition_date")),
        disposition_comments=_squash(row.get("disposition_comments")),
        device_number=_squash(row.get("device_number")),
    )


def fetch_for_bins(bins: list[str], *, since: date) -> list[Violation]:
    """Outstanding violations at these buildings, newest first.

    `since` bounds how far back to look. The dataset reaches 1988 and a
    violation issued in 1997 with no disposition is a records artefact rather
    than a deadline any contractor working there today can act on, so a caller
    picks the horizon and the README says which one it used.
    """
    unique = sorted({b for b in bins if b})
    if not unique:
        return []
    out: list[Violation] = []
    # A very long IN clause makes Socrata return a query-too-complex error, so
    # BINs go up in batches. Batch size chosen to stay well inside that limit.
    for start in range(0, len(unique), 150):
        batch = unique[start : start + 150]
        bin_list = ",".join(f"'{b}'" for b in batch)
        where = (
            f"bin in ({bin_list}) "
            f"AND violation_category like '%ACTIVE%' "
            f"AND issue_date >= '{ymd(since)}'"
        )
        out.extend(
            parse(r)
            for r in rows(DOB_VIOLATIONS, where, order="issue_date DESC, isn_dob_bis_viol")
        )
    out.sort(key=lambda v: (v.issued_on or date.min), reverse=True)
    return out


def count_open_since(since: date) -> int:
    from agent.feeds.socrata import count

    return count(
        DOB_VIOLATIONS,
        f"violation_category like '%ACTIVE%' AND issue_date >= '{ymd(since)}'",
    )


def count_open_between(start: date, end: date) -> int:
    from agent.feeds.socrata import count

    return count(
        DOB_VIOLATIONS,
        f"violation_category like '%ACTIVE%' "
        f"AND issue_date >= '{ymd(start)}' AND issue_date <= '{ymd(end)}'",
    )
