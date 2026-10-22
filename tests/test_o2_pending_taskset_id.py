"""Pending a decision: the own-tools taskset's verifiers id is `poisson-tasks-own`, a second
top-level module in the same wheel.

**Why it is open.**  The design gives own tools their own task data class, task and toolset, so they
need a taskset of their own, and the design does not say how verifiers finds it.  verifiers 0.3.1
resolves a taskset id to a top-level module only (`owner/` and `@version` stripped, `-` to `_`), and
a dotted id fails inside its loader: `importlib.util.find_spec("verifiers.v1.tasksets.poisson_tasks.
own.export")` raises on the missing parent before it falls back (measured 2026-10-13 against the
installed wheel).  The id `poisson-tasks` is the built-in taskset's, whose `__all__` must hold exactly
one `Taskset`.

**Recommended.**  A module `poisson_tasks_own` beside `poisson_tasks` in the same wheel
(`[tool.hatch.build.targets.wheel] packages` lists both), whose `__all__` is `OwnTaskset` and
`PoissonTasksEnv`, exported lazily so importing it loads no `verifiers`.  If it is declined, the
answer is one of: a separate distribution, or one taskset that serves both kinds of task, which the
design rules out.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib

from tests.o2_support import REPO, export


def test_the_own_taskset_id_is_poisson_tasks_own_a_top_level_module_of_the_wheel() -> None:
    from verifiers.v1.utils.loaders import import_taskset

    x = export()
    assert x.OWN_TASKSET_ID == "poisson-tasks-own"
    module = import_taskset(x.OWN_TASKSET_ID)
    assert module.__name__ == "poisson_tasks_own"
    assert sorted(module.__all__) == ["OwnTaskset", "PoissonTasksEnv"]
    wheel = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    packages = wheel["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert "src/poisson_tasks" in packages and "src/poisson_tasks_own" in packages
    done = subprocess.run([sys.executable, "-c", "import sys, poisson_tasks_own; print('verifiers' in sys.modules)"],
                          capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "False"
