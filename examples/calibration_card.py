"""Recompute a published calibration card from its per-episode records, and check it.

    python examples/calibration_card.py [DIR]

DIR defaults to `calibration/gpt-5-nano-2025-08-07`, model A's card. It holds the 4,200
per-episode records the card was computed from (`episodes.jsonl`) and the machine-readable
card (`artifact.json`). This rebuilds the artifact from the records alone, checks that it is
byte-identical to the committed one, and prints the rendered card.

No model, no network, no Proofload. Every published number is a function of the records and
the provenance below, so nothing here needs the run to be repeated.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

from poisson_tasks import calibration as cal

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIR = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "calibration" / cal.MODEL_A

# What the run declared about the model: where it was served, and the dollar rates read on
# the day of the run (per million tokens; cached input is billed at its own rate).
PROVENANCE = cal.Provenance.for_run(
    models=[
        {
            "id": cal.MODEL_A,
            "revision": cal.MODEL_A,
            "endpoint_host": "api.openai.com",
            "input_rate": 0.05,
            "cached_input_rate": 0.005,
            "output_rate": 0.40,
        }
    ],
    serving={cal.MODEL_A: {"kind": "hosted", "endpoint_host": "api.openai.com"}},
    rate_read_date="2026-09-25",
)

records = cal.read_records(DIR / "episodes.jsonl")
cells: dict[tuple[str, str], list[cal.EpisodeRecord]] = {}
for record in records:
    cells.setdefault((record.arm_id, record.model), []).append(record)

# The run recorded no instrument failure, so every cell's tally is empty.
artifact = cal.build_artifact(cells, PROVENANCE, tally={key: {} for key in cells})

with tempfile.TemporaryDirectory() as scratch:
    rebuilt = cal.write_artifact(artifact, pathlib.Path(scratch) / "artifact.json").read_bytes()
committed = (DIR / "artifact.json").read_bytes()

print(cal.render_document(artifact))
print(f"{len(records)} records, {len(cells)} cells")
if rebuilt != committed:
    sys.exit("the rebuilt artifact differs from the committed artifact.json")
print("the rebuilt artifact is byte-identical to the committed artifact.json")
