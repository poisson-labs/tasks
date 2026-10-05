"""The seven new knobs' names, levels, arm ids and turn budgets, frozen as tests.

`knobs.py` registers every launch knob at once -- similarity, faults, history, block, arguments,
shape and spread beside depth and the distractor dial -- so the knobs that follow add only their
tasks.  Its public names do not change (`tests/test_tg_m2_knobs.py` pins `__all__`); the new
knobs are reached through `ArmSpec`, `arm_id`, `levels` and `arms.arm_from_id`.

Shapes decided here
-------------------

**1. The arm id formats.**  `<knob>:<letter><level>`, the letter `s`, `f`, `t`, `k`, `a`, `w`
or `p`; the four knobs with a control arm (faults, block, arguments, shape) also write
`<knob>:<letter><level>+len(<letter><level>)`, the second number being the level the control
stands in for.  No `@k16`: every new knob uses one block size or varies it itself.

**2. What an arm spec refuses, beyond an unknown knob and a control that is not higher.**  A
control on similarity, history or spread, which have none; a similarity level outside 0 to 3,
since at 4 a lookalike would carry the target's own number; a negative faults or history
level.  Each is a `ValueError` at construction, as the old refusals are, and each is shown
beside an arm the same test accepts, so the refusal is pinned to its clause and not to a word
of its message.  A level outside a knob's candidate levels is still taken (`history:t12800`
builds): the candidate levels are what a card measures, not what the generator can make.

**3. Turn budgets.**  `reference_turns` is one call per turn plus the reply: the base task's two
stage calls for similarity, history, block and arguments; two plus one per planned failure for
faults; four stage calls for shape at every width; four reads and two stage calls for spread.  A
control follows its own level, never the one it stands in for.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest

from poisson_tasks.arms import arm_from_id
from poisson_tasks.knobs import ArmSpec, arm_id, levels

REPO = Path(__file__).resolve().parent.parent

LEVELS = {
    "similarity": (0, 1, 2, 3),
    "faults": (0, 1, 2, 4),
    "history": (0, 300, 600, 1200, 2400),
    "block": (8, 16, 32, 64),
    "arguments": (2, 4, 6, 8),
    "shape": (1, 2, 4),
    "spread": (1, 2, 4),
}
OLD = ("depth", "distractor")
WITH_CONTROL = ("faults", "block", "arguments", "shape")
WITHOUT_CONTROL = ("similarity", "history", "spread")

IDS = (
    (("similarity", 3, None), "similarity:s3"),
    (("faults", 4, None), "faults:f4"),
    (("faults", 0, 4), "faults:f0+len(f4)"),
    (("history", 2400, None), "history:t2400"),
    (("block", 64, None), "block:k64"),
    (("block", 8, 64), "block:k8+len(k64)"),
    (("arguments", 6, None), "arguments:a6"),
    (("arguments", 2, 8), "arguments:a2+len(a8)"),
    (("shape", 2, None), "shape:w2"),
    (("shape", 1, 4), "shape:w1+len(w4)"),
    (("spread", 4, None), "spread:p4"),
)


def spec(knob: str, level: int, control: int | None = None) -> ArmSpec:
    return ArmSpec(knob=knob, level=level, control=control, strictness="strict", split="eval",
                   generator_version="1")


def every_arm() -> list[tuple[str, int, int | None]]:
    """Every knob at every candidate level, with every control a knob admits there."""
    out = []
    for knob in OLD + tuple(LEVELS):
        for level in levels(knob):
            controls = [c for c in levels(knob) if c > level] if knob not in WITHOUT_CONTROL else []
            out += [(knob, level, control) for control in (None, *controls)]
    return out


def test_every_new_knob_has_its_cards_levels() -> None:
    for knob, expected in LEVELS.items():
        assert levels(knob) == expected, knob


@pytest.mark.parametrize("fields, expected", IDS, ids=[expected for _f, expected in IDS])
def test_each_new_format_renders_as_written(fields: tuple[str, int, int | None],
                                            expected: str) -> None:
    assert arm_id(spec(*fields)) == expected


def test_ids_are_distinct_and_read_back_to_their_arm_for_every_knob() -> None:
    seen: dict[str, tuple[str, int, int | None]] = {}
    for knob, level, control in every_arm():
        written = arm_id(spec(knob, level, control))
        assert written not in seen, (written, seen.get(written))
        seen[written] = (knob, level, control)
        back = arm_from_id(written)
        assert (back.knob, back.level, back.control) == (knob, level, control)
    assert len(seen) == len(every_arm())


@pytest.mark.parametrize("text", [
    "similarity:s1+len(s2)", "history:t300+len(t600)", "spread:p1+len(p4)",
    "faults:f2+len(f1)", "faults:f2+len(f2)", "block:k64+len(k8)",
    "faults:f02", "faults:f2+len(t4)", "block:k8@k16", "similarity:k3", "history:300",
    "shape:w1+len(w4) ", "Faults:f1", "spread:p", "arguments:a2+len()",
])
def test_an_id_no_arm_renders_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        arm_from_id(text)


def test_the_refused_ids_controls_are_taken() -> None:
    """The arms the refusals above stand beside: each differs from a refused id in the clause
    under test only."""
    for text in ("similarity:s1", "history:t300", "spread:p1", "faults:f1+len(f2)",
                 "faults:f2+len(f4)", "block:k8+len(k64)", "faults:f2", "shape:w1+len(w4)"):
        assert arm_id(arm_from_id(text)) == text


@pytest.mark.parametrize("knob", WITHOUT_CONTROL)
def test_a_knob_with_no_control_arm_refuses_any_control(knob: str) -> None:
    low, high = levels(knob)[0], levels(knob)[-1]
    assert spec(knob, low).control is None
    with pytest.raises(ValueError):
        spec(knob, low, high)


@pytest.mark.parametrize("knob", WITH_CONTROL)
def test_a_control_must_stand_in_for_a_higher_level(knob: str) -> None:
    low, high = levels(knob)[0], levels(knob)[-1]
    assert spec(knob, low, high).control == high
    for bad in ((high, low), (low, low)):
        with pytest.raises(ValueError):
            spec(knob, *bad)


@pytest.mark.parametrize("knob, refused, taken", [
    ("similarity", (4, -1, 9), (0, 3)),
    ("faults", (-1,), (0, 9)),
    ("history", (-1, -300), (0, 12800)),
])
def test_a_level_the_generator_cannot_build_is_refused(knob: str, refused: tuple[int, ...],
                                                        taken: tuple[int, ...]) -> None:
    for level in taken:
        assert spec(knob, level).level == level
    for level in refused:
        with pytest.raises(ValueError):
            spec(knob, level)


def test_the_turn_budget_of_every_arm() -> None:
    expected: dict[str, Callable[[int], int]] = {
        "similarity": lambda level: 3,
        "faults": lambda level: 2 + level + 1,
        "history": lambda level: 3,
        "block": lambda level: 3,
        "arguments": lambda level: 3,
        "shape": lambda level: 5,
        "spread": lambda level: 7,
    }
    for knob, level, control in every_arm():
        if knob in OLD:
            continue
        s = spec(knob, level, control)
        assert s.reference_turns == expected[knob](level), (knob, level, control)
        for slack in (0, 3):
            assert s.max_turns(slack) == s.reference_turns + slack


def test_the_faults_control_takes_its_own_levels_budget() -> None:
    assert spec("faults", 0, 4).reference_turns == spec("faults", 0).reference_turns == 3


# --------------------------------------------------------------------------
# the new literals live in knobs.py
# --------------------------------------------------------------------------

# Numbers that only the new knobs' design produces: the lookalike count, the history levels and
# the largest block.
NEW_LITERALS = {12, 300, 600, 1200, 2400, 64}


@pytest.mark.parametrize("module", ["tasks.py", "surface.py"])
def test_the_new_knobs_literals_are_not_minted_outside_knobs(module: str) -> None:
    """The rule `test_sf9` holds for the old literals, extended to the new knobs and to
    `surface.py`: checked at module level, where a second freeze would live."""
    tree = ast.parse((REPO / "src" / "poisson_tasks" / module).read_text())
    minted = set()
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            minted |= {c.value for c in ast.walk(node.value)
                       if isinstance(c, ast.Constant) and isinstance(c.value, int)}
    assert not minted & NEW_LITERALS, sorted(minted & NEW_LITERALS)

