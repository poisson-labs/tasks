"""A card's float figures add left to right, so a card rebuilds byte for byte on every Python.

From Python 3.12 the builtin `sum` of floats is a compensated sum, and the published cards were
built on 3.11, where it adds one value at a time from the left.  A figure computed with `sum`
then moves in its last digit on 3.12 and 3.13, and `card --published` and `card --check` report
a card that no longer rebuilds.  The calibration module adds its float figures itself, left to
right, which is 3.11's `sum` exactly.

The tests put a compensated `sum` in the calibration module's namespace, where the builtin is
looked up, so a float figure computed with `sum` fails on every Python and not only on 3.12 and
later:
- the published cards rebuild from their records byte for byte (the task means behind every
  rate and interval);
- a provider-reported cost is the left-to-right total of the episodes' costs (no published card
  carries one).
"""

from __future__ import annotations

import builtins
import dataclasses
import json
import math
from collections.abc import Iterable
from pathlib import Path

import pytest

from poisson_tasks import calibration as cal
from tests.helpers import rebuild_committed_card

CARDS = Path(__file__).resolve().parent.parent / "calibration"
MODEL_A = CARDS / "gpt-5-nano-2025-08-07"
MODEL_B = CARDS / "qwen3-8b-b968826d"


def _compensated(values: Iterable[object], start: object = 0) -> object:
    """A compensated sum where any value is a float, as 3.12's `sum` is; the builtin otherwise,
    so counts stay integers."""
    items = list(values)
    if any(isinstance(item, float) for item in items):
        return math.fsum([start, *items])  # type: ignore[list-item]
    return builtins.sum(items, start)  # type: ignore[call-overload]


@pytest.fixture
def compensated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cal, "sum", _compensated, raising=False)


@pytest.mark.usefixtures("compensated")
@pytest.mark.parametrize("folder", [MODEL_A, MODEL_B], ids=["model_a", "model_b"])
def test_a_published_card_rebuilds_byte_for_byte_under_a_compensated_sum(
    folder: Path, tmp_path: Path
) -> None:
    artifact, _cells = rebuild_committed_card(folder)
    rebuilt = cal.write_artifact(artifact, tmp_path / "artifact.json").read_bytes()
    assert rebuilt == (folder / "artifact.json").read_bytes()


@pytest.mark.usefixtures("compensated")
def test_a_reported_cost_is_the_left_to_right_total() -> None:
    stored = json.loads((MODEL_A / "artifact.json").read_text())
    records = [r for r in cal.read_records(MODEL_A / "episodes.jsonl") if r.arm_id == "depth:d1"]
    cell = [dataclasses.replace(r, cost=0.1) for r in records]
    expected = 0.0
    for _row in cal.scored(cell):
        expected += 0.1
    artifact = cal.build_artifact(
        {("depth:d1", records[0].model): cell}, cal.Provenance(**stored["provenance"])
    )
    assert artifact.cells[0]["reported_cost"] == expected
