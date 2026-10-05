"""Pending a yes/no: the levels the generator cannot build for block, arguments, shape and spread.

The knobs spec names three levels the generator cannot build, refused when an arm is made: a
similarity level outside 0 to 3, and a negative faults or history level
(`tests/test_k1_knobs.py`).  It names none for the other four new knobs, though each design has
them: an arguments level is how many of a stage tool's eight parameters a call carries, at least
the two the engine needs; a shape width is how four stage calls split into equal rows, so 1, 2 or
4; a spread level is how many of four named reads carry a part, at least one; and a block's
right tools and six reads fill its first eight slots at every level.  These pin those bounds
beside the spec's three, so no later knob has to edit `knobs.py` to add them.  Dropped if the
answer is no.
"""

from __future__ import annotations

import pytest

from poisson_tasks.knobs import ArmSpec


def spec(knob: str, level: int) -> ArmSpec:
    return ArmSpec(knob=knob, level=level, control=None, strictness="strict", split="eval",
                   generator_version="1")


@pytest.mark.parametrize("knob, refused, taken", [
    ("arguments", (1, 9, 0), (2, 3, 8)),
    ("shape", (0, 3, 5, 8), (1, 2, 4)),
    ("spread", (0, 5, -1), (1, 3, 4)),
    ("block", (7, 0, -8), (8, 9, 64, 256)),
])
def test_a_level_these_knobs_cannot_build_is_refused(knob: str, refused: tuple[int, ...],
                                                      taken: tuple[int, ...]) -> None:
    for level in taken:
        assert spec(knob, level).level == level
    for level in refused:
        with pytest.raises(ValueError):
            spec(knob, level)
