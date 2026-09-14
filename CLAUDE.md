# Lapse

An agent that watches a small NYC contractor's DOB permits and violations on a
schedule, computes what is about to lapse, drafts the renewal or the correction
response, and interrupts them exactly once per item, when a decision is
genuinely theirs. Submitted to the AWS Agents for Humans hackathon,
Professional Agents track, deadline 2026-09-14 17:00 PT.

## The one idea

A permit does not fail loudly. It expires. The failure mode in this whole
domain is silence, so the product's job is to break the silence exactly once
per item and then be quiet again.

## The rule that must never be broken

The model reads free text and writes drafts. The model never decides whether
anything is due.

- `agent/engine/deadline.py` decides, using dates, supersession and job status.
  No prompt reaches it. Returns FILE / DECIDE / HOLD.
- `read_disposition` accepts the model's read of DOB's free text but returns
  the computed verdict.
- `FilingVeto` in `agent/lapse_agent.py` is a Strands `BeforeToolCallEvent`
  hook that cancels `file_response` unless the ledger holds a FILE verdict, an
  item that is still open, and a written draft for that exact case.

`tests/test_veto.py::test_the_hook_cancels_a_filing_that_is_actually_attempted`
is the test that proves it. Remove the hook and it goes red by sending a real
renewal demand for a job that was signed off. Never weaken that test to make a
change pass.

A `StatusReading` may only replace the soft lexical `outstanding_by_text`
check. It can never touch the category, the disposition date, the class
thresholds or the arithmetic.

## The rulebook is data

`data/rulebook.json` holds every deadline this program acts on, and every entry
carries the URL it was read from and the sentence it was read out of.
`tests/test_rulebook.py` fails the suite on any entry whose citation is not an
https URL or whose quote is too short to be a sentence. Never add a rule
without a source. A window this program cannot cite is a window it refuses to
compute, and the item goes to DECIDE instead.

## Environment

- Python 3.12 venv at `.venv`. Run from the repo root.
- `.env` holds `ANTHROPIC_API_KEY`. Never print it, never commit it.
- AWS: profile `palimpsest`, region us-east-1. Always
  `export AWS_PROFILE=palimpsest AWS_DEFAULT_REGION=us-east-1` and
  `unset AWS_BEARER_TOKEN_BEDROCK` first.
- **Bedrock and AgentCore do not work on this account.** It is an AWS India
  (AISPL) account where Bedrock is not offered, and every model in every region
  returns `Operation not allowed`. Do not spend time on it. Strands is
  model-agnostic, so the agent runs on Anthropic directly while Lambda,
  EventBridge Scheduler, DynamoDB, S3 and SES carry the rest.

## Live resources

- DynamoDB `lapse-cases` (PK contractor, SK case_id), `lapse-permits`
- S3 `lapse-evidence-079415246611`
- Lambda `lapse-run`, EventBridge Scheduler `lapse-daily`

## Data honesty

The portfolio is a real business's public DOB filings and the README says so.
Everything in `data/` is a real Socrata response captured by
`scripts/capture.py`, stamped with the `$where` that produced it. Never write a
case by hand into DynamoDB to make a demo look fuller: cases come from a real
run or the console is showing fiction.

## House style

No em dashes. No decorative comments. Comments justify non-obvious decisions
only. Production code only: no mocks, no stubs, no placeholder data. Tests run
against the captured responses in `data/`, never against invented fixtures.
