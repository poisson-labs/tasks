"""What a verb builds: one result, printed by either renderer or as JSON.

Every verb builds one `Result`: the verdict word, its sentence, the detail (rows, bullets, a
command to copy, the card's levels, a document's parts) and the next commands.  The plain and
the pretty renderers print it; `--json` is `as_json()`.  A problem is raised: a `Refusal`
(nothing spent or written, exit 1) or a `Usage` error (the command line is wrong, exit 2).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence
from typing import Any


@dataclasses.dataclass
class Row:
    """One `label  value` line.  `status` is `doctor`'s per-line word: `"ok"` or `"bad"`.
    `apart` keeps a long label out of the column the other rows line up on: it takes two spaces
    after it, and the other rows keep the width their own labels need."""

    label: str
    value: str
    status: str | None = None
    apart: bool = False


@dataclasses.dataclass
class Bullets:
    """A label followed by one line per item."""

    label: str
    items: list[str]


@dataclasses.dataclass
class Command:
    """A command for the user to copy: printed broken before its flags with backslashes, so it
    is readable and still pastes as one command."""

    label: str
    argv: list[str]


@dataclasses.dataclass
class Levels:
    """The card's levels, one cell per arm: `arm_id`, `state` (`complete`, `incomplete` or
    `not run`), `pass_at_1`, `interval`, `leaky_at_1`, `overshoot`, `tasks`, `tasks_planned`
    and `attempts`."""

    cells: list[dict[str, Any]]


@dataclasses.dataclass
class Part:
    """One section of a document, printed after a blank line: `quote` (text the model is shown,
    word for word), `text`, `lines` (one per line, as written), `document` (a whole document,
    as written), `tools` (name, parameters, whether the reference solution calls it), `steps`
    (name, arguments, what came back) or `answers` (what, outcome, why)."""

    title: str
    kind: str
    body: Any


@dataclasses.dataclass
class Result:
    """The one result a verb builds."""

    schema: str
    verdict: str
    sentence: str
    tone: str = "good"
    rows: list[Any] = dataclasses.field(default_factory=list)
    document: list[Part] = dataclasses.field(default_factory=list)
    next: list[str] = dataclasses.field(default_factory=list)
    exit: int = 0
    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    silent: bool = False
    """True when stdout already holds the verb's data (`generate --print`): nothing more is
    printed, in any style."""

    def as_json(self) -> str:
        document: dict[str, Any] = {
            "schema": self.schema,
            "verdict": self.verdict,
            "sentence": self.sentence,
            **self.data,
        }
        if self.next:
            document["next"] = list(self.next)
        return json.dumps(document, indent=2, allow_nan=False, ensure_ascii=False) + "\n"


class Refusal(Exception):
    """An `error:` line: nothing was spent or written.  Exit 1."""

    def __init__(self, message: str, next: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.next = list(next)


class Usage(Exception):
    """The command line is wrong: one `error:` line, exit 2."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Stopped(Exception):
    """A verb stopped by the user: a `stopped` verdict on stdout and the exit code given."""

    def __init__(self, result: Result) -> None:
        super().__init__(result.sentence)
        self.result = result


TONES = ("good", "neutral", "warn", "bad")
