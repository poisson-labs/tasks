"""What a run's records say about the block-size knob: the replay check takes it in, frozen as a test.

Taylor's standing ruling for every knob that gains tasks: when a run's records are read, the calls
that reached the tool server are replayed against the engine and a disagreement with the tool
messages is `replay_mismatch`, which scores nothing.  For block size the calls a model can make
that no earlier knob offered are the aliased read copies, served under names the engine does not
know, so the replay must read them through the same display map the server answers them by.

The traces here are real `vf.Trace` objects in verifiers 0.3.1's shape, scored offline by the task
and written by the wheel's own writer (`tests/k3_support.py`), with tool messages that are the tool
server's answers, run in this process.

Shapes decided here
-------------------

**1. The episode reads two copies around the reference calls**: a copy, the first right call, a
second copy, the second right call, then a reply.  Answered by the server, it reads as `passed`;
a planted change to any one of the four tool messages reads as `replay_mismatch`.  So a replay that
read a copy as no tool fails the clean episode, and a check that did not run on block arms passes
the planted ones.

**2. A block record carries no fault verdict**: `gave_up_after_fault` is `None` and left out of the
written line, as on every arm that plans no failure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from poisson_tasks import calibration as cal
from poisson_tasks.engine import apply, init_state
from poisson_tasks.tasks import scenario_for
from tests.k3_support import (
    GAVE_UP,
    SPEC,
    answers,
    gave_up,
    records_of,
    run_dir_of,
    trace_of,
    written,
)
from tests.k5_support import CARD_SEEDS, block, copies, pair_of, read_of

SEED = CARD_SEEDS[5]


def ok_args(read: str) -> dict[str, str]:
    scenario = scenario_for(0, "eval")
    state = init_state(scenario, 1)
    item_param, page_param = SPEC.parameter_names["item"], SPEC.parameter_names["page"]
    for item in scenario.visible_items:
        for page in sorted(SPEC.page_keys):
            args = {item_param: item, page_param: page}
            if apply(state, (read, args))[1].split()[1] == "ok":
                return args
    raise AssertionError(f"{read} answers ok for no item")


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


def test_the_replay_check_covers_block_and_reads_the_aliased_copies(tmp_path: Path) -> None:
    bundle = block(64, SEED)
    first, second = copies(bundle)[0], copies(bundle)[-1]
    asked: list[tuple[str, Any]] = []
    for name in (first, second):
        pair = pair_of(name)
        assert pair is not None, name
        asked.append((name, ok_args(read_of(pair[1]))))
    (right1, args1), (right2, args2) = bundle.reference_calls
    calls = [asked[0], (str(right1), dict(args1)), asked[1], (str(right2), dict(args2))]
    sent = answers(bundle, calls)
    assert [line.split()[1] for line in sent] == ["ok"] * 4
    (record,) = records_of(tmp_path, trace_of(bundle, calls, sent))
    assert (record.label, record.strict, record.leaky) == ("passed", True, True)
    assert gave_up(record) is None and GAVE_UP not in written(record)

    for index in range(len(calls)):
        run_dir = run_dir_of(tmp_path, trace_of(bundle, calls, sent))
        planted(run_dir, index)
        (changed,) = cal.records_from_run(run_dir, model="m")
        assert (changed.label, changed.strict, changed.leaky) == ("replay_mismatch", False, False)
