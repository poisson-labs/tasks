"""What produced a run, the behaviours the 0.2.0 tests left unheld, frozen as tests once they were
ruled in (2026-10-26, for 0.2.1).

The invariants:
- on your own tools a resume of a folder started with another own-tools generator, or on another
  tool contract, is refused by `runs.run_plan` in one line before anything is written;
- a folder started before 0.2.0 (no record, episodes kept) resumed by this install writes one
  `resumed` line, and its card says it was started before 0.2.0 and resumed with this version;
- `run` refuses such a resume before the plan and its cost question are shown;
- `card --check` says a card is current exactly when its stale line is absent: from the generator
  its run recorded, on the built-in tasks and on your own tools;
- the coloured look breaks a `made with` row only between its items;
- a row that stands apart (`beside the published cards`) does not widen the label column the other
  rows line up on, in either look.

The built-in folders are copies of the `tests/fd4_support.py` scenarios and the own-tools folder is
the `own_run` fixture of `tests/test_o2_run.py`, copied before anything is edited or written.  Every
case but the `card --check` one held on the 0.2.0 tree: they pin behaviour 0.2.0 built and no test
held, so each catches a change that undoes it.  Expectations come from the folder, the plan and the
literals of `tests/pv_support.py`, never from the code under test.
"""

from __future__ import annotations

import dataclasses
import io
import json
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import needs_uv
from tests.fd4_support import RunFolders, fd4_runs
from tests.fd5_support import World, fixture_flags, invoke, world, write_config
from tests.pv_support import (
    BUILT_IN_GENERATOR,
    FIXTURE_HASHES,
    OWN_TOOLS_GENERATOR,
    PROG,
    RECORD,
    bare,
    card_md_section,
    copy_run,
    expected_record,
    invoke_json,
    other_hash,
    record_lines,
    rewrite_first_line,
    rows,
)
from tests.test_o2_run import OwnRun, own_run

__all__ = ["fd4_runs", "own_run", "world"]

STALE = ("It is pinned to the generator it was made with, which is not the one this install has, "
         "so it is stale.")
MCP_FILE, MCP_SPEC = FIXTURE_HASHES["acme-mcp-tools-list.json"]
SEPARATOR = " · "


def calibration() -> Any:
    from poisson_tasks import calibration as module

    return module


def snapshot(folder: Path) -> dict[str, bytes]:
    """Every file of the folder, by its path in it."""
    return {str(path.relative_to(folder)): path.read_bytes()
            for path in sorted(folder.rglob("*")) if path.is_file()}


# ---------------------------------------------------------------------------
# the resume, on your own tools and from before 0.2.0
# ---------------------------------------------------------------------------


@needs_uv
def test_pv_7_own_tools_a_resume_across_another_generator_or_contract_is_refused(
    own_run: OwnRun, tmp_path: Path
) -> None:
    """Copies of the own-tools run: one untouched, one whose `started` line names another
    own-tools generator, one another tool contract.  The two edited copies are refused before
    anything is written, each naming the value there and the one here; the untouched copy is not
    refused (it owes nothing, so it runs nothing)."""
    from poisson_tasks import runs

    caps = {"spend_usd": None, "tokens": 1_000_000}
    moved_generator, moved_spec = other_hash("own-tools generator"), other_hash("tool contract")
    cases = (
        ("control", {}, None),
        ("generator", {"own_generator_hash": moved_generator},
         f"({moved_generator[:12]} there, {OWN_TOOLS_GENERATOR[:12]} here)"),
        ("contract", {"tool_spec_hash": moved_spec},
         f"({moved_spec[:12]} there, {MCP_SPEC[:12]} here)"),
    )
    for name, edit, named in cases:
        copy = copy_run(own_run.folder, tmp_path / name / "runs" / own_run.folder.name)
        if edit:
            rewrite_first_line(copy, **edit)
        before = snapshot(copy)
        folder = runs.find_run(own_run.plan, tmp_path / name / "runs")
        assert Path(folder.path) == copy, folder
        if named is None:
            result = runs.run_plan(own_run.plan, folder, caps=caps, concurrency=1)
            assert (result.episodes_run, result.episodes_owed) == (0, 0), result
            continue
        with pytest.raises(ValueError) as refused:
            runs.run_plan(own_run.plan, folder, caps=caps, concurrency=1)
        message = str(refused.value).replace(str(tmp_path), "")
        assert message.strip() and "\n" not in message.strip(), message
        assert named in message, (name, message)
        assert snapshot(copy) == before, name


