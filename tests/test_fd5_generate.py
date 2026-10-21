"""`generate`, frozen as tests.

The invariants are FD5.14, FD5.15's last clause and FD5.20's second of the front door's plan (spec
§4.2, §10.3 and P-2), with the contrast check spec §4.2 asks for:
- **FD5.14** `generate`'s files are `generate`'s bundles: one file per arm, each line turning back
  through `bundle_from_data` into the bundle `tasks.generate` returns for that arm and seed, in
  the plan's order; with `--print` the same lines go to stdout and nothing is written;
- **FD5.15** `generate --show` names its task by its arm and its place in the plan, and by its
  seed: `depth:d3 task 7 (seed …)`; with `--seed`, a seed the user chose, by the arm and the seed;
  it prints the task as a model sees it, its reference solution and the verdict on every wrong
  answer it ships with, and writes nothing;
- **FD5.20** with the platform reported as Windows, `generate` still works;
- **the contrast** is checked through the pin ledger before anything is written: the ledger's line
  is the library's sentence (`arms.describe_pins` over `knobs.check_pins`), and a refused contrast
  is exit 1, nothing written, its line the library's refused sentence.

Shapes decided here
-------------------

**1. A file's name is the arm's id made folder-safe** (`depth:d1` → `depth-d1.jsonl`), as a run
folder names an arm's folder (`fd3_support.arm_dir`); a line is `ExportTaskData`'s JSON.

**2. Where the files go**: `--out DIR`; else the settings file's `[output] tasks` folder beside it;
else `./tasks/` when the arms are given as flags.

**3. Without a settings file, the plan is the flags'**: `--arm ID` (repeatable) or `--knob K
--levels L,…`, with `--tasks-per-level N` (the published seeds' first N, ten by default) or
`--seeds S,…`, `--strictness`, `--generator-version`.

**4. `--show` alone shows the arm's first task** (the look's yes/no 18 recommends it; not pinned
here: every test names its task).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import arm_dir
from tests.fd5_support import (
    World,
    arms,
    calibration,
    config,
    error_lines,
    export,
    invoke,
    knobs,
    next_commands,
    patch_everywhere,
    prog,
    tasks,
    tree,
    world,
)

__all__ = ["prog", "world"]


def bundles_of(path: Path) -> list[Any]:
    rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [export().bundle_from_data(export().ExportTaskData.model_validate(json.loads(row)))
            for row in rows]


def published(n: int) -> tuple[int, ...]:
    return tuple(calibration().seed_list()[:n])


def specs_of(ids: list[str], **fields: Any) -> list[Any]:
    return [arms().arm_from_id(arm, **fields) for arm in ids]


def write_config(path: Path, flags: list[str]) -> Any:
    made = config().config_from_init_args(flags)
    path.write_text(config().dump_config(made), encoding="utf-8")
    return config().resolve_plan(made)


# The flag plans: argv, then the arms and seeds they ask for.
FLAG_PLANS: dict[str, tuple[list[str], Callable[[], tuple[list[Any], tuple[int, ...]]]]] = {
    "two-arms-and-seeds": (["--arm", "depth:d3", "--arm", "depth:d1", "--seeds", "404,55"],
                           lambda: (specs_of(["depth:d3", "depth:d1"]), (404, 55))),
    "a-control-arm": (["--arm", "depth:d1+h8", "--tasks-per-level", "2"],
                      lambda: (specs_of(["depth:d1+h8"]), published(2))),
    "leaky-at-version-0": (["--arm", "depth:d2", "--strictness", "leaky",
                            "--generator-version", "0", "--tasks-per-level", "1"],
                           lambda: (specs_of(["depth:d2"], strictness="leaky",
                                             generator_version="0"), published(1))),
    "a-knob-and-levels": (["--knob", "distractor", "--levels", "0,8", "--controls",
                           "--tasks-per-level", "2"],
                          lambda: (specs_of(["distractor:r0@k16", "distractor:r8@k16",
                                             "distractor:r0+len(r8)@k16"]), published(2))),
}


@pytest.mark.parametrize("name", list(FLAG_PLANS))
def test_fd5_14_each_line_of_a_file_is_the_bundle_the_library_makes(
    name: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv, expected = FLAG_PLANS[name]
    specs, seeds = expected()
    ran = invoke(["generate", *argv], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    folder = world.work / "tasks"
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        f"{arm_dir(spec)}.jsonl" for spec in specs)
    assert sorted(str(p.relative_to(world.work)) for p in world.work.rglob("*")) == sorted(
        ["tasks", *(str(Path("tasks") / f"{arm_dir(spec)}.jsonl") for spec in specs)])
    for spec in specs:
        made = bundles_of(folder / f"{arm_dir(spec)}.jsonl")
        assert made == [tasks().generate(spec, seed) for seed in seeds], spec
        assert str(Path("tasks") / f"{arm_dir(spec)}.jsonl") in ran.out


def test_fd5_14_a_settings_files_plan_goes_to_its_tasks_folder(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    (world.work / "sub").mkdir()
    plan = write_config(world.work / "sub" / "mine.toml",
                        ["--tasks-per-level", "2", "--tasks-dir", "made"])
    ran = invoke(["generate", "--config", "sub/mine.toml"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    folder = world.work / "sub" / "made"
    for spec in plan.arms:
        assert bundles_of(folder / f"{arm_dir(spec)}.jsonl") == [
            tasks().generate(spec, seed) for seed in plan.seeds]
    assert len(list(folder.iterdir())) == len(plan.arms)


def test_fd5_14_out_names_the_folder(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["generate", "--arm", "depth:d1", "--tasks-per-level", "1", "--out", "x/y"],
                 prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert bundles_of(world.work / "x" / "y" / "depth-d1.jsonl") == [
        tasks().generate(specs_of(["depth:d1"])[0], published(1)[0])]


def test_fd5_14_print_writes_every_task_to_stdout_and_nothing_to_disk(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = write_config(world.work / "tasks.toml", ["--tasks-per-level", "2"])
    ran = invoke(["generate", "--print"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    lines = ran.out.splitlines()
    made = [export().bundle_from_data(export().ExportTaskData.model_validate(json.loads(line)))
            for line in lines]
    assert made == [tasks().generate(spec, seed) for spec in plan.arms for seed in plan.seeds]
    assert sorted(p.name for p in world.work.iterdir()) == ["tasks.toml"]


# ---------------------------------------------------------------------------
# the contrast
# ---------------------------------------------------------------------------


def ledger_sentences(plan: Any) -> set[str]:
    """The library's sentence for each seed's contrast, one knob at a time."""
    found = set()
    for seed in plan.seeds:
        made = {knobs().arm_id(spec): tasks().generate(spec, seed) for spec in plan.arms}
        found.add(arms().describe_pins(knobs().check_pins(made)))
    return found


def test_fd5_14_the_contrast_is_said_in_the_librarys_sentence(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = write_config(world.work / "tasks.toml", ["--tasks-per-level", "2"])
    ran = invoke(["generate"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert any(sentence in ran.out for sentence in ledger_sentences(plan)), ran


def test_fd5_14_a_refused_contrast_writes_nothing_and_says_the_librarys_sentence(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(world.work / "tasks.toml", ["--tasks-per-level", "2"])
    real = knobs().check_pins
    refused: list[Any] = []

    def check_pins(bundles: Any) -> Any:
        report = real(bundles)
        made = dataclasses.replace(report, refused=True,
                                   violations=(("N1", "the scenarios differ"),))
        refused.append(made)
        return made

    patch_everywhere(monkeypatch, "poisson_tasks.knobs", "check_pins", check_pins)
    ran = invoke(["generate"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    assert refused, "the contrast was not checked"
    assert error_lines(ran) == [f"error: {arms().describe_pins(refused[0])}"], ran
    assert sorted(p.name for p in world.work.iterdir()) == ["tasks.toml"]


# ---------------------------------------------------------------------------
# --show
# ---------------------------------------------------------------------------


def verdicts_of(bundle: Any) -> dict[str, str]:
    """The verdict each wrong answer the task ships with earns, by the library."""
    fmt = tasks().FormatSpec(name="direct", markers=())
    out = {}
    for name, calls in bundle.negative_controls.items():
        limit = name == "turn_limit"
        turns = tuple(tasks().Turn(content="", calls=(call,), finish_reason="tool_calls")
                      for call in calls)
        if not limit:
            turns += (tasks().Turn(content="Done.", calls=(), finish_reason="stop"),)
        out[name] = tasks().verify(bundle, turns, not limit, limit, fmt).label
    return out


def squashed(text: str) -> str:
    """Text with every run of white space one space: how a task is laid out is the look's."""
    return " ".join(text.split())


