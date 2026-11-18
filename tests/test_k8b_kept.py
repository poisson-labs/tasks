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

Re-pinned 2026-11-18 for 0.5.0 (the ruled fix to spread's base task, 2026-11-15): an answer that
holds no part has nothing before its full stop where it said `none`, and the request says to leave
it out, so all eight digests moved, level 4's too, whose request carries the new sentence.  Computed
on the 0.5.0 build, the generator at
`98cbd21dc912bed4dbde5398748b832aae4711c2096f0092c296eab77b52eac3`.  With the old sentence put back
every request is the one 0.4.2 made (`tests/test_g4_request.py`), and which reads and fills a task
draws are as they were.
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
    ("spread:p1", "eval"): "4637dddb40055ceebfd9386ef082fc83c1003875c81a05c03d4c58d9c0ce7a1c",
    ("spread:p1", "train"): "f43e4a27838177d021bc22c4be38e494518bfad2493e944539e6858d7f1a2936",
    ("spread:p2", "eval"): "af2fe72aec7746d256d6e4e37838947f61d08d8863ce47d1b83991bafd654f23",
    ("spread:p2", "train"): "902d9a113b51e0b9e68c7301d2b69b5b1c0788881b60f0d26e67ae631d51fb77",
    ("spread:p3", "eval"): "6893d18fb92ed7f391fc15e6867de12f4cd12bc96d216234f5c7cf5ef9f9d4c2",
    ("spread:p3", "train"): "75fbdb9b15788b5cf04d32f55a32d57a080f827bfb08aba4c623120aae09b5d0",
    ("spread:p4", "eval"): "f2d080fab6da59fd7729693667a01333cff82fadb538fd347d012e4c06ac7862",
    ("spread:p4", "train"): "de8d3107469f8837081ec7cb32f2bb261359b227112d83b037689ec30ef98e52",
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
