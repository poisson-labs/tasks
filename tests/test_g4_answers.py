"""What a spread task's four named reads answer from 0.5.0: an answer that holds no part has nothing
before its full stop, frozen as tests.

Until 0.5.0 an answer that held no part of the entry code said `none` where a part goes.  Entry
codes are English words, the word sat where a part sits, and the request never said to leave it
out, so a model joined it into the code: at level 1, where three answers said it, the first entry
code gpt-5-nano sent held `none` in 60 of 120 episodes.  Ruled 2026-11-15: the head of such an
answer is empty, so its payload is a full stop and then filler, and the request says to leave it
out (`tests/test_g4_request.py`).  Nothing else about an answer changes: its width, its layout,
its fill's alphabet, which reads hold the parts and how the code is cut.

Shapes decided here
-------------------

**1. An answer that holds no part** is a named read's payload that starts with its full stop.  At
level P exactly 4 - P of the four payloads do, at each of the sixty card seeds on both splits, at
the card's three levels and the one between them the generator can build; the other P heads are the
entry code cut into P parts as evenly as it goes, the earlier parts longer, in the listed order.
Read without saying which of the four hold the parts, which stays where
`tests/test_k8_pending_parts.py` put it.

**2. The word is gone**: `none` is in no head, at any level; and a payload that holds no part is a
full stop and then lowercase hex to the payload field's width, so nothing but filler follows the
stop.

**3. The join**: the four heads joined in the listed order, the empty ones included, are the entry
code at every level.  A model that reads each answer up to its full stop and joins what it read has
the code; before 0.5.0 that join was the code only at level 4.

**4. The band (N8)**: every answer line that holds no part is `L_obs` bytes and 14 to 35
`o200k_base` tokens, the table's band, over seeds, splits and positions.  Level 1 alone gives the
360 lines the design measured (sixty seeds, two splits, three positions); levels 2 and 3 are read
too.  The engine's `ok` status and the reference's own count are `tests/test_k8_parts.py`'s, which
reads every answer.

**5. The live answers**: the tool server answers a named read as the reference does, so a model
meets the same empty head.  Read at three seeds on each split; `tests/test_k8_live.py` holds the
server to the reference at every seed.
"""

from __future__ import annotations

from poisson_tasks.tokenizer import count_tokens
from tests.g4_support import (
    HEX,
    LEVELS,
    MARKER,
    READS,
    STOP,
    holds_no_part,
    lines,
    payloads,
    split_payloads,
)
from tests.k3_support import SPEC
from tests.k3_support import answers as served
from tests.k8_support import SPLITS, entry_code, listed, parts, payload, spread

BAND = (14, 35)
WIDTH = SPEC.layout["payload_width"]
DESIGN_LINES = 360


def test_at_level_p_four_less_p_answers_start_with_their_full_stop() -> None:
    """Shape 1."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                where = (level, seed, split)
                texts = payloads(bundle)
                assert len(texts) == READS, where
                empty = [text for text in texts if holds_no_part(text)]
                assert len(empty) == READS - level, (texts, *where)
                held = [head for head, _fill in split_payloads(bundle) if head]
                assert held == parts(entry_code(bundle), level), (texts, *where)


def test_no_head_says_none_and_only_filler_follows_an_empty_head() -> None:
    """Shape 2."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                where = (level, seed, split)
                for text, (head, fill) in zip(payloads(bundle), split_payloads(bundle)):
                    assert MARKER not in head, (text, *where)
                    assert len(text) == WIDTH, (text, *where)
                    if not holds_no_part(text):
                        continue
                    assert head == "", (text, *where)
                    assert text == STOP + fill, (text, *where)
                    assert len(fill) == WIDTH - len(STOP) and set(fill) <= HEX, (text, *where)


def test_the_heads_joined_in_the_listed_order_are_the_entry_code_at_every_level() -> None:
    """Shape 3."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                heads = [head for head, _fill in split_payloads(bundle)]
                assert "".join(heads) == entry_code(bundle), (heads, level, seed, split)


def test_every_answer_line_that_holds_no_part_is_inside_the_token_band() -> None:
    """Shape 4."""
    assert tuple(SPEC.table["token_band"]) == BAND
    low, high = BAND
    counted = {level: 0 for level in LEVELS}
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                for line in lines(bundle):
                    if not holds_no_part(payload(line)):
                        continue
                    where = (line, level, seed, split)
                    assert len(line.encode("utf-8")) == SPEC.L_obs, where
                    assert low <= count_tokens(line) <= high, (count_tokens(line), *where)
                    counted[level] += 1
    assert counted[1] == DESIGN_LINES
    assert counted == {1: DESIGN_LINES, 2: 240, 3: 120, 4: 0}


def test_the_tool_server_answers_a_read_that_holds_no_part_as_the_reference_does() -> None:
    """Shape 5."""
    for split, seeds in SPLITS:
        for seed in seeds[:3]:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                where = (level, seed, split)
                live = [payload(line) for line in served(bundle, listed(bundle))]
                assert live == payloads(bundle), where
                assert sum(holds_no_part(text) for text in live) == READS - level, (live, *where)
