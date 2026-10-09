"""The command a user types: `poisson-tasks` and its seven verbs, `init`, `generate`, `run`, `card`,
`verify`, `export` and `doctor`.

Names only: nothing is built yet.  `tests/test_fd5_*.py` say what each name does.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

__all__ = ["main", "build_parser"]


def build_parser(prog: str) -> argparse.ArgumentParser:
    """The command's parser, every usage line and command it names starting with `prog`."""
    raise NotImplementedError("the command is not built yet")


def main(argv: Sequence[str] | None = None, *, prog: str | None = None) -> int:
    """Run the command on `argv` (the process's own arguments by default) and return its exit
    code; `prog` is the command's name as the user typed it."""
    raise NotImplementedError("the command is not built yet")
