"""Which reads an information-spread request names, and that it states no entry code, frozen as
tests.

The request (`ledger-spread/v1`) names the
same four (facet, item, page) reads at every level, drawn from the block's reads, and does not
state the entry code (N35); the four reads come from their own PRF domain.

Shapes decided here
-------------------

**1. A named read** is a read call the reference makes (the ledger's N35 measures them so): a read
tool the block holds, with exactly two arguments, a catalogue item and a page key the table holds.
"Names four reads, by item, facet and page" is read as: each of the four is named on a line of the
request of its own, a line that carries its facet as a word, its item and its page.  This is this
file's reading, as the shape knob's goal lines were; how a line is worded is pending a decision
(`tests/test_k8_pending_wording.py`), and so is which reads may be drawn
(`tests/test_k8_pending_reads.py`).  At every level, the card's three and the one between them
the generator can build, the template is `ledger-spread/v1`, and exactly four lines of the request
name a catalogue item (no fifth read).  That the four are the same at every level is
`tests/test_k8_fixed.py`'s (the request and the reference equal across levels); a check of its own
here was removed before the freeze, catching nothing that one did not.

**2. The request states no entry code, and says the design's two sentences**: the code is not in
double quotes in it, and it is not a word of it, apart from the words every spread request carries
(the design's own sentence holds "part" and "parts", and `part` is one of the table's entry codes);
the sentences "The entry code is split across the answers of these four reads, in the order
listed: join the parts. An answer that holds no part reads `none`." are in it once, as the design
prints them.

**3. "Drawn from the block's reads, from their own PRF domain"** is read, as the arguments and shape
knobs' draws were, as what it excludes: across the card seeds of a split, each of the four places
takes more than one read tool, more than one item and more than one page; the four are not the
block's first four reads in slot order at every seed (the scenario's slot draw); they are not a
function of the target ledger (two seeds with the same target ledger name different reads); and at
some card seed the two splits name different reads.  Which domain, and the order of the draw, cannot
be pinned before the build exists: they are pinned by the content digests the build adds as its own
commit once the build is in (left to a decision).

**4. G1**: a spread task is the same in another process, under two hash seeds.
"""

from __future__ import annotations

import os
import subprocess
import sys

from tests.k3_support import CARD_SEEDS, SPEC, made
from tests.k8_support import (
    ITEM,
    LEVELS,
    PAGE,
    READS,
    SENTENCE,
    SPLITS,
    TEMPLATE_ID,
    entry_code,
    key,
    lines_naming,
    listed,
    named,
    names,
    request,
    spread,
    words,
)


def template_words() -> set[str]:
    """The words every spread request carries, over the card seeds on both splits."""
    common: set[str] | None = None
    for split, seeds in SPLITS:
        for seed in seeds:
            said = words(request(spread(1, seed, split)))
            common = said if common is None else common & said
    assert common is not None
    return common


def test_every_level_names_the_same_four_reads_of_its_block_and_states_no_code() -> None:
    """Shapes 1 and 2."""
    prose = template_words()
    items = set(SPEC.table["catalogue_items"])
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                where = (level, seed, split)
                text = request(bundle)
                assert bundle.template_id == TEMPLATE_ID, where
                reads = named(bundle)
                assert len(reads) == READS, where
                for name, args in reads:
                    assert name in SPEC.read_tools and name in names(bundle), (name, *where)
                    assert set(args) == {ITEM, PAGE}, (args, *where)
                    assert args[ITEM] in items and args[PAGE] in SPEC.page_keys, (args, *where)
                lines = [lines_naming(bundle, read) for read in reads]
                assert all(len(found) == 1 for found in lines), (lines, *where)
                assert len({found[0] for found in lines}) == READS, (lines, *where)
                items_named = [line for line in text.split("\n") if any(i in line for i in items)]
                assert len(items_named) == READS, where
                code = entry_code(bundle)
                assert f'"{code}"' not in text, where
                assert text.count(SENTENCE) == 1, where
                assert code not in words(text) - prose, where


def test_the_four_reads_are_drawn_from_the_seed_and_the_split() -> None:
    """Shape 3."""
    for split, seeds in SPLITS:
        places: list[dict[str, set[str]]] = [
            {"tool": set(), "item": set(), "page": set()} for _ in range(READS)
        ]
        by_target: dict[str, set[tuple[str, ...]]] = {}
        unlike_slots = False
        for seed in seeds:
            bundle = spread(2, seed, split)
            reads = listed(bundle)
            for place, (name, args) in zip(places, reads, strict=True):
                place["tool"].add(name)
                place["item"].add(args[ITEM])
                place["page"].add(args[PAGE])
            first = [name for name in names(bundle) if name in SPEC.read_tools][:READS]
            unlike_slots |= sorted(name for name, _args in reads) != sorted(first)
            by_target.setdefault(bundle.goal[0], set()).add(tuple(key(read) for read in reads))
        for place in places:
            assert all(len(seen) > 1 for seen in place.values()), (split, place)
        assert unlike_slots, split
        assert any(len(drawn) > 1 for drawn in by_target.values()), split
    assert any(
        listed(spread(2, seed, "eval")) != listed(spread(2, seed, "train")) for seed in CARD_SEEDS
    )


PROBE = """
import sys
from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import generate
for text in ("spread:p2", "spread:p4"):
    for split in ("eval", "train"):
        for seed in (int(s) for s in sys.argv[1:]):
            print(text, split, seed, generate(arm_from_id(text, split=split), seed).task_id)
"""


def test_a_spread_task_is_the_same_in_another_process_under_another_hash_seed() -> None:
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
            check=False,
        )
        assert done.returncode == 0, done.stderr[-400:]
        outputs.append(done.stdout)
    assert outputs[0] == outputs[1]
    for line in outputs[0].splitlines():
        text, split, seed, task_id = line.split()
        assert made(text, int(seed), split).task_id == task_id, line
