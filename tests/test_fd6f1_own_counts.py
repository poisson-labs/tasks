"""The counts `init` and `doctor` print for a set of your own tools are the set's after you have
said what each tool does, not only what the file says (FD6 follow-up 1, fix 9).

A file that does not say whether a tool reads or writes (an OpenAI tools file never does) leaves
every tool "not known (treated as write)".  You then say it in `tasks.toml` (`[own] read` and
`write`, or `--own-read` and `--own-write`), or answer `init`'s question about each such tool.
Until this fix the summary counted the file alone, so three tools declared as reads still read
"0 read, 5 not known".  Now every place that states the counts states the same ones: `init`'s
summary, its result line, `doctor`'s summary, `init --json`, and the plan a run writes (its `own`
carries the declared names, and the set made from the plan counts the same).

The counts are computed here from the effects of the set made the way the plan makes it, never from
the code under test, and the control rows pin that a declaration of nothing leaves the file's own
counts alone.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import config, runs
from tests.o1_support import fixture
from tests.test_o2_cli import QUIET, Answers, invoke, offered_recipes, work

__all__ = ["work"]

MADE_UP_KEY = "sk-made-up-for-the-counts-test"
LINE = re.compile(r"(\d+) tools: (\d+) read, (\d+) write, (\d+) not known \(treated as write\), "
                  r"(\d+) refused")
ORDER = ["get_order", "search_orders", "refund_order", "notify_customer", "list_channels"]


def counts(tools: Any) -> tuple[int, int, int, int]:
    """(tools, read, write, not known) of a set, counted from the tools' own effects."""
    effects = [tool.effect for tool in tools]
    return (len(effects), effects.count("read"), effects.count("write"), effects.count("unknown"))


def said(text: str) -> tuple[int, int, int, int]:
    """The four numbers of the one summary line in `text`."""
    (found,) = LINE.findall(text)[:1] or [None]
    assert found is not None, text
    total, read, write, unknown, _ = (int(each) for each in found)
    return (total, read, write, unknown)


def declare(read: list[str], write: list[str]) -> list[str]:
    flags: list[str] = []
    for name in read:
        flags += ["--own-read", name]
    for name in write:
        flags += ["--own-write", name]
    return flags


# (file, declared reads, declared writes, the counts after: tools, read, write, not known)
CASES = [
    pytest.param("acme-openai-chat.json", [], [], (5, 0, 0, 5), id="openai-nothing-declared"),
    pytest.param("acme-openai-chat.json", ORDER[:2] + ORDER[4:], [], (5, 3, 0, 2),
                 id="openai-three-reads"),
    pytest.param("acme-openai-chat.json", ORDER[:2] + ORDER[4:], ORDER[2:4], (5, 3, 2, 0),
                 id="openai-reads-and-writes"),
    pytest.param("acme-openai-chat.json", [], ORDER[:1], (5, 0, 1, 4), id="openai-one-write"),
    # the file says get_order reads; a declaration wins over the file
    pytest.param("acme-mcp-tools-list.json", [], ["get_order"], (5, 2, 3, 0),
                 id="mcp-write-over-the-files-read"),
    pytest.param("acme-mcp-tools-list.json", [], [], (5, 3, 2, 0), id="mcp-nothing-declared"),
]


@pytest.mark.parametrize(("name", "read", "write", "expected"), CASES)
def test_init_says_the_counts_after_what_you_declared(
    name: str, read: list[str], write: list[str], expected: tuple[int, int, int, int],
    work: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (work / "tools.json").write_bytes(fixture(name))
    ran = invoke(["init", *QUIET, "--own-file", "tools.json", *declare(read, write)], monkeypatch)
    assert ran.code == 0, ran
    assert said(ran.err) == expected, ran.err
    # the result line says the same thing as the summary printed before it
    row = next(line for line in ran.out.splitlines() if line.strip().startswith("your tools"))
    assert said(row) == expected, row


def test_doctor_says_the_same_counts_as_init(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", MADE_UP_KEY)
    (work / "tools.json").write_bytes(fixture("acme-openai-chat.json"))
    flags = declare(ORDER[:2] + ORDER[4:], ORDER[2:3])
    made = invoke(["init", *QUIET, "--own-file", "tools.json", *flags], monkeypatch)
    assert made.code == 0, made
    ran = invoke(["doctor", "--offline"], monkeypatch)
    assert ran.code == 0, ran
    row = next(line for line in ran.out.splitlines() if line.strip().startswith("tools"))
    assert said(row) == said(made.err) == (5, 3, 1, 1), (row, made.err)


def test_the_answers_to_the_per_tool_question_are_counted(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dialogue asks about each tool of unknown effect, in the file's order; what is answered
    is written to `tasks.toml` and is what the result line counts."""
    (work / "tools.json").write_bytes(fixture("acme-openai-chat.json"))
    stdin = Answers(["", "", "", "", str(len(offered_recipes()) + 1), "tools.json",
                     "r", "r", "w", "", "r"])
    ran = invoke(["init", "--no-check-key"], monkeypatch, stdin)
    assert ran.code == 0, ran
    written = config.load_config(work / "tasks.toml")
    assert written.own is not None
    assert (list(written.own.read), list(written.own.write)) == (
        ["get_order", "search_orders", "list_channels"], ["refund_order"])
    row = next(line for line in ran.out.splitlines() if line.strip().startswith("your tools"))
    assert said(row) == (5, 3, 1, 1), row


def test_init_json_the_summary_and_the_plan_agree(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`init --json` names the tools still not known; that list, the summary's number, and the
    set the plan makes (its `own` holds the declared names) all count the same."""
    (work / "tools.json").write_bytes(fixture("acme-openai-chat.json"))
    flags = declare(ORDER[:2] + ORDER[4:], [])
    ran = invoke(["init", *QUIET, "--own-file", "tools.json", *flags, "--json"], monkeypatch)
    assert ran.code == 0, ran
    document = json.loads(ran.out)["tools"]
    total, read, write, unknown = said(ran.err)
    assert (total, read, write, unknown) == (5, 3, 0, 2)
    assert document["tools"] == total
    assert document["unknown"] == ["refund_order", "notify_customer"]
    assert len(document["unknown"]) == unknown

    made = config.load_config(work / "tasks.toml")
    plan = config.resolve_plan(made, root=work)
    held = runs._plan_document(plan)["plan"]["own"]
    assert held["tools"] == total
    assert (held["read"], held["write"]) == (["get_order", "search_orders", "list_channels"], [])
    assert counts(config.plan_toolset(plan).tools) == (total, read, write, unknown)
