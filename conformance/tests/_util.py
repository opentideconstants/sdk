"""Helpers for the driver and server self-tests (standard library only)."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

CONF = Path(__file__).resolve().parent.parent
DRIVER = CONF / "driver.py"
NULL_RUNNER = CONF / "runners" / "null" / "runner.py"

# A fake runner: prints the hello from $FAKE_HELLO (raw line) and answers every
# request with $FAKE_REPLY (raw line). Optional $FAKE_STDERR is written first.
FAKE_RUNNER = textwrap.dedent('''
    import os, sys
    if os.environ.get("FAKE_STDERR"):
        sys.stderr.write(os.environ["FAKE_STDERR"] + "\\n"); sys.stderr.flush()
    if os.environ.get("FAKE_HOME_PROBE"):
        open(os.environ["FAKE_HOME_PROBE"], "a").write(os.environ.get("HOME", "") + "\\n")
    hello = os.environ.get("FAKE_HELLO", '{"hello": {"runner": "fake", "features": ["fs","fetch","json","eager","stream"]}}')
    if hello != "-":
        sys.stdout.write(hello + "\\n"); sys.stdout.flush()
    for line in sys.stdin:
        if line.strip():
            sys.stdout.write(os.environ.get("FAKE_REPLY", '{"ok": true, "result": {}}') + "\\n"); sys.stdout.flush()
''')


def write_fake_runner(tmp: Path) -> str:
    p = tmp / "fake_runner.py"
    p.write_text(FAKE_RUNNER)
    return f"{sys.executable} {p}"


def write_cases(tmp: Path, cases, name="t.json") -> Path:
    d = tmp / "cases"
    d.mkdir(exist_ok=True)
    (d / name).write_text(json.dumps({"cases": cases}))
    return d


def run_driver(*args, env=None, timeout=120):
    import os
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, str(DRIVER), *args], capture_output=True, text=True, env=e, timeout=timeout)
