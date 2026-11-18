"""Pending a decision: what a spread request on a user's own tools says about an answer that holds
no part.

**Why it is open.**  The 0.5.0 design gives one new sentence, "An answer that holds no part has
nothing before its full stop: leave it out.", and says own tools "get the same fix in the same
change".  The sentence fits the built-in ledger's answers, whose payload is a part, a full stop and
filler.  An own-tools answer is the tool's own JSON: the part is the value of a field the request
names on each read's line ("the order_id field"), and there is no full stop.  Said of an own-tools
answer, the built-in sentence points at something the answer does not have.

**Recommended.**  The own-tools request says "An answer that holds no part has nothing in its
field: leave it out." where it said "An answer that holds no part reads "none".", and nothing else
of the request moves: put the old sentence back and every request is the one 0.4.2 made (one digest
over 234 requests: six fixture sets, thirteen seeds, three levels, measured on 0.4.2's tree,
`917d2e7`).  If it is declined, the own-tools request carries the built-in sentence word for word,
and this file's sentence and digest change to say so; what `tests/test_g4_own.py` holds (the empty
field, the old sentence gone, one request at every level, the join) stands either way.
"""

from __future__ import annotations

import hashlib

from tests.o2_support import arm, fixture_sets, flows_for, generator

SEEDS = (404, 55, 2121, *range(10))
OWN_LEVELS = (1, 2, 4)
SENTENCE = "An answer that holds no part has nothing in its field: leave it out."
OLD_SENTENCE = 'An answer that holds no part reads "none".'
# sha256 over, for each fixture set by label, seed and level in order: the label, the seed, the
# level and the request, joined by 0x1f and ended by a newline.  Measured on 917d2e7.
REQUESTS_AT_0_4_2 = "6c9e79fd600d62092351de29c42329cd082177584d9bb4c020b5caf85f7626e3"


def test_the_own_request_says_the_field_is_empty_and_nothing_else_of_it_moved() -> None:
    digest = hashlib.sha256()
    for label, toolset in sorted(fixture_sets().items()):
        for seed in SEEDS:
            for level in OWN_LEVELS:
                bundle = generator().generate(
                    toolset, arm("spread", level), seed, flows=flows_for(label)
                )
                where = (label, level, seed)
                assert bundle.request.count(SENTENCE) == 1, where
                head = bundle.request.split("\n")[0]
                assert head.endswith("join the parts. " + SENTENCE), where
                restored = bundle.request.replace(SENTENCE, OLD_SENTENCE)
                digest.update(
                    b"\x1f".join(
                        (label.encode(), str(seed).encode(), str(level).encode(), restored.encode())
                    )
                    + b"\n"
                )
    assert digest.hexdigest() == REQUESTS_AT_0_4_2
