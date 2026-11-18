"""What a spread request says from 0.5.0 about an answer that holds no part, and that it says the
same at every level, frozen as tests.

Ruled 2026-11-15: the sentence "An answer that holds no part reads `none`." becomes "An answer
that holds no part has nothing before its full stop: leave it out."  The rest of the request is
unchanged, and it stays the same at every level (the ledger's N35): a level changes how the code is
spread across the answers and nothing a model reads before it calls a tool.

Shapes decided here
-------------------

**1. The new sentence, once, and the old one gone**: at each of the sixty card seeds on both
splits, at the card's three levels and the one between them, the request holds the line "The entry
code is split across the answers of these four reads, in the order listed: join the parts. An
answer that holds no part has nothing before its full stop: leave it out." exactly once, on a line
of its own; it does not hold the old sentence; and `none` is no word of it (it was a word of every
spread request before, and of none after).

**2. One request at every level**: the requests of levels 1, 2, 3 and 4 are the same bytes, and so
are the system prompts.  `tests/test_k8_fixed.py` holds every other field equal across levels; the
request is held here on its own, by its bytes, because it is the field this release edits.

**3. Nothing else moved**: put the old sentence back where the new one is, and every request is
the one 0.4.2 made.  Held by one digest over the 480 requests (two splits, sixty seeds, four
levels), measured on 0.4.2's tree (`917d2e7`) before the build existed.  A build that reworded
another line, renamed a read or drew the reads again fails here.
"""

from __future__ import annotations

import hashlib

from tests.g4_support import LEVELS, MARKER, OLD_NO_PART_SENTENCE, OLD_SENTENCE, SENTENCE
from tests.k8_support import SPLITS, request, spread, words

# sha256 over, for each split, seed and level in order: the split, the seed, the level and the
# request, joined by 0x1f and ended by a newline.  Measured on 917d2e7, the 0.4.2 generator.
REQUESTS_AT_0_4_2 = "89d13a7f339be7daa2e56e19fe4fa0c431a4dfc8a58c0d77821edafede108046"


def test_the_request_says_the_new_sentence_once_and_not_the_old_one() -> None:
    """Shape 1."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                text = request(spread(level, seed, split))
                where = (level, seed, split)
                assert text.count(SENTENCE) == 1, where
                assert text.split("\n").count(SENTENCE) == 1, where
                assert OLD_NO_PART_SENTENCE not in text, where
                assert MARKER not in words(text), where


def test_the_request_and_the_system_prompt_are_the_same_bytes_at_every_level() -> None:
    """Shape 2."""
    for split, seeds in SPLITS:
        for seed in seeds:
            bundles = [spread(level, seed, split) for level in LEVELS]
            requests = {request(bundle).encode("utf-8") for bundle in bundles}
            assert len(requests) == 1, (seed, split)
            assert len({bundle.system_prompt for bundle in bundles}) == 1, (seed, split)


def test_with_the_old_sentence_put_back_every_request_is_the_one_0_4_2_made() -> None:
    """Shape 3."""
    digest = hashlib.sha256()
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                text = request(spread(level, seed, split))
                assert text.count(SENTENCE) == 1, (level, seed, split)
                restored = text.replace(SENTENCE, OLD_SENTENCE)
                digest.update(
                    b"\x1f".join(
                        (split.encode(), str(seed).encode(), str(level).encode(), restored.encode())
                    )
                    + b"\n"
                )
    assert digest.hexdigest() == REQUESTS_AT_0_4_2
