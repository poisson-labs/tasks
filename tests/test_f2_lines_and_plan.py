"""The timeouts and ratelimits tasks: the line, the plan, the reference, the sentence and the
control, frozen as tests.

The invariants (the 0.3.0 faults spec, F2.2, F2.3 and F2.5).  A planned `timeout` is the engine's
line at the next `seq` with `timeout` in the status field and the table's error payload; a planned
`rate_limited` the same with `rate_limited` and the payload `retry-after=1s` padded with the table's
fill to 32 bytes; each is 52 bytes, inside N8's band, and moves no record.  The two knobs plan their
level as faults does, the first stage tool taking the odd answer, and the reference makes each
planned call and the same call again.  Each knob's system prompt is B's and its one sentence, at
every level, level 0 included; its levels and its control differ from level 0 only where faults'
do.

Faults' own tests (`tests/test_k3_plan.py`, `tests/test_k3_control.py`) are the pattern, and the
helpers are `tests/k3_support.py`'s.  That `surface` imports nothing private from the engine is
already held by `tests/test_k3_plan.py` over the same file, and is not repeated here.

Shapes decided here
-------------------

**1. `surface.fault_kind(arm_id)` is the status word an arm's planned answers carry**:
`unavailable` on faults, `timeout` on timeouts and on landed, `rate_limited` on ratelimits, and
`None` on an arm of any other knob.  It is the one name the spec's library list gives for the kind,
and the seam's readers (the server, `verify`, the replay check, the gave-up figure) read the word
from it.

**2. `surface.fault_plan` plans the new knobs as the spec's section 1.1 writes**: timeouts and
ratelimits as faults (the level over the path's tools, the earlier taking the extra); landed one
answer on the last tool of the path at level 1 and none at level 0.

**3. N25's measured value is faults' shape**, the tools of the path with the planned count each,
so a measure that counted `unavailable` lines on a timeouts task would read zeros and differ.

**4. The rows apply as the spec's section 2 says**: N24 and N25 to the three new knobs beside
faults, N26 to timeouts and ratelimits and not to landed; the ledger keeps thirty rows.
"""

from __future__ import annotations

import math

import pytest

from poisson_tasks import knobs, surface
from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import generate_contrast
from poisson_tasks.tokenizer import count_tokens
from tests.f2_support import KINDS, LEVELS, NEW_KNOBS, SPEC, Kind, fault_kind, planned_line
from tests.k3_support import (
    CARD_SEEDS,
    answers,
    base,
    made,
    names,
    right,
    seq,
    status,
    verdict_of,
)
from tests.test_k3_control import pair_tokens, seeded
from tests.test_k3_plan import label_of, other_fields

SPLITS = ("eval", "train")


def planned(level: int) -> tuple[int, int]:
    """faults' table: the first stage takes the odd answer."""
    return math.ceil(level / 2), level // 2


# --------------------------------------------------------------------------
# the kind and the plan
# --------------------------------------------------------------------------


def test_fault_kind_names_each_arms_word_and_fault_plan_plans_each_knob() -> None:
    """Shapes 1 and 2."""
    words = {
        "faults:f2": "unavailable",
        "faults:f0+len(f4)": "unavailable",
        "timeouts:o2": "timeout",
        "timeouts:o0+len(o4)": "timeout",
        "ratelimits:r2": "rate_limited",
        "landed:l1": "timeout",
        "depth:d3": None,
        "distractor:r0@k16": None,
        "history:t600": None,
    }
    assert {arm_id: fault_kind(arm_id) for arm_id in words} == words
    path = ("a", "b")
    for knob, letter in (("timeouts", "o"), ("ratelimits", "r")):
        for level in LEVELS:
            assert surface.fault_plan(f"{knob}:{letter}{level}", path) == surface.fault_plan(
                f"faults:f{level}", path
            )
    assert surface.fault_plan("landed:l1", path) == {"b": 1}
    assert surface.fault_plan("landed:l1", ("a", "b", "a")) == {"a": 1}
    assert surface.fault_plan("landed:l0", path) == {}


