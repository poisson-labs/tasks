"""The built-in generator is frozen: its hash, and the content of every knob's tasks, held in one
place, frozen as a test.

Spec Knobs §12.2 and plan K8: K1 to K8 each edited the generator, and when K8 merges it is
frozen.  Its hash is recorded in the vault's devlog and in the probe's record, and any later
edit to `tasks.py`, `surface.py` or `knobs.py` before the rerun is a ruling; the one the spec
foresees is a redesign after the probe (plan ruling 72), which refreezes the generator and
records the new hash.  The plan gave the freeze no invariant a test holds, and
`calibration_run.EXPECTED_GENERATOR_HASH` moves with every edit by design, so it does not hold
the freeze.  Ruled 2026-10-09 (K8 Session A's yes/no 10): one test file, added by K8 Session B
after the build as its own commit, holding the frozen generator hash as a literal beside every
knob's content digests, so any later change to the built-in generator fails here, in one named
place, with a message saying the generator is frozen and what a deliberate change must update.

Shapes decided here
-------------------

**1. The hash** is the generator hash of a task made at the default generator version, `"1"`,
on the tree this file was committed to (`k8-a` at `af67549`, the build of information spread),
and the driver expects the same one.  A literal: the point of the file is that it does not
follow the source.

**2. Every knob's content digests are the ones the kept files hold**, read from them and not
copied: similarity's and faults' (`tests/test_k4_kept.py`, both splits at the sixty card seeds),
history's (`tests/test_k5_kept.py`), block's (`tests/test_k6_kept.py`), arguments'
(`tests/test_k7_kept.py`), shape's (`tests/test_k8_kept.py`) and spread's
(`tests/test_k8b_kept.py`), the last five eval at the sixty card seeds and train at twelve
(`tests/k4_support.py`), each of every field but `task_id`, `generator_hash` and `pins`.  Depth's
and distractor's tasks are the 840 the published cards measured, held by the frozen
`tests/test_k1_content.py`, whose fixture and regeneration this file reads for the same check.
Each kept file keeps its own test, so a change to one knob's tasks still fails where that knob's
module pinned them; this file is where it also fails as a change to the frozen generator.

**3. What a deliberate change updates**, as every message here says: the literal below,
`calibration_run.EXPECTED_GENERATOR_HASH`, and the content digests of every knob whose tasks
the change moves, in the kept file that holds them.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

import pytest

from poisson_tasks import calibration_run as run
from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import generate
from tests import test_k1_content as published
from tests import (
    test_k4_kept,
    test_k5_kept,
    test_k6_kept,
    test_k7_kept,
    test_k8_kept,
    test_k8b_kept,
)
from tests.k3_support import CARD_SEEDS, made
from tests.k4_support import SPLITS

# The frozen generator: the hash of version "1" over tasks.py, surface.py and knobs.py as K8 left
# them, 2026-10-09.
FROZEN_GENERATOR_HASH = "b460964dc153fab4535af3b39abd41d50198f3dcc644ae3e43ddee85544b57f9"

MOVES = {"task_id", "generator_hash", "pins"}
BOTH_AT_CARD_SEEDS = {"eval": CARD_SEEDS, "train": CARD_SEEDS}
# Each knob's digests as the file that pinned them holds them, with the seeds they were taken at.
KEPT: tuple[tuple[str, dict[tuple[str, str], str], dict[str, tuple[int, ...]]], ...] = (
    ("similarity and faults", test_k4_kept.MAIN, BOTH_AT_CARD_SEEDS),
    ("history", test_k5_kept.MAIN, dict(SPLITS)),
    ("block", test_k6_kept.MAIN, dict(SPLITS)),
    ("arguments", test_k7_kept.MAIN, dict(SPLITS)),
    ("shape", test_k8_kept.MAIN, dict(SPLITS)),
    ("spread", test_k8b_kept.MAIN, dict(SPLITS)),
)
DIGESTS: dict[tuple[str, str], tuple[str, tuple[int, ...]]] = {
    (arm_id, split): (digest, seeds[split])
    for _knob, main, seeds in KEPT
    for (arm_id, split), digest in main.items()
}


def frozen(what: str) -> str:
    """The one message: what moved, that the generator is frozen, and what a deliberate change
    must update."""
    return (
        f"{what}: the built-in generator is frozen at {FROZEN_GENERATOR_HASH} (K8, 2026-10-09; "
        "spec Knobs §12.2).  A change to tasks.py, surface.py or knobs.py is a ruling, and a "
        "deliberate one updates FROZEN_GENERATOR_HASH in tests/test_frozen_generator.py, "
        "calibration_run.EXPECTED_GENERATOR_HASH, and the content digests of every knob whose "
        "tasks it moves, in the kept file that holds them (tests/test_k4_kept.py to "
        "tests/test_k8b_kept.py; the 840 published tasks in tests/test_k1_content.py)."
    )


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return list(value)


def content_digest(arm_id: str, split: str, seeds: tuple[int, ...]) -> str:
    """The kept files' digest: every field but the three that move, per task, one line each."""
    digest = hashlib.sha256()
    for seed in seeds:
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
    return digest.hexdigest()


def test_the_generator_is_the_frozen_one_and_the_driver_expects_it() -> None:
    """Shape 1."""
    bundle = generate(arm_from_id("distractor:r0@k16"), CARD_SEEDS[0])
    assert bundle.generator_hash == FROZEN_GENERATOR_HASH, frozen(
        f"the generator hash is {bundle.generator_hash}"
    )
    assert run.EXPECTED_GENERATOR_HASH == FROZEN_GENERATOR_HASH, frozen(
        f"the driver expects the generator {run.EXPECTED_GENERATOR_HASH}"
    )


def test_every_knob_with_kept_digests_is_read_here() -> None:
    """Shape 2: the seven knobs whose tasks the kept files pin, each at every card level."""
    knobs = {arm_id.partition(":")[0] for arm_id, _split in DIGESTS}
    assert knobs == {"similarity", "faults", "history", "block", "arguments", "shape", "spread"}
    assert all(split in {"eval", "train"} for _arm, split in DIGESTS)


@pytest.mark.parametrize(("arm_id", "split"), sorted(DIGESTS))
def test_every_knobs_tasks_keep_their_content(arm_id: str, split: str) -> None:
    """Shape 2."""
    want, seeds = DIGESTS[(arm_id, split)]
    got = content_digest(arm_id, split, seeds)
    assert got == want, frozen(f"the {arm_id} tasks on the {split} split moved ({got})")


def test_the_840_published_tasks_keep_their_content() -> None:
    """Shape 2, depth and distractor: the published cards' tasks, as `tests/test_k1_content.py`
    compares them, through its fixture and its regeneration."""
    differences = []
    for entry in published.fixture()["tasks"]:
        new = published.as_stored(published.regenerated()[(entry["arm_id"], entry["seed"])])
        old = entry["bundle"]
        moved = [name for name in old if name not in published.MOVING and new[name] != old[name]]
        if moved:
            differences.append((entry["arm_id"], entry["seed"], moved))
    assert not differences, frozen(f"{len(differences)} published tasks moved: {differences[:5]}")
