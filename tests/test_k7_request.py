"""What a task-shape request says: one line per goal, the rest the same at every width, its control
padded to the widest request's length; and the ledger over the contrast, frozen as tests.

The request (`ledger-goals/v1`)
lists one line per goal, so its length moves with the width; the control pads `w1`'s request to
`w4`'s length within two tokens, at the request's end (N34); N7's overlap set is reported for
shape and not refused, and every other ledger row holds.  The block's token count is reported (N33).

Shapes decided here
-------------------

**1. A goal line** is a line of the request that names a record id the scenario holds: this
file's reading of "one line per goal", so that each goal's record is named on its own line and on
no other line.  At every
width and on the control the request has exactly one goal line per target, in the knob's own
slot (`goal_lines`, `knobs._OWN_SLOT`, the slot N6 leaves out), and each names its target's record
id, its ledger's word and its goal stage's name, and no other ledger and no other record id.  The
template is `ledger-goals/v1` at every width.  The request names the entry code (how it is quoted is the wording's).  How a line is
worded is pending a decision (`tests/test_k7_pending_wording.py`); the order of the lines with the
reference's order is another (`tests/test_k7_pending_order.py`).

**2. Only the goal lines move**: the requests of `w1`, `w2` and `w4` are one text once each one's
goal lines are set aside, and every prompt slot but the knob's own is the same at every width.

**3. The control** is `w1`'s request followed by a filler (`tests/test_k7_fixed.py`), and its whole
request is within two tokens of `w4`'s: the ledger's N34, which the contrast below runs.  A test
of its own for the two was written and removed before the freeze: no deliberate bug failed it
that the contrast and the fixed test did not.

**4. The contrast**, `w1`, `w2`, `w4` and the control at every card seed on both splits: the ledger
refuses nothing, and reports N7 (the overlap set moves with the ledgers a wider request names) and
N33 (the block's token count moves with its composition), and nothing else.
"""

from __future__ import annotations

from typing import Any

from poisson_tasks.arms import arm_from_id
from poisson_tasks.knobs import check_pins
from poisson_tasks.tasks import generate_contrast
from tests.k3_support import SPEC, made
from tests.k7_support import (
    ARMS,
    SLOT,
    SPLITS,
    TEMPLATE_ID,
    entry_code,
    goal_lines,
    records,
    request,
    shape,
    targets,
    width_of,
    words,
)


def test_one_goal_line_per_target_in_the_knobs_own_slot() -> None:
    """Shape 1."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for arm_id in ARMS:
                bundle = made(arm_id, seed, split)
                where = (arm_id, seed, split)
                assert bundle.template_id == TEMPLATE_ID, where
                lines = goal_lines(bundle)
                found = targets(bundle)
                assert len(lines) == len(found) == width_of(arm_id), where
                assert dict(bundle.prompt_slots)[SLOT].split("\n") == lines, where
                held = records(bundle)
                unmatched = dict(found)
                for line in lines:
                    said = words(line)
                    ledgers = [q for q in SPEC.qualifiers if q in said]
                    named = [r for r in held if r in line]
                    assert len(ledgers) == 1 and len(named) == 1, (line, *where)
                    key = (ledgers[0], named[0])
                    assert key in unmatched, (line, *where)
                    stage = SPEC.stage_names[unmatched.pop(key) - 1]
                    assert stage in said, (line, *where)
                assert unmatched == {}, where
                assert entry_code(bundle) in words(request(bundle)), where


def test_only_the_goal_lines_move_across_widths() -> None:
    """Shape 2."""
    for split, seeds in SPLITS:
        for seed in seeds:
            rest = set()
            slots = set()
            for width in (1, 2, 4):
                bundle = shape(width, seed, split)
                lines = dict(bundle.prompt_slots)[SLOT]
                text = request(bundle)
                assert text.count(lines) == 1, (width, seed, split)
                rest.add(text.replace(lines, "\x00"))
                slots.add(tuple(slot for slot in bundle.prompt_slots if slot[0] != SLOT))
            assert len(rest) == 1 and len(slots) == 1, (seed, split)


def test_the_contrast_refuses_nothing_and_reports_the_overlap_and_the_block_tokens() -> None:
    """Shape 4."""
    for split, seeds in SPLITS:
        for seed in seeds:
            arms = tuple(arm_from_id(text, split=split) for text in ARMS)
            made_: dict[str, Any] = dict(generate_contrast(arms, seed))
            report = check_pins(made_)
            assert not report.refused and report.violations == (), (seed, split)
            assert [row for row, _detail in report.reported] == ["N7", "N33"], (seed, split)
