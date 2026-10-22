"""Pending a decision: when an own-tools card says a knob made the tasks harder.

**Why it is open.**  The design: each knob's card "says, in words, whether that knob made your tasks
harder for this model at this sample size", over its table against the first level.  The rule that
turns the table into the words is not given.

**Recommended.**  A knob made the tasks harder when at least one of its levels is called different
from its first under the two-clause rule (`calibration.DISTINGUISHABLE`) with a lower pass rate than
the first; otherwise the card says it did not show that, at this sample size.  A level called
different with a higher rate makes no claim of "harder".  If it is declined, the build takes another
rule (every level lower, say, or the top level against the first alone).
"""

from __future__ import annotations

from poisson_tasks import calibration as cal
from tests.o2_support import card


def row(knob: str, level: int, delta: float | None, verdict: str) -> object:
    return card().AgainstFirst(knob=knob, level=level, first=0, predicate="strict", delta=delta,
                               low=None if delta is None else delta - 0.1,
                               high=None if delta is None else delta + 0.1, verdict=verdict)


def test_a_knob_made_the_tasks_harder_when_a_level_is_called_lower_than_the_first() -> None:
    rows = [row("faults", 1, -0.05, cal.TOO_SMALL), row("faults", 2, -0.4, cal.DISTINGUISHABLE),
            row("history", 300, 0.4, cal.DISTINGUISHABLE), row("history", 600, -0.1, cal.TOO_SMALL),
            row("spread", 2, None, "excluded")]
    said = card().bite(rows)
    assert set(said) == {"faults", "history", "spread"}
    shape = {knob: line.replace(knob, "KNOB") for knob, line in said.items()}
    assert shape["history"] == shape["spread"] != shape["faults"]
    assert all("\n" not in line and knob in line for knob, line in said.items())
