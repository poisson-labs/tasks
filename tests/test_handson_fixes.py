"""What the hands-on pass on 0.1.0rc1 found broken on the agent-teams path, fixed as Taylor ruled on
2026-10-19, frozen as tests.

- **A preview on your own tools shows a task on your tools.**  `generate --show --arm ID` in a folder
  whose settings file has `[own]` shows the task `generate` writes for that arm, not a task on the
  built-in table; `generate --show` with a plan of several arms refuses, naming each arm it takes.
- **An own-tools request states every value its goal needs.**  On every knob but arguments, the
  target call carries every argument a value can be drawn for, required or not, and the request
  states each one that is not carried from an earlier answer, so the model is never left to ask
  which record or what to change (Petstore's `updatePet` takes the pet's `id` as an optional field;
  `updatePetWithForm` requires only `petId`).
- **The card's no-call refusal says where the replies are and what to do next**: it names each
  refused level's traces file in the run folder, and ends with a `next:` command.
- **`export` says its commands spend with no cap**, in the line right above them.
- **`verify --arm` in a folder on your own tools refuses in one line**, as `verify --tasks` refuses an
  own-tools tasks file (Taylor, 2026-10-20): it used to judge a task on the built-in table.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import config, runs
from poisson_tasks.knobs import arm_id
from tests.fd3_support import needs_uv
from tests.fd4_support import fd4_runs
from tests.fd5_support import World, invoke, world
from tests.o1_support import fixture
from tests.o2_support import arm, every_arm, fixture_sets, generator, petstore
from tests.test_o2_cli import invoke as invoke_here
from tests.test_o2_cli import work

__all__ = ["fd4_runs", "world", "work"]

QUIET = ["--yes", "--no-fetch", "--no-check-key"]


def _petstore_folder(work: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    (work / "petstore.json").write_bytes(fixture("petstore-openapi-3.0.json"))
    made = invoke_here(["init", *QUIET, "--own-file", "petstore.json", "--recipe", "error-recovery",
                        "--tasks-per-level", "2"], monkeypatch)
    assert made.code == 0, made
    return config.resolve_plan(config.load_config(work / "tasks.toml"), root=work)


def test_a_preview_on_your_own_tools_is_the_task_generate_writes(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _petstore_folder(work, monkeypatch)
    assert len(plan.arms) > 1
    refused = invoke_here(["generate", "--show"], monkeypatch)
    assert refused.code == 2, refused
    for spec in plan.arms:
        assert arm_id(spec) in refused.err, refused
    for spec in plan.arms:
        written = runs.own_bundles(plan, spec, plan.seeds)
        for place, bundle in enumerate(written, start=1):
            shown = invoke_here(["generate", "--show", "--arm", arm_id(spec), "--task", str(place)],
                                monkeypatch)
            assert shown.code == 0, shown
            assert bundle.task_id in shown.out, (arm_id(spec), place, shown.out)
    unheld = invoke_here(["generate", "--show", "--arm", "faults:f3"], monkeypatch)
    assert unheld.code == 2 and all(arm_id(spec) in unheld.err for spec in plan.arms), unheld
    (two,) = [spec for spec in plan.arms if spec.level == 2]
    first = runs.own_bundles(plan, two, plan.seeds[:1])[0]
    by_knob = invoke_here(["generate", "--show", "--knob", "faults", "--levels", "2",
                           "--seeds", str(plan.seeds[0])], monkeypatch)
    assert by_knob.code == 0 and first.task_id in by_knob.out, by_knob


def test_an_own_tools_request_states_every_value_its_goal_needs() -> None:
    for label in ("petstore", "acme-mcp", "everything"):
        toolset = fixture_sets()[label]
        for spec in every_arm(toolset):
            if spec.knob in ("arguments", "spread"):
                continue
            for seed in range(4):
                bundle = generator().generate(toolset, spec, seed)
                call = next(args for name, args in bundle.reference_calls if name == bundle.target)
                assert set(call) == {name for name, _value in bundle.stated}, (label, spec, seed)
    asked: dict[str, set[str]] = {"updatePet": {"id"}, "updatePetWithForm": {"name", "status"}}
    seen = set()
    for seed in range(60):
        bundle = generator().generate(petstore(), arm("faults", 0), seed)
        if bundle.target in asked:
            seen.add(bundle.target)
            assert asked[bundle.target] <= {name for name, _value in bundle.stated}, bundle.request
    assert seen == set(asked)


@needs_uv
def test_a_no_call_refusal_names_the_replies_and_ends_with_a_next_command(
    fd4_runs: Any, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = fd4_runs["silent"]
    folder = world.work / "runs" / Path(made.folder).name
    shutil.copytree(made.folder, folder)
    ran = invoke(["card", str(folder)], prog="poisson-tasks", monkeypatch=monkeypatch)
    assert ran.code == 1 and ran.word == "refused", ran
    named = [world.work / word for line in ran.lines for word in line.split()
             if word.endswith("traces.jsonl")]
    assert named and all(path.is_file() and folder in path.parents for path in named), ran.out
    assert ran.lines[-1].startswith("next: poisson-tasks "), ran.out


def test_export_says_its_commands_spend_with_no_cap_right_above_them(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = config.config_from_init_args(["--tasks-per-level", "1"])
    (world.work / "tasks.toml").write_text(config.dump_config(made), encoding="utf-8")
    ran = invoke(["export", "--to", "verifiers"], prog="poisson-tasks", monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    first = next(index for index, line in enumerate(ran.lines) if " @ " in line)
    above = ran.lines[first - 1].lower()
    assert "money" in above and "no cap" in above, ran.out


def test_verify_by_arm_in_a_folder_on_your_own_tools_refuses_in_one_line(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _petstore_folder(work, monkeypatch)
    for argv in (["--arm", "faults:f1", "--task", "1"], ["--arm", "faults:f1", "--seed", "7"]):
        ran = invoke_here(["verify", "--self-check", *argv], monkeypatch)
        assert ran.code == 1 and ran.out == "", ran
        assert len(ran.err.splitlines()) == 1 and ran.err.startswith("error: "), ran
