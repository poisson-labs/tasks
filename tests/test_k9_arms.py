"""K9.2, the arms, and the settings every episode runs under.

The spec's table: eighteen arms per model, run in this order: the seven bases, then the seven tops,
then the four controls.  Two attempts per task, 120 episodes an arm, 2,160 a model.  Every episode
capped at 32 model calls, through the `null` harness, concurrency recorded.  gpt-5-nano at
`gpt-5-nano-2025-08-07` at api.openai.com with temperature 1.0, top_p 1.0, reasoning effort low
and 2,048 completion tokens; Qwen3-8B served as its card was.

The list is typed in `tests/k9_support.py` from the spec's table, not read from the module.
"""

from __future__ import annotations

import types
from typing import Any

from poisson_tasks import calibration as cal
from poisson_tasks import calibration_run as run
from poisson_tasks.arms import arm_from_id
from poisson_tasks.knobs import arm_id, levels
from tests.k9_support import ARMS, BASES, CONTROLS, TOPS

TABLE = {
    "similarity": ("similarity:s0", "similarity:s3", None),
    "faults": ("faults:f0", "faults:f4", "faults:f0+len(f4)"),
    "history": ("history:t0", "history:t2400", None),
    "block": ("block:k8", "block:k64", "block:k8+len(k64)"),
    "arguments": ("arguments:a2", "arguments:a8", "arguments:a2+len(a8)"),
    "shape": ("shape:w1", "shape:w4", "shape:w1+len(w4)"),
    "spread": ("spread:p1", "spread:p4", None),
}


def test_the_eighteen_arms_run_bases_then_tops_then_controls() -> None:
    from poisson_tasks import knob_probe as probe

    assert probe.ARMS == ARMS
    assert (probe.BASES, probe.TOPS, probe.CONTROLS) == (BASES, TOPS, CONTROLS)
    assert len(set(probe.ARMS)) == 18


def test_each_knob_is_the_spec_tables_row() -> None:
    from poisson_tasks import knob_probe as probe

    assert {k.name: (k.base, k.top, k.control) for k in probe.KNOBS} == TABLE
    assert [k.name for k in probe.KNOBS] == list(TABLE)
    assert "depth" not in {k.name for k in probe.KNOBS}


def test_a_base_is_its_knobs_first_card_level_and_a_top_its_last() -> None:
    for knob, (base, top, _control) in TABLE.items():
        made = [
            arm_id(arm_from_id(f"{knob}:{x}", strictness="strict"))
            for x in (base.split(":")[1], top.split(":")[1])
        ]
        assert made == [base, top]
        first, last = levels(knob)[0], levels(knob)[-1]
        assert arm_from_id(base, strictness="strict").level == first
        assert arm_from_id(top, strictness="strict").level == last


def test_every_arm_is_an_eval_split_arm_the_calibration_path_can_make() -> None:
    for arm in ARMS:
        spec = run.spec_for(arm)
        assert arm_id(spec) == arm
        assert spec.split == "eval" and spec.strictness == "strict"
        assert (spec.control is not None) == (arm in CONTROLS)


def test_the_counts() -> None:
    from poisson_tasks import knob_probe as probe

    assert probe.ATTEMPTS == 2
    assert len(probe.PHASE1_SEEDS) == 3 and probe.DESIGN.phase1_attempts == 1
    assert probe.EPISODES_PER_ARM == 120 == probe.DESIGN.episodes_per_arm
    assert probe.EPISODES_PER_MODEL == 2160
    assert probe.DESIGN.arms == ARMS
    assert probe.DESIGN.probe_seeds == probe.PROBE_SEEDS
    assert probe.DESIGN.phase1_seeds == probe.PHASE1_SEEDS


def test_every_episode_is_capped_at_32_model_calls_through_the_null_harness() -> None:
    from poisson_tasks import knob_probe as probe
    from poisson_tasks.taskset import MAX_MODEL_CALLS

    assert probe.MAX_MODEL_CALLS == 32 == MAX_MODEL_CALLS
    plan = _plan(probe)
    assert plan.max_model_calls == 32
    from poisson_tasks import runs

    mapping = runs.verifiers_config(plan, plan.arms[0])
    assert mapping["env"]["agent"]["max_turns"] == 32
    from verifiers.v1.utils.loaders import load_environment

    _, config = cal.run_config_for(plan.arms[0])
    env = load_environment(config.env)
    assert env.config.agent.harness.id == "null"


