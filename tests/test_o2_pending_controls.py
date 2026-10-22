"""Pending a decision: there are no control arms on a user's own tools.

**Why it is open.**  The built-in knobs have control arms (depth's `d1+h8`, faults' `f0+len(f4)`,
block's, arguments' and shape's) that hold a level's length while the knob stays at its base.  The
design says nothing of controls on own tools, and the recipes, which are what own tools offer, use
none.  A control's length is made of the built-in table's own reads and filler, which have no
meaning on a user's tools.

**Recommended.**  An own-tools arm with a control is refused in one line by the generator, and
`tasks.toml`'s `controls = true` beside `[own]` is refused under `measure.controls` while
`controls = false` is read.  `controls` is read only under `preset = "custom"`, so the second test
also takes `custom` on own tools as recommended (`tests/test_o2_pending_custom.py`).  If it is
declined, the build designs a control per knob from the user's own reads, a design of its own.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from tests.o1_support import fixture
from tests.o2_support import acme, acme_flows, arm, config, generator


def test_an_own_tools_arm_with_a_control_is_refused() -> None:
    for knob, level, control in (("depth", 1, 3), ("faults", 0, 4)):
        spec = dataclasses.replace(arm(knob, level), control=control)
        with pytest.raises(ValueError):
            generator().generate(acme(), spec, 1, flows=acme_flows())


def test_controls_beside_own_are_refused_under_their_key(tmp_path: Path) -> None:
    cfg = config()
    (tmp_path / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    base = cfg.dump_config(cfg.config_from_init_args(["--provider", "openai", "--no-price", "--token-cap", "100"]))
    start, end = base.index("[measure]"), base.index("[tasks]")
    own = ('\n[own]\nfile = "tools.json"\n\n[[own.flow]]\nfrom = "get_order"\nfield = "order_id"\n'
           'to = "refund_order"\nparam = "order_id"\n')

    def text(controls: str) -> str:
        measure = f'[measure]\npreset = "custom"\nknob = "depth"\nlevels = [1, 2]\ncontrols = {controls}\n'
        return str(base[:start] + measure + "\n" + base[end:] + own)

    with pytest.raises(cfg.ConfigError) as refused:
        cfg.resolve_plan(cfg.loads_config(text("true")), root=tmp_path)
    assert refused.value.key == "measure.controls"
    plan = cfg.resolve_plan(cfg.loads_config(text("false")), root=tmp_path)
    assert all(spec.control is None for spec in plan.arms)
