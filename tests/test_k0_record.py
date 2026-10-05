"""Cost and time on every card: what an episode's record gains, and where it comes from.

The invariants are K0.1 and K0.2 of the knobs plan.  A record gains five optional fields:

- `episode_seconds`, the agent phase's `end - start`: the episode as the model and tools
  experienced it;
- `model_seconds`, the agent phase's `model.duration`;
- `harness_seconds`, the agent phase's `harness.duration`: tool calls and the harness between
  them;
- `setup_seconds`, the setup phase's `end - start`: the tool server's start;
- `first_request_prompt_tokens`, from the first model call's own `usage`.

Each is `None` when it was not recorded, and is never written as zero.  Both published cards were
recorded before these fields existed, so every line of their `episodes.jsonl` must read and
write back unchanged.

The traces here are real `vf.Trace` objects in verifiers 0.3.1's shape: a generated task's own
prompt, scored offline by the task itself, given a `timing` block and model calls, and written
to `traces.jsonl` by the wheel's own writer, so `records_from_run` reads them the way it reads a
run.

Shapes decided here
-------------------

**1. "No model call" is an empty `calls` list.**  The fixtures keep the trace's sampled
messages consistent with it, so a build that counts model calls by `num_turns` reads the same.

**2. When the agent phase never ended, none of its three figures was recorded.**  Model and
harness seconds are parts of the agent phase; 0.3.1 splits them only once the phase has ended
(`Trace.split_agent_time`), so with `end == 0.0` they hold the `0.0` default, and model calls may
still be present.

**3. A zero in an episode that made model calls is a measurement and stays zero.**  The rule
removes defaults, not measurements: 0.3.1's split gives the harness exactly `0.0` when the model
time reaches the whole phase.

**4. The first request is the first entry of `calls`.**  When that call carries no `usage`, the
figure was not recorded; a later call's usage does not stand in for it.

**5. Refusing a negative value is pinned by the refusal alone.**  Each refusal test has a
control that differs only in the field under test and is accepted, and none matches words in the
message.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import verifiers.v1 as vf
from verifiers.v1.cli.output import append_trace

from poisson_tasks import calibration as cal
from poisson_tasks import export
from poisson_tasks.knobs import ArmSpec
from poisson_tasks.tasks import generate
from tests.helpers import seeded_nodes

CARDS = Path(__file__).resolve().parent.parent / "calibration"
EPISODE_FILES = sorted(CARDS.glob("*/episodes.jsonl"))
FIELDS = ("episode_seconds", "model_seconds", "harness_seconds", "setup_seconds",
          "first_request_prompt_tokens")
SECONDS = FIELDS[:4]

# A realistic wall clock: 0.3.1's timestamps are `time.time()`.  Binary fractions, so the
# differences below are exact.
T = 1_790_000_000.0


def _record(**over: Any) -> cal.EpisodeRecord:
    base: dict[str, Any] = dict(
        task_id="t", arm_id="depth:d3", model="m", seed=1, attempt=0, strict=True, leaky=True,
        label="passed", turns=4, sampled_calls=3, prompt_tokens=3000, cached_input_tokens=0,
        completion_tokens=60, reasoning_tokens=0,
    )
    base.update(over)
    return cal.EpisodeRecord(**base)


# ---------------------------------------------------------------------------
# the record (K0.1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", EPISODE_FILES, ids=[p.parent.name for p in EPISODE_FILES])
def test_k0_1_every_published_record_reads_and_writes_back_byte_for_byte(
    path: Path, tmp_path: Path
) -> None:
    """Every line of both published `episodes.jsonl` files, read and written again, is the line
    it was; so is the whole file through `read_records` and `write_records`.  Neither card
    recorded time, so every record read from them carries none."""
    raw = path.read_bytes()
    lines = raw.decode("utf-8").split("\n")
    assert lines[-1] == "" and all(lines[:-1]), "one record per line, newline-terminated"
    for number, line in enumerate(lines[:-1], start=1):
        record = cal.EpisodeRecord.from_json(line)
        assert cal.EpisodeRecord.to_json(record) == line, f"line {number}"
        assert all(getattr(record, name) is None for name in FIELDS), f"line {number}"
    written = cal.write_records(cal.read_records(path), tmp_path / "episodes.jsonl")
    assert written.read_bytes() == raw


def test_k0_1_a_record_with_time_writes_what_it_recorded_and_reads_it_back(
    tmp_path: Path,
) -> None:
    """A recorded figure is written under its own name and read back to the same record; a
    figure that was not recorded is left out of the line rather than written as `null`, while
    `cost` still writes `null`."""
    full = _record(episode_seconds=18.25, model_seconds=16.0, harness_seconds=2.25,
                   setup_seconds=6.5, first_request_prompt_tokens=1526)
    partial = _record(attempt=1, setup_seconds=9.5)
    line = json.loads(cal.EpisodeRecord.to_json(full))
    assert {name: line[name] for name in FIELDS} == {
        "episode_seconds": 18.25, "model_seconds": 16.0, "harness_seconds": 2.25,
        "setup_seconds": 6.5, "first_request_prompt_tokens": 1526,
    }
    assert line["cost"] is None
    sparse = json.loads(cal.EpisodeRecord.to_json(partial))
    assert sparse["setup_seconds"] == 9.5
    assert [name for name in FIELDS if name in sparse] == ["setup_seconds"]
    assert "cost" in sparse and sparse["cost"] is None
    path = cal.write_records([full, partial], tmp_path / "episodes.jsonl")
    assert cal.read_records(path) == [full, partial]


@pytest.mark.parametrize("name", FIELDS)
def test_k0_1_each_new_field_refuses_a_negative_value(name: str) -> None:
    negative: float | int = -1 if name == "first_request_prompt_tokens" else -0.5
    _record(**{name: 0})  # the control: the same record at zero is a record
    with pytest.raises(ValueError):
        _record(**{name: negative})


# ---------------------------------------------------------------------------
# from the trace (K0.2)
# ---------------------------------------------------------------------------


def _task() -> Any:
    spec = ArmSpec(knob="depth", level=1, control=None, strictness="strict", split="eval",
                   generator_version="0")
    return export.task_from_bundle(generate(spec, 404))


def _call(usage: vf.Usage | None, start: float, end: float) -> vf.ModelCall:
    return vf.ModelCall(usage=usage, time=vf.TimeSpan(start=start, end=end))


def _timing(
    *, setup: tuple[float, float], agent: tuple[float, float], model: float, harness: float
) -> vf.Timing:
    # The trace's own `start` and the boot phase come before setup, as in 0.3.1.
    return vf.Timing(
        start=setup[0] - 0.25,
        boot=vf.TimeSpan(start=setup[0] - 0.25, end=setup[0]),
        setup=vf.TimeSpan(start=setup[0], end=setup[1]),
        agent=vf.AgentSpan(start=agent[0], end=agent[1], model=vf.TimeSplit(duration=model),
                           harness=vf.TimeSplit(duration=harness)),
    )


def _trace(task: Any, calls: Sequence[vf.ModelCall], timing: vf.Timing | None) -> Any:
    """The task's own prompt and one sampled reply per model call, scored offline by the task;
    then the calls and the timing block, as 0.3.1 records them."""
    nodes = seeded_nodes(task)
    for _ in calls:
        reply = vf.AssistantMessage(content="Done.")
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=reply, sampled=True))
    trace = vf.Trace(
        task=vf.TraceTask(type=type(task).__name__, data=task.data, key=task.key,
                          hash=task.hash),
        agent=vf.AgentInfo(config=vf.AgentConfig()), nodes=nodes, ok=True, is_completed=True,
    )
    asyncio.run(task.score(trace, None))
    trace.calls = list(calls)
    if timing is not None:
        trace.timing = timing
    return trace


def _records(tmp_path: Path, *traces: Any) -> list[cal.EpisodeRecord]:
    """Each trace as one episode in a run directory, written by the wheel's own writer, and
    read back the way a finished run is."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    lock = asyncio.Lock()
    for trace in traces:
        asyncio.run(append_trace(run_dir, trace, lock))
    return cal.records_from_run(run_dir, model="m")


