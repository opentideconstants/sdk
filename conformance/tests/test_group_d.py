"""Group D: the README describes what the driver does."""
from __future__ import annotations

import re
import sys

from _util import CONF

sys.path.insert(0, str(CONF))
import driver  # noqa: E402

README = (CONF / "README.md").read_text(encoding="utf-8")


def test_open_row_lists_every_open_argument():
    row = next(line for line in README.splitlines() if line.startswith("| `open` |"))
    listed = set(re.findall(r"`([a-z_]+)`", row.split("|")[2]))
    assert listed == set(driver.OPEN_ARGS), sorted(set(driver.OPEN_ARGS) ^ listed)


def test_readme_documents_exit_codes():
    for phrase in ["exits 0", "no case ran", "harness error", "handshake"]:
        assert phrase.lower() in README.lower(), phrase


def test_readme_documents_runner_environment_and_reply_rules():
    for phrase in ["`HOME`", "`ok` must be a JSON boolean", "a step with no `expect`"]:
        assert phrase.lower() in README.lower(), phrase
