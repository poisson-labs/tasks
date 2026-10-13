"""K9.6, outcomes, voids and stops, on made-up records of both models.

The spec: a knob ships when it bites on at least one model and on neither is the top easier by the
same rule; shape, whose rule is two-sided, ships when it bites on one, and says which width was
harder.  It does not ship when it bites on neither or the top is easier on either, and a
wrong-direction result is read in the traces first.  An arm whose instrument rate is above 0.02 is
void; a no-call share above 0.10 voids an arm only when its knob's base arm on the same model is
above 0.10 too, and on a top arm alone it is the knob's effect, scored as failures.  A knob whose
arms are void on one model is decided on the other alone; void on both, or a void faults control,
goes back for a decision with the cause.  A void arm may be re-run once, only when the cause is the
instrument, and the re-run is recorded.  After a stop, a knob is decided only on complete arms; a
knob left without its pairs is undecided.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.k9_support import MODEL, OTHER, cell, every_arm, model_run, outcome_of

BOTH = (MODEL, OTHER)


def analyse(nano: dict[str, Any] | None, qwen: dict[str, Any] | None) -> dict[str, Any]:
    from poisson_tasks import knob_probe as probe

    runs = {}
    if nano is not None:
        runs[MODEL] = nano
    if qwen is not None:
        runs[OTHER] = qwen
    return probe.analyse(runs, expected=BOTH)


def statuses(row: dict[str, Any]) -> dict[str, str | None]:
    return {m: (r or {}).get("status") for m, r in row["per_model"].items()}


# ---------------------------------------------------------------------------
# ships, does not ship
# ---------------------------------------------------------------------------


def test_a_knob_that_bites_on_one_model_and_not_on_the_other_ships() -> None:
    result = analyse(
        model_run(every_arm({"similarity:s3": 30})), model_run(every_arm({}, model=OTHER))
    )
    row = outcome_of(result, "similarity")
    assert statuses(row) == {MODEL: "bites", OTHER: "does not bite"}
    assert row["outcome"] == "ships"


def test_a_knob_that_bites_on_neither_does_not_ship() -> None:
    result = analyse(model_run(every_arm({})), model_run(every_arm({}, model=OTHER)))
    row = outcome_of(result, "history")
    assert statuses(row) == {MODEL: "does not bite", OTHER: "does not bite"}
    assert row["outcome"] == "does not ship" and not row["read_traces_first"]


def test_a_top_easier_on_either_model_does_not_ship_and_its_traces_are_read_first() -> None:
    result = analyse(
        model_run(every_arm({"spread:p4": 30})),
        model_run(every_arm({"spread:p1": 30}, model=OTHER)),
    )
    row = outcome_of(result, "spread")
    assert statuses(row) == {MODEL: "bites", OTHER: "top easier"}
    assert row["outcome"] == "does not ship" and row["read_traces_first"]
    assert any(OTHER in reason for reason in row["reasons"])


def test_shape_ships_when_it_bites_on_one_model_in_either_direction() -> None:
    nano = every_arm({"shape:w1": 30, "shape:w1+len(w4)": 30})
    qwen = every_arm({"shape:w4": 30}, model=OTHER)
    row = outcome_of(analyse(model_run(nano), model_run(qwen)), "shape")
    assert statuses(row) == {MODEL: "bites", OTHER: "bites"}
    assert row["outcome"] == "ships"
    assert row["per_model"][MODEL]["harder"] == "shape:w1"
    assert row["per_model"][OTHER]["harder"] == "shape:w4"
    assert any("shape:w1" in r and MODEL in r for r in row["reasons"])
    assert any("shape:w4" in r and OTHER in r for r in row["reasons"])
    alone = outcome_of(analyse(model_run(nano), model_run(every_arm({}, model=OTHER))), "shape")
    assert alone["outcome"] == "ships"


# ---------------------------------------------------------------------------
# voids
# ---------------------------------------------------------------------------


def arms_of(result: dict[str, Any], model: str = MODEL) -> dict[str, Any]:
    return dict(result["arms"][model])


def test_an_instrument_rate_above_0_02_voids_the_arm_and_0_02_or_less_does_not() -> None:
    three = every_arm({}, options={"similarity:s3": {"instrument": [(50, 0), (51, 0), (52, 0)]}})
    two = every_arm({}, options={"similarity:s3": {"instrument": [(50, 0), (51, 0)]}})
    void = arms_of(analyse(model_run(three), None))["similarity:s3"]
    kept = arms_of(analyse(model_run(two), None))["similarity:s3"]
    assert void["instrument_rate"] > 0.02 and void["void"]
    assert kept["instrument_rate"] <= 0.02 and kept["void"] == []


def test_the_tally_counts_failures_a_resume_dropped() -> None:
    tally = {"similarity:s3": {"api_error": 3}}
    found = arms_of(analyse(model_run(every_arm({}), tallies=tally), None))["similarity:s3"]
    assert found["instrument_failures"] == 3 and found["void"]


def test_no_calls_on_a_top_alone_are_the_knobs_effect_and_on_both_void_the_arms() -> None:
    effect = every_arm({"block:k64": 30}, options={"block:k64": {"no_call": range(30, 48)}})
    found = analyse(model_run(effect), None)
    assert arms_of(found)["block:k64"]["no_call_share"] > 0.10
    assert arms_of(found)["block:k64"]["void"] == []
    assert outcome_of(found, "block")["per_model"][MODEL]["status"] == "bites"
    both = every_arm(
        {"block:k8": 30, "block:k64": 30},
        options={"block:k8": {"no_call": range(40, 48)}, "block:k64": {"no_call": range(30, 48)}},
    )
    voided = analyse(model_run(both), None)
    assert arms_of(voided)["block:k8"]["void"] and arms_of(voided)["block:k64"]["void"]
    assert arms_of(voided)["block:k8+len(k64)"]["void"] == []
    assert outcome_of(voided, "block")["per_model"][MODEL]["status"] == "void"


def test_a_knob_void_on_one_model_is_decided_on_the_other_alone() -> None:
    nano = model_run(
        every_arm(
            {"similarity:s3": 30},
            options={"similarity:s3": {"instrument": [(i, 0) for i in range(5)]}},
        )
    )
    bites = analyse(nano, model_run(every_arm({"similarity:s3": 30}, model=OTHER)))
    row = outcome_of(bites, "similarity")
    assert statuses(row) == {MODEL: "void", OTHER: "bites"} and row["outcome"] == "ships"
    flat_other = analyse(nano, model_run(every_arm({}, model=OTHER)))
    assert outcome_of(flat_other, "similarity")["outcome"] == "does not ship"


def test_void_on_both_models_goes_back_for_a_decision_with_the_cause() -> None:
    def broken(model: str) -> dict[str, Any]:
        return model_run(
            every_arm(
                {},
                model=model,
                options={"history:t2400": {"instrument": [(i, 1) for i in range(4)]}},
            )
        )

    row = outcome_of(analyse(broken(MODEL), broken(OTHER)), "history")
    assert statuses(row) == {MODEL: "void", OTHER: "void"}
    assert row["outcome"] == "back for a decision"
    assert all("instrument rate" in reason for reason in row["reasons"])


def test_a_void_faults_control_goes_back_even_when_the_other_model_decides() -> None:
    nano = model_run(
        every_arm(
            {"faults:f4": 30},
            options={"faults:f0+len(f4)": {"instrument": [(i, 0) for i in range(4)]}},
        )
    )
    row = outcome_of(analyse(nano, model_run(every_arm({"faults:f4": 30}, model=OTHER))), "faults")
    assert row["per_model"][OTHER]["status"] == "bites"
    assert row["outcome"] == "back for a decision"
    assert any("faults:f0+len(f4)" in reason for reason in row["reasons"])


def test_another_knobs_void_control_is_decided_on_the_other_model() -> None:
    nano = model_run(
        every_arm(
            {"block:k64": 30},
            options={"block:k8+len(k64)": {"instrument": [(i, 0) for i in range(4)]}},
        )
    )
    row = outcome_of(analyse(nano, model_run(every_arm({"block:k64": 30}, model=OTHER))), "block")
    assert statuses(row) == {MODEL: "void", OTHER: "bites"}
    assert row["outcome"] == "ships"


# ---------------------------------------------------------------------------
# stops
# ---------------------------------------------------------------------------


def stopped(model: str, *arms: str, passes: dict[str, int] | None = None) -> dict[str, Any]:
    """A run a stop cut: `arms` hold none of their episodes, or half of them for the first."""
    from tests.k9_support import seeds60

    cells = every_arm(passes or {}, model=model)
    for arm in arms:
        cells[arm] = []
    if arms:
        cells[arms[0]] = cell(
            arms[0], (passes or {}).get(arms[0], 54), model=model, seeds=seeds60()[:30]
        )
    return model_run(cells)


def test_a_knob_without_its_complete_arms_is_undecided_and_goes_back() -> None:
    nano = stopped(MODEL, "arguments:a8", "arguments:a2+len(a8)")
    row = outcome_of(
        analyse(nano, model_run(every_arm({"arguments:a8": 30}, model=OTHER))), "arguments"
    )
    assert statuses(row) == {MODEL: "undecided", OTHER: "bites"}
    assert row["outcome"] == "back for a decision"
    assert any("arguments:a8" in reason and "not complete" in reason for reason in row["reasons"])
    done = outcome_of(analyse(nano, None), "similarity")
    assert done["per_model"][MODEL]["status"] == "does not bite"


def test_a_stop_before_an_arms_first_episode_is_read_and_reported_not_raised() -> None:
    cells = every_arm({})
    cells["history:t0"] = []
    result = analyse(model_run(cells), None)
    row = outcome_of(result, "history")
    assert row["per_model"][MODEL]["status"] == "undecided"
    check = result["check"][MODEL]
    assert check["delta"] is None and "history:t0 has no scored episode" in check["reason"]
    assert result["arms"][MODEL]["history:t0"]["episodes"] == 0


def test_shape_bitten_on_one_model_ships_though_the_other_stopped() -> None:
    nano = stopped(MODEL, "shape:w1+len(w4)")
    row = outcome_of(analyse(nano, model_run(every_arm({"shape:w4": 30}, model=OTHER))), "shape")
    assert statuses(row) == {MODEL: "undecided", OTHER: "bites"}
    assert row["outcome"] == "ships"


def test_with_one_model_run_a_knob_waits_unless_that_model_already_decides_it() -> None:
    result = analyse(
        model_run(every_arm({"similarity:s3": 30, "spread:p1": 30, "shape:w4": 30})), None
    )
    assert outcome_of(result, "similarity")["outcome"] == "waiting"
    assert outcome_of(result, "similarity")["per_model"][OTHER] is None
    assert outcome_of(result, "spread")["outcome"] == "does not ship"
    assert outcome_of(result, "shape")["outcome"] == "ships"


# ---------------------------------------------------------------------------
# the one re-run
# ---------------------------------------------------------------------------


def arm_result(cells: dict[str, Any], arm: str, reruns: list[dict[str, Any]] | None = None) -> Any:
    from poisson_tasks import knob_probe as probe

    return probe.arm_results(cells, {}, model=MODEL, reruns=reruns or [])[arm]


def test_a_void_arm_is_set_aside_once_for_its_re_run_and_the_re_run_is_recorded(
    tmp_path: Path,
) -> None:
    from poisson_tasks import knob_probe as probe

    cells = every_arm({}, options={"spread:p4": {"instrument": [(i, 0) for i in range(6)]}})
    source = tmp_path / "probe" / "spread-p4"
    source.mkdir(parents=True)
    (source / "traces.jsonl").write_text("{}\n")
    entry = probe.start_rerun(
        "spread:p4",
        arm_result(cells, "spread:p4"),
        cause="the provider answered 500s for ten minutes",
        reruns=[],
        folders=[(source, tmp_path / "void" / "spread-p4-1")],
    )
    assert not source.exists()
    assert (tmp_path / "void" / "spread-p4-1" / "traces.jsonl").read_text() == "{}\n"
    assert entry["arm"] == "spread:p4" and entry["cause"].startswith("the provider")
    assert entry["instrument_rate"] > 0.02
    with pytest.raises(probe.RerunRefused):
        probe.start_rerun(
            "spread:p4", arm_result(cells, "spread:p4"), cause="again", reruns=[entry], folders=[]
        )
    marked = probe.arm_results(cells, {}, model=MODEL, reruns=[entry])["spread:p4"]
    assert marked.rerun == entry
    result = probe.analyse({MODEL: model_run(cells, reruns=[entry])}, expected=BOTH)
    assert result["arms"][MODEL]["spread:p4"]["rerun"]["cause"].startswith("the provider")


@pytest.mark.parametrize("why", ["not void", "no-call void", "no cause", "not complete"])
def test_a_re_run_for_any_other_cause_is_refused(why: str, tmp_path: Path) -> None:
    from poisson_tasks import knob_probe as probe

    cause = "the key was revoked mid-run"
    if why == "not void":
        cells = every_arm({}, options={"spread:p4": {"instrument": [(1, 0)]}})
    elif why == "no-call void":
        cells = every_arm(
            {"spread:p1": 30, "spread:p4": 30},
            options={
                "spread:p1": {"no_call": range(40, 52)},
                "spread:p4": {"no_call": range(30, 52)},
            },
        )
        assert arm_result(cells, "spread:p4").void
    elif why == "no cause":
        cells = every_arm({}, options={"spread:p4": {"instrument": [(i, 0) for i in range(6)]}})
        cause = "  "
    else:
        from tests.k9_support import seeds60

        cells = every_arm({})
        cells["spread:p4"] = cell(
            "spread:p4", 0, seeds=seeds60()[:10], instrument=[(i, 0) for i in range(6)]
        )
    source = tmp_path / "spread-p4"
    source.mkdir()
    with pytest.raises(probe.RerunRefused):
        probe.start_rerun(
            "spread:p4",
            arm_result(cells, "spread:p4"),
            cause=cause,
            reruns=[],
            folders=[(source, tmp_path / "void" / "spread-p4-1")],
        )
    assert source.exists(), "a refused re-run moves nothing"
