"""Pending a yes/no: a contrast that has lost a seed to instrument failures is not computed.

**The question.**  Δ is "paired over the 60 seeds", on scored episodes.  An arm that is not void
(its instrument rate at most 0.02) can still lose both attempts at one seed to instrument
failures, and then its scored episodes no longer cover the sixty: `paired_delta` refuses two
cells with different seed sets.  The spec does not say what then.

**Proposed: the contrast is not computed and the knob is undecided on that model**, with the
reason, so it goes back for a decision.  **A no** pairs over the seeds both arms still hold
(fifty-nine), or counts the lost seed's attempts as failures; either changes what Δ is.
"""

from __future__ import annotations

from tests.k9_support import MODEL, OTHER, every_arm, model_run, outcome_of


def test_a_seed_lost_whole_leaves_the_knob_undecided_on_that_model() -> None:
    from poisson_tasks import knob_probe as probe

    cells = every_arm({"spread:p4": 30}, options={"spread:p4": {"instrument": [(50, 0), (50, 1)]}})
    result = probe.analyse(
        {MODEL: model_run(cells), OTHER: model_run(every_arm({"spread:p4": 30}, model=OTHER))},
        expected=(MODEL, OTHER),
    )
    arm = result["arms"][MODEL]["spread:p4"]
    assert arm["complete"] and not arm["void"] and arm["instrument_rate"] <= 0.02
    row = outcome_of(result, "spread")
    found = row["per_model"][MODEL]
    assert found["status"] == "undecided"
    assert any("cannot be computed" in reason for reason in found["reasons"])
    assert row["outcome"] == "back for a decision"
