"""Arms by their readable id, the one generator-version constant, and the pin ledger in one
sentence, frozen as tests.

The invariants are FD1.8, FD1.13 and FD1.14 of the front door's plan, for the new module
`poisson_tasks.arms`.  Its three names cannot go in `knobs.py`, whose public surface frozen tests
pin exactly.  The module's import purity (FD1.12) is tested beside `config`'s, in
`tests/test_fd1_config.py`.

Shapes decided here
-------------------

**1. `arm_from_id` takes exactly the ids `knobs.arm_id` writes.**  It reads an id with the
parser `check_pins` uses, and then refuses an id that does not render back to itself, so
`arm_id(arm_from_id(x)) == x` for every id it accepts.  That parser reads `@k8` and `d03`; neither
is an id Tasks writes, and a user who types one gets the refusal rather than a quiet `@k16` or
`d3`.  It does not judge the level: `depth:d4` is a well-formed id.  Whether a config or the
export config takes that arm is theirs to say.

**2. `describe_pins(report)` is one line in plain words.**  What it must carry is pinned as
facts, never as wording: the knob; for a refused report, each violated row by its name, and every
arm of the contrast; for the distractor knob's report, the reported row by its name.  A row id
may appear only beside its name.  The rows' names are `knobs.pin_ledger`'s `held` column.

**3. The refused reports are real.**  Mixing strictnesses refuses on the verifier-strictness row,
and mixing generator versions on the hashes row, so no report is built by hand.
"""

from __future__ import annotations

import dataclasses
import importlib
import re
from typing import Any

import pytest

from poisson_tasks.knobs import ArmSpec, arm_id, check_pins, pin_ledger
from poisson_tasks.tasks import generate

SEED = 404


def arms() -> Any:
    return importlib.import_module("poisson_tasks.arms")


def cal() -> Any:
    return importlib.import_module("poisson_tasks.calibration")


# --------------------------------------------------------------------------
# FD1.8: arm ids, both ways
# --------------------------------------------------------------------------


@pytest.mark.parametrize("strictness", ["strict", "leaky"])
def test_fd1_8_every_card_arm_comes_back_from_its_id(strictness: str) -> None:
    for spec in cal().arm_specs():
        spec = dataclasses.replace(spec, strictness=strictness)
        again = arms().arm_from_id(arm_id(spec), strictness=spec.strictness, split=spec.split,
                                   generator_version=spec.generator_version)
        assert again == spec, (arm_id(spec), again)


def test_fd1_8_the_other_three_fields_are_the_callers() -> None:
    spec = arms().arm_from_id("depth:d2+h5", strictness="leaky", split="train",
                              generator_version="tg-m3-v1")
    assert spec == ArmSpec(knob="depth", level=2, control=5, strictness="leaky", split="train",
                           generator_version="tg-m3-v1")


def test_fd1_8_and_fd1_13_an_id_alone_is_strict_on_eval_at_the_one_generator_version() -> None:
    assert arms().DEFAULT_GENERATOR_VERSION == cal().GENERATOR_VERSION
    assert arms().arm_from_id("distractor:r0+len(r8)@k16") == ArmSpec(
        knob="distractor", level=0, control=8, strictness="strict", split="eval",
        generator_version=arms().DEFAULT_GENERATOR_VERSION)


def test_fd1_8_a_well_formed_id_off_the_cards_is_read_as_written() -> None:
    assert arms().arm_from_id("depth:d4").level == 4
    assert arms().arm_from_id("depth:d1+h5").control == 5
    assert arms().arm_from_id("distractor:r3@k16").level == 3


MALFORMED = [
    "", "depth", "depth:", "depth:d", "depth:3", "Depth:d3", "depth:D3", "depth:d3 ", " depth:d3",
    "depth:d03", "depth:d-1", "depth:d3+h", "depth:d3+3", "depth:d1+h1", "depth:d5+h2",
    "depth:d3@k16", "distractor:r4", "distractor:r4@k8", "distractor:r4@k", "distractor:r0+len(r8)",
    "distractor:r0+r8@k16", "distractor:r8+len(r0)@k16", "width:w3", "depth:d3,depth:d8",
]


@pytest.mark.parametrize("text", MALFORMED)
def test_fd1_8_a_malformed_id_is_refused(text: str) -> None:
    with pytest.raises(ValueError):
        arms().arm_from_id(text)


def test_fd1_8_the_refusals_control_every_canonical_id_is_taken() -> None:
    ids = {arm_id(spec) for spec in cal().arm_specs()}
    assert len(ids) == 14
    for text in ids:
        assert arm_id(arms().arm_from_id(text)) == text


# --------------------------------------------------------------------------
# FD1.14: the pin ledger in one sentence
# --------------------------------------------------------------------------

REPR = re.compile(r"[\[\]{}]|=['\"(]|\b\w+\(\w+=|\(\(|\('|\\n|\bTrue\b|\bFalse\b|\bNone\b")
ROW_ID = re.compile(r"\bN\d+\b")


def spec(level: int, *, knob: str = "depth", control: int | None = None,
         strictness: str = "strict", generator_version: str = "0") -> ArmSpec:
    return ArmSpec(knob=knob, level=level, control=control, strictness=strictness, split="eval",
                   generator_version=generator_version)


def report(*specs: ArmSpec) -> Any:
    return check_pins({arm_id(s): generate(s, SEED) for s in specs})


def sentence(pins: Any) -> str:
    text = arms().describe_pins(pins)
    assert isinstance(text, str) and text.strip() == text and text, repr(text)
    assert "\n" not in text, text
    assert not re.search(r"[.!?] +[A-Z]", text), f"more than one sentence: {text}"
    assert not REPR.search(text), f"a Python repr: {text}"
    names = {row.row_id: row.held for row in pin_ledger(pins.knob)}
    for row in ROW_ID.findall(text):
        assert row in names and names[row] in text, f"{row} without its name: {text}"
    assert pins.knob in text, text
    return text


def test_fd1_14_a_held_report_is_one_plain_sentence() -> None:
    held = report(spec(1), spec(3), spec(8))
    assert not held.refused and not held.violations and not held.reported
    sentence(held)


@pytest.mark.parametrize(("specs", "row"), [
    ((spec(1), spec(3, strictness="leaky")), "N11"),
    ((spec(1), spec(3), spec(8, generator_version="tg-m3-v1")), "N12"),
])
def test_fd1_14_a_refused_report_names_each_failed_row_and_the_arms(
    specs: tuple[ArmSpec, ...], row: str
) -> None:
    refused = report(*specs)
    assert refused.refused and [v[0] for v in refused.violations] == [row]
    text = sentence(refused)
    names = {r.row_id: r.held for r in pin_ledger(refused.knob)}
    assert names[row] in text, text
    for s in specs:
        assert arm_id(s) in text, (arm_id(s), text)


def test_fd1_14_the_distractor_knobs_reported_row_is_named() -> None:
    reported = report(spec(0, knob="distractor"), spec(4, knob="distractor"))
    assert not reported.refused and [r[0] for r in reported.reported] == ["N5"]
    text = sentence(reported)
    names = {r.row_id: r.held for r in pin_ledger("distractor")}
    assert names["N5"] in text, text


def test_fd1_14_held_and_refused_read_differently() -> None:
    """The control for the refused case: the same arms at one strictness hold, and their
    sentence names no failed row."""
    held = sentence(report(spec(1), spec(3)))
    names = {r.row_id: r.held for r in pin_ledger("depth")}
    assert names["N11"] not in held
    assert held != sentence(report(spec(1), spec(3, strictness="leaky")))
