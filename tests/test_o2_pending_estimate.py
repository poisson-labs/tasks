"""Pending a decision: the estimate of a plan on a user's own tools.

**Why it is open.**  The design: "the plan's estimate scales the published card's per-call figures
by this block's token count", and the cap follows the front door's rule.  Which figures, and how the
block's count scales them, is not said; the built-in estimate reads the published records of each
arm, and an own-tools arm has none.

**Recommended.**  Per model call: the published card's mean figures per call over all its
records (prompt, cached input and completion tokens, each summed and divided by the model calls;
the card is the one the built-in estimate reads, the plan's model's, else model A's).  Per task: its reference turns (reference calls and the reply) times those figures,
the prompt and cached input multiplied by the task's block tokens over the built-in block's (the
tools of `depth:d1` at the first published seed, both rendered as JSON and counted in the reference
tokenizer); the output not scaled.  Dollars at the plan's prices; the sum over the plan's tasks and
attempts.  If it is declined, the build picks another scaling (the whole call, or the block alone).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks import cards
from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import generate
from poisson_tasks.tokenizer import count_tokens
from tests.o1_support import fixture
from tests.o2_support import acme, config, generator, runs


def test_the_estimate_scales_the_published_figures_per_call_by_the_block(tmp_path: Path) -> None:
    (tmp_path / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    flags = ["--provider", "openai", "--recipe", "first-look", "--tasks-per-level", "3",
             "--own-file", "tools.json", "--own-name", "acme",
             "--own-flow", "get_order.order_id:refund_order.order_id"]
    plan = config().resolve_plan(config().config_from_init_args(flags), root=tmp_path)
    found = runs().estimate(plan)
    (card,) = [c for c in cards.published() if c.name == "gpt-5-nano"]
    records = cal.read_records(card.folder / cal.RECORDS_FILE)
    calls = sum(r.turns for r in records)
    fields = ("prompt_tokens", "cached_input_tokens", "completion_tokens")
    per_call = {f: sum(getattr(r, f) for r in records) / calls for f in fields}
    built_in = count_tokens(json.dumps(list(generate(arm_from_id("depth:d1"), cal.seed_list()[0]).tools)))
    toolset = acme("mcp", name="acme")
    flows = (generator().Flow("get_order", "order_id", "refund_order", "order_id"),)
    rates = {"input_rate": plan.model.price.input, "cached_input_rate": plan.model.price.cached_input,
             "output_rate": plan.model.price.output}
    dollars = 0.0
    for spec in plan.arms:
        for seed in plan.seeds:
            bundle = generator().generate(toolset, spec, seed, flows=flows)
            turns = len(bundle.reference_calls) + 1
            scale = count_tokens(json.dumps(list(bundle.tools))) / built_in
            figures = {f: per_call[f] * turns * (scale if f in fields[:2] else 1.0) for f in fields}
            dollars += cal.dollars(figures, rates) * plan.attempts
    assert found.dollars_expected == pytest.approx(dollars, rel=1e-9)
    assert found.episodes == len(plan.arms) * len(plan.seeds) * plan.attempts
