"""The three new knobs' arms, and the generator labels 0.3.0 moves, frozen as tests.

The invariants (the 0.3.0 faults spec, F2.1 and F2.9): `knobs._KNOBS` is the nine then `timeouts`,
`ratelimits` and `landed`, with candidate levels `(0, 1, 2, 4)`, `(0, 1, 2, 4)` and `(0, 1)`; each
new arm id renders and reads back; a negative level is refused with faults' wording; a `landed`
control is refused with N26's reason; a level off the candidates is still an arm.  The labels move
to `"2"` and `"own-2"` (ruled, Q4), and a settings file that still names `own-1` is refused in one
line that names 0.3.0 and `own-2`.

Shapes decided here
-------------------

**1. The letters are the spec's**: `o` for timeouts (`t` is history's), `r` for ratelimits, `l`
for landed, each written after the knob's name, so `ratelimits:r2` and `distractor:r2@k16` are read
apart by the knob.  A control is written as faults' is, `timeouts:o0+len(o4)`.

**2. "Faults' wording" is faults' sentence with the knob's name**: `<knob> level -1 cannot be
built: the level counts ..., from 0 up`, what is counted being the knob's own.  The refusal is held
by a control (level 0 builds), not by the words alone.

**3. N26's reason is about tokens.**  `similarity`, `history` and `spread` are refused a control
with the shared sentence ("its levels differ in nothing a control could hold equal"), which is not
`landed`'s reason: one fault pair is 33 tokens and the shortest seeded read pair 51, so no control
reaches it within N26's two tokens.  The refusal is held to say something of tokens; `timeouts`'
`(0, 4)` control is the accepted case beside it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from poisson_tasks import arms, config, knobs
from poisson_tasks import calibration as cal
from poisson_tasks.arms import arm_from_id
from poisson_tasks.own import generator
from tests.f2_support import NEW_KNOBS
from tests.test_o2d_b2 import acme_with_flows, own_text

NINE = ("depth", "distractor", "similarity", "faults", "history", "block", "arguments", "shape",
        "spread")


def spec(knob: str, level: int, control: int | None = None) -> knobs.ArmSpec:
    return knobs.ArmSpec(knob=knob, level=level, control=control, strictness="strict",
                         split="eval", generator_version=arms.DEFAULT_GENERATOR_VERSION)


def test_the_knobs_are_the_nine_then_the_three_with_their_levels() -> None:
    assert knobs._KNOBS == (*NINE, *NEW_KNOBS)
    assert [knobs.levels(knob) for knob in NEW_KNOBS] == [(0, 1, 2, 4), (0, 1, 2, 4), (0, 1)]


@pytest.mark.parametrize(
    ("rendered", "knob", "level", "control"),
    [
        ("timeouts:o2", "timeouts", 2, None),
        ("ratelimits:r2", "ratelimits", 2, None),
        ("landed:l1", "landed", 1, None),
        ("timeouts:o0+len(o4)", "timeouts", 0, 4),
        ("ratelimits:r0+len(r4)", "ratelimits", 0, 4),
        ("timeouts:o3", "timeouts", 3, None),
    ],
)
def test_each_new_arm_id_renders_and_reads_back(
    rendered: str, knob: str, level: int, control: int | None
) -> None:
    """Shape 1; `timeouts:o3` is a level off the candidates and still an arm."""
    read = arm_from_id(rendered)
    assert (read.knob, read.level, read.control) == (knob, level, control)
    assert knobs.arm_id(read) == rendered
    assert knobs.arm_id(spec(knob, level, control)) == rendered


@pytest.mark.parametrize("knob", NEW_KNOBS)
def test_a_negative_level_is_refused_with_faults_wording(knob: str) -> None:
    """Shape 2."""
    spec(knob, 0)
    with pytest.raises(ValueError) as refused:
        spec(knob, -1)
    said = str(refused.value)
    assert "\n" not in said
    assert said.startswith(f"{knob} level -1 cannot be built: the level counts "), said
    assert said.endswith(", from 0 up"), said


def test_a_landed_control_is_refused_with_n26s_reason() -> None:
    """Shape 3."""
    spec("timeouts", 0, 4)
    spec("ratelimits", 0, 4)
    with pytest.raises(ValueError) as refused:
        spec("landed", 0, 1)
    said = str(refused.value)
    assert "\n" not in said and "token" in said, said
    with pytest.raises(ValueError):
        spec("similarity", 0, 3)
    with pytest.raises(ValueError):
        arm_from_id("landed:l0+len(l1)")


# --------------------------------------------------------------------------
# the labels (Q4)
# --------------------------------------------------------------------------


def test_the_labels_are_2_and_own_2_and_every_copy_agrees() -> None:
    assert arms.DEFAULT_GENERATOR_VERSION == "2"
    assert cal.GENERATOR_VERSION == "2"
    assert generator.GENERATOR_VERSION == "own-2"
    assert config._OWN_GENERATOR_VERSION == generator.GENERATOR_VERSION


def test_own_1_in_a_settings_file_is_refused_in_one_line_naming_0_3_0_and_own_2(
    tmp_path: Path,
) -> None:
    """The control is the same file naming `own-2`, which plans."""
    acme_with_flows(tmp_path)
    text = own_text('preset = "first-look"').replace(
        f'# generator_version = "{arms.DEFAULT_GENERATOR_VERSION}"', 'generator_version = "{}"', 1
    )
    assert 'generator_version = "{}"' in text
    fine = config.loads_config(text.replace("{}", "own-2"))
    assert config.resolve_plan(fine, root=tmp_path).arms
    with pytest.raises(config.ConfigError) as refused:
        config.resolve_plan(config.loads_config(text.replace("{}", "own-1")), root=tmp_path)
    said = str(refused.value).replace(str(tmp_path), "")
    assert refused.value.key == "tasks.generator_version"
    assert "\n" not in said and "0.3.0" in said and "own-2" in said, said
