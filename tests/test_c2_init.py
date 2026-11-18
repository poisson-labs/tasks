"""C2.5 and C2.6: what `init` writes for a Claude model, and its OpenAI default model and prices.

**C2.5.**  `init --provider anthropic` writes `top_p = "not sent"` and
`reasoning_effort = "not sent"`, and its plan says so in words.  Until now `init` wrote the card
decoding for every provider, `top_p = 1.0` included, and current Claude models answer a request
that carries both `temperature` and `top_p` with a 400.

**C2.6.**  The `openai` preset's default model is `gpt-6-luna` and its prefilled price is 0.10 /
0.01 / 0.50 dollars per million tokens of input, cached input and output, read on 2026-11-15; the
price table holds the published models with their read dates.

Readings made here:
* The two settings are defaults: a flag still sets either, and a settings file that names a value
  is read as before.  Every other provider keeps `top_p = 1.0` and `reasoning_effort = "low"`.
* The price table is `config.PUBLISHED_PRICES`, model name to a `config.PriceConfig`; a model in
  it is prefilled on the preset that serves it (`gpt-6-luna` on `openai`, `claude-haiku-5-5` on
  `anthropic`), and no other model is.  This file holds the two rows that carry dollars; whether
  the table also holds `gpt-5-nano-2025-08-07` until it retires is
  `tests/test_c2_pending_price_table.py`'s.
* "Says so in words": the lines `init` prints name `top_p` and the reasoning effort, each beside
  the words `not sent`.  No sentence is pinned.
"""

from __future__ import annotations

import re
import tomllib

import pytest

from tests.c2_support import HAIKU, LUNA, NOT_SENT, PRICES, card_run
from tests.fd5_support import World, config, invoke, prog, world

__all__ = ["prog", "world"]

QUIET = ["--yes", "--no-fetch", "--no-check-key"]
CLAUDE = ["--provider", "anthropic", "--model", HAIKU]

# ---------------------------------------------------------------------------
# C2.5
# ---------------------------------------------------------------------------


def test_the_anthropic_preset_leaves_top_p_and_the_reasoning_effort_unsent() -> None:
    made = config().config_from_init_args(CLAUDE)
    assert made.decoding.top_p == NOT_SENT
    assert made.decoding.reasoning_effort == NOT_SENT
    assert made.decoding.temperature == 1.0


def test_the_file_it_writes_says_not_sent_for_both_and_reads_back_the_same() -> None:
    made = config().config_from_init_args(CLAUDE)
    text = config().dump_config(made)
    table = tomllib.loads(text)["decoding"]
    assert table["top_p"] == NOT_SENT and table["reasoning_effort"] == NOT_SENT
    assert table["temperature"] == 1.0
    assert config().loads_config(text) == made


def test_a_flag_still_sets_either_on_the_anthropic_preset() -> None:
    made = config().config_from_init_args([*CLAUDE, "--top-p", "0.99", "--reasoning-effort", "low"])
    assert (made.decoding.top_p, made.decoding.reasoning_effort) == (0.99, "low")


@pytest.mark.parametrize(
    "flags",
    [
        [],
        ["--provider", "ollama"],
        ["--provider", "vllm", "--model", "m"],
        ["--provider", "openai-compatible", "--model", "m", "--base-url", "https://x.example/v1",
         "--api-key-env", "X_API_KEY", "--no-price"],
    ],
    ids=["openai", "ollama", "vllm", "another-endpoint"],
)
def test_every_other_preset_keeps_top_p_1_and_effort_low(flags: list[str]) -> None:
    made = config().config_from_init_args(flags)
    assert (made.decoding.temperature, made.decoding.top_p, made.decoding.reasoning_effort) == (
        1.0, 1.0, "low")


def test_the_plan_of_the_settings_it_writes_sends_neither_field() -> None:
    """What the file leaves unsent the run leaves out of every request (`runs.verifiers_config`
    builds each arm's request settings from the plan)."""
    from poisson_tasks import runs

    made = config().config_from_init_args([*CLAUDE, "--price", "0.10,0.01,0.50",
                                           "--price-read-on", "2026-11-15"])
    plan = config().resolve_plan(made)
    sent = runs.verifiers_config(plan, plan.arms[0])["sampling"]
    assert "top_p" not in sent and "reasoning_effort" not in sent
    assert sent["temperature"] == 1.0


