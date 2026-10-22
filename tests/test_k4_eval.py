"""History opened: the generator, `eval`, and what stays shut, frozen as tests.

The standing decisions: once a knob has tasks, the `eval` command takes its arms, the published
cards' table answers for the knob so that no arm raises a `KeyError`, and an arm no published card
covers gets the one note saying so.  The four knobs still unbuilt (block, arguments, shape, spread)
stay refused by the generator and by `eval`; that is the frozen
`tests/test_k2_eval.py::test_the_six_knobs_without_tasks_stay_refused_beside_similarity`, whose list
of arms loses its history arm in this knob's retrofit commit (a decided retrofit).  `tasks.toml` and
`init` do not offer history before its probe.

Shapes decided here
-------------------

**1. Every history arm is on no published card**: neither card measured history.  So `eval` takes
each card level with the one plain note (one `UserWarning`, one line, naming the arm by its id;
`tests/test_fd1_export_arm.py`).  The note's words are not pinned.  History has no control arm, so
the `KeyError` the shared base's build found cannot arise for it; what the table must say is that no
history level is on a card, which the note shows.

**2. Levels the card does not measure.**  `eval` takes any history level from 0 to 2400, and the
generator can build any level from 0 up (by design: `history:t12800` is a level no card measures
and the generator can still make).  Three such levels are held to the rule the export's pinned
knob test holds every plain arm to: an arm `eval` takes is an arm whose tasks load.  At level 1
no pair is seeded; at level 100 two pairs cannot total less than their smallest, so the ledger's
N23 would refuse that arm in a contrast while the arm itself still loads: that is the ledger's
job, not a refusal of the arm, and the test asks only that it loads.

**3. The census is B's.**  A history arm's first request is B's block, B's system prompt and B's
instruction at every level, and its seeded pairs are a derivation of the scenario, as a depth
control's are, so `structure_space` is `distractor:r0@k16`'s count, a lower bound for the seeded
levels as it is for a control.
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
from tests.k3_support import B_ARM
from tests.k4_support import LEVELS, arm

TASKSET_ID = "poisson-tasks"
SEEDS = [404, 55]
OFF_CARD_LEVELS = (1, 100, 900)


def loaders() -> Any:
    return importlib.import_module("verifiers.v1.utils.loaders")


def taskset_config(arm_: Any, seeds: list[int] = SEEDS) -> Any:
    return loaders().taskset_config_type(TASKSET_ID)(id=TASKSET_ID, arm=arm_, seeds=seeds)


def notes(arm_: Any) -> tuple[Any, list[str]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = taskset_config(arm_)
    return config, [str(w.message) for w in caught if issubclass(w.category, UserWarning)]


@pytest.mark.parametrize("text", [arm(level) for level in LEVELS])
def test_eval_takes_every_history_arm_with_the_one_note_for_an_arm_no_card_covers(
    text: str,
) -> None:
    """By its id and as the six fields: taken, one note naming the arm, and the tasks it loads are
    that arm's.  `depth:d3`, a card arm, takes none."""
    spec = arm_from_id(text)
    for given in (arm_id(spec), dataclasses.asdict(spec)):
        config, said = notes(given)
        assert config.arm == dataclasses.asdict(spec)
        assert len(said) == 1, said
        assert arm_id(spec) in said[0] and "\n" not in said[0], said[0]
        tasks = list(loaders().load_taskset(config).load())
        assert [task.data.arm_id for task in tasks] == [arm_id(spec)] * len(SEEDS)
        assert [task.key for task in tasks] == [generate(spec, seed).task_id for seed in SEEDS]
    _config, said = notes("depth:d3")
    assert said == []


@pytest.mark.parametrize("level", OFF_CARD_LEVELS)
def test_a_level_no_card_measures_that_eval_takes_is_one_whose_tasks_load(level: int) -> None:
    """Shape 2."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        config = taskset_config(arm(level))
    tasks = list(loaders().load_taskset(config).load())
    assert [task.data.arm_id for task in tasks] == [arm(level)] * len(SEEDS)


def test_the_generator_counts_a_history_arms_structures_as_bs() -> None:
    """Shape 3."""
    count = structure_space(arm_from_id(B_ARM))
    for level in LEVELS:
        assert structure_space(arm_from_id(arm(level))) == count, level


def custom_file(knob: str) -> str:
    """The file `init --measure custom --knob depth` writes, naming `knob` instead."""
    made = config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    text = config_module.dump_config(made)
    line = 'knob = "depth"'
    assert text.count(line) == 1, text
    return text.replace(line, f'knob = "{knob}"')


def test_tasks_toml_and_init_do_not_offer_history_before_its_probe() -> None:
    """The project file and `init`'s flags refuse the knob by the key that names it; depth, the
    control, is taken by both."""
    config_module.loads_config(custom_file("depth"))
    with pytest.raises(config_module.ConfigError) as refused:
        config_module.loads_config(custom_file("history"))
    assert refused.value.key == "measure.knob"
    config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    with pytest.raises(config_module.ConfigError) as flagged:
        config_module.config_from_init_args(["--measure", "custom", "--knob", "history"])
    assert flagged.value.key == "measure.knob"
