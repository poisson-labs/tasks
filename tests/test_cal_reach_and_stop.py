"""Depth is read on reaching the goal, with stopping at the goal shown beside it.

Every depth arm offers the whole eight-stage ladder, so below the top level the strict rate
asks two things at once: carry the record to the goal, and stop there.  The two calibrated
models fail on different halves.  gpt-5-nano's leaky rate falls at d3 and d5 (it does not
reach the goal); Qwen3-8B's leaky rate is 0.97 or more at every depth while its strict rate is
0.000 at d1, because it carries the record past the goal (overshoot).

So every cell now carries:
- its overshoot share (scored episodes that reached the goal and went past it);
- a task-clustered interval on leaky pass@1.

Depth's adjacent levels are also compared on leaky pass@1, which is reaching the goal. That
comparison uses the same pairing, the same two-clause rule, and saturation judged on the leaky
rate. The card reads depth on that table, with the overshoot column beside it.

Strict stays computed, published and first in the level table, and the strict comparisons stay
as they were.  Nothing here needs a model: both committed cards re-render from their records.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks.knobs import levels

MODEL = "m-reach"
TASKS = 20
N = 5
LEAKY_BY_LEVEL = {1: 5, 2: 4, 3: 2, 5: 2, 8: 1}
"""Per depth level, how many of a task's five attempts reach the goal (leaky)."""
STRICT_BY_LEVEL = {1: 0, 2: 1, 3: 2, 5: 2, 8: 1}
"""And how many of those also stop at it (strict); the rest of the reaching ones overshoot."""


def _provenance() -> cal.Provenance:
    seeds = list(range(3000, 3000 + cal.S))
    return cal.Provenance(
        package_version="0.0.1", engine_hash="e" * 64, generator_hash="g" * 64,
        vocabulary_hash="v" * 64, verifiers_version="0.3.1", harness_id="null",
        models=[{"id": MODEL, "revision": MODEL, "endpoint_host": "h"}],
        decoding=dict(cal.DECODING), seed_list=seeds,
        seed_list_hash=hashlib.sha256(json.dumps(seeds).encode()).hexdigest(),
        S=cal.S, n=N, k_values=[1, 2, 5], bootstrap_resamples=200, bootstrap_seed=20260922,
        delta_star=0.15, saturation_high=0.95, saturation_low=0.05, instrument_threshold=0.02,
        rate_read_date="2026-09-30", serving={MODEL: {"kind": "hosted", "endpoint_host": "h"}},
        budget=dict(cal.DEFAULT_BUDGET),
    )


def _cells(leaky_of: Callable[[int, int], int] | None = None) -> dict[tuple[str, str], list[cal.EpisodeRecord]]:
    """Depth cells in which reaching falls with depth while stopping improves.  `leaky_of`,
    given (level, task), overrides how many attempts of that task reach the goal."""
    cells: dict[tuple[str, str], list[cal.EpisodeRecord]] = {}
    for level in levels("depth"):
        arm = f"depth:d{level}"
        rows = []
        for task in range(TASKS):
            reach = LEAKY_BY_LEVEL[level] if leaky_of is None else leaky_of(level, task)
            stop = min(STRICT_BY_LEVEL[level], reach)
            for attempt in range(N):
                if attempt < stop:
                    label, strict, leaky = "passed", True, True
                elif attempt < reach:
                    label, strict, leaky = "overshoot", False, True
                else:
                    label, strict, leaky = "wrong_state", False, False
                rows.append(cal.EpisodeRecord(
                    task_id=f"{arm}-{task}", arm_id=arm, model=MODEL, seed=3000 + task,
                    attempt=attempt, strict=strict, leaky=leaky, label=label, turns=level + 1,
                    sampled_calls=level, prompt_tokens=10, cached_input_tokens=0,
                    completion_tokens=5, reasoning_tokens=0))
        cells[(arm, MODEL)] = rows
    return cells


def _table(document: str, heading: str) -> tuple[list[str], list[list[str]]]:
    """The first markdown table after `heading`: its column names and its rows, by position."""
    table: list[str] = []
    for line in document.partition(heading)[2].splitlines():
        if line.startswith("|"):
            table.append(line)
        elif table:
            break
    header = [cell.strip().lower() for cell in table[0].strip().strip("|").split("|")]
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in table[2:]]
    return header, rows


# ---------------------------------------------------------------------------
# the cell figures
# ---------------------------------------------------------------------------


def test_each_cell_carries_its_overshoot_share() -> None:
    artifact = cal.build_artifact(_cells(), _provenance())
    for cell in artifact.cells:
        level = int(cell["arm_id"].removeprefix("depth:d"))
        expected = (LEAKY_BY_LEVEL[level] - STRICT_BY_LEVEL[level]) / N
        assert cell["overshoot_share"] == pytest.approx(expected), cell["arm_id"]
        assert cell["overshoot_count"] == (LEAKY_BY_LEVEL[level] - STRICT_BY_LEVEL[level]) * TASKS


def test_the_leaky_interval_is_task_clustered() -> None:
    """Tasks that differ in how often they reach the goal give an interval; tasks that all
    reach it equally give a point, because the resampling carries each task's attempts whole."""
    varied = cal.build_artifact(
        _cells(lambda level, task: 5 if task % 2 else 1), _provenance())
    uniform = cal.build_artifact(_cells(), _provenance())
    for cell in varied.cells:
        low, high = cell["leaky_at_1_interval"]
        assert low < cell["leaky_at_1"] < high, cell["arm_id"]
    for cell in uniform.cells:
        low, high = cell["leaky_at_1_interval"]
        assert low == high == pytest.approx(cell["leaky_at_1"]), cell["arm_id"]


