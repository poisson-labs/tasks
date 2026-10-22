"""What the faults knob leaves alone: the similarity knob's tasks keep their content, frozen as a
test.

As the knobs' design states it for the faults knob: the 840 published tasks keep their content
(frozen `tests/test_k1_content.py`), and so do the similarity tasks.  No published card measures
similarity, so nothing else holds them: the `test_k2_*` tests pin their structure, not their bytes,
and a change to a draw they share with faults would pass them.

The digests are of every field but `task_id`, `generator_hash` and `pins`, which move with any edit
to the generator's modules (the rule in `tests/test_k1_content.py`), at every card seed, per
level and split, computed on `main` at `596eeaa` (the similarity knob merged) before any edit for
faults.  It passes on that
tree by design.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

import pytest

from tests.k3_support import CARD_SEEDS, made

MOVES = {"task_id", "generator_hash", "pins"}
MAIN = {
    ("similarity:s0", "eval"): "fb0ad92507616b7a2952043fa1f8e72b2cdee170fa961ac1578885a4805d5577",
    ("similarity:s1", "eval"): "66b860aa56c0f80dfc13414a7f614c8bb30c925763044181a4679209f1e645b3",
    ("similarity:s2", "eval"): "4d32693984fe4bb9cf43b0c6cf0fff57746c9c06b22338969de71fbcb95a3585",
    ("similarity:s3", "eval"): "17618e881159765949db7cf71b75b192d2f9fe9b23514823f904e78fdfb4ce73",
    ("similarity:s0", "train"): "eef471a9152136810648561f06d70d3127cf3d324abdcbe3f15355a0bc5f5928",
    ("similarity:s1", "train"): "96e00f48ccfe76377c1f6e45d5256289af622f620e3a0563d7228dcbe7b207e6",
    ("similarity:s2", "train"): "c1952d94d68b2e8ca1902a0b45c5c2e2c3d992bb369b07054c4826a7352b9b3f",
    ("similarity:s3", "train"): "a56920df5996ec5b9021190335e1e9ecbef10875ff77b62df4046c008fe9481b",
}


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return list(value)


@pytest.mark.parametrize(("arm_id", "split"), sorted(MAIN))
def test_the_similarity_tasks_keep_their_content(arm_id: str, split: str) -> None:
    digest = hashlib.sha256()
    for seed in CARD_SEEDS:
        bundle = made(arm_id, seed, split)
        content = {
            field.name: getattr(bundle, field.name)
            for field in dataclasses.fields(bundle)
            if field.name not in MOVES
        }
        digest.update(
            json.dumps(content, sort_keys=True, separators=(",", ":"), default=plain).encode()
        )
        digest.update(b"\n")
    assert digest.hexdigest() == MAIN[(arm_id, split)]
