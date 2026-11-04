"""The wheel gate's driver waits for a prompt to settle before it types at it (issue #39).

`scripts/release/drive.py` drives the built wheel's guided session in a pseudo-terminal.  At the
run's `Start? [y/N]` it waited for the prompt's text and then for one second of quiet, and typed.
On 2026-10-29 (0.3.0) the first run of the `built-in-pretty` scene lost its `y` that way: the
session had printed the prompt and was not yet reading it, an answer typed in between was read as
Enter, and Start took it for a no.  Rerun alone, the scene passed.  A prompt that draws itself
twice (the transcript of a passing run shows `Start? [y/N]Start? [y/N]`) and a machine under load
make the gap longer than a second.

The fake session here is the smallest one that has the gap: it prints the prompt, draws it again
1.4 s later, and at 2.0 s discards whatever has been typed (`tcflush`, as a terminal library that
switches the line to raw mode does) before it reads a line.  It needs a pseudo-terminal, as the
driver's does, so the test uses the same `Pty` the driver does.

- **FX39.1** the control: one second of quiet after the prompt, the driver's old rule, types into
  the gap, and the fake session reads an empty line.  A fake that cannot reproduce the race would
  make the next test mean nothing.
- **FX39.2** `settle.wait_settled` returns only after the prompt has stopped drawing itself, and
  an answer typed then is read.
- **FX39.3** it also waits for the prompt to be the last thing on the screen, and fails, with the
  screen, when it never is.
- **FX39.4** `drive.py` types `y` at a prompt only through that wait: no `.type("y"` of the
  scenes is left bare.
- **FX39.5** the control for the second cause, found by the first run of the wheel gate with only
  the settle in place: a session slow to show its next prompt (under load, as the first screens
  of a run are) leaves the last question on the screen, and a loop that answers every question it
  sees answers it twice.  The second Enter is read by the prompt after it, and the Enter the
  driver then sends on purpose reaches `Start? [y/N]` as an empty answer, which is a no.  That is
  the 0.3.0 failure again, and the settle does not touch it: the run that showed it has a fourth
  Enter at the same `› [1]` line three seconds after the third, where 0.3.1's passing run has
  three.
- **FX39.6** `settle.Answered` holds that loop to one answer until something new is on the screen:
  the same fake session reads one Enter.
- **FX39.7** `drive.py` answers the setup's questions through it, and marks it before it answers.
- **FX39.8** the guard reads the screen and not its length: a confirmation of the answered prompt
  is not a new question, a numbered question is, and so is one with no number.  A guard that
  marked after the answer, or compared lengths, stopped the first scene of the wheel gate at its
  first question, because the next question was already on the screen when the answer returned.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import pytest

from tests.fd6_support import REPO
from tests.fd9_support import Pty

FAKE = '''\
import os, select, sys, termios, time

def say(text):
    os.write(1, text.encode())

say("Start? [y/N]")
time.sleep(1.4)
say("\\rStart? [y/N]")
time.sleep(0.6)
termios.tcflush(0, termios.TCIFLUSH)
ready, _, _ = select.select([0], [], [], 8)
line = os.read(0, 100).decode() if ready else "(nothing typed)"
say("\\ngot:" + repr(line.strip()) + "\\n")
'''

NOT_LAST = '''\
import os, time
os.write(1, b"Start? [y/N]\\nstill working on something else\\n")
time.sleep(20)
'''


def session(tmp_path: Path, body: str) -> Pty:
    """A pseudo-terminal whose child is `body`, run as the `poisson_tasks` module of a folder of
    its own, which is what the driver's `Pty` starts."""
    package = tmp_path / "poisson_tasks"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "__main__.py").write_text(body)
    env = {"PATH": os.environ.get("PATH", ""), "TERM": "dumb", "HOME": str(tmp_path)}
    return Pty([], env=env, cwd=tmp_path)


def wait_settled(*args: Any, **kwargs: Any) -> None:
    """`scripts/release/settle.py`'s wait, imported when it is called so that the control above
    runs on a tree that does not have it."""
    from scripts.release.settle import wait_settled as real

    real(*args, **kwargs)


def test_fx39_1_one_second_of_quiet_types_into_the_gap_and_the_answer_is_lost(
    tmp_path: Path,
) -> None:
    pty = session(tmp_path, FAKE)
    try:
        pty.expect(r"Start\? \[y/N\]")
        pty.quiet(1.0)  # the driver's old rule
        pty.type("y", settle=0)
        pty.expect(r"got:", timeout=30)
        assert "got:''" in pty.plain or "got:'(nothing typed)'" in pty.plain, pty.plain
    finally:
        pty.close()


