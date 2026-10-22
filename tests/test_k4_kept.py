"""What the history knob leaves alone: the similarity and faults knobs' tasks keep their content,
frozen as tests.

As the knobs' design states it for the history knob: the 840 published tasks keep their content
(frozen `tests/test_k1_content.py`), and so do the similarity and faults tasks built before it.  No
published card measures either, so nothing else holds their bytes: the `test_k2_*` and `test_k3_*`
tests pin their structure, not their content, and a change to a draw or a seeding rule they share
with history would pass them.

The digests are of every field but `task_id`, `generator_hash` and `pins`, which move with any edit
to the generator's modules (the rule in `tests/test_k1_content.py`), at every card seed, per
arm and split, computed on `main` at `71ab1df` (the faults knob merged) before any edit for
history.  It passes on that tree by design.  The eight similarity digests equal the ones taken on
`596eeaa` for the faults knob (`tests/test_k3_kept.py`): faults moved nothing of similarity's.
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
    ("faults:f0", "eval"): "0f8fd375ceeb93fed9c0a4821da1a1c2f4d4f2e466548cf73d26bc1d4655e62a",
    ("faults:f1", "eval"): "4166854c3577cc0e6699c1d58cfe352ee000ddcd848da5a7f94f01f576ee05d8",
    ("faults:f2", "eval"): "58d70bd2e3f8e499683529a171bdab68bc50e5ffea3c7f9bf59d4964b6d654e9",
    ("faults:f4", "eval"): "bab083ae2163454cd61b2cccf43e769e4c7cb3dc6064044b5d8b750570de8618",
    (
        "faults:f0+len(f4)",
        "eval",
    ): "a79d9a8ecf06454d3891dff5c483636bc9b42b886a5fdf63414150856bd8373e",
    ("similarity:s0", "train"): "eef471a9152136810648561f06d70d3127cf3d324abdcbe3f15355a0bc5f5928",
    ("similarity:s1", "train"): "96e00f48ccfe76377c1f6e45d5256289af622f620e3a0563d7228dcbe7b207e6",
    ("similarity:s2", "train"): "c1952d94d68b2e8ca1902a0b45c5c2e2c3d992bb369b07054c4826a7352b9b3f",
    ("similarity:s3", "train"): "a56920df5996ec5b9021190335e1e9ecbef10875ff77b62df4046c008fe9481b",
    ("faults:f0", "train"): "d5d7f184f4aba87ae7327e909ef222006d5a3eeefe503cf2f9777a6b6283f155",
    ("faults:f1", "train"): "ac9dacb22193b72ba996113fb983082880a146e716737d7ddab617337d7a3dfd",
    ("faults:f2", "train"): "0e7f6a96ce0431a2dc37689ae883cd85d66bc6ae1fdd2489fdf31ecdc3ab7114",
    ("faults:f4", "train"): "9bae7a10009c916ad5866d91753c99d433d5e1efb706cf7ac18736778884613a",
    (
        "faults:f0+len(f4)",
        "train",
    ): "3ef3805fc65e6a64330ddf6640a1018a0049eb661c14d0aa52e8ef83d9790905",
}


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return list(value)


@pytest.mark.parametrize(("arm_id", "split"), sorted(MAIN))
def test_the_similarity_and_faults_tasks_keep_their_content(arm_id: str, split: str) -> None:
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
