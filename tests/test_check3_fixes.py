"""What the third hands-on check (0.1.0rc3, 2026-10-21) found wrong in the guided session, fixed
as decided the same day, frozen as tests.

- **G1. `replies` opens the tenth episode**, in both looks, on the plan setup writes by default (10
  tasks a level, 1 attempt: 10 episodes an arm).  The pretty look's menu gave questionary a
  shortcut key per option, and questionary refuses a tenth, so the session ended with a
  `ValueError`; above nine options a menu has no shortcut keys.
- **G2. On a depth plan the run-through's last sentence and the home screen's `latest card` row read
  leaky pass@1, and say so**, as the card does: below the top level strict also asks the model to
  stop at the goal, which the top level cannot ask.
- **G4. At the run-through's first prompt, `1`, `y` and `yes` start it**, as Enter does; they used
  to land on the home screen, whose step 1 opened the run-through again.  Its second prompt takes
  `3`, `y` and `yes` the same way (decided 2026-10-21).
- **The plain look numbers each episode once** (decided 2026-10-21): it printed
  `10) 10  passed`.

The ways of driving the session and the fixture model are `tests/fd9_support.py`'s; every
expectation is computed from the files on disk, never from the session under test.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import harness_env, needs_uv
from tests.fd5_support import World, fixture_flags, world, write_config
from tests.fd9_support import (
    INTERRUPT,
    PETSTORE,
    PUBLISHED_MODEL,
    Asked,
    Keys,
    States,
    Through,
    _quiet_main,
    harness,
    home_blocks,
    in_session,
    pretty_env,
    pty_session,
    run_folder,
    states,
    stripped,
)
from tests.test_fd9_session import keyed

__all__ = ["harness_env", "states", "world"]


def _flat(text: str) -> str:
    return " ".join(text.split())


@pytest.fixture(scope="module")
def first_look(states: States, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A folder set up with setup's defaults (the first look: depth at 1, 3 and 8, 10 tasks a
    level, 1 attempt), run to the end against the fixture model and its card built."""
    target = tmp_path_factory.mktemp("check3-first-look")
    with harness(target.parent):
        write_config(target / "tasks.toml", fixture_flags(
            states.model.base_url, model=PUBLISHED_MODEL, recipe="first-look",
            tasks_per_level=None))
        assert _quiet_main(["run", "--yes"], target) == 0
        assert _quiet_main(["card"], target) == 0
    return target


def test_g1_replies_opens_the_tenth_episode_in_both_looks_on_setups_defaults(
    first_look: Path, world: World
) -> None:
    """Red on main: in the pretty look the episode menu never shows, and the session ends with
    `an unexpected failure inside poisson-tasks (ValueError)`."""
    from poisson_tasks import transcripts
    from poisson_tasks.cli._common import arm_folder

    shutil.copytree(first_look, world.work, dirs_exist_ok=True)
    run = run_folder(world.work)
    for look in ("pretty", "plain"):
        argv = ["--plain"] if look == "plain" else []
        with pty_session(argv, env=pretty_env(world), cwd=world.work) as session:
            session.expect(r"^next\s*$")
            session.quiet()
            since = len(session.plain)
            session.type("replies")
            header = session.expect(r"^(\S+), (\d+) episodes of (\S+)", since=since)
            assert header.group(2) == "10" and header.group(3) == run.name, session.plain
            session.expect(r"Which episode\?", since=since)
            session.quiet()
            if look == "pretty":
                session.send("\x1b[B" * 9, settle=0.5)
                session.send("\r")
            else:
                session.type("10")
            session.expect(r"outcome\s", since=since)
            opened = _flat(session.plain[since:].split("Which episode?")[-1])
            session.type("quit")
            assert session.wait() == 0, session.plain
        kept = [line for line in (run / arm_folder(header.group(1)) / "traces.jsonl")
                .read_text(encoding="utf-8").splitlines(keepends=True)
                if json.loads(line).get("ok")]
        calls = []
        for row in (kept[0], kept[9]):
            turn = next(turn for turn in transcripts.read_transcript(row).turns if turn.calls)
            calls.append(json.dumps(turn.calls[0][1], default=str))
        assert calls[0] != calls[1], calls  # the first and the tenth can be told apart
        assert calls[1] in opened and calls[0] not in opened, (look, calls, opened)


def _overshooting(asked: Asked) -> Any:
    """Setup's defaults but the model's name, `fixture-overshoot`: it reaches every goal and goes
    one stage past it below the top level, so strict and leaky differ there.  The key check and
    every other yes-or-no question gets no; `run`'s own question is `Through`'s."""
    if asked.kind == "ask" and asked.question.startswith("The model's name"):
        return "fixture-overshoot"
    if asked.kind == "confirm":
        return "n"
    return None


