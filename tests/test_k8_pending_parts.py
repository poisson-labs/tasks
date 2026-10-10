"""Pending a yes/no: which of the four named reads carry the parts.

Spec §14.4 and plan K8.2 say that at level P exactly P of the four answers carry a part, in order,
joining to the entry code, and the rest answer `none`; they do not say which P.  If the answer is
yes, the parts are in the first P reads in the order the request lists them, and the rest read
`none`: so the reads that carry a part at one level carry one at every higher level, and the order
the four are drawn in decides which read holds what.  Dropped if the answer is no: which reads carry
the parts is then the build's, inside the frozen tests (exactly P, in the listed order, joining to
the code).
"""

from __future__ import annotations

from tests.k8_support import LEVELS, NONE, READS, SPLITS, entry_code, heads, parts, spread


def test_the_parts_are_in_the_first_reads_the_request_lists() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                expected = parts(entry_code(bundle), level) + [NONE] * (READS - level)
                assert heads(bundle) == expected, (level, seed, split)
