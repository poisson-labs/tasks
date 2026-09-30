"""A bundle written before the card gained a figure still verifies, and a tampered one does not.

`verify` rebuilds a bundle's artifact from its records and compares it with the stored one.
When the card gains a figure, as it did with the overshoot share, the leaky interval and depth's
comparisons on reaching the goal, the rebuild carries figures an older artifact never had.
Comparing whole files would then call every earlier bundle broken, including the model B run
filed in the vault, though every number it holds still recomputes.  So `verify` checks every
number the stored artifact carries, and only those.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks import calibration_run as run

REPO = Path(__file__).resolve().parent.parent
MODEL_B = REPO / "calibration" / "qwen3-8b-b968826d"
NEWER = {"leaky_at_1_interval", "overshoot_count", "overshoot_share"}


def _current_artifact() -> dict[str, Any]:
    stored = json.loads((MODEL_B / "artifact.json").read_text())
    cells: dict[tuple[str, str], list[cal.EpisodeRecord]] = {}
    for record in cal.read_records(MODEL_B / "episodes.jsonl"):
        cells.setdefault((record.arm_id, record.model), []).append(record)
    tallies = json.loads((MODEL_B / "tallies.json").read_text())
    artifact = cal.build_artifact(cells, cal.Provenance(**stored["provenance"]),
                                  tally={key: tallies.get(key[0], {}) for key in cells})
    return artifact.as_dict()


def _older(artifact: dict[str, Any]) -> dict[str, Any]:
    """The same artifact as it was written before the newer figures existed."""
    older = {key: value for key, value in artifact.items() if key != "reach_pairs"}
    older["cells"] = [{k: v for k, v in cell.items() if k not in NEWER}
                      for cell in artifact["cells"]]
    return older


def _bundle(folder: Path, artifact: dict[str, Any]) -> Path:
    folder.mkdir()
    (folder / "artifact.json").write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    for name in ("episodes.jsonl", "tallies.json"):
        (folder / name).write_bytes((MODEL_B / name).read_bytes())
    manifest = "".join(
        f"{hashlib.sha256((folder / name).read_bytes()).hexdigest()}  {name}\n"
        for name in ("artifact.json", "episodes.jsonl", "tallies.json"))
    (folder / run.MANIFEST).write_text(manifest)
    return folder


def test_a_bundle_from_before_the_newer_figures_still_verifies(tmp_path: Path) -> None:
    older = _older(_current_artifact())
    assert "reach_pairs" not in older and not NEWER & set(older["cells"][0])
    result = run.verify_bundle(_bundle(tmp_path / "older", older))
    assert result["recomputed"] is True


def test_a_tampered_number_in_an_older_bundle_is_still_refused(tmp_path: Path) -> None:
    older = _older(_current_artifact())
    older["cells"][0]["pass_at_1"] = older["cells"][0]["pass_at_1"] + 0.001
    with pytest.raises(ValueError):
        run.verify_bundle(_bundle(tmp_path / "tampered", older))


def test_a_current_bundle_verifies_with_every_figure(tmp_path: Path) -> None:
    current = _current_artifact()
    assert "reach_pairs" in current
    assert run.verify_bundle(_bundle(tmp_path / "current", current))["recomputed"] is True


def test_a_bundle_cannot_drop_a_cell_and_still_verify(tmp_path: Path) -> None:
    """Checking only what the stored artifact carries must not let a whole cell go missing."""
    older = _older(_current_artifact())
    older["cells"] = older["cells"][1:]
    with pytest.raises(ValueError):
        run.verify_bundle(_bundle(tmp_path / "short", older))
