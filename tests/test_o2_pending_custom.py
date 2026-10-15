"""Pending a yes/no: `custom` on a user's own tools.

**Why it is open.**  Spec §8.1 has `init` offer, on own tools, the recipes that apply to the set; it
says nothing of choosing the knob and levels yourself there, which the built-in tasks offer as
`[measure] preset = "custom"`.  `tasks.toml` can say `custom` beside `[own]` all the same.

**Recommendation: yes.**  `custom` is read on own tools: `knob` must be one offered on this set
(`own.recipes.offered_knobs`) and every level one the set reaches (`knob_levels`), each refused under
its key otherwise; `strictness` is as for the built-in tasks; the arms come in the knob's order of
levels, whatever order they were written in (as FD1's shape 6 has it for the built-in tasks).  `init`'s dialogue does not ask for it; the flags
`--recipe custom --knob ... --levels ...` and the file say it.  A no refuses `custom` beside
`[own]` under `measure.preset`.

*Ruled yes 2026-10-13, and on 2026-10-13 23:26 every knob stays available on own tools (spec Own
Tools §6.3 as amended): retrofitted 2026-10-14 by O2 Session B2, a recorded commit.  As frozen, a
knob the probe had not shipped was refused under `measure.knob`; `custom` now takes any knob the
set reaches, whatever `arms.SHIPPED_KNOBS` holds, and the knob that is no knob on own tools (the
distractor dial) is still refused under `measure.knob`.*
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import arms
from tests.o1_support import fixture
from tests.o2_support import config

OWN = ('\n[own]\nfile = "tools.json"\n\n[[own.flow]]\nfrom = "get_order"\nfield = "order_id"\n'
       'to = "refund_order"\nparam = "order_id"\n')


def text_with(measure: str) -> str:
    cfg = config()
    base = cfg.dump_config(cfg.config_from_init_args(["--provider", "openai", "--no-price", "--token-cap", "100"]))
    start, end = base.index("[measure]"), base.index("[tasks]")
    return str(base[:start] + "[measure]\n" + measure + "\n" + base[end:] + OWN)


def outcome(measure: str, root: Path) -> Any:
    cfg = config()
    try:
        return cfg.resolve_plan(cfg.loads_config(text_with(measure)), root=root)
    except cfg.ConfigError as error:
        return error.key


@pytest.mark.parametrize("shipped", [(), ("faults",)], ids=["none", "faults"])
def test_custom_takes_a_knob_offered_on_the_set_at_levels_it_reaches(
    shipped: tuple[str, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arms, "SHIPPED_KNOBS", shipped)
    (tmp_path / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    plan = outcome('preset = "custom"\nknob = "depth"\nlevels = [2, 1]\nstrictness = "leaky"', tmp_path)
    assert [(a.knob, a.level, a.strictness, a.generator_version) for a in plan.arms] == [
        ("depth", 1, "leaky", "own-1"), ("depth", 2, "leaky", "own-1")]
    assert outcome('preset = "custom"\nknob = "depth"\nlevels = [3]', tmp_path) == "measure.levels"
    faults = outcome('preset = "custom"\nknob = "faults"\nlevels = [0, 4]', tmp_path)
    # every knob the set reaches, shipped or not (ruled 2026-10-13 23:26)
    assert [(a.knob, a.level) for a in faults.arms] == [("faults", 0), ("faults", 4)]
    assert outcome('preset = "custom"\nknob = "distractor"\nlevels = [0]', tmp_path) == "measure.knob"

