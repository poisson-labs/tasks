"""Block size opened: the generator, `eval`, the census, the levels it cannot build, and what stays
shut, frozen as tests.

The standing decisions: once a knob has tasks, the `eval` command takes its arms, the published
cards' table answers for the knob so that no arm raises a `KeyError`, and an arm no published card
covers gets the one note saying so.  The three knobs still unbuilt (arguments, shape, spread) stay
refused by the generator and by `eval`; that is the frozen
`tests/test_k2_eval.py::test_the_six_knobs_without_tasks_stay_refused_beside_similarity`, whose list
of arms loses its two block arms in this knob's retrofit commit (a decided retrofit).  `tasks.toml`
and `init` do not offer block size before its probe.

Shapes decided here
-------------------

**1. Every block arm is on no published card**, the control included: neither card measured block
size.  `eval` takes each card level and the control with the one plain note (one `UserWarning`, one
line, naming the arm by its id; `tests/test_fd1_export_arm.py`).  The control is the arm that would
raise the `KeyError` the shared base's build found if the table read a control pair for a knob it
does not hold; the note shows it does not.  The note's words are not pinned.

**2. Levels the card does not measure.**  `eval` takes any block level from 8 to 64, the ends of
the knob's candidate levels.  Three it takes between them (9, 20, 50) are held to the rule the
export's pinned knob test holds every plain arm to: an arm `eval` takes is an arm whose tasks load.

**3. The census counts what the arm can make**, which for a block is every tool and its slot, since
nothing in it is masked: the target ledger (12), the order of the first eight slots (8!), the
order of the table's other ten reads in the slots they take (10 perm min(K - 8, 10)), and the
order of the copies after them (240 perm max(K - 18, 0)), the table's 16 x 16 pairs less its 16
reads.  The control counts k8's, a lower bound as for every control (its filler is a derivation
of k64's block).  At k8 that is 483,840, which clears G16's floor of 360,000 at N = 60.  The count
stands only if the draw reaches every order it counts, which is why `tests/test_k5_block.py` holds
the last slot of k64 to many different copies.

The level past which a block cannot be built is pinned in its own file, pending a decision
(`tests/test_k5_pending_upper_bound.py`).
"""

from __future__ import annotations

import dataclasses
import importlib
import warnings
from math import factorial, perm
from typing import Any

import pytest

from poisson_tasks import config as config_module
from poisson_tasks.arms import arm_from_id
from poisson_tasks.knobs import arm_id
from poisson_tasks.tasks import generate, structure_space
from tests.k3_support import SPEC
from tests.k5_support import ARMS, CONTROL, FACETS, READS, VERBS, size_of

TASKSET_ID = "poisson-tasks"
SEEDS = [404, 55]
OFF_CARD_LEVELS = (9, 20, 50)


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
def test_eval_takes_every_block_arm_with_the_one_note_for_an_arm_no_card_covers(
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
    _config, said = notes("depth:d3")
    assert said == []


@pytest.mark.parametrize("level", OFF_CARD_LEVELS)
def test_a_level_no_card_measures_that_eval_takes_is_one_whose_tasks_load(level: int) -> None:
    """Shape 2."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        config = taskset_config(f"block:k{level}")
    tasks = list(loaders().load_taskset(config).load())
    assert [task.data.arm_id for task in tasks] == [f"block:k{level}"] * len(SEEDS)
    assert [len(task.data.tools) for task in tasks] == [level] * len(SEEDS)


@pytest.mark.parametrize("text", ARMS)
def test_the_census_counts_every_order_the_block_draw_can_make(text: str) -> None:
    """Shape 3."""
    extra = size_of(text) - 8
    others = len(READS) - 6
    copies = len(VERBS) * len(FACETS) - len(READS)
    k = (
        len(SPEC.qualifiers)
        * factorial(8)
        * perm(others, min(extra, others))
        * perm(copies, max(extra - others, 0))
    )
    assert structure_space(arm_from_id(text)) == k
    if text == CONTROL:
        assert k == 483_840


def custom_file(knob: str) -> str:
    """The file `init --measure custom --knob depth` writes, naming `knob` instead."""
    made = config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    text = config_module.dump_config(made)
    line = 'knob = "depth"'
    assert text.count(line) == 1, text
    return text.replace(line, f'knob = "{knob}"')


def test_tasks_toml_and_init_do_not_offer_block_before_its_probe() -> None:
    """The project file and `init`'s flags refuse the knob by the key that names it; depth, the
    control, is taken by both."""
    config_module.loads_config(custom_file("depth"))
    with pytest.raises(config_module.ConfigError) as refused:
        config_module.loads_config(custom_file("block"))
    assert refused.value.key == "measure.knob"
    config_module.config_from_init_args(["--measure", "custom", "--knob", "depth"])
    with pytest.raises(config_module.ConfigError) as flagged:
        config_module.config_from_init_args(["--measure", "custom", "--knob", "block"])
    assert flagged.value.key == "measure.knob"
