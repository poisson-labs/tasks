"""What the recipe tests share: the recipe table's rows, the two kinds of knob, and a fresh
interpreter.

The test files are `tests/test_r0_recipes.py` (the recipe table, with the invariant-to-test table
and the shapes decided) and `tests/test_r0_config.py` (recipes in the settings file).  Nothing here
asserts anything but that a fresh interpreter exited cleanly.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from typing import Any

from poisson_tasks.knobs import arm_id

# Depth and the distractor dial are on the published cards; the other seven ship through the
# probe.
PUBLISHED_KNOBS = ("depth", "distractor")
PROBE_KNOBS = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")

# The recipe table, every recipe but `card`, with every knob shipped: (what it asks, the arms, tasks
# per level, attempts, episodes).
ROWS: dict[str, tuple[str, tuple[str, ...], int, int, int]] = {
    "first-look": (
        "where does depth start to hurt?",
        ("depth:d1", "depth:d3", "depth:d8"),
        10,
        1,
        30,
    ),
    "tool-choice": (
        "can it pick the right tool among lookalikes and in a long list?",
        ("similarity:s0", "similarity:s3", "block:k8", "block:k64"),
        10,
        1,
        40,
    ),
    "error-recovery": (
        "does it retry when a call fails?",
        ("faults:f0", "faults:f1", "faults:f2", "faults:f4"),
        10,
        1,
        40,
    ),
    "long-sessions": (
        "does earlier work in the conversation throw it off?",
        ("history:t0", "history:t600", "history:t2400"),
        10,
        1,
        30,
    ),
    "planning": (
        "chains and parallel steps",
        ("depth:d1", "depth:d3", "depth:d8", "shape:w1", "shape:w4"),
        10,
        1,
        50,
    ),
    "reading-and-filling": (
        "can it assemble a value from outputs and fill arguments exactly?",
        ("spread:p1", "spread:p4", "arguments:a2", "arguments:a8"),
        10,
        1,
        40,
    ),
    "profile": (
        "one line per knob: how much each moves this model",
        (
            "depth:d1",
            "depth:d8",
            "similarity:s0",
            "similarity:s3",
            "faults:f0",
            "faults:f4",
            "history:t0",
            "history:t2400",
            "block:k8",
            "block:k64",
            "arguments:a2",
            "arguments:a8",
            "shape:w1",
            "shape:w4",
            "spread:p1",
            "spread:p4",
        ),
        20,
        2,
        640,
    ),
}
NAMES = (*ROWS, "card")
CARD_TASKS, CARD_ATTEMPTS = 60, 5


def arms() -> Any:
    return importlib.import_module("poisson_tasks.arms")


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


def cal() -> Any:
    return importlib.import_module("poisson_tasks.calibration")


def knob_of(arm: str) -> str:
    return arm.split(":", 1)[0]


def in_order(items: Any) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def card_arms() -> tuple[str, ...]:
    """The published design's arm ids, in `calibration.arm_specs()`'s order."""
    return tuple(arm_id(spec) for spec in cal().arm_specs())


def full_design(name: str) -> tuple[str, ...]:
    return card_arms() if name == "card" else ROWS[name][1]


def tasks_and_attempts(name: str) -> tuple[int, int]:
    return (CARD_TASKS, CARD_ATTEMPTS) if name == "card" else ROWS[name][2:4]


def fresh(code: str) -> str:
    """Run `code` in a fresh interpreter with this one's environment, and give its stdout."""
    done = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
        env=dict(os.environ),
    )
    assert done.returncode == 0, done.stderr[-3000:]
    return done.stdout
