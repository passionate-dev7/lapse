"""One pass over a real contractor's portfolio, in the space of a breath."""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent

out = subprocess.run(
    [str(ROOT / ".venv/bin/python"), "-m", "agent.run", "--engine-only"],
    capture_output=True, text=True, cwd=ROOT,
)
events = [json.loads(line) for line in out.stdout.splitlines() if line.startswith("{")]
done = next(e for e in events if e["event"] == "run_finished")
holds = [e for e in events if e["event"] == "hold"]

print("VARSITY PLBG AND HTG INC, their real public DOB filings")
print()
print(f"  permits screened      {done['permits_screened']:>4}")
print(f"  violations screened   {done['violations_screened']:>4}")
print(f"  items screened        {done['items_screened']:>4}")
print()
print(f"  held, said nothing    {done['held']:>4}")
print(f"  FILE, drafted         {done['engine_file']:>4}")
print(f"  DECIDE, one question  {done['engine_decide']:>4}")
print()
c = done["classes"]
print(f"  classes   lapsed {c['lapsed']}, critical {c['critical']}, due {c['due']}, clear {c['clear']}")
print()
print("Every one of the 179 held names the check that held it:")
print()
reasons = Counter(h["why"].split(":")[0].replace("FAIL ", "") for h in holds)
meaning = {
    "contractor_is_respondent": "the building owner's filing obligation, not this contractor's",
    "within_action_window": "not due for more than thirty days",
    "job_open": "DOB signed the job off, so the expiry date is paperwork",
    "not_superseded": "a later sequence already renewed this permit",
}
for reason, n in reasons.most_common():
    print(f"  {n:>3}  {reason:<26} {meaning.get(reason, '')}")