def test_n24_and_n25_apply_to_the_new_knobs_and_n26_to_two_of_them() -> None:
    """Shape 4."""
    rows = {row.row_id: row for row in knobs.pin_ledger("timeouts")}
    assert len(rows) == 30
    for row_id in ("N24", "N25"):
        assert {"faults", *NEW_KNOBS} <= set(rows[row_id].applies_to)
    assert {"faults", "timeouts", "ratelimits"} <= set(rows["N26"].applies_to)
    assert "landed" not in rows["N26"].applies_to


# --------------------------------------------------------------------------
# the line
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(KINDS.values()), ids=list(KINDS))
def test_a_planned_answer_is_one_engine_line_that_moves_nothing(kind: Kind) -> None:
    """Every planned line of level 4 at the card seeds is the table's layout at its `seq` with the
    kind's word and payload, `L_obs` bytes, inside N8's band.  At level 1 the first right call
    alone moves no record in `verify` or in the tool server, whose next call meets the record
    where it was."""
    low, high = SPEC.table["token_band"]
    for seed in CARD_SEEDS:
        lines = [
            line
            for line in made(kind.arm(4), seed).reference_observations
            if status(line) == kind.word
        ]
        assert len(lines) == 4, seed
        for line in lines:
            assert line == planned_line(seq(line), kind), line
            assert len(line.encode("ascii")) == SPEC.L_obs
            assert low <= count_tokens(line) <= high
    bundle = made(kind.arm(1), CARD_SEEDS[0])
    first, second = right(bundle)
    got = verdict_of(bundle, [first])
    assert (got.strict_label, got.leaky_pass, got.mutations) == ("wrong_state", False, ())
    assert [status(line) for line in answers(bundle, [first, second])] == [kind.word, "not_ready"]


# --------------------------------------------------------------------------
# the plan and the reference
# --------------------------------------------------------------------------


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("kind", list(KINDS.values()), ids=list(KINDS))
def test_the_reference_makes_each_planned_answer_and_then_the_same_call_again(
    kind: Kind, level: int
) -> None:
    """At every card seed on both splits: the calls, the words, the numbering from `seq_start`,
    the plan `fault_plan` gives, N25 (shape 3), and a reference one call per planned answer longer
    than B's, `reference_turns` 2 + F + 1."""
    first_fails, second_fails = planned(level)
    for split in SPLITS:
        for seed in CARD_SEEDS:
            bundle = made(kind.arm(level), seed, split)
            first, second = right(bundle)
            assert list(bundle.reference_calls) == (
                [first] * (first_fails + 1) + [second] * (second_fails + 1)
            ), (split, seed)
            observations = list(bundle.reference_observations)
            assert [status(o) for o in observations] == (
                [kind.word] * first_fails + ["ok"] + [kind.word] * second_fails + ["ok"]
            ), (split, seed)
            assert [seq(o) for o in observations] == list(
                range(bundle.seq_start, bundle.seq_start + len(observations))
            )
            done = [o.split()[2] for o in observations if status(o) == "ok"]
            assert done == [o.split()[2] for o in base(seed, split).reference_observations]
            path = (first[0], second[0])
            plan = {name: n for name, n in zip(path, planned(level), strict=True) if n}
            assert surface.fault_plan(bundle.arm_id, path) == plan
            assert bundle.pins.values["N25"] == ((first[0], first_fails), (second[0], second_fails))
    assert arm_from_id(kind.arm(level)).reference_turns == 2 + level + 1


