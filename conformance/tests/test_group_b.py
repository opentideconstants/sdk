"""Group B: driver process handling."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from _util import CONF, run_driver, write_cases, write_fake_runner

sys.path.insert(0, str(CONF))
import driver  # noqa: E402
from server import FixtureServer, RecordingProxy  # noqa: E402

OK_STEP = {"op": "station_count", "expect": {"count": 1}}


def test_probe_stderr_is_shown_when_handshake_fails(tmp_path):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases),
                   env={"FAKE_HELLO": "-", "FAKE_STDERR": "kaboom-at-startup"})
    assert r.returncode == 2, (r.returncode, r.stdout[-300:], r.stderr[-300:])
    assert "kaboom-at-startup" in r.stdout + r.stderr
    assert "Traceback" not in r.stderr


def test_non_object_hello_fails_cleanly(tmp_path):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    for hello in ['"hello"', '["hello"]', '{"hello": "x"}', "42"]:
        r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_HELLO": hello})
        assert r.returncode == 2 and "Traceback" not in r.stderr, (hello, r.stderr[-500:])


def test_missing_runner_command_exits_2(tmp_path):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    r = run_driver("--runner", str(tmp_path / "no-such-runner"), "--cases", str(cases))
    assert r.returncode == 2 and "Traceback" not in r.stderr, r.stderr[-500:]


def test_case_runner_is_closed_when_hello_fails(tmp_path):
    pidfile = tmp_path / "pid"
    script = tmp_path / "bad_hello.py"
    # prints a bad hello, then waits on stdin (a leaked runner stays alive)
    script.write_text(f"import os, sys\nopen({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
                      "print('[1]', flush=True)\nsys.stdin.read()\n")
    srv, proxy = FixtureServer().start(), RecordingProxy().start()
    try:
        stats = {"steps_compared": 0, "steps_failed": 0, "harness_errors": 0}
        failures, _ = driver.run_case({"id": "x", "steps": [OK_STEP]}, [sys.executable, str(script)], set(),
                                      srv, proxy, False, False, stats)
    finally:
        srv.shutdown()
        proxy.shutdown()
    assert failures
    pid = int(pidfile.read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, 9)
        raise AssertionError("the runner process was left running")


def test_server_variant_requires_fs():
    out = driver.expand([{"id": "m", "matrix": {"release": "20991231.2", "root": "good"}, "steps": []}])
    srv = [c for c in out if c["id"] == "m@server"][0]
    assert "fs" in srv["requires"] and "fetch" in srv["requires"]


def test_runner_home_is_isolated(tmp_path):
    probe = tmp_path / "homes"
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_HOME_PROBE": str(probe)})
    homes = [h for h in probe.read_text().splitlines()]
    assert len(homes) >= 2, homes  # the probe and the case runner
    assert all(h and h != os.environ.get("HOME") for h in homes), homes