@needs_uv
def test_pv_7_a_run_started_before_0_2_0_and_resumed_records_resumed(
    fd4_runs: RunFolders, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `failed_once` folder before its resume, as 0.1.0 left it: no record, one episode
    owed.  Resumed by this install against the fixture model (the plan's endpoint is the new
    fixture's, so `plan.json` names it), it writes exactly one line, `resumed`, and the card says
    the run was started before 0.2.0 and resumed with this version."""
    from poisson_tasks import config, runs
    from tests.fd2_fakes import network_guard
    from tests.fixtures.model_server import FixtureModel

    made = fd4_runs["failed_once"]
    copy = copy_run(made.folder, world.tmp / "runs" / made.folder.name)
    (copy / RECORD).unlink()
    version = metadata.version("poisson-tasks")
    with fd4_runs._environment(world.tmp) as patch, FixtureModel() as model:
        plan = dataclasses.replace(
            made.plan, model=dataclasses.replace(made.plan.model, base_url=model.base_url))
        held = json.loads((copy / "plan.json").read_text(encoding="utf-8"))
        assert held["plan"]["model"]["base_url"] == made.plan.model.base_url
        held["plan"]["model"]["base_url"] = model.base_url
        held["plan_hash"] = config.plan_hash(plan)
        (copy / "plan.json").write_text(json.dumps(held, indent=2) + "\n", encoding="utf-8")
        folder = runs.find_run(plan, world.tmp / "runs")
        assert (Path(folder.path), folder.status) == (copy, "resume")
        with network_guard(patch):
            result = runs.run_plan(plan, folder, caps={"spend_usd": None, "tokens": None},
                                   concurrency=1)
    assert result.episodes_run >= 1 and result.episodes_owed == 0, result
    lines = record_lines(copy)
    assert [line["segment"] for line in lines] == ["resumed"], lines
    assert bare(lines[0]) == expected_record(plan)

    words = f"the run was started before poisson-tasks 0.2.0 (resumed with {version})"
    ran = invoke(["card", str(copy)], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert [value for label, value, _, _ in rows(ran.out) if label == "made with"] == [
        f"not recorded: {words}"], ran
    section = card_md_section((copy / "card" / "card.md").read_text(encoding="utf-8"),
                              "What produced it")
    assert f"Not recorded: {words}." in section, section


def plan_document(plan: Any) -> dict[str, Any]:
    """`plan.json` as 0.1.0 writes it (`tests/test_pv_records.py` pins its keys)."""
    from poisson_tasks import config

    return {"plan": {
        "preset": plan.preset, "arms": [dataclasses.asdict(spec) for spec in plan.arms],
        "seeds": list(plan.seeds), "attempts": plan.attempts,
        "model": dataclasses.asdict(plan.model), "decoding": dict(plan.decoding),
        "max_model_calls": plan.max_model_calls,
    }, "plan_hash": config.plan_hash(plan)}


def run_against(world: World, settings: Any, plan: Any, generator: str,
                monkeypatch: pytest.MonkeyPatch) -> Any:
    """`run` on a folder that holds the plan and a `started` line naming `generator`; the folder
    keeps its bytes and is removed after."""
    from poisson_tasks import runs

    folder = runs.find_run(plan, world.work / settings.output.runs)
    path = Path(folder.path)
    path.mkdir(parents=True)
    (path / "plan.json").write_text(json.dumps(plan_document(plan), indent=2) + "\n",
                                    encoding="utf-8")
    line = {"schema": "poisson-tasks.produced-by/1", "at": "2026-10-26T12:00:00Z",
            "segment": "started", **{key: value for key, value in expected_record(plan).items()
                                     if key != "schema"}}
    line["builtin_generator_hash"] = generator
    (path / RECORD).write_text(json.dumps(line) + "\n", encoding="utf-8")
    before = snapshot(path)
    ran = invoke(["run"], prog=PROG, monkeypatch=monkeypatch)
    assert all(address[0] == "127.0.0.1" for address in ran.connections), ran
    assert snapshot(path) == before, ran
    for name in (RECORD, "plan.json"):
        (path / name).unlink()
    path.rmdir()
    return ran


def test_pv_7_run_refuses_a_resume_across_generators_before_the_cost_question(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A settings file against the fixture model and its run folder, the folder holding the plan
    and a `started` line: in one copy the line names this install's generator, in the other
    another one.  `run` with stdin not a terminal shows the first copy's plan, cost row included,
    and then stops at the question; the second copy is refused on stderr before any of it (nothing
    on stdout), naming both generators, and its folder keeps its bytes.  The free key check is the only request either
    makes: the fixture serves no completion."""
    from poisson_tasks import config
    from tests.fd3_support import KEY, KEY_VAR
    from tests.fixtures.model_server import FixtureModel

    monkeypatch.setenv(KEY_VAR, KEY)
    moved = other_hash("generator")
    outcomes = {}
    with FixtureModel() as model:
        write_config(world.work / "tasks.toml", fixture_flags(model.base_url))
        settings = config.load_config(world.work / "tasks.toml")
        plan = config.resolve_plan(settings)
        for name, generator in (("control", BUILT_IN_GENERATOR), ("moved", moved)):
            outcomes[name] = run_against(world, settings, plan, generator, monkeypatch)
        assert model.calls() == 0, model.calls()

    control, refused = outcomes["control"], outcomes["moved"]
    assert control.code != 0 and control.word == "plan", control
    assert "cost" in [label for label, _, _, _ in rows(control.out)], control
    assert refused.code == 1 and refused.out == "", refused
    (message,) = [line.replace(str(world.work), "") for line in refused.err_lines
                  if line.startswith("error: ")]
    assert f"({moved[:12]} there, {BUILT_IN_GENERATOR[:12]} here)" in message, refused
    assert "Start?" not in refused.err, refused


# ---------------------------------------------------------------------------
# card --check says current from the record
# ---------------------------------------------------------------------------


def check_current(card: Path, monkeypatch: pytest.MonkeyPatch) -> bool:
    ran, document = invoke_json(["card", "--check", str(card)], monkeypatch)
    assert ran.code == 0, ran
    value: bool = document["data"]["current"] if "data" in document else document["current"]
    return value


@needs_uv
def test_pv_10_card_check_says_current_from_the_generator_the_run_recorded(
    fd4_runs: RunFolders, own_run: OwnRun, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Built-in: a card whose run recorded this install's generator is current; one whose run
    recorded another is not, though its block was built by this install.  Own tools: a card whose
    run recorded this install's own-tools generator is current; one whose run recorded another is
    not.  Each answer is the card's stale line read the other way."""
    cases = (
        ("strict", fd4_runs["strict"].folder, {}, True),
        ("strict-moved", fd4_runs["strict"].folder,
         {"builtin_generator_hash": other_hash("generator")}, False),
        ("own", own_run.folder, {}, True),
        ("own-moved", own_run.folder,
         {"own_generator_hash": other_hash("own-tools generator")}, False),
    )
    for name, source, edit, current in cases:
        folder = copy_run(source, world.tmp / name)
        if edit:
            rewrite_first_line(folder, **edit)
        made = invoke(["card", str(folder)], prog=PROG, monkeypatch=monkeypatch)
        assert made.code == 0, made
        document = (folder / "card" / "card.md").read_text(encoding="utf-8")
        assert (STALE in " ".join(document.split())) is (not current), (name, document)
        assert check_current(folder / "card", monkeypatch) is current, name


# ---------------------------------------------------------------------------
# the two display fixes
# ---------------------------------------------------------------------------


def rendered(width: int, result: Any) -> str:
    """The coloured look's lines for `result` on a terminal `width` columns wide, escapes
    removed."""
    from rich.console import Console
    from rich.text import Text

    from poisson_tasks.cli import _pretty

    held = io.StringIO()
    console = Console(file=held, width=width, force_terminal=True, color_system="standard",
                      highlight=False, emoji=False, legacy_windows=False)
    _pretty.Pretty(PROG, out=console, err=console).show(result)
    return Text.from_ansi(held.getvalue()).plain


def own_items() -> list[str]:
    """A `made with` row on your own tools, item by item, with the docs' wording."""
    return ["poisson-tasks 0.2.0", f"generator {BUILT_IN_GENERATOR[:12]}",
            f"own-tools generator {OWN_TOOLS_GENERATOR[:12]}",
            f"tool spec {MCP_SPEC[:12]} (an MCP tool list)",
            f"plan {other_hash('plan')[:12]} (first-look)",
            f"6 seeds, list {other_hash('seed list')[:12]}"]


@pytest.mark.parametrize("width", [56, 60, 72, 90])
def test_pv_8_the_coloured_made_with_row_breaks_only_between_items(width: int) -> None:
    """At widths where every item fits a line: every line the row takes fits the terminal and ends
    with the separator but its last, holds whole items only, and the items read in order; at 90
    columns the row takes more than one line too."""
    from poisson_tasks.cli._result import Result, Row

    items = own_items()
    result = Result(schema="poisson-tasks.test/1", verdict="ok", tone="good",
                    sentence="the card", rows=[Row("run", "first-look, 6 tasks"),
                                               Row("made with", SEPARATOR.join(items))])
    lines = rendered(width, result).splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("  made with  "))
    column = len("  made with  ")
    taken = [lines[start][column:]]
    for line in lines[start + 1:]:
        if not line.startswith(" " * column) or not line.strip():
            break
        taken.append(line[column:])
    assert len(taken) > 1, lines
    assert all(len(lines[start + index]) <= width for index in range(len(taken))), lines
    assert all(line.endswith(SEPARATOR.rstrip()) for line in taken[:-1]), taken
    assert not taken[-1].endswith(SEPARATOR.rstrip()), taken
    found = [item for line in taken
             for item in line.removesuffix(SEPARATOR.rstrip()).rstrip().split(SEPARATOR)]
    assert found == items, taken


def test_pv_8_a_row_apart_does_not_widen_the_label_column(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The own-tools card's rows: `run` and `made with` line up on the column `made with` needs,
    and `beside the published cards` takes two spaces after its own label, in both looks."""
    from poisson_tasks.cli._plain import PlainUI
    from poisson_tasks.cli._result import Result, Row

    beside = ("beside the published cards", "read on its own")
    result = Result(schema="poisson-tasks.test/1", verdict="ok", tone="good", sentence="the card",
                    rows=[Row("run", "first-look, 6 tasks"),
                          Row("made with", "poisson-tasks 0.2.0"),
                          Row(*beside, apart=True)])
    wanted = ["  run        first-look, 6 tasks", "  made with  poisson-tasks 0.2.0",
              f"  {beside[0]}  {beside[1]}"]
    coloured = [line.rstrip() for line in rendered(100, result).splitlines()[1:4]]
    assert coloured == wanted, coloured
    PlainUI(PROG).show(result)
    plain = capsys.readouterr().out.splitlines()[1:4]
    assert plain == wanted, plain