@pytest.mark.parametrize("kind", list(KINDS.values()), ids=list(KINDS))
def test_every_contrast_holds_the_ledger_and_every_negative_control_its_label(kind: Kind) -> None:
    """G11 and G8 on the new knobs, at six card seeds: the four levels and the control generate
    as one contrast with no row violated, and each generated control gives the label its key
    opens with, the planned answers applied."""
    arms = tuple(arm_from_id(kind.arm(level)) for level in LEVELS) + (arm_from_id(kind.control),)
    for seed in CARD_SEEDS[:6]:
        contrast = generate_contrast(arms, seed)
        assert set(contrast) == {kind.arm(level) for level in LEVELS} | {kind.control}
        for arm_id, bundle in contrast.items():
            for key, calls in bundle.negative_controls.items():
                label = label_of(key)
                got = (
                    verdict_of(bundle, calls, reply=False, limit=True)
                    if label == "turn_limit"
                    else verdict_of(bundle, calls)
                )
                assert got.strict_label == label, (arm_id, seed, key, got)


# --------------------------------------------------------------------------
# the sentence and the single factor
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(KINDS.values()), ids=list(KINDS))
def test_every_arm_is_b_with_its_one_sentence_and_the_retries_it_plans(kind: Kind) -> None:
    """At twelve card seeds on both splits, as faults' arms are held: level 0 is B but `arm_id`,
    `task_id`, `pins` and the system prompt, which is B's and the sentence on a line of its own; a
    level above 0 is level 0 but those three, the reference and the negative controls; the
    control is level 0 but those three, its seeded prompt, `seq_start` and the reference's
    numbering."""
    for split in SPLITS:
        for seed in CARD_SEEDS[:12]:
            b = base(seed, split)
            zero = made(kind.arm(0), seed, split)
            assert other_fields(zero, b) == {"arm_id", "task_id", "pins", "system_prompt"}
            assert zero.system_prompt == b.system_prompt + "\n" + kind.sentence
            for level in LEVELS[1:]:
                bundle = made(kind.arm(level), seed, split)
                assert bundle.system_prompt == zero.system_prompt
                assert other_fields(bundle, zero) == {
                    "arm_id",
                    "task_id",
                    "pins",
                    "reference_calls",
                    "reference_observations",
                    "negative_controls",
                }, (split, seed, level)
            assert other_fields(made(kind.control, seed, split), zero) == {
                "arm_id",
                "task_id",
                "pins",
                "prompt",
                "seq_start",
                "reference_observations",
            }


@pytest.mark.parametrize("kind", list(KINDS.values()), ids=list(KINDS))
def test_the_control_seeds_the_fewest_read_pairs_as_long_as_the_top_levels_four(
    kind: Kind,
) -> None:
    """N26 at every card seed on both splits: read pairs of history's kind, seeded before the first
    move, whose tokens total level 4's four planned pairs within two, and the reference is level 0's
    two calls numbered from `seq_start`.  "The fewest" is three, for faults' reason
    (`tests/test_k3_control.py`, shape 3): each planned line is as many tokens as `unavailable`'s
    (the spec's M2), so two read pairs cannot reach the total and four overshoot it."""
    for split in SPLITS:
        for seed in CARD_SEEDS:
            control = made(kind.control, seed, split)
            zero = made(kind.arm(0), seed, split)
            top = made(kind.arm(4), seed, split)
            pairs = seeded(control)
            assert len(pairs) == 3, (split, seed)
            assert control.prompt[0] == {"role": "user", "content": zero.prompt}
            assert control.seq_start == len(pairs) + 1
            for index, (name, _args, observation) in enumerate(pairs):
                assert name in SPEC.read_tools and name in names(control), name
                assert (status(observation), seq(observation)) == ("ok", index + 1)
            planned_pairs = [
                pair_tokens(name, args, observation)
                for (name, args), observation in zip(
                    top.reference_calls, top.reference_observations, strict=True
                )
                if status(observation) == kind.word
            ]
            assert len(planned_pairs) == 4
            total = sum(pair_tokens(*pair) for pair in pairs)
            assert abs(total - sum(planned_pairs)) <= 2, (split, seed, total, planned_pairs)
            assert control.reference_calls == zero.reference_calls
            assert [(status(o), seq(o)) for o in control.reference_observations] == [
                ("ok", control.seq_start),
                ("ok", control.seq_start + 1),
            ]

