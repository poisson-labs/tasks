"""A card for any plan, frozen as tests: `calibration.Provenance.for_plan`, the `self_served`
serving kind, and what FD4 must leave as it is.

The invariants are FD4.1, FD4.2 and FD4.8 of the front door's plan (spec §9.2 and §9.5), and the
plan's §2 for this module: both published cards rebuild byte for byte, and `calibration.run_arm`
keeps its signature and behaviour.

- **FD4.1 The card design.**  `for_plan` on the `card` preset agrees with `for_run` with the
  taskset's turn cap on every field two cards must share to be read side by side
  (`calibration._COMPARABLE`), and neither that nor the published cards' rebuild depends on the
  package version.
- **FD4.2 Any design.**  For every number of tasks per level from 1 to 60 and every number of
  attempts from 1 to 5, the block's `k_values` are those of 1, 2 and 5 that are at most the
  attempts, and its seed list is the plan's, in the plan's order; the gates a card is refused by
  still fire under it, each beside a control at the threshold.
- **FD4.8 `self_served`.**  A serving entry of that kind is accepted with what the server
  reported, and refused without an endpoint.

Shapes decided here, where the spec leaves them open
----------------------------------------------------

**1. `Provenance.for_plan(plan, *, serving, rate_read_date, budget=None, concurrency=None)`.**
The model entry is the plan's model, its `endpoint_host` the endpoint's host and port, and its
three rates the plan's price when it has one (none otherwise).  `budget` is not among the fields
two cards share and is the caller's; none of these tests pins it.

**2. A `self_served` entry needs `endpoint`, a non-empty string**, and is refused without one,
in one line naming the model whose entry it is; the fields the server reported (`stack`, `stack_version`,
`model_digest` or `served_model`, `reported_by_server`, as `providers.server_facts` gives them)
are kept as given, and any of them may be `None`.

The seed-list hash's own refusal is the frozen
`tests/test_cal_calibration.py::test_cal18_3_the_seed_list_hash_is_over_the_seed_list`.  Two
models in one cell is
refused by `build_artifact` whatever the provenance, and the frozen
`tests/test_cal_calibration.py::test_cal14_1_the_renderer_refuses_a_record_holding_more_than_one_model`
holds it; `check_decoding` is held by the frozen CAL5 tests in the same file.
"""

from __future__ import annotations

import dataclasses
import hashlib
import inspect
import json
from typing import Any

import pytest

from tests.fd2_fakes import FakeServer, network_guard
from tests.fd3_support import calibration, config, make_plan
from tests.fd4_support import differing, one_line, package_generator_hash, shipped_artifacts

RATE_DATE = "2026-10-08"


def hosted(model: Any) -> dict[str, dict[str, Any]]:
    return {model.name: {"kind": "hosted", "endpoint_host": "api.openai.com"}}


def resolved(*flags: str) -> Any:
    cfg = config()
    return cfg.resolve_plan(cfg.config_from_init_args(list(flags)))


def for_plan(plan: Any, **kwargs: Any) -> Any:
    return calibration().Provenance.for_plan(
        plan, serving=kwargs.pop("serving", hosted(plan.model)), rate_read_date=RATE_DATE,
        **kwargs)


