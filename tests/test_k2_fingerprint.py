"""The similarity knob's structural fingerprint and census, frozen as tests.

The invariant is K2.8 of the knobs plan, from spec §5.4 and §5.7: G15's fingerprint masks the
ledger numbers for similarity arms and is unchanged for every other knob, and `structure_space`
counts each level's structures and clears G16's floor at the card's N, 60.

Shapes decided here
-------------------

**1. What the mask keeps.**  Spec §5.4 masks the numbers in the tools' names and descriptions "as
it masks the record id"; spec §5.7 counts "the kept positions" among the structures.  Both hold
only if the digits are masked and **which places each number shares with the target's** is kept,
so a lookalike one digit off in the last place and one off in the first are different structures
(the reference tokenizer splits `4417` as `441` and `7`, so the two read differently, spec §5.3),
while two tasks whose numbers differ but share the same places are one.  The ledger number slot
is opaque, as the record id and the entry code are.  How a masked number is written is the
build's.

**2. Unchanged for every other knob** is pinned as digests: the fingerprints of the published
design's fourteen arms at the card's sixty seeds, taken on `main` before K2 (`6089e79`), one
digest per arm over its sixty fingerprints in seed order.

**3. The census here is the floor.**  Each level's count clears `100 * N**2` at N = 60, and sixty
tasks of a level collide with probability under 0.005, as `test_g16_3` asks of the pilot's arms;
the sixty card tasks of each level are in fact pairwise distinct.  At s0 every lookalike shares
no place, so that distinctness rests on the scenario's draw and the block's composition alone,
both fixed before this knob's own draws; at s1 to s3 the shared places add to it.  The exact
count waits on a yes/no and is pinned in `tests/test_k2_pending_census.py`.
"""

from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks.arms import arm_from_id
from poisson_tasks.knobs import arm_id
from poisson_tasks.tasks import generate, structural_fingerprint, structure_space
from tests.k2_support import (
    CARD_SEEDS,
    LEVELS,
    NUMBER,
    arm,
    names,
    number_of,
    lookalike_slots,
    shared,
    sim,
    target_number,
)

N_CARD = 60
FLOOR = 100 * N_CARD**2

# Shape 2: on `main` 6089e79, before K2.
MAIN_FINGERPRINTS = {
    "depth:d1": "ddcacf19159fe796e58a178cf0a1ea902292caf631ec766c01b441b2e8c95de0",
    "depth:d2": "79e9592ead52a458bdabfb0845659cebf645f231c094d751faf7b9411953f03f",
    "depth:d3": "e799a0a10cb61106bdff4bf3d03a8dff96f346b483b1126a2ac117ce9d3f6cdb",
    "depth:d5": "647abd29a1e35665b64cb8c067f11937b1bc2104b6e3566b2d05ed30aafd6b38",
    "depth:d8": "03d2747b6560006868c53b043c397b80db98e51f8b2e34c872c63ae2561c464e",
    "depth:d1+h8": "f65937a43bd8a0d76b755d24f6b7e21273d2d7cd85def7568ff320da31da58d8",
    "depth:d2+h5": "4fcf825d01618963bbf9a8770a22533890a34239845d7a050705f18f317a672c",
    "distractor:r0@k16": "b4265c47130b6442794bccb4dfc3bf39733c0be7469f947d5573be013c218d7c",
    "distractor:r2@k16": "fdf568c9807f6339f932452f9e57889b7ac60b0dd721a98dfe63c6a5ed5177f6",
    "distractor:r4@k16": "0183ac65f992abdbef9982a016a7b18b36ae0ff2a584037d5985e05e4af09468",
    "distractor:r8@k16": "9d312fb5ed550787fa3c7157535feae6b135256c7e02d91905e45d637dcc855c",
    "distractor:r14@k16": "91790b737b1ce01a2ea49dc3f9a9defb11c4d676f66d5ce1c9ea2778de523f20",
    "distractor:r0+len(r8)@k16": "c512d6403177ab9040426edb5717c5ea7e6f870bb0c6a4fc18e1e2717cd26fdf",
    "distractor:r2+len(r14)@k16": "e51d01d7a7d945fe125db9baa88022938c65ed9ac717b929cb44806bb064e77c",
}


