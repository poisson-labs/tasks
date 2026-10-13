"""The verifiers export of tasks on a user's own tools: the taskset, the task, its data and the
tool server (spec §11).

Names only: each is the build's.  `tests/test_o2_server.py` says what each name does.
"""

from __future__ import annotations

from typing import Any as _Any

__all__ = [
    "OWN_TASKSET_ID",
    "OwnTasksetConfig",
    "OwnTaskData",
    "OwnTask",
    "OwnTaskset",
    "OwnToolsetConfig",
    "OwnToolset",
    "task_from_bundle",
    "bundle_from_data",
]

OWN_TASKSET_ID = ""


class OwnTasksetConfig:
    """The taskset's config: the tool file's settings (`own`), the arm and the seeds."""


class OwnTaskData:
    """One task as the wire carries it."""


class OwnTask:
    """One task: its key, its reward and metrics, its toolset and G4."""


class OwnTaskset:
    """One task per declared seed, in the order declared."""


class OwnToolsetConfig:
    """The toolset takes no configuration."""


class OwnToolset:
    """The task's block, served, answered by the simulator."""


def task_from_bundle(bundle: _Any) -> OwnTask:
    """One own-tools bundle as one task."""
    raise NotImplementedError("the own-tools export is not built yet")


def bundle_from_data(data: _Any) -> _Any:
    """The bundle a task's data carries."""
    raise NotImplementedError("the own-tools export is not built yet")
