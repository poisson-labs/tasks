"""K9.3, the gates before the run: phase 1's, as the spec splits it, and the notebook's own for Qwen.

The spec: phase 1, before anything else, is one attempt at each of phase 1's three seeds per arm.
The existing `plumbing_gate` applies to the seven base arms, its no-call clause read since
2026-10-13 as the cards' share rule: more than 0.10 of the 21 base episodes, pooled, without a tool
call stops phase 1, so 3 or more (a new pre-registration of that one clause, made after the first
gpt-5-nano run stopped on 1 of 21; `test_k9_regate.py` pins it).  The other eleven are checked
only for plumbing (every episode scores and none carries an instrument label), because "half reach
the structural minimum" and "at least one tool call" could stop the probe on a knob that bites
hard.  For Qwen the notebook's probe-only design applies the plumbing and instrument checks and
the context checks (no context stop; the headroom gate) to every arm, and its leaky floor and
no-call stop to the seven base arms only.

How the base arms' gate is read (pooled, one call) is pending its own yes/no
(`test_k9_pending_phase1_pooled.py`); every case here passes or fails the same way read per arm.
"""

from __future__ import annotations

from typing import Any

from poisson_tasks import calibration as cal
from tests.k9_support import ARMS, BASES, CONTROLS, TOPS, episode

PHASE1 = (1180681854, 601375552, 2652385879)
CAP = 16384 - 2048


def phase1(**override: dict[str, Any]) -> dict[str, list[cal.EpisodeRecord]]:
    """Every arm's three phase 1 episodes, each solving its task with its minimum calls; an arm
    named takes `calls`, `label` and `passed` from `override[arm]`."""
    out: dict[str, list[cal.EpisodeRecord]] = {}
    for arm in ARMS:
        given = dict(override.get(arm.replace(":", "_").replace("+", "_"), {}))
        rows = []
        for index, seed in enumerate(PHASE1):
            minimum = cal._minimum_calls(arm)
            assert minimum is not None
            calls = given.get("calls", minimum)
            label = given.get("label", "passed" if given.get("passed", True) else "wrong_state")
            if index in given.get("skip", ()):
                continue
            rows.append(episode(arm, seed, 0, label=label, calls=calls))
        out[arm] = rows
    return out


def verdict(
    records: dict[str, list[cal.EpisodeRecord]], tallies: dict[str, dict[str, int]] | None = None
) -> Any:
    from poisson_tasks import knob_probe as probe

    return probe.phase1_verdict(records, tallies or {})


def test_clean_episodes_pass() -> None:
    found = verdict(phase1())
    assert found.passed and found.reasons == ()
    assert found.bases.episodes == 21


def test_a_top_or_a_control_that_never_calls_a_tool_does_not_stop_phase_1() -> None:
    found = verdict(
        phase1(
            **{
                "block_k64": {"calls": 0, "passed": False},
                "shape_w1_len(w4)": {"calls": 0, "passed": False},
            }
        )
    )
    assert found.passed, found.reasons


def test_a_top_that_stops_short_of_its_minimum_does_not_stop_phase_1() -> None:
    found = verdict(
        phase1(
            **{
                "spread_p4": {"calls": 2, "passed": False},
                "faults_f4": {"calls": 1, "passed": False},
            }
        )
    )
    assert found.passed, found.reasons


def test_a_base_that_never_calls_a_tool_stops_phase_1() -> None:
    """Its three episodes are 3 of the 21: the share rule's boundary."""
    found = verdict(phase1(**{"history_t0": {"calls": 0, "passed": False}}))
    assert not found.passed
    assert any(r.startswith("base arms: ") and "made no tool call" in r for r in found.reasons)


def test_bases_mostly_short_of_their_minimum_stop_phase_1() -> None:
    short = {
        name: {"calls": 1, "passed": False}
        for name in ("similarity_s0", "faults_f0", "history_t0", "block_k8")
    }
    found = verdict(phase1(**short))
    assert not found.passed
    assert any("reached their structural minimum" in r for r in found.reasons)


