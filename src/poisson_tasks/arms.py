"""Arms by their readable id, the one generator-version constant, and the pin ledger in words.

The three names cannot go in `knobs.py`, whose public surface frozen tests pin exactly;
`tests/test_fd1_arms.py` says what each one does.  Importing this module imports no
`verifiers` and none of `tasks`, `calibration` and `export`.

The module also holds, privately, which arms the published cards measured.  `calibration` is
where that design is declared (`arm_specs()`), and it cannot be imported here or by the two
modules that need the answer without it: `config` reads a settings file with no tokenizer in the
environment, and `export` is imported by `calibration`.  The tests hold this copy equal to
`calibration`'s.
"""

from __future__ import annotations

from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.knobs import PinReport as _PinReport
from poisson_tasks.knobs import _parse_arm_id, _render_arm_id
from poisson_tasks.knobs import levels as _levels
from poisson_tasks.knobs import pin_ledger as _pin_ledger

__all__ = ["arm_from_id", "DEFAULT_GENERATOR_VERSION", "describe_pins"]

DEFAULT_GENERATOR_VERSION = "0"

# The published cards' control arms, as (level, the level it stands in for): equal to
# `calibration.D_CONTROLS` and `calibration.R_CONTROLS`.
_CONTROL_PAIRS: dict[str, tuple[tuple[int, int], ...]] = {
    "depth": ((1, 8), (2, 5)),
    "distractor": ((0, 8), (2, 14)),
}
_CARD_STRICTNESS = "strict"
_CARD_SPLIT = "eval"


def arm_from_id(
    arm_id: str,
    *,
    strictness: str = "strict",
    split: str = "eval",
    generator_version: str = DEFAULT_GENERATOR_VERSION,
) -> _ArmSpec:
    """The arm an id names: the inverse of `knobs.arm_id`.

    An id carries the knob, the level and the control, and the other three fields are the
    caller's.  It is read with the parser `check_pins` uses, and then must render back to itself,
    so only the ids `knobs.arm_id` writes are taken: that parser also reads `depth:d03` and
    `distractor:r4@k8`, and neither is an arm's id.  The level is not judged here; `depth:d4`
    is a well-formed id, and whether an arm at that level may run is the caller's to say.
    """
    if not isinstance(arm_id, str):
        raise ValueError(f"an arm id is text such as depth:d3; got {type(arm_id).__name__}")
    parsed = _parse_arm_id(arm_id)
    spec = _ArmSpec(
        knob=parsed.knob,
        level=parsed.level,
        control=parsed.control,
        strictness=strictness,
        split=split,
        generator_version=generator_version,
    )
    canonical = _render_arm_id(spec.knob, spec.level, spec.control)
    if canonical != arm_id:
        raise ValueError(f"{arm_id!r} is not an arm id: the arm it reads as is written {canonical}")
    return spec


def _on_a_published_card(spec: _ArmSpec) -> bool:
    """Whether `spec` is one of the published cards' fourteen arms, as the cards measured it."""
    if (spec.strictness, spec.split, spec.generator_version) != (
        _CARD_STRICTNESS,
        _CARD_SPLIT,
        DEFAULT_GENERATOR_VERSION,
    ):
        return False
    if spec.control is None:
        return spec.level in _levels(spec.knob)
    return (spec.level, spec.control) in _CONTROL_PAIRS[spec.knob]


def _listed(items: list[str]) -> str:
    if len(items) < 2:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def describe_pins(report: _PinReport) -> str:
    """A pin report as one sentence in plain words.

    It says which knob's contrast it is, across which arms, and whether everything else was held
    fixed.  A refused report names each thing that differed, and a report with something measured
    and reported (the distractor knob's tool-block size) names that.  Each is named as the pin
    ledger names it; the ledger's own detail strings are left to the report.
    """
    names = {row.row_id: row.held for row in _pin_ledger(report.knob)}
    arms = _listed(sorted(report.records))
    contrast = f"The {report.knob} contrast across {arms}"
    reported = [names[row_id] for row_id, _ in report.reported]
    if report.violations:
        differed = [names[row_id] for row_id, _ in report.violations]
        sentence = (
            f"{contrast} is refused, because its arms differ in more than the {report.knob} "
            f"level: {'; '.join(differed)}"
        )
        if reported:
            sentence += f" (also reported: {'; '.join(reported)})"
        return sentence + "."
    sentence = f"{contrast} holds everything but the {report.knob} level fixed"
    if reported:
        sentence += (
            f", apart from what is measured and reported rather than held: {'; '.join(reported)}"
        )
    return sentence + "."
