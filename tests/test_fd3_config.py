"""The configs a run hands to verifiers, frozen as tests: `run` and `export` agree, the
calibration's runner is unchanged, and a decoding field declared "not sent" is never sent.

The invariants:
- for every arm of the three presets, and for a leaky custom arm and one at another
  generator version, the config `run_plan` resolves equals `verifiers_config(plan, arm)` after both
  go through verifiers' own loader; the exceptions are `run.*`, `output_dir` and `max_concurrent`;
- `run_arm` is unchanged: its existing tests stay green (they are in the suite), and
  `run_arm(spec, …)` equals `run_cell` under the card design;
- a decoding field declared `"not sent"` is absent from every request body the fake
  server receives.

**The config `run_plan` resolves** is the one the wheel's own `save_config` writes into each arm's
folder, `configs/resolved/eval.json` (each arm's folder is the wheel's run folder).
**Verifiers' own loader** is the one `eval` uses for `eval @ FILE`: `pydantic_config.cli` over
`narrow_config(EvalConfig, ["@", FILE])`, which fills every default and applies the taskset's pins.
Both sides go through it, so a field that only one side writes, or writes differently, shows.

The arms: the published design's fourteen, which hold every arm the first-look, card and custom
presets can resolve to under `strict`; plus a leaky custom plan and one at another generator
version, with two attempts, a turn cap of 20 and one decoding field not sent, so that what agrees
is not only the defaults.

Shapes decided here
-------------------

**1. `verifiers_config(plan, arm)`** returns a plain mapping that `eval @` reads, holding the
taskset id `poisson-tasks`, the arm as its six-field mapping, the plan's seeds,
`num_rollouts` = attempts, the model, `client.base_url` and `client.api_key_var` (the variable's
name, never a key), the declared decoding with "not sent" fields left out, `env.agent.max_turns` =
the plan's turn cap, and `push = false`.  The token limit goes out as `max_completion_tokens`, as
`run_config_for` sends it (frozen CAL tests pin why).

**2. `calibration.run_cell(spec, *, seeds, attempts, decoding, output_dir, model, client, budget,
…)`** runs one arm's cell for any design and returns `RunOutcome`; its run folder under
`output_dir` is named as `run_arm`'s is.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import SENTINEL, leaked
from tests.fd3_support import (
    DECODING,
    KEY_VAR,
    arm_dir,
    calibration,
    fixture_model,
    harness_env,
    knobs,
    make_plan,
    needs_uv,
    run_here,
    runs,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["fixture_model", "harness_env"]

# The leaky arms and the arm at another generator version carry the export config's note that no
# published card covers them, as a `UserWarning` from the export config; it is expected here.
pytestmark = [needs_uv, pytest.mark.filterwarnings("ignore::UserWarning:poisson_tasks.export")]

EXEMPT_PREFIXES = ("run.",)
EXEMPT_KEYS = {"output_dir", "max_concurrent"}


def through_verifiers(mapping: Any, where: Path) -> dict[str, Any]:
    """`mapping` read the way `eval @ FILE` reads a config file, as JSON."""
    from pydantic_config import cli  # type: ignore[import-untyped]
    from verifiers.v1.cli.resolve import narrow_config
    from verifiers.v1.configs.cli.eval import EvalConfig

    where.write_text(json.dumps(mapping), encoding="utf-8")
    argv = ["@", str(where)]
    saved = sys.argv
    sys.argv = ["eval", *argv]
    try:
        loaded = cli(narrow_config(EvalConfig, argv))
    finally:
        sys.argv = saved
    value = json.loads(loaded.model_dump_json())
    assert isinstance(value, dict)
    return value


def flat(node: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            out.update(flat(value, f"{prefix}.{key}" if prefix else str(key)))
        return out
    return {prefix: node}


def compared(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in flat(config).items()
            if key not in EXEMPT_KEYS and not key.startswith(EXEMPT_PREFIXES)}


def card_arm_ids() -> tuple[str, ...]:
    return tuple(knobs().arm_id(spec) for spec in calibration().arm_specs())


# ---------------------------------------------------------------------------
# run and export agree
# ---------------------------------------------------------------------------


def test_fd3_11_the_config_a_run_uses_is_the_config_export_writes(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    not_sent = {**DECODING, "reasoning_effort": "not sent"}
    plans = [
        make_plan(fixture_model.base_url, arms=card_arm_ids(), seeds=(404,)),
        make_plan(fixture_model.base_url, arms=("depth:d1", "depth:d3"), seeds=(404,),
                  attempts=2, strictness="leaky", max_model_calls=20, decoding=not_sent),
        make_plan(fixture_model.base_url, arms=("depth:d1",), seeds=(55,), attempts=2,
                  generator_version="tg-m3-v1", max_model_calls=20, decoding=not_sent),
    ]
    assert plans[2].arms[0].generator_version != plans[0].arms[0].generator_version
    assert all(spec.strictness == "leaky" for spec in plans[1].arms)
    checked = 0
    for index, plan in enumerate(plans):
        folder, result = run_here(plan, tmp_path / f"runs-{index}", monkeypatch, concurrency=8)
        assert result.verdict == "done", result
        for spec in plan.arms:
            saved = Path(folder.path) / arm_dir(spec) / "configs" / "resolved" / "eval.json"
            ran = through_verifiers(json.loads(saved.read_text(encoding="utf-8")),
                                    tmp_path / "ran.json")
            exported = through_verifiers(runs().verifiers_config(plan, spec),
                                         tmp_path / "exported.json")
            mine, theirs = compared(ran), compared(exported)
            differ = sorted(key for key in set(mine) | set(theirs)
                            if mine.get(key) != theirs.get(key))
            assert differ == [], (knobs().arm_id(spec), {k: (mine.get(k), theirs.get(k))
                                                         for k in differ})
            checked += 1
    assert checked == 14 + 2 + 1


def test_fd3_11_the_export_config_holds_the_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the mapping says, read back through verifiers: the plan, and the key's variable's
    name but never the key, which is set in this shell."""
    monkeypatch.setenv(KEY_VAR, SENTINEL)
    decoding = {**DECODING, "top_p": "not sent"}
    plan = make_plan("http://127.0.0.1:9/v1", arms=("depth:d3",), seeds=(404, 55, 2121),
                     attempts=3, strictness="leaky", max_model_calls=17, decoding=decoding)
    spec = plan.arms[0]
    mapping = runs().verifiers_config(plan, spec)
    assert leaked(json.dumps(mapping)) == []
    loaded = through_verifiers(mapping, tmp_path / "c.json")
    assert loaded["env"]["taskset"]["id"] == "poisson-tasks"
    assert loaded["env"]["taskset"]["arm"] == dataclasses.asdict(spec)
    assert loaded["env"]["taskset"]["seeds"] == [404, 55, 2121]
    assert loaded["num_rollouts"] == 3
    assert loaded["model"] == "fixture-reference"
    assert loaded["client"]["base_url"] == plan.model.base_url
    assert loaded["client"]["api_key_var"] == KEY_VAR
    assert loaded["push"] is False
    assert loaded["env"]["agent"]["max_turns"] == 17
    assert loaded["env"]["agent"]["harness"]["id"] == "null"
    assert loaded["env"]["agent"]["runtime"]["type"] == "subprocess"
    sampling = loaded["sampling"]
    assert sampling.get("top_p") is None
    assert sampling["temperature"] == 1.0 and sampling["reasoning_effort"] == "low"
    assert (sampling.get("extra_body") or {}).get("max_completion_tokens") == 2048


