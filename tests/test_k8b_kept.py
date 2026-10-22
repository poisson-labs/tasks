"""The information-spread knob's tasks keep their content, frozen as a test.

As the knobs' design states it for the spread knob's build: the 840 published tasks keep
their content (frozen `tests/test_k1_content.py`), and so do the similarity, faults, history,
block, arguments and shape tasks (`tests/test_k4_kept.py` to `tests/test_k8_kept.py`).  Nothing
held spread's: the frozen `test_k8_*` tests pin its structure (four named reads of the base block's
fourteen, the parts in the first reads listed, one fill per read, the reference's order, the
server's and the replay's answers), not its content, and its mutation pass found three choices
of the build that move every spread task and pass every frozen test, because which reads and
fills a task draws could not be pinned before the build existed: the spelling of the domain the
reads are drawn under, the spelling of the domain the fill is keyed under, and the order of the
draw (three rows of its mutation pass).  Decided 2026-10-09: the spread knob's build pins spread's
content with digests, the way its frozen tests pinned shape's,
in a file and a commit of their own, once the build is in.

The digests are of every field but `task_id`, `generator_hash` and `pins`, which move with any
edit to the generator's modules (the rule in `tests/test_k1_content.py`), per arm and
split, at every level the generator can build (the card's three and 3 between them), at every
card seed on the eval split and the first twelve on train (`tests/k4_support.py`).  Computed on
the build, `k8-a` at `af67549`, the generator at
`b460964dc153fab4535af3b39abd41d50198f3dcc644ae3e43ddee85544b57f9`.  It passes on that tree by
design; each of the three choices above, made as a deliberate bug, fails it and nothing else.
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
    ("spread:p1", "eval"): "140856100a6fa0e2112de5c0eb2a15f02b1cd5143fbdb4f2d08fc4b9d658fa9f",
    ("spread:p1", "train"): "e4b50421fc165480d6638b8c4861a059da25e4ca5df1a026ca439fb2bdb4fce4",
    ("spread:p2", "eval"): "edf3f502396b1883a059c009f3cdd96bca0a6c1705d5a926942954533ed54f19",
    ("spread:p2", "train"): "e46ccff85326f48047fed7f5b4bc773d5cce53624ed71d2c5187923acdd5d464",
    ("spread:p3", "eval"): "d10f5941f9382968fa955eb59579675d5ede86ff9789664dc59720f1b996f2f2",
    ("spread:p3", "train"): "8967d8499541611354fe28c98ec1596b86353a20ad329d6db1334825fa316cba",
    ("spread:p4", "eval"): "013736ea1f46864ed8154551d51ed457547cb686928db6c8b39bd78ca235cdd3",
    ("spread:p4", "train"): "beaf35cad77bb1e961cb95b20f067582a0732f80c888e95bbca6145cf42e6746",
}
SEEDS = dict(SPLITS)


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return list(value)


@pytest.mark.parametrize(("arm_id", "split"), sorted(MAIN))
def test_the_spread_tasks_keep_their_content(arm_id: str, split: str) -> None:
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
