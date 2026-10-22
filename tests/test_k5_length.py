"""The block-size knob's length: the ledger over the contrast, the control's filler, and Qwen's room,
frozen as tests.

It rests on the pin ledger's N3 and N29.  The
block's reference tokens grow with the level by definition, about 56 a tool, and the ledger
reports the growth and refuses nothing for it (N29); the control `block:k8+len(k64)` holds k8's
block with a neutral filler in its system prompt, within two tokens of what k64's block adds, which
N3's extended rule lets through and N29 refuses outside its band; the filler's words carry no
token of the vocabulary table (the rule `tasks._check_filler_words` asserts for knob R's).  At
k64, Qwen's first request plus 31 calls of growth stays under the notebook's gate.

Shapes decided here
-------------------

**1. The contrast is the five arms at once**, k8 to k64 and the control, at every card seed on both
splits, as `generate_contrast` would refuse it: the ledger refuses nothing, and the one row it
reports is N29, the block's growth.  So every row the block knob is held to (N1 to N3, N6 to N8,
N11, N12, N27 to N29) holds over the levels, and the filler's length is held by N29's band, which
is the ledger's to measure and is not measured a second way here.

**2. The filler is the end of the system prompt**: the control's system prompt is k8's (B's)
followed by the filler, and each word of the filler is one that no part of the vocabulary table
spells, with no underscore, so it neither names a tool nor reads as one.

**3. Qwen's room is model B's arithmetic over the block the generator makes.**  The design: k64's
first request is about 5,500 Qwen tokens, at 1.48 Qwen tokens per reference token of schema, and
31 calls of growth bring it to about 8,900, under the gate.  B's first request is about 1,526 Qwen
tokens and a call adds about 110 (model B's measured figures); the gate is
`calibration_run.HEADROOM` of what model B's serving pin leaves for the prompt.  So at every card
seed, 1,526 + 1.48 x (k64's block tokens less B's) + 31 x 110 must stay under the gate.  The three
ratios are measurements the generator does not control and are not re-measured at $0; the block
is the one figure the generator controls, and nothing else bounds it.  The notebook's probe phase
measures the prompt itself.
"""

from __future__ import annotations

import json
from typing import Any

from poisson_tasks import calibration as cal
from poisson_tasks import calibration_run as driver
from poisson_tasks.knobs import check_pins
from tests.k3_support import B_ARM, SPEC, made
from tests.k5_support import ARMS, SPLITS, block, block_tokens, control

B_FIRST_REQUEST = 1526
SCHEMA_RATIO = 1.48
GROWTH_PER_CALL = 110
CALLS_AFTER_THE_FIRST = 31


def test_the_contrast_holds_everything_but_the_block_and_reports_its_growth() -> None:
    """Shape 1."""
    for split, seeds in SPLITS:
        for seed in seeds:
            contrast: dict[str, Any] = {arm_id: made(arm_id, seed, split) for arm_id in ARMS}
            report = check_pins(contrast)
            assert report.violations == (), (seed, split, report.violations)
            assert [row for row, _detail in report.reported] == ["N29"], (seed, split)


def test_the_controls_filler_ends_the_system_prompt_in_words_the_table_does_not_spell() -> None:
    """Shape 2."""
    table = json.dumps(SPEC.table).lower()
    for split, seeds in SPLITS:
        for seed in seeds:
            base = block(8, seed, split).system_prompt
            prompt = control(seed, split).system_prompt
            assert prompt.startswith(base), (seed, split)
            words = prompt[len(base) :].split()
            assert words, (seed, split)
            for word in words:
                assert "_" not in word and word.lower() not in table, (word, seed, split)


def test_k64s_first_request_leaves_room_under_qwens_gate() -> None:
    """Shape 3."""
    gate = driver.HEADROOM * (driver.QWEN3_8B.max_model_len - int(cal.DECODING["max_tokens"]))
    assert gate == 10_752
    for split, seeds in SPLITS:
        for seed in seeds:
            extra = block_tokens(block(64, seed, split)) - block_tokens(made(B_ARM, seed, split))
            first = B_FIRST_REQUEST + SCHEMA_RATIO * extra
            assert first + CALLS_AFTER_THE_FIRST * GROWTH_PER_CALL < gate, (seed, split, extra)
