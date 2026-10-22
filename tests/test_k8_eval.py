"""Information spread opened: `eval`, the levels it cannot build, and what is still not offered,
frozen as tests.

The standing decisions for a knob that gains tasks: the `eval` command takes its arms, the
published cards' table answers for the knob so that no arm raises a `KeyError`, and an arm no
published card covers gets the one note saying so; the census takes them.  Spread is the last knob
without tasks: once it has them no knob is left for the generator or `eval` to refuse for want of
tasks, which the frozen `tests/test_k2_eval.py` held for every knob in turn (its list of arms loses
its last arm, `spread:p2`, in this knob's retrofit commit, a decided retrofit).  `tasks.toml` and
`init` do not offer information spread; the knob probe did not ship it (decided 2026-10-14), so
the shipped-knobs list the recipes read leaves it out.

Shapes decided here
-------------------

**1. Every spread arm is on no published card**: neither card measured the knob.  `eval` takes the
card's three levels and 3, the one level between them the generator can build (spread
from 1 to 4), each with the one plain note (one `UserWarning`, one line, naming the arm by its id;
`tests/test_fd1_export_arm.py`), by its id and as the six fields, and the tasks it loads are that
arm's.  The note's words are not pinned.  The census takes every arm `eval` takes (its count is
pending a decision, `tests/test_k8_pending_census.py`).

**2. A level the knob cannot build is refused in one line naming the knob**, as decided 2026-10-04
(spread outside 1 to 4), and so is any control (spread has none): when the arm is made from its id,
and by `eval`, by id and as the six fields.  The frozen `tests/test_k1_pending_level_bounds.py` and
`tests/test_k1_knobs.py` pin that these are refused;  this pins that each refusal is one line naming
the knob.  On `main`, before the spread knob, `eval` refuses the six fields for the knob itself (it
has no tasks); after it, for the level or the control.

**3. A knob no generator knows** is refused by `eval` as the six fields in one line naming it.  It
is the refusal that turned away the knobs without tasks; from the spread knob on, only a name that
is no knob reaches it, and a build of spread changes the list of knobs it names.  This passes on
`main` by design and holds the one-line rule over that list's rewording; the list's words are not
pinned.  (The generator's own refusal of a knob without tasks can no longer be reached: `ArmSpec`
refuses a name that is no knob before the generator sees it.)

**4. Spread is not offered**: the project file and `init`'s flags refuse `spread` by the key that
names it; the file `init` writes names none of the seven probe knobs; the knob probe did not ship
spread (decided 2026-10-14, a recorded retrofit of this file), so the package's list of shipped
knobs leaves it out and the recipe that measures spread (`reading-and-filling`) is not offered and
waits on it.
"""

from __future__ import annotations

import dataclasses
import importlib
import warnings
from typing import Any

import pytest

from poisson_tasks import arms as arms_module
from poisson_tasks import config as config_module
from poisson_tasks.arms import arm_from_id
from poisson_tasks.knobs import arm_id
from poisson_tasks.tasks import generate, structure_space
from tests.k8_support import ARMS

TASKSET_ID = "poisson-tasks"
SEEDS = [404, 55]
# The knobs no probe has yet shown to bite: none is offered before its probe.
UNPROBED = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")
UNBUILDABLE = ("spread:p0", "spread:p5", "spread:p8", "spread:p1+len(p4)", "spread:p2+len(p4)")


def loaders() -> Any:
    return importlib.import_module("verifiers.v1.utils.loaders")


def taskset_config(arm_: Any, seeds: list[int] = SEEDS) -> Any:
    return loaders().taskset_config_type(TASKSET_ID)(id=TASKSET_ID, arm=arm_, seeds=seeds)


def notes(arm_: Any) -> tuple[Any, list[str]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = taskset_config(arm_)
    return config, [str(w.message) for w in caught if issubclass(w.category, UserWarning)]


@pytest.mark.parametrize("text", ARMS)
def test_eval_takes_every_spread_arm_with_the_one_note_for_an_arm_no_card_covers(
    text: str,
) -> None:
    """Shape 1.  By its id and as the six fields: taken, one note naming the arm, and the tasks it
    loads are that arm's.  `depth:d3`, a card arm, takes none."""
    spec = arm_from_id(text)
    for given in (arm_id(spec), dataclasses.asdict(spec)):
        config, said = notes(given)
        assert config.arm == dataclasses.asdict(spec)
        assert len(said) == 1, said
        assert arm_id(spec) in said[0] and "\n" not in said[0], said[0]
        tasks = list(loaders().load_taskset(config).load())
        assert [task.data.arm_id for task in tasks] == [arm_id(spec)] * len(SEEDS)
        assert [task.key for task in tasks] == [generate(spec, seed).task_id for seed in SEEDS]
    assert structure_space(spec) > 0
    _config, said = notes("depth:d3")
    assert said == []


def one_line(refusal: BaseException) -> str:
    """The refusal's message: a configuration error's one error, or the exception's text."""
    errors = refusal.errors() if hasattr(refusal, "errors") else []
    if errors:
        assert len(errors) == 1, errors
        return str(errors[0]["msg"])
    return str(refusal)


def fields_of(text: str) -> dict[str, Any]:
    """An arm id's six fields, as a mapping `eval` takes, without making the arm."""
    level, _plus, control = text.removeprefix("spread:p").partition("+len(p")
    return {
        "knob": "spread",
        "level": int(level),
        "control": int(control.rstrip(")")) if control else None,
        "strictness": "strict",
        "split": "eval",
        "generator_version": "1",
    }


@pytest.mark.parametrize("text", UNBUILDABLE)
def test_a_level_the_knob_cannot_build_is_refused_in_one_line_naming_it(text: str) -> None:
    """Shape 2."""
    asked: list[Any] = [
        lambda: arm_from_id(text),
        lambda: taskset_config(text),
        lambda: taskset_config(fields_of(text)),
    ]
    for ask in asked:
        with pytest.raises(ValueError) as refused:
            ask()
        message = one_line(refused.value)
        assert "\n" not in message and "spread" in message, message


def test_eval_refuses_a_knob_no_generator_knows_in_one_line_naming_it() -> None:
    """Shape 3."""
    for knob in ("speed", "spreads"):
        given = {**fields_of("spread:p2"), "knob": knob}
        with pytest.raises(ValueError) as refused:
            taskset_config(given)
        message = one_line(refused.value)
        assert "\n" not in message and knob in message, message


def custom_file(knob: str) -> str:
    """The file `init --measure custom --knob depth` writes, naming `knob` instead."""
    made = config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    text = config_module.dump_config(made)
    line = 'knob = "depth"'
    assert text.count(line) == 1, text
    return text.replace(line, f'knob = "{knob}"')


def test_tasks_toml_and_init_do_not_offer_spread_and_it_has_not_shipped() -> None:
    """Shape 4."""
    written = custom_file("depth")
    config_module.loads_config(written)
    for knob in UNPROBED:
        assert knob not in written, knob
    with pytest.raises(config_module.ConfigError) as refused:
        config_module.loads_config(custom_file("spread"))
    assert refused.value.key == "measure.knob"
    config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    with pytest.raises(config_module.ConfigError) as flagged:
        config_module.config_from_init_args(["--measure", "custom", "--knob", "spread"])
    assert flagged.value.key == "measure.knob"
    assert "spread" not in arms_module.SHIPPED_KNOBS
    recipe = arms_module.RECIPES["reading-and-filling"]
    assert not recipe.offered and "spread" in recipe.waiting
