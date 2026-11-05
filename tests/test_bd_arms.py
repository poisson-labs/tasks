"""The two new knobs' arms, the labels 0.4.0 moves, and no combination of dials, frozen as tests.

The invariants (the 0.4.0 stale-data spec, BD.1, BD.10, BD.18).  `knobs._KNOBS` is the twelve then
`baddata` and `lagged`, with levels `(0, 1, 2, 3)` and `(0, 1)`; each arm id renders and reads back; a
level off the range is refused naming the range; both knobs have no control arm, and a control on
either is refused with a sentence of its own.  The labels move to `"3"` and `"own-3"`, and a settings
file that names an older own-tools label is refused in one line that names the release it moved in
and `own-3`.  An arm stays one knob: a composed id is refused by `arm_from_id`, `generate --arm` and
the export; `[measure] knob` takes no list; `ArmSpec` has six fields; neither knob plans an answer, so
`gave_up_after_fault` is `None` on both.

Shapes decided here
-------------------

**1. The range is held by its numbers, not its words.**  A refusal names the range when its one line
holds the lowest and the highest level as whole numbers, and it is held beside a control, a level in
the range that is accepted.  `baddata:b-1` as text is not an arm id to the parser, whose refusal lists
what an id is; the range is held on `ArmSpec(level=-1)`, as 0.3.0's negative level is, and the text is
held refused and no more (put to the maintainer as a yes/no; nothing more is frozen on it).

**2. "A sentence naming why" is held to say something of the read**, the spec's reason being that the
extra read is on the passing path only, and to be neither the shared sentence nor `landed`'s.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import arms, config, knobs, surface
from poisson_tasks import calibration as cal
from poisson_tasks.arms import arm_from_id
from poisson_tasks.own import generator
from tests.k3_support import episode, made
from tests.test_o2_cli import invoke, work  # noqa: F401 - the fixture is used by name
from tests.test_o2d_b2 import acme_with_flows, own_text
from tests.bd_support import figures

TWELVE = ("depth", "distractor", "similarity", "faults", "history", "block", "arguments", "shape",
          "spread", "timeouts", "ratelimits", "landed")
SHARED = "its levels differ in nothing a control could hold equal"
COMPOSED = (
    "faults:f1+history:t300",
    "faults:f1,timeouts:o1",
    "baddata:b1+faults:f1",
    "baddata:b1+lagged:g1",
    "lagged:g1,baddata:b1",
)


def spec(knob: str, level: int, control: int | None = None) -> knobs.ArmSpec:
    return knobs.ArmSpec(knob=knob, level=level, control=control, strictness="strict",
                         split="eval", generator_version=arms.DEFAULT_GENERATOR_VERSION)


def holds(said: str, number: int) -> bool:
    return re.search(rf"(?<![\d-]){number}(?!\d)", said) is not None


# --------------------------------------------------------------------------
# the arms (BD.1)
# --------------------------------------------------------------------------


def test_the_knobs_are_the_twelve_then_the_two_with_their_levels() -> None:
    assert knobs._KNOBS == (*TWELVE, "baddata", "lagged")
    assert knobs.levels("baddata") == (0, 1, 2, 3)
    assert knobs.levels("lagged") == (0, 1)


@pytest.mark.parametrize(
    ("rendered", "knob", "level"),
    [(f"baddata:b{level}", "baddata", level) for level in (0, 1, 2, 3)]
    + [(f"lagged:g{level}", "lagged", level) for level in (0, 1)],
)
def test_each_new_arm_id_renders_and_reads_back(rendered: str, knob: str, level: int) -> None:
    read = arm_from_id(rendered)
    assert (read.knob, read.level, read.control) == (knob, level, None)
    assert knobs.arm_id(read) == rendered
    assert knobs.arm_id(spec(knob, level)) == rendered


@pytest.mark.parametrize(
    ("rendered", "knob", "level", "low", "high"),
    [
        ("baddata:b4", "baddata", 4, 0, 3),
        ("lagged:g2", "lagged", 2, 0, 1),
    ],
)
def test_a_level_above_the_range_is_refused_naming_the_range(
    rendered: str, knob: str, level: int, low: int, high: int
) -> None:
    """Shape 1: the top of the range is accepted beside it, by the id and by `ArmSpec`."""
    arm_from_id(f"{rendered[:rendered.index(':') + 2]}{high}")
    spec(knob, high)
    for refuse in (lambda: arm_from_id(rendered), lambda: spec(knob, level)):
        with pytest.raises(ValueError) as refused:
            refuse()
        said = str(refused.value)
        assert "\n" not in said and holds(said, low) and holds(said, high), said


@pytest.mark.parametrize(("knob", "letter", "low", "high"),
                         [("baddata", "b", 0, 3), ("lagged", "g", 0, 1)])
def test_a_negative_level_is_refused_naming_the_range(
    knob: str, letter: str, low: int, high: int
) -> None:
    """Shape 1."""
    spec(knob, low)
    with pytest.raises(ValueError) as refused:
        spec(knob, -1)
    said = str(refused.value)
    assert "\n" not in said and holds(said, low) and holds(said, high), said
    with pytest.raises(ValueError):
        arm_from_id(f"{knob}:{letter}-1")


@pytest.mark.parametrize(("knob", "letter", "low", "high"),
                         [("baddata", "b", 0, 3), ("lagged", "g", 0, 1)])
def test_a_control_on_either_knob_is_refused_with_a_sentence_of_its_own(
    knob: str, letter: str, low: int, high: int
) -> None:
    """Shape 2.  Both are in `knobs._NO_CONTROL`; the shared sentence is held to still be what
    `similarity` says, so the comparison is not with words nothing prints."""
    assert knob in knobs._NO_CONTROL
    with pytest.raises(ValueError) as shared:
        spec("similarity", 0, 3)
    assert SHARED in str(shared.value)
    with pytest.raises(ValueError) as refused:
        spec(knob, low, high)
    said = str(refused.value)
    assert "\n" not in said and SHARED not in said, said
    assert "read" in said and "token" not in said, said
    with pytest.raises(ValueError):
        arm_from_id(f"{knob}:{letter}{low}+len({letter}{high})")


# --------------------------------------------------------------------------
# the labels (BD.10)
# --------------------------------------------------------------------------


def test_the_labels_are_3_and_own_3_and_every_copy_agrees() -> None:
    assert arms.DEFAULT_GENERATOR_VERSION == "3"
    assert cal.GENERATOR_VERSION == "3"
    assert generator.GENERATOR_VERSION == "own-3"
    assert config._OWN_GENERATOR_VERSION == generator.GENERATOR_VERSION


@pytest.mark.parametrize(("label", "release"), [("own-1", "0.3.0"), ("own-2", "0.4.0")])
def test_an_older_own_label_in_a_settings_file_is_refused_in_one_line_naming_its_release(
    label: str, release: str, tmp_path: Path
) -> None:
    """The control is the same file naming `own-3`, which plans."""
    acme_with_flows(tmp_path)
    text = own_text('preset = "first-look"').replace(
        f'# generator_version = "{arms.DEFAULT_GENERATOR_VERSION}"', 'generator_version = "{}"', 1
    )
    assert 'generator_version = "{}"' in text
    fine = config.loads_config(text.replace("{}", "own-3"))
    assert config.resolve_plan(fine, root=tmp_path).arms
    with pytest.raises(config.ConfigError) as refused:
        config.resolve_plan(config.loads_config(text.replace("{}", label)), root=tmp_path)
    said = str(refused.value).replace(str(tmp_path), "")
    assert refused.value.key == "tasks.generator_version"
    assert "\n" not in said and release in said and "own-3" in said, said


# --------------------------------------------------------------------------
# no combination (BD.18)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("composed", COMPOSED)
def test_a_composed_arm_id_is_refused_and_each_knob_alone_is_an_arm(composed: str) -> None:
    arm_from_id("baddata:b1")
    arm_from_id("lagged:g1")
    with pytest.raises(ValueError):
        arm_from_id(composed)


def test_generate_refuses_a_composed_arm_and_takes_each_built_in_arm(
    work: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """The control is the same command with `baddata:b1`, which prints a task."""
    assert invoke(["generate", "--arm", "baddata:b1", "--show"], monkeypatch).code == 0
    for composed in COMPOSED:
        ran = invoke(["generate", "--arm", composed, "--show"], monkeypatch)
        assert ran.code not in (0, None), (composed, ran)


def test_the_export_refuses_a_composed_arm_and_takes_each_built_in_arm() -> None:
    """Through the taskset's config, as `eval --env.taskset.arm` reaches it."""
    from tests.test_fd1_export_arm import taskset_config

    taskset_config("baddata:b1", [404])
    for composed in COMPOSED:
        with pytest.raises(ValueError):
            taskset_config(composed, [404])


