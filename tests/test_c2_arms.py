"""C2.1: the version 2 card's design, 56 arms in the order they run.

The design: every level of every built-in dial but distractor, with every control arm the dial
has (52 arms), then the four arms on acme's tool file, on the card's sixty tasks at five attempts,
each episode capped at 32 model calls.  The arms run bases first (each dial's first level), then
tops, then controls, then the middle levels, then the own-tools arms, so a stop costs middle
levels and never a decision pair.

The list is typed in `tests/c2_support.py` from the design's table, not read from the module
under test.  Readings made here: inside each of the five groups the arms keep the table's own
order of dials; depth's two controls are the published design's (`d1+h8`, `d2+h5`), and every
other control is the dial's first level standing in for its last.
"""

from __future__ import annotations

from poisson_tasks import calibration as cal
from poisson_tasks.knobs import arm_id, levels
from tests.c2_support import (
    ARMS,
    ATTEMPTS,
    BASES,
    BUILT_IN_ARMS,
    CONTROLS,
    DESIGN,
    EPISODES,
    MIDDLES,
    OWN_ARMS,
    OWN_TABLE,
    PHASE1_EPISODES,
    PHASE1_SEEDS,
    TABLE,
    TASKS,
    TOPS,
    card_run,
    knob_of,
)

LETTERS = {
    "depth": "d",
    "similarity": "s",
    "faults": "f",
    "history": "t",
    "block": "k",
    "arguments": "a",
    "shape": "w",
    "spread": "p",
    "timeouts": "o",
    "ratelimits": "r",
    "baddata": "b",
    "landed": "l",
    "lagged": "g",
}


def test_the_typed_list_is_the_designs_table_and_nothing_else() -> None:
    """A guard on the test's own list: its five groups are the table's 52 arms and the four on
    acme's tool file, each once."""
    table = [f"{knob}:{arm}" for knob, row in TABLE.items() for arm in row]
    own = [f"{knob}:{arm}" for knob, row in OWN_TABLE.items() for arm in row]
    assert len(table) == 52 and sorted(BUILT_IN_ARMS) == sorted(table)
    assert list(OWN_ARMS) == own
    assert len(ARMS) == len(set(ARMS)) == 56
    assert (len(BASES), len(TOPS), len(CONTROLS), len(MIDDLES)) == (11, 11, 8, 22)


def test_the_design_is_the_56_arms_in_the_order_they_run() -> None:
    specs = cal.arm_specs(DESIGN)
    assert tuple(arm_id(spec) for spec in specs) == ARMS


def test_the_run_order_is_bases_tops_controls_middles_then_own_tools() -> None:
    made = [arm_id(spec) for spec in cal.arm_specs(DESIGN)]
    assert tuple(made[:11]) == BASES
    assert tuple(made[11:22]) == TOPS
    assert tuple(made[22:30]) == CONTROLS
    assert tuple(made[30:52]) == MIDDLES
    assert tuple(made[52:]) == OWN_ARMS


def test_distractor_is_absent_and_every_other_built_in_dial_has_every_level() -> None:
    specs = cal.arm_specs(DESIGN)
    assert "distractor" not in {spec.knob for spec in specs}
    for knob in TABLE:
        plain = sorted(spec.level for spec in specs if spec.knob == knob and spec.control is None)
        assert tuple(plain) == levels(knob), knob
    for knob in OWN_TABLE:
        own = [spec.level for spec in specs if spec.knob == knob]
        assert tuple(own) == levels(knob) == (0, 1), knob


def test_the_levels_are_read_from_the_dials_and_the_controls_from_their_tables() -> None:
    """Each plain arm's id is its dial's letter and a level `levels()` gives; a control is the
    dial's first level standing in for its last, and depth's are the published design's two."""
    for arm in BUILT_IN_ARMS + OWN_ARMS:
        knob = knob_of(arm)
        if "+" in arm:
            continue
        assert arm in {f"{knob}:{LETTERS[knob]}{level}" for level in levels(knob)}, arm
    controls = {
        knob: [(s.level, s.control) for s in cal.arm_specs(DESIGN) if s.knob == knob and s.control]
        for knob in TABLE
    }
    assert controls["depth"] == list(cal.D_CONTROLS)
    for knob in ("faults", "block", "arguments", "shape", "timeouts", "ratelimits"):
        assert controls[knob] == [(levels(knob)[0], levels(knob)[-1])], knob
    for knob in ("similarity", "history", "spread", "baddata"):
        assert controls[knob] == [], knob


def test_every_arm_is_a_strict_eval_arm_at_the_frozen_labels() -> None:
    specs = cal.arm_specs(DESIGN)
    assert {(spec.strictness, spec.split) for spec in specs} == {("strict", "eval")}
    assert {spec.generator_version for spec in specs[:52]} == {"4"}
    assert {spec.generator_version for spec in specs[52:]} == {"own-4"}


def test_the_published_generator_0_design_is_still_its_fourteen_arms() -> None:
    """A guard: the archive's cards rebuild from `arm_specs()` as it was."""
    old = [arm_id(spec) for spec in cal.arm_specs()]
    assert len(old) == 14 and {knob_of(arm) for arm in old} == {"depth", "distractor"}


def test_the_drivers_design_is_the_same_arms_seeds_and_counts() -> None:
    run = card_run()
    assert run.ARMS == ARMS == tuple(arm_id(spec) for spec in cal.arm_specs(DESIGN))
    assert (run.BASES, run.TOPS, run.CONTROLS, run.MIDDLES, run.OWN_ARMS) == (
        BASES,
        TOPS,
        CONTROLS,
        MIDDLES,
        OWN_ARMS,
    )
    design = run.DESIGN
    assert design.arms == ARMS
    assert tuple(design.seeds) == tuple(cal.seed_list()) and len(design.seeds) == TASKS == 60
    assert design.attempts == ATTEMPTS == 5
    assert tuple(design.phase1_seeds) == PHASE1_SEEDS
    assert len(design.arms) * len(design.seeds) * design.attempts == EPISODES == 16_800
    assert len(design.arms) * len(design.phase1_seeds) == PHASE1_EPISODES == 168
    assert EPISODES + PHASE1_EPISODES == 16_968


def test_phase_1s_seeds_are_the_knob_probes_first_three_and_on_no_card() -> None:
    from poisson_tasks import knob_probe as probe

    assert tuple(probe.PHASE1_SEEDS) == PHASE1_SEEDS
    assert not set(PHASE1_SEEDS) & set(cal.seed_list())


def test_every_episode_is_capped_at_32_model_calls() -> None:
    from poisson_tasks.taskset import MAX_MODEL_CALLS

    assert card_run().MAX_MODEL_CALLS == 32 == MAX_MODEL_CALLS
