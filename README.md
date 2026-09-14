# Lapse

An agent that watches a New York City contractor's permits and violations, works out what is about to lapse, writes the renewal or the correction response, and interrupts them exactly once per item, when the decision is actually theirs.

## The problem, measured against the city's own data

Run `.venv/bin/python -m scripts.measure`. On 2026-09-14, against live NYC Open Data:

**605** DOB work permits carried an ISSUED status and an expiry date that fell in the previous thirty days, 2026-08-15 to 2026-09-13.

```
$where=expiration_date in (<the 30 days 2026-08-15..2026-09-13>) AND permit_status='ISSUED'
```

That number is too big, because the permit feed holds one row per issuance and a permit renewed four times looks like four permits. Collapse the renewal sequences onto the permit they renew and **542** are left. Then join each one to its job filing in a second dataset and ask whether DOB ever signed that job off. **463** had not been signed off or completed.

Four hundred and sixty three permits went past their date last month on jobs that were still open. Another **142** expire in the next seven days.

A permit does not fail loudly. It expires. Nobody calls. The date passes, the permit lapses, and the next thing that happens is an inspector at the site, a stop work order, and a re-file that costs weeks. The failure mode of this entire domain is silence.

On the violations side, **165,001** DOB violations issued since 2021-09-14 are still categorised ACTIVE. **581** of those carry a sentence a clerk typed into a free text field that says something about disposition, and seven of those say things a keyword list will never understand.

`scripts/measure.py` reports a wider violation count for the portfolio below than a pass does, on purpose. It counts every open violation at every building the contractor holds a permit in, over five years, which is the raw exposure. A pass narrows that twice before deciding anything, to two years and to the buildings where a live permit still sits. The wide number is what is out there. The narrow one is what is actually theirs.

## What Lapse does

It reads three NYC datasets, no key, no auth, and joins them on the permit record, which is the only thing that touches all three:

