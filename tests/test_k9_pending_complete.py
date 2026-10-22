"""Pending a decision: what makes an arm complete.

**The question.**  "A knob is decided only on complete arms."  The design does not define complete.

**Proposed: every one of the probe's sixty seeds has its two attempts recorded**, scored or
labelled with an instrument failure: what the run engine ran to its end.  Instrument failures
then count in the arm's instrument rate (and void it above 0.02), not against its completeness.
**A no** might ask for two *scored* attempts at every seed, which an arm with one instrument
failure would never reach without a re-run.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from poisson_tasks import calibration as cal
from tests.k9_support import MODEL, cell, every_arm, model_run, seeds60


def arms(cells: Mapping[str, list[cal.EpisodeRecord]]) -> dict[str, dict[str, Any]]:
    from poisson_tasks import knob_probe as probe

    result = probe.analyse({MODEL: model_run(cells)}, expected=(MODEL,))
    found: dict[str, dict[str, Any]] = result["arms"][MODEL]
    return found


def test_an_instrument_failure_is_an_attempt_and_a_missing_one_is_not() -> None:
    labelled = every_arm({}, options={"block:k64": {"instrument": [(7, 1)]}})
    found = arms(labelled)["block:k64"]
    assert found["complete"] and found["episodes"] == 120
    short = every_arm({})
    short["block:k64"] = [
        row for row in cell("block:k64", 54) if (row.seed, row.attempt) != (seeds60()[7], 1)
    ]
    found = arms(short)["block:k64"]
    assert not found["complete"] and found["episodes"] == 119
