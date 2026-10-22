"""Pending a decision: "the top is easier by the same rule" is read on base minus top alone.

**The question.**  A knob does not ship when "the top is easier on either" model.  For faults,
block size and argument difficulty, which bite only on two contrasts, "easier by the same rule"
can mean the base-minus-top contrast meets the rule the other way, or both contrasts do.

**Proposed: base minus top alone**: when the top level is easier than the base by the rule, the
knob does not ship, whatever its control shows.  **A no** asks both contrasts to turn, so such a
knob would read "does not bite" on that model and could still ship on the other.
"""

from __future__ import annotations

from tests.k9_support import MODEL, OTHER, every_arm, model_run, outcome_of


def test_a_top_easier_than_its_base_does_not_ship_whatever_its_control_shows() -> None:
    from poisson_tasks import knob_probe as probe

    nano = every_arm({"faults:f0": 30, "faults:f4": 54, "faults:f0+len(f4)": 54})
    qwen = every_arm({"faults:f4": 30}, model=OTHER)
    result = probe.analyse(
        {MODEL: model_run(nano), OTHER: model_run(qwen)}, expected=(MODEL, OTHER)
    )
    row = outcome_of(result, "faults")
    primary, control = row["per_model"][MODEL]["contrasts"]
    assert primary["reversed"] and not control["reversed"]
    assert row["per_model"][MODEL]["status"] == "top easier"
    assert row["per_model"][OTHER]["status"] == "bites"
    assert row["outcome"] == "does not ship" and row["read_traces_first"]
