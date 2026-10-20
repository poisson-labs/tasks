"""`init`'s own-tools path and `doctor` on a settings file with `[own]`, frozen as tests.

Spec §8.1: question 6 of the front door's `init` lists the recipes on the built-in tasks first,
then "Tasks on my own tools: an OpenAI tools file, an MCP tool list, or an OpenAPI spec", then the
knob menu; there is one question 6.  Choosing own tools asks for the file, reads it, prints one
summary line, then each refusal; asks whether the unknowns read or write; offers the recipes that
apply to this set, with `tool-choice` as the default; and writes the file.  §8.2: `doctor`
re-reads the file and reports the same summary.  Taylor's rulings of 2026-10-13: the command is
`poisson-tasks`, and there is no umbrella command; the command line is being built now (FD5
Session B, branch `fd5-a`), so these tests are written against the spec and the command's public
behaviour as FD5 Session A froze it, and they fail on any tree without `poisson_tasks.cli` until
FD5 merges.  O2 Session B builds these parts after that.

The command's public behaviour these tests rely on, every piece from FD5 Session A's frozen tests:
`cli.main(argv, prog=...)` returns the exit code; under `--yes` `init` reads no stdin;
`--no-fetch` and `--no-check-key` open no socket; the dialogue is asked on stderr and read a line
at a time from a stdin that says it is a terminal (`isatty()`, `readline()`), Enter taking a
question's default and a menu's answer being its number; with no key variable set and
`--no-check-key`, question 6 is the fifth line read; question 6's entries are the offered recipes
in `arms.RECIPES`' order, numbered from 1.

Shapes decided here
-------------------

**1. Question 6's own-tools entry** is the one after the offered recipes, and choosing the knob
yourself is the one after it.  (FD5's frozen test of question 6 answers "3" for `custom`, which
today is the third entry; with own tools in the spec's place it is the fourth.  That frozen test
needs a retrofit, a ruling owed to Taylor.)

**2. The file `init` writes** is the library's, `dump_config(config_from_init_args(flags))` with
the run's estimate making the default cap when a price is set, as FD5 pins it, the own-tools
flags among the flags and `--recipe` the set's default recipe when none is given
(`own.recipes.default_recipe`).

**3. The summary** is `own.summary(reading)`: its first line, then each refusal's line, printed
in that order before the file is written.
"""

from __future__ import annotations

import dataclasses
import importlib
import io
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import arms as arms_module
from poisson_tasks import own
from tests.fd2_fakes import network_guard
from tests.o1_support import fixture
from tests.o2_support import config, recipes, runs

PROG = "poisson-tasks"
QUIET = ["--yes", "--no-fetch", "--no-check-key"]
FLOWS = ["--own-flow", "search_orders.orders[].order_id:get_order.order_id",
         "--own-flow", "get_order.order_id:refund_order.order_id"]


def cli() -> Any:
    return importlib.import_module("poisson_tasks.cli")


@dataclasses.dataclass(frozen=True)
class Ran:
    code: int
    out: str
    err: str

    @property
    def said(self) -> str:
        return self.out + self.err


