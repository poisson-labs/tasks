"""K9.1, the seeds: the probe's sixty and phase 1's three, from their own named derivation.

The spec: a new named derivation, `poisson-tasks/knob-probe/seeds/v1`, from the eval split,
skipping any seed in the cards' published sixty; its first three seeds are phase 1's; the next
sixty, sorted, are the probe's.  So no probe task is a card task.  The driver records the seed
list's hash.

Seed `i` is computed here from the derivation string with `hashlib` alone, the shape the cards'
own seeds have (`calibration._derive_seeds`), so the module under test is checked against the
declaration and not against itself.  The same sixty-three are the ones K2 Session A made in
`tests/k2_support.py` and checked the similarity block's length on; equality here is K2.4's check
re-run on the probe's own list, as K2 owed it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import pytest

from poisson_tasks import calibration as cal
from tests.k9_support import REPO

DERIVATION = "poisson-tasks/knob-probe/seeds/v1"


def draws(count: int) -> list[int]:
    """The derivation's first `count` seeds, before anything is skipped."""
    return [
        int.from_bytes(hashlib.sha256(f"{DERIVATION}:{i}".encode()).digest()[:4], "big")
        for i in range(count)
    ]


def test_phase_1s_three_are_the_first_drawn_in_their_order_and_the_probes_sixty_the_next_sorted() -> (
    None
):
    from poisson_tasks import knob_probe as probe

    drawn = draws(63)
    assert not set(drawn) & set(cal.seed_list()), "a raw draw meets a card seed; recount"
    assert len(set(drawn)) == 63
    assert probe.DERIVATION == DERIVATION
    assert probe.PHASE1_SEEDS == tuple(drawn[:3])
    assert probe.PROBE_SEEDS == tuple(sorted(drawn[3:]))
    assert probe.PROBE_SEEDS != tuple(drawn[3:]), "the sixty come out of the derivation unsorted"


def test_the_lists_are_pinned_by_value() -> None:
    """The first three seeds and the probe list's digest as literals: a change to the
    derivation's string, its byte shape or its order shows here first."""
    from poisson_tasks import knob_probe as probe

    assert probe.PHASE1_SEEDS == (1180681854, 601375552, 2652385879)
    assert len(probe.PROBE_SEEDS) == 60 and len(set(probe.PROBE_SEEDS)) == 60
    assert probe.PROBE_SEEDS[:3] == (1914295, 23674784, 124320910)


def test_no_probe_task_is_a_card_task() -> None:
    from poisson_tasks import knob_probe as probe

    assert not set(probe.PROBE_SEEDS) & set(cal.seed_list())
    assert not set(probe.PHASE1_SEEDS) & set(cal.seed_list())
    assert not set(probe.PHASE1_SEEDS) & set(probe.PROBE_SEEDS)


def test_a_card_seed_or_a_repeat_is_skipped_and_the_next_draw_takes_its_place() -> None:
    """The real derivation meets no card seed in its first draws, so the skip is shown on a list
    to skip that holds one of them."""
    from poisson_tasks import knob_probe as probe

    drawn = draws(64)
    phase1, sixty = probe.derive_seeds(skip={drawn[1]})
    assert phase1 == (drawn[0], drawn[2], drawn[3])
    assert sixty == tuple(sorted(drawn[4:64]))
    unskipped = probe.derive_seeds(skip=set())
    assert unskipped == (tuple(drawn[:3]), tuple(sorted(drawn[3:63])))


def test_the_derivation_skips_the_cards_own_sixty_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from poisson_tasks import knob_probe as probe

    first = draws(1)[0]
    monkeypatch.setattr(cal, "_SEEDS", (first, *cal.seed_list()[1:]))  # holds the first draw
    phase1, _ = probe.derive_seeds()
    assert first not in phase1


def test_the_seed_lists_hashes_are_the_cards_digest_of_each_list() -> None:
    from poisson_tasks import knob_probe as probe

    for seeds, digest in (
        (probe.PROBE_SEEDS, probe.PROBE_SEED_LIST_HASH),
        (probe.PHASE1_SEEDS, probe.PHASE1_SEED_LIST_HASH),
    ):
        assert digest == hashlib.sha256(json.dumps(list(seeds)).encode()).hexdigest()


def test_another_process_makes_the_same_lists() -> None:
    code = (
        "from poisson_tasks import knob_probe as p; import json; "
        "print(json.dumps([p.PHASE1_SEEDS, p.PROBE_SEEDS, p.PROBE_SEED_LIST_HASH]))"
    )
    done = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(REPO / "src"), "PYTHONHASHSEED": "7", "PATH": "/usr/bin:/bin"},
        timeout=300,
    )
    assert done.returncode == 0, done.stderr
    from poisson_tasks import knob_probe as probe

    phase1, sixty, digest = json.loads(done.stdout)
    assert (tuple(phase1), tuple(sixty), digest) == (
        probe.PHASE1_SEEDS,
        probe.PROBE_SEEDS,
        probe.PROBE_SEED_LIST_HASH,
    )


def test_k2s_sixty_three_are_the_probes() -> None:
    """K2.4 was checked on `tests/k2_support.py`'s sixty-three; they are the driver's."""
    from poisson_tasks import knob_probe as probe
    from tests.k2_support import PROBE_SEEDS

    assert probe.PHASE1_SEEDS + probe.PROBE_SEEDS == PROBE_SEEDS
