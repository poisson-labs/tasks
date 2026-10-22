"""Reading a card beside the published ones, frozen as tests: `calibration.comparable` and
`calibration.render_side_by_side`.

The invariants, with the decision the card's build was given: a card for a plan no published card
covers compares nothing it cannot compare.

- `comparable` answers with the first field of `_COMPARABLE` two cards differ in, and
  says whether they measured one model.  The published cards are comparable with each other.  A
  first look never is, by design: its seed list is not the published one.
- `render_side_by_side` keys cards by a label, so a run and the published card of the
  same model can sit side by side, which the published page (`render_combined_document`, one card
  per model) refuses; it pools nothing, and it refuses cards `comparable` says differ.

**Two readings of the design, and which holds.**  One said a first look's answer against either
published card is the seed-list hash.  The other says the answer is the first field of
`_COMPARABLE` that differs, and the generator hash comes first in that tuple; since the knobs'
shared base moved the generator, both published cards are on another generator than any
run, so the first field is the generator hash today, and the seed-list hash once the new cards
land.  The second holds: the test reads the order from `_COMPARABLE` and the provenance blocks, and
checks the seed-list hash is among the fields that differ.

Shapes decided here, where the design leaves them open
------------------------------------------------------

**1. `comparable(a, b)` returns a `Comparison`**: `field` (the first field they differ in, or
`None`), `reason` (one line saying it in words, `None` when comparable), `same_model` (the two
cards' models are one, matched without a `@revision`, as the estimate matches a card) and
`shared_arms` (the arm ids both hold a cell of).  It is symmetric in `field`.

**2. `render_side_by_side(cards)` takes a mapping of label to artifact** and returns the
document.  Every label is in it, and each card's own figures; it refuses a set in which
`comparable` names a field for any pair, and a set in which some card shares no arm with
another, since nothing can be read side by side there: in one line naming the two cards by their
labels.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from tests.fd3_support import calibration, needs_uv
from tests.fd4_support import (
    RunFolders,
    differing,
    fd4_runs,
    one_line,
    shipped_artifacts,
)

__all__ = ["fd4_runs"]


def run_card(fd4_runs: RunFolders, scenario: str) -> Any:
    return calibration().card_from_run(fd4_runs[scenario].folder).artifact


def models(artifact: Any) -> set[str]:
    return {cell["model"].split("@", 1)[0] for cell in artifact.cells}


def arms(artifact: Any) -> list[str]:
    return [cell["arm_id"] for cell in artifact.cells]


# ---------------------------------------------------------------------------
# comparable
# ---------------------------------------------------------------------------


def test_fd4_5_the_published_cards_are_comparable_with_each_other() -> None:
    shipped = shipped_artifacts()
    assert len(shipped) >= 2
    for a in shipped:
        for b in shipped:
            answer = calibration().comparable(a, b)
            assert (answer.field, answer.reason) == (None, None)
            assert answer.same_model == (models(a) == models(b))
            assert set(answer.shared_arms) == set(arms(a)) & set(arms(b))


@needs_uv
def test_fd4_5_a_first_look_is_not_comparable_and_says_the_first_field(
    fd4_runs: RunFolders,
) -> None:
    card = run_card(fd4_runs, "first_look")
    assert any(models(card) == models(other) for other in shipped_artifacts())
    for other in shipped_artifacts():
        fields = differing(card.provenance, other.provenance)
        assert "seed_list_hash" in fields
        answer = calibration().comparable(card, other)
        assert answer.field == fields[0]
        assert one_line(answer.reason)
        assert calibration().comparable(other, card).field == fields[0]
        assert answer.same_model == (models(card) == models(other))
        assert set(answer.shared_arms) == set(arms(card)) & set(arms(other))


@needs_uv
def test_fd4_5_a_model_named_without_its_revision_has_its_published_card(
    fd4_runs: RunFolders,
) -> None:
    """The second published card's model is recorded with its revision; a run of that model by
    the name its server serves it under is the same model."""
    card = run_card(fd4_runs, "qwen")
    matches = [other for other in shipped_artifacts() if models(other) == models(card)]
    assert matches, "a shipped card measured this model"
    for other in shipped_artifacts():
        assert calibration().comparable(card, other).same_model == (other in matches)


@needs_uv
def test_fd4_5_a_card_at_another_generator_version_is_not_comparable(
    fd4_runs: RunFolders,
) -> None:
    """Two runs of one plan are comparable (the control); a run at another generator version is
    not, though its arms' ids are the same, and the field named is the generator's."""
    strict = run_card(fd4_runs, "strict")
    assert calibration().comparable(strict, run_card(fd4_runs, "strict_again")).field is None
    other = run_card(fd4_runs, "generator_0")
    assert arms(other) == arms(strict)
    answer = calibration().comparable(strict, other)
    assert answer.field == differing(strict.provenance, other.provenance)[0]
    assert one_line(answer.reason)


# ---------------------------------------------------------------------------
# side by side
# ---------------------------------------------------------------------------


def synthetic(model: str, strict: tuple[int, ...], arm_list: tuple[str, ...]) -> Any:
    """A card of `model` over four tasks per arm, five attempts each, of which `strict[i]` pass
    strictly at the i-th task and the rest overshoot, under one fixed provenance block, so that
    two of them are comparable whatever their model."""
    cal = calibration()
    seeds = [7001, 7002, 7003, 7004]
    prov = cal.Provenance(
        package_version="0.0.1", engine_hash="e" * 64, generator_hash="g" * 64,
        vocabulary_hash="v" * 64, verifiers_version="0.3.1", harness_id="null",
        models=[{"id": model, "revision": model, "endpoint_host": "h"}],
        decoding=dict(cal.DECODING), seed_list=seeds,
        seed_list_hash=hashlib.sha256(json.dumps(seeds).encode()).hexdigest(),
        S=len(seeds), n=5, k_values=[1, 2, 5], bootstrap_resamples=200,
        bootstrap_seed=20260922, delta_star=0.15, saturation_high=0.95, saturation_low=0.05,
        instrument_threshold=0.02, rate_read_date="2026-10-08",
        serving={model: {"kind": "hosted", "endpoint_host": "h"}},
        budget=dict(cal.DEFAULT_BUDGET))
    cells = {}
    for arm in arm_list:
        rows = []
        for seed, passes in zip(seeds, strict, strict=True):
            for attempt in range(5):
                passed = attempt < passes
                rows.append(cal.EpisodeRecord(
                    task_id=f"{arm}-{seed}", arm_id=arm, model=model, seed=seed,
                    attempt=attempt, strict=passed, leaky=True,
                    label="passed" if passed else "overshoot", turns=3, sampled_calls=2,
                    prompt_tokens=10, cached_input_tokens=0, completion_tokens=5,
                    reasoning_tokens=0))
        cells[(arm, model)] = rows
    return cal.build_artifact(cells, prov)


def test_fd4_6_side_by_side_keys_cards_by_label_and_pools_nothing() -> None:
    """Two cards of one model, which the published page refuses, sit side by side under their
    labels.  Each card's own strict rate is printed (0.700 and 0.150) and their pooled rate
    (0.425), which no figure of either card can be, is not."""
    cal = calibration()
    mine = synthetic("gpt-5-nano-2025-08-07", (1, 1, 0, 1), ("depth:d3",))
    published = synthetic("gpt-5-nano-2025-08-07", (4, 4, 3, 3), ("depth:d3",))
    with pytest.raises(ValueError):
        cal.render_combined_document([published, mine])
    page = cal.render_side_by_side({"label-published-xq": published, "label-run-xq": mine})
    assert "label-published-xq" in page and "label-run-xq" in page
    assert "0.700" in page and "0.150" in page
    assert "0.425" not in page


@needs_uv
def test_fd4_6_side_by_side_refuses_cards_measured_differently(fd4_runs: RunFolders) -> None:
    card = run_card(fd4_runs, "first_look")
    for other in shipped_artifacts():
        assert calibration().comparable(card, other).field is not None
        with pytest.raises(ValueError) as refused:
            calibration().render_side_by_side({"label-published-xq": other, "label-run-xq": card})
        assert one_line(str(refused.value))
        assert "label-published-xq" in str(refused.value) and "label-run-xq" in str(refused.value)


@needs_uv
def test_fd4_a_plan_no_published_card_covers_compares_nothing(fd4_runs: RunFolders) -> None:
    """A card of a level no published card measured (the first depth level none holds) shares no
    arm with any of them, and is not put beside them.  Measured alike, two cards that share no arm are refused too, and two that
    share one are not (the control)."""
    card = run_card(fd4_runs, "uncovered")
    for other in shipped_artifacts():
        assert tuple(calibration().comparable(card, other).shared_arms) == ()
        with pytest.raises(ValueError):
            calibration().render_side_by_side({"published": other, "mine": card})
    a = synthetic("model-a", (2, 2, 2, 2), ("depth:d1", "depth:d3"))
    b = synthetic("model-b", (3, 3, 3, 3), ("depth:d4",))
    c = synthetic("model-c", (3, 3, 3, 3), ("depth:d3", "depth:d4"))
    assert calibration().comparable(a, b).field is None
    assert tuple(calibration().comparable(a, b).shared_arms) == ()
    with pytest.raises(ValueError) as refused:
        calibration().render_side_by_side({"label-a-xq": a, "label-b-xq": b})
    assert one_line(str(refused.value))
    assert "label-a-xq" in str(refused.value) and "label-b-xq" in str(refused.value)
    page = calibration().render_side_by_side({"label-a-xq": a, "label-c-xq": c})
    assert "label-a-xq" in page and "label-c-xq" in page
