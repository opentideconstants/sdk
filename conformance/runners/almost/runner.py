# /// script
# requires-python = ">=3.10"
# ///
"""The "almost right" runner: a stronger RED proof than the null runner.

It answers `open` the way a working SDK would for the cases' open variants
({loaded_from, datestamp, format_version} worked out from the arguments), and
every other op with an empty result, {"ok": true, "result": {}}. So it passes
the open step of a matrix case and must fail a later step. Run it with
--all-steps to show that the later runner steps and driver steps catch an SDK
that opens correctly and then does nothing:

    uv run conformance/driver.py --runner "python3 conformance/runners/almost/runner.py" --all-steps

It calls no SDK and opens no file or socket.
"""
import json
import re
import sys

FEATURES = ["fs", "fetch", "json", "eager", "stream"]
DATESTAMP = re.compile(r"OTC_(\d{8}(?:\.[1-9]\d*)?)\.")


def open_result(args):
    if args.get("file"):
        m = DATESTAMP.search(args["file"])
        return {"loaded_from": "file", "datestamp": m.group(1) if m else None,
                "format_version": "0.3" if "format-minor" in args["file"] else "0.2"}
    return {"loaded_from": "download", "datestamp": args.get("release"), "format_version": "0.2"}


def main():
    out = sys.stdout
    out.write(json.dumps({"hello": {"runner": "almost", "version": "0.0.0", "features": FEATURES}}) + "\n")
    out.flush()
    for line in sys.stdin:
        if not line.strip():
            continue
        req = json.loads(line)
        result = open_result(req.get("args") or {}) if req.get("op") == "open" else {}
        out.write(json.dumps({"ok": True, "result": result}) + "\n")
        out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
