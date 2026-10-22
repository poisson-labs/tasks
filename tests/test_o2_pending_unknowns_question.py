"""Pending a decision: how `init` asks whether the tools of unknown effect read or write.

**Why it is open.**  The design: "It asks whether the 2 unknowns read or write", and a tool whose
effect is unknown is treated as write until the user says otherwise in `tasks.toml`
(`read = [...]`, `write = [...]`).  One question for all of them, or one each, and what Enter means,
are not said.

**Recommended.**  One question per tool whose effect is unknown, naming it, in the file's order,
after the summary: `r` for read, `w` for write, Enter to leave it unknown (and so treated as write,
and in neither list).  The answers land in `[own] read` and `write`.  If it is declined, the build
asks once, listing them, with one answer for all.
"""

from __future__ import annotations

import importlib
import io
import os
import sys
from pathlib import Path

import pytest

from tests.o1_support import fixture
from tests.o2_support import config

FLOWS = ["--own-flow", "get_order.id:refund_order.order_id"]
UNKNOWN = ["get_order", "search_orders", "refund_order", "notify_customer", "list_channels"]


class Responder(io.TextIOBase):
    """A terminal's stdin that answers a question naming one of `answers`' tools with that tool's
    answer, and Enter to any other; it records the tools each question named."""

    def __init__(self, err: io.StringIO, answers: dict[str, str]) -> None:
        self.err, self.answers, self.seen = err, answers, 0
        self.asked: list[str] = []

    def isatty(self) -> bool:
        return True

    def readline(self, size: int | None = -1) -> str:  # type: ignore[override]
        said = self.err.getvalue()[self.seen:]
        self.seen = len(self.err.getvalue())
        last = [line for line in said.splitlines() if line.strip()][-1:] or [""]
        named = [tool for tool in UNKNOWN if tool in last[0]]
        if len(named) == 1:
            self.asked.append(named[0])
            return self.answers.get(named[0], "") + "\n"
        return "\n"


def run(answers: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    err = io.StringIO()
    stdin = Responder(err, answers)
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", err)
    code = importlib.import_module("poisson_tasks.cli").main(
        ["init", "--no-check-key", "--own-file", "tools.json", "--recipe", "first-look", *FLOWS],
        prog="poisson-tasks")
    assert code == 0, err.getvalue()
    return stdin.asked


def test_one_question_per_unknown_tool_in_file_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for name in [n for n in os.environ if "API_KEY" in n]:
        monkeypatch.delenv(name)
    (tmp_path / "tools.json").write_bytes(fixture("acme-openai-chat.json"))
    asked = run({}, monkeypatch)
    assert asked == UNKNOWN
    plain = config().load_config(tmp_path / "tasks.toml")
    assert (plain.own.read, plain.own.write) == ((), ())
    (tmp_path / "tasks.toml").unlink()
    run({"get_order": "r", "search_orders": "r", "refund_order": "w", "list_channels": "r"}, monkeypatch)
    made = config().load_config(tmp_path / "tasks.toml")
    assert (made.own.read, made.own.write) == (("get_order", "search_orders", "list_channels"), ("refund_order",))
