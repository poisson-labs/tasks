"""The export config refuses, when it is validated, every arm the generator cannot make.

**This file waits on a decision.**  It goes beyond the first decision of 2026-10-02 (an unknown
strictness and a level below 1 are refused), and is its own commit so that if it is declined it
is dropped whole.

Measured on the tree the settings file's build started from (verifiers 0.3.1), each of these is
taken by the config, so `eval --dry-run` passes, and fails only when the tasks are generated, as a
bare `IndexError`, `TypeError` or `ValueError` from inside the generator:
- depth above 8, and a depth control above 8: the stage ladder has eight stages;
- distractor above 14, and a distractor control above 14: the table offers fourteen distractors;
- a split other than `eval` and `train`.

And each of these fails in the validator itself with a `TypeError`, which pydantic does not turn
into a validation error, so `eval` prints a traceback:
- a mapping with a field missing or misspelled (`"levl"`);
- a control that is text.

Two more are taken and generate something no one meant:
- a level of `true`, which is the integer 1 to Python and renders as `depth:dTrue`;
- a level of `"3"`, which renders as `depth:d3` and then fails in the generator.

Each case here is refused as a `ValueError` (pydantic's `ValidationError` is one) when the config
is validated, in one line that names the field refused (read from pydantic's `msg`, which holds
the validator's own words and not the input), and each has a control that is taken.
"""

from __future__ import annotations

import dataclasses
import importlib
from typing import Any

import pytest

from poisson_tasks.knobs import ArmSpec

TASKSET_ID = "poisson-tasks"


def taskset_config(arm: Any) -> Any:
    loaders = importlib.import_module("verifiers.v1.utils.loaders")
    return loaders.taskset_config_type(TASKSET_ID)(id=TASKSET_ID, arm=arm, seeds=[404])


def arm(knob: str = "depth", level: Any = 3, control: Any = None, **over: Any) -> dict[str, Any]:
    fields = dataclasses.asdict(ArmSpec(knob=knob, level=0, control=None, strictness="strict",
                                        split="eval", generator_version="0"))
    fields.update(level=level, control=control, **over)
    return fields


REFUSED_WITH_CONTROL = [
    pytest.param(arm(level=9), arm(level=8), "level", id="depth-9"),
    pytest.param(arm(level=16), arm(level=8), "level", id="depth-16"),
    pytest.param(arm(level=1, control=9), arm(level=1, control=8), "control", id="depth-control-9"),
    pytest.param(arm("distractor", 15), arm("distractor", 14), "level", id="distractor-15"),
    pytest.param(arm("distractor", 2, 16), arm("distractor", 2, 14), "control", id="distractor-control-16"),
    pytest.param(arm(split="test"), arm(split="train"), "split", id="split-test"),
    pytest.param(arm(split=""), arm(split="eval"), "split", id="split-empty"),
    pytest.param(arm(level=True), arm(level=1), "level", id="level-true"),
    pytest.param(arm(level="3"), arm(level=3), "level", id="level-text"),
    pytest.param(arm(level=3.0), arm(level=3), "level", id="level-fraction"),
    pytest.param(arm(level=1, control="8"), arm(level=1, control=8), "control", id="control-text"),
    pytest.param({k: v for k, v in arm().items() if k != "split"}, arm(), "split", id="a-field-missing"),
    pytest.param({**{k: v for k, v in arm().items() if k != "level"}, "levl": 3}, arm(),
                 "levl", id="a-field-misspelled"),
    pytest.param({**arm(), "seed": 404}, arm(), "seed", id="a-seventh-field"),
]


@pytest.mark.parametrize(("refused", "control", "field"), REFUSED_WITH_CONTROL)
def test_an_arm_the_generator_cannot_make_is_refused_when_the_config_is_validated(
    refused: dict[str, Any], control: dict[str, Any], field: str
) -> None:
    with pytest.raises(ValueError) as refusal:
        taskset_config(refused)
    errors = refusal.value.errors() if hasattr(refusal.value, "errors") else []
    assert len(errors) == 1, errors
    message = str(errors[0]["msg"])
    assert "\n" not in message and field in message, message
    taskset_config(control)
