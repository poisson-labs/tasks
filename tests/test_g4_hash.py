"""The generator hashes from 0.5.0: each is one literal, every copy of it agrees, and a driver runs
on that generator and no other, frozen as tests.

The 0.5.0 change edits `tasks.py`, `surface.py` and `knobs.py`, whose bytes are the built-in
generator's hash, and the own-tools generator's modules, so both hashes move (ruled 2026-11-15).
The new values cannot be known before the build exists: a hash is of the build's own bytes.  So
this file holds no new value.  It reads the literal the build sets and holds everything else to it.

**How the build sets it.**  The built-in literal is `FROZEN_GENERATOR_HASH` in
`tests/test_frozen_generator.py`; the own-tools literal is `OWN_GENERATOR_HASH` in
`tests/test_o2b_kept.py`.  The build measures each hash on its finished tree and writes it there,
and in each copy named below, as the frozen file's docstring says a deliberate change does.  This
file then passes with no edit.

Shapes decided here
-------------------

**1. The built-in hash is one literal.**  The literal is sixty-four lowercase hex characters, it is
not the hash 0.4.2 had (`38a8db83...`, generator `"3"`), and these all equal it: the hash a task
made at the default label carries, at a card seed, on both splits and for a spread arm as for the
base task; `calibration_run.EXPECTED_GENERATOR_HASH`; the knob probe's
`FROZEN_GENERATOR_HASH`; `tests/test_k9_driver.py`'s `HASH`; `tests/pv_support.py`'s
`BUILT_IN_GENERATOR`; and the value CI's hash step holds (`.github/workflows/ci.yml`).

**2. The own-tools hash is one literal** in the same way: not 0.4.2's (`f941d7f8...`, `"own-3"`),
and equal to what `own.generator.generator_hash()` computes, to the hash an own-tools task
carries, to `tests/pv_support.py`'s `OWN_TOOLS_GENERATOR` and to CI's value.

**3. A driver refuses any other generator.**  The knob probe's check returns the literal on this
tree, and told to expect a hash no generator has it refuses in one line that names both.  The card
driver's preflight, told to expect the same, stops before it asks the server anything, in one
line that names both.  `tests/test_k9_driver.py` holds the probe's refusal through a whole run; here it
is held at the check itself, for both drivers.
"""

from __future__ import annotations

import re
import types
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration_run as run
from poisson_tasks import knob_probe as probe
from poisson_tasks.arms import arm_from_id
from poisson_tasks.own import generator as own
from poisson_tasks.tasks import generate
from tests import pv_support, test_frozen_generator, test_k9_driver, test_o2b_kept
from tests.g4_support import BUILT_IN_HASH_BEFORE, OWN_HASH_BEFORE, OWN_LABEL
from tests.k3_support import CARD_SEEDS
from tests.o2_support import fixture_sets

REPO = Path(__file__).resolve().parent.parent
CI = REPO / ".github" / "workflows" / "ci.yml"
HASH = re.compile(r"[0-9a-f]{64}")

# The one literal of each generator, read from where the build sets it.
BUILT_IN = test_frozen_generator.FROZEN_GENERATOR_HASH
OWN = test_o2b_kept.OWN_GENERATOR_HASH
# A hash no generator has: what a driver is told to expect, to see it refuse.
OTHER = "0" * 64


def ci_value(name: str) -> str:
    """The value CI's hash step holds under `name`, which the workflow states once."""
    (value,) = re.findall(rf"^\s*{name}: ([0-9a-f]+)\s*$", CI.read_text(encoding="utf-8"), re.M)
    return str(value)


def test_the_built_in_hash_is_one_literal_and_every_copy_equals_it() -> None:
    """Shape 1."""
    assert HASH.fullmatch(BUILT_IN), BUILT_IN
    assert BUILT_IN != BUILT_IN_HASH_BEFORE
    made = {
        generate(arm_from_id(arm_id, split=split), CARD_SEEDS[0]).generator_hash
        for arm_id in ("distractor:r0@k16", "spread:p1", "spread:p4", "depth:d3")
        for split in ("eval", "train")
    }
    assert made == {BUILT_IN}
    copies = {
        "calibration_run.EXPECTED_GENERATOR_HASH": run.EXPECTED_GENERATOR_HASH,
        "knob_probe.FROZEN_GENERATOR_HASH": probe.FROZEN_GENERATOR_HASH,
        "tests/test_k9_driver.py HASH": test_k9_driver.HASH,
        "tests/pv_support.py BUILT_IN_GENERATOR": pv_support.BUILT_IN_GENERATOR,
        "ci.yml BUILT_IN_GENERATOR_HASH": ci_value("BUILT_IN_GENERATOR_HASH"),
    }
    assert {name: value for name, value in copies.items() if value != BUILT_IN} == {}


def test_the_own_tools_hash_is_one_literal_and_every_copy_equals_it() -> None:
    """Shape 2."""
    assert HASH.fullmatch(OWN), OWN
    assert OWN != OWN_HASH_BEFORE
    assert OWN != BUILT_IN
    task = own.generate(
        fixture_sets()["petstore"], arm_from_id("spread:p1", generator_version=OWN_LABEL), 404
    )
    copies = {
        "own.generator.generator_hash()": own.generator_hash(),
        "an own-tools task's generator_hash": task.generator_hash,
        "tests/pv_support.py OWN_TOOLS_GENERATOR": pv_support.OWN_TOOLS_GENERATOR,
        "ci.yml OWN_TOOLS_GENERATOR_HASH": ci_value("OWN_TOOLS_GENERATOR_HASH"),
    }
    assert {name: value for name, value in copies.items() if value != OWN} == {}


PROBE_ARMS = ("spread:p1", "spread:p4", "depth:d1")


def test_the_probe_runs_on_the_literal_and_refuses_any_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shape 3, the knob probe."""
    assert probe.check_generator(PROBE_ARMS) == BUILT_IN
    monkeypatch.setattr(probe, "FROZEN_GENERATOR_HASH", OTHER)
    with pytest.raises(probe.GeneratorMoved) as refused:
        probe.check_generator(PROBE_ARMS)
    said = str(refused.value)
    assert "\n" not in said and BUILT_IN in said and OTHER in said, said


def test_the_card_drivers_preflight_stops_on_any_other_before_it_asks_the_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Shape 3, the card driver."""
    asked: list[Any] = []
    pin = types.SimpleNamespace(gpu="L4")
    ctx: Any = types.SimpleNamespace(pin=pin, base_url="http://127.0.0.1:9/v1")
    monkeypatch.setattr(run, "gpu_facts", lambda: {"name": "Tesla L4", "driver_version": "0"})
    monkeypatch.setattr(run, "check_server", lambda *a, **k: asked.append("server"))
    monkeypatch.setattr(run, "check_thinking_off", lambda *a, **k: asked.append("thinking"))
    monkeypatch.setattr(run, "EXPECTED_GENERATOR_HASH", OTHER)
    assert run.cmd_preflight(ctx) == 1
    said = capsys.readouterr().out.strip()
    assert asked == []
    assert said.startswith("STOP: ") and "\n" not in said, said
    assert BUILT_IN in said and OTHER in said, said
