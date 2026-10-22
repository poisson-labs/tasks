"""The knob probe's analysis: the decision rule, and each knob's rule, on made-up records.

The probe's design: for each knob and model, Δ = strict pass@1 at the base minus at the top, paired
over the 60 seeds, with the cards' task-clustered bootstrap (`cluster_bootstrap`: 2,000 resamples,
seed 20260922, its quantile rule) and its 95% interval.  `paired_delta` is called without a
provenance block, so the cards' saturation refusal does not apply, and the analysis applies the two
clauses itself: the knob bites when the interval excludes zero, Δ ≥ 0.15 and Δ is positive.  The
saturation exclusion is dropped on purpose.  Per knob: similarity, history and spread on one
contrast; faults, block size and argument difficulty on two (base minus top, and control minus top);
shape two-sided, and only when its control differs from `w1` by less than 0.15.

The records: an arm "passing on its first k seeds" passes both attempts at the first k of the
probe's sixty and fails both elsewhere (`tests/k9_support.cell`), so two such arms differ only on
the seeds between, and their paired interval is tight.
"""

from __future__ import annotations

from typing import Any

from poisson_tasks import calibration as cal
from tests.k9_support import MODEL, cell, every_arm, model_run, outcome_of, seeds60


def status(cells: dict[str, Any], knob: str) -> dict[str, Any]:
    from poisson_tasks import knob_probe as probe

    result = probe.analyse({MODEL: model_run(cells)}, expected=(MODEL,))
    found = outcome_of(result, knob)["per_model"][MODEL]
    assert found is not None
    return dict(found)


def noisy(arm: str, first: bool) -> list[cal.EpisodeRecord]:
    """Passing on the first 36 seeds, or on the last 24: Δ = 0.2 between the two, with every
    seed differing, so the interval is wide."""
    return cell(arm, range(36) if first else range(36, 60))


# ---------------------------------------------------------------------------
# the rule's three clauses
# ---------------------------------------------------------------------------


def test_a_clear_drop_bites() -> None:
    found = status(every_arm({"similarity:s3": 30}), "similarity")
    assert found["status"] == "bites"
    (contrast,) = found["contrasts"]
    assert (contrast["a"], contrast["b"]) == ("similarity:s0", "similarity:s3")
    assert abs(contrast["delta"] - 0.4) < 1e-12 and contrast["low"] > 0


def test_an_interval_that_holds_zero_does_not_bite_whatever_the_size() -> None:
    cells = every_arm({})
    cells["similarity:s0"], cells["similarity:s3"] = (
        noisy("similarity:s0", True),
        noisy("similarity:s3", False),
    )
    found = status(cells, "similarity")
    (contrast,) = found["contrasts"]
    assert abs(contrast["delta"] - 0.2) < 1e-12
    assert contrast["low"] <= 0 <= contrast["high"]
    assert found["status"] == "does not bite"


def test_a_drop_below_0_15_does_not_bite_however_sure() -> None:
    found = status(every_arm({"similarity:s3": 48}), "similarity")
    (contrast,) = found["contrasts"]
    assert abs(contrast["delta"] - 0.1) < 1e-12 and contrast["low"] > 0
    assert found["status"] == "does not bite"


def test_a_rise_at_the_top_does_not_bite_it_is_the_top_easier() -> None:
    found = status(every_arm({"similarity:s0": 30, "similarity:s3": 54}), "similarity")
    (contrast,) = found["contrasts"]
    assert contrast["delta"] < 0 and contrast["high"] < 0
    assert found["status"] == "top easier"


def test_a_base_at_1_000_can_still_bite_the_saturation_exclusion_is_dropped() -> None:
    cells = every_arm({"history:t0": 60, "history:t2400": 42})
    assert cal.pass_at_1(cells["history:t0"]) == 1.0
    found = status(cells, "history")
    assert found["status"] == "bites"
    (contrast,) = found["contrasts"]
    assert abs(contrast["delta"] - 0.3) < 1e-12


def test_the_interval_is_the_cards_bootstrap_with_no_provenance_block() -> None:
    from poisson_tasks import knob_probe as probe

    cells = every_arm({})
    cells["spread:p1"] = cell("spread:p1", range(30), half=range(30, 45))
    cells["spread:p4"] = cell("spread:p4", range(10, 32), half=range(40, 55))
    found = probe.contrast("spread:p1", "spread:p4", cells)
    cards = cal.paired_delta(cells["spread:p1"], cells["spread:p4"], resamples=2000, seed=20260922)
    assert (found.delta, found.low, found.high) == (cards.point, cards.low, cards.high)
    for resamples, seed in ((2000, 20260923), (1000, 20260922)):
        other = cal.paired_delta(
            cells["spread:p1"], cells["spread:p4"], resamples=resamples, seed=seed
        )
        assert (other.low, other.high) != (cards.low, cards.high), (resamples, seed)


