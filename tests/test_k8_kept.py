"""What K8 leaves alone: the task-shape knob's tasks keep their content, frozen as a test.

Plan Knobs §2, as the session prompt states it for K8: the 840 published tasks keep their content
(frozen `tests/test_k1_content.py`), and so do the similarity, faults, history, block, arguments and
shape tasks the knob modules before this one built.  Similarity's and faults' are held by the
frozen `tests/test_k4_kept.py`, history's by the frozen `tests/test_k5_kept.py`, block's by the
frozen `tests/test_k6_kept.py`, arguments' by the frozen `tests/test_k7_kept.py`.  Nothing held
shape's: K7's tests pin its structure (four stage calls, the targets, the block's stage tools, the
goal lines, the verdict), not its content, and K7 Session B found four of its build's choices that
move shape tasks and that no frozen test sees: which two of B's reads give way to the extra stage
tools (every `w1`, `w4` and control task), where the drawn ledgers' tools sit at `w4` (every `w4`
task), the order the three other ledgers are drawn in (every `w4` task), and the order of the
prompt slots (every shape task's id; its mutation rows S2 to S5).  Ruled 2026-10-09, in K8
Session A's prompt: K8 Session A pins shape's content with digests, the way K7 Session A pinned
arguments', in a file and a commit of their own.

The digests are of every field but `task_id`, `generator_hash` and `pins`, which move with any edit
to the generator's modules (K-P6's rule, as in `tests/test_k1_content.py`), per arm and split, at
every width and the control, at every card seed on the eval split and the first twelve on train
(`tests/k4_support.py`).  Computed on `main` at `583f712` (K7 merged) before any K8 edit.  It
passes on that tree by design.
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
    ("shape:w1", "eval"): "279193dc8f765cb938f885a12dc871e0f8da4f0970c0b1e43dc2ad23936e26ec",
    ("shape:w1", "train"): "29c833e5011eb33e5e34be24fc5c3d72171089534a494552b22e003b7425d3d7",
    ("shape:w2", "eval"): "31f6c0a56fddd2adca208cb31e461347a4b3fa3909a48c3e59b7b475694a0c85",
    ("shape:w2", "train"): "264e54a71306b695ecc75f83e10264a625e163f568cec45d650f088e3e5b343f",
    ("shape:w4", "eval"): "bd9235f91f51d97ffd4f83a5df2eaac89d0c904b5160378bdeff003f3b82f2f9",
    ("shape:w4", "train"): "599e074ff84dc4567317e56fd205c2b3708d3f1234568b5f4e413511dca27365",
    ("shape:w1+len(w4)", "eval"): (
        "417a6fcc25e4ecc66953b642631945d26977acebb16db9098d0f655f27a3d9c1"
    ),
    ("shape:w1+len(w4)", "train"): (
        "db275933568b3004da0936322e2323ae737b323dcfb753f73543ba670de153c6"
    ),
}
SEEDS = dict(SPLITS)


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return list(value)


@pytest.mark.parametrize(("arm_id", "split"), sorted(MAIN))
def test_the_shape_tasks_keep_their_content(arm_id: str, split: str) -> None:
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
