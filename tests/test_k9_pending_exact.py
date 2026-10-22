"""Pending a decision: "at least 0.15" and "less than 0.15" are read exactly, not in floating point.

**The question.**  Pass rates over sixty tasks at two attempts are multiples of 1/120, so a drop
of 0.15 is 18/120 exactly, but floating point computes some such drops a hair under 0.15
(0.7 - 0.55 is 0.1499999999999999).  The cards' `call_pair` compares with no allowance.

**Proposed: yes**, an exact reading: a drop of exactly 0.15 meets the rule, and shape's control
"differs by less than 0.15" is false at exactly 0.15.  The comparison allows one part in a billion.
**A no** compares the floating-point numbers as they come, so whether a drop of exactly 0.15 bites
depends on which pass rates produced it.
"""

from __future__ import annotations

from typing import Any

from tests.k9_support import MODEL, every_arm, model_run, outcome_of


def per_model(passes: dict[str, int], knob: str) -> dict[str, Any]:
    from poisson_tasks import knob_probe as probe

    result = probe.analyse({MODEL: model_run(every_arm(passes))}, expected=(MODEL,))
    found = outcome_of(result, knob)["per_model"][MODEL]
    assert isinstance(found, dict)
    return found


def test_a_drop_of_exactly_0_15_bites_though_floating_point_falls_short() -> None:
    found = per_model({"similarity:s0": 42, "similarity:s3": 33}, "similarity")
    (contrast,) = found["contrasts"]
    assert contrast["delta"] < 0.15 and abs(contrast["delta"] - 0.15) < 1e-12
    assert contrast["low"] > 0
    assert found["status"] == "bites"


def test_a_shape_control_exactly_0_15_from_w1_is_not_less_than_0_15() -> None:
    found = per_model({"shape:w1": 42, "shape:w4": 12, "shape:w1+len(w4)": 33}, "shape")
    _, control = found["contrasts"]
    assert control["delta"] < 0.15 and abs(control["delta"] - 0.15) < 1e-12
    assert found["status"] == "does not bite"
