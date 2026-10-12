"""Pending a yes/no: the notebook's own gates are read on phase 1's episodes, by the probe step.

**The question.**  For Qwen, "its probe-only design applies the plumbing and instrument checks and
the context checks ... to every arm, and its leaky floor and no-call stop to the seven base arms
only."  The spec does not say which episodes those gates read, or when.  Model B's card ran a
probe of its own (48 episodes at the hardest and longest arms) before the card.

**Proposed: they read phase 1's 54 episodes, in the notebook's probe step, which runs none**, so
they stop the run before its 2,160 episodes as phase 1's gate does, and run no episode outside the
pre-registration.  The headroom check is then read on three episodes of `history:t2400` and of
`block:k64`, the arms with the longest prompts.  **A no** runs a probe of its own (more episodes,
which the pre-registration does not list), or reads the gates on the full run's records as it goes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from tests.k9_support import ARMS, episode

PHASE1 = (1180681854, 601375552, 2652385879)


def test_the_probe_step_reads_phase_1s_episodes_and_runs_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from poisson_tasks import calibration_run as run

    ctx = run.Context(
        local=tmp_path / "local",
        durable=tmp_path / "durable",
        port=1,
        mirror_interval=3600.0,
        design="knob-probe",
    )
    ctx.local.mkdir(parents=True)
    (ctx.local / "phase1.json").write_text(json.dumps({"passed": True}))
    asked: list[Path] = []
    records = {
        arm: [
            episode(arm, seed, 0, passed=True, calls=cal._minimum_calls(arm) or 2)
            for seed in PHASE1
        ]
        for arm in ARMS
    }
    facts = {arm: {"episodes": 3, "max_prompt_tokens": 9000, "context_stops": 0} for arm in ARMS}

    def rows(root: Path, arms: Any, served: str) -> Any:
        asked.append(root)
        return records, {}, facts

    def ran(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the probe step ran an episode")

    monkeypatch.setattr(run, "_knob_rows", rows)
    monkeypatch.setattr(run, "_run_arms", ran)
    assert run.knob_gate(ctx) == 0
    assert asked == [ctx.local / "phase1"]
    report = json.loads((ctx.local / "probe.json").read_text())
    assert report["proceed"] and report["max_prompt_tokens"] == 9000
