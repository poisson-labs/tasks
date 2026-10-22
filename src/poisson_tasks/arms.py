"""Arms by their readable id, the one generator-version constant, the pin ledger in words, the
recipes, and each probe knob's measured status.

The names cannot go in `knobs.py`, whose public surface frozen tests pin exactly;
`tests/test_fd1_arms.py` and `tests/test_r0_recipes.py` say what each one does.  Importing this
module imports no `verifiers` and none of `tasks`, `calibration` and `export`.

The module also holds, privately, which arms the published cards measured.  `calibration` is
where that design is declared (`arm_specs()`), and it cannot be imported here or by the two
modules that need the answer without it: `config` reads a settings file with no tokenizer in the
environment, and `export` is imported by `calibration`.  The tests hold this copy equal to
`calibration`'s.
"""

from __future__ import annotations

import dataclasses as _dataclasses
import json as _json
import pathlib as _pathlib
import types as _types
from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import Any as _Any

from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.knobs import PinReport as _PinReport
from poisson_tasks.knobs import _parse_arm_id, _render_arm_id
from poisson_tasks.knobs import levels as _levels
from poisson_tasks.knobs import pin_ledger as _pin_ledger

__all__ = [
    "arm_from_id",
    "DEFAULT_GENERATOR_VERSION",
    "describe_pins",
    "knob_status",
    "Recipe",
    "RECIPES",
    "SHIPPED_KNOBS",
    "recipe_table",
]

DEFAULT_GENERATOR_VERSION = "1"

# The published cards' control arms, as (level, the level it stands in for): equal to
# `calibration.D_CONTROLS` and `calibration.R_CONTROLS`.
_CONTROL_PAIRS: dict[str, tuple[tuple[int, int], ...]] = {
    "depth": ((1, 8), (2, 5)),
    "distractor": ((0, 8), (2, 14)),
}
_CARD_STRICTNESS = "strict"
_CARD_SPLIT = "eval"


def arm_from_id(
    arm_id: str,
    *,
    strictness: str = "strict",
    split: str = "eval",
    generator_version: str = DEFAULT_GENERATOR_VERSION,
) -> _ArmSpec:
    """The arm an id names: the inverse of `knobs.arm_id`.

    An id carries the knob, the level and the control, and the other three fields are the
    caller's.  It is read with the parser `check_pins` uses, and then must render back to itself,
    so only the ids `knobs.arm_id` writes are taken: that parser also reads `depth:d03` and
    `distractor:r4@k8`, and neither is an arm's id.  The level is not judged here; `depth:d4`
    is a well-formed id, and whether an arm at that level may run is the caller's to say.
    """
    if not isinstance(arm_id, str):
        raise ValueError(f"an arm id is text such as depth:d3; got {type(arm_id).__name__}")
    parsed = _parse_arm_id(arm_id)
    spec = _ArmSpec(
        knob=parsed.knob,
        level=parsed.level,
        control=parsed.control,
        strictness=strictness,
        split=split,
        generator_version=generator_version,
    )
    canonical = _render_arm_id(spec.knob, spec.level, spec.control)
    if canonical != arm_id:
        raise ValueError(f"{arm_id!r} is not an arm id: the arm it reads as is written {canonical}")
    return spec


def _on_a_published_card(spec: _ArmSpec) -> bool:
    """Whether `spec` is one of the published cards' fourteen arms, as the cards measured it.

    The cards' knobs are the table's; an arm of any other knob, similarity's first, is on no
    card at any level.
    """
    if (spec.strictness, spec.split, spec.generator_version) != (
        _CARD_STRICTNESS,
        _CARD_SPLIT,
        DEFAULT_GENERATOR_VERSION,
    ):
        return False
    if spec.knob not in _CONTROL_PAIRS:
        return False
    if spec.control is None:
        return spec.level in _levels(spec.knob)
    return (spec.level, spec.control) in _CONTROL_PAIRS[spec.knob]


