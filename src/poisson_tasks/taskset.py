"""The taskset the id ``poisson-tasks`` names, and the ``Env`` that makes ``eval`` run the
measured harness with no flag.

The model path's first layer: a hosted model over an API, no GPU (the MP1 to MP9 cases in
`tests/test_tg_m5_standalone.py`).  A stranger installs the package, names an
OpenAI-compatible endpoint and runs ``uv run eval poisson-tasks ...``: the wheel resolves
the id to the package root, whose ``__all__`` points here, and finds one ``Taskset`` and one
``Env``.

The taskset is ``poisson_tasks.export.ExportTaskset``, re-exported and unchanged: one task
per declared seed, scored by the export's own ``strict`` reward (X4).  The ``Env`` is the wheel's
single-agent env with a config that pins what the section below lists, because at 0.3.1 a
taskset's default harness is ``bash`` unless its own ``Env`` says otherwise, and
``AgentConfig.runtime`` defaults to a hosted sandbox (both read at source in the wheel).

Pins
----
Every field this module's env config sets away from the wheel's own single-agent default is
listed here, one line each, with the reason (MP4).  Nothing else is pinned: a stranger's run
differs from a plain ``eval`` of this taskset in exactly these, each shows in the run's saved
config, and a flag on the command line overrides any of them (MP5).

- `agent.harness.id` = `null` -- the measured harness; the default is otherwise `bash` (X9).
  Every number the pin ledger carries was produced under the
  `null` harness: it adds no system prompt and no tools of its own, and a run under `bash`
  measures something the ledger cannot be compared with.
- `agent.runtime.type` = `subprocess` -- the harness program runs on the caller's machine
  (MP8).  ``AgentConfig.runtime`` defaults to Prime's hosted sandbox, which a stranger
  has no account for, and which would make the run's outbound connections something other
  than the endpoint they named.
- `agent.max_turns` = `32` -- an episode ends after 32 model calls, four times the deepest
  task's minimum (eight, at `depth:d8`).  The wheel sets no turn limit by default, so a model
  that never stops calls tools until its context fills, and the run reports that as a setup
  failure while it burns tokens.  At the cap it stops as `max_turns`, which the verdict labels
  `turn_limit`, the model's own failure.  Ordinary episodes of both calibrated models end
  within 18 calls, so the cap binds only an episode that does not stop.

Nothing here imports Proofload: the standalone path needs no extra (MP6).
"""

from __future__ import annotations

from typing import Any as _Any

import verifiers.v1 as _vf

from poisson_tasks.export import MEASURED_HARNESS as _MEASURED_HARNESS
from poisson_tasks.export import ExportTaskset

__all__ = ["ExportTaskset", "PoissonTasksEnvConfig", "PoissonTasksEnv", "MAX_MODEL_CALLS"]

MAX_MODEL_CALLS = 32
"""The pinned turn limit: four times the deepest task's minimum (the module docstring)."""


class PoissonTasksEnvConfig(_vf.SingleAgentEnvConfig):
    """The single-agent config with the pins the module docstring lists.

    A pinned ``harness`` narrows to the harness's own config type when the config is built,
    and a role's partial CLI data deep-merges onto this declared instance, which is what
    makes each pin a default and not a lock.
    """

    agent: _vf.AgentConfig = _vf.AgentConfig(
        harness={"id": _MEASURED_HARNESS}, runtime={"type": "subprocess"},
        max_turns=MAX_MODEL_CALLS,
    )


class PoissonTasksEnv(_vf.Env[PoissonTasksEnvConfig]):
    """The single-agent env, one seat, bound to the pinned config.

    ``vf.Env[PoissonTasksEnvConfig]`` is how the wheel learns the config type (it reads the
    generic parameter through the MRO), and it is what narrows ``--env.agent.*`` to this
    config on the command line.  ``run`` is the wheel's single-agent body.
    """

    async def run(self, task: _Any, agents: _Any) -> None:
        await agents.agent.run(task)
