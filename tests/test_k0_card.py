"""Cost and time on every card: the figures, where the card prints them, and what they never
decide.

Every cell gains what its scored episodes
cost in calls and tokens, and, when its records carry time, what they took in seconds.  Every
level table and the instrument table print median model calls, median tokens and median episode
seconds beside the pass rates; the cost section prints the rest.  Time is never compared and
never decides anything: it belongs to the serving and its load, so the card prints the run's
concurrency with it.

A figure the records do not carry is not recorded: it is `None` in the artifact and the card
prints *not recorded*, never a zero and never a guess.  Both published cards recorded no time.

Shapes decided here
-------------------

**1. The artifact's names.**  Every cell gains `model_calls_mean`, `tool_calls_mean`,
`tool_calls_median`, `tokens_mean`, `tokens_p90`, `tokens_per_strict_pass`,
`first_request_prompt_tokens_median`, `episode_seconds_median`, `episode_seconds_p90`,
`model_seconds_median`, `model_seconds_p90`, `harness_seconds_median`, `harness_seconds_p90`
and `setup_seconds_median`; each figure not recorded is `null`, so the key is always there.
Tokens are prompt, cached input and completion, as `tokens_median` already counts them.

**2. Over the scored episodes, and over those that recorded the figure.**  Every figure is over
the cell's scored episodes, like every other figure on the card.  A time or first-request figure
is over the scored episodes that recorded it, and is `None` when none did.

**3. The 90th percentile is the module's own quantile rule:** the smallest value whose
cumulative share reaches 0.9, which at ten values is the ninth, not the tenth.

**4. Tokens per strict pass is the mean tokens divided by strict pass@1**, and `None` (printed
*n/a*) when nothing passed strictly.

**5. Columns are read by the position their header gives them,** as the card's other column tests
read them, and a printed number is compared with the artifact's own figure to the nearest whole
unit; the fixtures keep every figure a whole number or several units from every other, so the
card may print seconds to any precision.  The header names are pinned as written here.

**6. Concurrency is printed in each section that prints time** (levels, instrument arms, cost)
and in the provenance, as the number or as *not recorded*.  `Provenance.as_dict` leaves it out
when it is `None`, so a published provenance block keeps its bytes.  Whether the published cards
gain one is `tests/test_k0_published_concurrency.py`'s.

**7. The committed cards keep every figure.**  Each committed `artifact.json` with the new cell
keys (and a provenance `concurrency`, if it has one) taken out is, byte for byte, the file
published before them; its SHA-256 is pinned below.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import math
import re
import statistics
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks.knobs import arm_id, levels

REPO = Path(__file__).resolve().parent.parent
CARDS = REPO / "calibration"
MODEL = "gpt-5-nano-2025-08-07"
N = 5

# The new keys on every cell.
TIME_KEYS = ("episode_seconds_median", "episode_seconds_p90", "model_seconds_median",
             "model_seconds_p90", "harness_seconds_median", "harness_seconds_p90",
             "setup_seconds_median")
NEW_CELL_KEYS = ("model_calls_mean", "tool_calls_mean", "tool_calls_median", "tokens_mean",
                 "tokens_p90", "tokens_per_strict_pass", "first_request_prompt_tokens_median",
                 *TIME_KEYS)

# Each committed artifact.json as published before the new keys, by SHA-256.
PUBLISHED = {
    "gpt-5-nano-2025-08-07":
        "e8ffb215e7e7dfcf474979fd35cdd35d7ab89dcd57729f00a3498f7597f74242",
    "qwen3-8b-b968826d":
        "c111dc4fa5a37f228ed51c9db2776a0b8d2788418994a2d41d2b8768447a0707",
}

NOT_RECORDED = "not recorded"


def provenance(model: str = MODEL, **over: Any) -> cal.Provenance:
    seeds = list(range(1000, 1000 + cal.S))
    base: dict[str, Any] = dict(
        package_version="0.1.0", engine_hash="e" * 64, generator_hash="g" * 64,
        vocabulary_hash="v" * 64, verifiers_version="0.3.1", harness_id="null",
        models=[{"id": model, "revision": model, "endpoint_host": "h"}],
        decoding=dict(cal.DECODING), seed_list=seeds,
        seed_list_hash=hashlib.sha256(json.dumps(seeds).encode("utf-8")).hexdigest(),
        S=cal.S, n=N, k_values=[1, 2, 5], bootstrap_resamples=200, bootstrap_seed=20260922,
        delta_star=0.15, saturation_high=0.95, saturation_low=0.05, instrument_threshold=0.02,
        rate_read_date="2026-09-30", serving={model: {"kind": "hosted", "endpoint_host": "h"}},
        budget=dict(cal.DEFAULT_BUDGET),
    )
    base.update(over)
    return cal.Provenance(**base)


def record(*, task: int, attempt: int, arm: str = "depth:d3", model: str = MODEL,
           strict: bool = False, label: str | None = None, **over: Any) -> cal.EpisodeRecord:
    if label is None:
        label = "passed" if strict else "wrong_state"
    base: dict[str, Any] = dict(
        task_id=f"{arm}-{task}", arm_id=arm, model=model, seed=1000 + task, attempt=attempt,
        strict=strict, leaky=strict, label=label, turns=4, sampled_calls=3, prompt_tokens=3000,
        cached_input_tokens=0, completion_tokens=60, reasoning_tokens=0,
    )
    base.update(over)
    return cal.EpisodeRecord(**base)


def p90(values: Sequence[float]) -> float:
    """The smallest value whose cumulative share reaches 0.9."""
    ordered = sorted(values)
    return ordered[math.ceil(0.9 * len(ordered)) - 1]


def columns_of(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def tables(text: str) -> list[list[str]]:
    """Every markdown table in `text`, as its lines."""
    out: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("|"):
            current.append(line)
        elif current:
            out.append(current)
            current = []
    if current:
        out.append(current)
    return out


def rows_by_arm(text: str) -> dict[str, dict[str, str]]:
    """Every table row in `text` that names an arm, merged by arm across tables: column name,
    as its header gives it, to the printed value."""
    out: dict[str, dict[str, str]] = {}
    for table in tables(text):
        header = [column.lower() for column in columns_of(table[0])]
        if not header or header[0] != "arm":
            continue
        for line in table[2:]:
            values = columns_of(line)
            assert len(values) == len(header), line
            out.setdefault(values[0].strip("`"), {}).update(zip(header, values, strict=True))
    return out


def section(document: str, start: str, end: str | None) -> str:
    after = document.partition(start)[2]
    assert after, f"no {start!r} in the card"
    return after.partition(end)[0] if end is not None else after


def printed(value: str, figure: float | None, *, none: str = NOT_RECORDED) -> None:
    """A printed figure is the artifact's figure to the nearest whole unit, and a figure not
    recorded is printed as `none`."""
    if figure is None:
        assert value == none, (value, none)
    else:
        assert float(value) == pytest.approx(figure, abs=0.5), (value, figure)


# ---------------------------------------------------------------------------
# the figures
# ---------------------------------------------------------------------------

# Two tasks of five attempts.  Tokens per episode are ten distinct values, so the mean, the
# median and the 90th percentile all differ, and at ten values the quantile rule's ninth
# value differs from the tenth.
TOKENS = (1000, 1200, 1400, 1600, 1800, 2000, 2600, 3200, 9000, 30000)
TURNS = (2, 2, 2, 3, 3, 3, 4, 9, 9, 12)
TOOL_CALLS = (1, 1, 1, 2, 2, 2, 3, 8, 8, 11)


def spend_cell(**over: Any) -> list[cal.EpisodeRecord]:
    """Ten scored episodes, the first three strict passes and the next two leaky passes only,
    and one instrument failure that burned far more than any of them and must count in none of
    the figures."""
    rows = []
    for index in range(10):
        reached: dict[str, Any] = {"label": "overshoot", "leaky": True} if index in (3, 4) else {}
        rows.append(record(task=index // N, attempt=index % N, strict=index < 3,
                           turns=TURNS[index], sampled_calls=TOOL_CALLS[index],
                           prompt_tokens=TOKENS[index] - 100, cached_input_tokens=40,
                           completion_tokens=60, **reached, **over))
    rows.append(record(task=2, attempt=0, label="api_error", turns=40, sampled_calls=39,
                       prompt_tokens=900_000, completion_tokens=900, **over))
    return rows


def figures_of(cell: Sequence[cal.EpisodeRecord], **prov: Any) -> dict[str, Any]:
    prov.setdefault("instrument_threshold", 1.0)
    built = cal.build_artifact({(cell[0].arm_id, cell[0].model): list(cell)}, provenance(**prov))
    return built.cells[0]


def test_k0_3_every_cell_carries_its_calls_and_tokens() -> None:
    figures = figures_of(spend_cell())
    mean_tokens = sum(TOKENS) / 10
    assert figures["pass_at_1"] == pytest.approx(0.3)
    assert figures["leaky_at_1"] == pytest.approx(0.5)
    assert figures["model_calls_mean"] == pytest.approx(sum(TURNS) / 10)
    assert figures["tool_calls_mean"] == pytest.approx(sum(TOOL_CALLS) / 10)
    assert figures["tool_calls_median"] == statistics.median(TOOL_CALLS)
    assert figures["tokens_mean"] == pytest.approx(mean_tokens)
    assert figures["tokens_p90"] == p90(TOKENS) == 9000
    assert figures["tokens_per_strict_pass"] == pytest.approx(mean_tokens / 0.3)
    # The figures already on the card are the same episodes' (unchanged; the new ones sit
    # beside them).
    assert figures["tokens_median"] == statistics.median(TOKENS)
    assert figures["model_calls_median"] == statistics.median(TURNS)


def test_k0_3_tokens_per_strict_pass_is_none_when_nothing_passed() -> None:
    cell = [record(task=index // N, attempt=index % N, strict=False) for index in range(10)]
    figures = figures_of(cell)
    assert figures["pass_at_1"] == 0.0
    assert figures["tokens_per_strict_pass"] is None
    assert figures["tokens_mean"] == pytest.approx(3060.0)


# Per scored episode: (episode, model, harness, setup) seconds and the first request's tokens.
# Ten timed episodes, two scored ones that recorded nothing, and an instrument failure that
# recorded long times and must count in none of the figures.
TIMED = (
    (18.0, 15.5, 2.5, 6.0, 1526), (19.0, 16.0, 3.0, 6.5, 1526), (20.0, 17.0, 3.0, 7.0, 1530),
    (21.0, 18.5, 2.5, 7.5, 1530), (22.0, 19.0, 3.0, 8.0, 1540), (24.0, 20.0, 4.0, 8.5, 1540),
    (26.0, 22.5, 3.5, 9.0, 1550), (30.0, 26.0, 4.0, 9.5, 1550), (60.0, 55.0, 5.0, 10.0, 1560),
    (95.0, 88.0, 7.0, 30.0, 1900),
)


def timed_cell(arm: str = "depth:d3", model: str = MODEL) -> list[cal.EpisodeRecord]:
    rows = [
        record(task=index // N, attempt=index % N, arm=arm, model=model, strict=index == 0,
               episode_seconds=episode, model_seconds=model_s, harness_seconds=harness,
               setup_seconds=setup, first_request_prompt_tokens=first)
        for index, (episode, model_s, harness, setup, first) in enumerate(TIMED)
    ]
    rows += [record(task=2, attempt=attempt, arm=arm, model=model) for attempt in range(2)]
    rows.append(record(task=2, attempt=2, arm=arm, model=model, label="api_error",
                       episode_seconds=900.0, model_seconds=890.0, harness_seconds=10.0,
                       setup_seconds=300.0, first_request_prompt_tokens=9000))
    return rows


def test_k0_3_time_figures_are_over_the_episodes_that_recorded_time() -> None:
    figures = figures_of(timed_cell())
    columns = list(zip(*TIMED, strict=True))
    for name, values in zip(("episode_seconds", "model_seconds", "harness_seconds"), columns,
                            strict=False):
        assert figures[f"{name}_median"] == pytest.approx(statistics.median(values)), name
        assert figures[f"{name}_p90"] == pytest.approx(p90(values)), name
    assert figures["setup_seconds_median"] == pytest.approx(statistics.median(columns[3]))
    assert figures["first_request_prompt_tokens_median"] == statistics.median(columns[4])
    # The two untimed episodes still count where every episode counts.
    assert figures["episodes_scored"] == 12


def test_k0_3_a_cell_whose_records_carry_no_time_has_no_time_figures() -> None:
    figures = figures_of(spend_cell())
    for key in (*TIME_KEYS, "first_request_prompt_tokens_median"):
        assert key in figures and figures[key] is None, key


# ---------------------------------------------------------------------------
# beside the rate, and in the cost section
# ---------------------------------------------------------------------------

LEVEL_COLUMNS = ("median model calls", "median tokens", "median episode seconds")
COST_COLUMNS = {
    "mean model calls": "model_calls_mean", "median model calls": "model_calls_median",
    "mean tool calls": "tool_calls_mean", "median tool calls": "tool_calls_median",
    "mean tokens": "tokens_mean", "median tokens": "tokens_median",
    "90th percentile tokens": "tokens_p90", "tokens per strict pass": "tokens_per_strict_pass",
    "median episode seconds": "episode_seconds_median",
    "90th percentile episode seconds": "episode_seconds_p90",
    "median model seconds": "model_seconds_median",
    "90th percentile model seconds": "model_seconds_p90",
    "median harness seconds": "harness_seconds_median",
    "90th percentile harness seconds": "harness_seconds_p90",
    "median setup seconds": "setup_seconds_median",
}


# Per attempt: skewed, so every cell's mean, median and 90th percentile differ by more than a
# unit.
OFFSETS = (0, 1, 2, 3, 10)


def every_arm_card(concurrency: int | None = None) -> cal.Artifact:
    """A cell for every arm, five attempts at one task each, every figure a whole number or
    several units from every other.  The arms alternate between timed and untimed, so each
    table holds both kinds of row; the numbers move with the arm, so a row printing another
    arm's figure is caught."""
    cells: dict[tuple[str, str], list[cal.EpisodeRecord]] = {}
    for position, spec in enumerate(cal.arm_specs()):
        arm = arm_id(spec)
        timed = position % 2 == 0
        rows = []
        for attempt, offset in enumerate(OFFSETS):
            step = 10 * position + offset
            extra: dict[str, Any] = {}
            if timed:
                extra = dict(episode_seconds=float(100 + 3 * step),
                             model_seconds=float(60 + 2 * step),
                             harness_seconds=float(20 + 3 * offset),
                             setup_seconds=float(5 + offset),
                             first_request_prompt_tokens=1500 + step)
            rows.append(record(task=0, attempt=attempt, arm=arm, strict=attempt == 0,
                               turns=2 + position + 3 * offset,
                               sampled_calls=1 + position + 2 * offset,
                               prompt_tokens=1000 * (position + 1) + 700 * offset, **extra))
        cells[(arm, MODEL)] = rows
    return cal.build_artifact(cells, provenance(concurrency=concurrency))


