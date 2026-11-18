"""C2.3: what every episode record of a version 2 run carries.

The design: every episode record carries the arm id, seed, attempt, strict, leaky, label, turns,
sampled calls, prompt, cached-input and completion tokens, reasoning tokens (`null` where the
provider reports none), length stops, the `model` each answer carried, seconds, the dial columns
(gave up after a fault; acted on bad data; read again after a bad answer; retried after a landed
timeout; duplicate write) and `first_entry_code` on spread.  The reading and the filing read only
the fields this file pins.

The keys are the written line's (`tests/c2_support.RECORD_FIELDS` and `DIAL_FIELDS`): a line of
`records/episodes.jsonl` is one JSON object, read here as JSON and not through the package.

Readings made here:
* `length_stops` is a count: how many of the episode's model calls ended at the completion cap.
* `answer_models` is a list: the distinct `model` values the episode's answers carried, in the
  order first seen.
* A dial column is `true` or `false` on a record whose arm plans what the column counts, and
  `null` or left out of the line everywhere else (a dial's level 0, a control arm that plans no
  failure, another dial's arm), as the columns have been written since they shipped.
* `first_entry_code` is one of `right`, `joined_marker`, `filler`, `other` and `none_sent`, on
  every spread record, and `null` or left out on every other.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.c2_support import (
    ARMS,
    DIAL_FIELDS,
    FIRST_ENTRY_CODES,
    HAIKU,
    LUNA,
    RECORD_FIELDS,
    by_arm,
    clean_run,
    knob_of,
    lines,
    needs_uv,
)

pytestmark = needs_uv


@pytest.fixture(scope="module")
def luna(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return clean_run(LUNA, tmp_path_factory)


@pytest.fixture(scope="module")
def haiku(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return clean_run(HAIKU, tmp_path_factory)


def rows_of(found: dict[str, Any]) -> list[dict[str, Any]]:
    assert found["code"] == 0, found["out"] + found["err"]
    return lines(found["folder"])


def test_there_is_one_line_per_planned_episode_arm_by_arm_in_run_order(
    luna: dict[str, Any],
) -> None:
    rows = rows_of(luna)
    design = luna["design"]
    per_arm = len(design.seeds) * design.attempts
    assert len(rows) == len(ARMS) * per_arm
    assert [row["arm_id"] for row in rows[::per_arm]] == list(ARMS)
    for arm, cell in by_arm(rows).items():
        assert sorted((row["seed"], row["attempt"]) for row in cell) == sorted(
            (seed, attempt) for seed in design.seeds for attempt in range(design.attempts)
        ), arm


@pytest.mark.parametrize("model", [LUNA, HAIKU])
def test_every_line_carries_every_pinned_field(
    model: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    rows = rows_of(clean_run(model, tmp_path_factory))
    assert rows
    for row in rows:
        missing = [name for name in RECORD_FIELDS if name not in row]
        assert not missing, (row["arm_id"], missing)
        assert row["model"] == model


def test_the_scoring_fields_are_what_the_cards_have_always_recorded(luna: dict[str, Any]) -> None:
    for row in rows_of(luna):
        assert isinstance(row["strict"], bool) and isinstance(row["leaky"], bool)
        assert row["strict"] == (row["label"] == "passed")
        assert isinstance(row["attempt"], int) and isinstance(row["seed"], int)
        # the fake makes one tool call a turn and then replies, on a task it fails too
        assert row["turns"] == row["sampled_calls"] + 1 >= 2, row["arm_id"]
        for name in ("prompt_tokens", "cached_input_tokens", "completion_tokens"):
            assert isinstance(row[name], int) and row[name] >= 0, name
        assert row["prompt_tokens"] > 0 and row["completion_tokens"] > 0
        assert isinstance(row["episode_seconds"], (int, float)) and row["episode_seconds"] > 0


def test_a_passing_and_a_failing_arm_are_both_in_the_records(luna: dict[str, Any]) -> None:
    """The run's fake fails `spread:p4` at the card's seeds and nothing else."""
    cells = by_arm(rows_of(luna))
    assert {row["label"] for row in cells["spread:p4"]} == {"wrong_state"}
    assert {row["label"] for row in cells["spread:p1"]} == {"passed"}
    assert {row["label"] for row in cells["landed:l1"]} == {"passed"}


def test_reasoning_tokens_are_a_count_where_the_provider_reports_one(
    luna: dict[str, Any],
) -> None:
    """The OpenAI-like fake reports 20 reasoning tokens on every completion."""
    for row in rows_of(luna):
        assert row["reasoning_tokens"] == 20 * row["turns"], row["arm_id"]
        assert row["reasoning_tokens"] <= row["completion_tokens"]


def test_reasoning_tokens_are_null_where_the_provider_reports_none(
    haiku: dict[str, Any],
) -> None:
    """The Claude-like fake sends no `completion_tokens_details`, as Anthropic's
    OpenAI-compatible endpoint sends none: the count is not known, and is not written as 0."""
    rows = rows_of(haiku)
    assert {row["reasoning_tokens"] for row in rows} == {None}
    assert all(row["completion_tokens"] > 0 for row in rows)


def test_a_clean_run_has_no_length_stop_and_one_answering_model(luna: dict[str, Any]) -> None:
    for row in rows_of(luna):
        assert row["length_stops"] == 0, row["arm_id"]
        assert row["answer_models"] == [LUNA], row["arm_id"]


def test_a_dial_column_says_nothing_on_another_dials_records(luna: dict[str, Any]) -> None:
    for row in rows_of(luna):
        knob = knob_of(row["arm_id"])
        for name, knobs in DIAL_FIELDS.items():
            if knob not in knobs:
                assert row.get(name) is None, (row["arm_id"], name)


def test_a_dial_column_is_a_verdict_where_the_arm_plans_it_and_nothing_where_not(
    luna: dict[str, Any],
) -> None:
    cells = by_arm(rows_of(luna))
    told = {
        "gave_up_after_fault": ("faults:f4", "timeouts:o4", "ratelimits:r4"),
        "acted_on_bad_data": ("baddata:b3", "lagged:g1"),
        "read_again_after_bad": ("baddata:b3", "lagged:g1"),
        "retried_after_landed": ("landed:l1",),
        "duplicate_write": ("landed:l0", "landed:l1", "lagged:g0", "lagged:g1"),
    }
    for name, arms in told.items():
        for arm in arms:
            assert {type(row[name]) for row in cells[arm]} == {bool}, (arm, name)
    untold = {
        "gave_up_after_fault": ("faults:f0", "faults:f0+len(f4)", "timeouts:o0", "ratelimits:r0"),
        "acted_on_bad_data": ("baddata:b0", "lagged:g0"),
        "read_again_after_bad": ("baddata:b0", "lagged:g0"),
        "retried_after_landed": ("landed:l0",),
    }
    for name, arms in untold.items():
        for arm in arms:
            assert {row.get(name) for row in cells[arm]} == {None}, (arm, name)


def test_the_reference_play_reads_as_it_should_in_each_dial_column(luna: dict[str, Any]) -> None:
    """The fake plays each task's reference: it retries after a planned failure, does not act on
    a bad answer, reads again after one, never repeats a landed write and writes nothing twice."""
    cells = by_arm(rows_of(luna))
    for arm in ("faults:f4", "timeouts:o4", "ratelimits:r4"):
        assert {row["gave_up_after_fault"] for row in cells[arm]} == {False}, arm
    for arm in ("baddata:b3", "lagged:g1"):
        assert {row["acted_on_bad_data"] for row in cells[arm]} == {False}, arm
        assert {row["read_again_after_bad"] for row in cells[arm]} == {True}, arm
    assert {row["retried_after_landed"] for row in cells["landed:l1"]} == {False}
    for arm in ("landed:l0", "landed:l1", "lagged:g0", "lagged:g1"):
        assert {row["duplicate_write"] for row in cells[arm]} == {False}, arm


def test_first_entry_code_is_on_every_spread_record_from_the_closed_list(
    luna: dict[str, Any],
) -> None:
    cells = by_arm(rows_of(luna))
    for arm in ("spread:p1", "spread:p2", "spread:p4"):
        assert {row["first_entry_code"] for row in cells[arm]} <= set(FIRST_ENTRY_CODES), arm
    # the reference joins the parts and sends the code; the failed tasks stop one call short of
    # the goal, after the entry code went in right
    assert {row["first_entry_code"] for row in cells["spread:p1"]} == {"right"}
    assert {row["first_entry_code"] for row in cells["spread:p2"]} == {"right"}


def test_a_line_reads_back_through_the_package_as_the_record_it_was(luna: dict[str, Any]) -> None:
    """The reading takes the records through the package's own reader: every line reads, and
    writes back as the bytes it was."""
    from poisson_tasks import calibration as cal

    path = luna["folder"] / "records" / "episodes.jsonl"
    text = path.read_text(encoding="utf-8")
    records = cal.read_records(path)
    assert len(records) == len(text.splitlines())
    assert "".join(cal.EpisodeRecord.to_json(row) + "\n" for row in records) == text


def test_a_generator_0_record_still_writes_back_as_the_line_it_was() -> None:
    """A guard for the archive: the new fields are left out of a line that never had them."""
    from poisson_tasks import calibration as cal
    from tests.c2_support import REPO

    found = sorted((REPO / "calibration").rglob("episodes.jsonl"))
    assert found, "the checkout keeps no card's records"
    for path in found:
        first = path.read_text(encoding="utf-8").splitlines()[:50]
        for line in first:
            assert cal.EpisodeRecord.to_json(cal.EpisodeRecord.from_json(line)) == line
