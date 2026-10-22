"""The argument-difficulty knob's stated values, and the ledger over its contrast, frozen as tests.

It rests on the pin ledger's N31 and N32.  `arguments:aA`'s
request states exactly `A - 2` extra values, opaque words drawn from `(seed, split)`, which both
stage calls must carry; the control `arguments:a2+len(a8)` holds a2's request plus a neutral filler
within two tokens of what a8's request adds.

Shapes decided here
-------------------

**1. What a level states is read off its reference**: both stage calls carry the same extra
values, exactly the level less two of them (none on the control), each in a parameter the stage
tool lists and does not require, each value in the request (more times than in B's request, so a
value that is only a piece of the record id or the entry code is not stated) and carried by no name
of a tool the table defines; and the request names no other of the six, neither as written nor in
words.  So a request that stated more than its level, or a reference
that carried fewer, fails here.

**2. "Drawn from `(seed, split)`" is read as what it excludes**: the values a level states are among
the six a8 states for the same task, so the draw does not read the level (which parameter takes
which value at each level is pending a decision, `tests/test_k6_pending_nested.py`); the values move
from seed to seed, so that no value fills one parameter at more than half the card seeds of a split;
and at some card seed the two splits draw different values.  The words are opaque; which list they
come from is not pinned.  A task is the same in another process under another hash seed, so the draw
reads nothing but its inputs.

**3. The contrast is the five arms at once**, a2 to a8 and the control, at every card seed on both
splits, as `generate_contrast` would refuse it: the ledger refuses nothing and reports nothing.  So
every row the knob is held to (N1 to N4, N6 to N8, N11, N12, N30 to N32) holds over the levels; N31
also holds each value to one no tool name carries, and N32 the control's whole request to a8's
within two tokens, which is the ledger's to measure and is not measured a second way here.
"""

from __future__ import annotations

import json
import os
from collections import Counter
import subprocess
import sys
from pathlib import Path
from typing import Any

from poisson_tasks.knobs import check_pins
from tests.k3_support import made
from tests.k3_support import SPEC
from tests.k6_support import (
    ARMS,
    CONTROL,
    SPLITS,
    arm,
    base,
    extras,
    in_words,
    more,
    request,
    stage_tools,
    stated,
    stated_count,
)

REPO = Path(__file__).resolve().parent.parent
TOOL_NAMES = [tool.name.lower() for tool in SPEC.tools]


def test_both_stage_calls_carry_exactly_the_values_the_request_states() -> None:
    """Shape 1."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for arm_id in ARMS:
                bundle = made(arm_id, seed, split)
                first, second = bundle.reference_calls
                assert extras(first) == extras(second), (arm_id, seed, split)
                carried = stated(bundle)
                assert len(carried) == stated_count(arm_id), (arm_id, seed, split, carried)
                listed = set(more(stage_tools(bundle)[0]))
                assert set(carried) <= listed, (arm_id, seed, split)
                text, b_text = request(bundle), request(base(seed, split))
                for name, value in carried.items():
                    assert isinstance(value, str) and value, (arm_id, name)
                    assert text.count(value) > b_text.count(value), (arm_id, name, seed)
                    carried_by = [tool for tool in TOOL_NAMES if value.lower() in tool]
                    assert carried_by == [], (arm_id, name, value, carried_by[:3])
                for name in listed - set(carried):
                    assert name not in text and in_words(name) not in text, (arm_id, name, seed)


def test_a_value_is_drawn_from_the_seed_and_the_split_and_never_the_level() -> None:
    """Shape 2: one value per parameter per task, moving with the seed and with the split."""
    drawn: dict[tuple[str, int], dict[str, str]] = {}
    for split, seeds in SPLITS:
        per_name: dict[str, Counter[str]] = {}
        for seed in seeds:
            values = stated(made(arm(8), seed, split))
            for arm_id in ARMS:
                held = set(stated(made(arm_id, seed, split)).values())
                assert held <= set(values.values()), (arm_id, seed, split)
            for name, value in values.items():
                per_name.setdefault(name, Counter())[value] += 1
            drawn[(split, seed)] = dict(values)
        assert per_name, split
        for name, counts in per_name.items():
            ((common, times),) = counts.most_common(1)
            assert times <= len(seeds) // 2, (name, common, times, split)
    eval_seeds = dict(SPLITS)["eval"]
    train_seeds = dict(SPLITS)["train"]
    shared = [seed for seed in eval_seeds if seed in train_seeds]
    assert any(drawn[("eval", seed)] != drawn[("train", seed)] for seed in shared)


def test_the_contrast_holds_every_row_and_reports_nothing() -> None:
    """Shape 3."""
    for split, seeds in SPLITS:
        for seed in seeds:
            contrast: dict[str, Any] = {arm_id: made(arm_id, seed, split) for arm_id in ARMS}
            report = check_pins(contrast)
            assert report.violations == (), (seed, split, report.violations)
            assert report.reported == (), (seed, split, report.reported)


PROGRAM = """
import json, sys
from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import generate
out = []
for arm_id, split, seed in json.loads(sys.argv[1]):
    out.append(generate(arm_from_id(arm_id, split=split), seed).task_id)
print(json.dumps(out))
"""


def test_an_arguments_task_is_the_same_in_another_process_under_another_hash_seed() -> None:
    """Shape 2's last clause."""
    asked = [
        (arm_id, split, seeds[index])
        for split, seeds in SPLITS
        for index in (0, 23, 51)
        for arm_id in ("arguments:a8", CONTROL)
    ]
    here = [made(arm_id, seed, split).task_id for arm_id, split, seed in asked]
    for hash_seed in ("1", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed}
        done = subprocess.run(
            [sys.executable, "-c", PROGRAM, json.dumps(asked)],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO,
            env=env,
        )
        assert json.loads(done.stdout) == here, hash_seed
