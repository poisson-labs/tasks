"""The calibration side after the generator change, frozen as tests.

Three things move with the generator:

* **The label.**  The generator version a user gets is `"1"`, in `arms` and in `calibration`.
  Both published cards were measured at `"0"`: they still recompute from their records and
  render every table, and the generator hash they carry is no longer the package's, which their
  own page says makes them stale.
* **Finding an arm.**  The calibration side read an arm's knob, control and minimum calls by
  searching the card design (`arm_specs()`), so an arm outside the design had none.  It now reads
  them from the id itself, so every knob's arms have them, and the published cards' arms keep
  theirs when the design changes.  The minimum calls are the arm's reference turns less the
  reply.
* **The driver's pin.**  The notebook's driver refuses to run on a generator other than the one it
  expects; that expectation is the package's generator, and its refusal names hashes, not a card.

The export's `--env.taskset.arm` help calls the distractor dial retired as well as experimental,
and its example arms are at the default generator version.

Shapes decided here
-------------------

**1. `_spec_for`, `_is_control` and `_minimum_calls` are tested by name**, because the build's plan
names them; one card-level test shows a cell of an arm outside the card design carrying its
minimum calls and its control flag.

**2. "Stale" is a fact about hashes.**  A card is stale when the generator hash it recorded is not
the one the package generates; the test reads both.  The page's own sentence about it must not
name a source file, since the generator is three of them now.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest

from poisson_tasks import arms, calibration as cal, calibration_run as run, export
from poisson_tasks.arms import arm_from_id
from poisson_tasks.knobs import ArmSpec, arm_id, levels
from poisson_tasks.tasks import generate

from tests.helpers import rebuild_committed_card

REPO = Path(__file__).resolve().parent.parent
CARDS = ("gpt-5-nano-2025-08-07", "qwen3-8b-b968826d")
KNOBS = ("depth", "distractor", "similarity", "faults", "history", "block", "arguments",
         "shape", "spread")
NO_CONTROL = ("similarity", "history", "spread")


def every_arm() -> list[ArmSpec]:
    out = []
    for knob in KNOBS:
        for level in levels(knob):
            controls = [] if knob in NO_CONTROL else [c for c in levels(knob) if c > level]
            for control in (None, *controls):
                out.append(ArmSpec(knob=knob, level=level, control=control, strictness="strict",
                                   split=cal.SPLIT, generator_version=cal.GENERATOR_VERSION))
    return out


def written(spec: ArmSpec) -> str:
    return arm_id(spec)


# --------------------------------------------------------------------------
# the label
# --------------------------------------------------------------------------


def test_the_generator_version_a_user_gets_is_1_everywhere() -> None:
    assert arms.DEFAULT_GENERATOR_VERSION == "1"
    assert cal.GENERATOR_VERSION == arms.DEFAULT_GENERATOR_VERSION
    assert {spec.generator_version for spec in cal.arm_specs()} == {"1"}


@pytest.mark.parametrize("card", CARDS)
def test_each_published_card_is_stale_against_the_package(card: str) -> None:
    stored = json.loads((REPO / "calibration" / card / "artifact.json").read_text())
    package = generate(cal.arm_specs()[0], cal.seed_list()[0]).generator_hash
    assert stored["provenance"]["generator_hash"] != package


@pytest.mark.parametrize("card", CARDS)
def test_each_published_card_renders_every_table_with_every_arm_it_measured(card: str) -> None:
    artifact, cells = rebuild_committed_card(REPO / "calibration" / card)
    text = cal.render_document(artifact)
    assert "tasks.py" not in text
    arms_measured = {arm for arm, _model in cells}
    assert len(arms_measured) == 14
    for knob in ("depth", "distractor"):
        heading = text.index(f"### {knob}")
        section = text[heading:]
        for arm in sorted(a for a in arms_measured if a.startswith(knob)):
            row = re.search(r"^\| `" + re.escape(arm) + r"` \|", section, flags=re.M)
            assert row is not None, (knob, arm)


def test_the_combined_page_says_the_cards_are_stale_without_naming_a_source_file() -> None:
    page = (REPO / "docs" / "calibration.md").read_text(encoding="utf-8")
    assert "tasks.py" not in page
    assert "stale" in page


# --------------------------------------------------------------------------
# finding an arm from its id
# --------------------------------------------------------------------------


def test_every_arm_of_every_knob_is_read_from_its_id() -> None:
    for spec in every_arm():
        arm = written(spec)
        assert cal._spec_for(arm) == spec, arm
        assert cal._is_control(arm) is (spec.control is not None), arm
        assert cal._minimum_calls(arm) == spec.reference_turns - 1, arm
        assert run.spec_for(arm) == spec, arm


@pytest.mark.parametrize("arm, minimum", [
    ("depth:d5", 5), ("depth:d1+h8", 1), ("distractor:r8@k16", 2), ("faults:f4", 6),
    ("faults:f0+len(f4)", 2), ("history:t2400", 2), ("shape:w4", 4), ("spread:p1", 6),
])
def test_the_minimum_calls_of_arms_on_and_off_the_card_design(arm: str, minimum: int) -> None:
    assert cal._minimum_calls(arm) == minimum


@pytest.mark.parametrize("text", ["not an arm", "depth:d03", "faults:f2+len(f1)", ""])
def test_text_that_is_not_an_arm_id_has_no_spec(text: str) -> None:
    assert cal._spec_for(text) is None
    assert cal._minimum_calls(text) is None
    assert cal._is_control(text) is False
    with pytest.raises(ValueError):
        run.spec_for(text)
    assert run.spec_for("faults:f2+len(f4)").control == 4


@pytest.mark.parametrize("arm, minimum, control", [
    ("history:t300", 2, False), ("faults:f0+len(f4)", 2, True), ("faults:f4", 6, False),
])
def test_a_cell_off_the_card_design_carries_its_minimum_and_its_control_flag(
    arm: str, minimum: int, control: bool
) -> None:
    folder = REPO / "calibration" / CARDS[0]
    stored = json.loads((folder / "artifact.json").read_text())
    records = [dataclasses.replace(r, arm_id=arm) for r in cal.read_records(folder / "episodes.jsonl")
               if r.arm_id == "distractor:r0@k16"]
    artifact = cal.build_artifact({(arm, CARDS[0]): records},
                                  cal.Provenance(**stored["provenance"]))
    (cell,) = artifact.cells
    assert (cell["minimum_calls"], cell["control"]) == (minimum, control)


# --------------------------------------------------------------------------
# the driver's pin
# --------------------------------------------------------------------------


def test_the_driver_expects_the_packages_generator() -> None:
    bundle = generate(cal.arm_specs()[0], cal.seed_list()[0])
    assert run.EXPECTED_GENERATOR_HASH == bundle.generator_hash


def test_the_drivers_stop_names_both_hashes_and_no_card(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ctx = run.Context(local=tmp_path / "local", durable=tmp_path / "durable", port=1,
                      mirror_interval=1.0)
    monkeypatch.setattr(run, "gpu_facts", lambda: {"name": f"NVIDIA {ctx.pin.gpu}"})
    monkeypatch.setattr(run, "EXPECTED_GENERATOR_HASH", "f" * 64)
    monkeypatch.setattr(run, "check_server", lambda *a: pytest.fail("ran past the stop"))
    assert run.cmd_preflight(ctx) == 1
    said = capsys.readouterr().out
    package = generate(cal.arm_specs()[0], cal.seed_list()[0]).generator_hash
    assert package in said and "f" * 64 in said
    assert not re.search(r"\bcard\b|model A|gpt-5|qwen", said, flags=re.I), said


# --------------------------------------------------------------------------
# the export's arm help
# --------------------------------------------------------------------------


def arm_help() -> str:
    return str(export.ExportTasksetConfig.model_fields["arm"].description)


def test_the_arm_help_calls_the_distractor_dial_retired_and_experimental() -> None:
    sentence = next(s for s in arm_help().split(". ") if "distractor" in s)
    assert "retired" in sentence.lower() and "experimental" in sentence.lower()


def test_every_example_arm_the_export_shows_is_at_the_default_generator_version() -> None:
    examples = re.findall(r"\{[^{}]*\"generator_version\"[^{}]*\}",
                          arm_help() + export._NO_ARM.replace('\\"', '"'))
    assert len(examples) == 2
    for example in examples:
        assert json.loads(example)["generator_version"] == arms.DEFAULT_GENERATOR_VERSION
    assert arm_from_id("depth:d3").generator_version == arms.DEFAULT_GENERATOR_VERSION