def test_fx39_2_a_settled_prompt_is_answered_and_the_answer_is_read(tmp_path: Path) -> None:
    pty = session(tmp_path, FAKE)
    try:
        wait_settled(pty, r"Start\? \[y/N\]", quiet_for=1.5, timeout=30)
        pty.type("y", settle=0)
        pty.expect(r"got:", timeout=30)
        assert "got:'y'" in pty.plain, pty.plain
    finally:
        pty.close()


def test_fx39_3_it_waits_for_the_prompt_to_be_the_last_line_and_fails_with_the_screen(
    tmp_path: Path,
) -> None:
    pty = session(tmp_path, NOT_LAST)
    try:
        with pytest.raises(AssertionError, match="still working on something else"):
            wait_settled(pty, r"Start\? \[y/N\]", quiet_for=0.5, timeout=2)
    finally:
        pty.close()


def test_fx39_4_drive_py_types_y_only_through_the_wait() -> None:
    text = (REPO / "scripts" / "release" / "drive.py").read_text(encoding="utf-8")
    assert "wait_settled" in text
    bare = [line.strip() for line in text.splitlines()
            if re.search(r"\.type\(\s*(\"y\"|start\b)", line)]
    assert bare == [], bare


SLOW = '''\
import os, select, time

os.write(1, b"Question? [1] ")
os.read(0, 100)
time.sleep(4.0)
os.write(1, b"\\nNEXT\\n")
ready, _, _ = select.select([0], [], [], 3)
extra = repr(os.read(0, 100).decode().strip()) if ready else "(none)"
os.write(1, ("extra:" + extra + "\\n").encode())
'''


def answer_every_question(pty: Pty, guard: Any = None) -> None:
    """The driver's setup loop, reduced: wait for quiet, stop when the next screen is there, and
    otherwise answer the question on the screen with Enter (once the guard allows, if one is given)."""
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        pty.quiet(1.0)
        if "NEXT" in pty.plain:
            return
        if guard is not None and not guard.fresh():
            time.sleep(0.5)
            continue
        if guard is not None:
            guard.mark()
        pty.send("\r", settle=1.0)
    raise AssertionError(pty.plain)


def test_fx39_5_a_loop_that_answers_every_question_it_sees_answers_a_slow_one_twice(
    tmp_path: Path,
) -> None:
    pty = session(tmp_path, SLOW)
    try:
        answer_every_question(pty)
        pty.expect(r"extra:", timeout=30)
        assert "extra:''" in pty.plain, pty.plain
    finally:
        pty.close()


def test_fx39_6_the_guard_holds_the_loop_to_one_answer_until_something_new_is_on_the_screen(
    tmp_path: Path,
) -> None:
    from scripts.release.settle import Answered

    pty = session(tmp_path, SLOW)
    try:
        answer_every_question(pty, Answered(pty))
        pty.expect(r"extra:", timeout=30)
        assert "extra:(none)" in pty.plain, pty.plain
    finally:
        pty.close()


def test_fx39_7_drive_py_answers_the_setups_questions_through_the_guard() -> None:
    text = (REPO / "scripts" / "release" / "drive.py").read_text(encoding="utf-8")
    body = text[text.index("    def setup_answers("):]
    body = body[: body.index("\ndef scene(")]
    assert "self.answered.fresh()" in body, "the loop answers without asking the guard"
    assert body.index("self.answered.mark()") < body.index("self.pty.send(ENTER"), (
        "the guard is marked after the answer, when the next question may already be on the screen")


class Screen:
    """What the guard reads of a pseudo-terminal: its text so far."""

    def __init__(self, plain: str) -> None:
        self.plain = plain


def test_fx39_8_the_guard_reads_the_screen_not_its_length() -> None:
    """The first guard compared the screen's length, and could not tell a question the session has
    not taken yet from one it has: the answered prompt leaves a confirmation line (`    › [10]`, one
    indent more than the question and drawn once where the question was drawn twice), which is
    output, and the next question can be on the screen before the driver looks.  So the guard
    compares what is on the screen with what was there at the answer.  A confirmation of the same
    prompt is not a new question; a numbered question is, though its prompt reads like the one
    before; so is a question with no number."""
    from scripts.release.settle import Answered

    question = "7. How many tasks per level?\n   › [10]   › [10]\n"
    screen = Screen(question)
    guard = Answered(screen)
    assert guard.fresh(), "nothing has been answered yet"
    guard.mark()
    assert not guard.fresh(), "the question is still on the screen"
    screen.plain += "\n    › [10]\n"
    assert not guard.fresh(), "the confirmation of the answered prompt is not a new question"
    screen.plain += "8. How many attempts at each task?\n   › [10]   › [10]\n"
    assert guard.fresh(), "a numbered question is new, though its prompt reads like the last"
    guard.mark()
    screen.plain += "\n    › [10]\nCheck it with a free request to 127.0.0.1:1? [Y/n]\n"
    assert guard.fresh(), "a question with no number, a different line, is new"
