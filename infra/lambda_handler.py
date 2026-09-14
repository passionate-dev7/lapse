"""The unattended pass: what makes Lapse work with nobody watching.

EventBridge Scheduler fires `lapse-daily` once a day and this is what it calls.
Lambda Function URLs return 403 on this account, so there is no HTTP surface
here on purpose: anything that wants a run out of turn invokes the function
through the SDK, and the payload it sends is the same dict the schedule sends.

A pass is three things, in this order:

  1. Fetch the contractor's portfolio and diff it against `lapse-permits`, the
     table holding the last seen state of every permit and violation. That says
     what moved since yesterday, which is the only number a daily run can put in
     front of a person without them having to re-read the whole portfolio. It
     also fails early and cheaply when NYC Open Data is unreachable, before the
     model has been paid for anything.
  2. Run `agent.run.run` over that portfolio, persisting cases to DynamoDB. The
     deadline engine settles most items with arithmetic and only the survivors
     reach the model.
  3. Write the pass itself to the evidence bucket, so what a run saw on a given
     morning survives the next run overwriting the cases it touched.

Logging is one JSON object per line, which is what `agent.run` already emits, so
CloudWatch Logs Insights reads the whole pass without a custom parser.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import date, datetime, timezone
from typing import Any

import boto3

from agent.engine.portfolio import CONTRACTOR, fetch, load_snapshot
from agent.lapse_agent import DynamoSink
from agent.run import run
from agent.store import ItemStore

EVIDENCE_BUCKET_PREFIX = "lapse-evidence-"

# The fields whose movement changes what Lapse should do about an item. A
# permit whose owner name was re-spelled has not changed; one whose status went
# from ISSUED to EXPIRED has. Anything not in here is carried in the record for
# a person to read but does not raise a change.
PERMIT_WATCHED = ("status", "expires_on", "superseded_by", "filing_status", "permit_sequence")
VIOLATION_WATCHED = ("category", "disposition_date", "disposition_comments", "issued_on")


def _log(event: str, **fields: Any) -> None:
    print(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "event": event, **fields}, default=str), flush=True)


def _account_id(context: Any) -> str:
    arn = getattr(context, "invoked_function_arn", "") or ""
    parts = arn.split(":")
    if len(parts) > 4 and parts[4]:
        return parts[4]
    return boto3.client("sts").get_caller_identity()["Account"]


def _fingerprint(item: dict) -> str:
    watched = PERMIT_WATCHED if item.get("kind") == "permit" else VIOLATION_WATCHED
    return json.dumps({k: item.get(k) for k in watched}, sort_keys=True, default=str)


def _diff_portfolio(contractor: str, items: list[dict]) -> dict:
    """What moved since the last pass, and the new state written down.

    `gone` is counted but never deleted. An item dropping out of the feed means
    the query window moved past it far more often than it means DOB closed it,
    and quietly forgetting an item is how a lapsed permit stops being anybody's
    problem without anybody deciding that.
    """
    store = ItemStore()
    previous = {i["item_key"]: i for i in store.all_items(contractor)}

    changed: list[dict] = []
    new: list[dict] = []
    for item in items:
        key = ItemStore.item_key(item["kind"], item["item_id"])
        before = previous.get(key)
        item["fingerprint"] = _fingerprint(item)
        if before is None:
            new.append(item)
        elif before.get("fingerprint") != item["fingerprint"]:
            moved = [
                {"field": f, "was": before.get(f), "now": item.get(f)}
                for f in (PERMIT_WATCHED if item["kind"] == "permit" else VIOLATION_WATCHED)
                if before.get(f) != item.get(f)
            ]
            changed.append({"item_key": key, "label": item.get("address", ""), "moved": moved})

    seen_keys = {ItemStore.item_key(i["kind"], i["item_id"]) for i in items}
    gone = sorted(set(previous) - seen_keys)
    written = store.put_items(contractor, items)

    delta = {
        "tracked": written,
        "first_seen": len(new),
        "changed": len(changed),
        "unchanged": written - len(new) - len(changed),
        "absent_from_feed": len(gone),
        "changes": changed[:25],
    }
    _log("portfolio_delta", **{k: v for k, v in delta.items() if k != "changes"})
    for change in changed:
        _log("item_changed", item=change["item_key"], moved=change["moved"])
    return delta


def _write_evidence(bucket: str, contractor: str, payload: dict) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    slug = "".join(c if c.isalnum() else "-" for c in contractor.lower()).strip("-")
    key = f"runs/{slug}/{stamp}.json"
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, indent=2, default=str).encode("utf-8"),
        ContentType="application/json",
    )
    uri = f"s3://{bucket}/{key}"
    _log("evidence_written", uri=uri)
    return uri


def run_pass(event: dict, context: Any = None) -> dict:
    contractor = event.get("contractor") or os.environ.get("LAPSE_CONTRACTOR") or CONTRACTOR
    live = bool(event.get("live", True))
    today = date.fromisoformat(event["today"]) if event.get("today") else None
    limit = event.get("limit")
    only = event.get("only")
    approvals = set(event.get("approve") or ())

    # No key, no model. The deadline engine is the half of this product that is
    # arithmetic, so a keyless pass still screens the whole portfolio and still
    # writes down what is due; it just cannot read DOB's free text or draft the
    # response. Saying that in the summary is better than a pass that looks
    # complete and quietly skipped the reading.
    with_model = bool(os.environ.get("ANTHROPIC_API_KEY")) and bool(event.get("with_model", True))

    _log(
        "pass_started",
        contractor=contractor,
        live=live,
        with_model=with_model,
        sender=os.environ.get("LAPSE_SENDER", ""),
        limit=limit,
        only=only,
    )

    portfolio = fetch(contractor, today=today) if live else load_snapshot(today=today)
    items = [p.to_dict() for p in portfolio.permits] + [v.to_dict() for v in portfolio.violations]
    delta = _diff_portfolio(portfolio.contractor, items)

    summary = run(
        live=live,
        sink=DynamoSink(),
        today=today,
        with_model=with_model,
        limit=limit,
        only=only,
        contractor=contractor,
        approvals=approvals,
    )

    result = {
        "contractor": portfolio.contractor,
        "as_of": (today or portfolio.as_of).isoformat(),
        "source": portfolio.source,
        "read_by_model": with_model,
        "delta": delta,
        "summary": summary,
    }
    bucket = f"{EVIDENCE_BUCKET_PREFIX}{_account_id(context)}"
    result["evidence_uri"] = _write_evidence(bucket, portfolio.contractor, result)
    _log("pass_finished", contractor=portfolio.contractor,
         items_screened=summary.get("items_screened"), changed=delta["changed"])
    return result


def handler(event: dict, context: Any = None) -> dict:
    event = event if isinstance(event, dict) else {}
    try:
        return run_pass(event, context)
    except Exception as exc:
        _log("pass_failed", reason=str(exc), traceback=traceback.format_exc())
        raise


if __name__ == "__main__":
    print(json.dumps(handler({"live": True, "with_model": False}), indent=2, default=str))
    sys.exit(0)