| dataset | what it answers | key |
|---|---|---|
| DOB Permit Issuance [`ipu4-2q9a`](https://data.cityofnewyork.us/d/ipu4-2q9a) | what expires and when | permittee business name |
| DOB Job Application Filings [`ic3t-wcy2`](https://data.cityofnewyork.us/d/ic3t-wcy2) | whether the job is even open, and what the work is | job number |
| DOB Violations [`3h2n-5cm9`](https://data.cityofnewyork.us/d/3h2n-5cm9) | what is outstanding at the same building | BIN |

Nothing in NYC Open Data answers "what does this business have to do this month". The three datasets are keyed differently on purpose. A permit names its BIN and its job number, so walking the permit list once turns a business name into a set of buildings, and the set of buildings turns into violations that nobody attached to the contractor because the city does not attach them to contractors.

## The one idea

**The model reads free text and writes drafts. The model never decides whether anything is due.**

`agent/engine/deadline.py` decides, and no prompt reaches it. It returns one of three things:

| outcome | meaning | what the contractor sees |
|---|---|---|
| `FILE` | every check passed and the rulebook names one specific filing | the drafted response, and one Approve button |
| `DECIDE` | the arithmetic is sound but a fact only they hold changes which action is right | one question, and no send button |
| `HOLD` | nothing is due, or the item is already closed | nothing, ever |

and one of four deadline classes, on a single axis of days remaining: `lapsed`, `critical` (inside a week), `due` (inside a month), `clear`.

`HOLD` is the common case and the product depends on it. A contractor told about everything in their portfolio reads nothing, and then the one that mattered goes past too. Every `HOLD` is a notification that was correctly not sent, and there is a test that fails if the engine ever starts surfacing more than 40 percent of a portfolio.

### Where the Strands work actually is

The obvious question about an agent built this way is: if a deadline engine makes every decision, what is the agent for? The answer is not the model's judgment. It is the control structure, and it is three specific things in the Strands SDK:

1. **`FilingVeto`**, a `BeforeToolCallEvent` `HookProvider` that sets `event.cancel_tool` before `file_response` runs. Not a check inside the tool, which a model that never calls the tool would never reach, and not a prompt instruction, which a model can talk itself out of. The refusal happens in the framework, above the tool body.
2. **`approval_gate`**, a `HumanInTheLoop` vended intervention with `allowed_tools=["*", "!file_response"]`. The negation is the point: in Strands a negated tool cannot be trusted for the session, so no amount of prior approval makes the send automatic. An if-statement does not buy that property.
3. **A seam the model cannot cross.** `read_disposition` accepts the model's read of DOB's prose and returns the verdict computed from it. The model learns the outcome; it never chooses it. A `StatusReading` below 0.7 confidence is ignored entirely, and a reading can only ever close an item, never argue a closed one back open.

Neutering the hook by one line turns the suite red, which is the test that separates a guardrail from a decoration. That proof is below.

## The three checks that make it credible

These are why the engine can be quiet without being wrong.

**Supersession.** `permit_sequence__` increments on every renewal and the old rows stay. A reader that treats each row as a live permit reports three emergencies that were handled months ago. Lapse collapses rows onto `(job, job doc, permit type)`, keeps the highest sequence, and every superseded row carries `superseded_by` so the verdict can say "this looks expired and it is, and sequence 09 already replaced it".

**Job status.** The permit feed cannot tell an expired permit on a live site from an expired permit on a job that closed two years ago. The filings feed can: `job_status` X is SIGNED OFF and U is COMPLETED. A lapsed permit on a closed job is paperwork. A lapsed permit on an open job is unpermitted work. That join is the difference between an alarm and noise.

**Whose obligation it is.** A violation attaches to a building, and for the periodic filing classes the city names the owner, not whoever happens to hold a permit there. 1 RCNY 103-01(d): "The owner shall be responsible for hiring a qualified boiler inspector to conduct inspections and file low pressure boiler annual inspection reports". So a plumbing contractor does not get handed the building's annual boiler filings. On the portfolio below that check alone holds back 87 items that a naive BIN join would have dumped in their queue.

## The rulebook is data, and every rule carries its source

`data/rulebook.json`. Every deadline this program acts on carries the URL it was read from and the sentence it was read out of.

```json
{
  "key": "PL",
  "label": "Plumbing permit",
  "action": "Renew it in the system it was issued in, DOB NOW: Build or eFiling, before the expiry date...",
  "artifact": "DOB NOW: Build or eFiling permit renewal, PW2 if anything changed, $130 renewal fee",
  "grace_days": 730,
  "lapsed_question": "Was any plumbing work done on this site after the permit expired? ...",
  "citation": "https://www.nyc.gov/site/buildings/property-or-business-owner/permit-renewal.page",
  "quote": "Permit renewals are issued on active permits and permits that have expired but have activity on the application within a two-year period of the permit expiration date..."
}
```

Two tests enforce that, and the second one is the one that matters.

`tests/test_rulebook.py` fails the build on any rule whose citation is not an https URL at nyc.gov or the city's code publisher, or whose quote is too short to be a sentence. That is a check on the shape of a citation, and shape is not provenance: a quote can pass all of it and still be two passages from different subdivisions glued together.

So `tests/test_rulebook.py -m live` fetches every cited document and asserts the quote appears in it contiguously. It found four spliced or approximated quotes in this rulebook the first time it ran, including the boiler one, which had "Late filing. An inspection report..." from definition (b)(4) joined to a sentence twenty five lines later in subdivision (e). Both halves were real and the meaning was right, and a judge with a PDF reader would have got zero hits searching for it. All twelve verifiable quotes now pass. The suite also asserts the check can fail, by running the same match against a sentence nobody wrote.

Four rules cite a DOB `.page` URL whose body is rendered by JavaScript, so fetching one returns a shell with none of the quoted text in it. Those are listed as unverifiable rather than quietly counted as passing.

Where the city publishes a cure path but no deadline, `window_days` is `null` and the engine refuses to invent one: the item goes to `DECIDE` with the clock handed back to the contractor. Two published NYC sources genuinely disagree about the permit renewal window, one anchored to issuance and one to expiry. Both are recorded in `meta.known_conflicts` and a test fails if they are deleted. Silently picking one and writing it into an engine is how a wrong number survives a rewrite.

## Why a lapsed permit is a question and not a filing

This is the rule that decides the shape of the product, and it is the city's, not mine.

1 RCNY 102-04(a)(2) bars the renewal of a lapsed permit until the unpermitted work penalty is paid. 1 RCNY 102-04(d)(6) waives that penalty "Where a permit ... expired and no work was performed after the permit's expiration". Whether anybody worked on that site after the date passed is a fact that exists only on the site. No dataset holds it.

So the engine stops and asks one question, and the question is worth answering: if nothing was done it is a clean renewal, and if work continued the penalty is $600 on a one or two family dwelling and $6,000 on anything else, and it has to clear before the renewal will be issued at all.

That is what "interrupts them exactly once, when the decision is genuinely theirs" means here. It is not a design preference. It is where the city put the fork.

## What happens when they answer

A question that can never become anything is a dead end wearing the costume of a decision, so the answer closes the loop.

The engine asks, in the contractor's own terms, because the model turns the rulebook's generic question into a site-specific one:

> Was any plumbing work done at 850 GRAND STREET after September 11, 2026?

They answer in the console. The next pass picks it up off the case record and the verdict moves, for a reason it can cite:

```
{"event": "answers_loaded", "count": 1}
verdict   permit job 302582729/02 permit PL seq 08: FILE (8 checks passed, 0 failed)
outcome   FILE
action    Renew it. DOB waives the unpermitted work penalty where a permit expired and
          nothing was done after it, so this is a clean renewal with the standard fee.
citation  https://www.nyc.gov/assets/buildings/rules/1_RCNY_102-04.pdf
check     answered_by[the contractor]: No work was done after the permit expired
          (answered 2026-09-14T13:13:29+00:00). "Where a permit (other than for temporary
          construction equipment) expired and no work was performed after the permit's
          expiration."
```

and the draft that comes out says it:

> Job 302582729/02 Permit PL Seq 08 at 850 Grand Street, Brooklyn expired September 11, 2026. The work covered exterior lighting replacement, removal and reinstallation of rooftop mechanical equipment, replacement of mechanical systems as indicated, and replacement of roof drains. Renew this permit in DOB NOW: Build or eFiling before September 11, 2028. No work was performed after expiration, so DOB waives the unpermitted work penalty.

Answer "yes" instead and it still becomes a filing, but a different one: the penalty has to be paid before DOB will issue the renewal at all, under 1 RCNY 102-04(a)(2), and the draft says to pay first rather than file first. Both branches are in `data/rulebook.json` with their own verbatim quotes, and a test asserts they do not produce the same instruction, because if they did the question was theatre.

**An answer is scoped to the exact verdict it answers.** `evidence_id` carries a hash of the checks the verdict rested on, so if DOB's record moved between the question going out and the answer coming back, the answer was given about something else. It is refused, visibly:

```
FAIL answer_still_applies: answered 'no' on 2026-09-14 against a different reading of
     this permit; DOB's record has moved since, so the question stands again
```

An answer supplies one fact no dataset holds. It is not a veto override: on a permit whose job DOB signed off, the structured checks fail long before the answer is ever consulted, and `tests/test_answers.py::test_an_answer_cannot_resurrect_a_permit_the_checks_closed` is what keeps that true.

## What the model is actually for

A keyword list already handles most of DOB's closure language, and I measured exactly how much. Of the 581 ACTIVE violations carrying a disposition comment, the shallow check in `outstanding_by_text` correctly calls **574** of them closed. It leaves **7** open. Run `.venv/bin/python -m scripts.measure_prose`:

```
000810 PAID INVOICE 90876458
000810 PAID INVOICE 90876457
CHALLENGE APPROVED
000810 PAID INVOICE 90888813
```

Seven is a small number and I am not going to dress it up. It is also the only number that matters, because every one of those is a violation the city still lists as ACTIVE where the contractor has already paid the invoice or already won the challenge. Acting on one means paying twice, or re-curing something DOB already approved. No keyword list gets there. A reader gets there instantly.

That is the whole job description: `read_disposition` takes the model's honest read of DOB's prose and returns the verdict computed from it, so the model learns the outcome rather than choosing it. On permits there is no prose at all, so there is nothing for a model to be better at than a date comparison, and the engine is total. The model's work on a permit is the draft, written from the job description the architect filed:

> Job 104213922/03 permit PL seq 04 at 240 SECOND AVENUE, MANHATTAN expires September 15, 2026. The work is to provide new steam convector, remove and reinstall split AC unit condensers in cellar, replace four area drains, one floor drain, duplex sump pump, and house trap in cellar. Renew this plumbing permit in the system it was issued in, DOB NOW: Build or eFiling, before the expiry date.

A renewal request written from `job_type=A2, permit_type=PL, work_type=OT` is unreadable. That one reads like a filing agent wrote it.

## The two things that stop it sending

**`FilingVeto`**, a Strands `BeforeToolCallEvent` hook in `agent/lapse_agent.py`, cancels `file_response` unless the ledger holds a `FILE` verdict, an item that is still open, and a written draft for that exact case. Openness is re-read at send time off the verdict currently in the ledger, never remembered from when the case was opened.

**`approval_gate`**, a Strands `HumanInTheLoop` intervention with `allowed_tools=["*", "!file_response"]`, so that one tool always requires a person even if a caller has trusted everything else in the session. In a scheduled run nobody is at a terminal, so the gate does not block: it marks the case `awaiting_approval` and the pass moves on.

Approval is permission to send something that already passed every check. It is never permission to skip the checking, and `tests/test_veto.py::test_the_hook_cancels_a_filing_that_is_actually_attempted` approves a case first and then asserts the veto still refuses it.

## Who the response goes to, and why it is not the city

Lapse cannot file anything with DOB, and every message it sends says so in its own body.

DOB NOW accepts a filing from a licensed person signed in under their own login, and for most job types from a registered filing representative. There is no API, no filing address and no delegated path that would let an agent file on somebody's behalf, and there should not be one. An entry that claimed otherwise would be claiming something the city does not permit.

So the end of this pipeline is the desk of the person who can actually file, holding the drafted text, the deadline, the evidence the engine checked and the rule it came from. `data/contractor.json` names that desk, and `agent/dispatch.py` records honestly what happened to each response:

| mode | meaning |
|---|---|
| `direct` | the filing desk is a verified SES identity, or the account has left the sandbox, and it was delivered there |
| `held_for_verification` | the filing desk is not reachable yet, so it went to the operator desk unaltered, with the real intended recipient named in the body. The filing desk has not received it |
| `simulated` | neither is reachable, so the send was proven against the AWS mailbox simulator. Nothing reached anybody |

`intended` always names the party the response is for, never the address it settled for. It is also never the sender: a message addressed from Lapse to Lapse returns a real MessageId and a real delivery record while reaching nobody but the program that wrote it, which is a failure that looks exactly like success. `_assert_not_a_loop` raises rather than let that be written to a case, and `tests/test_dispatch.py::test_a_response_addressed_to_ourselves_is_refused` proves it.

## The portfolio

`VARSITY PLBG AND HTG INC`, a real plumbing contractor, and these are their real public DOB filings. Nothing here is invented, because a made-up portfolio would have proved nothing: the failures this engine exists to prevent are all shaped like a real record that a naive reader mistakes for something else.

One pass, `.venv/bin/python -m agent.run --engine-only`:

```
permits screened     140      across 118 addresses in all five boroughs
violations screened   95      at the buildings where a live permit sits
items screened       235
held                 179      correctly silent
FILE                  16      drafted, waiting for one approval
DECIDE                40      one question each
classes              lapsed 31, critical 4, due 12, clear 80
```

Every one of the 179 held names the check that held it:

```
 87  contractor_is_respondent   the building owner's filing obligation, not this contractor's
 80  within_action_window       not due for more than thirty days
  9  job_open                   DOB signed the job off, so the expiry date is paperwork
  3  not_superseded             a later sequence already renewed this permit
```

Those 99 that are not simply "not due yet" are the ones a naive BIN-and-expiry join would have put in front of a person. All five boroughs, 118 addresses.

Then the full pass, `.venv/bin/python -m agent.run --live --dynamo`, with the model on every one of the 56 the engine did not settle:

```
{"event": "run_finished", "permits_screened": 140, "violations_screened": 95,
 "items_screened": 235, "held": 179, "engine_file": 16, "engine_decide": 40,
 "considered": 56, "cases_opened": 56, "drafted": 16, "awaiting_approval": 16,
 "needs_decision": 40, "filed": 0, "vetoed": 0, "source": "live NYC Open Data"}
```

`filed: 0` is the correct outcome of an unattended run. Sixteen responses are written and waiting for one person to press one button. Nothing left the building on its own.

Then one person presses Approve in the console. That invokes the deployed Lambda with the case id and the DOB item id read off the record server-side, and the same pass runs again against that single item:

```json
{"considered": 1, "cases_opened": 1, "drafted": 1, "filed": 1, "vetoed": 0,
 "items_screened": 235, "held": 179, "source": "live NYC Open Data"}
```

```
delivery  {"mode": "direct", "to": "filing-desk@getava.xyz",
           "intended": "filing-desk@getava.xyz",
           "message_id": "010001a0a007514a-d4842c75-bf29-412d-9ecb-34fd93c6eb0f-000000",
           "reason": "filing-desk@getava.xyz is a verified identity in this account"}
timeline  ["opened", "drafted", "redrafted", "filed"]
evidence  s3://lapse-evidence-079415246611/runs/varsity-plbg-and-htg-inc/2026-09-14T13-07-11Z.json
```

Sixteen seconds end to end. A real SES send in `direct` mode with a real MessageId, and the sender is `lapse@getava.xyz` while the recipient is the filing desk, which is a different address on purpose. The veto ran underneath the approval and had nothing to object to, which is the only circumstance in which anything is ever sent. The timeline says `redrafted` rather than a second `drafted` because the case was already open and a pass that reopens one preserves what the earlier pass established instead of replaying it.

## Running it

```bash
python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'

# the deterministic pass, no model, no credentials, captured data
.venv/bin/python -m agent.run --engine-only

# the same thing against NYC Open Data right now
.venv/bin/python -m agent.run --engine-only --live

# the full pass with the agent, drafts and all
.venv/bin/python -m agent.run --live --dynamo

# the suite, from a clean shell with nothing in the environment
env -i PATH="$PATH" HOME="$HOME" .venv/bin/python -m pytest tests -q
```

Everything in `data/` is a real Socrata response captured by `scripts/capture.py` and stamped with the `$where` that produced it. The suite reads those, never a fixture written to make a parser look right, so a schema change at the city's end shows up as a failure rather than as a silently empty portfolio.

### Proving the suite can fail

A guardrail that has only ever been tested by code that agrees with it has not been tested. Break the veto and the suite has to notice. From a clean clone, change one line in `FilingVeto.inspect`:

```python
        refusal = self.ledger.may_file(cid)
-       if refusal:
+       if False:
```

```
=== RED ===
FAILED tests/test_veto.py::test_the_hook_cancels_a_filing_that_is_actually_attempted
1 failed, 161 passed, 1 skipped, 2 deselected

=== GREEN, after git checkout -- agent/lapse_agent.py ===
162 passed, 1 skipped, 2 deselected
```

The test that goes red approves the case first, then calls `file_response` on a permit whose job DOB already signed off. With the hook, it is refused. Without it, a contractor gets told to renew a permit on a job that closed.

The blind spot worth stating: the fast suite proves the hook refuses. It does not prove the model would decline on its own, which is a different question and is covered by `tests/test_veto.py::test_the_model_will_not_file_a_response_it_was_ordered_to_file` under `-m live`, where the real model is instructed to file anyway and does not.

## Architecture

Strands Agents SDK, running on Anthropic `claude-sonnet-4-5-20250929`.

**On Bedrock, plainly:** this is an AWS India (AISPL) account, where Bedrock is not offered. Every model in every region returns `Operation not allowed`, for the account administrator too. Strands is model-agnostic by design, so that was one configuration line rather than a dead end, and it is worth noticing that this is exactly the portability the SDK exists to give you. Everything else in the stack is AWS and all of it is deployed and exercised:

- **Lambda** `lapse-run`, one unattended pass
- **EventBridge Scheduler** `lapse-daily`
- **DynamoDB** `lapse-cases` (PK `contractor`, SK `case_id`), `lapse-permits` for last-seen state so a pass can tell what moved
- **S3** `lapse-evidence-079415246611`
- **SES** from `lapse@getava.xyz`, with the delivery mode recorded honestly on every case
- **CloudWatch** for the run log

![Lapse architecture](docs/architecture.png)

See `docs/architecture.html` for the interactive version with its three views, and `docs/RECORD.md` for the case record contract that `agent/`, `infra/` and `console/` all write and read.

## The console

**[lapse-console.vercel.app](https://lapse-console.vercel.app)**

A decision queue, not a dashboard. One route, cards sorted by `verdict.days_remaining` ascending, one action per card. A card `awaiting_approval` shows the whole draft and one button. A card `needs_decision` shows the one question and has no send affordance at all. Every card carries the rule's citation, the BIS link for the record, the dataset it was read from, and the evidence id of the exact decision it rests on, because a deadline a contractor cannot check is a deadline they have no reason to believe.

The healthy state is empty, and it says so in a way that does not look broken. There is a separate state for the table being missing, which says "This page is not saying you are clear", because an empty render and a broken read look identical and only one of them is good news.

## Licence

MIT.
