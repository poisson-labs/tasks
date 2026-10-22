"""Pending a decision: an arm the export config takes is an arm whose tasks load.

The mutation pass on the settings file's build named the export validator's knob check
equivalent: with it gone, the generator's
own `levels()` refused an unknown knob, also as a `ValueError`.  Since the knobs' shared base,
`levels()` knows nine knobs and the generator makes tasks for two, so with the check gone an arm
of a knob such as faults is taken when the config is validated, with no note, and refused only
when its tasks are generated.  `eval --dry-run` would accept it.

This pins the rule the check keeps, in a form the knob modules can open knobs under without
editing it: for every knob `levels()` knows, at every candidate level, the export config either
refuses the arm when it is validated, in one line naming the knob, or takes it and its tasks
load.  Dropped if it is declined.
"""

from __future__ import annotations

import dataclasses
import importlib
import warnings
from typing import Any

import pytest

from poisson_tasks.arms import DEFAULT_GENERATOR_VERSION
from poisson_tasks.knobs import ArmSpec, levels

TASKSET_ID = "poisson-tasks"
KNOBS = (
    "depth",
    "distractor",
    "similarity",
    "faults",
    "history",
    "block",
    "arguments",
    "shape",
    "spread",
)


def loaders() -> Any:
    return importlib.import_module("verifiers.v1.utils.loaders")


@pytest.mark.parametrize("knob", KNOBS)
def test_an_arm_the_export_config_takes_is_one_whose_tasks_load(knob: str) -> None:
    taken = 0
    for level in levels(knob):
        arm = dataclasses.asdict(
            ArmSpec(
                knob=knob,
                level=level,
                control=None,
                strictness="strict",
                split="eval",
                generator_version=DEFAULT_GENERATOR_VERSION,
            )
        )
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                config = loaders().taskset_config_type(TASKSET_ID)(
                    id=TASKSET_ID, arm=arm, seeds=[404]
                )
        except ValueError as refusal:
            errors = refusal.errors() if hasattr(refusal, "errors") else []
            assert len(errors) == 1, errors
            message = str(errors[0]["msg"])
            assert "\n" not in message and knob in message, message
            continue
        assert len(list(loaders().load_taskset(config).load())) == 1, (knob, level)
        taken += 1
    if knob in ("depth", "distractor"):
        assert taken == len(levels(knob)), knob