def test_an_instrument_label_or_a_tally_on_any_arm_stops_phase_1() -> None:
    labelled = verdict(phase1(**{"similarity_s3": {"label": "api_error", "calls": 0}}))
    assert not labelled.passed
    assert any(
        r.startswith("similarity:s3: ") and "instrument label" in r for r in labelled.reasons
    )
    tallied = verdict(phase1(), {"arguments:a2+len(a8)": {"api_error": 1}})
    assert not tallied.passed
    assert any(r.startswith("arguments:a2+len(a8): ") for r in tallied.reasons)
    on_base = verdict(phase1(), {"spread:p1": {"wall_timeout": 1}})
    assert not on_base.passed


def test_an_episode_missing_on_any_arm_stops_phase_1() -> None:
    for arm in (TOPS[3], CONTROLS[0], BASES[2]):
        found = verdict(phase1(**{arm.replace(":", "_").replace("+", "_"): {"skip": [1]}}))
        assert not found.passed, arm
        assert any(r.startswith(f"{arm}: 2 of its 3") for r in found.reasons), found.reasons


# ---------------------------------------------------------------------------
# the notebook's own gates, for Qwen
# ---------------------------------------------------------------------------


def facts(**override: dict[str, int]) -> dict[str, dict[str, int]]:
    out = {arm: {"episodes": 3, "max_prompt_tokens": 4000, "context_stops": 0} for arm in ARMS}
    for name, values in override.items():
        out[name.replace("__", ":")].update(values)
    return out


def gate(
    records: dict[str, list[cal.EpisodeRecord]],
    found_facts: dict[str, dict[str, int]] | None = None,
    tallies: dict[str, dict[str, int]] | None = None,
) -> Any:
    from poisson_tasks import knob_probe as probe

    return probe.notebook_verdict(records, tallies or {}, found_facts or facts(), prompt_cap=CAP)


def test_the_notebooks_gates_pass_clean_episodes() -> None:
    found = gate(phase1())
    assert found.proceed and found.reasons == ()


def test_the_floor_and_the_no_call_stop_read_the_base_arms_only() -> None:
    tops_silent = {
        arm.replace(":", "_").replace("+", "_"): {"calls": 0, "passed": False}
        for arm in TOPS + CONTROLS
    }
    assert gate(phase1(**tops_silent)).proceed
    bases_failing = {arm.replace(":", "_"): {"passed": False} for arm in BASES}
    floored = gate(phase1(**bases_failing))
    assert not floored.proceed and any(r.startswith("floor: ") for r in floored.reasons)
    silent = gate(phase1(**{"block_k8": {"calls": 0, "passed": False}}))
    assert not silent.proceed and any("made no tool call" in r for r in silent.reasons)


def test_instrument_failures_stop_on_every_arm() -> None:
    for arm in ("spread:p4", "shape:w1+len(w4)", "history:t0"):
        name = arm.replace(":", "_").replace("+", "_")
        found = gate(phase1(**{name: {"label": "api_error", "calls": 0}}))
        assert not found.proceed, arm
        assert any("instrument failure" in r for r in found.reasons), arm
    tallied = gate(phase1(), tallies={"block:k64": {"api_error": 2}})
    assert not tallied.proceed


def test_the_context_checks_stop_on_every_arm() -> None:
    ended = gate(phase1(), facts(**{"faults__f0+len(f4)": {"context_stops": 1}}))
    assert not ended.proceed and any("context cap" in r for r in ended.reasons)
    near = gate(phase1(), facts(**{"history__t2400": {"max_prompt_tokens": 10753}}))
    assert not near.proceed and any("past 75%" in r for r in near.reasons)
    under = gate(phase1(), facts(**{"block__k64": {"max_prompt_tokens": 10752}}))
    assert under.proceed