def test_k0_4_every_level_table_and_the_instrument_table_carry_calls_tokens_and_seconds(
) -> None:
    artifact = every_arm_card()
    document = cal.render_document(artifact)
    figures = {cell["arm_id"]: cell for cell in artifact.cells}
    level_part, _, after = document.partition(cal.INSTRUMENT_TABLE_HEADING)
    instrument_part = after.partition("## Cost per episode")[0]
    seen: dict[str, list[str]] = {"levels": [], "instrument": []}
    for part, text in (("levels", level_part), ("instrument", instrument_part)):
        for table in tables(text):
            header = [column.lower() for column in columns_of(table[0])]
            for name in LEVEL_COLUMNS:
                assert name in header, (name, header)
            for line in table[2:]:
                values = columns_of(line)
                assert len(values) == len(header), line
                cell = figures[values[0].strip("`")]
                printed(values[header.index("median model calls")], cell["model_calls_median"])
                printed(values[header.index("median tokens")], cell["tokens_median"])
                printed(values[header.index("median episode seconds")],
                        cell["episode_seconds_median"])
                seen[part].append(cell["arm_id"])
    assert sorted(seen["levels"]) == sorted(c["arm_id"] for c in artifact.cells
                                            if not c["control"])
    assert sorted(seen["instrument"]) == sorted(c["arm_id"] for c in artifact.cells
                                                if c["control"])
    untimed = [cell for cell in artifact.cells if cell["episode_seconds_median"] is None]
    assert untimed and len(untimed) < len(artifact.cells)