def test_init_says_in_words_that_neither_is_sent(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init", *QUIET, *CLAUDE], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    table = tomllib.loads((world.work / "tasks.toml").read_text(encoding="utf-8"))["decoding"]
    assert table["top_p"] == NOT_SENT and table["reasoning_effort"] == NOT_SENT
    said = " ".join((ran.out + ran.err).split())
    assert re.search(r"top_p[^.]{0,80}not sent|not sent[^.]{0,80}top_p", said), said
    assert re.search(
        r"reasoning[ _]effort[^.]{0,80}not sent|not sent[^.]{0,80}reasoning[ _]effort", said
    ), said


def test_init_on_openai_does_not_say_a_field_is_unsent(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init", *QUIET], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert NOT_SENT not in ran.out + ran.err


# ---------------------------------------------------------------------------
# C2.6
# ---------------------------------------------------------------------------


def test_the_openai_presets_default_model_is_gpt_6_luna() -> None:
    assert config().PRESETS["openai"].default_model == LUNA == "gpt-6-luna"
    assert config().config_from_init_args([]).model.name == LUNA


def test_its_prefilled_price_is_the_one_read_on_2026_11_15() -> None:
    price = config().config_from_init_args([]).model.price
    assert price is not None
    assert (price.input, price.cached_input, price.output, price.read_on) == (
        0.10, 0.01, 0.50, "2026-11-15")
    assert PRICES[LUNA] == (0.10, 0.01, 0.50, "2026-11-15")


def test_the_price_table_holds_each_priced_published_model_with_its_read_date() -> None:
    import datetime

    table = config().PUBLISHED_PRICES
    for model, expected in PRICES.items():
        row = table[model]
        assert (row.input, row.cached_input, row.output, row.read_on) == expected, model
    for model, row in table.items():
        assert datetime.date.fromisoformat(row.read_on), model


def test_a_claude_model_in_the_table_is_prefilled_on_the_anthropic_preset() -> None:
    price = config().config_from_init_args(CLAUDE).model.price
    assert price is not None
    assert (price.input, price.cached_input, price.output, price.read_on) == PRICES[HAIKU]


def test_a_model_outside_the_table_is_prefilled_nowhere() -> None:
    assert config().config_from_init_args(["--model", "gpt-4o-mini"]).model.price is None
    with pytest.raises(config().ConfigError):
        # no price and no cap in tokens asked for, on a preset that asks for a price: as today
        config().config_from_init_args(["--provider", "anthropic", "--model", "claude-test",
                                        "--spend-cap", "1"])
    # a model of the table on a preset that does not serve it gets none
    assert config().config_from_init_args(["--provider", "ollama", "--model", LUNA]).model.price is None


def test_a_given_price_still_wins_over_the_table() -> None:
    made = config().config_from_init_args(["--price", "1,0.1,5", "--price-read-on", "2026-12-01"])
    price = made.model.price
    assert (price.input, price.cached_input, price.output, price.read_on) == (
        1.0, 0.1, 5.0, "2026-12-01")
    assert config().config_from_init_args(["--no-price"]).model.price is None


def test_the_run_is_capped_in_the_prices_the_table_holds() -> None:
    models, table = card_run().MODELS, config().PUBLISHED_PRICES
    for model in (LUNA, HAIKU):
        assert models[model].price == table[model], model


def test_init_writes_gpt_6_luna_and_its_price_and_no_retired_model(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init", *QUIET], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    text = (world.work / "tasks.toml").read_text(encoding="utf-8")
    written = tomllib.loads(text)["model"]
    assert written["name"] == LUNA
    assert written["price"] == {
        "input": 0.10, "cached_input": 0.01, "output": 0.50, "read_on": "2026-11-15"}
    assert "gpt-5-nano" not in text