def _plan(probe: Any, **kwargs: Any) -> Any:
    rates, read_on = probe.card_rates()
    base = dict(
        model=probe.MODEL,
        base_url=probe.BASE_URL,
        rates=rates,
        read_on=read_on,
        key_var=probe.KEY_VAR,
    )
    base.update(kwargs)
    return probe.probe_plan(probe.DESIGN, probe.PROBE_SEEDS, probe.ATTEMPTS, **base)


def test_gpt_5_nano_runs_with_the_spec_settings() -> None:
    from poisson_tasks import knob_probe as probe

    assert probe.MODEL == "gpt-5-nano-2025-08-07"
    assert probe.BASE_URL == "https://api.openai.com/v1"
    assert dict(probe.DECODING) == {
        "temperature": 1.0,
        "top_p": 1.0,
        "reasoning_effort": "low",
        "max_tokens": 2048,
    }
    plan = _plan(probe)
    assert plan.model.name == "gpt-5-nano-2025-08-07"
    assert plan.model.base_url == "https://api.openai.com/v1"
    assert dict(plan.decoding) == dict(probe.DECODING)
    from poisson_tasks import runs

    sampling = runs.verifiers_config(plan, plan.arms[0])["sampling"]
    assert sampling == {
        "temperature": 1.0,
        "top_p": 1.0,
        "reasoning_effort": "low",
        "extra_body": {"max_completion_tokens": 2048},
    }


def test_the_plan_the_run_engine_is_handed_is_the_designs_arms_seeds_and_attempts_in_order() -> (
    None
):
    from poisson_tasks import knob_probe as probe

    plan = _plan(probe)
    assert tuple(arm_id(spec) for spec in plan.arms) == ARMS
    assert plan.seeds == probe.PROBE_SEEDS and plan.attempts == 2
    first = probe.probe_plan(
        probe.DESIGN,
        probe.PHASE1_SEEDS,
        1,
        model=probe.MODEL,
        base_url=probe.BASE_URL,
        rates=probe.card_rates()[0],
        read_on="2026-09-25",
        key_var=probe.KEY_VAR,
    )
    assert tuple(arm_id(spec) for spec in first.arms) == ARMS
    assert first.seeds == probe.PHASE1_SEEDS and first.attempts == 1
    assert isinstance(plan.decoding, types.MappingProxyType)


def test_qwen_is_the_card_models_pinned_serving() -> None:
    """Served as its card was: the pin `calibration_run.QWEN3_8B` (its own frozen tests pin each
    flag), and its served name is the one the outcome reads."""
    from poisson_tasks import knob_probe as probe

    pin = run.QWEN3_8B
    assert probe.EXPECTED_MODELS == ("gpt-5-nano-2025-08-07", pin.served_name)
    assert pin.model == "Qwen/Qwen3-8B" and pin.revision.startswith("b968826d")
    assert (pin.vllm_version, pin.quantization, pin.max_model_len, pin.tool_call_parser) == (
        "0.29.0",
        "fp8",
        16384,
        "hermes",
    )
    assert pin.template_sha256.startswith("b4d28698")
    assert "--generation-config" in pin.flags() and "VLLM_USE_FLASHINFER_SAMPLER=0" in pin.flags()


def test_the_probe_is_no_command_of_the_tool() -> None:
    """A module run with `python -m`, beside the notebook's driver: no entry point names it, and
    the package's top level, which the taskset loader reads, does not export it."""
    import tomllib

    import poisson_tasks
    from tests.k9_support import REPO

    project = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
    scripts = {**project.get("scripts", {}), **project.get("gui-scripts", {})}
    assert not any("probe" in f"{name} {target}" for name, target in scripts.items())
    assert poisson_tasks.__all__ == ["ExportTaskset", "PoissonTasksEnv"]
    from poisson_tasks import knob_probe as probe

    assert probe.build_parser().prog == "python -m poisson_tasks.knob_probe"
