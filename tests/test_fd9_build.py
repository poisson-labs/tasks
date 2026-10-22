"""Three behaviours of the guided session's build that its frozen tests leave unpinned, each found
by a mutant that survived the build's mutation pass (2026-10-21):

- the word `card` in a folder whose card is built reads it again with `--force`, so the action
  is never an overwrite refusal (a step is offered only when its verb accepts it);
- a run folder that holds another plan is not the settings file's (`RunFacts.this_plan`), so
  the home screen's step 1 is `run`, not that run's card (the action table, state B);
- a refused card's silent arms, the arms whose every attempt made no tool call, are read from
  its records, and the step below `replies` and `card` names one (the refusal's own
  `next:`, `generate --show --arm <arm>`).
"""

from __future__ import annotations

import json

import pytest

from tests.fd5_support import World, invoke, world, write_config
from tests.fd9_support import PROG, Keys, States, folder_module, in_session, states, steps_of
from tests.test_fd9_session import answering, first_home, here

__all__ = ["states", "world"]


def test_the_word_card_reads_a_built_card_again_without_a_refusal(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    here(states, "D", world)
    copy = states.copy("D", world.tmp / "copy")
    session = in_session(Keys(["card", "quit"], answer=answering()), monkeypatch)
    commands = session.same_as()
    assert commands and commands[0][1] == "card" and "--force" in commands[0], session
    monkeypatch.chdir(copy)
    shell = invoke(commands[0][1:], prog=PROG, monkeypatch=monkeypatch,
                   stdin=Keys([], answer=answering()), check=False)
    assert shell.code == 0, shell


def test_a_run_of_another_plan_is_not_the_settings_files_and_step_1_is_run(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = here(states, "D", world)
    write_config(work / "tasks.toml", states.flags(model="fixture-reference"))
    (run,) = folder_module().read_folder(work / "tasks.toml").runs
    assert run.card == "built" and run.this_plan is False
    session = in_session(Keys(["quit"], answer=answering()), monkeypatch)
    assert steps_of(first_home(session))[0] == "run", session


def test_a_refused_cards_silent_arms_are_read_and_the_task_step_names_one(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = here(states, "D-refused", world)
    (run,) = folder_module().read_folder(work / "tasks.toml").runs
    calls: dict[str, list[int]] = {}
    for line in (run.path / "card" / "episodes.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            calls.setdefault(str(row["arm_id"]), []).append(int(row["sampled_calls"]))
    silent = {arm for arm, made in calls.items() if not any(made)}
    assert silent and set(run.silent_arms) == silent
    shown = in_session(Keys(["quit"], answer=answering()), monkeypatch)
    number = steps_of(first_home(shown)).index("task") + 1
    session = in_session(Keys([str(number), "quit"], answer=answering()), monkeypatch)
    command = session.same_as()[0]
    assert "--arm" in command and command[command.index("--arm") + 1] in silent, command
