"""Pending a yes/no: gpt-5-nano's episodes run through the run engine's arm runner.

**The question.**  The probe runs "through the calibration path (`run_arm`'s body)", and the
driver "takes a dollar cap ... use the run engine's cap and ledger where they fit; do not write a
second cap".  `calibration.run_arm`'s body is `run_config_for` and the runner `_run_arm`, which
checks tokens, the wall clock and the provider's credit before each episode but has no dollar cap
and no ledger.  The run engine (`runs.run_plan`) runs an arm with the same steps (the wheel's
resume, the tally, `env.run_slot`) and weaves its cap and ledger into them: the cap checked before
every model call and before every episode is dispatched, every episode's cost on an append-only
ledger, a call the cap refuses neither recorded nor counted as an instrument failure.

**Proposed: yes.**  The driver runs each phase as a run engine plan, and each arm's config is
`run_config_for`'s, field for field, at the run's concurrency (128 by default, the wheel's own).
**A no** means threading the run engine's meter and ledger into `calibration._run_arm`, a second
copy of the run engine's loop in the calibration module.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from poisson_tasks import calibration as cal
from poisson_tasks import calibration_run as run
from poisson_tasks import runs
from poisson_tasks.knobs import arm_id


def flat(node: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            out.update(flat(value, f"{prefix}.{key}" if prefix else str(key)))
        return out
    return {prefix: node}


def differences(concurrency: int) -> dict[str, dict[str, Any]]:
    import verifiers.v1 as vf

    from poisson_tasks import knob_probe as probe

    rates, read_on = probe.card_rates()
    plan = probe.probe_plan(
        probe.DESIGN,
        probe.PROBE_SEEDS,
        probe.ATTEMPTS,
        model=probe.MODEL,
        base_url=probe.BASE_URL,
        rates=rates,
        read_on=read_on,
        key_var=probe.KEY_VAR,
    )
    folder = pathlib.Path("/nonexistent/probe")
    client = vf.EvalClientConfig(base_url=probe.BASE_URL, api_key_var=probe.KEY_VAR)
    out: dict[str, dict[str, Any]] = {}
    for spec in plan.arms:
        engine = runs._arm_config(plan, spec, folder, concurrency)
        with run.design(run.Design(seeds=probe.PROBE_SEEDS, n=probe.ATTEMPTS, k_values=(1, 2))):
            _, path = cal.run_config_for(
                spec,
                model=probe.MODEL,
                client=client,
                output_dir=folder,
                run_dir=cal._run_dir_name(spec),
            )
        a, b = flat(json.loads(engine.model_dump_json())), flat(json.loads(path.model_dump_json()))
        out[run._arm_dir(arm_id(spec))] = {
            key: (a.get(key), b.get(key))
            for key in sorted(set(a) | set(b))
            if a.get(key) != b.get(key)
        }
    return out


def test_each_arms_config_is_the_calibration_paths_at_the_wheels_own_concurrency() -> None:
    found = differences(128)
    assert len(found) == 18
    assert all(diff == {} for diff in found.values()), found


def test_another_concurrency_moves_that_one_field_only() -> None:
    found = differences(16)
    assert all(diff == {"max_concurrent": (16, 128)} for diff in found.values()), found


def test_the_driver_hands_both_phases_to_the_run_engine() -> None:
    import inspect

    from poisson_tasks import knob_probe as probe

    source = inspect.getsource(probe.run_probe)
    assert source.count("_runs.run_plan(") == 2
    assert "_cal.run_arm(" not in source and "_cal._run_arm(" not in source
