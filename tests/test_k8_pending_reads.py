"""Pending a decision: the pools the four named reads are drawn from.

The design says the four reads are drawn from the block's reads, from their own PRF
domain, and name them by item, facet and page; it does not say whether one read tool may be named
twice, nor which items and pages a read may name.  If the answer is yes, a task's four named reads
are four different read tools, every one of B's fourteen reads may be drawn, and a read's item may
be any of the table's sixteen catalogue items and its page any of its sixteen page keys: over the
card seeds on both splits and the four places, every one of them is drawn.  Dropped if the answer
is no: the pools are then the build's, inside the frozen tests (a read tool the block holds, an
item the catalogue holds, a page key the table holds).
"""

from __future__ import annotations

from tests.k3_support import SPEC
from tests.k8_support import ITEM, PAGE, SPLITS, base, named, names, spread


def test_four_different_read_tools_any_of_bs_reads_and_any_item_and_page() -> None:
    tools: set[str] = set()
    items: set[str] = set()
    pages: set[str] = set()
    pool: set[str] = set()
    for split, seeds in SPLITS:
        for seed in seeds:
            reads = named(spread(1, seed, split))
            assert len({name for name, _args in reads}) == len(reads), (seed, split)
            tools |= {name for name, _args in reads}
            items |= {args[ITEM] for _name, args in reads}
            pages |= {args[PAGE] for _name, args in reads}
            pool |= {name for name in names(base(seed, split)) if name in SPEC.read_tools}
    assert len(pool) == 14
    assert tools == pool
    assert items == set(SPEC.table["catalogue_items"])
    assert pages == set(SPEC.page_keys)
