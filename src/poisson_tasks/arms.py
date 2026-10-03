"""Arms by their readable id, the one generator-version constant, and the pin ledger in words.

A names-only skeleton.  The three names cannot go in `knobs.py`, whose public surface frozen
tests pin exactly; `tests/test_fd1_arms.py` says what each one does.  Importing this module
imports no `verifiers` and none of `tasks`, `calibration` and `export`.
"""

from __future__ import annotations

from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.knobs import PinReport as _PinReport

__all__ = ["arm_from_id", "DEFAULT_GENERATOR_VERSION", "describe_pins"]

DEFAULT_GENERATOR_VERSION = "0"


def arm_from_id(
    arm_id: str,
    *,
    strictness: str = "strict",
    split: str = "eval",
    generator_version: str = DEFAULT_GENERATOR_VERSION,
) -> _ArmSpec:
    raise NotImplementedError


def describe_pins(report: _PinReport) -> str:
    raise NotImplementedError
