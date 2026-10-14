"""The verifiers taskset ``poisson-tasks-own``: Poisson Tasks on a user's own tools.

At ``verifiers==0.3.1`` a taskset id names a top-level module (``owner/`` and ``@version``
stripped, ``-`` to ``_``), and a dotted id fails inside its loader, so the own-tools taskset
needs a module of its own beside ``poisson_tasks`` in the same wheel (ruled 2026-10-13, O2
Session A's yes/no 1).  The wheel reads ``__all__`` and looks each name up: exactly one
``Taskset`` subclass, ``poisson_tasks.own.export.OwnTaskset``, and one ``Env`` subclass, the
measured ``null`` harness's ``poisson_tasks.taskset.PoissonTasksEnv``.

Both are exported lazily (PEP 562): ``import poisson_tasks_own`` imports no ``verifiers``.
"""

from __future__ import annotations

from typing import Any as _Any

__all__ = ["OwnTaskset", "PoissonTasksEnv"]


def __getattr__(name: str) -> _Any:
    if name == "OwnTaskset":
        from poisson_tasks.own import export as _export

        return _export.OwnTaskset
    if name == "PoissonTasksEnv":
        from poisson_tasks import taskset as _taskset

        return _taskset.PoissonTasksEnv
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
