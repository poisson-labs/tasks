"""Neither published card carries a concurrency.

The card prints the run's concurrency with every time figure, and a provenance block without
one prints *not recorded*.  Both published runs went through the runner with no declared limit
on episodes at once, and neither wrote down how many ran together; neither card recorded any
time either.  So neither gains a concurrency when the cards are re-committed with their new
figures: a number read back from the code's default would be a claim the run never made.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CARDS = Path(__file__).resolve().parent.parent / "calibration"
FOLDERS = sorted(path.parent.name for path in CARDS.glob("*/artifact.json"))


@pytest.mark.parametrize("folder", FOLDERS)
def test_k0_7_neither_published_card_records_a_concurrency(folder: str) -> None:
    stored = json.loads((CARDS / folder / "artifact.json").read_text(encoding="utf-8"))
    assert len(FOLDERS) == 2
    assert "concurrency" not in stored["provenance"]