def test_k0_4_the_cost_section_prints_every_figure_of_every_cell() -> None:
    artifact = every_arm_card()
    cost = section(cal.render_document(artifact), "## Cost per episode", "## Adjacent levels")
    rows = rows_by_arm(cost)
    assert sorted(rows) == sorted(cell["arm_id"] for cell in artifact.cells)
    for cell in artifact.cells:
        row = rows[cell["arm_id"]]
        for column, key in COST_COLUMNS.items():
            assert column in row, (column, sorted(row))
            none = "n/a" if key == "tokens_per_strict_pass" else NOT_RECORDED
            printed(row[column], cell[key], none=none)


def test_k0_4_tokens_per_strict_pass_prints_na_when_nothing_passed() -> None:
    cell = [record(task=0, attempt=attempt) for attempt in range(N)]
    artifact = cal.build_artifact({("depth:d3", MODEL): cell}, provenance())
    cost = section(cal.render_document(artifact), "## Cost per episode", "## Adjacent levels")
    assert rows_by_arm(cost)["depth:d3"]["tokens per strict pass"] == "n/a"


# ---------------------------------------------------------------------------
# nothing moves that was there
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("folder", sorted(PUBLISHED))
def test_k0_5_the_committed_cards_keep_every_figure_and_gain_the_new_ones(folder: str) -> None:
    """Every cell of the committed artifact carries every new key, and neither card recorded
    time.  With the new keys taken out, the file is byte for byte the one published before
    them: every key it had keeps its value, and nothing else moved.  A provenance
    `concurrency` is taken out too: whether a published card carries one is a separate
    question (`tests/test_k0_published_concurrency.py`)."""
    stored = json.loads((CARDS / folder / "artifact.json").read_text(encoding="utf-8"))
    for cell in stored["cells"]:
        missing = [key for key in NEW_CELL_KEYS if key not in cell]
        assert not missing, (cell["arm_id"], missing)
        assert all(cell[key] is None for key in TIME_KEYS), cell["arm_id"]
        assert cell["first_request_prompt_tokens_median"] is None, cell["arm_id"]
    before = copy.deepcopy(stored)
    for cell in before["cells"]:
        for key in NEW_CELL_KEYS:
            del cell[key]
    before["provenance"].pop("concurrency", None)
    text = json.dumps(before, indent=2, sort_keys=True) + "\n"
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == PUBLISHED[folder]