def naming_line(text: str, arm: str, place: int | None, seed: int) -> list[str]:
    import re

    found = []
    for line in text.splitlines():
        if arm not in line or not re.search(rf"(?<!\d){seed}(?!\d)", line):
            continue
        if place is not None and not re.search(rf"\btask {place}\b", line):
            continue
        found.append(line)
    return found


@pytest.mark.parametrize("place", [1, 7])
def test_fd5_15_show_names_its_task_by_arm_and_place_and_shows_it_in_full(
    place: int, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["generate", "--arm", "depth:d3", "--show", "--task", str(place)], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    seed = calibration().seed_list()[place - 1]
    spec = specs_of(["depth:d3"])[0]
    bundle = tasks().generate(spec, seed)
    assert naming_line(ran.out.splitlines()[0], "depth:d3", place, seed), ran.out[:400]
    assert squashed(str(bundle.prompt)) in squashed(ran.out)
    assert squashed(bundle.system_prompt) in squashed(ran.out)
    for name, _arguments in bundle.reference_calls:
        assert name in ran.out
    for control, label in verdicts_of(bundle).items():
        assert any(control in line and label in line for line in ran.out.splitlines()), (
            control, label)
    assert tree(world.work) == {}


def test_fd5_15_show_with_a_chosen_seed_names_the_seed(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["generate", "--arm", "depth:d2", "--show", "--seed", "4242"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    bundle = tasks().generate(specs_of(["depth:d2"])[0], 4242)
    assert naming_line(ran.out.splitlines()[0], "depth:d2", None, 4242), ran.out[:400]
    assert squashed(str(bundle.prompt)) in squashed(ran.out)
    assert tree(world.work) == {}


def test_fd5_15_show_takes_one_arm(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["generate", "--arm", "depth:d1", "--arm", "depth:d3", "--show"], prog=prog,
                 monkeypatch=monkeypatch)
    # Retrofitted by ruling G13 (FD9 Session A): no refusal; the first arm's task 1, and the other
    # arm named.
    assert ran.code == 0, ran
    assert "depth:d1" in ran.first and "depth:d3" in ran.out, ran
    assert error_lines(ran) == []


# ---------------------------------------------------------------------------
# FD5.20 on Windows
# ---------------------------------------------------------------------------


def test_fd5_20_generate_works_on_windows(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    import platform

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    ran = invoke(["generate", "--arm", "depth:d1", "--tasks-per-level", "1"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert bundles_of(world.work / "tasks" / "depth-d1.jsonl") == [
        tasks().generate(specs_of(["depth:d1"])[0], published(1)[0])]


def test_fd5_14_generate_from_a_settings_file_points_at_the_run(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(world.work / "tasks.toml", ["--tasks-per-level", "1"])
    ran = invoke(["generate"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert next_commands(ran.out)[-1:] == [f"{prog} run"], ran
