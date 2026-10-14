"""Task shape opened: `eval`, the levels it cannot build, and what stays shut, frozen as tests.

Taylor's standing rulings for a knob that gains tasks: the `eval` command takes its arms, the
published cards' table answers for the knob so that no arm raises a `KeyError`, and an arm no
published card covers gets the one note saying so; the census takes them.  The one knob then
unbuilt (information spread) was held here to one-line refusals by the generator, the census and
`eval` until K8 gave it tasks; that test left this file in a recorded retrofit, ruled with K8
Session A's filing.  `tasks.toml` and `init` do not offer task shape as the custom knob (spec
K-P3); the knob probe shipped it (ruled 2026-10-14), so the shipped-knobs list the recipes read
names it and the recipe that measures it is offered.

Shapes decided here
-------------------

**1. Every shape arm is on no published card**, the control included: neither card measured the
knob.  `eval` takes each width and the control with the one plain note (one `UserWarning`, one
line, naming the arm by its id; `tests/test_fd1_export_arm.py`), and the tasks it loads are that
arm's.  The note's words are not pinned.  The census takes every arm `eval` takes (its count is
pending a yes/no, `tests/test_k7_pending_census.py`).  Shape has no level between the card's: its
widths are 1, 2 and 4, and 3 is not one (spec §3.2).

**2. A width the knob cannot build is refused in one line naming the knob**, spec §3.2 as ruled
2026-10-04 (a width other than 1, 2 or 4): when the arm is made from its id, as a control standing
in for one, and by `eval`, by id and as the six fields.  The frozen
`tests/test_k1_pending_level_bounds.py` pins that these are refused; this pins that each refusal
is one line naming the knob.  On `main`, before K7, `eval` refuses the six fields for the knob
itself (it has no tasks); after it, for the width.

**3. Shape is offered through its recipe, not as the custom knob**: the project file and `init`'s
flags refuse `shape` as the custom knob by the key that names it; the file `init` writes names none
of the seven probe knobs; the knob probe shipped shape (ruled 2026-10-14, a recorded retrofit of
this file), so the package's list of shipped knobs names it and the recipe that measures shape
(`planning`) is offered and waits on nothing.  (The frozen `tests/test_r0_recipes.py` checks that
every arm offered generates, which stops catching a shipped shape once shape generates.)
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
from tests.k7_support import ARMS

TASKSET_ID = "poisson-tasks"
SEEDS = [404, 55]
# The knobs no probe has yet shown to bite: none is offered before its probe (spec K-P3).
UNPROBED = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")
UNBUILDABLE = ("shape:w3", "shape:w0", "shape:w5", "shape:w8", "shape:w1+len(w3)")


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
def test_eval_takes_every_shape_arm_with_the_one_note_for_an_arm_no_card_covers(text: str) -> None:
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


def fields_of(knob: str, level: int) -> dict[str, Any]:
    return {
        "knob": knob,
        "level": level,
        "control": None,
        "strictness": "strict",
        "split": "eval",
        "generator_version": "1",
    }


@pytest.mark.parametrize("text", UNBUILDABLE)
def test_a_width_the_knob_cannot_build_is_refused_in_one_line_naming_it(text: str) -> None:
    """Shape 2."""
    asked: list[Any] = [lambda: arm_from_id(text), lambda: taskset_config(text)]
    if "+" not in text:
        level = int(text.removeprefix("shape:w"))
        asked.append(lambda: taskset_config(fields_of("shape", level)))
    for ask in asked:
        with pytest.raises(ValueError) as refused:
            ask()
        message = one_line(refused.value)
        assert "\n" not in message and "shape" in message, message


def custom_file(knob: str) -> str:
    """The file `init --measure custom --knob depth` writes, naming `knob` instead."""
    made = config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    text = config_module.dump_config(made)
    line = 'knob = "depth"'
    assert text.count(line) == 1, text
    return text.replace(line, f'knob = "{knob}"')


def test_tasks_toml_and_init_do_not_offer_shape_as_custom_and_planning_is_offered() -> None:
    """Shape 3."""
    written = custom_file("depth")
    config_module.loads_config(written)
    for knob in UNPROBED:
        assert knob not in written, knob
    with pytest.raises(config_module.ConfigError) as refused:
        config_module.loads_config(custom_file("shape"))
    assert refused.value.key == "measure.knob"
    config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    with pytest.raises(config_module.ConfigError) as flagged:
        config_module.config_from_init_args(["--measure", "custom", "--knob", "shape"])
    assert flagged.value.key == "measure.knob"
    assert "shape" in arms_module.SHIPPED_KNOBS
    planning = arms_module.RECIPES["planning"]
    assert planning.offered and tuple(planning.waiting) == ()
    assert {"shape:w1", "shape:w4"} <= set(planning.arms)
