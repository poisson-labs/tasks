"""What K7 leaves alone: the argument-difficulty knob's tasks keep their content, frozen as a test.

Plan Knobs §2, as the session prompt states it for K7: the 840 published tasks keep their content
(frozen `tests/test_k1_content.py`), and so do the similarity, faults, history, block and arguments
tasks the knob modules before this one built.  Similarity's and faults' are held by the frozen
`tests/test_k4_kept.py`, history's by the frozen `tests/test_k5_kept.py`, block's by the frozen
`tests/test_k6_kept.py`.  Nothing held arguments': K6's tests pin its structure (the eight
parameters, the stated values, the check, the request's form), not its content, and K6 Session B
found two changes that move every arguments task, the six parameter names in another order and the
values' domain respelled, which no frozen test sees (its mutation rows X6 and X7).  Ruled
2026-10-08, in K7 Session A's prompt: K7 Session A pins arguments' content with digests, the way K6
Session A pinned block's, in a file and a commit of their own.

The digests are of every field but `task_id`, `generator_hash` and `pins`, which move with any edit
to the generator's modules (K-P6's rule, as in `tests/test_k1_content.py`), per arm and split, at
every card level and the control, at every card seed on the eval split and the first twelve on
train (`tests/k4_support.py`).  Computed on `main` at `1c618ad` (K6 merged) before any K7 edit.
It passes on that tree by design.
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
    ("arguments:a2", "eval"): "dd6bf751cdf9c4028d918ba7eb6db9db140cdf4b0e4f55f39380ed9ef7561888",
    ("arguments:a2", "train"): "e378fd4a0922ce83042f65857f45dfcd30cd9577021ce4b506733cd0605b6a22",
    ("arguments:a4", "eval"): "a2e48796d8f006c39f9104b109b2023ad9e3273c7b4cff0fc0962d35e4720f44",
    ("arguments:a4", "train"): "833d2166257097509618d4d714600ab586cfe80c5862f82b2ab186bb9e8b9b85",
    ("arguments:a6", "eval"): "d1bf57c98ce48e6066e95b4763563a3ea696828e3702fdb60a36e47ec4e4545b",
    ("arguments:a6", "train"): "726dcab3b7ef81233985582bffa81fc19626cab9c6a9c275d3a9721d7e4872d6",
    ("arguments:a8", "eval"): "03cfd7e7e3de652cae4330f9647e4bfb1efa2723db902e409b0c8bae2d41ef46",
    ("arguments:a8", "train"): "48a4debb3d6a0ad1c4a8039e884741d294b6cbccab976762c72757c4f09403d2",
    ("arguments:a2+len(a8)", "eval"): (
        "4f277eccfc0b80272ff48b0d6a26cbc2cbd63c9fdca4261fe3f2498f6ce985bc"
    ),
    ("arguments:a2+len(a8)", "train"): (
        "03776cc04c38f89a5040ae3807bf2ef1b7f9fd6d356aee7347330bc7c1ed36fc"
    ),
}
SEEDS = dict(SPLITS)


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return list(value)


@pytest.mark.parametrize(("arm_id", "split"), sorted(MAIN))
def test_the_arguments_tasks_keep_their_content(arm_id: str, split: str) -> None:
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
