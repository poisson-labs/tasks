"""Similarity opened, and only similarity: the generator, `eval`, and what stays shut, frozen as
tests.

Taylor's ruling of 2026-10-05 on K1 Session B's second yes/no: once similarity has tasks, the
`eval` command takes a similarity arm instead of refusing it as no knob, and the published cards'
table of arms answers for the knob, so that no arm raises a `KeyError` there.  K1 generates no
new knob's tasks and refuses their arms; K2 opens similarity alone.

Shapes decided here
-------------------

**1. A similarity arm is on no published card.**  Neither published card measured similarity,
so every similarity arm through `eval` is taken with the one plain note the front door gives an
arm no card covers (`tests/test_fd1_export_arm.py`, ruling 1's pin: one `UserWarning`, one line,
naming the arm by its id).  Similarity has no control arm, so the `KeyError` K1 Session B found
(`_CONTROL_PAIRS[knob]` read for a control arm) cannot arise for it; what its row must say is that
no similarity level is on a card, which the note shows.  The note's words are not pinned; they
must not say the cards measure similarity.

**2. The six other new knobs stay refused**, by the generator (`generate`, `structure_space`)
and by `eval`, each as a `ValueError` (never a `KeyError`), beside similarity taken, until each
knob's own module opens it: faults opened at K3, history at K4, block at K5, arguments at K6,
shape at K7 and spread, the last, at K8, so no knob is left to refuse.  The test that held them
keeps its other half, similarity taken, under a name that says so (ruled 2026-10-09).

**3. `tasks.toml` and `init` still do not offer similarity.**  Spec K-P3: no difficulty knob
reaches `init`, `tasks.toml` or a published card until its probe has shown it bites.  `eval` is
the library's command and takes any arm the generator makes; the project file is the product's
and waits for the probe and K10.
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

TASKSET_ID = "poisson-tasks"
SEEDS = [404, 55]


def loaders() -> Any:
    return importlib.import_module("verifiers.v1.utils.loaders")


def taskset_config(arm: Any, seeds: list[int] = SEEDS) -> Any:
    return loaders().taskset_config_type(TASKSET_ID)(id=TASKSET_ID, arm=arm, seeds=seeds)


def notes(arm: Any) -> tuple[Any, list[str]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = taskset_config(arm)
    return config, [str(w.message) for w in caught if issubclass(w.category, UserWarning)]


@pytest.mark.parametrize("level", [0, 1, 2, 3])
def test_eval_takes_every_similarity_arm_with_the_one_note_for_an_arm_no_card_covers(
    level: int,
) -> None:
    """By its id and as the six fields: taken, one note naming the arm, and the tasks it loads
    are similarity tasks of that level.  The control, a card arm, takes none."""
    spec = arm_from_id(f"similarity:s{level}")
    for arm in (arm_id(spec), dataclasses.asdict(spec)):
        config, said = notes(arm)
        assert config.arm == dataclasses.asdict(spec)
        assert len(said) == 1, said
        assert arm_id(spec) in said[0] and "\n" not in said[0], said[0]
        tasks = list(loaders().load_taskset(config).load())
        assert [task.data.arm_id for task in tasks] == [arm_id(spec)] * len(SEEDS)
        assert [task.key for task in tasks] == [generate(spec, seed).task_id for seed in SEEDS]
    _config, said = notes("depth:d3")
    assert said == []


def test_similarity_generates_has_a_census_and_is_taken_by_eval() -> None:
    """Shape 2.  Similarity generates, has a census and is taken by `eval`.

    The test was `test_the_six_knobs_without_tasks_stay_refused_beside_similarity`, parametrised
    by the arms still refused, each refused as a `ValueError` by
    `generate`, `structure_space` and `eval` by id and as the six fields.  Faults left that list
    when K3 gave it tasks, history at K4, block at K5, arguments at K6, shape at K7 and spread, its
    last arm, at K8 (each a retrofit ruled with that module's Session A filing).  With no arm left,
    a parametrisation over the empty list would be collected as one skipped case and run nothing,
    so the parametrisation and its refusals went with the list, the control's half runs as it did,
    and the name says what is left (ruled 2026-10-09)."""
    control = arm_from_id("similarity:s1")
    assert generate(control, 404).arm_id == "similarity:s1"
    assert structure_space(control) > 0
    assert taskset_config("similarity:s1").arm["knob"] == "similarity"


def custom_file(knob: str) -> str:
    """The file `init --measure custom --knob depth` writes, naming `knob` instead."""
    made = config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    text = config_module.dump_config(made)
    line = 'knob = "depth"'
    assert text.count(line) == 1, text
    return text.replace(line, f'knob = "{knob}"')


def test_tasks_toml_and_init_do_not_offer_similarity_before_its_probe() -> None:
    """Shape 3: the project file and `init`'s flags refuse the knob by the key that names it;
    depth, the control, is taken by both."""
    config_module.loads_config(custom_file("depth"))
    with pytest.raises(config_module.ConfigError) as refused:
        config_module.loads_config(custom_file("similarity"))
    assert refused.value.key == "measure.knob"
    config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    with pytest.raises(config_module.ConfigError) as flagged:
        config_module.config_from_init_args(["--measure", "custom", "--knob", "similarity"])
    assert flagged.value.key == "measure.knob"
