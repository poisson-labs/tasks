"""Pending a decision: spread on a user's own tools names four reads at every level.

**Why it is open.**  The design: "a target value is split across the answers of 1, 2 or 4 named
reads of your read tools".  Read literally, the number of reads (and so of calls, and of the
request's lines) changes with the level, which is more than one factor.  The built-in knob names
four reads at every level and has the first level-many hold a part, the others `none`
(`tests/test_k8_parts.py`).

**Recommended.**  As the built-in knob: four named reads at every level, each a different call, the
reads and their order drawn per seed and kept across levels; `level` of them hold a part of the
value, in order, and the others hold `none` in the same field.  Level 1 is the design's "read then
call".  If it is declined, the build names exactly `level` reads.
"""

from __future__ import annotations

import json
from typing import Any

from tests.o2_support import acme, fixture_sets, generator, arm


def field_value(text: str, path: str) -> Any:
    node: Any = json.loads(text)
    for part in path.split("."):
        node = node[part.removesuffix("[]")]
        if part.endswith("[]"):
            node = node[0]
    return node


def test_four_reads_at_every_level_and_the_rest_hold_none() -> None:
    for toolset in (acme(), fixture_sets()["petstore"]):
        for seed in range(10):
            made = {level: generator().generate(toolset, arm("spread", level), seed) for level in (1, 2, 4)}
            assert len({json.dumps([list(r[:2]) for r in b.named_reads]) for b in made.values()}) == 1
            for level, bundle in made.items():
                assert len(bundle.named_reads) == 4
                assert len({json.dumps(list(r[:2])) for r in bundle.named_reads}) == 4
                held = [field_value(text, path) for text, (_t, _a, path)
                        in zip(bundle.reference_observations, bundle.named_reads, strict=False)]
                assert sum(value == "none" for value in held) == 4 - level, held
