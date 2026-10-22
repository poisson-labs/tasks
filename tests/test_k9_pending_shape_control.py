"""Pending a decision: shape's control clause is read on the point difference against 0.15.

**The question.**  Shape bites when `w1 - w4` meets the two-sided rule "and the control
`w1+len(w4)` differs from `w1` by less than that".  "That" can be read as 0.15 on the point
difference, as "the control contrast does not itself meet the rule" (so a wide interval lets a
large difference through), or as "less than `w1 - w4`".

**Proposed: the first**, |pass@1(w1) - pass@1(w1+len(w4))| < 0.15 on the point estimate, as the
sentence's own size.  **A no** picks one of the other two; the cases below are where they part.
"""

from __future__ import annotations

from typing import Any

from tests.k9_support import MODEL, cell, every_arm, model_run, outcome_of


def shape(cells: dict[str, Any]) -> dict[str, Any]:
    from poisson_tasks import knob_probe as probe

    result = probe.analyse({MODEL: model_run(cells)}, expected=(MODEL,))
    found = outcome_of(result, "shape")["per_model"][MODEL]
    assert isinstance(found, dict)
    return found


def test_a_control_0_2_from_w1_with_a_wide_interval_still_stops_shape() -> None:
    cells = every_arm({"shape:w1": 54, "shape:w4": 24})
    cells["shape:w1"] = cell("shape:w1", range(36))
    cells["shape:w4"] = cell("shape:w4", range(6))
    cells["shape:w1+len(w4)"] = cell("shape:w1+len(w4)", range(36, 60))
    found = shape(cells)
    _, control = found["contrasts"]
    assert abs(control["delta"] - 0.2) < 1e-12 and control["low"] <= 0 <= control["high"]
    assert found["status"] == "does not bite"


def test_a_control_0_3_from_w1_stops_shape_though_w4_is_0_8_away() -> None:
    found = shape(every_arm({"shape:w1": 54, "shape:w4": 6, "shape:w1+len(w4)": 36}))
    primary, control = found["contrasts"]
    assert abs(primary["delta"] - 0.8) < 1e-12 and abs(control["delta"] - 0.3) < 1e-12
    assert found["status"] == "does not bite"
