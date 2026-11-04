"""A mistyped arm id gets the closest arm back, and the choices (issue #31, first half).

`generate --arm` and `verify --arm` took any text that was not an arm id and answered with the
shape of one and a list of nine of the knobs.  A person who typed `detph:d3` was told what an arm id
looks like and was left to find the typo; `depth:d33`, an id that is well formed and beyond what the
generator can build, was not refused at all but ended as an unexpected failure, exit 3.

- **FX31.1** a text that is not an arm id is refused as it was (a usage error, exit 2, one `error:`
  line, nothing written) and the line now says `did you mean <the nearest arm>?` when an arm is
  near it, for a transposition (`detph:d3`), a stray digit (`depth:d33`), a missing field
  (`distractor:r8`, `history:t60`), a missing letter (`faluts:f2`, `timeout:o2`) and a control arm.
- **FX31.2** the line names the choices: every knob the built-in tasks take, so a person who
  did not know `timeouts` and `ratelimits` exist is told they do.
- **FX31.3** a text that is nowhere near an arm gets the choices and no guess.
- **FX31.4** a well-formed id deeper than the generator goes is refused in one line that says how
  deep it goes, where it ended in an unexpected failure.
- **FX31.5** the controls: an arm id that is right is not refused, and an id that only needs its
  canonical spelling (`depth:d03`) is told its spelling, as before.

Each case is held against these controls and not by the words of a message beyond the two the
rule names (`did you mean` and the arm).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fd5_support import World, error_lines, invoke, prog, tree, world
from tests.o1_support import fixture
from tests.test_o2_cli import FLOWS, QUIET, work  # noqa: F401 - the fixture is used by name
from tests.test_o2_cli import invoke as invoke_own

__all__ = ["prog", "world"]

# Every knob the built-in tasks take; `landed` is the tenth knob of 0.3.0 and is offered on
# your own tools only.
KNOBS = ("depth", "distractor", "similarity", "faults", "history", "block", "arguments", "shape",
         "spread", "timeouts", "ratelimits")

COMMANDS = {
    "generate --show": lambda arm: ["generate", "--show", "--arm", arm],
    "generate": lambda arm: ["generate", "--arm", arm],
    "verify": lambda arm: ["verify", "--self-check", "--arm", arm, "--task", "1"],
}

TYPOS = [
    ("detph:d3", "depth:d3"),
    ("depth:d33", "depth:d3"),
    ("dpeth:d1+h8", "depth:d1+h8"),
    ("distractor:r8", "distractor:r8@k16"),
    ("faluts:f2", "faults:f2"),
    ("history:t60", "history:t600"),
    ("timeout:o2", "timeouts:o2"),
]


@pytest.mark.parametrize("command", list(COMMANDS))
@pytest.mark.parametrize(("typed", "near"), TYPOS)
def test_fx31_1_a_mistyped_arm_is_refused_with_the_arm_it_is_nearest(
    command: str, typed: str, near: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(COMMANDS[command](typed), prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 2, ran
    lines = error_lines(ran)
    assert len(lines) == 1 and ran.err_lines[0] == lines[0], ran
    assert f"did you mean {near}?" in lines[0], ran
    assert ran.out == "" and tree(world.work) == {}, ran


@pytest.mark.parametrize("command", list(COMMANDS))
def test_fx31_2_the_refusal_names_every_knob_the_built_in_tasks_take(
    command: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(COMMANDS[command]("detph:d3"), prog=prog, monkeypatch=monkeypatch)
    (line,) = error_lines(ran)
    assert [knob for knob in KNOBS if knob not in line] == [], line


@pytest.mark.parametrize("command", list(COMMANDS))
def test_fx31_3_a_text_nowhere_near_an_arm_gets_the_choices_and_no_guess(
    command: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(COMMANDS[command]("qqqq"), prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 2, ran
    (line,) = error_lines(ran)
    assert "did you mean" not in line, line
    assert [knob for knob in KNOBS if knob not in line] == [], line


@pytest.mark.parametrize("command", list(COMMANDS))
@pytest.mark.parametrize("arm", ["depth:d9", "depth:d33", "depth:d0"])
def test_fx31_4_an_id_deeper_than_the_generator_goes_is_refused_in_one_line(
    command: str, arm: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(COMMANDS[command](arm), prog=prog, monkeypatch=monkeypatch)
    assert ran.code in (1, 2), ran
    (line,) = error_lines(ran)
    assert ran.err_lines[0] == line and "unexpected failure" not in line, ran
    assert "1 to 8" in line, line
    assert ran.out == "" and tree(world.work) == {}, ran


@pytest.mark.parametrize("command", ["generate --show", "verify"])
def test_fx31_5_a_right_arm_is_not_refused_and_a_spelling_is_still_told(
    command: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    right = invoke(COMMANDS[command]("depth:d3"), prog=prog, monkeypatch=monkeypatch)
    assert right.code == 0 and error_lines(right) == [], right
    spelled = invoke(COMMANDS[command]("depth:d03"), prog=prog, monkeypatch=monkeypatch)
    assert spelled.code == 2, spelled
    (line,) = error_lines(spelled)
    assert "depth:d3" in line and "did you mean" not in line, line


def test_fx31_5_generate_writes_its_files_for_a_right_arm_and_nothing_for_a_wrong_one(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = invoke(["generate", "--arm", "detph:d3"], prog=prog, monkeypatch=monkeypatch)
    assert wrong.code == 2 and tree(world.work) == {}, wrong
    right = invoke(["generate", "--arm", "depth:d3"], prog=prog, monkeypatch=monkeypatch)
    assert right.code == 0 and error_lines(right) == [], right
    assert tree(world.work) != {}


def test_fx31_9_on_your_own_tools_a_mistyped_arm_gets_the_plans_nearest_arm_and_its_arms(
    work: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """The refusal on your own tools already named the plan's arms.  It now also says which one a
    mistyped id is nearest to; a text near none of them gets the arms and no guess."""
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    assert invoke_own(["init", *QUIET, "--own-file", "tools.json", *FLOWS], monkeypatch).code == 0
    held = ["depth:d1", "depth:d2", "depth:d3"]
    near = invoke_own(["generate", "--show", "--arm", "detph:d2"], monkeypatch)
    assert near.code == 2, near
    (line,) = [text for text in near.err.splitlines() if text.startswith("error: ")]
    assert "did you mean depth:d2?" in line, line
    assert [arm for arm in held if arm not in line] == [], line
    far = invoke_own(["generate", "--show", "--arm", "qqqq"], monkeypatch)
    assert far.code == 2, far
    (line,) = [text for text in far.err.splitlines() if text.startswith("error: ")]
    assert "did you mean" not in line and [arm for arm in held if arm not in line] == [], line
    right = invoke_own(["generate", "--show", "--arm", "depth:d2"], monkeypatch)
    assert right.code == 0, right
