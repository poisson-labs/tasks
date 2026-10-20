"""What a folder holds, read from disk alone: the facts the guided session's home screen shows
(spec §16.2).

`read_folder(config_path)` reads the settings file, the environment, whether the key's variable is
set, the tool file's counts on your own tools, every run folder under the settings' `runs` folder
and the newest card's levels.  It opens no socket and does not load the tokenizer.  `Folder` holds
facts only: no sentence and no command.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any

__all__ = ["Folder", "RunFacts", "ToolsFacts", "read_folder"]


@dataclasses.dataclass(frozen=True)
class RunFacts:
    """One run folder: its `name` and `path`; `kept` of `total` episodes, counted as a resume
    counts them; `spent_usd` from its ledger (`None` without a price); `card`, `"built"`,
    `"refused"` or `None`; `locked`, whether a process holds its `run.lock` now; and
    `this_plan`, whether it holds the settings file's plan."""

    name: str
    path: Path
    kept: int
    total: int
    spent_usd: float | None
    card: str | None
    locked: bool
    this_plan: bool


@dataclasses.dataclass(frozen=True)
class ToolsFacts:
    """Your own tools, as the tool file reads with the effects you declared: the set's `name`,
    its `tools`, how many were `refused`, and how many `flows` are declared."""

    name: str
    tools: int
    refused: int
    flows: int


@dataclasses.dataclass(frozen=True)
class Folder:
    """The facts of one folder.  `settings` is the settings file's config, or `None` when there
    is none or the reader refuses it (`problem` then holds the reader's words); `environment` is
    `providers.environment_report()`; `runs` is newest first; `levels` is the newest card's
    (arm id, strict pass@1) per level, empty when no card is built."""

    config_path: Path
    settings: Any | None
    problem: str | None
    environment: Any
    key_variable: str | None
    key_set: bool
    tools: ToolsFacts | None
    runs: tuple[RunFacts, ...]
    levels: tuple[tuple[str, float], ...]


def read_folder(config_path: str | os.PathLike[str]) -> Folder:
    """The facts of the folder whose settings file is `config_path`, from disk alone."""
    raise NotImplementedError("read_folder is built in FD9's Session B")