def test_an_episode_with_an_instrument_label_leaves_the_denominator() -> None:
    """Strict pass@1 is over scored episodes, as on the cards: a seed whose one attempt carries an
    instrument label counts its other attempt alone."""
    cells = every_arm({})
    cells["spread:p4"] = cell("spread:p4", 30, instrument=[(40, 0)])
    found = status(cells, "spread")
    (contrast,) = found["contrasts"]
    assert abs(contrast["delta"] - 24 / 60) < 1e-12


# ---------------------------------------------------------------------------
# each knob's rule
# ---------------------------------------------------------------------------


def test_a_knob_with_a_control_bites_only_when_the_top_is_harder_than_its_control_too() -> None:
    for knob, base, top, control in (
        ("faults", "faults:f0", "faults:f4", "faults:f0+len(f4)"),
        ("block", "block:k8", "block:k64", "block:k8+len(k64)"),
        ("arguments", "arguments:a2", "arguments:a8", "arguments:a2+len(a8)"),
    ):
        both = status(every_arm({base: 54, top: 30, control: 54}), knob)
        assert both["status"] == "bites", knob
        assert [(c["a"], c["b"]) for c in both["contrasts"]] == [(base, top), (control, top)]
        length = status(every_arm({base: 54, top: 30, control: 33}), knob)
        assert length["status"] == "does not bite", knob
        assert [c["meets"] for c in length["contrasts"]] == [True, False], knob


def test_a_knob_without_a_control_reads_one_contrast() -> None:
    for knob, base, top in (
        ("similarity", "similarity:s0", "similarity:s3"),
        ("history", "history:t0", "history:t2400"),
        ("spread", "spread:p1", "spread:p4"),
    ):
        found = status(every_arm({base: 54, top: 30}), knob)
        assert found["status"] == "bites", knob
        assert [(c["a"], c["b"]) for c in found["contrasts"]] == [(base, top)], knob


def test_shape_bites_in_either_direction_and_names_the_harder_width() -> None:
    narrow = status(every_arm({"shape:w1": 54, "shape:w4": 30, "shape:w1+len(w4)": 54}), "shape")
    assert narrow["status"] == "bites" and narrow["harder"] == "shape:w4"
    wide = status(every_arm({"shape:w1": 30, "shape:w4": 54, "shape:w1+len(w4)": 30}), "shape")
    assert wide["status"] == "bites" and wide["harder"] == "shape:w1"


def test_shape_does_not_bite_when_its_control_differs_from_w1_by_0_15_or_more() -> None:
    """The control is read against `w1`, not `w4`: here it moves as far from `w1` as `w4` does,
    so the difference is the request's length and not the arrangement."""
    found = status(every_arm({"shape:w1": 54, "shape:w4": 30, "shape:w1+len(w4)": 30}), "shape")
    assert found["status"] == "does not bite"
    assert [(c["a"], c["b"]) for c in found["contrasts"]] == [
        ("shape:w1", "shape:w4"),
        ("shape:w1", "shape:w1+len(w4)"),
    ]
    close = status(every_arm({"shape:w1": 54, "shape:w4": 30, "shape:w1+len(w4)": 46}), "shape")
    assert close["status"] == "bites"


def test_shape_needs_its_own_size_and_interval_either_way() -> None:
    small = status(every_arm({"shape:w1": 54, "shape:w4": 48, "shape:w1+len(w4)": 54}), "shape")
    assert small["status"] == "does not bite"
    cells = every_arm({})
    cells["shape:w1"], cells["shape:w4"] = noisy("shape:w1", True), noisy("shape:w4", False)
    cells["shape:w1+len(w4)"] = noisy("shape:w1+len(w4)", True)
    assert status(cells, "shape")["status"] == "does not bite"


def test_the_seeds_are_paired_not_pooled() -> None:
    """Base on its first 35 seeds, top on its first 25: paired, the drop is on the same ten
    seeds and its interval is tight; each arm's own interval, by the same bootstrap, is wide
    enough that comparing marginals would hold zero."""
    cells = every_arm({"similarity:s0": 35, "similarity:s3": 25})
    found = status(cells, "similarity")
    (contrast,) = found["contrasts"]
    assert abs(contrast["delta"] - 10 / 60) < 1e-12 and contrast["low"] > 0
    assert found["status"] == "bites"
    base = cal.cluster_bootstrap(
        cells["similarity:s0"], cal.pass_at_1, resamples=2000, seed=20260922
    )
    top = cal.cluster_bootstrap(
        cells["similarity:s3"], cal.pass_at_1, resamples=2000, seed=20260922
    )
    assert base[0] - top[1] < 0 < base[1] - top[0]
    assert len(seeds60()) == 60
