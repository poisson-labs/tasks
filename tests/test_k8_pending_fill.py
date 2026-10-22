"""Pending a decision: how a named read's fill is keyed.

The design says a part answer's payload is the part, a `.`, then hex from a keyed hash to fill the
width, and a `none` answer `none.` and hex the same way; it does not say what the hash is keyed on.
If the answer is yes, each named read has one fill of its own, keyed by the task and the read's
place in the request and not by the level: at every level a read's fill is the start of that one
string, as long as its head leaves room for, so the level moves only the heads; and the four reads
of a task have four different fills.  Dropped if the answer is no: the key is then the build's,
inside the frozen tests (lowercase hex, keyed by the task, the payload as wide as the table's).
"""

from __future__ import annotations

from tests.k8_support import LEVELS, SPLITS, answers, head_and_fill, key, listed, payload, spread


def test_a_reads_fill_is_its_own_and_the_same_at_every_level() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            fills: list[set[str]] = [set(), set(), set(), set()]
            for level in LEVELS:
                bundle = spread(level, seed, split)
                found = answers(bundle)
                for place, read in enumerate(listed(bundle)):
                    fills[place].add(head_and_fill(payload(found[key(read)]))[1])
            longest = [max(seen, key=len) for seen in fills]
            for seen, whole in zip(fills, longest, strict=True):
                assert all(whole.startswith(fill) for fill in seen), (seed, split, seen)
            starts = {whole[:16] for whole in longest}
            assert len(starts) == len(longest), (seed, split, longest)
