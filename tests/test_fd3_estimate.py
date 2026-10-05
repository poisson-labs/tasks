"""What a plan will cost, before anything is spent, frozen as tests: `runs.estimate`.

The invariant is FD3.1 of the front door's plan (spec §8.2):
- episodes = arms × seeds × attempts;
- `calls_min` = Σ over the plan's tasks of each one's reference turns (its reference solution's
  tool calls plus a reply) × attempts;
- `calls_at_cap` = episodes × `max_model_calls`;
- `calls_expected`, `tokens_expected` and `dollars_expected` = the reference card's per-arm means
  times the plan's counts, the dollars at the plan's prices through `calibration.dollars`;
- `source` names the card used; with no price, `dollars_expected` is `None`.

**Every mean here is computed from the shipped records** (`calibration/<card>/episodes.jsonl`,
read with `calibration.read_records`), never from a literal, and every minimum from the tasks the
generator makes.  So a published card that is re-run, or a generator change that moves a
reference solution, moves the test with it.

Shapes decided here
-------------------

**1. `Estimate`'s fields** are `episodes`, `calls_min`, `calls_expected`, `calls_at_cap`,
`tokens_expected`, `dollars_expected`, `source` and `same_model`.  `tokens_expected` is the plan's
figure when there is no price (spec §8.2: "Without a price there is no dollar figure, only
tokens"); tokens are prompt, cached input and completion tokens, as the card counts them.

**2. `source` is the published card's short name**, `gpt-5-nano` or `qwen3-8b` (the names ruled
on 2026-10-03, spec §4.4), and `same_model` says whether that card measured the plan's model.  The
words the plan line prints ("from the published card for this model", "your model's usage will
differ") are the CLI's, from these two fields.

**3. The card for a plan's model** is the one whose records name that model, read without its
`@revision` suffix: `gpt-5-nano-2025-08-07` is model A's card and `Qwen/Qwen3-8B` model B's.  Any
other model is estimated from model A's card (spec §8.2), with `same_model` false.

**4. A per-arm mean is over every record of that arm**, whatever its outcome: an episode that
failed still made the calls it made and cost what it cost.  An arm is matched by its id
(`knobs.arm_id`), so a leaky arm, or one at another generator version, is estimated from the
card's strict arm of the same id: the tasks differ in their ids and scoring, not their length.

**5. `reference=` names a published card** to estimate from instead; a name that is not one is a
`ValueError` of one line naming it.

Not pinned: the estimate for an arm no published card measured (a plan can only be built with
one by hand; `tasks.toml` cannot name it), and how long `estimate` takes.
"""

from __future__ import annotations

import importlib
import math
import statistics
from typing import Any

import pytest

from tests.fd3_support import REPO, arms_module, calibration, config, knobs, make_plan, runs

CARD_FOLDERS = {"gpt-5-nano": "gpt-5-nano-2025-08-07", "qwen3-8b": "qwen3-8b-b968826d"}


def card_records(name: str) -> list[Any]:
    path = REPO / "calibration" / CARD_FOLDERS[name] / "episodes.jsonl"
    return list(calibration().read_records(path))


def figures(row: Any) -> dict[str, int]:
    return {
        "prompt_tokens": int(row.prompt_tokens),
        "cached_input_tokens": int(row.cached_input_tokens),
        "completion_tokens": int(row.completion_tokens),
    }


def rates_of(plan: Any) -> dict[str, float] | None:
    price = plan.model.price
    if price is None:
        return None
    return {"input_rate": price.input, "cached_input_rate": price.cached_input,
            "output_rate": price.output}


def expected(plan: Any, card: str) -> dict[str, Any]:
    """The estimate, worked out here from the card's records and the generator's tasks."""
    tasks = importlib.import_module("poisson_tasks.tasks")
    rows = card_records(card)
    rates = rates_of(plan)
    per_task = len(plan.seeds) * plan.attempts
    calls_min = sum(
        (len(tasks.generate(spec, seed).reference_calls) + 1) * plan.attempts
        for spec in plan.arms for seed in plan.seeds
    )
    calls = tokens = dollars = 0.0
    for spec in plan.arms:
        mine = [row for row in rows if row.arm_id == knobs().arm_id(spec)]
        assert mine, f"the {card} card has no records of {knobs().arm_id(spec)}"
        calls += statistics.fmean(row.turns for row in mine) * per_task
        tokens += statistics.fmean(sum(figures(row).values()) for row in mine) * per_task
        if rates is not None:
            dollars += statistics.fmean(
                calibration().dollars(figures(row), rates) for row in mine) * per_task
    episodes = len(plan.arms) * per_task
    return {
        "episodes": episodes, "calls_min": calls_min, "calls_expected": calls,
        "calls_at_cap": episodes * plan.max_model_calls, "tokens_expected": tokens,
        "dollars_expected": dollars if rates is not None else None,
    }


def assert_matches(estimate: Any, plan: Any, card: str) -> None:
    want = expected(plan, card)
    assert estimate.episodes == want["episodes"]
    assert estimate.calls_min == want["calls_min"]
    assert estimate.calls_at_cap == want["calls_at_cap"]
    assert math.isclose(estimate.calls_expected, want["calls_expected"], rel_tol=1e-9)
    assert math.isclose(estimate.tokens_expected, want["tokens_expected"], rel_tol=1e-9)
    if want["dollars_expected"] is None:
        assert estimate.dollars_expected is None
    else:
        assert estimate.dollars_expected is not None
        assert math.isclose(estimate.dollars_expected, want["dollars_expected"], rel_tol=1e-9)
    assert estimate.source == card


