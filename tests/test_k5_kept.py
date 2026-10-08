"""What K5 leaves alone: the history knob's tasks keep their content, frozen as a test.

Plan Knobs §2, as the session prompt states it for K5: the 840 published tasks keep their content
(frozen `tests/test_k1_content.py`), and so do the similarity, faults and history tasks the knob
modules before this one built.  Similarity's and faults' are held by the frozen
`tests/test_k4_kept.py`, at the digests K4 Session A took.  Nothing held history's: K4's tests pin
its structure (the seeded pairs' kind, their total, their count), not its content, and a change to
a draw or a seeding rule history shares with the block knob, such as the read-pair table or the
order the block's reads are listed in, would pass them.  K4 Session B found no frozen test pinning
history's content across later modules, and none does on `main` at `e39c7fc`.

The digests are of every field but `task_id`, `generator_hash` and `pins`, which move with any edit
to the generator's modules (K-P6's rule, as in `tests/test_k1_content.py`), per arm and split, at
the seeds K4's tests read: every card seed on the eval split and the first twelve on train
(`tests/k4_support.py`).  `history:t0` is left out: it is B in every field but its id and pins
(frozen `tests/test_k4_kind.py`), and B's eval tasks are among the 840.  Computed on `main` at
`e39c7fc` (K4 and the run engine merged) before any K5 edit.  It passes on that tree by design.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

import pytest

from tests.k3_support import made
from tests.k4_support import SPLITS

MOVES = {"task_id", "generator_hash", "pins"}
MAIN = {
    ("history:t300", "eval"): "1e1a814a69c38a22f29c24fb5030d3f2a57049c04921ff1d87923aca9f46bd66",
    ("history:t600", "eval"): "24d97582bee305c965967330b67c9736049e4fa256ab4fee13f54b7e43957421",
    ("history:t1200", "eval"): "0d3a89215a1e36c0ef57554f76e0a32dafd65df9642392106970210daa6ad238",
    ("history:t2400", "eval"): "6669a37f30d8b70b3281cc7f1024fbbe7854dfd762a5febf9f0d7ff37dd3a7b2",
    ("history:t300", "train"): "3db1f54c1c225f6a88078c9a0801fe1baed074e849f314ae7ddb8af592b8d2b3",
    ("history:t600", "train"): "6a61e32a8aa669d50ad38a7637a865701a438c695f2882445566fabfda44a740",
    ("history:t1200", "train"): "bd44b72ebfe997d4e986d9090d7a43c34b922cfba89f97f0c3d393ec5a3bfe3b",
    ("history:t2400", "train"): "076436f21173ebd83b1c26d68911e684aadfa1eb95bc74866a05fecaac5f2237",
}
SEEDS = dict(SPLITS)


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return list(value)


@pytest.mark.parametrize(("arm_id", "split"), sorted(MAIN))
def test_the_history_tasks_keep_their_content(arm_id: str, split: str) -> None:
    digest = hashlib.sha256()
    for seed in SEEDS[split]:
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
