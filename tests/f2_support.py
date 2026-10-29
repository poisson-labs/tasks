"""What the 0.3.0 faults tests share: the three new knobs, the words each one's answers and
sentences carry, the names the build adds, and an own-tools episode written as a run's trace.

The test files are `tests/test_f2_*.py`; each says in its own docstring what it pins and what it
decided.  Nothing here asserts anything.

Every name the build adds is read here by name, through `vars()` or `getattr` at call time and
never imported, so each test file collects on a tree that lacks them and each test fails there
because a name is missing or a value is wrong.  The built-in helpers are `tests/k3_support.py`'s
and the own-tools ones `tests/o2_support.py`'s, reused as they are.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import verifiers.v1 as vf

from poisson_tasks import arms as arms_module
from poisson_tasks import calibration as cal
from poisson_tasks import surface
from poisson_tasks.arms import arm_from_id
from poisson_tasks.engine import EngineSpec
from tests.helpers import seeded_nodes
from tests.k3_support import run, run_dir_of
from tests.o2_support import generator, simulator

SPEC = EngineSpec.load()
LEVELS = (0, 1, 2, 4)
OWN_SEEDS = (404, 55, 2121)
NEW_KNOBS = ("timeouts", "ratelimits", "landed")


@dataclass(frozen=True)
class Kind:
    """One of the two kinds the built-in tasks carry: the knob, the letter its arm id writes its
    level with, the status word its line carries, the line's payload, the system prompt's
    sentence, and on own tools the error code, the OpenAPI status and the message's tail."""

    knob: str
    letter: str
    word: str
    payload: str
    sentence: str
    status: int
    tail: str

    def arm(self, level: int) -> str:
        return f"{self.knob}:{self.letter}{level}"

    @property
    def control(self) -> str:
        return f"{self.knob}:{self.letter}0+len({self.letter}4)"


# The spec's words, word for word with their backticks (section 1.2).
TIMEOUTS = Kind(
    knob="timeouts",
    letter="o",
    word="timeout",
    payload=str(SPEC.layout["error_payload"]),
    sentence="A call can come back `timeout`: whether it went through is not known.",
    status=504,
    tail="timed out; whether it went through is not known",
)
RATELIMITS = Kind(
    knob="ratelimits",
    letter="r",
    word="rate_limited",
    payload="retry-after=1s".ljust(int(SPEC.layout["payload_width"]), "0"),
    sentence=(
        "A call can come back `rate_limited` with a retry-after: nothing changed, and the same "
        "call can be made again after that long."
    ),
    status=429,
    tail="is rate limited; retry after 1 second",
)
KINDS = {kind.knob: kind for kind in (TIMEOUTS, RATELIMITS)}

# The own-tools system prompt's fault clause: today's, and each new knob's (section 1.2).
OWN_CLAUSE = "A call may answer that the tool is unavailable; make the same call again."
OWN_CLAUSES = {
    "timeouts": "A call may time out; whether it went through is then not known.",
    "landed": "A call may time out; whether it went through is then not known.",
    "ratelimits": (
        "A call may answer that the tool is rate limited, with how long to wait; make the same "
        "call again after that."
    ),
}

# The reasons `arms.EXPERIMENTAL_KNOBS` gives (section 6).
NOT_MEASURED = "no model has been measured on it yet"
DID_NOT_BITE = "it did not make tasks harder for either calibrated model"
EXPERIMENTAL_REASONS = {
    "distractor": DID_NOT_BITE,
    "timeouts": NOT_MEASURED,
    "ratelimits": NOT_MEASURED,
    "landed": NOT_MEASURED,
}

# `init`'s and `doctor`'s note on a set with no check read (section 4.3).
NO_CHECK_READ = (
    "A landed timeout can only be told from one that went nowhere by reading the record back, "
    "so landed needs a read tool that takes one of the target write's arguments. This set has "
    "none."
)

# The names the build adds, read by name.
EXPERIMENTAL_KNOBS = "EXPERIMENTAL_KNOBS"
FAULT_KIND = "fault_kind"
WRITES = "writes"
RETRIED = "retried_after_landed"
DUPLICATE = "duplicate_write"


def experimental() -> dict[str, str]:
    """`arms.EXPERIMENTAL_KNOBS`, as a plain mapping."""
    return dict(vars(arms_module)[EXPERIMENTAL_KNOBS])


def fault_kind(arm_id: str) -> Any:
    """`surface.fault_kind(arm_id)`."""
    return vars(surface)[FAULT_KIND](arm_id)


def writes(state: Any) -> tuple[Any, ...]:
    """The simulator's `State.writes`."""
    return tuple(vars(state)[WRITES])


def field(record: Any, name: str) -> Any:
    """A record's field by name."""
    return vars(record)[name]


