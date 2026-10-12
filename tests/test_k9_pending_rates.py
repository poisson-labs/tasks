"""Pending a yes/no: the cap is counted at the published card's rates for gpt-5-nano.

**The question.**  The run engine's cap counts dollars from tokens at a price.  The spec's spend
estimate uses gpt-5-nano's published per-call figures with no cache discount; it names no price.

**Proposed:** the rates the published card declares and was billed at, read from its artifact
(input $0.05, cached input $0.005, output $0.40 per million tokens, read 2026-09-25), with the
cache counted at its own rate as the cards count it.  The driver prints them before the run; if
OpenAI's page says otherwise on the day, the run is not started until that is settled.
**A no** names other rates, or a `--rates` setting read on the day.
"""

from __future__ import annotations


def test_the_cap_is_counted_at_the_published_cards_rates() -> None:
    from poisson_tasks import knob_probe as probe

    rates, read_on = probe.card_rates()
    assert rates == {"input_rate": 0.05, "cached_input_rate": 0.005, "output_rate": 0.40}
    assert read_on == "2026-09-25"
    plan = probe.probe_plan(
        probe.DESIGN,
        probe.PROBE_SEEDS,
        2,
        model=probe.MODEL,
        base_url=probe.BASE_URL,
        rates=rates,
        read_on=read_on,
        key_var=probe.KEY_VAR,
    )
    price = plan.model.price
    assert (price.input, price.cached_input, price.output) == (0.05, 0.005, 0.40)
