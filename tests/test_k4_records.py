"""What a run's records say about the history knob: the replay check takes it in, frozen as a test.

The standing decision for every knob that gains tasks: when a run's records are read, the
calls that reached the tool server are replayed against the engine and a disagreement with the
tool messages is `replay_mismatch`, which scores nothing.  For history the sampled calls start
at `seq_start`, after the seeded pairs, which the trace holds as prompt-supplied messages.

The traces here are real `vf.Trace` objects in verifiers 0.3.1's shape, with the task's own
seeded prompt in front, scored offline by the task and written by the wheel's own writer
(`tests/k3_support.py`), with tool messages that are the tool server's answers, run in this
process.

Shapes decided here
-------------------

**1. The seeded pairs are not replayed.**  The replay starts the engine at `seq_start`, as the
server does, and walks the sampled calls alone; a check that walked every tool message would
meet the seeded `seq`s 1 to N at state `N + 1` and call every history episode a mismatch.  So
the reference episode, answered by the server, reads as `passed`, and a planted change to any
message the server sent reads as `replay_mismatch`.

**2. A history record carries no fault verdict**: `gave_up_after_fault` is `None` and left out of
the written line, as on every arm that plans no failure.
"""

from __future__ import annotations

import json
from pathlib import Path

from poisson_tasks import calibration as cal
from tests.k3_support import (
    CARD_SEEDS,
    GAVE_UP,
    answers,
    gave_up,
    records_of,
    run_dir_of,
    trace_of,
    written,
)
from tests.k4_support import history, seeded

SEED = CARD_SEEDS[3]
LEVEL = 600


def planted(run_dir: Path, index: int) -> None:
    """The `index`-th tool message of the one episode, its last character changed."""
    path = run_dir / cal.TRACES_FILE
    (line,) = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(line)
    seen = 0
    for trace in row["traces"]:
        for node in trace["nodes"]:
            message = node.get("message") or {}
            if message.get("role") == "tool":
                if seen == index:
                    text = message["content"]
                    message["content"] = text[:-1] + ("0" if text[-1] != "0" else "1")
                seen += 1
    assert seen > index
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_the_replay_check_covers_history_and_leaves_the_seeded_pairs_alone(tmp_path: Path) -> None:
    bundle = history(LEVEL, SEED)
    calls = list(bundle.reference_calls)
    sent = answers(bundle, calls)
    assert [int(line.split()[0]) for line in sent] == [bundle.seq_start, bundle.seq_start + 1]
    (record,) = records_of(tmp_path, trace_of(bundle, calls, sent))
    assert (record.label, record.strict, record.leaky) == ("passed", True, True)
    assert gave_up(record) is None and GAVE_UP not in written(record)

    pairs = len(seeded(bundle))
    for index in range(len(calls)):
        run_dir = run_dir_of(tmp_path, trace_of(bundle, calls, sent))
        planted(run_dir, pairs + index)
        (changed,) = cal.records_from_run(run_dir, model="m")
        assert (changed.label, changed.strict, changed.leaky) == ("replay_mismatch", False, False)
