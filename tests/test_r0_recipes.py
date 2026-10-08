"""The recipe table, frozen as tests.

The invariant is R0.1 of the knobs plan, from spec §17.1, §17.2 and §17.4: `RECIPES` in
`poisson_tasks.arms` holds the eight recipes, each derived from `levels` and the list of shipped
knobs; a recipe whose knobs have not shipped is not offered; before the probe (K9) only
`first-look` and `card` are.  R0.2 and R0.3, the preset key and `--recipe`, are in
`tests/test_r0_config.py`.

Invariants and the tests that hold them
---------------------------------------

| invariant | tests |
|---|---|
| R0.1 the table: eight recipes, spec §17.2's rows | `test_the_table_is_the_eight_recipes_in_the_specs_order`, `test_with_every_knob_shipped_each_recipe_is_its_spec_row`, `test_the_card_recipe_is_the_published_design` |
| R0.1 derived from `levels` | `test_the_recipes_follow_levels_rather_than_a_table_written_out` |
| R0.1 offered turns on the shipped knobs | `test_what_is_offered_turns_on_the_shipped_knobs`, `test_before_the_probe_only_first_look_and_card_are_offered` |
| R0.1 unbuilt knobs stay refused | `test_every_arm_offered_generates_and_only_a_probe_knob_can_ship` |
| R0.2 the preset key takes the recipes and `custom` | `tests/test_r0_config.py`: `test_every_recipe_offered_is_a_preset_and_reads_back`, `test_a_recipe_not_offered_is_refused_in_one_line_naming_it_and_its_knobs`, `test_the_written_file_lists_only_the_recipes_offered`, `test_a_recipe_sets_inits_tasks_and_attempts_and_the_flags_override`, `test_custom_is_unchanged` |
| R0.3 `--recipe`, with `--measure` its alias | `tests/test_r0_config.py`: `test_recipe_and_measure_give_the_same_config`, `test_recipe_is_the_flag_init_names_and_writes`, `test_the_last_of_recipe_and_measure_wins` |
| R0.2 FD1's frozen tests stay green | the whole suite, at FD1's file digests |

Shapes decided here
-------------------

**1. The names.**  `RECIPES` is a read-only mapping from name to `Recipe`, all eight, in spec
§17.2's order.  `SHIPPED_KNOBS` is the knobs the probe has shipped (spec K-P3, §9.6), and
`RECIPES == recipe_table(SHIPPED_KNOBS)`.  `recipe_table(shipped)` is the table for any list of
shipped knobs, so what "offered" turns on is testable without waiting for the probe, and a knob
shipping is one edit to `SHIPPED_KNOBS` with no test edit.  It takes only the seven probe knobs and
refuses anything else in one line naming it: a misspelt knob would otherwise leave a recipe
withdrawn with nothing said, and depth and the distractor dial ship with the published cards.

**2. A `Recipe`** carries `name`, `asks` (spec §17.2's "what it asks"), `knobs` (every knob its
design draws on, in the row's order), `arms` (arm ids it runs now), `tasks_per_level`,
`attempts`, `episodes` (arms times tasks times attempts), `offered`, and `waiting` (its knobs
that have not shipped).

**3. What "offered" turns on.**  Depth and the distractor dial are on the published cards and
need no probe: they are always available.  Each of the other seven knobs needs the probe.  A
recipe is offered when it uses only the published cards' knobs, or when at least one of its other
knobs has shipped; the arms of a knob that has not shipped are dropped (spec §17.2: "drops the
unshipped arms").  A recipe not offered runs no arm.  So `planning` (depth and shape) is not
offered before shape ships, rather than offered as `first-look` again; and `profile` waits for
its first probe knob.  This is the one reading under which spec §17.2's mixing rule and the plan's
"before K9 only `first-look` and `card`" agree; it is a yes/no in the session's rulings.

**4. Derived from `levels`.**  A recipe names a knob and which of its levels: all of them; the
first and last; or the first, the middle (`levels[len(levels) // 2]`) and the last.  So depth's
1, 3, 8 and history's 0, 600, 2400 are one rule.  `card` is the published design: every level of
each published knob, then that knob's control arms, in `calibration.arm_specs()`'s order.

**5. Every recipe is strict with no control arm**, but `card`, which is the published design.
An arm id carries no strictness; a recipe's arms resolve to strict arms (`tests/test_r0_config.py`).
"""

from __future__ import annotations

import itertools
import json
import textwrap
from typing import Any

import pytest

