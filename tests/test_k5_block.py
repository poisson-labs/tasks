"""The block-size knob's block: how many tools, in which slots, drawn from where, frozen as tests.

It rests on the pin ledger's N27 and N28.
`block:kK` offers exactly K tools; the target ledger's two stage tools and six reads fill the
first eight slots, in an order drawn from the block knob's own keyed draw, the same at every level;
slots 8 and up follow a drawn order, the table's other reads first, then aliased read copies
(`tests/test_k5_aliases.py`).  `block:k8+len(k64)` offers k8's block.

How many tools an arm offers is held by the ledger's N27 over the five arms at every seed
(`tests/test_k5_length.py`) and, for levels no card measures, by `tests/test_k5_eval.py`; that no
name repeats in a block, by the copies' distinct descriptions and the tool server's advertised
list (`tests/test_k5_aliases.py`).  A test of the count and the names alone caught no wrong build
that those did not, and was removed before the freeze.

Shapes decided here
-------------------

**1. The six reads of the first eight slots are the table's first six, in table order before the
draw.**  The design says the k8 block is "the target ledger's two stage tools and six reads, in an
order drawn from the block knob's own PRF domain" and never which six.  The generator's rule for
B's block decides it the same way (`tasks.py`: "the block's read tools are the table's first `n`
reads, in table order, and the block is then permuted by the scenario's one slot draw"): drawing
the subset and the order would parameterise one arrangement twice, and the census
(`tests/test_k5_eval.py`) could no longer be stated as the size of what the arm can make.

**2. One drawn order, read as far as the level goes: each level's block is the start of the next
one's.**  The design says the k8 block "fills slots 0 to 7 at every level" and that more reads fill
slots 8 and up "in a drawn order: first the table's other engine reads, then display-aliased read
copies".  Read as one order, a level adds tools and changes nothing it already offered, which is
"only that factor" for a knob whose factor is how many tools there are.  So k16's block is the
first sixteen of k32's and of k64's, schema for schema.

**3. "From the block knob's own PRF domain" is checked by what it protects**, as the similarity
knob's draws were (`tests/test_k2_block.py`, shape 6): every level's scenario is B's
(`tests/test_k5_fixed.py`), and the published tasks keep their content (`tests/test_k1_content.py`),
so the draw took nothing from the scenario's.  What is pinned here is that it is a draw over the
whole range: across the card seeds on both splits the first stage tool sits in each of the eight
head slots, the ninth slot holds most of the table's other reads, the last slot of k64 holds many
different copies, every copy is offered somewhere, and the two splits order a seed's block
differently (the right tools' names set aside, since they carry the target ledger, which the
scenario draws from the split anyway).  A draw that runs out of keyed bits before k64's last slot (a
single 32-byte draw cannot order 46 copies after the head: about 2^393 orders) leaves its last slots
to the decoding's fallback and fails the k64 clause.  An order read off the scenario's own slot
digits, which moves no other task, is not observable here and is named in the mutation table.

**4. The draw does not read the process**: a block task, the control's filler included, is the
same in another process under another hash seed (G1).  An order built by iterating a set would
not be.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from typing import Any

from tests.k3_support import SPEC, made, names
from tests.k5_support import (
    CARD_SEEDS,
    CONTROL,
    ENGINE_TOOLS,
    FACETS,
    HEAD,
    LEVELS,
    READS,
    SPLITS,
    VERBS,
    block,
    control,
    copies,
)


def test_the_first_eight_slots_are_the_right_tools_and_six_reads_the_same_at_every_level() -> None:
    """N28 and shape 1: k8's block is the target ledger's first two stage tools and the table's
    first six reads; every level's first eight slots, and the control's block, are k8's, schema
    for schema, so the right tools keep their slots inside the first eight."""
    for split, seeds in SPLITS:
        for seed in seeds:
            head = list(block(8, seed, split).tools)
            ledger = block(8, seed, split).goal[0]
            right = {
                name
                for name, (index, qualifier) in SPEC.stage_tools.items()
                if qualifier == ledger and index < 2
            }
            assert {str(tool["name"]) for tool in head} == right | set(READS[:6]), (seed, split)
            for level in LEVELS:
                assert list(block(level, seed, split).tools[:HEAD]) == head, (level, seed, split)
            assert list(control(seed, split).tools) == head, (seed, split)


def test_past_the_eighth_slot_the_other_reads_come_first_and_each_level_starts_the_next() -> None:
    """The design's order and shape 2: slots 8 and up hold the table's ten other reads before any
    tool that is no engine tool, and each level's block is the start of the next level's."""
    others = set(READS[6:])
    for split, seeds in SPLITS:
        for seed in seeds:
            top = list(block(64, seed, split).tools)
            tail = [str(tool["name"]) for tool in top[HEAD:]]
            assert set(tail[: len(others)]) == others, (seed, split)
            assert not ENGINE_TOOLS & set(tail[len(others) :]), (seed, split)
            for level in LEVELS:
                assert list(block(level, seed, split).tools) == top[:level], (level, seed, split)


def test_the_block_draw_covers_its_range_on_both_splits() -> None:
    """Shape 3, over the sixty card seeds on both splits (120 draws)."""
    head_slots: Counter[int] = Counter()
    ninth: Counter[str] = Counter()
    last: Counter[str] = Counter()
    offered: set[str] = set()
    for split, seeds in SPLITS:
        for seed in seeds:
            top = block(64, seed, split)
            shown = names(top)
            head_slots[shown.index(str(top.reference_calls[0][0]))] += 1
            ninth[shown[HEAD]] += 1
            last[shown[-1]] += 1
            offered |= set(copies(top))
    assert set(head_slots) == set(range(HEAD)), head_slots
    assert len(ninth) >= 8, ninth
    assert len(last) >= 30, last
    assert len(offered) == len(VERBS) * len(FACETS) - len(READS), len(offered)
    orders = {split: [masked(block(64, seed, split)) for seed in seeds] for split, seeds in SPLITS}
    assert orders["eval"] != orders["train"]


def masked(bundle: Any) -> tuple[str, ...]:
    """The block's names with the two right tools as one mark: their names carry the target
    ledger, which the scenario draws from the split already, so only the order is compared."""
    right = {str(name) for name, _args in bundle.reference_calls}
    return tuple("right" if name in right else name for name in names(bundle))


def test_a_block_task_is_the_same_in_another_process_and_under_another_hash_seed() -> None:
    """Shape 4, for the top level and the control."""
    seed = CARD_SEEDS[7]
    here = {arm_id: made(arm_id, seed).task_id for arm_id in (f"block:k{LEVELS[-1]}", CONTROL)}
    code = (
        "import json; from poisson_tasks.arms import arm_from_id; "
        "from poisson_tasks.tasks import generate; "
        f"print(json.dumps({{a: generate(arm_from_id(a), {seed}).task_id "
        f"for a in {sorted(here)!r}}}))"
    )
    for hash_seed in ("0", "4242"):
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": hash_seed, "PATH": ""},
        )
        assert json.loads(out.stdout) == here, hash_seed