def _figures(record: cal.EpisodeRecord) -> dict[str, Any]:
    return {name: getattr(record, name) for name in FIELDS}


def test_k0_2_the_fields_come_from_the_traces_timing_and_first_call(tmp_path: Path) -> None:
    """Every figure differs from every other, so a field read from the wrong place is caught.
    The model calls' own spans add to 15 s while the agent phase's `model.duration` says 16 s:
    model seconds are the phase's own figure, not a sum over calls.  The second call's prompt is
    larger than the first's, so the first request is neither the last nor the total."""
    task = _task()
    trace = _trace(
        task,
        [_call(vf.Usage(prompt_tokens=1526, completion_tokens=40), T + 7.0, T + 15.0),
         _call(vf.Usage(prompt_tokens=1700, completion_tokens=30), T + 16.0, T + 23.0)],
        _timing(setup=(T, T + 6.5), agent=(T + 6.5, T + 24.75), model=16.0, harness=2.25),
    )
    (record,) = _records(tmp_path, trace)
    assert _figures(record) == {
        "episode_seconds": pytest.approx(18.25), "model_seconds": pytest.approx(16.0),
        "harness_seconds": pytest.approx(2.25), "setup_seconds": pytest.approx(6.5),
        "first_request_prompt_tokens": 1526,
    }
    assert record.turns == 2 and record.prompt_tokens == 1526 + 1700


