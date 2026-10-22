"""Pending a decision: the arguments knob's levels on own tools run within 2 to 8.

**Why it is open.**  The design: "levels from the target's required count up to its parameter
count".  The frozen `knobs.ArmSpec` carries an arguments level from 2 to 8 only (its own design's
bounds), so a level of 1, or of 9 and more, has no arm id; changing `knobs.py` after the freeze is a
decision of its own.

**Recommended.**  The levels run from the larger of 2 and the target's required checkable count to
the smaller of 8 and its checkable count; the request states the required ones first and then the
others in a drawn order, each level's set holding the one below it.  If it is declined, the build
gives own tools arm ids of their own, a `knobs.py` change.
"""

from __future__ import annotations

from tests.o2_support import acme, arm, fixture_sets, generator


def test_the_levels_are_the_targets_range_within_two_and_eight() -> None:
    assert generator().knob_levels(acme(), "arguments") == (2, 3)
    toolset = fixture_sets()["petstore"]
    found = generator().knob_levels(toolset, "arguments")
    assert found and found[0] >= 2 and found[-1] <= 8 and list(found) == list(range(found[0], found[-1] + 1))
    for seed in range(6):
        sets = [{n for n, _v in generator().generate(toolset, arm("arguments", level), seed).stated}
                for level in found]
        assert all(len(s) == level for s, level in zip(sets, found, strict=True))
        assert all(a < b for a, b in zip(sets, sets[1:], strict=False))