def _listed(items: list[str]) -> str:
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def describe_pins(report: _PinReport) -> str:
    """A pin report as one sentence in plain words.

    It says which knob's contrast it is, across which arms, and whether everything else was held
    fixed.  A refused report names each thing that differed, and a report with something measured
    and reported (the distractor knob's tool-block size) names that.  Each is named as the pin
    ledger names it; the ledger's own detail strings are left to the report.
    """
    names = {row.row_id: row.held for row in _pin_ledger(report.knob)}
    arms = _listed(sorted(report.records))
    contrast = f"The {report.knob} contrast across {arms}"
    reported = [names[row_id] for row_id, _ in report.reported]
    if report.violations:
        differed = [names[row_id] for row_id, _ in report.violations]
        sentence = (
            f"{contrast} is refused, because its arms differ in more than the {report.knob} "
            f"level: {'; '.join(differed)}"
        )
        if reported:
            sentence += f" (also reported: {'; '.join(reported)})"
        return sentence + "."
    sentence = f"{contrast} holds everything but the {report.knob} level fixed"
    if reported:
        sentence += (
            f", apart from what is measured and reported rather than held: {'; '.join(reported)}"
        )
    return sentence + "."


# ---------------------------------------------------------------------------
# recipes
# ---------------------------------------------------------------------------

# The knobs the knob probe shipped: each made tasks harder on at least one of the
# two models it ran on, and easier at the top on neither.  Depth and the distractor dial are on the
# published cards and need no probe.  The other four probe knobs did not ship: they stay in the
# generator and their arms work, and they reach no recipe.  `knob_status()` says what each knob did
# on each model.
SHIPPED_KNOBS: tuple[str, ...] = ("faults", "history", "shape")

_PROBE_KNOBS = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")

# Which of a knob's levels a recipe takes.
_EVERY = "every"
_ENDS = "first and last"
_THREE = "first, middle and last"


