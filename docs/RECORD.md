# The case record

One row per decision Lapse has made about one item. This is the contract
between `agent/`, `infra/` and `console/`. Nothing renders a number that is not
in here.

DynamoDB table `lapse-cases`, PK `contractor` (S), SK `case_id` (S), PAY_PER_REQUEST.

```json
{
  "contractor": "VARSITY PLBG AND HTG INC",
  "case_id": "9f3c1a7b2e5d0846",
  "record_type": "case",
  "status": "awaiting_approval | needs_decision | filed | dismissed",
  "kind": "permit | violation",

  "item": {
    "kind": "permit",
    "item_id": "3765466",
    "job": "104213922", "job_doc": "03",
    "job_type": "A2", "permit_type": "PL", "permit_subtype": "", "permit_sequence": "04",
    "work_type": "PL", "status": "ISSUED", "filing_status": "RENEWAL",
    "issued_on": "2026-03-11", "expires_on": "2026-09-15",
    "bin": "1020416", "address": "240 SECOND AVENUE, MANHATTAN",
    "permittee": "VARSITY PLBG AND HTG INC", "owner": "...",
    "self_cert": "N", "superseded_by": "",
    "url": "https://a810-bisweb.nyc.gov/...",
    "source": "https://data.cityofnewyork.us/d/ipu4-2q9a"
  },

  "job": {
    "job": "104213922", "doc": "03", "job_type": "A2",
    "status": "R", "status_text": "PERMIT ISSUED - ENTIRE JOB/WORK",
    "description": "PROVIDE NEW STEAM CONVECTOR. REMOVE AND REINSTALL ...",
    "latest_action_on": "2026-03-11", "signed_off_on": null,
    "initial_cost": "$120000.00", "building_type": "OTHER",
    "landmarked": "N", "applicant": "...",
    "source": "https://data.cityofnewyork.us/d/ic3t-wcy2"
  },

  "verdict": {
    "outcome": "FILE | DECIDE | HOLD",
    "klass": "lapsed | critical | due | clear | null",
    "due_on": "2026-09-15",
    "days_remaining": 1,
    "anchor_name": "permit expiry",
    "checks": [{"name": "permit_live", "passed": true, "detail": "permit status is ISSUED"}],
    "missing": ["whether work under job 104213922/03 is still going on"],
    "action": "Renew the permit before it expires",
    "artifact": "DOB NOW: Build permit renewal",
    "citation": "https://www.nyc.gov/...",
    "evidence_id": "permit:3765466:critical:FILE"
  },

  "draft_text": "Full text of the renewal request or the correction response, or null",
  "question": "The one question put to the contractor, or null",

  "timeline": [{"at": "2026-09-14T18:02:11+00:00", "event": "opened", "detail": "verdict FILE"}],
  "delivery": {
    "mode": "direct | held_for_verification | simulated",
    "to": "filing-desk@getava.xyz",
    "intended": "filing-desk@getava.xyz",
    "message_id": "010001a0a007514a-...",
    "reason": "why it went where it went",
    "sent_at": "2026-09-14T13:07:09+00:00"
  },
  "created_at": "2026-09-14T18:02:11+00:00",
  "updated_at": "2026-09-14T18:02:11+00:00"
}
```

## The run summary record

Same table, same partition. `case_id` is `run#<iso timestamp>` and
`record_type` is `run`. It exists so the console can say how many items a pass
covered instead of counting the leftovers it can see.

```json
{
  "contractor": "VARSITY PLBG AND HTG INC",
  "case_id": "run#2026-09-14T18:04:00+00:00",
  "record_type": "run",
  "status": "run_summary",
  "finished_at": "2026-09-14T18:04:00+00:00",
  "permits_screened": 140,
  "violations_screened": 98,
  "items_screened": 238,
  "held": 201,
  "cases_opened": 37,
  "drafted": 22,
  "awaiting_approval": 22,
  "needs_decision": 15,
  "filed": 0,
  "vetoed": 0,
  "source": "live NYC Open Data",
  "as_of": "2026-09-14",
  "timeline": [{"at": "...", "event": "run_finished", "detail": "{...}"}],
  "created_at": "...", "updated_at": "..."
}
```

## Statuses

| status | meaning | what the console shows |
|---|---|---|
| `awaiting_approval` | verdict FILE, a draft is written, waiting for a person to press send | the draft, one Approve button |
| `needs_decision` | verdict DECIDE, one question is waiting | the question, no send button |
| `filed` | the response left the building, `delivery.message_id` is set | the delivery record, no button |
| `dismissed` | a later pass found the item closed | archived |

`delivery.intended` always names the party the response was for. `delivery.to`
is where it actually went, which is the same address in `direct` mode and a
different one in the other two. A console that renders `filed` without saying
which mode is telling a contractor their permit is safe when it may not be.

`HOLD` never becomes a case. It is the silent majority and it is only counted
on the run record.
