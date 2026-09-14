"""The one HTTP client that talks to NYC Open Data.

Socrata's SoQL is the whole reason this module exists. Both datasets Lapse
reads store their dates as `text`, not as `calendar_date`, which is verifiable
from the dataset metadata:

    curl -s https://data.cityofnewyork.us/api/views/ipu4-2q9a.json \
      | jq '.columns[] | select(.fieldName=="expiration_date")'
    -> "dataTypeName": "text"

A text column cannot be compared with `>` in any way that means what a reader
expects. DOB permits store expiry as `MM/DD/YYYY`, so `expiration_date >
'2026-09-01'` is a lexicographic comparison that silently returns the wrong
rows rather than an error, which is the worst kind of wrong. DOB violations
store issue date as `YYYYMMDD`, where lexicographic order happens to agree with
chronological order, so there the comparison is safe.

So this module offers two ways to ask a date question and each dataset gets the
one that is actually correct for its encoding:

    `day_list`  enumerates the days in a range as literal `MM/DD/YYYY` strings
                for an `IN (...)` clause. Exact, no ordering assumption.
    `ymd`       formats a date as `YYYYMMDD` for the violation feed, where
                string order is date order.

Nothing here caches. A permit that expired an hour ago is the entire product.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

DOMAIN = "https://data.cityofnewyork.us"
TIMEOUT = 90
# Socrata caps a single page at 50,000 rows and this walks pages until short.
PAGE = 5000


class FeedError(RuntimeError):
    """NYC Open Data refused or could not answer. Never silently a zero."""


@dataclass(frozen=True)
class Dataset:
    resource: str
    name: str

    @property
    def url(self) -> str:
        return f"{DOMAIN}/resource/{self.resource}.json"

    @property
    def human_url(self) -> str:
        return f"{DOMAIN}/d/{self.resource}"


def day_list(start: date, end: date) -> str:
    """Every day from `start` to `end` inclusive, as an MM/DD/YYYY IN clause.

    A quarter of a year is ninety-odd literals, which Socrata accepts and which
    is exact. Anything much wider than a year should filter on a real
    `calendar_date` column instead, and neither of these datasets has one for
    the field that matters.
    """
    if end < start:
        raise ValueError(f"day_list needs start <= end, got {start} .. {end}")
    days = (end - start).days + 1
    if days > 800:
        raise ValueError(
            f"day_list would emit {days} literals; that range is too wide for an IN clause"
        )
    return ",".join(
        "'%s'" % (start + timedelta(days=i)).strftime("%m/%d/%Y") for i in range(days)
    )


def ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def _request(url: str, params: dict[str, str]) -> list[dict]:
    query = urllib.parse.urlencode(params)
    full = f"{url}?{query}"
    request = urllib.request.Request(full, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:400].decode("utf-8", "replace")
        raise FeedError(f"{exc.code} from Socrata for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FeedError(f"could not reach {url}: {exc.reason}") from exc
    payload = json.loads(body)
    if isinstance(payload, dict):
        raise FeedError(f"Socrata returned an error object for {url}: {payload}")
    return payload


def select(dataset: Dataset, where: str, *, select: str = "*", order: str = "") -> list[dict]:
    """One aggregate or filtered read. Use `rows` when the result can be large."""
    params = {"$select": select, "$where": where, "$limit": str(PAGE)}
    if order:
        params["$order"] = order
    return _request(dataset.url, params)


def rows(dataset: Dataset, where: str, *, order: str, cap: int = 20000) -> list[dict]:
    """Every row matching `where`, paged.

    `order` is required and must be deterministic. Socrata does not guarantee a
    stable page boundary without one, so an unordered paged read can return the
    same row twice and skip another.
    """
    out: list[dict] = []
    offset = 0
    while len(out) < cap:
        page = _request(
            dataset.url,
            {
                "$where": where,
                "$order": order,
                "$limit": str(PAGE),
                "$offset": str(offset),
            },
        )
        out.extend(page)
        if len(page) < PAGE:
            break
        offset += PAGE
    return out[:cap]


def count(dataset: Dataset, where: str) -> int:
    result = select(dataset, where, select="count(*) AS n")
    return int(result[0]["n"]) if result else 0


def escape(value: str) -> str:
    """SoQL string literal escaping. A permittee name can contain an apostrophe."""
    return value.replace("'", "''")