def renumbered(bundle: Any, numbers: dict[str, str]) -> Any:
    """The bundle with each ledger number replaced as `numbers` says, everywhere it appears."""
    def swap(text: str) -> str:
        return NUMBER.sub(lambda m: numbers.get(m.group(0), m.group(0)), text)

    def deep(value: Any) -> Any:
        if isinstance(value, str):
            return swap(value)
        if isinstance(value, dict):
            return {key: deep(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return tuple(deep(item) for item in value)
        return value

    return dataclasses.replace(
        bundle, tools=deep(bundle.tools), prompt=deep(bundle.prompt),
        prompt_slots=deep(bundle.prompt_slots), reference_calls=deep(bundle.reference_calls),
        negative_controls=deep(bundle.negative_controls))


def the_numbers(bundle: Any) -> list[str]:
    out = [target_number(bundle)]
    for slot in lookalike_slots(bundle):
        number = number_of(names(bundle)[slot])
        if number is not None and number not in out:
            out.append(number)
    return out


def same_places(number: str, target: str, new_target: str, step: int) -> str:
    """A number sharing with `new_target` exactly the places `number` shares with `target`.  Each
    changed digit is sent, by its rank among the digits that place could change to, to the digit
    `step` ranks on among the new target's; a bijection per place, so distinct numbers stay
    distinct."""
    out = []
    for place, (digit, kept) in enumerate(zip(number, target, strict=True)):
        if digit == kept:
            out.append(new_target[place])
            continue
        lowest = 1 if place == 0 else 0
        old = [str(d) for d in range(lowest, 10) if str(d) != target[place]]
        new = [str(d) for d in range(lowest, 10) if str(d) != new_target[place]]
        out.append(new[(old.index(digit) + step) % len(new)])
    return "".join(out)


@pytest.mark.parametrize("level", LEVELS)
def test_renumbering_the_ledgers_and_keeping_their_shared_places_moves_no_fingerprint(
    level: int,
) -> None:
    """Shape 1, first half: the digits are opaque.  Every number replaced, the target's too, by
    others sharing the same places with the new target, and the fingerprint does not move.
    The number slot is masked along with them."""
    for seed in CARD_SEEDS[:10]:
        bundle = sim(level, seed)
        numbers = the_numbers(bundle)
        target = numbers[0]
        new_target = str(1000 + (int(target) + 4321) % 9000)
        mapping = {target: new_target}
        for number in numbers[1:]:
            mapping[number] = same_places(number, target, new_target, 3)
        assert len(set(mapping.values())) == len(mapping), mapping
        assert all(shared(mapping[n], new_target) == shared(n, target) for n in numbers[1:])
        other = renumbered(bundle, mapping)
        assert other.tools != bundle.tools and other.prompt_slots != bundle.prompt_slots
        assert structural_fingerprint(other) == structural_fingerprint(bundle), (seed, mapping)


def test_a_lookalike_sharing_other_places_is_another_structure() -> None:
    """Shape 1, second half: which places a lookalike shares is structure.  One lookalike ledger
    given a number at the same distance from the target but sharing other places moves the
    fingerprint; so does the level, at one seed."""
    for seed in CARD_SEEDS[:10]:
        prints = {structural_fingerprint(sim(level, seed)) for level in LEVELS}
        assert len(prints) == len(LEVELS), seed
        bundle = sim(1, seed)
        numbers = the_numbers(bundle)
        target, first = numbers[0], numbers[1]
        place = next(p for p in range(4) if first[p] == target[p])
        other_place = (place + 1) % 4
        moved = list(first)
        moved[place] = next(d for d in "123456789" if d != target[place])
        moved[other_place] = target[other_place]
        candidate = "".join(moved)
        assert shared(candidate, target) == 1 and candidate not in numbers, candidate
        assert candidate[0] != "0"
        other = renumbered(bundle, {first: candidate})
        assert structural_fingerprint(other) != structural_fingerprint(bundle), seed


def test_the_other_knobs_fingerprints_are_the_ones_main_gave() -> None:
    """Shape 2: masking the numbers changes no depth or distractor fingerprint, the depth
    controls' seeded history (whose sequence numbers are digits) included."""
    for spec in cal.arm_specs():
        prints = [structural_fingerprint(generate(spec, seed)) for seed in CARD_SEEDS]
        digest = hashlib.sha256("\n".join(prints).encode()).hexdigest()
        assert digest == MAIN_FINGERPRINTS[arm_id(spec)], arm_id(spec)


@pytest.mark.parametrize("level", LEVELS)
def test_each_level_clears_g16s_floor_at_the_cards_n(level: int) -> None:
    """Shape 3: the census per level, as `test_g16_3` holds the pilot's arms: `k >= 100 * N**2`
    at N = 60, a property of the arm and not of a draw, and sixty tasks of the level collide
    with probability under 0.005; the card's sixty are pairwise distinct structures."""
    spec = arm_from_id(arm(level))
    k = structure_space(spec)
    assert k == structure_space(arm_from_id(arm(level), split="train"))
    assert k >= FLOOR, (level, k)
    assert N_CARD * (N_CARD - 1) / (2 * k) < 0.005, (level, k)
    prints = {structural_fingerprint(sim(level, seed)) for seed in CARD_SEEDS}
    assert len(prints) == len(CARD_SEEDS) == N_CARD
