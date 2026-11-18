"""The generators' labels from 0.5.0, `"4"` and `"own-4"`, and what becomes of the labels before
them, frozen as tests.

0.5.0 changes what a spread task's answers and request say, on the built-in tools and on a user's
own, so both generators change and every task id moves once more.  Ruled 2026-11-15: the built-in
label moves from `"3"` to `"4"` and the own-tools label from `"own-3"` to `"own-4"`, as 0.3.0 and
0.4.0 moved them, so that one label names one generator.

Shapes decided here
-------------------

**1. The labels and every copy of them**: `arms.DEFAULT_GENERATOR_VERSION` is `"4"` and the card
runner's copy is the same object's value; `own.generator.GENERATOR_VERSION` is `"own-4"` and the
settings reader's copy equals it; an arm made from an id with no version named is at `"4"`; the
settings file `init` writes shows the built-in label on its commented line.

**2. A task is made at the new label and at no older one on a user's own tools**: the own-tools
generator makes a task for an arm at `"own-4"` and refuses an arm at `"own-3"` in one line that
names both labels.

**3. `own-3` joins the labels before**: beside `[own]`, a settings file that names `own-3` is
refused when its plan is resolved, in one line, on the key `tasks.generator_version`, and the line
names `0.5.0`, the release that changed the generator, and `own-4`, the label now.  `own-1` and
`own-2` are refused as they were, each naming its own release (`0.3.0`, `0.4.0`) and now `own-4`.
The control is the same file naming `own-4`, which plans.

**4. The card preset at `"3"`**: the card preset holds its tasks to the default label, so a file
that sets `"3"` under it is refused on `tasks.generator_version` in one line that shows `"3"` and
`"4"`; the same file at `"4"` reads.

Whether a built-in settings file that is not the card preset is refused at `"3"` is pending a
decision (`tests/test_g4_pending_builtin_label.py`): no built-in label was ever refused there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from poisson_tasks import arms, config
from poisson_tasks import calibration as cal
from poisson_tasks.arms import arm_from_id
from poisson_tasks.own import generator
from tests.g4_support import BUILT_IN_LABEL, BUILT_IN_LABEL_BEFORE, OWN_LABEL, OWN_LABEL_BEFORE, RELEASE
from tests.test_o2d_b2 import BASE, acme_with_flows, own_text

COMMENTED = f'# generator_version = "{BUILT_IN_LABEL}"'
BEFORE = (("own-1", "0.3.0"), ("own-2", "0.4.0"), (OWN_LABEL_BEFORE, RELEASE))


def test_the_labels_are_4_and_own_4_and_every_copy_agrees() -> None:
    """Shape 1."""
    assert arms.DEFAULT_GENERATOR_VERSION == BUILT_IN_LABEL == "4"
    assert cal.GENERATOR_VERSION == BUILT_IN_LABEL
    assert generator.GENERATOR_VERSION == OWN_LABEL == "own-4"
    assert config._OWN_GENERATOR_VERSION == generator.GENERATOR_VERSION
    assert arm_from_id("spread:p1").generator_version == BUILT_IN_LABEL
    written = config.dump_config(config.config_from_init_args(BASE))
    assert written.count(COMMENTED) == 1
    assert f'generator_version = "{BUILT_IN_LABEL_BEFORE}"' not in written


def test_the_own_generator_makes_a_task_at_own_4_and_refuses_an_arm_at_own_3(
    tmp_path: Path,
) -> None:
    """Shape 2."""
    toolset, flows = acme_with_flows(tmp_path)
    now = arm_from_id("spread:p1", generator_version=OWN_LABEL)
    assert generator.generate(toolset, now, 404, flows=flows).arm_id == "spread:p1"
    before = arm_from_id("spread:p1", generator_version=OWN_LABEL_BEFORE)
    with pytest.raises(ValueError) as refused:
        generator.generate(toolset, before, 404, flows=flows)
    said = str(refused.value)
    assert "\n" not in said and OWN_LABEL in said and OWN_LABEL_BEFORE in said, said


@pytest.mark.parametrize(("label", "release"), BEFORE)
def test_an_own_label_before_own_4_is_refused_in_one_line_naming_its_release_and_own_4(
    label: str, release: str, tmp_path: Path
) -> None:
    """Shape 3."""
    acme_with_flows(tmp_path)
    text = own_text('preset = "first-look"').replace(COMMENTED, 'generator_version = "{}"', 1)
    assert 'generator_version = "{}"' in text
    fine = config.loads_config(text.replace("{}", OWN_LABEL))
    assert config.resolve_plan(fine, root=tmp_path).arms
    with pytest.raises(config.ConfigError) as refused:
        config.resolve_plan(config.loads_config(text.replace("{}", label)), root=tmp_path)
    said = str(refused.value).replace(str(tmp_path), "")
    assert refused.value.key == "tasks.generator_version"
    assert "\n" not in said and release in said and OWN_LABEL in said and label in said, said
    others = {each for _label, each in BEFORE} - {release}
    assert not any(other in said for other in others), said


def card_file(version: str) -> str:
    """The settings file `init` writes for the card preset, with its label set."""
    text = config.dump_config(config.config_from_init_args(["--measure", "card"]))
    assert text.count(COMMENTED) == 1
    return text.replace(COMMENTED, f'generator_version = "{version}"', 1)


def test_the_card_preset_reads_at_4_and_refuses_3_in_one_line_showing_both() -> None:
    """Shape 4."""
    made = config.loads_config(card_file(BUILT_IN_LABEL))
    assert made.tasks.generator_version == BUILT_IN_LABEL
    with pytest.raises(config.ConfigError) as refused:
        config.loads_config(card_file(BUILT_IN_LABEL_BEFORE))
    said = str(refused.value)
    assert refused.value.key == "tasks.generator_version"
    assert "\n" not in said, said
    assert f'"{BUILT_IN_LABEL_BEFORE}"' in said and f'"{BUILT_IN_LABEL}"' in said, said
