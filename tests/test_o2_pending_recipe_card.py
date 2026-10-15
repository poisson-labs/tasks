"""Pending a yes/no: the `card` recipe is not offered on own tools.

**Why it is open.**  `card` is the published cards' design: depth and the distractor dial at every
candidate level with their control arms, sixty tasks and five attempts.  On own tools the distractor
dial is no knob and there are no control arms; depth is.  Knobs spec §17.4 shows on own tools "only
the recipes whose knobs work on that tool set" and does not name `card`.

**Recommendation: yes.**  `card` is never offered on own tools, and `[measure] preset = "card"` beside
`[own]` is refused under `measure.preset`: its point is to be the published design, which a user's
tools cannot be.  A no runs its depth arms alone at sixty tasks and five attempts.
"""

from __future__ import annotations

from pathlib import Path

from tests.o1_support import fixture
from tests.o2_support import acme, acme_flows, config, recipes

SHIPPABLE_ALL = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")


def test_card_is_never_offered_on_own_tools(tmp_path: Path) -> None:
    for shipped in ((), SHIPPABLE_ALL):
        card = recipes().recipes_for(acme(), flows=acme_flows(), shipped=shipped)["card"]
        assert not card.offered and card.arms == ()
    (tmp_path / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    cfg = config()
    base = cfg.dump_config(cfg.config_from_init_args(["--provider", "openai", "--no-price", "--token-cap", "100"]))
    text = base.replace('preset = "first-look"', 'preset = "card"', 1) + (
        '\n[own]\nfile = "tools.json"\n\n[[own.flow]]\nfrom = "get_order"\nfield = "order_id"\n'
        'to = "refund_order"\nparam = "order_id"\n')
    try:
        cfg.resolve_plan(cfg.loads_config(text), root=tmp_path)
    except cfg.ConfigError as error:
        assert error.key == "measure.preset"
    else:
        raise AssertionError("the card preset was taken on own tools")