# ---------------------------------------------------------------------------
# time is never a verdict
# ---------------------------------------------------------------------------


def depth_cells(model: str, seconds: Sequence[float | None], passes: dict[int, int],
                scale: dict[int, float] | None = None
                ) -> dict[tuple[str, str], list[cal.EpisodeRecord]]:
    """Every depth level for one model over twenty tasks, `passes[level]` of each task's five
    attempts passing; attempt `a` at level `l` took `seconds[a] * scale[l]` (or recorded
    none)."""
    cells: dict[tuple[str, str], list[cal.EpisodeRecord]] = {}
    for level in levels("depth"):
        arm = f"depth:d{level}"
        rows = []
        for task in range(20):
            for attempt in range(N):
                base = seconds[attempt]
                taken = None if base is None else base * (scale or {}).get(level, 1.0)
                rows.append(record(
                    task=task, attempt=attempt, arm=arm, model=model,
                    strict=attempt < passes[level], label=None,
                    episode_seconds=taken,
                    model_seconds=None if taken is None else 0.75 * taken,
                    harness_seconds=None if taken is None else 0.25 * taken,
                    setup_seconds=None if taken is None else 6.0,
                ))
        cells[(arm, model)] = rows
    return cells


PASSES_A = {1: 5, 2: 4, 3: 2, 5: 1, 8: 0}
PASSES_B = {1: 5, 2: 1, 3: 3, 5: 1, 8: 0}


