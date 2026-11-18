"""Pending a decision: where the open model's wall-clock allowance comes from.

**The question.**  The design says the notebook's `WALL_CLOCK_HOURS` entry for the version 2
design "is set by Session B2a from the measured throughput of its own phase 1 (no fixed figure
is written here)", and the plan says "its wall-clock budget is set from phase 1's measured
throughput".  The build session has no GPU, so the only phase 1 it can measure is against a fake
model, whose pace says nothing about Qwen3.8-27B on an A100 or an H100.  Taylor's cap for this
run is in Colab units (300 on an A100, or the H100 equivalent read in Colab), not in hours.

**Proposed:** the notebook types no hours for `card-v2`.  Phase 1 on Colab writes its measured
seconds per episode and the hours the 16,800 episodes would take at that pace
(`tests/test_c2_notebook.py` holds both figures).  The phase 3 cell, when the configuration cell
gives no hours, passes that projection and a quarter more, read from the durable folder's
`phase1.json`; the run's session checks the figure against Taylor's units at the rate Colab shows
before it starts phase 3, and types a smaller one into the configuration cell if the units do
not cover it.
**A no** has the build session type a figure for `card-v2` beside the other two, and says which.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tests.c2_support import DESIGN, NOTEBOOK

CONFIG_MARK = "# Configuration: the only cell to edit."


def code_cells() -> list[str]:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def configuration(design: str) -> dict[str, Any]:
    (source,) = [text for text in code_cells() if text.startswith(CONFIG_MARK)]
    assert source.count('DESIGN = "card"') == 1
    ns: dict[str, Any] = {}
    exec(source.replace('DESIGN = "card"', f'DESIGN = "{design}"'), ns)
    return ns


def phase3_cell() -> str:
    (source,) = [text for text in code_cells() if 'step("phase3"' in text]
    return source


def test_the_notebook_types_no_hours_for_card_v2() -> None:
    (source,) = [text for text in code_cells() if text.startswith(CONFIG_MARK)]
    assert not re.search(r'"card-v2"\s*:\s*[0-9]', source), source
    assert configuration(DESIGN)["WALL_CLOCK_HOURS"] is None
    assert configuration("card")["WALL_CLOCK_HOURS"] == 6.0
    assert configuration("knob-probe")["WALL_CLOCK_HOURS"] == 2.0


def test_phase_3_is_given_phase_1s_projection_and_a_quarter_more(tmp_path: Path) -> None:
    (tmp_path / "phase1.json").write_text(json.dumps({"passed": True, "projected_hours": 12.0}))
    calls: list[tuple[str, ...]] = []
    ns = {**configuration(DESIGN), "DRIVE_DIR": str(tmp_path),
          "step": lambda *args: calls.append(tuple(str(arg) for arg in args))}
    exec(phase3_cell(), ns)
    assert len(calls) == 1 and calls[0][:2] == ("phase3", "--wall-clock-hours")
    assert float(calls[0][2]) == 15.0


def test_hours_typed_into_the_configuration_cell_are_the_ones_used(tmp_path: Path) -> None:
    (tmp_path / "phase1.json").write_text(json.dumps({"passed": True, "projected_hours": 12.0}))
    calls: list[tuple[str, ...]] = []
    ns = {**configuration(DESIGN), "DRIVE_DIR": str(tmp_path), "WALL_CLOCK_HOURS": 9.5,
          "step": lambda *args: calls.append(tuple(str(arg) for arg in args))}
    exec(phase3_cell(), ns)
    assert calls == [("phase3", "--wall-clock-hours", "9.5")]


def test_the_other_designs_cell_is_called_as_it_was() -> None:
    calls: list[tuple[str, ...]] = []
    for design in ("card", "knob-probe"):
        ns = {**configuration(design),
              "step": lambda *args: calls.append(tuple(str(arg) for arg in args))}
        exec(phase3_cell(), ns)
    assert calls == [("phase3", "--wall-clock-hours", "6.0"),
                     ("phase3", "--wall-clock-hours", "2.0")]
