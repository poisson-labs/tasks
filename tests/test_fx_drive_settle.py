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
"""

from __future__ import annotations

import os
import re
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