def without_time(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value for key, value in cell.items() if key not in TIME_KEYS}
            for cell in cells]


def test_k0_6_two_cards_that_differ_only_in_time_compare_equal() -> None:
    """The same records with very different times, one timed and one not, under provenances
    that differ only in concurrency: every pair, ordering and verdict is the same, and each
    shares a page with a third card and agrees with it the same way.  In the slow card the
    levels' times also differ from each other by up to twenty times."""
    fast = cal.build_artifact(depth_cells("a", (1.0, 2.0, 3.0, 4.0, 5.0), PASSES_A),
                              provenance("a", concurrency=4))
    slow = cal.build_artifact(depth_cells("a", (900.0, 5.0, 700.0, 1.0, 800.0), PASSES_A,
                                          {1: 1.0, 2: 20.0, 3: 1.0, 5: 0.1, 8: 3.0}),
                              provenance("a", concurrency=128))
    untimed = cal.build_artifact(depth_cells("a", (None,) * N, PASSES_A), provenance("a"))
    other = cal.build_artifact(depth_cells("b", (3.0,) * N, PASSES_B),
                               provenance("b", concurrency=1))
    assert fast.cells[0]["episode_seconds_median"] != slow.cells[0]["episode_seconds_median"]
    for card in (slow, untimed):
        assert card.pairs == fast.pairs
        assert card.reach_pairs == fast.reach_pairs
        assert card.orderings == fast.orderings
        assert without_time(card.cells) == without_time(fast.cells)
        assert cal.agreement_rows([card, other]) == cal.agreement_rows([fast, other])
        cal.render_combined_document([card, other])


