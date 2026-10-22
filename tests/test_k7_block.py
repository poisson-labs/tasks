"""What a task-shape block holds: sixteen tools, exactly the stage tools the width needs and reads,
frozen as a test.

It rests on the pin ledger's N33.  Sixteen tools at
every width, holding exactly the stage tools the width needs (`w1`: the target ledger's stages 1 to
4; `w2`: its stages 1 and 2; `w4`: stage 1 of the four ledgers), with reads to sixteen, so no tool
can carry any target past its goal; the block's token count is reported, never refused (N33; the
ledger's report over the contrast is `tests/test_k7_request.py`'s).

Shapes decided here
-------------------

**1. "Exactly the stage tools the width needs"** is every stage tool any target's reference path
calls, and no other stage tool; the other tools are reads the engine defines.  So for every
target, its ledger's stage above its goal is not in the block, and no stage tool of any other
ledger is.  The control holds `w1`'s block.

**2. Every tool is the engine's own**, shown under its own name with its own description and its
own parameters, all required: the display map is the identity for shape, and shape
adds no parameter (that is argument difficulty's knob).

**3. No overshoot control** at any width: no tool in the block carries a target past its goal, so no
call sequence can produce `overshoot`, as at stage 8 today.
"""

from __future__ import annotations

from tests.k3_support import SPEC, made
from tests.k7_support import (
    ARMS,
    SPLITS,
    TOOLS,
    engine_schema,
    names,
    stage_names_in,
    stage_tool,
    targets,
)


def test_sixteen_tools_exactly_the_stage_tools_the_width_needs_and_reads() -> None:
    """Shapes 1 to 3.  Where the stage tools sit is the ledger's N2 (the right tools that two
    widths share sit in the same slot; `tests/test_k7_request.py`'s contrast) and, beyond it,
    pending a decision (`tests/test_k7_pending_block.py`)."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for arm_id in ARMS:
                bundle = made(arm_id, seed, split)
                where = (arm_id, seed, split)
                shown = names(bundle)
                assert len(shown) == TOOLS and len(set(shown)) == TOOLS, where
                needed = {
                    stage_tool(ledger, stage)
                    for (ledger, _record), goal in targets(bundle).items()
                    for stage in range(1, goal + 1)
                }
                assert set(stage_names_in(bundle)) == needed, where
                assert {name for name, _args in bundle.reference_calls} == needed, where
                for name in shown:
                    assert name in SPEC.stage_tools or name in SPEC.read_tools, (name, *where)
                for tool in bundle.tools:
                    assert tool == engine_schema(str(tool["name"])), (tool["name"], *where)
                for (ledger, _record), goal in targets(bundle).items():
                    if goal < len(SPEC.stage_names):
                        assert stage_tool(ledger, goal + 1) not in shown, where
                assert "overshoot" not in bundle.negative_controls, where
