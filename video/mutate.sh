#!/bin/bash
# Break the guardrail, watch the suite go red, put it back.
cd "$(dirname "$0")/.."
cp agent/lapse_agent.py /tmp/lapse_veto.bak
/Users/kamal/Desktop/lapse/.venv/bin/python - <<'PY'
import pathlib
p = pathlib.Path('agent/lapse_agent.py')
s = p.read_text()
p.write_text(s.replace("        refusal = self.ledger.may_file(cid)\n        if refusal:",
                       "        refusal = self.ledger.may_file(cid)\n        if False:"))
PY
echo '$ # the filing veto is now deleted'
.venv/bin/python -m pytest tests/test_veto.py -q 2>&1 | tail -4
cp /tmp/lapse_veto.bak agent/lapse_agent.py
echo
echo '$ # restored'
.venv/bin/python -m pytest tests -q 2>&1 | tail -2
