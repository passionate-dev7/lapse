# Lapse win conditions

Scope note: written by the console agent for the AWS Agents for Humans hackathon, Professional
Agents track, deadline 2026-09-14 17:00 PT (from `CLAUDE.md` at the repo root). Every line below
is checkable against a URL, a file path, or a row in DynamoDB table `lapse-cases`.

Scoreboard: first edition of this event, so there is no prior winner list to name. The comparable
set is the live project gallery for the event, and the entry is judged on a rubric of which
Design is one weighted component. The console is the only judge-facing surface, so it carries
that component alone.

Bar to beat: a judge opening https://lapse-console.vercel.app reaches a real decision, sees the
named checks with the values the engine actually compared, and clicks through to the nyc.gov rule
the deadline was read from, without scrolling past the first card. Concretely: first card above
the fold carries the class, the due date, the day count, the address, the DOB identifiers, the
pass and fail checks, and the citation link. Verified in `deepsurge` at 1440 and 390 with zero
console errors.

Asset we will own: the cited rulebook, `data/rulebook.json`. Every deadline the engine acts on
carries the nyc.gov URL it was read from and the sentence it was read out of, and
`tests/test_rulebook.py` fails the build on any rule whose citation is not an https URL at
nyc.gov or the city's code publisher, or whose quote is too short to find on that page. The city
publishes these as prose across dozens of pages and PDFs; nobody publishes them as fields with
`window_days`, `grace_days` and a quote. Where two published NYC sources disagree on the permit
renewal window, both are recorded in `meta.known_conflicts` and a test fails if either is deleted.

Off-platform buyer: the owner of a two to six person NYC plumbing or HVAC contractor who holds a
master licence, pulls permits under their own business name, and has no office manager. They
existed before this event and will exist after it. They do not know the DOB Permit Issuance
dataset exists.

Single entry: Lapse.

Verb the brief names: "handles repetitive tasks", from the event line "Build an AI agent with
Strands Agents SDK that handles repetitive tasks".

Our product performs that verb: yes, and the repetitive task is the one nobody does, which is
reading a portfolio every day and saying nothing. `agent/engine/deadline.py` returns FILE, DECIDE
or HOLD from arithmetic on dates, supersession and job status, with no prompt reaching it.
`console/app/api/cases/[case_id]/route.ts` writes the human approval to DynamoDB under a
condition on the status and hands the case to the `lapse-run` filing function, which sets `filed`
and writes the delivery record with the real message id. The console never claims a response left
the building; only the function that sent one may write that.

Metric plan: share of a screened portfolio that is held without a word. Target 3 of every 4.
Read off the run record in `lapse-cases`, where `held / items_screened` is written per pass, and
quoted verbatim on the page rather than counted in the browser. Measured on the live portfolio at
2026-09-14: 179 of 235, 76 percent. The engine has a test that fails if it ever surfaces more than
40 percent of a portfolio.

Live by: 2026-09-14, the day of the deadline. This misses the seven day live-by target in the
canonical gate, and that is a real deviation, not a rounding.

Deviation from research: the seven day live-by target above was missed, stated rather than
hidden. One other, narrower: the console's own rendering of the dense queue was first exercised
against a local fixture in `.local/`, built from live NYC Open Data rows, because the case table
did not exist at the time the renderer was written. It has since been verified against the real
table and the fixture is not in the deployment. Nothing else deviates.
