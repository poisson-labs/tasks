"""The session's load screen (decided 2026-10-20): the Poisson distribution
at lambda = 4 as one row of eighth blocks, flat cobalt, with "poisson labs" bold beside it and
"tasks" bold with the version dim beneath, in the terminal's foreground.  26 columns by 2 rows,
its own narrow form; below its own width, and with `--plain` or `TERM=dumb`, the one line
`Poisson Labs  tasks <version>`.  Under `NO_COLOR` the same text with no escape sequence.  The
colour steps down as Rich steps it down, from the depth the terminal declares."""

from __future__ import annotations

import sys
from typing import Any

MARK = "▁▃▆██▆▄▂▁▁▁▁"
COBALT = "#3B5BDB"
SKY = "#15AABF"
NAME = "poisson labs"
GAP = "  "
WIDTH = len(MARK) + len(GAP) + len(NAME)
"""The banner's own width, 26: below it, the one line (decided 2026-10-20)."""


def _version() -> str:
    import importlib.metadata

    try:
        return importlib.metadata.version("poisson-tasks")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def one_line() -> str:
    return f"Poisson Labs  tasks {_version()}"


def text_lines() -> list[str]:
    indent = " " * (len(MARK) + len(GAP))
    return [f"{MARK}{GAP}{NAME}", f"{indent}tasks  {_version()}"]


def show(*, mode: str, width: int, stream: Any = None) -> None:
    """Print the banner and a blank line: `mode` is `colour`, `mono` or `line`."""
    out = stream if stream is not None else sys.stdout
    if mode == "line" or width < WIDTH:
        out.write(one_line() + "\n\n")
        out.flush()
        return
    if mode == "mono":
        out.write("\n".join(text_lines()) + "\n\n")
        out.flush()
        return
    from rich.console import Console
    from rich.text import Text

    console = Console(file=out, highlight=False, emoji=False, legacy_windows=False)
    first = Text.assemble((MARK, COBALT), GAP, (NAME, "bold"))
    second = Text.assemble(" " * (len(MARK) + len(GAP)), ("tasks", "bold"), "  ",
                           (_version(), "dim"))
    console.print(first, soft_wrap=True)
    console.print(second, soft_wrap=True)
    console.print()
