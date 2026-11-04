"""Wait for a prompt on a pseudo-terminal to settle before anything is typed at it.

`drive.py` (the wheel gate, step 6 of docs/releasing.md) types at the guided session's prompts.
A prompt can be on the screen before the session reads it: it draws itself again (a passing
run's transcript shows `Start? [y/N]Start? [y/N]`), it switches the line to a mode that discards
what is waiting, and a machine under load stretches the gap.  An answer typed in that gap is read
as Enter, and `Start? [y/N]` takes Enter for a no: the first run of the `built-in-pretty` scene
lost its `y` that way on 2026-10-29 (0.3.0).  So the driver waits until the prompt has been on the
screen, and nothing has been written, for `SETTLE` seconds, and only then types.

Standard library only: `tests/test_fx_drive_settle.py` runs it against a fake session.
"""

from __future__ import annotations

import re
import time
from typing import Any

__all__ = ["SETTLE", "wait_settled"]

SETTLE = 3.0
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


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
