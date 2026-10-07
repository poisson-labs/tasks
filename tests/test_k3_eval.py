"""Faults opened: the generator, `eval`, and what stays shut, frozen as tests.

Taylor's standing rulings of 2026-10-05 and 2026-10-06: once a knob has tasks, the `eval` command
takes its arms, the published cards' table answers for the knob so that no arm raises a
`KeyError`, and an arm no published card covers gets the one note saying so.  The five knobs
still unbuilt (history, block, arguments, shape, spread) stay refused by the generator and by
`eval`; that is the frozen `tests/test_k2_eval.py::test_the_six_knobs_without_tasks_stay_refused_beside_similarity`,
whose list of arms loses its two faults arms in this session's retrofit commit (a ruling).
`tasks.toml` and `init` do not offer faults before its probe (spec K-P3).

Shapes decided here
-------------------

**1. Every faults arm is on no published card**, the control included: neither card measured
faults.  So `eval` takes each with the one plain note (one `UserWarning`, one line, naming the
arm by its id; `tests/test_fd1_export_arm.py`).  The note's words are not pinned.  The control is
where K1 Session B's `KeyError` would have come from (`_CONTROL_PAIRS[knob]` read for a control
arm); this asks for it by id and as the six fields.

**2. Levels and controls the card does not measure.**  The spec names one faults control,
`faults:f0+len(f4)`; `eval` takes a control at any level below its reference level, so
`faults:f2+len(f4)` reaches the generator too, and so does `faults:f3`, a level no card measures.  Whether such a control is built or refused is left to the build, held to the rule
the export's pinned knob test (`tests/test_fd1_export_knob_pending.py`) holds every plain arm to:
an arm `eval` takes is an arm whose tasks load, and an arm it refuses is refused when the config is
validated, in one line naming the knob or the level.

**3. The census is B's.**  A faults arm's first request is B's block, B's prompt and B's system
prompt with one sentence, at every level, so `structure_space` is `distractor:r0@k16`'s count; the
control's seeded pairs are a derivation of the scenario and, as for a depth control, the count is
a lower bound for it.
"""

from __future__ import annotations

import dataclasses
import importlib
import warnings
from typing import Any

import pytest

from poisson_tasks import config as config_module
from poisson_tasks.arms import arm_from_id
from poisson_tasks.knobs import ArmSpec, arm_id
from poisson_tasks.tasks import generate, structure_space
from tests.k3_support import B_ARM, CONTROL, LEVELS, arm

TASKSET_ID = "poisson-tasks"
SEEDS = [404, 55]


def loaders() -> Any:
    return importlib.import_module("verifiers.v1.utils.loaders")


def taskset_config(arm_: Any, seeds: list[int] = SEEDS) -> Any:
    return loaders().taskset_config_type(TASKSET_ID)(id=TASKSET_ID, arm=arm_, seeds=seeds)


def notes(arm_: Any) -> tuple[Any, list[str]]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = taskset_config(arm_)
    return config, [str(w.message) for w in caught if issubclass(w.category, UserWarning)]


@pytest.mark.parametrize("text", [arm(level) for level in LEVELS] + [CONTROL])
def test_eval_takes_every_faults_arm_with_the_one_note_for_an_arm_no_card_covers(
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


def test_every_faults_arm_eval_takes_is_one_whose_tasks_load() -> None:
    """Shape 2, over every plain level from 0 to the highest, `faults:f3` included, and every
    control below it."""
    version = arm_from_id("faults:f0").generator_version
    highest = max(LEVELS)
    arms = [(level, None) for level in range(highest + 1)] + [
        (low, high) for high in range(1, highest + 1) for low in range(high)
    ]
    for level, control in arms:
        spec = ArmSpec(
            knob="faults",
            level=level,
            control=control,
            strictness="strict",
            split="eval",
            generator_version=version,
        )
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                config = taskset_config(dataclasses.asdict(spec))
        except ValueError as refusal:
            errors = refusal.errors() if hasattr(refusal, "errors") else []
            assert len(errors) == 1, errors
            assert "\n" not in str(errors[0]["msg"]), errors
            continue
        assert len(list(loaders().load_taskset(config).load())) == len(SEEDS), arm_id(spec)


def test_the_generator_counts_a_faults_arms_structures_as_bs() -> None:
    """Shape 3."""
    count = structure_space(arm_from_id(B_ARM))
    for text in [arm(level) for level in LEVELS] + [CONTROL]:
        assert structure_space(arm_from_id(text)) == count, text


def custom_file(knob: str) -> str:
    """The file `init --measure custom --knob depth` writes, naming `knob` instead."""
    made = config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    text = config_module.dump_config(made)
    line = 'knob = "depth"'
    assert text.count(line) == 1, text
    return text.replace(line, f'knob = "{knob}"')


def test_tasks_toml_and_init_do_not_offer_faults_before_its_probe() -> None:
    """The project file and `init`'s flags refuse the knob by the key that names it; depth, the
    control, is taken by both."""
    config_module.loads_config(custom_file("depth"))
    with pytest.raises(config_module.ConfigError) as refused:
        config_module.loads_config(custom_file("faults"))
    assert refused.value.key == "measure.knob"
    config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    with pytest.raises(config_module.ConfigError) as flagged:
        config_module.config_from_init_args(["--measure", "custom", "--knob", "faults"])
    assert flagged.value.key == "measure.knob"