def test_measure_knob_takes_one_word_and_refuses_a_list(tmp_path: Path) -> None:
    from tests.test_f2_card_and_experimental import planned_arms

    assert planned_arms('preset = "custom"\nknob = "baddata"\nlevels = [0, 3]', tmp_path) == [
        "baddata:b0", "baddata:b3"]
    with pytest.raises(config.ConfigError) as refused:
        planned_arms('preset = "custom"\nknob = ["baddata", "faults"]', tmp_path)
    assert refused.value.key == "measure.knob"


def test_an_arm_has_six_fields_and_neither_knob_plans_an_answer(tmp_path: Path) -> None:
    """On both knobs and every level: no fault word, an empty plan, and on a built-in episode no
    giving up; on an own-tools `lagged` task the plan is empty too, its level being read from the
    arm id (the spec's section 9)."""
    assert [field.name for field in dataclasses.fields(knobs.ArmSpec)] == [
        "knob", "level", "control", "strictness", "split", "generator_version"]
    path = ("a", "b")
    for rendered in ("baddata:b0", "baddata:b1", "baddata:b2", "baddata:b3", "lagged:g0", "lagged:g1"):
        arm_from_id(rendered)
        assert surface.fault_kind(rendered) is None, rendered
        assert surface.fault_plan(rendered, path) == {}, rendered
    bundle = made("baddata:b2", 404)
    record: Any = episode(tmp_path, bundle, list(bundle.reference_calls))
    assert record.gave_up_after_fault is None
    assert figures(record)[1] is True


def test_the_ci_hash_gate_holds_the_two_frozen_hashes() -> None:
    """BD.9's clause that is no kept file's: `ci.yml`'s two values are the literals
    `tests/test_frozen_generator.py` and `tests/test_o2b_kept.py` hold, so a re-freeze moves all
    three.  A guard, true on `main` by construction, as the frozen file's own hash test is."""
    from tests.test_frozen_generator import FROZEN_GENERATOR_HASH
    from tests.test_o2b_kept import OWN_GENERATOR_HASH

    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text()
    held = dict(re.findall(r"(BUILT_IN|OWN_TOOLS)_GENERATOR_HASH: ([0-9a-f]{64})", workflow))
    assert held == {"BUILT_IN": FROZEN_GENERATOR_HASH, "OWN_TOOLS": OWN_GENERATOR_HASH}
