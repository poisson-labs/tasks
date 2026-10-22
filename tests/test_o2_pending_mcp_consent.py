"""Pending a decision: `--yes` beside `--mcp-command` is the consent to start the user's server.

**Why it is open.**  The design: Tasks starts the user's MCP server "only to list its tools, with
your consent", and lists `--mcp-command CMD` among `init`'s flags, and under `--yes` `init` asks
nothing.

**Recommended.**  A user who typed `--mcp-command` and `--yes` has consented; without `--yes` the
dialogue asks before anything starts.  If it is declined, the build makes `--mcp-command` refuse
under `--yes` unless a flag of its own (`--start-server`, say) is given.
"""

from __future__ import annotations

import importlib
import io
import shlex
import sys
from pathlib import Path

import pytest

from poisson_tasks import arms, own
from tests.o1_support import FAKE_MCP_SERVER


def test_init_yes_lists_the_servers_tools_without_asking(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(arms, "SHIPPED_KNOBS", ("faults",))
    command = shlex.join([sys.executable, str(FAKE_MCP_SERVER), str(tmp_path / "log"), str(tmp_path / "marker")])
    listed = own.list_mcp_tools(command, consent=True)
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    code = importlib.import_module("poisson_tasks.cli").main(
        ["init", "--yes", "--no-fetch", "--no-check-key", "--mcp-command", command, "--recipe", "error-recovery"],
        prog="poisson-tasks")
    assert code == 0, err.getvalue()
    assert (tmp_path / "tools.mcp.json").read_bytes() == listed
    assert not (tmp_path / "marker").exists()