def _chosen(knob: str, which: str) -> tuple[int, ...]:
    found = _levels(knob)
    if which == _EVERY:
        return found
    if which == _ENDS:
        return found[0], found[-1]
    return found[0], found[len(found) // 2], found[-1]


@_dataclasses.dataclass(frozen=True)
class Recipe:
    """A ready-made measurement: a named set of arms, a task count and an attempt count.

    `knobs` is every knob the recipe's design draws on; `arms` is what it runs now, the arms of
    knobs that have not shipped left out, and nothing when it is not offered; `waiting` is its
    knobs that have not shipped.
    """

    name: str
    asks: str
    knobs: tuple[str, ...]
    arms: tuple[str, ...]
    tasks_per_level: int
    attempts: int
    offered: bool
    waiting: tuple[str, ...]

    @property
    def episodes(self) -> int:
        return len(self.arms) * self.tasks_per_level * self.attempts


# A recipe holds the name, what it asks, each knob with the levels it takes, the tasks per
# level and the attempts.  `card` is the published cards' design and is built apart.
_ROWS: tuple[tuple[str, str, tuple[tuple[str, str], ...], int, int], ...] = (
    ("first-look", "where does depth start to hurt?", (("depth", _THREE),), 10, 1),
    (
        "tool-choice",
        "can it pick the right tool among lookalikes and in a long list?",
        (("similarity", _ENDS), ("block", _ENDS)),
        10,
        1,
    ),
    ("error-recovery", "does it retry when a call fails?", (("faults", _EVERY),), 10, 1),
    (
        "long-sessions",
        "does earlier work in the conversation throw it off?",
        (("history", _THREE),),
        10,
        1,
    ),
    ("planning", "chains and parallel steps", (("depth", _THREE), ("shape", _ENDS)), 10, 1),
    (
        "reading-and-filling",
        "can it assemble a value from outputs and fill arguments exactly?",
        (("spread", _ENDS), ("arguments", _ENDS)),
        10,
        1,
    ),
    (
        "profile",
        "one line per knob: how much each moves this model",
        tuple((knob, _ENDS) for knob in ("depth", *_PROBE_KNOBS)),
        20,
        2,
    ),
)
_CARD = ("card", "the published cards' full design")
_CARD_TASKS = 60
_CARD_ATTEMPTS = 5


def _card_design() -> tuple[str, ...]:
    """Every level of each published knob, then that knob's control arms: `arm_specs()`'s order."""
    out: list[str] = []
    for knob, pairs in _CONTROL_PAIRS.items():
        out += [_render_arm_id(knob, level, None) for level in _levels(knob)]
        out += [_render_arm_id(knob, level, control) for level, control in pairs]
    return tuple(out)


def _recipe(
    name: str,
    asks: str,
    design: tuple[str, ...],
    tasks_per_level: int,
    attempts: int,
    shipped: frozenset[str],
) -> Recipe:
    knobs = tuple(dict.fromkeys(_parse_arm_id(arm).knob for arm in design))
    probed = tuple(knob for knob in knobs if knob not in _CONTROL_PAIRS)
    offered = not probed or any(knob in shipped for knob in probed)
    usable = set(_CONTROL_PAIRS) | shipped
    return Recipe(
        name=name,
        asks=asks,
        knobs=knobs,
        arms=tuple(arm for arm in design if _parse_arm_id(arm).knob in usable) if offered else (),
        tasks_per_level=tasks_per_level,
        attempts=attempts,
        offered=offered,
        waiting=tuple(knob for knob in probed if knob not in shipped),
    )


def recipe_table(shipped: _Iterable[str]) -> _Mapping[str, Recipe]:
    """The recipes of the recipe table with `shipped` as the knobs the probe has shipped.

    A recipe is offered when it uses only the published cards' knobs (depth and the distractor
    dial), or when at least one of its other knobs has shipped; the arms of a knob that has not
    shipped are left out.  `shipped` takes only the seven knobs a probe ships.
    """
    chosen = tuple(shipped)
    for knob in chosen:
        if knob not in _PROBE_KNOBS:
            raise ValueError(
                f"{knob!r} is not a knob the probe ships; those are {_listed(list(_PROBE_KNOBS))}"
            )
    given = frozenset(chosen)
    table: dict[str, Recipe] = {}
    for name, asks, parts, tasks_per_level, attempts in _ROWS:
        design = tuple(
            _render_arm_id(knob, level, None)
            for knob, which in parts
            for level in _chosen(knob, which)
        )
        table[name] = _recipe(name, asks, design, tasks_per_level, attempts, given)
    name, asks = _CARD
    table[name] = _recipe(name, asks, _card_design(), _CARD_TASKS, _CARD_ATTEMPTS, given)
    return _types.MappingProxyType(table)


RECIPES: _Mapping[str, Recipe] = recipe_table(SHIPPED_KNOBS)


# ---------------------------------------------------------------------------
# what the knob probe measured
# ---------------------------------------------------------------------------

_STATUS_PATH = _pathlib.Path(__file__).resolve().parent / "knob_status.json"


def knob_status() -> dict[str, _Any]:
    """Each probe knob's measured status on each model the knob probe ran, and whether it shipped.

    Read from the package's `knob_status.json`, a fresh copy on every call.  `models` names each
    model the probe ran.  `knobs` maps the seven probe knobs, in the probe's order, to whether the
    knob `shipped`, its `outcome`, a line that `says` it in words, and per model its `status` (one
    of bites, does not bite, top easier and cannot tell), its `base` and `top` arms with each
    arm's strict pass@1, and each contrast's `delta` with its 95% `interval`.  `probe` says how
    it was measured.  "Cannot tell" replaces "does not bite" where the base arm passed below
    `floor`, so a drop of the rule's size could not show, and replaces "top easier" where the
    top arm passed above `ceiling`; a bite is always a bite.
    """
    table: dict[str, _Any] = _json.loads(_STATUS_PATH.read_text(encoding="utf-8"))
    return table