class Answers(io.TextIOBase):
    """A terminal's stdin answering each line read with the next answer, then Enter."""

    def __init__(self, answers: Sequence[str] = ()) -> None:
        self.answers = list(answers)
        self.reads = 0

    def isatty(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def readline(self, size: int | None = -1) -> str:  # type: ignore[override]
        self.reads += 1
        return (self.answers.pop(0) if self.answers else "") + "\n"


class NoStdin(io.TextIOBase):
    def isatty(self) -> bool:
        return False

    def readline(self, size: int | None = -1) -> str:  # type: ignore[override]
        raise AssertionError("the command read stdin")


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A world of the test's own, as FD5's: home, working folder and temporary folder; colour off;
    no provider or key variable."""
    for name in ("home", "work", "tmp"):
        (tmp_path / name).mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.setattr(tempfile, "tempdir", None)
    monkeypatch.chdir(tmp_path / "work")
    for name in list(os.environ):
        if any(part in name.upper() for part in ("API_KEY", "TOKEN", "SECRET")) or name in (
                "OPENAI_BASE_URL", "OPENAI_ORG_ID", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("COLUMNS", "100")
    return tmp_path / "work"


def invoke(argv: Sequence[str], monkeypatch: pytest.MonkeyPatch, stdin: Any = None) -> Ran:
    out, err = io.StringIO(), io.StringIO()
    saved = sys.stdin, sys.stdout, sys.stderr
    sys.stdin = stdin if stdin is not None else NoStdin()
    sys.stdout, sys.stderr = out, err
    try:
        with network_guard(monkeypatch):
            try:
                code = cli().main(list(argv), prog=PROG)
            except SystemExit as stop:
                code = stop.code if isinstance(stop.code, int) else 1
    finally:
        sys.stdin, sys.stdout, sys.stderr = saved
    return Ran(code=int(code or 0), out=out.getvalue(), err=err.getvalue())


def library_file(flags: Sequence[str], root: Path) -> str:
    """The file the library writes for `init`'s flags, the default cap from the estimate."""
    made = config().config_from_init_args(list(flags))
    if made.model.price is not None and "--spend-cap" not in flags:
        estimate = runs().estimate(config().resolve_plan(made, root=root))
        made = config().config_from_init_args(list(flags), expected_dollars=estimate.dollars_expected)
    text: str = config().dump_config(made)
    return text


def offered_recipes() -> list[str]:
    return [name for name, recipe in arms_module.RECIPES.items() if recipe.offered]


def acme_set() -> own.OwnToolSet:
    from tests.o2_support import acme

    return acme("mcp", name="tools")


# --------------------------------------------------------------------------
# init under --yes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("shipped", [None, ("similarity",)], ids=["as-shipped", "similarity"])
def test_init_yes_with_own_flags_writes_the_librarys_file_with_the_sets_default_recipe(
    shipped: tuple[str, ...] | None, work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whatever `arms.SHIPPED_KNOBS` holds: as it ships, and with similarity shipped, when the
    set's default is `tool-choice` and no longer depth's `first-look`."""
    if shipped is not None:
        monkeypatch.setattr(arms_module, "SHIPPED_KNOBS", shipped)
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    from tests.o2_support import acme_flows

    default = recipes().default_recipe(acme_set(), flows=acme_flows())
    assert default is not None
    ran = invoke(["init", *QUIET, "--own-file", "tools.json", *FLOWS], monkeypatch)
    assert ran.code == 0, ran
    expected = library_file(["--own-file", "tools.json", *FLOWS, "--recipe", default], work)
    assert (work / "tasks.toml").read_text(encoding="utf-8") == expected


def test_init_prints_the_summary_line_then_each_refusal(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = json.loads(fixture("acme-mcp-tools-list.json"))
    listing["tools"].append({"name": "merge_orders", "description": "Merges two.",
                             "inputSchema": {"type": "object", "properties": {
                                 "ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True}}},
                             "annotations": {"readOnlyHint": False}})
    listing["tools"].append({"name": "pick", "description": "Picks.",
                             "inputSchema": {"type": "object", "properties": {"v": {"anyOf": [{"type": "string"}]}}}})
    data = json.dumps(listing).encode()
    (work / "tools.json").write_bytes(data)
    reading = own.read_tools(data, name="tools")
    lines = own.summary(reading).splitlines()
    first, refusals = lines[0], lines[1:1 + len(reading.refused)]
    assert len(refusals) == 2
    ran = invoke(["init", *QUIET, "--own-file", "tools.json", *FLOWS], monkeypatch)
    assert ran.code == 0, ran
    said = ran.said
    at = said.index(first)
    for line in refusals:
        assert said.index(line) > at
        at = said.index(line)


def test_init_writes_the_own_table_of_every_own_flag(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (work / "tools.json").write_bytes(fixture("acme-openai-chat.json"))
    flags = ["--own-file", "tools.json", "--own-format", "openai", "--own-name", "acme-support",
             "--own-read", "get_order", "--own-read", "search_orders", "--own-read", "list_channels",
             "--own-intent", "refund_order=refund a customer's order",
             "--own-flow", "get_order.id:refund_order.order_id", "--recipe", "first-look"]
    ran = invoke(["init", *QUIET, *flags], monkeypatch)
    assert ran.code == 0, ran
    assert (work / "tasks.toml").read_text(encoding="utf-8") == library_file(flags, work)
    made = config().load_config(work / "tasks.toml")
    command = config().equivalent_init_command(made, prog=PROG)
    (work / "tasks.toml").unlink()
    again = invoke([*command[1:], "--no-fetch", "--no-check-key"], monkeypatch)
    assert again.code == 0, again
    assert (work / "tasks.toml").read_text(encoding="utf-8") == library_file(flags, work)


# --------------------------------------------------------------------------
# the dialogue
# --------------------------------------------------------------------------


def test_question_six_offers_own_tools_after_the_recipes_and_the_knob_menu_after_it(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec §8.1 and Knobs §17.4: recipes, then own tools, then choosing the knob yourself.  With
    flows given as flags and every effect in the file, choosing own tools asks for the file and
    then offers the set's recipes, Enter taking the default; the file is the one `--yes` writes
    with the same answers as flags.  Whatever `arms.SHIPPED_KNOBS` holds, the flows give the set a
    recipe (depth's)."""
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    # Retrofitted by ruling G7 (FD9 Session A): own tools is the first question's second answer,
    # and the file follows the price; custom is the entry after the recipes.
    custom_entry = str(len(offered_recipes()) + 1)
    stdin = Answers(["2", "", "", "", "", "tools.json"])
    ran = invoke(["init", "--no-check-key", *FLOWS], monkeypatch, stdin)
    assert ran.code == 0, ran
    from tests.o2_support import acme_flows

    default = recipes().default_recipe(acme_set(), flows=acme_flows())
    assert default is not None
    written = (work / "tasks.toml").read_text(encoding="utf-8")
    assert config().load_config(work / "tasks.toml").own is not None
    (work / "tasks.toml").unlink()
    yes = invoke(["init", "--yes", "--no-check-key", "--own-file", "tools.json", *FLOWS,
                  "--recipe", default], monkeypatch)
    assert yes.code == 0, yes
    assert (work / "tasks.toml").read_text(encoding="utf-8") == written
    (work / "tasks.toml").unlink()
    custom = invoke(["init", "--no-check-key"], monkeypatch,
                    Answers(["", "", "", "", "", custom_entry]))
    assert custom.code == 0, custom
    made = config().load_config(work / "tasks.toml")
    assert (made.measure.preset, made.own) == ("custom", None)


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def test_doctor_reads_the_tool_file_again_and_reports_the_same_summary(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = fixture("acme-mcp-tools-list.json")
    (work / "tools.json").write_bytes(data)
    assert invoke(["init", *QUIET, "--own-file", "tools.json", *FLOWS], monkeypatch).code == 0
    ran = invoke(["doctor", "--offline"], monkeypatch)
    first = own.summary(own.read_tools(data, name="tools")).splitlines()[0]
    assert first in ran.said, ran
    assert own.read_tools(data).toolset.file_digest in ran.said


def test_init_lists_depth_and_shape_as_unavailable_with_the_specs_sentence_without_flows(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec §6.2: without flows, depth and shape "are listed as unavailable with the sentence".  A set
    with flows hears no such line."""
    from tests.o2_support import generator

    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    sentence = generator().UNAVAILABLE_WITHOUT_FLOWS
    without = invoke(["init", *QUIET, "--own-file", "tools.json", "--recipe", "first-look"], monkeypatch)
    assert sentence in without.said, without
    (work / "tasks.toml").unlink(missing_ok=True)
    with_flows = invoke(["init", *QUIET, "--own-file", "tools.json", *FLOWS], monkeypatch)
    assert with_flows.code == 0, with_flows
    assert sentence not in with_flows.said