from poisson_tasks.tasks import generate
from tests.r0_support import (
    NAMES,
    PROBE_KNOBS,
    PUBLISHED_KNOBS,
    ROWS,
    arms,
    card_arms,
    fresh,
    full_design,
    in_order,
    knob_of,
    tasks_and_attempts,
)

SEED = 404


def expected(name: str, shipped: tuple[str, ...]) -> dict[str, Any]:
    """Shape 3, written out: what `recipe_table(shipped)` must say about one recipe."""
    design = full_design(name)
    knobs = in_order(knob_of(arm) for arm in design)
    probe = tuple(knob for knob in knobs if knob not in PUBLISHED_KNOBS)
    offered = not probe or any(knob in shipped for knob in probe)
    kept = (
        tuple(arm for arm in design if knob_of(arm) in PUBLISHED_KNOBS or knob_of(arm) in shipped)
        if offered
        else ()
    )
    tasks, attempts = tasks_and_attempts(name)
    return {
        "knobs": knobs,
        "arms": kept,
        "offered": offered,
        "waiting": tuple(knob for knob in probe if knob not in shipped),
        "episodes": len(kept) * tasks * attempts,
    }


def seen(recipe: Any) -> dict[str, Any]:
    return {
        "knobs": tuple(recipe.knobs),
        "arms": tuple(recipe.arms),
        "offered": recipe.offered,
        "waiting": tuple(recipe.waiting),
        "episodes": recipe.episodes,
    }


# --------------------------------------------------------------------------
# R0.1: the table
# --------------------------------------------------------------------------


def test_the_table_is_the_eight_recipes_in_the_specs_order() -> None:
    """Bugs caught: a recipe left out or renamed; the table in another order; a recipe filed
    under a key other than its own name."""
    table = arms().RECIPES
    assert tuple(table) == NAMES
    for name, recipe in table.items():
        assert isinstance(recipe, arms().Recipe), name
        assert recipe.name == name
    for name, recipe in arms().recipe_table(PROBE_KNOBS).items():
        assert recipe.name == name


def test_with_every_knob_shipped_each_recipe_is_its_spec_row() -> None:
    """Spec §17.2 row by row.  Bugs caught: history's middle level read as 1200; shape's top as
    w2; `profile` at 20 tasks and one attempt; a control arm in a recipe; a recipe's knobs in
    another order; episodes counted at ten tasks for every recipe."""
    table = arms().recipe_table(PROBE_KNOBS)
    for name, (asks, design, tasks, attempts, episodes) in ROWS.items():
        recipe = table[name]
        assert recipe.asks == asks, name
        assert tuple(recipe.arms) == design, name
        assert tuple(recipe.knobs) == in_order(knob_of(arm) for arm in design), name
        assert (recipe.tasks_per_level, recipe.attempts) == (tasks, attempts), name
        assert recipe.episodes == episodes, name
        assert recipe.offered and tuple(recipe.waiting) == (), name
        assert not any("+" in arm for arm in recipe.arms), name


def test_the_card_recipe_is_the_published_design() -> None:
    """`card` is `calibration.arm_specs()`, sixty tasks and five attempts, offered whatever has
    shipped.  Bugs caught: the control arms left out; the distractor dial left out because no
    probe shipped it; the arms in another order; the card at ten tasks."""
    for table in (arms().RECIPES, arms().recipe_table(()), arms().recipe_table(PROBE_KNOBS)):
        card = table["card"]
        assert tuple(card.arms) == card_arms()
        assert (card.tasks_per_level, card.attempts) == (60, 5)
        assert card.episodes == len(card_arms()) * 60 * 5
        assert card.offered and tuple(card.waiting) == ()
        assert tuple(card.knobs) == PUBLISHED_KNOBS


