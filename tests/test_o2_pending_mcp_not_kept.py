"""Pending a decision: `init --mcp-command` keeps the listed tools, not the command.

**Why it is open.**  The design: with `--mcp-command` "there is no file of yours: Tasks saves the
merged `tools/list` result ... as canonical JSON (`tools.mcp.json`) beside `tasks.toml`, and the
digest covers that file".  The `[own]` keys do not include the command, and the equivalent command
must write the same file; whether the command is kept to list the tools again is not said.

**Recommended.**  `[own] file = "tools.mcp.json"`, the command kept nowhere; the equivalent command
says `--own-file tools.mcp.json`, so it writes the same file without starting the server; the plan's
digest is the saved file's.  If it is declined, the build keeps the command in `[own]` and lists the
tools on every run, which starts the user's program each time.
"""

from __future__ import annotations

import hashlib
import importlib
import io
import shlex
import sys
from pathlib import Path

import pytest

from poisson_tasks import arms
from tests.o1_support import FAKE_MCP_SERVER
from tests.o2_support import config


def test_the_file_names_the_saved_list_and_the_command_is_kept_nowhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(arms, "SHIPPED_KNOBS", ("faults",))
    command = shlex.join([sys.executable, str(FAKE_MCP_SERVER), str(tmp_path / "log"), str(tmp_path / "marker")])
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    code = importlib.import_module("poisson_tasks.cli").main(
        ["init", "--yes", "--no-fetch", "--no-check-key", "--mcp-command", command, "--recipe", "error-recovery"],
        prog="poisson-tasks")
    assert code == 0
    made = config().load_config(tmp_path / "tasks.toml")
    assert made.own is not None and made.own.file == "tools.mcp.json"
    assert str(FAKE_MCP_SERVER) not in (tmp_path / "tasks.toml").read_text(encoding="utf-8")
    words = config().equivalent_init_command(made, prog="poisson-tasks")
    assert "--mcp-command" not in words and words[words.index("--own-file") + 1] == "tools.mcp.json"
    plan = config().resolve_plan(made, root=tmp_path)
    assert plan.own["file_digest"] == hashlib.sha256((tmp_path / "tools.mcp.json").read_bytes()).hexdigest()
