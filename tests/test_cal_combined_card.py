"""One page for every calibrated model: `docs/calibration.md`.

The page is rendered, never typed: each model's own card in full, and before them where the
models' difficulty orderings agree. It is built from the committed cards, and this file holds
the committed page to that rendering byte for byte.

Agreement is read from each card's own level comparisons, never from the raw sign of a
difference:
- the models **agree** on a pair of adjacent levels when both cards call it distinguishable in
  the same direction;
- they **disagree** when both call it distinguishable in opposite directions;
- otherwise at least one card cannot call it, and the page says so.

A sign alone would count noise as agreement.

Cards compare only when they were measured the same way: one generator, one engine table and
vocabulary, one harness, one seed list of one length, the same attempts per task, decoding and
resolution, and the same saturation bounds and bootstrap. The page refuses a set that does
not.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks.knobs import levels
from tests.helpers import rebuild_committed_card

REPO = Path(__file__).resolve().parent.parent
N = 5
TASKS = 20


def _provenance(model: str, **over: Any) -> cal.Provenance:
    seeds = list(range(5000, 5000 + cal.S))
    base: dict[str, Any] = dict(
        package_version="0.0.1", engine_hash="e" * 64, generator_hash="g" * 64,
        vocabulary_hash="v" * 64, verifiers_version="0.3.1", harness_id="null",
        models=[{"id": model, "revision": model, "endpoint_host": "h"}],
        decoding=dict(cal.DECODING), seed_list=seeds,
        seed_list_hash=hashlib.sha256(json.dumps(seeds).encode()).hexdigest(),
        S=cal.S, n=N, k_values=[1, 2, 5], bootstrap_resamples=200, bootstrap_seed=20260922,
        delta_star=0.15, saturation_high=0.95, saturation_low=0.05, instrument_threshold=0.02,
        rate_read_date="2026-09-30", serving={model: {"kind": "hosted", "endpoint_host": "h"}},
        budget=dict(cal.DEFAULT_BUDGET),
    )
    base.update(over)
    return cal.Provenance(**base)


def _artifact(model: str, strict_by_level: dict[int, int], **over: Any) -> cal.Artifact:
    """A depth-only card on which every attempt reaches the goal and `strict_by_level[level]`
    of each task's five also stop at it."""
    cells: dict[tuple[str, str], list[cal.EpisodeRecord]] = {}
    for level in levels("depth"):
        arm = f"depth:d{level}"
        rows = []
        for task in range(TASKS):
            for attempt in range(N):
                passed = attempt < strict_by_level[level]
                rows.append(cal.EpisodeRecord(
                    task_id=f"{arm}-{task}", arm_id=arm, model=model, seed=5000 + task,
                    attempt=attempt, strict=passed, leaky=True,
                    label="passed" if passed else "overshoot", turns=level + 1,
                    sampled_calls=level, prompt_tokens=10, cached_input_tokens=0,
                    completion_tokens=5, reasoning_tokens=0))
        cells[(arm, model)] = rows
    return cal.build_artifact(cells, _provenance(model, **over))


# Strict per level out of five.  Model "a" falls from d2 to d3 and from d3 to d5; model "b"
# rises from d2 to d3 and falls from d3 to d5; d1 and d8 are saturated for both.
A_STRICT = {1: 5, 2: 4, 3: 2, 5: 1, 8: 0}
B_STRICT = {1: 5, 2: 1, 3: 3, 5: 1, 8: 0}


def _demoted(card: str) -> str:
    """A card nested under its model's `##` section: every heading two levels down."""
    return "\n".join("##" + line if line.startswith("#") else line for line in card.splitlines())


def test_the_page_holds_each_models_card_in_full() -> None:
    a, b = _artifact("a", A_STRICT), _artifact("b", B_STRICT)
    page = cal.render_combined_document([b, a])
    for artifact in (a, b):
        assert _demoted(cal.render_document(artifact)) in page
    assert page.index("## a") < page.index("## b"), "models in a stable order"


