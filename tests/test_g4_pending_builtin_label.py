"""Pending a decision: a built-in settings file that names a label before `"4"` is refused.

**Why it is open.**  The 0.5.0 plan holds that `"3"` and `"own-3"` "join the versions-before tables"
and that "a settings file at `"3"` is refused in one line that names what moved".  On a user's own
tools there is such a table, and `own-3` joins it (`tests/test_g4_labels.py`).  On the built-in
tools there is none: only a comment lists the labels before, and a settings file may name any
label outside the card preset.  At 0.4.2 a built-in file at `"2"` is not refused; it makes tasks
that carry the label `"2"` from the generator of `"3"`, with ids no release at `"2"` ever made.
The settings page says only that another version moves every task id.  So refusing `"3"` there is a
behaviour the code does not have, which the plan asks for and the design does not describe.

**Recommended.**  Yes, and for every label the built-in generator has left, so that one label
names one generator: a built-in settings file that sets `generator_version` to `"1"`, `"2"` or
`"3"` is refused, when it is read or when its plan is resolved, in one line, on the key
`tasks.generator_version`, and the line shows the label, names the release that changed the
generator (`0.3.0`, `0.4.0`, `0.5.0`) and shows `"4"`, the label now.  A label the generator never
had (`"0"`, a name of the user's own) stays allowed, as it is used to make tasks apart from every
published one.  The same file at `"4"`, or with the key left out, plans.  If it is declined, a
built-in file may name `"3"` as it may name `"2"` today, the plan's sentence is read as the
own-tools refusal and the card preset's, and this file is dropped.
"""

from __future__ import annotations

import pytest

from poisson_tasks import config
from tests.g4_support import BUILT_IN_LABEL

BASE = ["--provider", "openai", "--no-price", "--token-cap", "100000"]
COMMENTED = f'# generator_version = "{BUILT_IN_LABEL}"'
BEFORE = (("1", "0.3.0"), ("2", "0.4.0"), ("3", "0.5.0"))


def built_in_file(version: str | None) -> str:
    """The first-look settings file `init` writes, with its label set or left commented."""
    text = config.dump_config(config.config_from_init_args(BASE))
    assert text.count(COMMENTED) == 1
    if version is None:
        return text
    return text.replace(COMMENTED, f'generator_version = "{version}"', 1)


def plan_of(text: str) -> config.Plan:
    return config.resolve_plan(config.loads_config(text))


@pytest.mark.parametrize(("label", "release"), BEFORE)
def test_a_built_in_label_before_4_is_refused_in_one_line_naming_its_release_and_4(
    label: str, release: str
) -> None:
    with pytest.raises(config.ConfigError) as refused:
        plan_of(built_in_file(label))
    said = str(refused.value)
    assert refused.value.key == "tasks.generator_version"
    assert "\n" not in said, said
    assert f'"{label}"' in said and release in said and f'"{BUILT_IN_LABEL}"' in said, said
    others = {each for _label, each in BEFORE} - {release}
    assert not any(other in said for other in others), said


@pytest.mark.parametrize("version", [None, BUILT_IN_LABEL, "0", "mine"])
def test_the_label_now_no_label_and_a_label_the_generator_never_had_still_plan(
    version: str | None,
) -> None:
    plan = plan_of(built_in_file(version))
    assert plan.arms
    assert {spec.generator_version for spec in plan.arms} == {version or BUILT_IN_LABEL}
