# Win conditions: Lapse

Answered before the product code that follows it. Private working note, not a
judge-facing document. The one-line answers are the gate; the sections below
are the reasoning behind them.

## The gate, answered

- Scoreboard: AWS x Devpost "Agents for Humans", Professional Agents track, five equally weighted criteria with Strands Agents SDK usage named explicitly, deadline 2026-09-14 17:00 PT.
- Bar to beat: a chat wrapper over one API with invented sample data. Beating it needs a live no-auth data source a judge can hit, a decision the model is structurally forbidden from making, and README numbers that reproduce from a command in the repo.
- Asset we will own: data/rulebook.json, a cited deadline rulebook where every rule carries the URL and the verbatim sentence it was read from, enforced by a test that fails the build on an uncited rule.
- Off-platform buyer: small NYC general contractors and speciality trades running 3 to 40 open jobs, who today pay a filing representative a retainer to refresh BIS for them. The expediting trade already charges for exactly this vigilance.
- Single entry: one, Lapse. No variant, no second submission.
- Verb the brief names: "runs autonomously and only surfaces when there's a real decision to make". The operative clause is about silence, and silence is measurable.
- Our product performs that verb: 235 items screened, 179 held silently, 56 surfaced, and 99 of the held were held by a substantive check rather than by "not due yet". Enforced by tests/test_deadline.py::test_most_of_the_portfolio_is_silence, which fails below a 60 percent held share.
- Metric plan: held share above 60 percent (currently 76, test-enforced), README reproduction rate at 100 percent with the SoQL printed beside every figure, and a mutation kill where neutering FilingVeto.inspect must turn the suite red.
- Live by: repo public, README measured, Lambda deployed and invoked with a CloudWatch line captured, console deployed with real rows and zero console errors, diagram exported. All done and verified before 17:00 PT on 2026-09-14.
- Deviation from research: two, both recorded rather than hidden. DOB publishes no deadline in days for most BIS violation classes, so window_days is null there and the engine refuses to invent one. Two published NYC sources disagree about the permit renewal window anchor, so both are recorded in meta.known_conflicts with a test that fails if they are deleted.

## Scoreboard

AWS x Devpost "Agents for Humans", Professional Agents track. Five criteria,
equally weighted: Technological Implementation (specifically, how thoroughly
and skilfully the Strands Agents SDK is used), Design, Potential Impact,
Creativity and Originality, Presentation. Judged on a repo, a README, a
deployed thing and a demo. Deadline 2026-09-14 17:00 PT.

## Bar to beat

The median entry in a track like this is a chat wrapper over one API with a
Streamlit page, submitted with invented sample data and a README that describes
a roadmap. The bar that actually wins is: a live data source with no auth that
a judge can hit themselves, a decision the model is structurally not allowed to
make, and a number in the README that reproduces when they run the command.

Concretely, to beat it we need all four of these true at once:

1. Every number in the README reproduces from a command in the repo.
2. The Strands surface is load-bearing, not decorative: removing it changes
   behaviour, and there is a test that goes red when it is removed.
3. The product is quiet. Anything that surfaces its whole input set has not
   solved the problem it claims to solve.
4. A judge can click a live URL and see rows that came out of a real run.

## Asset we will own

`data/rulebook.json`: a cited deadline rulebook where every rule carries the
URL it was read from and the verbatim sentence it was read out of, with a test
that fails the build on an uncited rule.

This is the thing that does not fall out of a weekend of prompting. Anybody can
call a Socrata endpoint. Knowing that 1 RCNY 102-04(a)(2) bars renewal of a
lapsed permit until the unpermitted work penalty is paid, and that (d)(6)
waives it where no work was done after expiry, and that therefore a lapsed
permit is a question and not a filing, is the asset. It is also portable: the
shape generalises to any jurisdiction, and a contractor in another city swaps
the file rather than the engine.

## Off-platform buyer

Small NYC general contractors and speciality trades, roughly 3 to 40 open jobs,
who today either pay a filing representative a retainer to watch this for them
or find out a permit lapsed when an inspector arrives. The permit expediting
trade already exists and already charges for exactly this vigilance, which is
the market proof: somebody is paying a person to refresh BIS.

The buyer is the contractor, not the city. Nothing here is sold to DOB.

## Single entry

One. Lapse. No second submission, no variant.

## Verb the brief names

The brief says: "handles routine and repetitive tasks in the background", "runs
autonomously and only surfaces when there's a real decision to make", "does
real work for people, handle it end to end".

The operative clause is the middle one. "Only surfaces when there is a real
decision to make" is a claim about silence, and silence is measurable.

## Our product performs that verb

Measured, not asserted. One pass over a real contractor's portfolio:

- 235 items screened, 179 held silently, 56 surfaced.
- Of the 179 held, 99 were held by a substantive check rather than by "not due
  yet": 87 because the city names the building owner and not the contractor as
  respondent, 9 because DOB signed the job off, 3 because a later permit
  sequence already renewed it.
- Of the 56 surfaced, 16 arrive with the response already written and need one
  approval, and 40 ask exactly one question each.

`tests/test_deadline.py::test_most_of_the_portfolio_is_silence` fails the build
if the held share ever drops below 60 percent, so the verb is enforced rather
than described.

## Metric plan

Primary metric: held share, the fraction of screened items the engine correctly
says nothing about. Target above 60 percent, currently 76 percent, enforced by
a test.

Secondary: reproduction rate of README numbers. Target 100 percent, every
figure traceable to `scripts/measure.py` or `scripts/measure_prose.py` with the
SoQL printed beside it.

Guard metric: mutation kill. Neutering `FilingVeto.inspect` must turn the suite
red. If it does not, the guardrail is decoration.

## Live by

Repo public and README measured: done.
Lambda deployed, scheduled, invoked, CloudWatch line captured: done.
Console deployed with real rows and zero console errors: done.
Architecture diagram exported: done.
All of it live and verified well before 17:00 PT on 2026-09-14.

## Deviation from research

Two deliberate deviations from what the research returned, both recorded rather
than hidden:

1. Research found that DOB publishes a cure path but no deadline in days for
   most BIS violation classes. The tempting move was to pick a plausible
   number. Instead `window_days` is `null` for those classes and the engine
   refuses to compute a deadline, routing the item to DECIDE with the clock
   handed back to the contractor. This costs us a more impressive-looking queue
   and buys correctness.

2. Research found two published NYC sources that genuinely disagree about the
   permit renewal window, one anchored to issuance and one to expiry. Rather
   than pick one silently, both are recorded in `meta.known_conflicts` and a
   test fails if they are deleted.

One more, added late after an adversarial review: the filing recipient. The
obvious demo move is to send the drafted response "to DOB". DOB NOW takes a
filing from a licensed person signed in under their own login and there is no
delegated path, so claiming otherwise would be the overreach that loses the
Creativity criterion. The response goes to the filing desk of the person who
can actually file, and the case record names them.
