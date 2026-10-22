"""What each task-shape width asks of the reference: four stage calls and a reply, arranged by the
width, frozen as tests.

Every width's reference makes four stage
calls and a reply (N33); `w1` advances the target record through four stages, a chain; `w2`
advances the target and the decoy record, which the scenario already holds in the target ledger,
two stages each; `w4` advances the target record's id one stage in four ledgers, the scenario
already holding it in every ledger, the three besides the target ledger drawn from `(seed, split)`
in a domain of their own, never from the scenario's draw.

Shapes decided here
-------------------

**1. The calls** are read from the bundle: every reference call is a stage tool's (no read), four
of them, each answered `ok`, and the observations are the engine's own answers to the calls in
order from `seq_start`; each target's calls are its ledger's stage tools from the first stage up
to its goal, each once, in stage order, on that record, the first with the scenario's entry code
and each later one with the token the call before it on that record returned.  The control, which
stands in for `w4`'s length, makes `w1`'s calls.

**2. The targets** are the records whose stage differs between the initial and the expected
records.  `w1`: the target record (the seed's own id) in the target ledger (the
scenario's), at stage 4.  `w2`: that record and the scenario's decoy record, in the target ledger,
at stage 2.  `w4`: the target record at stage 1 in the target ledger and in three others.  The
goal is the first target, the target record in the target ledger, at its stage.

**3. "Drawn from `(seed, split)`, a domain of their own"** is read, as the arguments knob's draw
was, as what it excludes: the three other ledgers are three different ledgers none the target's;
none is one of the three at more than half the card seeds of a split; they are not a function of the
target ledger (two seeds with the same target ledger draw different ones); the split is read by the
draw itself (at the card seeds whose two splits draw the same target ledger, the three differ at
some);  and they are not drawn from the similarity knob's domain (at some seed they are not among
the six lookalike ledgers similarity draws for the same task, read through its block and the display
map).  Their order is not pinned here.  "Never from the scenario's draw" is pinned only as far as
"not a function of the target ledger": a draw from the scenario's slot order is not told apart.

**4. G1**: `w4` and the control are the same task in another process, under two hash seeds.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections import Counter
from typing import Any

from poisson_tasks import surface
from poisson_tasks.engine import replay
from poisson_tasks.tasks import scenario_for
from tests.k3_support import CARD_SEEDS, SPEC, made, names, status
from tests.k7_support import (
    ARMS,
    CALLS,
    SPLITS,
    base,
    entry_code,
    ledger_of,
    records,
    shape,
    stage_of,
    targets,
    width_of,
)

RECORD = SPEC.parameter_names["record"]
ENTRY = SPEC.parameter_names["entry"]
TOKEN = SPEC.parameter_names["token"]


def expected_targets(bundle: Any, width: int) -> dict[tuple[str, str], int] | None:
    """The targets the design names for `width`; `None` for `w4`, whose other ledgers are drawn."""
    ledger, target, _stage = bundle.goal
    _target, decoy = records(bundle)
    if width == 1:
        return {(ledger, target): 4}
    if width == 2:
        return {(ledger, target): 2, (ledger, decoy): 2}
    return None


def test_every_width_makes_four_stage_calls_on_its_targets_and_a_reply() -> None:
    """Shapes 1 and 2."""
    for split, seeds in SPLITS:
        for seed in seeds:
            b = base(seed, split)
            for arm_id in ARMS:
                bundle = made(arm_id, seed, split)
                where = (arm_id, seed, split)
                calls = bundle.reference_calls
                assert len(calls) == CALLS, where
                assert all(name in SPEC.stage_tools for name, _args in calls), where
                assert [status(o) for o in bundle.reference_observations] == ["ok"] * CALLS, where
                _final, observed = replay(scenario_for(seed, split), list(calls), bundle.seq_start)
                assert tuple(observed) == tuple(bundle.reference_observations), where

                found = targets(bundle)
                ledger, target, stage = bundle.goal
                assert (ledger, target) == (b.goal[0], b.goal[1]), where
                assert found[(ledger, target)] == stage, where
                wanted = expected_targets(bundle, width_of(arm_id))
                if wanted is not None:
                    assert found == wanted, where
                else:
                    assert set(found.values()) == {1}, where
                    assert {record for _ledger, record in found} == {target}, where
                    assert len({ledger for ledger, _record in found}) == 4, where

                # Each target's calls: its ledger's stage tools from the first up, once each, the
                # first with the entry code and each later one with the token the one before it
                # on that record returned.
                reached: dict[tuple[str, str], tuple[int, str]] = {}
                for (name, args), observation in zip(
                    calls, bundle.reference_observations, strict=True
                ):
                    key = (ledger_of(name), str(args[RECORD]))
                    assert key in found, (name, args, *where)
                    before = reached.get(key)
                    if before is None:
                        assert stage_of(name) == 1, where
                        assert args == {RECORD: key[1], ENTRY: entry_code(bundle)}, where
                    else:
                        assert stage_of(name) == before[0] + 1, where
                        assert args == {RECORD: key[1], TOKEN: before[1]}, where
                    reached[key] = (stage_of(name), observation.split()[2])
                assert {key: done[0] for key, done in reached.items()} == found, where


def other_ledgers(seed: int, split: str) -> tuple[str, ...]:
    bundle = shape(4, seed, split)
    return tuple(sorted(ledger for ledger, _r in targets(bundle) if ledger != bundle.goal[0]))


def similarity_ledgers(seed: int, split: str) -> set[str]:
    """The six lookalike ledgers the similarity knob draws for the same task: the ledgers of the
    stage tools its block holds besides the target ledger's."""
    bundle = made("similarity:s0", seed, split)
    shown = surface.display_map(seed, split, bundle.arm_id, bundle.goal, names(bundle))
    engines = {entry.engine for entry in shown.values() if entry.engine in SPEC.stage_tools}
    return {ledger_of(name) for name in engines} - {bundle.goal[0]}


