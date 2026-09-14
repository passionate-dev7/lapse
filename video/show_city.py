"""The city-wide numbers, and nothing else on the screen."""

import subprocess
from pathlib import Path

ROOT = Path("/tmp/lapse-film")
out = subprocess.run(
    ["/Users/kamal/Desktop/lapse/.venv/bin/python", "-m", "scripts.measure"],
    capture_output=True, text=True, cwd=ROOT,
    env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "PYTHONPATH": str(ROOT)},
)
for line in out.stdout.splitlines():
    if line.startswith("The portfolio"):
        break
    if len(line) > 92:
        line = line[:92]
    print(line)