# ---------------------------------------------------------------------------
# depth compared on reaching the goal
# ---------------------------------------------------------------------------


def test_depth_is_compared_on_reaching_the_goal() -> None:
    """Strict rises from d1 to d3 here while reaching falls, so the two comparisons point
    opposite ways, and the reaching one must follow the leaky rates."""
    artifact = cal.build_artifact(_cells(), _provenance())
    reach = {(row["level_a"], row["level_b"]): row for row in artifact.reach_pairs}
    assert set(reach) == {(1, 2), (2, 3), (3, 5), (5, 8)}
    assert all(row["knob"] == "depth" and row["model"] == MODEL for row in reach.values())
    # d1 reaches the goal on every attempt: saturated on the rate being compared.
    assert reach[(1, 2)]["verdict"] == "excluded"
    assert reach[(2, 3)]["delta"] == pytest.approx(0.4)
    assert reach[(2, 3)]["verdict"] == cal.DISTINGUISHABLE
    assert reach[(3, 5)]["verdict"] == cal.TOO_SMALL
    assert reach[(5, 8)]["delta"] == pytest.approx(0.2)
    assert reach[(5, 8)]["verdict"] == cal.DISTINGUISHABLE
    strict = {(row["level_a"], row["level_b"]): row for row in artifact.pairs
              if row["knob"] == "depth"}
    assert strict[(2, 3)]["delta"] == pytest.approx(-0.2)


def test_a_leaky_comparison_is_paired_within_the_resample() -> None:
    """The same paired, task-clustered interval as the strict comparisons: tasks whose
    reaching varies give a real interval around the point difference."""
    artifact = cal.build_artifact(
        _cells(lambda level, task: LEAKY_BY_LEVEL[level] - (task % 2 if level == 2 else 0)),
        _provenance())
    row = next(r for r in artifact.reach_pairs if (r["level_a"], r["level_b"]) == (2, 3))
    assert row["low"] < row["delta"] < row["high"]


def test_the_distractor_knob_gets_no_reaching_comparison() -> None:
    """Every distractor level needs the same two calls, and the question there is selection,
    not stopping; its comparisons stay on strict alone."""
    cells = _cells()
    renamed = {}
    for (arm, model), rows in cells.items():
        if arm == "depth:d1":
            for new_arm in ("distractor:r0@k16", "distractor:r2@k16"):
                renamed[(new_arm, model)] = [
                    cal.EpisodeRecord(**{**row.__dict__, "arm_id": new_arm,
                                         "task_id": f"{new_arm}-{row.seed}"}) for row in rows]
    artifact = cal.build_artifact(renamed, _provenance())
    assert artifact.reach_pairs == []


# ---------------------------------------------------------------------------
# the card
# ---------------------------------------------------------------------------


def test_the_level_table_shows_overshoot_and_the_leaky_interval_by_column() -> None:
    artifact = cal.build_artifact(_cells(), _provenance())
    document = cal.render_document(artifact)
    header, rows = _table(document, "### depth")
    assert header.index("strict pass@1") < header.index("leaky pass@1")
    at_over, at_interval = header.index("overshoot"), header.index("leaky 95% interval")
    by_arm = {cell["arm_id"]: cell for cell in artifact.cells}
    assert len(rows) == 5
    for row in rows:
        cell = by_arm[row[0].strip("`")]
        assert row[at_over] == f"{cell['overshoot_share']:.3f}", row
        low, high = cell["leaky_at_1_interval"]
        assert row[at_interval] == f"[{low:.3f}, {high:.3f}]", row


def test_the_card_reads_depth_on_the_reaching_table() -> None:
    artifact = cal.build_artifact(_cells(), _provenance())
    document = cal.render_document(artifact)
    heading = "### depth, on reaching the goal (leaky pass@1)"
    assert heading in document
    reaching_at = document.index(heading)
    assert reaching_at < document.index("| model | knob | levels | delta strict pass@1")
    header, rows = _table(document, heading)
    at_delta, at_verdict = header.index("delta leaky pass@1"), header.index("verdict")
    by_levels = {(row["level_a"], row["level_b"]): row for row in artifact.reach_pairs}
    assert len(rows) == len(by_levels)
    for row in rows:
        a, b = (int(level) for level in row[header.index("levels")].split(" vs "))
        expected = by_levels[(a, b)]
        shown = "n/a" if expected["delta"] is None else f"{expected['delta']:.3f}"
        assert row[at_delta] == shown, row
        assert row[at_verdict].startswith(expected["verdict"]), row


def test_the_readme_lines_carry_reaching_and_stopping() -> None:
    artifact = cal.build_artifact(_cells(), _provenance())
    lines = cal.render_readme_lines(artifact).splitlines()
    by_arm = {cell["arm_id"]: cell for cell in artifact.cells}
    assert len(lines) == 5
    for line in lines:
        arm = line.split("`")[1]
        cell = by_arm[arm]
        assert f"leaky pass@1 {cell['leaky_at_1']:.3f}" in line, line
        assert f"overshoot {cell['overshoot_share']:.3f}" in line, line
