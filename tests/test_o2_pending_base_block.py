"""Pending a decision: every arm but block offers the whole set, in the file's order.

**Why it is open.**  The design says block's levels draw blocks from the set's tools only, the
target always present, and similarity adds copies of the target; it does not say what an arm of
any other knob offers.  The built-in tasks offer a fixed block of sixteen.

**Recommended.**  Every arm but block offers every usable tool of the set, in the file's
order (similarity's seven numbered tools standing where the target stands), since that is the
block the user's own agent offers, and a fixed size would need a draw the user never sees.  A
no fixes a size (sixteen, as the built-in tasks) and draws which tools, as block does at that level.
"""

from __future__ import annotations

from tests.o2_support import every_arm, everything, fixture_sets, generator, names


def test_every_arm_but_block_offers_the_whole_set_in_file_order() -> None:
    for toolset in (everything(), fixture_sets()["petstore"], fixture_sets()["acme-mcp"]):
        order = [t.name for t in toolset.tools]
        for spec in every_arm(toolset):
            if spec.knob == "block":
                continue
            for seed in range(5):
                bundle = generator().generate(toolset, spec, seed)
                shown = names(bundle)
                if spec.knob == "similarity":
                    original = bundle.target.rsplit("_", 1)[0]
                    at = order.index(original)
                    numbered = shown[at:at + 7]
                    assert all(name.rsplit("_", 1)[0] == original for name in numbered)
                    shown = shown[:at] + [original] + shown[at + 7:]
                assert shown == order, (spec, seed)
