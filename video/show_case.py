"""One case the engine settled, and one it refused to."""

import sys
import textwrap

import boto3

ddb = boto3.resource("dynamodb", region_name="us-east-1")
rows = ddb.Table("lapse-cases").scan()["Items"]
want = sys.argv[1] if len(sys.argv) > 1 else "both"


def wrap(text, indent="    "):
    for para in str(text).split("\n"):
        if not para.strip():
            print()
            continue
        for line in textwrap.wrap(para, 84):
            print(indent + line)


if want in ("draft", "both"):
    drafted = next(r for r in rows if r.get("draft_text") and r.get("verdict", {}).get("outcome") == "FILE")
    i = drafted["item"]
    print("=" * 90)
    print("THE RULEBOOK NAMES THE FILING, SO THE RESPONSE IS WRITTEN")
    print("=" * 90)
    print(f"  {i['address']}")
    print(f"  job {i['job']}/{i['job_doc']}  permit {i['permit_type']} seq {i['permit_sequence']}"
          f"  expires {i['expires_on']}")
    print()
    wrap(drafted["draft_text"])
    print()
    print(f"  status: {drafted['status']}")
    print(f"  evidence: {drafted['verdict'].get('evidence_id', '')}")
    print()
    print("  Nothing is sent. It waits behind one button.")

if want in ("question", "both"):
    asked = max(
        (r for r in rows if r.get("verdict", {}).get("outcome") == "DECIDE" and r.get("kind") == "permit"),
        key=lambda r: abs(int(r["verdict"].get("days_remaining") or 0)),
    )
    j = asked["item"]
    print("=" * 90)
    print("AND WHERE A FACT IS MISSING, IT ASKS INSTEAD")
    print("=" * 90)
    print(f"  {j['address']}")
    print(f"  job {j['job']}/{j['job_doc']}  permit {j['permit_type']} seq {j['permit_sequence']}"
          f"  expired {j['expires_on']}, {abs(int(asked['verdict']['days_remaining']))} days ago")
    print()
    for m in asked["verdict"]["missing"]:
        wrap(m)
    print()
    print(f"  status: {asked['status']}")
    print("  There is no send button on this one at all.")
