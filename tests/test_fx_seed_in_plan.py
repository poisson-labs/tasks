"""A seed outside the plan is refused, and the refusal names the plan's seeds (issue #31, second half).

`generate --show --seed S` and `verify --seed S` judged any integer: `--seed 42` was shown, and
verified, with no word that 42 is not a seed of the plan, and nothing told the person which seeds
the plan holds.  The plan is where a task has its place: the settings file's seeds, the published
sixty when `verify` finds no settings file, and the first ten of them when `generate` finds none.

- **FX31.6** a seed the plan does not hold is a refusal (exit 1, as `--task 99` is), in one `error:`
  line first on stderr, and nothing is written.  The line names the seed, and the plan's seeds when
  there are ten or fewer, or how many there are and the places `--task` counts them in when there
  are more.
- **FX31.7** the controls, which differ in the one thing under test: a seed the plan holds is shown
  and verified, and named by its seed, in the same folder; so is the plan's own `--task N`.
- **FX31.8** the plan is the settings file's when `verify` finds one, and the flags' when `generate`
  is given `--arm` (which builds its plan from its flags): with the seeds 404, 55 and 2121 the seed 55
  is held and the seed 42 is not, and the refusal names the three.

The refusal is held against these controls, never by its words beyond the numbers it must carry.
"""

from __future__ import annotations

import pytest

from tests.fd5_support import (
    World,
    calibration,
    config,
    error_lines,
    invoke,
    prog,
    tree,
    world,
)

__all__ = ["prog", "world"]

OUT = 42  # not one of the published sixty, and not one of the three below
THREE = (404, 55, 2121)

COMMANDS = {
    "generate --show": lambda seed: ["generate", "--arm", "depth:d3", "--show", "--seed", seed],
    "verify": lambda seed: ["verify", "--arm", "depth:d3", "--seed", seed, "--self-check"],
}
BY_PLACE = {
    "generate --show": ["generate", "--arm", "depth:d3", "--show", "--task", "5"],
    "verify": ["verify", "--arm", "depth:d3", "--task", "5", "--self-check"],
}


def three_seeds(world: World) -> None:
    made = config().config_from_init_args(["--seeds", ",".join(str(s) for s in THREE)])
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")


def plan_seeds(command: str) -> list[int]:
    """The seeds the command's plan holds with no settings file."""
    sixty = calibration().seed_list()
    return list(sixty[:10]) if command == "generate --show" else list(sixty)


def numbers_in(line: str) -> set[str]:
    return {word.strip(",.;:()") for word in line.split()}


@pytest.mark.parametrize("command", list(COMMANDS))
def test_fx31_6_a_seed_outside_the_plan_is_refused_naming_the_plan(
    command: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(COMMANDS[command](str(OUT)), prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    lines = error_lines(ran)
    assert len(lines) == 1 and ran.err_lines[0] == lines[0], ran
    assert ran.out == "" and tree(world.work) == {}, ran
    line = lines[0]
    assert str(OUT) in numbers_in(line), line
    held = plan_seeds(command)
    if len(held) <= 10:
        assert [str(s) for s in held if str(s) not in numbers_in(line)] == [], line
    else:
        assert str(len(held)) in numbers_in(line), line
    assert "--task" in line, line


@pytest.mark.parametrize("command", list(COMMANDS))
def test_fx31_7_a_seed_the_plan_holds_and_its_task_number_are_not_refused(
    command: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = plan_seeds(command)[4]
    chosen = invoke(COMMANDS[command](str(seed)), prog=prog, monkeypatch=monkeypatch)
    assert chosen.code == 0 and error_lines(chosen) == [], chosen
    assert str(seed) in chosen.first, chosen.first
    by_place = invoke(BY_PLACE[command], prog=prog, monkeypatch=monkeypatch)
    assert by_place.code == 0 and str(seed) in by_place.first, by_place


@pytest.mark.parametrize("command", list(COMMANDS))
def test_fx31_8_the_plan_is_the_settings_files_or_the_flags_seeds(
    command: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`verify` counts in the settings file's seeds.  `generate --arm` builds the plan from its
    flags and not from the settings file, so there `--seeds` is what makes the plan."""
    if command == "verify":
        three_seeds(world)
        extra: list[str] = []
    else:
        extra = ["--seeds", ",".join(str(seed) for seed in THREE)]
    held = invoke([*COMMANDS[command]("55"), *extra], prog=prog, monkeypatch=monkeypatch)
    assert held.code == 0 and "55" in held.first, held
    ran = invoke([*COMMANDS[command](str(OUT)), *extra], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    (line,) = error_lines(ran)
    assert {str(OUT), *map(str, THREE)} <= numbers_in(line), line