def test_agreement_is_read_from_both_cards_verdicts() -> None:
    a, b = _artifact("a", A_STRICT), _artifact("b", B_STRICT)
    rows = {(row["knob"], row["predicate"], row["level_a"], row["level_b"]): row
            for row in cal.agreement_rows([a, b])}
    # Both call d2 vs d3, in opposite directions.
    assert rows[("depth", "strict", 2, 3)]["agreement"] == "disagree"
    # Both call d3 vs d5 in the same direction.
    assert rows[("depth", "strict", 3, 5)]["agreement"] == "agree"
    # d1 and d8 are saturated, so neither card can call a pair that touches them.
    assert rows[("depth", "strict", 1, 2)]["agreement"] == "cannot tell"
    assert rows[("depth", "strict", 5, 8)]["agreement"] == "cannot tell"


def test_a_difference_one_card_calls_too_small_is_not_agreement() -> None:
    """Same sign, but one card says the design cannot resolve it: not counted as agreement."""
    a = _artifact("a", A_STRICT)
    b = _artifact("b", {1: 5, 2: 4, 3: 4, 5: 1, 8: 0})
    rows = {(row["knob"], row["predicate"], row["level_a"], row["level_b"]): row
            for row in cal.agreement_rows([a, b])}
    assert rows[("depth", "strict", 2, 3)]["agreement"] == "cannot tell"


def test_the_page_counts_agreement_per_table() -> None:
    a, b = _artifact("a", A_STRICT), _artifact("b", B_STRICT)
    page = cal.render_combined_document([a, b])
    summary = next(line for line in page.splitlines()
                   if line.startswith("depth, strict pass@1:"))
    assert "agree on 1" in summary and "disagree on 1" in summary and "of 4" in summary


def _measured_otherwise(provenance: cal.Provenance, change: dict[str, Any]) -> cal.Provenance:
    """`provenance` with `change` applied.  `Provenance` refuses any harness but the measured
    one when it is built, so that change is set on a built copy: the page has to refuse it on
    its own account."""
    if "harness_id" in change:
        changed = copy.copy(provenance)
        object.__setattr__(changed, "harness_id", change["harness_id"])
        return changed
    return dataclasses.replace(provenance, **change)


# One case per field two cards must share, each changing that field alone among them.
@pytest.mark.parametrize("change", [
    {"generator_hash": "x" * 64}, {"engine_hash": "x" * 64}, {"vocabulary_hash": "x" * 64},
    {"n": 4, "k_values": [1, 2]}, {"delta_star": 0.2},
    {"decoding": {**cal.DECODING, "temperature": 0.7}},
    {"seed_list_hash": "x" * 64},
    {"S": cal.S + 1, "seed_list": [*range(5000, 5000 + cal.S), 9999]},
    {"harness_id": "bash"},
    {"saturation_high": 0.9}, {"saturation_low": 0.1},
    {"bootstrap_resamples": 100}, {"bootstrap_seed": 1},
], ids=["generator", "engine", "vocabulary", "attempts", "resolution", "decoding",
        "seed_list", "tasks", "harness", "saturation_high", "saturation_low",
        "bootstrap_resamples", "bootstrap_seed"])
def test_cards_measured_differently_do_not_share_a_page(change: dict[str, Any]) -> None:
    a = _artifact("a", A_STRICT)
    b = _artifact("b", B_STRICT)
    changed = dataclasses.replace(b, provenance=_measured_otherwise(b.provenance, change))
    with pytest.raises(ValueError):
        cal.render_combined_document([a, changed])


def test_one_model_twice_is_refused() -> None:
    with pytest.raises(ValueError):
        cal.render_combined_document([_artifact("a", A_STRICT), _artifact("a", B_STRICT)])


def _committed(folder: str) -> cal.Artifact:
    artifact, _ = rebuild_committed_card(REPO / "calibration" / folder)
    return artifact


def test_docs_calibration_md_is_the_rendering_of_the_committed_cards() -> None:
    cards = [_committed(folder.name) for folder in sorted((REPO / "calibration").iterdir())
             if (folder / "artifact.json").exists()]
    assert len(cards) == 2
    expected = cal.render_combined_document(cards)
    assert (REPO / "docs" / "calibration.md").read_text(encoding="utf-8") == expected