def test_k0_6_the_page_says_time_is_not_compared_across_cards() -> None:
    """Before any card, the page says that time is each card's own, under its serving and
    concurrency, and is not compared with another card's."""
    first = cal.build_artifact(depth_cells("a", (10.0,) * N, PASSES_A),
                               provenance("a", concurrency=4))
    second = cal.build_artifact(depth_cells("b", (30.0,) * N, PASSES_B),
                                provenance("b", concurrency=64))
    page = cal.render_combined_document([first, second])
    preamble = page.partition("\n## a\n")[0]
    lines = [line.lower() for line in preamble.splitlines()]
    assert any(("time" in line or "seconds" in line) and "serving" in line
               and "concurrency" in line for line in lines), preamble


# ---------------------------------------------------------------------------
# concurrency
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("concurrency", [37, None], ids=["recorded", "not_recorded"])
def test_k0_7_the_card_prints_the_concurrency_with_every_time_figure(
    concurrency: int | None,
) -> None:
    """Each section that prints seconds says at what concurrency they were measured, and so
    does the provenance: the number, or *not recorded*."""
    document = cal.render_document(every_arm_card(concurrency))
    parts = {
        "levels": section(document, "## Levels", cal.INSTRUMENT_TABLE_HEADING),
        "instrument": section(document, cal.INSTRUMENT_TABLE_HEADING, "## Cost per episode"),
        "cost": section(document, "## Cost per episode", "## Adjacent levels"),
        "provenance": section(document, "## Provenance", None),
    }
    for name, text in parts.items():
        said = [line for line in text.splitlines()
                if "concurrency" in line.lower() and not line.startswith("|")]
        if concurrency is None:
            assert any(NOT_RECORDED in line for line in said), (name, said)
        else:
            assert any(re.search(r"\b37\b", line) for line in said), (name, said)


@pytest.mark.parametrize("bad", [0, -4, True, 2.5, "8"])
def test_k0_7_a_concurrency_that_is_not_a_count_of_episodes_is_refused(bad: Any) -> None:
    accepted = provenance(concurrency=8)  # the control
    assert accepted.as_dict()["concurrency"] == 8
    assert cal.Provenance(**accepted.as_dict()) == accepted
    with pytest.raises(ValueError):
        provenance(concurrency=bad)


def test_k0_7_a_run_records_its_concurrency_in_the_provenance() -> None:
    """`Provenance.for_run` builds a real run's block; it carries the run's concurrency, and a
    run that declares none carries none."""
    model = {"id": "m", "revision": "m", "endpoint_host": "h"}
    serving = {"m": {"kind": "hosted", "endpoint_host": "h"}}
    declared = cal.Provenance.for_run(models=[model], serving=serving,
                                      rate_read_date="2026-10-03", concurrency=16)
    undeclared = cal.Provenance.for_run(models=[model], serving=serving,
                                        rate_read_date="2026-10-03")
    assert declared.concurrency == 16 and declared.as_dict()["concurrency"] == 16
    assert undeclared.concurrency is None and "concurrency" not in undeclared.as_dict()
    assert dataclasses.replace(declared, concurrency=None) == undeclared
