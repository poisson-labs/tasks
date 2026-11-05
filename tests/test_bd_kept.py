"""The 0.4.0 stale-data knobs' tasks keep their content, frozen as a test.

As the knobs' design states it for every knob built since the freeze: the 840 published tasks keep
their content (frozen `tests/test_k1_content.py`), and so do the tasks of the knobs built after them
(`tests/test_k4_kept.py` to `tests/test_k8b_kept.py`, `tests/test_f2_kept.py`).  Nothing held the two
knobs of 0.4.0: the frozen `tests/test_bd_*.py` tests pin their structure (one request at every
level, the answers' three parts, the sequence, the carrier and showing rules, the one lagging read)
and not their content, and a later change to a draw, a sentence's bytes, a fill's count or the own
generator's pair draw would pass every one of them.  So the build pins their content with digests,
the way every knob's build did, in a file of its own, read by `tests/test_frozen_generator.py` for
the built-in half (the 0.4.0 stale-data spec, BD.9).

**The built-in half**, `MAIN`: the `baddata` arms, every level, at the card seeds on both splits
(the sixty published seeds on eval and twelve on train, `tests/k4_support.py`'s, as the K-sessions'
kept files take them), keyed `(arm_id, split)`, of every field but `task_id`, `generator_hash` and
`pins`, which move with any edit to the generator's modules.  `baddata` has no control arm, and
`lagged` has no built-in tasks (ruled, Q5 and Q7 of the stale-data spec), so neither has a digest
here.

**The own-tools half**, `OWN`: every arm of the two knobs each fixture set reaches (the acme sets
with their flows), at the seeds 404, 55 and 2121 on the eval split, strict, keyed `(set, arm_id)` as
`tests/test_o2b_kept.py`'s digests are, of every field but `task_id` and `generator_hash`.

Computed on the build, branch `bd-build`, at the two hashes `tests/test_frozen_generator.py` and
`tests/test_o2b_kept.py` hold.  It passes on that tree by design; a change that moves any of these
tasks fails here.  What a deliberate change updates: the digests of the arms whose tasks moved, and
the two hashes in their records.

This file imports nothing from `tests/test_frozen_generator.py`: that file reads this one by name,
and an import back would be a circle that stops whichever shard collects them together.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

import pytest

from poisson_tasks.knobs import arm_id
from tests.k3_support import made
from tests.k4_support import SPLITS
from tests.o2_support import every_arm, fixture_sets, flows_for, generator

MOVES = {"task_id", "generator_hash", "pins"}
OWN_MOVES = {"task_id", "generator_hash"}
OWN_SEEDS = (404, 55, 2121)
NEW = ("baddata", "lagged")

# 8 rows: baddata, the four levels, on both splits.
MAIN = {
    ("baddata:b0", "eval"): "29584910a3a59736c1bfa747acbd35d9725fd508190e54fd0c7994234bdf5619",
    ("baddata:b0", "train"): "a60af83a557d9b50952c3f82e8d464321aa9c31f8f8b78b28bfae99f5bdcf32b",
    ("baddata:b1", "eval"): "df9a5862cc093ef912577b7a17210bf78dfef1340891e5fae4652234a21d9789",
    ("baddata:b1", "train"): "6fcf5e308827fe21bcd9061bad3896e48dbf05970b7d15149ed45667ecf06693",
    ("baddata:b2", "eval"): "05c55d551de0fe830c627e250fa19f30da06781fcf32c25f787f68560cf53cdc",
    ("baddata:b2", "train"): "98c58e76d06513925543ceaf94957444a5c72f7540a5fb8f5bfedee9debef2de",
    ("baddata:b3", "eval"): "033a5efc5d0d7a8bf6846b680f74a5391441fca2c68f61dbd4ff54af769664e7",
    ("baddata:b3", "train"): "9621eec8bca268397cc20e6a812e7b34d8e612ce1b4e42825d4640306a313045",
}

# 27 rows: every arm of the two knobs each fixture set reaches.
OWN = {
    ("acme-mcp", "baddata:b0"): "d9bd5dc8ed4465e043c6c187e4ca67579edea580dc4b7c918eb8c38e47819f04",
    ("acme-mcp", "baddata:b1"): "a11b9db05fe86e732fcd60ecc32d0b2fc2cf35d18ae8b271aec1c975fb44f57c",
    ("acme-mcp", "baddata:b2"): "622ede95f1be30906b3c132b662d5604af22cadcfae128902cf3cd4b8310d9f8",
    ("acme-mcp", "baddata:b3"): "f7628f54b71299a3be8633294848d208af245cd3304ed0f26bbc65553f6a7ff0",
    ("acme-openai", "baddata:b0"): "e5adecb6ea54396a3d43072a1b237d141a4bc3bfecd0ea05065450cfd75d326b",
    ("acme-openai", "baddata:b1"): "525d3530ddc525a8d6562f5d6594bc0a732336ed204410f37472790e129a503d",
    ("acme-openai", "baddata:b2"): "67f6036dd5f0f8b1041383086cf49ea7caed257a1dc9fef4cfeeb20b1f2a2391",
    ("acme-openai", "baddata:b3"): "89522806186a06ead88e3f55b30cd9a654953bb3071cf105d9e86cbda709f2ef",
    ("acme-openai", "lagged:g0"): "e3f63b4f0ace1fd399a7a95d5fbe16c1507209c77aeed3ac311747a0c2de0f82",
    ("acme-openai", "lagged:g1"): "da24ed9db3137ae375b02c51a83dfcf77e01ef26b3b5704b8456e5b74812f111",
    ("acme-openapi-3.0", "baddata:b0"): "78d2c2bb72677510bc349d9fda1f18fed204748c13177c276c8ec2f1353b92d5",
    ("acme-openapi-3.0", "baddata:b1"): "d5bc9d66cfc7ea800d7a913d1847683c2b513792d5f9a5720e5a478bebeade93",
    ("acme-openapi-3.0", "baddata:b2"): "5f1a9d22d89fa2961e2b9968d982f3a5455ed2b51de146a755df4e29713d73de",
    ("acme-openapi-3.0", "baddata:b3"): "609ca5baacce4338ab10f54a0677d1540bbd72d1aa7e5f0f3ba119b59e42755f",
    ("acme-openapi-3.1", "baddata:b0"): "b2189c048f86735cc0091bd1797f953c6694b691a5b52a895fc345b9dfaad97c",
    ("acme-openapi-3.1", "baddata:b1"): "76cb608647ae9a5647ab48e789f0f2c0ca0325d3865752e325c66f4cc5309112",
    ("acme-openapi-3.1", "baddata:b2"): "d84fd0eff119255d4f9ff8917e620ec94d0c3742253f79a07c9c86957a995ac5",
    ("acme-openapi-3.1", "baddata:b3"): "39dd71dc3cd0588208dc80e0a196b65c0c8c5ceb40a212ebeadd8134d7e577ed",
    ("petstore", "baddata:b0"): "582762d5fc2aae4e8f09d7d1d0854fefe481566ce855cef8a1f11aa9dbcb858d",
    ("petstore", "baddata:b2"): "b156b00919d5e55e309ab13182c8f6ca1f09bbed31bbaa20c7fa2a69803a2647",
    ("petstore", "baddata:b3"): "f8b3b357bb03966239ac2e2f3a5a252406429ef209230c2522418f712a081369",
    ("petstore", "lagged:g0"): "b09e481a70b00a69124f16d26fe8d9956e77eb9fc412d2cc2f88b68dd2f25cd7",
    ("petstore", "lagged:g1"): "63cd910beb5e3b8d0d1dffafcd42f37c811a01c4598d78641a1cde8b6023c61a",
    ("everything", "baddata:b0"): "57d015d138820080f643fee95f9d68b1121ef82a0f9578f82738607c50fc8c6f",
    ("everything", "baddata:b1"): "4c2f3296492c469842384a8cd3d6a753f8e227c5c74f461aec5f121c6099ff65",
    ("everything", "baddata:b2"): "f25639fc38b5b81bcac9883b223ae7b904dd5566df38e408027d52ec57e79fc3",
    ("everything", "baddata:b3"): "de1cdd6d6a05d98eb8f4efaf64fad5eafabaaef78b31c6b04b33d312e3e557d1",
}


def plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return list(value)


def digest_of(bundles: Any, moves: set[str]) -> str:
    digest = hashlib.sha256()
    for bundle in bundles:
        content = {
            field.name: getattr(bundle, field.name)
            for field in dataclasses.fields(bundle)
            if field.name not in moves
        }
        digest.update(
            json.dumps(content, sort_keys=True, separators=(",", ":"), default=plain).encode()
        )
        digest.update(b"\n")
    return digest.hexdigest()


def test_the_built_in_half_holds_every_level_of_baddata_on_both_splits() -> None:
    assert set(MAIN) == {
        (f"baddata:b{level}", split) for level in (0, 1, 2, 3) for split, _seeds in SPLITS
    }


@pytest.mark.parametrize(("arm", "split"), sorted(MAIN))
def test_the_baddata_tasks_keep_their_content(arm: str, split: str) -> None:
    seeds = dict(SPLITS)[split]
    assert digest_of((made(arm, seed, split) for seed in seeds), MOVES) == MAIN[(arm, split)], (
        f"the {arm} tasks on the {split} split moved: a deliberate change updates this digest"
    )


def test_the_own_half_holds_every_arm_of_the_two_knobs_each_set_reaches() -> None:
    expected = {
        (label, arm_id(spec))
        for label, toolset in fixture_sets().items()
        for spec in every_arm(toolset, flows_for(label))
        if spec.knob in NEW
    }
    assert set(OWN) == expected


@pytest.mark.parametrize(("label", "arm"), sorted(OWN))
def test_the_own_tools_tasks_of_the_two_knobs_keep_their_content(label: str, arm: str) -> None:
    toolset, flows = fixture_sets()[label], flows_for(label)
    (spec,) = [s for s in every_arm(toolset, flows) if arm_id(s) == arm]
    bundles = (generator().generate(toolset, spec, seed, flows=flows) for seed in OWN_SEEDS)
    assert digest_of(bundles, OWN_MOVES) == OWN[(label, arm)], (
        f"the own-tools tasks of {label} {arm} moved: a deliberate change updates this digest"
    )