@pytest.mark.parametrize("phase", ["agent", "setup"])
def test_k0_2_a_phase_whose_end_is_zero_was_not_recorded(phase: str, tmp_path: Path) -> None:
    """0.3.1 defaults every timing field to `0.0`.  A phase that never ended gives `None`
    for each of its figures, and the other phase's figures are unaffected."""
    task = _task()
    calls = [_call(vf.Usage(prompt_tokens=1526, completion_tokens=40), T + 7.0, T + 15.0)]
    if phase == "agent":
        timing = _timing(setup=(T, T + 6.5), agent=(T + 6.5, 0.0), model=0.0, harness=0.0)
        expected = {"episode_seconds": None, "model_seconds": None, "harness_seconds": None,
                    "setup_seconds": pytest.approx(6.5), "first_request_prompt_tokens": 1526}
    else:
        timing = _timing(setup=(T, 0.0), agent=(T + 6.5, T + 24.75), model=16.0, harness=2.25)
        expected = {"episode_seconds": pytest.approx(18.25), "model_seconds": pytest.approx(16.0),
                    "harness_seconds": pytest.approx(2.25), "setup_seconds": None,
                    "first_request_prompt_tokens": 1526}
    (record,) = _records(tmp_path, _trace(task, calls, timing))
    assert _figures(record) == expected


def test_k0_2_a_zero_in_an_episode_with_no_model_call_was_not_recorded(tmp_path: Path) -> None:
    """Two episodes that made no model call.  One carries 0.3.1's untouched defaults; the other
    an agent phase that ended the instant it started, so its duration and both its splits are
    zero.  Every zero is `None`; the second episode's setup, which took time, is kept."""
    task = _task()
    untouched = _trace(task, [], None)
    instant = _trace(task, [], _timing(setup=(T, T + 6.5), agent=(T + 6.5, T + 6.5), model=0.0,
                                       harness=0.0))
    first, second = _records(tmp_path, untouched, instant)
    assert _figures(first) == dict.fromkeys(FIELDS)
    assert _figures(second) == {**dict.fromkeys(FIELDS), "setup_seconds": pytest.approx(6.5)}


def test_k0_2_a_measured_zero_in_an_episode_with_model_calls_stays_zero(tmp_path: Path) -> None:
    """The model's time reached the whole agent phase, so 0.3.1's split leaves the harness
    exactly `0.0`.  The episode made a model call, so that zero was measured and is printed
    as zero, not as missing."""
    task = _task()
    trace = _trace(
        task, [_call(vf.Usage(prompt_tokens=1526, completion_tokens=40), T + 6.5, T + 9.0)],
        _timing(setup=(T, T + 6.5), agent=(T + 6.5, T + 9.0), model=2.5, harness=0.0),
    )
    (record,) = _records(tmp_path, trace)
    assert record.harness_seconds == 0.0 and record.harness_seconds is not None
    assert record.model_seconds == pytest.approx(2.5)


def test_k0_2_a_first_call_without_usage_records_no_first_request(tmp_path: Path) -> None:
    """The first request's size is read from the first call alone.  Here that call carries no
    usage and the second does: the figure is `None`, never the second call's prompt."""
    task = _task()
    trace = _trace(
        task,
        [_call(None, T + 7.0, T + 15.0),
         _call(vf.Usage(prompt_tokens=1700, completion_tokens=30), T + 16.0, T + 23.0)],
        _timing(setup=(T, T + 6.5), agent=(T + 6.5, T + 24.75), model=15.0, harness=3.25),
    )
    (record,) = _records(tmp_path, trace)
    assert record.first_request_prompt_tokens is None
    assert record.episode_seconds == pytest.approx(18.25)
