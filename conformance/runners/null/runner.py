# /// script
# requires-python = ">=3.10"
# ///
"""The null runner (SDK spec §7.1, phase step S2).

It speaks the runner protocol (conformance/README.md) and calls no SDK: every
step gets an empty result, {"ok": true, "result": {}}. Every case must fail
against it; that is the proof that the suite catches a runner that does nothing.

    uv run conformance/driver.py --runner "python3 conformance/runners/null/runner.py"
    ... --runner "python3 conformance/runners/null/runner.py --features none"

--features sets the features it claims (comma-separated; "none" for no
features; default: all of fs, fetch, json, eager, stream). With fewer features
the driver takes the cases' expect_if_missing paths (not_built, unsupported)
and skips cases that need a missing feature.
"""
import argparse
import json
import sys

ALL = ["fs", "fetch", "json", "eager", "stream"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default=",".join(ALL))
    a = ap.parse_args()
    features = [] if a.features == "none" else [f for f in a.features.split(",") if f]
    out = sys.stdout
    out.write(json.dumps({"hello": {"runner": "null", "version": "0.0.0", "features": features}}) + "\n")
    out.flush()
    for line in sys.stdin:
        if not line.strip():
            continue
        json.loads(line)  # a malformed request is a driver bug; let it raise
        out.write(json.dumps({"ok": True, "result": {}}) + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
