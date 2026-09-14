"""Durable state, over DynamoDB.

    lapse-cases    PK contractor (S)  SK case_id (S)
    lapse-permits  PK contractor (S)  SK item_key (S)

This module is the only thing in the codebase that talks to DynamoDB. It moves
plain JSON-shaped dicts in and out; no boto3 type (Decimal, set) leaks past its
own boundary.

`put_case` is a read-modify-write rather than a conditional put. A conditional
put only protects the first write, and every write after that has to merge:
keep `created_at`, grow the timeline, and let the caller's newer view replace
everything else. Merging a list and taking a min over a timestamp is not
expressible as a ConditionExpression, so it happens in Python. The race that
accepts: two writers on the same case_id can interleave between the read and
the write and one can lose a timeline entry. A case_id is only ever written by
the scheduled pass for one contractor, one at a time, so that does not happen
here. If two passes ever run concurrently for one contractor, move this to a
transaction that reads inside the transaction.

The second table is what makes a pass incremental. `lapse-permits` holds the
last seen state of every permit and violation, so tomorrow's pass can say what
changed rather than re-deciding a portfolio that did not move.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import boto3

CASES_TABLE = "lapse-cases"
ITEMS_TABLE = "lapse-permits"


def _to_dynamo(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_dynamo(asdict(value))
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_dynamo(v) for v in value]
    return value


def _from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        as_int = int(value)
        return as_int if as_int == value else float(value)
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CaseStore:
    def __init__(self, resource: Any = None) -> None:
        self._ddb = resource or boto3.resource("dynamodb")
        self._table = self._ddb.Table(CASES_TABLE)

    @staticmethod
    def case_id(contractor: str, kind: str, item_id: str) -> str:
        """Deterministic idempotency key.

        Same contractor, same kind, same DOB identifier, run a thousand times,
        must always name the same case. The identifier is DOB's own
        (`permit_si_no` for a permit, `isn_dob_bis_viol` for a violation), so a
        case survives the item moving address, changing status, or being
        renewed under a new sequence.
        """
        raw = f"{contractor}|{kind}|{item_id}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def get_case(self, contractor: str, case_id: str) -> dict | None:
        resp = self._table.get_item(
            Key={"contractor": contractor, "case_id": case_id}, ConsistentRead=True
        )
        item = resp.get("Item")
        return _from_dynamo(item) if item else None

    def list_cases(self, contractor: str, status: str | None = None) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        items: list[dict] = []
        kwargs: dict[str, Any] = {"KeyConditionExpression": Key("contractor").eq(contractor)}
        while True:
            resp = self._table.query(**kwargs)
            items.extend(resp.get("Items", []))
            last = resp.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        cases = [_from_dynamo(i) for i in items]
        if status is not None:
            cases = [c for c in cases if c.get("status") == status]
        cases.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
        return cases

    def put_case(self, case: dict) -> dict:
        contractor, case_id = case["contractor"], case["case_id"]
        existing = self.get_case(contractor, case_id)

        merged = dict(case)
        if existing is not None:
            merged["created_at"] = existing.get("created_at", case.get("created_at"))
            seen = {(e.get("at"), e.get("event")) for e in existing.get("timeline", [])}
            grown = list(existing.get("timeline", []))
            for entry in case.get("timeline", []):
                key = (entry.get("at"), entry.get("event"))
                if key not in seen:
                    grown.append(entry)
                    seen.add(key)
            merged["timeline"] = grown

        self._table.put_item(Item=_to_dynamo(merged))
        return merged

    def append_timeline(self, contractor: str, case_id: str, event: str, detail: str) -> dict:
        now = _now()
        resp = self._table.update_item(
            Key={"contractor": contractor, "case_id": case_id},
            UpdateExpression=(
                "SET timeline = list_append(if_not_exists(timeline, :empty), :entry), "
                "updated_at = :now"
            ),
            ExpressionAttributeValues={
                ":entry": _to_dynamo([{"at": now, "event": event, "detail": detail}]),
                ":empty": [],
                ":now": now,
            },
            ReturnValues="ALL_NEW",
        )
        return _from_dynamo(resp["Attributes"])

    def set_status(self, contractor: str, case_id: str, status: str) -> dict:
        now = _now()
        resp = self._table.update_item(
            Key={"contractor": contractor, "case_id": case_id},
            UpdateExpression="SET #s = :status, updated_at = :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": status, ":now": now},
            ReturnValues="ALL_NEW",
        )
        return _from_dynamo(resp["Attributes"])


class ItemStore:
    """Last seen state of every permit and violation in a portfolio.

    The key is `{kind}#{item_id}` so a permit and a violation can never collide
    on an identifier, which they otherwise could: DOB's `permit_si_no` and
    `isn_dob_bis_viol` are both bare integers drawn from different sequences.
    """

    def __init__(self, resource: Any = None) -> None:
        self._ddb = resource or boto3.resource("dynamodb")
        self._table = self._ddb.Table(ITEMS_TABLE)

    @staticmethod
    def item_key(kind: str, item_id: str) -> str:
        return f"{kind}#{item_id}"

    def put_items(self, contractor: str, items: list[dict]) -> int:
        now = _now()
        count = 0
        with self._table.batch_writer(overwrite_by_pkeys=["contractor", "item_key"]) as batch:
            for item in items:
                record = dict(item)
                record["contractor"] = contractor
                record["item_key"] = self.item_key(record["kind"], record["item_id"])
                record["seen_at"] = now
                batch.put_item(Item=_to_dynamo(record))
                count += 1
        return count

    def all_items(self, contractor: str) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        items: list[dict] = []
        kwargs: dict[str, Any] = {"KeyConditionExpression": Key("contractor").eq(contractor)}
        while True:
            resp = self._table.query(**kwargs)
            items.extend(resp.get("Items", []))
            last = resp.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        return [_from_dynamo(i) for i in items]