def test_w4s_three_other_ledgers_are_drawn_from_the_seed_and_the_split() -> None:
    """Shape 3."""
    for split, seeds in SPLITS:
        seen: Counter[str] = Counter()
        by_target: dict[str, set[tuple[str, ...]]] = {}
        unlike_similarity = False
        for seed in seeds:
            others = other_ledgers(seed, split)
            target = shape(4, seed, split).goal[0]
            assert len(set(others)) == 3 and target not in others, (seed, split)
            seen.update(others)
            by_target.setdefault(target, set()).add(others)
            unlike_similarity |= not set(others) <= similarity_ledgers(seed, split)
        assert max(seen.values()) <= len(seeds) // 2, (split, seen)
        assert any(len(drawn) > 1 for drawn in by_target.values()), split
        assert unlike_similarity, split
    # The split is read by the draw itself, not only through the target ledger: at the card seeds
    # whose two splits draw the same target ledger, the other three differ at some.
    alike = [
        seed
        for seed in CARD_SEEDS
        if shape(4, seed, "eval").goal[0] == shape(4, seed, "train").goal[0]
    ]
    assert alike
    assert any(other_ledgers(seed, "eval") != other_ledgers(seed, "train") for seed in alike)


PROBE = """
import sys
from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import generate
for text in ("shape:w4", "shape:w1+len(w4)"):
    for split in ("eval", "train"):
        for seed in (int(s) for s in sys.argv[1:]):
            print(text, split, seed, generate(arm_from_id(text, split=split), seed).task_id)
"""


def test_a_shape_task_is_the_same_in_another_process_under_another_hash_seed() -> None:
    """Shape 4."""
    seeds = [str(seed) for seed in CARD_SEEDS[:3]]
    outputs = []
    for hash_seed in ("0", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        done = subprocess.run(
            [sys.executable, "-c", PROBE, *seeds],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.append(done.stdout)
    assert outputs[0] == outputs[1]
    for line in outputs[0].splitlines():
        text, split, seed, task_id = line.split()
        assert made(text, int(seed), split).task_id == task_id, line
