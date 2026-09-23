# Lapse

Lapse reads a New York City contractor's DOB permits and violations from NYC Open Data and works out which ones lapse next. For each item that needs action, it drafts the renewal or correction response. The contractor is asked at most one question per item, and only when the answer depends on something no dataset records.

It runs against a real portfolio: VARSITY PLBG AND HTG INC, a plumbing contractor, using their public DOB filings.

## How a pass works

`agent/run.py` runs one pass in two stages.

Stage one is the deadline engine in `agent/engine/deadline.py`. It's plain Python with no model involved. It looks at every permit and violation and returns one of three outcomes:

| outcome | meaning |
|---|---|
| `FILE` | every check passed and the rulebook names a specific filing |
| `DECIDE` | the dates work out, but a fact only the contractor has decides the right action |
| `HOLD` | nothing is due, or the item is already closed |

Each item with a date also gets a deadline class based on days remaining: `lapsed`, `critical` (under a week), `due` (under a month) or `clear`.

Stage two passes the `FILE` and `DECIDE` items to a Strands agent (`agent/lapse_agent.py`). The agent reads DOB's free-text disposition comments and writes the draft. It never decides whether something is due.

The data comes from three datasets, joined through the permit record:

| dataset | used for | join key |
|---|---|---|
| DOB Permit Issuance [`ipu4-2q9a`](https://data.cityofnewyork.us/d/ipu4-2q9a) | expiry dates | permittee business name |
| DOB Job Application Filings [`ic3t-wcy2`](https://data.cityofnewyork.us/d/ic3t-wcy2) | whether the job is still open, and the work description | job number |
| DOB Violations [`3h2n-5cm9`](https://data.cityofnewyork.us/d/3h2n-5cm9) | open violations at the same buildings | BIN |

The fetch code lives in `agent/feeds/` (`socrata.py`, `permits.py`, `jobs.py`, `violations.py`). The portfolio join is in `agent/engine/portfolio.py`.

## Checks that keep items on HOLD

The engine holds most of a portfolio, and every hold names the check that failed:

- `within_action_window`: the expiry is more than 30 days away.
- `not_superseded`: a later `permit_sequence__` already renewed this permit. The permit feed keeps one row per issuance, so a permit renewed four times appears four times; `agent/feeds/permits.py` collapses each chain and records `superseded_by` on the older rows.
- `job_open`: DOB signed off or completed the job (`job_status` X or U), so the expired permit doesn't matter anymore.
- `contractor_is_respondent`: the violation belongs to a filing class where the city holds the building owner responsible, such as boiler inspections, so it isn't the contractor's job.

`tests/test_deadline.py::test_most_of_the_portfolio_is_silence` fails if the engine holds 60 percent or less of the captured portfolio.

## Lapsed permits become a question

A lapsed permit leads to a question instead of a filing. Under 1 RCNY 102-04, DOB won't renew a lapsed permit until the unpermitted-work penalty is paid, and it waives that penalty if no work happened after expiry. Only someone at the site knows which case applies. So the engine returns `DECIDE`, and the agent turns the rulebook's generic question into one about the actual site ("Was any plumbing work done at 850 GRAND STREET after September 11, 2026?").

The answer is saved on the case record, and the next pass reads it through `load_answers` in `agent/run.py`. A "no" gives a clean renewal, and a "yes" gives pay-then-renew. `tests/test_answers.py` checks that the two answers produce different instructions. Each answer is tied to a hash of the checks behind the verdict it answered, so if DOB's record changes before the next pass, the answer is refused and the question comes back. An answer also can't reopen an item that the structured checks already closed (`test_an_answer_cannot_resurrect_a_permit_the_checks_closed`).

For some violation classes DOB publishes how to cure them but no deadline. There the rule's `window_days` is `null`, the engine won't make up a number, and the question asks the contractor to pick a date. After that the item follows the same deadline classes as everything else.

## Where the model is used

On permits, there's no free text to read, so the model's only job is the draft, written from the job description in the filing. On violations, the model also reads `disposition_comments`. A keyword check (`outstanding_by_text`) handles most of these. `scripts/measure_prose.py` shows what it misses. Run against live data on 2026-09-23:

```
Violations categorised ACTIVE since 2021-09-23 carrying a disposition comment: 578
  the keyword check calls closed: 571
  the keyword check leaves open:  7
...
     1  000810 PAID INVOICE 90876458
     1  CHALLENGE APPROVED
```

Those are violations DOB still lists as ACTIVE that have in fact been paid or successfully challenged. The model reports its reading through `read_disposition`, which returns a verdict computed by the engine. Readings below 0.7 confidence (`StatusReading.MIN_CONFIDENCE`) are ignored, and a reading can close an item but never reopen one.

## What stops a send

The only tool that sends anything is `file_response`, and two Strands mechanisms in `agent/lapse_agent.py` guard it:

- `FilingVeto` is a `HookProvider` on `BeforeToolCallEvent`. It sets `event.cancel_tool` unless the ledger holds a `FILE` verdict, the item is still open when the send happens, and a draft exists for that case. It also refuses a case that has already been filed.
- `approval_gate` is a `HumanInTheLoop` with `allowed_tools=["*", "!file_response"]`, so this tool always needs a person, even in a session where everything else is trusted. In an unattended run nobody is there to approve, so the case is marked `awaiting_approval` and the pass moves on.

`agent/dispatch.py` handles delivery through SES and writes the delivery mode onto the case: `direct` (the filing desk is a verified identity), `held_for_verification` (sent to the operator desk, with the intended recipient named in the body) or `simulated` (sent to the SES mailbox simulator). `_assert_not_a_loop` raises if the sender and recipient are the same address. The filing desk and operator desk are set in `data/contractor.json` and belong to whoever runs Lapse, not to the contractor whose records it reads. Lapse can't file anything with DOB itself. DOB NOW only accepts filings from a licensed person signed in under their own account.

## The rulebook

`data/rulebook.json` has one entry per permit type or violation class. Each entry has the action, the artifact to file, the window, a `citation` URL and a verbatim `quote` from that source. `agent/engine/rulebook.py` loads it.

The two sources that disagree on the permit renewal window are both listed under `meta.known_conflicts`, and `tests/test_rulebook.py` fails if either is removed. That file also checks every citation's host and quote length. `tests/test_rulebook_provenance.py` (marked `live`) fetches each cited page and checks that the quote appears in it word for word. Some DOB `.page` URLs render their content with JavaScript, and the test reports those as unverifiable instead of passing them.

## Running it

Requires Python 3.12.

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'

# deadline engine only, on the captured data in data/, no network or credentials
.venv/bin/python -m agent.run --engine-only

# same, against NYC Open Data right now
.venv/bin/python -m agent.run --engine-only --live

# full pass with the model; needs ANTHROPIC_API_KEY, and --dynamo needs AWS credentials
.venv/bin/python -m agent.run --live --dynamo
```

Other flags: `--today YYYY-MM-DD` evaluates deadlines as of that date, `--only <item id>` limits the pass to one DOB item, `--limit N` caps how many items reach the model, `--approve <case id>` (repeatable) marks a case approved, and `--contractor` sets the permittee name. Without `--dynamo`, cases go to `data/cases/`.

The pass prints one JSON object per line. The last line of an `--engine-only` run on the captured data:

```
{"event": "run_finished", "permits_screened": 140, "violations_screened": 95, "items_screened": 235, "held": 179, "engine_file": 16, "engine_decide": 40, "answers_applied": 0, "classes": {"critical": 4, "due": 12, "lapsed": 31, "clear": 80}, "source": "captured NYC Open Data responses, 2026-09-14", "as_of": "2026-09-14", "cases_opened": 0, "drafted": 0, "filed": 0, "vetoed": 0, "asked": 0}
```

The model defaults to `claude-sonnet-4-5-20250929` through Strands' `AnthropicModel`. Set `LAPSE_MODEL` to use a different one. Bedrock isn't available on the AWS account this was deployed from, so the model is called directly.

Two scripts measure the problem against live data. Results change daily, and large Socrata queries sometimes time out.

```bash
.venv/bin/python -m scripts.measure        # permits that expired in the last 30 days on jobs still open
.venv/bin/python -m scripts.measure_prose  # ACTIVE violations whose disposition text the keyword check misreads
```

`scripts/capture.py` refreshes the snapshot in `data/`. Each file there is a real Socrata response, stamped with the `$where` query that produced it.

## Tests

```bash
env -i PATH="$PATH" HOME="$HOME" .venv/bin/python -m pytest tests -q
```

On a clean clone this printed `189 passed, 1 skipped, 16 deselected`. The deselected tests are marked `live` (see `pytest.ini`) because they call NYC Open Data, nyc.gov, the model API or AWS. To run the rulebook ones:

```bash
.venv/bin/python -m pytest tests/test_rulebook_provenance.py -m live -q
```

which printed `14 passed, 1 deselected`.

The veto test fails when the veto is broken. Change `if refusal:` to `if False:` in `FilingVeto.inspect` and the suite reports:

```
FAILED tests/test_veto.py::test_the_hook_cancels_a_filing_that_is_actually_attempted
1 failed, 188 passed, 1 skipped, 16 deselected
```

Restore the line and it's back to 189 passed.

## Deployment

`infra/deploy.sh` creates or updates these resources, and it's safe to rerun:

- DynamoDB tables `lapse-cases` and `lapse-permits`
- an S3 evidence bucket
- the `lapse-run` Lambda (`infra/lambda_handler.py`)
- a daily EventBridge Scheduler schedule, `lapse-daily`

It reads `ANTHROPIC_API_KEY` from `.env`. `docs/RECORD.md` defines the case record that `agent/`, `infra/` and `console/` all read and write.

![Lapse architecture](docs/architecture.png)

## Console

`console/` is a Next.js app that reads `lapse-cases` and shows one card per open case, most urgent first. Cards waiting for approval show the draft and an Approve button, which calls the Lambda for that single case. Cards needing a decision show the question and have no send button. It's deployed at [lapse-console.vercel.app](https://lapse-console.vercel.app).

```bash
cd console && pnpm install && pnpm dev   # http://localhost:3011
```

It needs `LAPSE_AWS_ACCESS_KEY_ID` and `LAPSE_AWS_SECRET_ACCESS_KEY` (or `AWS_PROFILE`). Without them it shows an error explaining that it couldn't read the table, not an empty queue.

## Layout

```
agent/
  run.py            one pass: triage, then the agent on what survives
  lapse_agent.py    Strands agent, tools, FilingVeto, approval_gate, case sinks
  dispatch.py       SES delivery and delivery-mode recording
  engine/           deadline.py, rulebook.py, portfolio.py
  feeds/            Socrata client and the three dataset readers
console/            Next.js decision queue
data/               captured Socrata responses, rulebook.json, contractor.json
docs/               RECORD.md (case record contract), architecture diagram
infra/              deploy.sh, lambda_handler.py
scripts/            capture.py, measure.py, measure_prose.py
tests/
```

## Licence

MIT.
