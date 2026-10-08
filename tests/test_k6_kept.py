"""What K6 leaves alone: the block-size knob's tasks keep their content, frozen as a test.

Plan Knobs §2, as the session prompt states it for K6: the 840 published tasks keep their content
(frozen `tests/test_k1_content.py`), and so do the similarity, faults, history and block tasks the
knob modules before this one built.  Similarity's and faults' are held by the frozen
`tests/test_k4_kept.py`, history's by the frozen `tests/test_k5_kept.py`.  Nothing held block's:
K5's tests pin its structure (the first eight slots, the reads before the copies, the copies'
names and answers, the census), not its content, and K5 Session B found two changes that move every
block task, the copies listed in another order before the draw and the order's domain respelled,
which no frozen test sees (its yes/no 3).  Ruled 2026-10-08, in K6 Session A's prompt: K6 Session
A pins block's content with digests, the way K5 Session A pinned history's, in a file and a commit of
their own.

The digests are of every field but `task_id`, `generator_hash` and `pins`, which move with any edit
to the generator's modules (K-P6's rule, as in `tests/test_k1_content.py`), per arm and split, at
every card level and the control, at every card seed on the eval split and the first twelve on
train (`tests/k4_support.py`).  Computed on `main` at `044ecfa` (K5 merged) before any K6 edit.
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
    ("block:k8", "eval"): "ee245c7baea814319429602bd0987c8141f4acd81b84ba767dfbd93c710758fa",
    ("block:k8", "train"): "e1aa7a52cb345e45b079daf0804fa1931d3e6231cdef24ab2a0d4a02aa90ae96",
    ("block:k16", "eval"): "c5e0385c79b5fa481ecfcf9510b8a31320cdf22dd570bac33fd66fd97579cbfa",
    ("block:k16", "train"): "18b6c3d20df06449558c1b3a7b38027b08963d8a0b39578ddcf1d716ed1b706c",
    ("block:k32", "eval"): "2628a460b3b1f233cddffa055b38bb29ee2a85509dce7492d8013a772903d06d",
    ("block:k32", "train"): "f6ff754f132af2ba8297e9549e6b14e3271e6dd4c11803f11457c6ec62e74506",
    ("block:k64", "eval"): "1296e589f40535e34f84e8d0aee071efea388827c63d877b5cbd28557c32672b",
    ("block:k64", "train"): "0114979c120cdc5e621a310dae7044f00b968c777cef6ba7b7ecc7ecdd8d6fe2",
    ("block:k8+len(k64)", "eval"): (
        "699568a30dce081084325258c28179d3c7fa93c3a9f1f6e2061d8016f264b8a2"
    ),
    ("block:k8+len(k64)", "train"): (
        "391d80c43cd6a3546acfe898fd31c8b4c58273317196f9fc630cc64164efe5cd"
    ),
}
SEEDS = dict(SPLITS)


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return list(value)


@pytest.mark.parametrize(("arm_id", "split"), sorted(MAIN))
def test_the_block_tasks_keep_their_content(arm_id: str, split: str) -> None:
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