@needs_uv
def test_g2_on_a_depth_plan_the_summary_and_the_latest_card_row_read_leaky_and_name_it(
    harness_env: Path, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red on main: both read strict pass@1 (0.000 at depth:d1, where leaky is 1.000)."""
    from poisson_tasks.cli import _format

    keyed(monkeypatch, states)
    session = in_session(Keys([Through("y"), "quit"], answer=_overshooting), monkeypatch)
    assert session.keys.started, session
    cells = json.loads((run_folder(world.work) / "card" / "artifact.json")
                       .read_text(encoding="utf-8"))["cells"]
    assert all(str(cell["arm_id"]).startswith("depth:") for cell in cells), cells
    leaky = {str(cell["arm_id"]): _format.rate(float(cell["leaky_at_1"])) for cell in cells}
    strict = {str(cell["arm_id"]): _format.rate(float(cell["pass_at_1"])) for cell in cells}
    differ = [arm for arm in leaky if leaky[arm] != strict[arm]]
    assert differ, (leaky, strict)
    text = _flat(stripped(session.out))
    summary = re.search(r"You have a card for .*?From here:", text)
    assert summary is not None, session
    row = next(line for line in home_blocks(session.out)[-1] if line.startswith("latest card"))
    for said in (summary.group(0), row):
        assert "leaky pass@1" in said and "strict" not in said, said
        assert all(strict[arm] not in said for arm in differ), (said, strict)
    assert all(arm.split(":")[-1] in row and leaky[arm] in row for arm in leaky), row


@pytest.mark.parametrize("word", ["1", "y", "yes"])
def test_g4_one_y_or_yes_at_the_run_throughs_first_prompt_starts_step_one(
    word: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Step 1's first question is asked (and answered with Ctrl-C, which leaves the folder as it
    was).  Red on main: the word lands on the home screen, never at a setup question."""
    states.copy("A", world.work)

    def answer(asked: Asked) -> Any:
        return INTERRUPT if asked.module == "_init" else None

    session = in_session(Keys([word, "quit"], answer=answer), monkeypatch)
    assert any(asked.module == "_init" for asked in session.keys.asked), session
    assert re.search(r"^Step 1 of 5", stripped(session.out), re.MULTILINE), session
    assert not (world.work / "tasks.toml").exists()


@pytest.mark.parametrize("plan", ["planning", "own-depth"])
def test_g2_the_latest_card_row_stays_on_strict_where_the_card_reads_strict(
    plan: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plan that mixes depth with another knob (the planning recipe: depth and shape), and depth
    on your own tools (a write has no stage past its goal, so that card reads every knob on
    strict): the row reads strict pass@1 and says so."""
    from poisson_tasks import config, runs

    work = world.work
    with harness(work.parent):
        if plan == "planning":
            flags = fixture_flags(states.model.base_url, model=PUBLISHED_MODEL,
                                  recipe="planning", tasks_per_level=1)
        else:
            shutil.copy(PETSTORE, work / "petstore.json")
            flags = fixture_flags(states.reference.base_url, model=PUBLISHED_MODEL, levels="1,2",
                                  extra=["--own-file", "petstore.json",
                                         "--own-flow", "addPet.id:updatePetWithForm.petId"])
        write_config(work / "tasks.toml", flags)
        if plan == "own-depth":
            made = config.resolve_plan(config.load_config(work / "tasks.toml"), root=work)
            for spec in made.arms:
                for bundle in runs.own_bundles(made, spec, made.seeds):
                    states.reference.register(bundle)
        assert _quiet_main(["run", "--yes"], work) == 0
        assert _quiet_main(["card"], work) == 0
    cells = json.loads((run_folder(work) / "card" / "artifact.json")
                       .read_text(encoding="utf-8"))["cells"]
    assert any(str(cell["arm_id"]).startswith("depth:") for cell in cells), cells
    session = in_session(Keys(["quit"]), monkeypatch)
    row = next(line for line in home_blocks(session.out)[0] if line.startswith("latest card"))
    assert "strict pass@1" in row and "leaky" not in row, row


@pytest.mark.parametrize("word", ["3", "y", "yes"])
def test_g4_three_y_or_yes_at_the_run_throughs_second_prompt_starts_step_three(
    word: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setup with every default (its key check declined), one task, then `word` at the prompt
    before the run: step 3's plan and its `Start?` (answered no, so nothing is spent).  Red on
    check3's tip at `c47c1e6`: `3` is the home screen's third step and `y` and `yes` are not
    words, so `run`'s question is never asked."""
    states.copy("A", world.work)
    keyed(monkeypatch, states)

    def answer(asked: Asked) -> Any:
        return "n" if asked.kind == "confirm" else None

    session = in_session(Keys(["", word, "quit"], answer=answer), monkeypatch)
    assert session.keys.started, session
    assert re.search(r"^Step 3 of 5", stripped(session.out), re.MULTILINE), session


def test_the_plain_episode_menu_numbers_each_episode_once(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red on check3's tip at `c47c1e6`: each option reads `1)  1  passed`."""
    states.copy("D", world.work)

    def answer(asked: Asked) -> Any:
        return INTERRUPT if asked.module == "_session" else None

    session = in_session(Keys(["replies", "quit"], answer=answer), monkeypatch)
    menu = stripped(session.err).split("Which episode?")[-1]
    numbered = re.findall(r"^\s+(\d+)\)\s+(.*)$", menu, re.MULTILINE)
    assert numbered, session
    assert all(not re.match(r"\d+\s", rest) for _, rest in numbered), numbered
