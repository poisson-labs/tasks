"""The verdict on a user's own tools: the built-in outcome vocabulary, judged by replaying an
episode's calls through the simulator (spec §5.2).

Names only: each body is the build's.  `tests/test_o2_verdict.py` says what `verify` does.
"""

from __future__ import annotations

from typing import Any as _Any

__all__ = ["verify"]


def verify(
    task: _Any, turns: _Any, ended_with_reply: bool, turn_limit_hit: bool, fmt: _Any
) -> _Any:
    """The `tasks.Verdict` on one episode of `task`, a pure function of its arguments."""
    raise NotImplementedError("the own-tools verdict is not built yet")