# ---------------------------------------------------------------------------
# run_arm, through run_cell
# ---------------------------------------------------------------------------


def test_fd3_14_run_arm_is_run_cell_under_the_card_design(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The card design shrunk the way the frozen CAL23_9 shrinks it (two seeds, one attempt).
    Both runners write the same config, apart from where; reach the same outcome; and record the
    same episodes."""
    import verifiers.v1 as vf

    module = calibration()
    monkeypatch.setattr(module, "_SEEDS", (404, 55))
    monkeypatch.setattr(module, "N", 1)
    spec = importlib.import_module("poisson_tasks.arms").arm_from_id("depth:d2")
    client = vf.EvalClientConfig(base_url=fixture_model.base_url, api_key_var=KEY_VAR)
    budget = {"tokens": 10**9, "wall_clock_seconds": 3600}
    by_arm = module.run_arm(spec, output_dir=tmp_path / "a", model="fixture-reference",
                            client=client, budget=budget)
    by_cell = module.run_cell(spec, seeds=module.seed_list(spec), attempts=module.N,
                              decoding=module.DECODING, output_dir=tmp_path / "b",
                              model="fixture-reference", client=client, budget=budget)
    assert by_arm.run_dir.name == by_cell.run_dir.name
    assert by_arm.run_dir.parent == tmp_path / "a" and by_cell.run_dir.parent == tmp_path / "b"
    assert dataclasses.replace(by_arm, run_dir=Path()) == dataclasses.replace(by_cell,
                                                                              run_dir=Path())

    def saved(outcome: Any) -> dict[str, Any]:
        path = outcome.run_dir / "configs" / "resolved" / "eval.json"
        config = flat(json.loads(path.read_text(encoding="utf-8")))
        return {key: value for key, value in config.items()
                if key not in ("output_dir", "run.id")}

    assert saved(by_arm) == saved(by_cell)

    def recorded(outcome: Any) -> list[tuple[Any, ...]]:
        rows = module.records_from_run(outcome.run_dir, model="fixture-reference")
        return sorted((row.task_id, row.seed, row.attempt, row.label, row.turns,
                       row.prompt_tokens, row.cached_input_tokens, row.completion_tokens)
                      for row in rows)

    assert recorded(by_arm) == recorded(by_cell) and len(recorded(by_arm)) == 2


def test_fd3_14_run_cell_runs_the_design_it_is_given(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The generalisation: other seeds, another number of attempts, a field not sent.  What it
    saved and what it ran are that design, not the published one."""
    import verifiers.v1 as vf

    module = calibration()
    spec = importlib.import_module("poisson_tasks.arms").arm_from_id("depth:d1")
    client = vf.EvalClientConfig(base_url=fixture_model.base_url, api_key_var=KEY_VAR)
    decoding = {**DECODING, "top_p": "not sent"}
    outcome = module.run_cell(spec, seeds=(55,), attempts=2, decoding=decoding,
                              output_dir=tmp_path, model="fixture-reference", client=client,
                              budget={"tokens": 10**9, "wall_clock_seconds": 3600})
    assert (outcome.episodes_run, outcome.episodes_owed, outcome.stop) == (2, 0, None)
    config = json.loads((outcome.run_dir / "configs" / "resolved" / "eval.json").read_text(
        encoding="utf-8"))
    assert config["env"]["taskset"]["seeds"] == [55] and config["num_rollouts"] == 2
    assert config["sampling"].get("top_p") is None
    rows = module.records_from_run(outcome.run_dir, model="fixture-reference")
    assert sorted((row.seed, row.attempt) for row in rows) == [(55, 0), (55, 1)]
    assert all("top_p" not in seen.body for seen in fixture_model.posts())


# ---------------------------------------------------------------------------
# "not sent"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["top_p", "reasoning_effort", "max_tokens"])
def test_fd3_17_a_field_declared_not_sent_is_in_no_request(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch, field: str,
) -> None:
    """Each field alone; the fields declared beside it are the control, and are sent as declared
    in every request."""
    decoding = {**DECODING, field: "not sent"}
    plan = make_plan(fixture_model.base_url, seeds=(404, 55), decoding=decoding)
    _, result = run_here(plan, tmp_path, monkeypatch)
    assert result.verdict == "done"
    bodies = [seen.body for seen in fixture_model.posts()]
    assert len(bodies) == 4
    absent = {"max_tokens": ("max_tokens", "max_completion_tokens")}.get(field, (field,))
    for body in bodies:
        assert not set(absent) & set(body), (field, sorted(body))
        assert body["temperature"] == DECODING["temperature"]
        if field != "top_p":
            assert body["top_p"] == DECODING["top_p"]
        if field != "reasoning_effort":
            assert body["reasoning_effort"] == DECODING["reasoning_effort"]
        if field != "max_tokens":
            assert DECODING["max_tokens"] in (body.get("max_completion_tokens"),
                                              body.get("max_tokens"))
