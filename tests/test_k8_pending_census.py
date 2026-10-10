"""Pending a yes/no: the census of an information-spread arm, and the named reads masked in its
fingerprint.

Spec §14.4 does not say what `structure_space` counts for spread, nor whether the fingerprint reads
the named reads (the frozen tests only require that the census takes every spread arm).  If the
answer is yes, the fingerprint masks the slot that names the four reads whole, as it masks the
goal lines of a shape task (ruled 2026-10-09), so replacing every slot that names a read's page by
another task's moves nothing, whatever the slots are called: their pages are opaque keys, as a seeded read's
page is, and which facet and item each names is a draw of the task's and not its structure; the
parts are in the answers, which no first request holds.  Then the count is B's at every level:
the target ledger times every order of the sixteen slots.  Dropped if the answer is no: the count
and whether the fingerprint reads the named reads are then the build's.
"""

from __future__ import annotations

import dataclasses

import pytest

from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import structural_fingerprint, structure_space
from tests.k8_support import ARMS, CARD_SEEDS, PAGE, named, spread


@pytest.mark.parametrize("text", ARMS)
def test_the_census_of_a_spread_arm_is_bs(text: str) -> None:
    assert structure_space(arm_from_id(text)) == structure_space(arm_from_id("distractor:r0@k16"))


def test_the_fingerprint_masks_the_named_reads_whole() -> None:
    for seed, other in zip(CARD_SEEDS[:12], CARD_SEEDS[12:24], strict=True):
        for level in (1, 4):
            bundle = spread(level, seed)
            pages = [args[PAGE] for _name, args in named(bundle)]
            slots = {name for name, value in bundle.prompt_slots if any(p in value for p in pages)}
            assert slots, (level, seed)
            elsewhere = dict(spread(level, other).prompt_slots)
            moved = dataclasses.replace(
                bundle,
                prompt_slots=tuple(
                    (name, elsewhere[name] if name in slots else value)
                    for name, value in bundle.prompt_slots
                ),
            )
            assert moved.prompt_slots != bundle.prompt_slots, (level, seed)
            assert structural_fingerprint(moved) == structural_fingerprint(bundle), (level, seed)
