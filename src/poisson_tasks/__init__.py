"""A deterministic generator of tool-use tasks, each generated with its verifier.

The package is also the verifiers taskset ``poisson-tasks``.  At ``verifiers==0.3.1`` a
taskset id names the top-level module the wheel's own transformation gives it (``owner/``
and ``@version`` stripped, ``-`` to ``_``, lower-cased), so ``poisson-tasks`` resolves to
this package, and the wheel then reads ``__all__`` and looks each name up: exactly one
``Taskset`` subclass and exactly one ``Env`` subclass, and no ``Harness`` (read at source in
the wheel's loader).

The two names are exported lazily (PEP 562): ``import poisson_tasks`` imports no
``verifiers``, so the generator's own users pay nothing for the export, and the loader's
``getattr`` on each listed name is what imports ``poisson_tasks.taskset`` (MP7).
"""

from __future__ import annotations

from typing import Any as _Any

__all__ = ["ExportTaskset", "PoissonTasksEnv"]


def __getattr__(name: str) -> _Any:
    if name in __all__:
        from poisson_tasks import taskset as _taskset

        return getattr(_taskset, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
