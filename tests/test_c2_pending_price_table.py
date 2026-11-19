"""Pending a decision: which models the price table holds.

**The question.**  Ruled 2026-11-15: `init`'s OpenAI default model and prefilled price move from
gpt-5-nano to gpt-6-luna, "with a price table for the three published models, each with its read
date".  The three published models of 0.5.0 are gpt-6-luna, claude-haiku-5-5 and
Qwen/Qwen3.8-27B.  The open model is paid for in Colab units and has no dollar price, and the
providers that serve it (`ollama`, `vllm`) ask for none.  So a table of dollar prices can hold
two of the three.  `tests/test_c2_init.py` holds those two rows whatever is ruled here.

**Proposed:** the table holds three rows that carry dollars: gpt-6-luna and claude-haiku-5-5,
read on 2026-11-15, and gpt-5-nano-2025-08-07 at the rates its published card declares, read on
2026-09-25, so that a user who names it gets its price prefilled, as today, until OpenAI retires
it on 2026-12-11.  The open model is not in it.
**A no** drops the gpt-5-nano row now (its price is then typed by whoever still names it), or
names a third row.
"""

from __future__ import annotations

from poisson_tasks import config
from tests.c2_support import HAIKU, LUNA, NANO, QWEN, QWEN_REPO


def test_the_table_is_the_two_new_models_and_gpt_5_nano_until_it_retires() -> None:
    assert set(config.PUBLISHED_PRICES) == {LUNA, HAIKU, NANO}
    row = config.PUBLISHED_PRICES[NANO]
    assert (row.input, row.cached_input, row.output, row.read_on) == (
        0.05, 0.005, 0.40, "2026-09-25")


def test_the_open_model_has_no_row() -> None:
    for name in (QWEN, QWEN_REPO, "Qwen/Qwen3.8-27B"):
        assert name not in config.PUBLISHED_PRICES


def test_gpt_5_nano_named_on_the_openai_preset_is_still_prefilled() -> None:
    made = config.config_from_init_args(["--model", NANO])
    price = made.model.price
    assert price is not None
    assert (price.input, price.cached_input, price.output, price.read_on) == (
        0.05, 0.005, 0.40, "2026-09-25")
    assert made.limits.spend_usd is not None and made.limits.tokens is None
