"""Pending a yes/no: phase 1's full gate reads the seven base arms pooled.

**The question.**  "The existing `plumbing_gate` applies in full to the seven base arms."  It can
be called once on their 21 episodes together (at least 11 of 21 reach their structural minimum,
none without a tool call), or once per base arm (at least 2 of 3 each).

**Proposed: pooled**, one call on the 21: the function as it stands, applied to the base arms.
**A no** reads it per arm, so one base arm whose three episodes all stop short stops the probe.
"""

from __future__ import annotations

from poisson_tasks import calibration as cal
from tests.k9_support import ARMS, episode

PHASE1 = (1180681854, 601375552, 2652385879)


def records(short: str) -> dict[str, list[cal.EpisodeRecord]]:
    out: dict[str, list[cal.EpisodeRecord]] = {}
    for arm in ARMS:
        minimum = cal._minimum_calls(arm)
        assert minimum is not None
        calls = minimum - 1 if arm == short else minimum
        out[arm] = [episode(arm, seed, 0, passed=arm != short, calls=calls) for seed in PHASE1]
    return out


def test_one_base_arm_short_of_its_minimum_three_times_does_not_stop_phase_1() -> None:
    from poisson_tasks import knob_probe as probe

    found = probe.phase1_verdict(records("spread:p1"), {})
    assert found.passed, found.reasons
    assert found.bases.episodes == 21 and found.bases.reached_minimum == 18
    per_arm = cal.plumbing_gate(records("spread:p1")["spread:p1"])
    assert not per_arm.passed