def test_the_recipes_follow_levels_rather_than_a_table_written_out() -> None:
    """Shape 4.  With `knobs.levels` giving other levels before `arms` is imported, every recipe
    follows them.  Bug caught: any recipe's levels written out by hand."""
    other = {
        "depth": (1, 2, 3, 4, 5, 6, 7),
        "history": (0, 100, 200, 400, 800, 1600),
        "block": (8, 24, 40),
        "faults": (0, 3),
        "shape": (1, 2, 4, 8),
        "spread": (1, 3),
        "arguments": (2, 5, 8, 9),
        "similarity": (0, 2),
        "distractor": (0, 1, 2),
    }
    code = textwrap.dedent(f"""\
        import json
        import poisson_tasks.knobs as knobs
        other = {other!r}
        knobs.levels = lambda knob: other[knob]
        import poisson_tasks.arms as arms
        table = arms.recipe_table({PROBE_KNOBS!r})
        print(json.dumps({{name: list(recipe.arms) for name, recipe in table.items()}}))
    """)
    got = json.loads(fresh(code))

    def ids(knob: str, chosen: tuple[int, ...]) -> list[str]:
        letter = {
            "depth": "d",
            "similarity": "s",
            "faults": "f",
            "history": "t",
            "block": "k",
            "arguments": "a",
            "shape": "w",
            "spread": "p",
        }[knob]
        return [f"{knob}:{letter}{level}" for level in chosen]

    def ends(knob: str) -> tuple[int, ...]:
        return other[knob][0], other[knob][-1]

    def three(knob: str) -> tuple[int, ...]:
        found = other[knob]
        return found[0], found[len(found) // 2], found[-1]

    assert got["first-look"] == ids("depth", three("depth")) == ["depth:d1", "depth:d4", "depth:d7"]
    assert got["tool-choice"] == ids("similarity", ends("similarity")) + ids("block", ends("block"))
    assert got["error-recovery"] == ids("faults", other["faults"])
    assert got["long-sessions"] == ids("history", three("history"))
    assert got["planning"] == ids("depth", three("depth")) + ids("shape", ends("shape"))
    assert got["reading-and-filling"] == (
        ids("spread", ends("spread")) + ids("arguments", ends("arguments"))
    )
    assert got["profile"] == [
        arm for knob in ("depth", *PROBE_KNOBS) for arm in ids(knob, ends(knob))
    ]
    card = [f"depth:d{level}" for level in other["depth"]] + ["depth:d1+h8", "depth:d2+h5"]
    card += [f"distractor:r{level}@k16" for level in other["distractor"]]
    card += ["distractor:r0+len(r8)@k16", "distractor:r2+len(r14)@k16"]
    assert got["card"] == card


# --------------------------------------------------------------------------
# R0.1: what "offered" turns on
# --------------------------------------------------------------------------


def test_what_is_offered_turns_on_the_shipped_knobs() -> None:
    """Shape 3, over every set of shipped probe knobs (128 of them).  Bugs caught: depth
    counted as a shipped knob, so `planning` and `profile` are offered before the probe; a mixed
    recipe offered only when all its knobs shipped; an unshipped knob's arms kept; a recipe not
    offered still listing arms; `waiting` naming a shipped knob."""
    for size in range(len(PROBE_KNOBS) + 1):
        for shipped in itertools.combinations(PROBE_KNOBS, size):
            table = arms().recipe_table(shipped)
            assert tuple(table) == NAMES, shipped
            for name in NAMES:
                assert seen(table[name]) == expected(name, shipped), (shipped, name)


def test_before_the_probe_only_first_look_and_card_are_offered() -> None:
    """The plan's R0.1, and the package's table is the shipped list's.  Bugs caught: the
    package's table built as if every knob had shipped; any recipe offered with nothing shipped."""
    before = arms().recipe_table(())
    assert [name for name, recipe in before.items() if recipe.offered] == ["first-look", "card"]
    for name, recipe in before.items():
        if not recipe.offered:
            assert tuple(recipe.arms) == () and recipe.episodes == 0, name
            assert tuple(recipe.waiting), name
    shipped = tuple(arms().SHIPPED_KNOBS)
    assert dict(arms().RECIPES) == dict(arms().recipe_table(shipped))


def test_every_arm_offered_generates_and_only_a_probe_knob_can_ship() -> None:
    """Unbuilt knobs stay refused: every arm of every recipe the package offers makes a task, and
    `recipe_table` takes only the seven probe knobs.  Bugs caught: a knob the generator does not
    make yet (block, on this tree) put in `SHIPPED_KNOBS`; a misspelt knob taken silently, so a
    recipe stays withdrawn with nothing said."""
    shipped = tuple(arms().SHIPPED_KNOBS)
    assert set(shipped) <= set(PROBE_KNOBS) and len(set(shipped)) == len(shipped), shipped
    for name, recipe in arms().RECIPES.items():
        for arm in recipe.arms if recipe.offered else ():
            bundle = generate(arms().arm_from_id(arm), SEED)
            assert bundle.arm_id == arm, (name, arm)
    for wrong in ("simliarity", "depth", "distractor", "Faults"):
        with pytest.raises(ValueError) as error:
            arms().recipe_table((wrong,))
        assert "\n" not in str(error.value) and wrong in str(error.value), str(error.value)
