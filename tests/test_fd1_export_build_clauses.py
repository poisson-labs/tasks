"""The export arm validator's clause that FD1's build added and no frozen test pinned: a generator
version that is not text is refused when the config is validated.

The arm is given as one JSON object on `eval`'s command line, where `"generator_version": 1` is
easy to write.  Without the clause the number is taken, and the arm reads as one no published
card covers, though the user named the cards' own version.  The refusal is pinned against the
same arm with the version as text, and by pydantic's `msg` for the one error being one line that
names the field, as `tests/test_fd1_export_arm.py` reads a refusal.
"""

from __future__ import annotations

import dataclasses
import importlib
from typing import Any

import pytest

from poisson_tasks.arms import DEFAULT_GENERATOR_VERSION
from poisson_tasks.knobs import ArmSpec

TASKSET_ID = "poisson-tasks"


def taskset_config(arm: Any) -> Any:
    loaders = importlib.import_module("verifiers.v1.utils.loaders")
    return loaders.taskset_config_type(TASKSET_ID)(id=TASKSET_ID, arm=arm, seeds=[404])


def depth_3(generator_version: Any) -> dict[str, Any]:
    arm = dataclasses.asdict(
        ArmSpec(
            knob="depth",
            level=3,
            control=None,
            strictness="strict",
            split="eval",
            generator_version=DEFAULT_GENERATOR_VERSION,
        )
    )
    return {**arm, "generator_version": generator_version}


@pytest.mark.parametrize("version", [1, None], ids=["a-number", "null"])
def test_a_generator_version_that_is_not_text_is_refused(version: Any) -> None:
    with pytest.raises(ValueError) as refusal:
        taskset_config(depth_3(version))
    errors = refusal.value.errors() if hasattr(refusal.value, "errors") else []
    assert len(errors) == 1, errors
    message = str(errors[0]["msg"])
    assert "\n" not in message and "generator_version" in message, message
    assert taskset_config(depth_3(DEFAULT_GENERATOR_VERSION)).arm == depth_3(
        DEFAULT_GENERATOR_VERSION
    )
