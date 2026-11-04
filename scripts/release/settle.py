"""Wait for a prompt on a pseudo-terminal to settle before anything is typed at it.

`drive.py` (the wheel gate, step 6 of docs/releasing.md) types at the guided session's prompts.
A prompt can be on the screen before the session reads it: it draws itself again (a passing
run's transcript shows `Start? [y/N]Start? [y/N]`), it switches the line to a mode that discards
what is waiting, and a machine under load stretches the gap.  An answer typed in that gap is read
as Enter, and `Start? [y/N]` takes Enter for a no: the first run of the `built-in-pretty` scene
lost its `y` that way on 2026-10-29 (0.3.0).  So the driver waits until the prompt has been on the
screen, and nothing has been written, for `SETTLE` seconds, and only then types.

A second cause of the same failure is a question answered twice.  A session under load can be
slow to take an answer and show the next prompt, and a driver that answers whatever question is on
the screen answers the same one again.  The second Enter is read by the prompt after it, and the
Enter the driver sends on purpose then reaches `Start? [y/N]` as an empty answer, which is a no.
The first run of the wheel gate with only the wait above showed it: a fourth Enter at the same
line three seconds after the third, where 0.3.1's passing run has three.  `Answered` holds the
driver to one answer until the screen has something new on it.

Standard library only: `tests/test_fx_drive_settle.py` runs it against a fake session.
"""

from __future__ import annotations

import re
import time
from typing import Any

__all__ = ["SETTLE", "Answered", "wait_settled"]

SETTLE = 3.0
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_NUMBERED = re.compile(r"\s*\d+\. \S")


def wait_settled(
    pty: Any, prompt: str, *, since: int = 0, quiet_for: float = SETTLE, timeout: float = 120.0,
    last_line: bool = True,
) -> None:
    """Return once `prompt` (a regular expression) is on the screen from character `since` on and
    nothing has been written for `quiet_for` seconds.  With `last_line` the prompt must also be
    in the last line that has text, so a screen that has moved on is not mistaken for a prompt
    that is waiting.  `pty` is a `tests.fd9_support.Pty`.  Raises `AssertionError` with the end of
    the screen when that does not happen within `timeout` seconds, or when the session ends."""
    deadline = time.monotonic() + timeout
    while True:
        pty.quiet(quiet_for, timeout=max(timeout, quiet_for))
        screen = _CONTROLS.sub("", pty.plain[since:])
        lines = [line for line in screen.splitlines() if line.strip()]
        found = bool(lines) and bool(re.search(prompt, lines[-1] if last_line else screen))
        if found:
            return
        if time.monotonic() > deadline or pty.process.poll() is not None:
            raise AssertionError(f"{prompt!r} never settled"
                                 f"{' as the last line' if last_line else ''}\n{screen[-1500:]}")


class Answered:
    """Remembers what was on the screen when the driver last answered, so that a question is
    answered once.  `mark()` is called just before an answer is sent, and `fresh()` is true when the
    session has put something new to answer on the screen since: a numbered question
    (`7. How many tasks per level?`) that was not there, or a last line that is not the one
    answered.  The answered prompt leaves a confirmation line (`    › [10]`, drawn once where the
    question was drawn twice, `› [10]   › [10]`), which reads like the question and is not a new
    one.  Nothing has been answered at the start, so it is fresh.

    It is marked before the answer and not after, because a session that takes the answer quickly
    has the next question on the screen by the time the answer returns."""

    def __init__(self, pty: Any) -> None:
        self.pty = pty
        self._seen: tuple[str, int] | None = None

    def _state(self) -> tuple[str, int]:
        text = _CONTROLS.sub("", self.pty.plain)
        lines = [line for line in text.splitlines() if line.strip()]
        words = (lines[-1] if lines else "").split()
        half = len(words) // 2
        if half and len(words) % 2 == 0 and words[:half] == words[half:]:
            words = words[:half]  # a prompt is drawn twice on its line
        return " ".join(words), sum(1 for line in lines if _NUMBERED.match(line))

    def fresh(self) -> bool:
        if self._seen is None:
            return True
        last, numbered = self._state()
        return numbered > self._seen[1] or last != self._seen[0]

    def mark(self) -> None:
        self._seen = self._state()
