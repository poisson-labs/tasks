"""Argument difficulty opened: `eval`, the levels it cannot build, and what stays shut, frozen as
tests.

The standing decisions for a knob that gains tasks: the `eval` command takes its arms, the published
cards' table answers for the knob so that no arm raises a `KeyError`, and an arm no published card
covers gets the one note saying so.  The two knobs still unbuilt (shape, spread) stay refused by the
generator and by `eval`; that is the frozen
`tests/test_k2_eval.py::test_the_six_knobs_without_tasks_stay_refused_beside_similarity`, whose list
of arms loses its two arguments arms in this knob's retrofit commit (a decided retrofit).
`tasks.toml` and `init` do not offer argument difficulty before its probe.

Shapes decided here
-------------------

**1. Every arguments arm is on no published card**, the control included: neither card measured the
knob.  `eval` takes each card level and the control with the one plain note (one `UserWarning`, one
line, naming the arm by its id; `tests/test_fd1_export_arm.py`), and the tasks it loads are that
arm's.  The control is the arm that would raise the `KeyError` the shared base's build found if the
table read a control pair for a knob it does not hold; the note shows it does not.  The note's words
are not pinned.  The census takes every arm `eval` takes (its count is pending a decision,
`tests/test_k6_pending_census.py`).

**2. Levels the card does not measure.**  `eval` takes any arguments level from 2 to 8, the ends
of the knob's candidate levels; the three between the card's (3, 5, 7) are held to the rule the
export's pinned knob test holds every plain arm to, that an arm `eval` takes is one whose tasks
load, and each loads tasks whose request states its level less two values.

**3. A level the knob cannot build is refused in one line naming the knob**, as decided 2026-10-04
(arguments outside 2 to 8): when the arm is made from its id, as a control standing in for one, and
by `eval`, by id and as the six fields.  The frozen `tests/test_k1_pending_level_bounds.py` pins
that these are refused; this pins that each refusal is one line naming the knob.  On `main`, before
the arguments knob, `eval` refuses the six fields for the knob itself (it has no tasks); after it,
for the level.
"""

from __future__ import annotations

import dataclasses
import importlib
import warnings
from typing import Any

import pytest

from poisson_tasks import config as config_module
from poisson_tasks.arms import arm_from_id
from poisson_tasks.knobs import arm_id
from poisson_tasks.tasks import generate, structure_space
from tests.k6_support import ARMS, OFF_CARD_LEVELS, extras

TASKSET_ID = "poisson-tasks"
SEEDS = [404, 55]
# The knobs no probe has yet shown to bite: none is offered before its probe.
UNPROBED = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")
UNBUILDABLE = ("arguments:a1", "arguments:a9", "arguments:a0", "arguments:a2+len(a9)")


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
def test_eval_takes_every_arguments_arm_with_the_one_note_for_an_arm_no_card_covers(
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


@pytest.mark.parametrize("level", OFF_CARD_LEVELS)
def test_a_level_no_card_measures_that_eval_takes_is_one_whose_tasks_load(level: int) -> None:
    """Shape 2."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        config = taskset_config(f"arguments:a{level}")
    tasks = list(loaders().load_taskset(config).load())
    assert [task.data.arm_id for task in tasks] == [f"arguments:a{level}"] * len(SEEDS)
    for task in tasks:
        first, second = task.data.reference_calls
        assert len(extras(first)) == len(extras(second)) == level - 2, (level, task.key)


def one_line(refusal: BaseException) -> str:
    """The refusal's message: a configuration error's one error, or the exception's text."""
    errors = refusal.errors() if hasattr(refusal, "errors") else []
    if errors:
        assert len(errors) == 1, errors
        return str(errors[0]["msg"])
    return str(refusal)


@pytest.mark.parametrize("text", UNBUILDABLE)
def test_a_level_the_knob_cannot_build_is_refused_in_one_line_naming_it(text: str) -> None:
    """Shape 3."""
    asked: list[Any] = [lambda: arm_from_id(text), lambda: taskset_config(text)]
    if "+" not in text:
        level = int(text.removeprefix("arguments:a"))
        fields = {
            "knob": "arguments",
            "level": level,
            "control": None,
            "strictness": "strict",
            "split": "eval",
            "generator_version": "1",
        }
        asked.append(lambda: taskset_config(fields))
    for ask in asked:
        with pytest.raises(ValueError) as refused:
            ask()
        message = one_line(refused.value)
        assert "\n" not in message and "arguments" in message, message


def custom_file(knob: str) -> str:
    """The file `init --measure custom --knob depth` writes, naming `knob` instead."""
    made = config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    text = config_module.dump_config(made)
    line = 'knob = "depth"'
    assert text.count(line) == 1, text
    return text.replace(line, f'knob = "{knob}"')


def test_tasks_toml_and_init_do_not_offer_arguments_before_its_probe() -> None:
    """The project file and `init`'s flags refuse the knob by the key that names it, and the file
    `init` writes names no knob that has not had its probe; depth, the control, is taken by
    both."""
    written = custom_file("depth")
    config_module.loads_config(written)
    for knob in UNPROBED:
        assert knob not in written, knob
    with pytest.raises(config_module.ConfigError) as refused:
        config_module.loads_config(custom_file("arguments"))
    assert refused.value.key == "measure.knob"
    config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    with pytest.raises(config_module.ConfigError) as flagged:
        config_module.config_from_init_args(["--measure", "custom", "--knob", "arguments"])
    assert flagged.value.key == "measure.knob"
