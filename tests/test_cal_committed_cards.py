"""The calibration cards committed under `calibration/` recompute from their own records.

Each folder holds one model's per-episode records (`episodes.jsonl`), the machine-readable card
built from them (`artifact.json`), and for model B the instrument tally the run kept as it went
(`tallies.json`).  Every number the README and the calibration guide quote is read from these
files, so they must keep recomputing: the artifact is rebuilt here from the records alone,
under the provenance block the run recorded, and compared byte for byte.

The two cards are comparable only when measured the same way; `docs/calibration.md`, which
`tests/test_cal_combined_card.py` renders from these cards, refuses them otherwise.  Model B's
records the serving settings its run used: the 16,384-token context, vLLM's own sampler and
the 32-call cap.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from poisson_tasks import calibration as cal

CARDS = Path(__file__).resolve().parent.parent / "calibration"
MODEL_A = CARDS / "gpt-5-nano-2025-08-07"
MODEL_B = CARDS / "qwen3-8b-b968826d"


def _provenance(folder: Path) -> dict[str, object]:
    stored: dict[str, object] = json.loads((folder / "artifact.json").read_text())["provenance"]
    return stored


@pytest.mark.parametrize("folder", [MODEL_A, MODEL_B], ids=["model_a", "model_b"])
def test_the_committed_card_recomputes_byte_for_byte(folder: Path) -> None:
    committed = (folder / "artifact.json").read_bytes()
    provenance = cal.Provenance(**json.loads(committed)["provenance"])
    cells: dict[tuple[str, str], list[cal.EpisodeRecord]] = {}
    for record in cal.read_records(folder / "episodes.jsonl"):
        cells.setdefault((record.arm_id, record.model), []).append(record)
    tallies_path = folder / "tallies.json"
    tallies = json.loads(tallies_path.read_text()) if tallies_path.exists() else {}
    artifact = cal.build_artifact(
        cells, provenance, tally={key: tallies.get(key[0], {}) for key in cells}
    )
    with tempfile.TemporaryDirectory() as scratch:
        rebuilt = cal.write_artifact(artifact, Path(scratch) / "artifact.json").read_bytes()
    assert rebuilt == committed
    assert len(cells) == 14 and all(len(cell) == cal.S * cal.N for cell in cells.values())


def test_model_b_records_its_serving_settings_and_the_cap() -> None:
    b = _provenance(MODEL_B)
    assert b["max_model_calls"] == 32
    (serving,) = b["serving"].values()  # type: ignore[attr-defined]
    flags = serving["flags"]
    assert flags[flags.index("--max-model-len") + 1] == "16384"
    assert "VLLM_USE_FLASHINFER_SAMPLER=0" in flags


def test_model_a_ran_without_a_cap_and_never_reached_it() -> None:
    assert "max_model_calls" not in _provenance(MODEL_A)
    longest = max(r.turns for r in cal.read_records(MODEL_A / "episodes.jsonl"))
    assert longest < 32
