"""The first request's size counts the tokens the provider read from its cache.

`first_request_prompt_tokens` is the model's own count of what it saw before its first move.  A
provider that caches a shared prefix reports part of that prompt as cached reads, which
verifiers 0.3.1's `Usage` keeps out of `prompt_tokens` and carries in `cached_input_tokens`.  The
model saw both, so the figure is their sum, `Usage.input_tokens`: otherwise the same prompt would
read shorter whenever the cache was warm.  Neither published card's model reported a cached read
on a first call that this figure was read from, and model B's probe traces carry none.

The trace here is the same shape as `tests/test_k0_record.py`'s: a generated task's own prompt,
scored offline by the task, with one model call and a timing block, written to `traces.jsonl` by
the wheel's own writer and read back by `records_from_run`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import verifiers.v1 as vf
from verifiers.v1.cli.output import append_trace

from poisson_tasks import calibration as cal
from poisson_tasks import export
from poisson_tasks.knobs import ArmSpec
from poisson_tasks.tasks import generate
from tests.helpers import seeded_nodes

T = 1_790_000_000.0


def test_k0_2_the_first_request_counts_its_cached_reads(tmp_path: Path) -> None:
    spec = ArmSpec(knob="depth", level=1, control=None, strictness="strict", split="eval",
                   generator_version="0")
    task = export.task_from_bundle(generate(spec, 404))
    nodes = seeded_nodes(task)
    reply = vf.AssistantMessage(content="Done.")
    nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=reply, sampled=True))
    trace = vf.Trace(
        task=vf.TraceTask(type=type(task).__name__, data=task.data, key=task.key,
                          hash=task.hash),
        agent=vf.AgentInfo(config=vf.AgentConfig()), nodes=nodes, ok=True, is_completed=True,
    )
    asyncio.run(task.score(trace, None))
    usage = vf.Usage(prompt_tokens=526, cached_input_tokens=1000, completion_tokens=40)
    trace.calls = [vf.ModelCall(usage=usage, time=vf.TimeSpan(start=T + 7.0, end=T + 9.0))]
    trace.timing = vf.Timing(
        start=T, setup=vf.TimeSpan(start=T, end=T + 6.5),
        agent=vf.AgentSpan(start=T + 6.5, end=T + 10.0, model=vf.TimeSplit(duration=2.0),
                           harness=vf.TimeSplit(duration=1.5)),
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    asyncio.run(append_trace(run_dir, trace, asyncio.Lock()))
    (record,) = cal.records_from_run(run_dir, model="m")
    assert record.first_request_prompt_tokens == 1526
    assert (record.prompt_tokens, record.cached_input_tokens) == (526, 1000)
