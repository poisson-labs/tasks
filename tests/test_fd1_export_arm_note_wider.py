"""The export config's note covers every arm that is not one of the published cards' fourteen as
written, not only a level the cards do not measure.

**This file waits on a yes/no.**  Taylor's first ruling of 2026-10-02 asks for a plain note on "a
level that is legitimate but on no published card"; that is pinned in
`tests/test_fd1_export_arm.py`.  An arm at a published level can still be on no published card:
- a leaky arm carries other task ids (the strictness is in every task), so its tasks are not the
  cards' tasks, which the spec's own strictness question already tells an `init` user;
- an arm on the `train` split draws other scenarios;
- an arm at another generator version carries other task ids, which the spec's plan line says
  for `run` (`tasks at generator version "tg-m3-v1" ... match no published card`).
This file asks for the same note on each.  It is its own commit, so that a "no" drops it whole.

Pinned as in the ruling's own test: exactly one `UserWarning`, one line, naming the arm by its id;
and the control, the same arm as the cards measured it, carries none.
"""

from __future__ import annotations

import dataclasses
import importlib
import warnings
from typing import Any

import pytest

from poisson_tasks.arms import DEFAULT_GENERATOR_VERSION
from poisson_tasks.knobs import ArmSpec, arm_id

TASKSET_ID = "poisson-tasks"
CARD_ARM = ArmSpec(knob="depth", level=3, control=None, strictness="strict", split="eval",
                   generator_version=DEFAULT_GENERATOR_VERSION)


def notes(spec: ArmSpec) -> list[str]:
    loaders = importlib.import_module("verifiers.v1.utils.loaders")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loaders.taskset_config_type(TASKSET_ID)(id=TASKSET_ID, arm=dataclasses.asdict(spec),
                                                seeds=[404])
    return [str(w.message) for w in caught if issubclass(w.category, UserWarning)]


@pytest.mark.parametrize("change", [
    {"strictness": "leaky"},
    {"split": "train"},
    {"generator_version": "tg-m3-v1"},
    {"control": 8, "level": 1, "strictness": "leaky"},
])
def test_an_arm_off_the_cards_by_any_field_carries_one_note(change: dict[str, Any]) -> None:
    spec = dataclasses.replace(CARD_ARM, **change)
    said = notes(spec)
    assert len(said) == 1, said
    assert arm_id(spec) in said[0] and "\n" not in said[0], said[0]
    assert notes(dataclasses.replace(spec, strictness="strict", split="eval",
                                     generator_version=DEFAULT_GENERATOR_VERSION)) == []
