"""Recompute a published calibration card from its per-episode records, and check it.

    python examples/calibration_card.py [DIR]

DIR is one model's folder under `calibration/`, and defaults to model A's,
`calibration/gpt-5-nano-2025-08-07`; model B's is `calibration/qwen3-8b-b968826d`.  A folder
holds the per-episode records the card was computed from (`episodes.jsonl`), the
machine-readable card (`artifact.json`) and, for a run that tallied instrument failures as they
happened, that tally (`tallies.json`).  This rebuilds the artifact from the records alone,
under the provenance block the run recorded, checks that it is byte-identical to the committed
one, says whether the card is current for the installed generator, and prints the rendered card.

No model, no network, no Proofload.  Every published number is a function of the records and
the provenance, so nothing here needs the run to be repeated.
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

from poisson_tasks import calibration as cal
from poisson_tasks.tasks import generate

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIR = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "calibration" / cal.MODEL_A

committed = (DIR / "artifact.json").read_bytes()
provenance = cal.Provenance(**json.loads(committed)["provenance"])

records = cal.read_records(DIR / "episodes.jsonl")
cells: dict[tuple[str, str], list[cal.EpisodeRecord]] = {}
for record in records:
    cells.setdefault((record.arm_id, record.model), []).append(record)

# The instrument failures tallied as they happened, per arm; a run with none has none.
tallies_path = DIR / "tallies.json"
tallies = json.loads(tallies_path.read_text()) if tallies_path.exists() else {}
artifact = cal.build_artifact(
    cells, provenance, tally={key: tallies.get(key[0], {}) for key in cells}
)

with tempfile.TemporaryDirectory() as scratch:
    rebuilt = cal.write_artifact(artifact, pathlib.Path(scratch) / "artifact.json").read_bytes()

print(cal.render_document(artifact))
print(f"{len(records)} records, {len(cells)} cells")
if rebuilt != committed:
    sys.exit("the rebuilt artifact differs from the committed artifact.json")
print("the rebuilt artifact is byte-identical to the committed artifact.json")
# The installed generator's hash, read off a generated task (it is `tasks.py`'s own bytes).
current = generate(cal.arm_specs()[0], cal.seed_list()[0]).generator_hash
print("the card is current for this generator" if provenance.generator_hash == current
      else f"the card is STALE: it was measured at generator {provenance.generator_hash}, "
           f"and the installed generator is {current}")