# --------------------------------------------------------------------------
# the built-in tasks
# --------------------------------------------------------------------------


def status(observation: str) -> str:
    fields = observation.split()
    return fields[1] if len(fields) > 1 and fields[0].isdigit() else ""


def planned_line(seq: int, kind: Kind) -> str:
    """The line a planned answer of `kind` is: the engine's layout at `seq` (section 1.2)."""
    layout = SPEC.layout
    return str(layout["separator"]).join(
        (
            str(seq).rjust(int(layout["seq_width"]), str(layout["seq_fill"])),
            kind.word.ljust(int(layout["status_width"]), str(layout["status_fill"])),
            kind.payload,
        )
    )


# --------------------------------------------------------------------------
# own tools
# --------------------------------------------------------------------------


@lru_cache(maxsize=64)
def own_arm(knob: str, level: int, strictness: str = "strict") -> Any:
    """An own-tools arm of any knob, the new three included, at the own generator's label."""
    letters = {"timeouts": "o", "ratelimits": "r", "landed": "l", "faults": "f",
               "similarity": "s", "history": "t", "block": "k", "arguments": "a",
               "spread": "p", "depth": "d", "shape": "w"}
    return arm_from_id(
        f"{knob}:{letters[knob]}{level}", strictness=strictness, split="eval",
        generator_version=generator().GENERATOR_VERSION,
    )


def own_made(toolset: Any, knob: str, level: int, seed: int, **kwargs: Any) -> Any:
    flows = kwargs.pop("flows", ())
    return generator().generate(toolset, own_arm(knob, level, **kwargs), seed, flows=flows)


def stepped(bundle: Any, calls: Sequence[tuple[str, Any]]) -> tuple[Any, list[Any]]:
    """The simulator's store after `calls` and its answer to each, from the task's start."""
    sim = simulator()
    state = sim.start(bundle)
    out = []
    for call in calls:
        state, answer = sim.step(bundle, state, call)
        out.append(answer)
    return state, out


def loaded(answer: Any) -> Any:
    """An answer's text read as JSON, or the text itself where it is not JSON (an MCP error)."""
    try:
        return json.loads(answer.text)
    except ValueError:
        return answer.text


def own_trace_of(
    bundle: Any, calls: Sequence[tuple[str, Any]], contents: Sequence[str], *, reply: bool = True
) -> Any:
    """`tests/k3_support.py`'s `trace_of` for an own-tools task: the own export's task, one sampled
    assistant message per call with its tool message holding `contents[i]`, then a reply, scored
    offline by the task itself."""
    from poisson_tasks.own import export as own_export

    task = own_export.task_from_bundle(bundle)
    nodes = seeded_nodes(task)
    for index, ((name, args), content) in enumerate(zip(calls, contents, strict=True)):
        arguments = args if isinstance(args, str) else json.dumps(args)
        message = vf.AssistantMessage(
            content=None,
            tool_calls=[vf.ToolCall(id=f"call_f2_{index}", name=name, arguments=arguments)],
        )
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=message, sampled=True))
        answer = vf.ToolMessage(tool_call_id=f"call_f2_{index}", content=content)
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=answer, sampled=False))
    if reply:
        done = vf.AssistantMessage(content="Done.")
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=done, sampled=True))
    trace = vf.Trace(
        task=vf.TraceTask(type=type(task).__name__, data=task.data, key=task.key, hash=task.hash),
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        nodes=nodes,
        ok=True,
        is_completed=True,
    )
    run(task.score(trace, None))
    return trace


def own_contents(bundle: Any, calls: Sequence[tuple[str, Any]]) -> list[str]:
    """What each call's tool message holds: the simulator's answer for a call that reaches the
    server, in one store for the episode, and the harness's own refusal otherwise."""
    sim = simulator()
    block = {str(tool["name"]): tool for tool in bundle.tools}
    state = sim.start(bundle)
    out: list[str] = []
    for name, args in calls:
        if sim.reaches_the_server(name, args, block):
            state, answer = sim.step(bundle, state, (name, args))
            out.append(answer.text)
        else:
            out.append("error: the harness answered this call itself")
    return out


def own_record(tmp_path: Path, bundle: Any, calls: Sequence[tuple[str, Any]]) -> Any:
    """One own-tools episode whose tool messages are the simulator's answers, read back as its
    record."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    trace = own_trace_of(bundle, calls, own_contents(bundle, calls))
    (record,) = cal.records_from_run(run_dir_of(tmp_path, trace), model="m")
    return record


def written(record: Any) -> dict[str, Any]:
    loaded_line: dict[str, Any] = json.loads(cal.EpisodeRecord.to_json(record))
    return loaded_line