def resolved(*flags: str) -> Any:
    """A plan as `init` and `resolve_plan` make one, from `init`'s flags."""
    cfg = config()
    return cfg.resolve_plan(cfg.config_from_init_args(list(flags)))


FIRST_LOOK = ("--provider", "openai", "--measure", "first-look", "--tasks-per-level", "10",
              "--attempts", "1")


def test_fd3_1_a_first_look_on_model_a_is_estimated_from_model_as_card() -> None:
    """The spec's own example (§8.2): the first look against gpt-5-nano at the published price,
    10 tasks per level and one attempt, is estimated from model A's card, for this model.  Its
    structural figures are the spec's: at least 150 model calls, at most 960."""
    plan = resolved(*FIRST_LOOK)
    estimate = runs().estimate(plan)
    assert_matches(estimate, plan, "gpt-5-nano")
    assert estimate.same_model is True
    assert (estimate.calls_min, estimate.calls_at_cap) == (150, 960)


def test_fd3_1_the_card_design_is_estimated_over_its_fourteen_arms() -> None:
    """The published design: fourteen arms, the sixty seeds, five attempts, every arm on the
    card, the controls' minimum read off their own tasks."""
    plan = resolved("--provider", "openai", "--measure", "card")
    assert len(plan.arms) == 14 and len(plan.seeds) == 60 and plan.attempts == 5
    assert_matches(runs().estimate(plan), plan, "gpt-5-nano")


@pytest.mark.parametrize("attempts, per_level, turn_cap", [(3, 4, 32), (1, 7, 9)])
def test_fd3_1_a_custom_plan_scales_with_its_own_counts_and_turn_cap(
    attempts: int, per_level: int, turn_cap: int
) -> None:
    """The distractor knob at three levels with its controls, at other counts and another turn
    cap: every figure scales with the plan, none with the card's design."""
    plan = resolved(
        "--provider", "openai", "--measure", "custom", "--knob", "distractor",
        "--levels", "0,2,8", "--controls", "--tasks-per-level", str(per_level),
        "--attempts", str(attempts), "--max-model-calls", str(turn_cap),
    )
    assert any(spec.control is not None for spec in plan.arms)
    assert_matches(runs().estimate(plan), plan, "gpt-5-nano")


def test_fd3_1_without_a_price_there_are_tokens_and_no_dollars() -> None:
    plan = resolved(*FIRST_LOOK, "--no-price", "--token-cap", "2000000")
    assert plan.model.price is None
    estimate = runs().estimate(plan)
    assert estimate.dollars_expected is None
    assert_matches(estimate, plan, "gpt-5-nano")
    assert estimate.tokens_expected > 0


def test_fd3_1_model_bs_plan_is_estimated_from_model_bs_card() -> None:
    """vLLM serving `Qwen/Qwen3-8B`, the model of the second published card, with no price."""
    plan = resolved(
        "--provider", "vllm", "--base-url", "http://127.0.0.1:8000/v1", "--model",
        "Qwen/Qwen3-8B", "--measure", "first-look", "--tasks-per-level", "5",
    )
    estimate = runs().estimate(plan)
    assert_matches(estimate, plan, "qwen3-8b")
    assert estimate.same_model is True and estimate.dollars_expected is None


@pytest.mark.parametrize("model", ["qwen3:8b", "llama3.1:8b", "fixture-reference"])
def test_fd3_1_a_model_with_no_card_is_estimated_from_model_as_card_and_says_so(
    model: str,
) -> None:
    """Ollama's `qwen3:8b` is not the weights model B's card measured as served; it, a model no
    card measured and the fixture are all estimated from model A's card, which is not theirs."""
    plan = make_plan("http://127.0.0.1:9/v1", model=model, arms=("depth:d1", "depth:d3"),
                     seeds=(404, 55, 2121), attempts=2)
    estimate = runs().estimate(plan)
    assert_matches(estimate, plan, "gpt-5-nano")
    assert estimate.same_model is False


def test_fd3_1_reference_names_the_card_to_estimate_from() -> None:
    plan = resolved(*FIRST_LOOK)
    other = runs().estimate(plan, reference="qwen3-8b")
    assert_matches(other, plan, "qwen3-8b")
    assert other.same_model is False
    own = runs().estimate(plan, reference="gpt-5-nano")
    assert_matches(own, plan, "gpt-5-nano")
    assert own.same_model is True


def test_fd3_1_a_reference_that_is_not_a_published_card_is_refused() -> None:
    plan = resolved(*FIRST_LOOK)
    runs().estimate(plan, reference="qwen3-8b")
    with pytest.raises(ValueError) as refused:
        runs().estimate(plan, reference="qwen3-8b-b968826d")
    message = str(refused.value)
    assert "\n" not in message and "qwen3-8b-b968826d" in message, message


@pytest.mark.parametrize("change", ["leaky", "another-generator-version"])
def test_fd3_1_an_arm_is_estimated_by_its_id(change: str) -> None:
    """A leaky arm, or one at another generator version, carries the same arm id as the card's
    strict arm, and is estimated from that arm's records."""
    leaky = change == "leaky"
    plan = make_plan(
        "http://127.0.0.1:9/v1", model="gpt-5-nano-2025-08-07", arms=("depth:d1", "depth:d8"),
        seeds=(404, 55), attempts=3, strictness="leaky" if leaky else "strict",
        generator_version=None if leaky else "tg-m3-v1",
    )
    if not leaky:
        assert plan.arms[0].generator_version != arms_module().DEFAULT_GENERATOR_VERSION
    estimate = runs().estimate(plan)
    assert_matches(estimate, plan, "gpt-5-nano")
    assert estimate.same_model is True