# ---------------------------------------------------------------------------
# FD4.1 the card design
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("version", [None, "9.9.9"], ids=["installed", "another-version"])
def test_fd4_1_the_card_preset_is_measured_as_the_published_cards_were(
    version: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`for_plan` on the `card` preset and `for_run` under the taskset's turn cap differ in no
    comparable field; under another package version as well, where both blocks carry that version
    and the published cards still rebuild byte for byte."""
    cal = calibration()
    if version is not None:
        real = cal._metadata.version
        monkeypatch.setattr(cal._metadata, "version",
                            lambda name: version if name == "poisson-tasks" else real(name))
    plan = resolved("--provider", "openai", "--measure", "card")
    serving = hosted(plan.model)
    price = plan.model.price
    entry = {"id": plan.model.name, "revision": plan.model.name,
             "endpoint_host": "api.openai.com", "input_rate": price.input,
             "cached_input_rate": price.cached_input, "output_rate": price.output}
    mine = for_plan(plan, serving=serving)
    theirs = cal.Provenance.for_run(models=[entry], serving=serving, rate_read_date=RATE_DATE,
                                    max_model_calls=plan.max_model_calls)
    assert differing(mine, theirs) == []
    assert mine.max_model_calls == plan.max_model_calls
    if version is not None:
        assert theirs.package_version == version
    from poisson_tasks import cards

    for card in cards.published():
        assert cards.recompute(card).identical, card.name


def test_fd4_1_the_card_preset_differs_from_each_published_block_only_where_that_card_is_stale(
) -> None:
    """Read against the shipped cards' own blocks, not a fresh `for_run`: the `card` preset's block
    differs from each in no comparable field but the generator hash, and in that one exactly when
    the card is stale.  So while both cards are stale, no run made today can be read beside them
    (`card --compare published` refuses every run until the new cards land); once they are
    current, a `card` preset run can."""
    plan = resolved("--provider", "openai", "--measure", "card")
    mine = for_plan(plan)
    for artifact in shipped_artifacts():
        stale = artifact.provenance.generator_hash != package_generator_hash()
        assert differing(mine, artifact.provenance) == (["generator_hash"] if stale else [])


# ---------------------------------------------------------------------------
# FD4.2 any design
# ---------------------------------------------------------------------------


def test_fd4_2_any_number_of_tasks_and_attempts_gives_the_plans_own_design() -> None:
    """Every S from 1 to 60 and n from 1 to 5.  The seeds are taken in an order that is not the
    published list's, so a block that sorted them, or took the published list, is caught."""
    published = list(calibration().seed_list())
    for S in range(1, 61):
        seeds = tuple(reversed(published[:S]))
        for n in range(1, 6):
            plan = make_plan("http://127.0.0.1:9/v1", model="fixture-reference", seeds=seeds,
                             attempts=n)
            prov = for_plan(plan)
            assert (prov.S, prov.n) == (S, n)
            assert list(prov.k_values) == [k for k in (1, 2, 5) if k <= n], (S, n)
            assert list(prov.seed_list) == list(seeds)
            assert prov.seed_list_hash == hashlib.sha256(
                json.dumps(list(seeds)).encode("utf-8")).hexdigest()
            assert prov.generator_hash == package_generator_hash()


def records_for(plan: Any, *, failed: int = 0, silent: int = 0) -> list[Any]:
    """One attempt at each of the plan's tasks on its one arm: `failed` of them instrument
    failures, `silent` of them scored with no tool call, the rest passes."""
    from poisson_tasks.knobs import arm_id

    cal = calibration()
    arm = arm_id(plan.arms[0])
    rows = []
    for index, seed in enumerate(plan.seeds):
        label = "api_error" if index < failed else "passed"
        calls = 0 if failed <= index < failed + silent else 1
        rows.append(cal.EpisodeRecord(
            task_id=f"task-{seed}", arm_id=arm, model=plan.model.name, seed=seed, attempt=0,
            strict=label == "passed", leaky=label == "passed", label=label, turns=calls + 1,
            sampled_calls=calls, prompt_tokens=10, cached_input_tokens=0, completion_tokens=5,
            reasoning_tokens=0))
    return rows


@pytest.mark.parametrize("gate", ["instrument", "no_call"])
def test_fd4_2_the_gates_still_fire_under_a_plans_design(gate: str) -> None:
    """Under the plan's own block, a cell just over the gate is refused and a cell at it is
    published.  Fifty tasks: one instrument failure is 1 in 50, at the 0.02 threshold, and two
    are over it; five no-call episodes are 5 in 50, at the 0.10 threshold, and six are over it."""
    cal = calibration()
    plan = make_plan("http://127.0.0.1:9/v1", model="fixture-reference",
                     seeds=tuple(reversed(cal.seed_list()[:50])))
    prov = for_plan(plan)
    at, over = ({"failed": 1}, {"failed": 2}) if gate == "instrument" else (
        {"silent": 5}, {"silent": 6})
    for counts, refused in ((at, False), (over, True)):
        rows = records_for(plan, **counts)
        cells = {(rows[0].arm_id, plan.model.name): rows}
        if refused:
            with pytest.raises(ValueError):
                cal.build_artifact(cells, prov)
        else:
            cal.build_artifact(cells, prov)


# ---------------------------------------------------------------------------
# FD4.8 self_served
# ---------------------------------------------------------------------------


def server_reports(provider: str, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, dict[str, Any]]:
    """A plan of `provider` and what a fake server of that kind reports about itself."""
    from poisson_tasks import providers

    fake = FakeServer()
    try:
        if provider == "ollama":
            name = "qwen3:8b"
            fake.route("/api/version", 200, {"version": "0.12.6"})
            fake.route("/api/tags", 200, {"models": [{"name": name, "model": name,
                                                      "digest": "a" * 64}]})
        else:
            name = "Qwen/Qwen3-8B"
            fake.route("/version", 200, {"version": "0.29.0"})
            fake.route("/v1/models", 200, {"object": "list", "data": [{"id": name}]})
        plan = make_plan(fake.url + "/v1", model=name, priced=False)
        plan = dataclasses.replace(plan, model=dataclasses.replace(plan.model, provider=provider))
        with network_guard(monkeypatch):
            facts = providers.server_facts(plan.model, timeout=5)
    finally:
        fake.close()
    assert facts["reported_by_server"], facts
    return plan, facts


@pytest.mark.parametrize("provider", ["ollama", "vllm"])
def test_fd4_8_a_self_served_model_is_recorded_with_what_its_server_reported(
    provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan, facts = server_reports(provider, monkeypatch)
    entry = {"kind": "self_served", **facts}
    prov = for_plan(plan, serving={plan.model.name: entry})
    assert dict(prov.serving[plan.model.name]) == entry
    for broken in ({key: value for key, value in entry.items() if key != "endpoint"},
                   {**entry, "endpoint": ""}, {**entry, "endpoint": None}):
        with pytest.raises(ValueError) as refused:
            dataclasses.replace(prov, serving={plan.model.name: broken})
        assert one_line(str(refused.value)) and plan.model.name in str(refused.value)


# ---------------------------------------------------------------------------
# what FD4 leaves as it is (the plan's §2)
# ---------------------------------------------------------------------------


def test_fd4_run_arm_keeps_its_signature() -> None:
    """`run_arm`'s behaviour is held by its frozen tests (CAL23, FD3.14); its signature here."""
    cal = calibration()
    parameters = inspect.signature(cal.run_arm).parameters
    assert [(name, p.kind.name) for name, p in parameters.items()] == [
        ("spec", "POSITIONAL_OR_KEYWORD"), ("output_dir", "KEYWORD_ONLY"),
        ("model", "KEYWORD_ONLY"), ("client", "KEYWORD_ONLY"), ("budget", "KEYWORD_ONLY")]
    assert [parameters[name].default for name in ("model", "client", "budget")] == [
        cal.MODEL_A, None, None]

