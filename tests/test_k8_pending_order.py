"""Pending a decision: the order of the reference's calls.

The design says the six calls an episode needs (four reads and two stage calls) are the same at
every level, and the reference makes one call per turn; it does not say in which order.  If the
answer is yes, the reference makes the four named reads first, in the order the request lists them,
then B's two stage calls: the order a model reading the request top to bottom makes them.  Dropped
if the answer is no: the order is then the build's, inside the frozen tests (the four reads and
B's two stage calls; G4).
"""

from __future__ import annotations

from tests.k8_support import LEVELS, SPLITS, base, listed, spread


def test_the_reference_reads_in_the_listed_order_then_makes_bs_two_stage_calls() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            b_calls = list(base(seed, split).reference_calls)
            for level in LEVELS:
                bundle = spread(level, seed, split)
                calls = [(str(name), dict(args)) for name, args in bundle.reference_calls]
                assert calls == [*listed(bundle), *b_calls], (level, seed, split)
