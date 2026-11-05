"""The own-tools generator: tasks on a user's own tools, the knobs applied to them.

A task is a pure function of the tool file's bytes (through the set's digest), the arm and the
seed: every draw is a keyed hash of those and of nothing else, no set or dict built from a set is
ever iterated, and the task id is a content hash over every other field.  The version label is
`own-3` (it was `own-1` until 0.3.0 changed the generator and `own-2` until 0.4.0 changed it
again, each with the ruled change to the frozen built-in one); `generator_hash` covers this
module's bytes and every module of the package that
importing the generator, the simulator and the verdict loads (`HASHED_MODULES`), the shared
`surface.py` and `knobs.py` among them, and none of `arms`, so a knob shipping moves no task.
It never changes a built-in task.

What a task is made of, by knob (as decided 2026-10-13):
- the **target** is a write of the set that can be a task's target, drawn per seed on
  similarity, faults, history, block and spread; on arguments the write with the most checkable
  parameters; on depth and shape the end of the declared chain;
- the **request** uses the target's intent, else the first sentence of its description, never a
  tool's name, and states as JSON every argument a value can be drawn for, required or not, so
  the model has nothing to guess (decided 2026-10-19, after the hands-on pass: a
  request that named no record, or no value to change, was answered with a question); free text
  is stated and never checked;
- **similarity** shows the target and six copies named `<name>_<number>` and described
  `... (account <number>)`, the numbers `surface`'s; **faults** plans `surface.fault_plan`'s
  failures; **history** seeds the fewest read pairs that reach T tokens; **block** offers
  `level` of the set's tools, the target among them, each block the next's first tools; every
  other arm offers the whole set in the file's order;
- **arguments** states the required checkable parameters first and then the others in a drawn
  order, `level` of them, and the call must carry exactly those; **spread** names four reads
  with a checkable argument, `level` of them holding a part of a target value in order and the
  rest `none`; **depth** follows the longest declared chain, level d its last d calls; **shape**
  runs the longest keyed chain four times, width 1 in sequence, width 2 as two sequences side by
  side, width 4 all side by side;
- **timeouts** and **ratelimits** (0.3.0) plan `surface.fault_plan`'s answers as faults does,
  each in its own word, and swap the system prompt's fault clause for the kind's; **landed**
  (0.3.0) plans one answer on the target, which the simulator applies as any call and answers
  the timeout, so its reference is the one call and a reply; it is offered only on a set with a
  check read, a read tool with a checkable argument named as one of the target write's, and its
  target is drawn per seed from the writes that have one, the same at both levels, so that a
  model can tell a write that landed from one that went nowhere by reading the record back
  (decided 2026-10-29, Q3 of the faults design).  Since 0.4.0 the check read's answer must also
  be able to show one of the write's arguments, its key among them: a read that answers the
  same before and after the write tells a model nothing (ruled 2026-11-04, Q14);
- **baddata** (0.4.0) carries one argument of the target in a read's answer: the request states
  every other value and says which read and which field hold the carried one, and the write
  waits on that read.  At a level above 0 the read's first answer is wrong and every later one
  right: at 1 it holds another value under another key, at 2 another value under the asked key,
  at 3 the smallest change to the true value.  The target, the argument, the read and every
  value are drawn per seed and never by the level.  A set needs a write with a checkable scalar
  argument that has such a smallest change, and a keyed read whose answer has a field for it
  that is not one of the read's own arguments; level 1 also needs an answer that can name the
  key it was asked, and where a set has such reads the task is drawn from them at every level;
- **lagged** (0.4.0) is a write and a read that checks it: the request says to make the change
  again only if it did not take, and at level 1 the first read after the write answers as if
  it had not landed.  A set needs a read that takes one of the write's arguments, requires no
  argument the write lacks, and whose answer can show another of the write's arguments; the
  write's values are drawn again until the read's answer before the write and after it differ
  on the task made, the same at both levels (ruled 2026-11-04, the stale-data spec).

`OwnBundle.steps` is what the simulator and the verdict read: the calls the task expects, each
with the arguments that identify it, the steps it waits for and the values its answer serves.
`tests/test_o2_*.py` pin all of this.
"""

from __future__ import annotations

import hashlib as _hashlib
import json as _json
import re as _re
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from dataclasses import fields as _fields
from dataclasses import replace as _replace
from importlib import import_module as _import_module
from typing import Any as _Any

from poisson_tasks import knobs as _knobs
from poisson_tasks import surface as _surface
from poisson_tasks.own import can_target as _can_target
from poisson_tasks.own import is_write as _is_write
from poisson_tasks.own import simulator as _sim
from poisson_tasks.own._schema import is_free_text as _is_free_text
from poisson_tasks.own._types import OwnTool as _OwnTool
from poisson_tasks.own._types import OwnToolSet as _OwnToolSet
from poisson_tasks.own.verdict import verify as _verify
from poisson_tasks.tasks import FormatSpec as _FormatSpec
from poisson_tasks.tasks import Turn as _Turn
from poisson_tasks.tokenizer import count_tokens as _count_tokens

__all__ = [
    "GENERATOR_VERSION",
    "KNOBS",
    "HASHED_MODULES",
    "UNAVAILABLE_WITHOUT_FLOWS",
    "LANDED_NEEDS_A_CHECK_READ",
    "BADDATA_NEEDS_A_CARRIER",
    "BADDATA_NEEDS_A_NAMED_KEY",
    "LAGGED_NEEDS_A_SHOWING_READ",
    "Flow",
    "OwnBundle",
    "generator_hash",
    "hash_of",
    "check_flows",
    "knob_levels",
    "pair_tokens",
    "generate",
]

GENERATOR_VERSION = "own-3"
KNOBS = ("similarity", "faults", "history", "block", "arguments", "spread", "depth", "shape",
         "timeouts", "ratelimits", "landed", "baddata", "lagged")
# Every `poisson_tasks` module a fresh interpreter loads for the generator, the simulator and the
# verdict (`tests/test_o2_determinism.py` holds this list to that), in alphabetical order.
HASHED_MODULES: tuple[str, ...] = (
    "poisson_tasks",
    "poisson_tasks.engine",
    "poisson_tasks.knobs",
    "poisson_tasks.own",
    "poisson_tasks.own._readers",
    "poisson_tasks.own._schema",
    "poisson_tasks.own._server",
    "poisson_tasks.own._types",
    "poisson_tasks.own.generator",
    "poisson_tasks.own.simulator",
    "poisson_tasks.own.verdict",
    "poisson_tasks.surface",
    "poisson_tasks.tasks",
    "poisson_tasks.tokenizer",
)
UNAVAILABLE_WITHOUT_FLOWS = (
    "Depth and shape need the model to carry a value from one tool's output into another's "
    "input in a way that makes sense for your domain. Tasks will not guess that."
)
LANDED_NEEDS_A_CHECK_READ = (
    "A landed timeout can only be told from one that went nowhere by reading the record back, "
    "so landed needs a read tool that takes one of the target write's arguments. This set has "
    "none."
)
BADDATA_NEEDS_A_CARRIER = (
    "Bad data needs a read whose answer holds a value a write then takes, so baddata needs a "
    "read tool with a checkable argument and a write with a checkable argument that read's "
    "answer has a field for. This set has none."
)
BADDATA_NEEDS_A_NAMED_KEY = (
    "Level 1 of baddata needs a read whose answer names what it was asked for. This set's "
    "answers do not, so it reaches 0, 2 and 3."
)
LAGGED_NEEDS_A_SHOWING_READ = (
    "A read that lags a write can only be told from a write that failed if a later read shows "
    "the write, so lagged needs a read tool that takes one of the target write's arguments and "
    "whose answer shows another of them. This set has none."
)

(_SIMILARITY, _FAULTS, _HISTORY, _BLOCK, _ARGUMENTS, _SPREAD, _DEPTH, _SHAPE, _TIMEOUTS,
 _RATELIMITS, _LANDED, _BADDATA, _LAGGED) = KNOBS
# The knobs whose level is a plan of answers in front of the store, each in its own word
# (`surface.fault_kind`); the three faults-shaped ones carry the retries in the reference,
# and landed carries none, its one planned call going through.
_PLANNED = (_FAULTS, _TIMEOUTS, _RATELIMITS, _LANDED)
# The system prompt's fault clause: today's on every knob but the two new kinds', each of which
# says what its answer means and no more.
_FAULT_CLAUSE = "A call may answer that the tool is unavailable; make the same call again."
_FAULT_CLAUSES = {
    _TIMEOUTS: "A call may time out; whether it went through is then not known.",
    _LANDED: "A call may time out; whether it went through is then not known.",
    _RATELIMITS: (
        "A call may answer that the tool is rate limited, with how long to wait; make the same "
        "call again after that."
    ),
    # The two stale-data knobs plan no error, so the unavailable clause does not belong on their
    # arms; each names its hazard and not what to do about it, at every level.
    _BADDATA: "A read may answer with a value that is out of date or wrong.",
    _LAGGED: "A read may answer with a record as it was before your last write.",
}
_READ = "read"
_WRITE = "write"
_EVAL = "eval"
_HASH_DOMAIN = b"poisson-tasks/own/generator-hash/1\n"
_TASK_ID_DOMAIN = b"poisson-tasks/own/task-id/1\n"
_DRAW_KEY = b"poisson-tasks/own/generator-draw/1"
_FMT = _FormatSpec(name="reference", markers=())
_LOOKALIKES = 6
_NUMBER_WIDTH = 4
_MAX_NAME = 64
_SPREAD_READS = 4
_SHAPE_RUNS = 4
_MOST_DEPTH = 8
_FEWEST_ARGUMENTS = 2
_MOST_ARGUMENTS = 8
_ATTEMPTS = 256
# How many times another value is drawn before a schema is taken to hold no other, and how many
# times a carried value is drawn before an argument is taken to have none a read can carry.
_FRESH_DRAWS = 32
_CARRY_DRAWS = 16
_NONE_PART = "none"
_NAME_WORD = _re.compile(r"[A-Za-z0-9_-]+")
_SENTENCE_END = _re.compile(r"(?<=[.!?])\s")
_CALL = "call"
_READ_THEN_CALL = "read then call"
_FLOW = "flow"
# The level of baddata whose first answer shows another key, and the one whose bad value is the
# smallest change; level 2 holds another value under the asked key.
_OTHER_KEY_LEVEL = 1
_NEAR_LEVEL = 3
_CLAUSE_2_ARGUMENTS = ("not", "an", "object")
_OUTSIDE = "not_a_tool_of_this_block"


@_dataclass(frozen=True)
class Flow:
    """One declared link: the `from_tool`'s output at `field` goes into the `to_tool`'s `param`."""

    from_tool: str
    field: str
    to_tool: str
    param: str


@_dataclass(frozen=True)
class OwnBundle:
    """One task on a user's own tools.

    The fields through `negative_controls` are the ones the tests read; `effects` (each shown
    tool's effect), `output_schemas` (each shown tool's output schema or `None`) and `steps`
    (the calls the task expects: `tool`, `effect`, `match`, the arguments that identify the
    call, `needs`, the steps it waits for, `serves`, the `[path, value]` pairs its answer
    carries, and `exact`, whether no other checkable argument may be given) carry what the
    simulator and the verdict need."""

    task_id: str
    arm_id: str
    seed: int
    split: str
    strictness: str
    set_name: str
    source_format: str
    file_digest: str
    generator_hash: str
    form: str
    system_prompt: str
    request: str
    prompt: str | tuple[dict[str, _Any], ...]
    tools: tuple[dict[str, _Any], ...]
    target: str
    target_tool: str
    stated: tuple[tuple[str, _Any], ...]
    named_reads: tuple[tuple[str, _Any, str], ...]
    fault_plan: _Mapping[str, int]
    reference_calls: tuple[tuple[str, _Any], ...]
    reference_observations: tuple[str, ...]
    negative_controls: _Mapping[str, tuple[tuple[str, _Any], ...]]
    effects: tuple[tuple[str, str], ...] = ()
    output_schemas: tuple[tuple[str, _Any], ...] = ()
    steps: tuple[dict[str, _Any], ...] = ()


# ---------------------------------------------------------------------------
# the hash and the id
# ---------------------------------------------------------------------------


def hash_of(sources: _Mapping[str, bytes]) -> str:
    """The hash of a mapping from module name to the module's bytes, in name order."""
    digest = _hashlib.sha256(_HASH_DOMAIN)
    for name in sorted(sources):
        digest.update(name.encode("utf-8") + b"\x1f" + sources[name] + b"\x1e")
    return digest.hexdigest()


def generator_hash() -> str:
    """The own-tools generator's hash: `hash_of` the bytes of `HASHED_MODULES`."""
    sources: dict[str, bytes] = {}
    for name in HASHED_MODULES:
        path = _import_module(name).__file__
        if not path:
            raise ValueError(f"{name} has no source file to hash")
        with open(path, "rb") as handle:
            sources[name] = handle.read()
    return hash_of(sources)


def _canon(value: _Any) -> _Any:
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, list | tuple):
        return [_canon(v) for v in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return repr(value)


def _task_id(bundle: OwnBundle) -> str:
    body = {f.name: _canon(getattr(bundle, f.name)) for f in _fields(bundle) if f.name != "task_id"}
    text = _json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _hashlib.sha256(_TASK_ID_DOMAIN + text).hexdigest()


# ---------------------------------------------------------------------------
# the draw
# ---------------------------------------------------------------------------


def _key(toolset: _OwnToolSet, split: str, seed: int) -> bytes:
    return f"{toolset.file_digest}\x1f{split}\x1f{seed}".encode()


def _pick(key: bytes, salt: str, count: int) -> int:
    if count <= 0:
        raise ValueError("a draw needs at least one option")
    digest = _hashlib.blake2b(key + b"\x1f" + salt.encode("utf-8"), key=_DRAW_KEY,
                              digest_size=32).digest()
    return int.from_bytes(digest, "big") % count


def _value(schema: _Any, key: bytes, salt: str) -> _Any:
    """A value conforming to an argument schema, or `None` when no draw conforms (a `pattern`
    the draw cannot meet); `None` is never a conforming value here, since a schema that admits
    null admits something else first."""
    for attempt in range(8):
        drawn = _sim.draw_value(_sim._strip(schema), key, f"{salt}/{attempt}")
        if drawn is not None and _sim.conforms(drawn, schema):
            return drawn
    return None


def _drawable(schema: _Any) -> bool:
    return _value(schema, b"probe", "drawable") is not None


# ---------------------------------------------------------------------------
# the set, read for a task
# ---------------------------------------------------------------------------


def _properties(tool: _OwnTool) -> dict[str, _Any]:
    found = tool.input_schema.get("properties")
    return dict(found) if isinstance(found, dict) else {}


def _required(tool: _OwnTool) -> list[str]:
    found = tool.input_schema.get("required")
    return [str(name) for name in found] if isinstance(found, list) else []


def _checkable(tool: _OwnTool) -> list[str]:
    """The tool's arguments a request can state and the verdict check, in schema order."""
    return [name for name, schema in _properties(tool).items()
            if not _is_free_text(schema) and _drawable(schema)]


def _required_drawable(tool: _OwnTool) -> bool:
    props = _properties(tool)
    return all(name in props and _drawable(props[name]) for name in _required(tool))


def _targets(toolset: _OwnToolSet) -> list[_OwnTool]:
    return [t for t in toolset.tools
            if _is_write(t) and _can_target(t) and _checkable(t) and _required_drawable(t)]


def _reads(toolset: _OwnToolSet) -> list[_OwnTool]:
    return [t for t in toolset.tools if t.effect == _READ and _required_drawable(t)]


def _check_reads(toolset: _OwnToolSet, target: _OwnTool) -> list[_OwnTool]:
    """The reads that can check a write to `target`: a read tool with a checkable argument whose
    name is one of the target's arguments, so a read of the written record answers with what
    was written after the write (the simulator's reflection)."""
    names = set(_properties(target))
    return [t for t in _reads(toolset) if names & set(_checkable(t))]


def _output_properties(tool: _OwnTool) -> dict[str, _Any] | None:
    """The properties of the tool's output schema, or `None` where it has no output schema."""
    if tool.output_schema is None:
        return None
    found = tool.output_schema.get("properties")
    return dict(found) if isinstance(found, dict) else {}


def _can_show(read: _OwnTool, target: _OwnTool) -> bool:
    """Whether a read's answer can show one of the target write's arguments: it has no output
    schema, so a whole write can show, or one of its output properties is named as one."""
    properties = _output_properties(read)
    return properties is None or any(name in properties for name in _properties(target))


def _landed_targets(toolset: _OwnToolSet) -> list[_OwnTool]:
    """The writes a landed task can target: those with a check read whose answer can show one
    of the write's arguments, the key it was read by among them.  A read that answers the same
    before the write and after it tells a model nothing about whether the write landed."""
    return [t for t in _targets(toolset)
            if any(_can_show(read, t) for read in _check_reads(toolset, t))]


def _string_field(tool: _OwnTool) -> str | None:
    """The field of the tool's answer a value the task needs is placed in: a free string
    property of its output schema, else any string property, else `id` when it has no output
    schema, else none."""
    if tool.output_schema is None:
        return "id"
    props = tool.output_schema.get("properties")
    if not isinstance(props, dict):
        return None
    strings = [name for name, schema in props.items()
               if isinstance(schema, dict) and schema.get("type") == "string"]
    free = [name for name in strings if _is_free_text(props[name])
            and "pattern" not in props[name]]
    if free:
        return str(free[0])
    return str(strings[0]) if strings else None


def _keyed_reads(toolset: _OwnToolSet) -> list[_OwnTool]:
    """Reads with a checkable argument and a field to answer in: spread's named reads."""
    return [t for t in _reads(toolset) if _checkable(t) and _string_field(t) is not None]


def _stated_names(tool: _OwnTool, carried: _Sequence[str] = ()) -> list[str]:
    """The arguments a request states on an arm whose values are not the knob: every argument a
    value can be drawn for, required or not, free text included, less what is carried."""
    return [name for name, schema in _properties(tool).items()
            if _drawable(schema) and name not in carried]


def _arguments_of(tool: _OwnTool, key: bytes, salt: str) -> dict[str, _Any]:
    """A value for every argument of the tool, drawn once at `salt`."""
    return {name: _value(schema, key, f"{salt}/{name}")
            for name, schema in _properties(tool).items()}


def _call_arguments(tool: _OwnTool, values: _Mapping[str, _Any], stated: _Sequence[str],
                    carried: _Mapping[str, _Any] | None = None) -> dict[str, _Any]:
    """The reference call's arguments: every required one, the stated ones and the carried
    ones, in the schema's order."""
    wanted = set(_required(tool)) | set(stated) | set(carried or {})
    out: dict[str, _Any] = {}
    for name in _properties(tool):
        if name in wanted:
            out[name] = (carried or {}).get(name, values.get(name))
    return out


def _spread_value(schema: _Any, key: bytes, salt: str) -> str | None:
    """A string value of the schema at least four characters long, or `None`."""
    if isinstance(schema, dict) and isinstance(schema.get("enum"), list):
        long = [v for v in schema["enum"] if isinstance(v, str) and len(v) >= _SPREAD_READS]
        return long[_pick(key, salt, len(long))] if long else None
    if isinstance(schema, dict) and "const" in schema:
        const = schema["const"]
        return const if isinstance(const, str) and len(const) >= _SPREAD_READS else None
    widened = dict(schema) if isinstance(schema, dict) else {}
    if "format" not in widened:
        low = widened.get("minLength")
        low = max(int(low) if isinstance(low, int) and not isinstance(low, bool) else 0,
                  _SPREAD_READS)
        high = widened.get("maxLength")
        if isinstance(high, int) and not isinstance(high, bool) and high < low:
            return None
        widened["minLength"] = low
    value = _value(widened, key, salt)
    if isinstance(value, str) and len(value) >= _SPREAD_READS and _sim.conforms(value, schema):
        return value
    return None


def _spread_targets(toolset: _OwnToolSet) -> list[tuple[_OwnTool, str]]:
    """Each target with the first of its checkable string arguments that admits a value of
    four characters or more."""
    out: list[tuple[_OwnTool, str]] = []
    for tool in _targets(toolset):
        props = _properties(tool)
        for name in _checkable(tool):
            schema = props[name]
            if isinstance(schema, dict) and schema.get("type") == "string" and (
                _spread_value(schema, b"probe", "spread") is not None
            ):
                out.append((tool, name))
                break
    return out


def _distinct_reads(
    toolset: _OwnToolSet, key: bytes, salt: str
) -> list[tuple[_OwnTool, dict[str, _Any]]]:
    """Four reads of the keyed read tools, no two the same call, or fewer when the set cannot
    make four."""
    tools = _keyed_reads(toolset)
    out: list[tuple[_OwnTool, dict[str, _Any]]] = []
    seen: set[str] = set()
    if not tools:
        return out
    for attempt in range(_ATTEMPTS):
        tool = tools[_pick(key, f"{salt}/tool/{attempt}", len(tools))]
        values = _arguments_of(tool, key, f"{salt}/args/{attempt}")
        checkable = _checkable(tool)
        wanted = set(_required(tool)) | set(checkable[:1])
        args = {name: values[name] for name in _properties(tool) if name in wanted}
        if any(value is None for value in args.values()):
            continue
        shape = f"{tool.name}\x1f{_sim.canonical(args)}"
        if shape in seen:
            continue
        seen.add(shape)
        out.append((tool, args))
        if len(out) == _SPREAD_READS:
            break
    return out


def _parts(value: str, count: int) -> list[str]:
    """`value` cut into `count` parts, as even as it goes, the earlier parts taking the extra."""
    each, extra = divmod(len(value), count)
    out: list[str] = []
    at = 0
    for index in range(count):
        size = each + (1 if index < extra else 0)
        out.append(value[at:at + size])
        at += size
    return out


# ---------------------------------------------------------------------------
# flows and chains
# ---------------------------------------------------------------------------


def _path_schema(schema: _Any, path: str) -> _Any:
    """The schema at `path` in an output schema (`a.b[].c`, `[]` marking an array), or raise."""
    node = schema
    for part in path.split("."):
        name = part.removesuffix("[]")
        props = node.get("properties") if isinstance(node, dict) else None
        if not isinstance(props, dict) or name not in props:
            raise KeyError(path)
        node = props[name]
        is_array = isinstance(node, dict) and (
            node.get("type") == "array" or ("items" in node and "type" not in node))
        if part.endswith("[]"):
            if not is_array:
                raise KeyError(path)
            node = node.get("items") if isinstance(node, dict) else None
        elif is_array:
            raise KeyError(path)
    return node


def check_flows(toolset: _Any, flows: _Sequence[Flow]) -> None:
    """Refuse, in one line, a flow that names no tool of the set, no path in the from-tool's
    output or no argument of the to-tool."""
    by_name = {tool.name: tool for tool in toolset.tools}
    for flow in flows:
        source = by_name.get(flow.from_tool)
        if source is None:
            raise ValueError(f"the flow names {flow.from_tool!r}, which is not a tool of the set")
        sink = by_name.get(flow.to_tool)
        if sink is None:
            raise ValueError(f"the flow names {flow.to_tool!r}, which is not a tool of the set")
        if source.output_schema is None:
            if flow.field != "id":
                raise ValueError(
                    f"{flow.from_tool} has no output schema, so its answer offers only id, not"
                    f" {flow.field!r}"
                )
        else:
            try:
                _path_schema(source.output_schema, flow.field)
            except KeyError:
                raise ValueError(
                    f"{flow.field!r} is not a path in {flow.from_tool}'s output; an array is"
                    " marked with [], as orders[].order_id"
                ) from None
        if flow.param not in _properties(sink):
            raise ValueError(f"{flow.param!r} is not an argument of {flow.to_tool}")


def _chains(toolset: _OwnToolSet, flows: _Sequence[Flow]) -> list[list[Flow]]:
    """Every path along the declared links that ends at a write that can be a target, longest
    first and then in the file's order of their tools."""
    order = {tool.name: index for index, tool in enumerate(toolset.tools)}
    ends = {tool.name for tool in _targets(toolset)}
    out: list[list[Flow]] = []

    def walk(path: list[Flow], seen: list[str]) -> None:
        last = path[-1].to_tool
        if last in ends:
            out.append(list(path))
        for flow in flows:
            if flow.from_tool == last and flow.to_tool not in seen:
                walk([*path, flow], [*seen, flow.to_tool])

    for flow in flows:
        walk([flow], [flow.from_tool, flow.to_tool])
    out.sort(key=lambda chain: (-len(chain), [order.get(chain[0].from_tool, 0)]
                                + [order.get(f.to_tool, 0) for f in chain]))
    return out


def _chain_tools(toolset: _OwnToolSet, chain: _Sequence[Flow]) -> list[_OwnTool]:
    by_name = {tool.name: tool for tool in toolset.tools}
    return [by_name[chain[0].from_tool], *[by_name[flow.to_tool] for flow in chain]]


def _longest_chain(
    toolset: _OwnToolSet, flows: _Sequence[Flow], *, keyed_first: bool
) -> list[Flow]:
    for chain in _chains(toolset, flows):
        tools = _chain_tools(toolset, chain)
        if not all(_required_drawable(tool) for tool in tools):
            continue
        if keyed_first and not _checkable(tools[0]):
            continue
        return chain
    return []


# ---------------------------------------------------------------------------
# levels
# ---------------------------------------------------------------------------


def _best_target(toolset: _OwnToolSet) -> _OwnTool | None:
    targets = _targets(toolset)
    if not targets:
        return None
    best = targets[0]
    for tool in targets[1:]:
        if len(_checkable(tool)) > len(_checkable(best)):
            best = tool
    return best


def _argument_levels(toolset: _OwnToolSet) -> tuple[int, ...]:
    best = _best_target(toolset)
    if best is None:
        return ()
    checkable = _checkable(best)
    required = [name for name in _required(best) if name in checkable]
    low = max(_FEWEST_ARGUMENTS, len(required))
    high = min(_MOST_ARGUMENTS, len(checkable))
    return tuple(range(low, high + 1)) if low <= high else ()


def _shape_runs(
    toolset: _OwnToolSet, chain: _Sequence[Flow], key: bytes
) -> list[list[dict[str, _Any]]] | None:
    """Four runs of the chain on values of their own, each run a list of per-call argument
    mappings (the carried ones included), no two runs sharing a first call or a last call."""
    tools = _chain_tools(toolset, chain)
    runs: list[list[dict[str, _Any]]] = []
    firsts: set[str] = set()
    lasts: set[str] = set()
    for attempt in range(_ATTEMPTS):
        calls = _chain_calls(tools, chain, key, f"shape/{attempt}")
        if calls is None:
            continue
        first = _sim.canonical(calls[0])
        last = _sim.canonical(calls[-1])
        if first in firsts or last in lasts:
            continue
        firsts.add(first)
        lasts.add(last)
        runs.append(calls)
        if len(runs) == _SHAPE_RUNS:
            return runs
    return None


def _chain_calls(
    tools: _Sequence[_OwnTool], chain: _Sequence[Flow], key: bytes, salt: str
) -> list[dict[str, _Any]] | None:
    """The arguments of each call of a chain: the first call's required and stated arguments,
    then each call's with the carried value drawn from its own parameter's schema."""
    calls: list[dict[str, _Any]] = []
    carried: dict[str, _Any] = {}
    for index, tool in enumerate(tools):
        values = _arguments_of(tool, key, f"{salt}/{index}")
        if index > 0:
            param = chain[index - 1].param
            drawn = _value(_properties(tool)[param], key, f"{salt}/{index}/carried")
            if drawn is None:
                return None
            carried = {param: drawn}
        args = _call_arguments(tool, values, _stated_names(tool, list(carried)), carried)
        if any(value is None for value in args.values()):
            return None
        calls.append(args)
    return calls


def knob_levels(toolset: _Any, knob: str, *, flows: _Sequence[Flow] = ()) -> tuple[int, ...]:
    """The levels of `knob` this set reaches; empty where it reaches none."""
    if knob not in KNOBS:
        raise ValueError(f"{knob!r} is not a knob on own tools: " + ", ".join(KNOBS))
    flows = tuple(flows)
    check_flows(toolset, flows)
    if not _targets(toolset):
        return ()
    if knob in (_SIMILARITY, _FAULTS, _TIMEOUTS, _RATELIMITS):
        return _knobs.levels(knob)
    if knob == _LANDED:
        return _knobs.levels(knob) if _landed_targets(toolset) else ()
    if knob == _BADDATA:
        pairs = _carrier_pairs(toolset)
        if not pairs:
            return ()
        if any(_names_its_key(read) for _target, _name, read in pairs):
            return _knobs.levels(knob)
        return tuple(level for level in _knobs.levels(knob) if level != _OTHER_KEY_LEVEL)
    if knob == _LAGGED:
        return _knobs.levels(knob) if _lagged_pairs(toolset) else ()
    if knob == _HISTORY:
        return _knobs.levels(knob) if _reads(toolset) else ()
    if knob == _BLOCK:
        return tuple(level for level in _knobs.levels(knob) if level <= len(toolset.tools))
    if knob == _ARGUMENTS:
        return _argument_levels(toolset)
    if knob == _SPREAD:
        if not _spread_targets(toolset):
            return ()
        probe = _distinct_reads(toolset, _key(toolset, _EVAL, 0), "spread-probe")
        return _knobs.levels(knob) if len(probe) == _SPREAD_READS else ()
    if knob == _DEPTH:
        chain = _longest_chain(toolset, flows, keyed_first=False)
        return tuple(range(1, min(len(chain) + 1, _MOST_DEPTH) + 1)) if chain else ()
    chain = _longest_chain(toolset, flows, keyed_first=True)
    if not chain or _shape_runs(toolset, chain, _key(toolset, _EVAL, 0)) is None:
        return ()
    return _knobs.levels(knob)


# ---------------------------------------------------------------------------
# the request's words
# ---------------------------------------------------------------------------


def _first_sentence(description: str) -> str:
    joined = " ".join(description.split())
    sentence = _SENTENCE_END.split(joined, maxsplit=1)[0] if joined else ""
    return sentence.rstrip(".!?")


def _scrub(text: str, names: _Sequence[str]) -> str:
    """`text` with every tool name that stands as a word replaced, so no request names a tool."""
    forbidden = set(names)

    def swap(match: _re.Match[str]) -> str:
        return "this tool" if match.group(0) in forbidden else match.group(0)

    return _NAME_WORD.sub(swap, text)


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _sentence(tool: _OwnTool, intents: _Mapping[str, str], names: _Sequence[str]) -> str:
    text = intents.get(tool.name) or _first_sentence(tool.description)
    return _capital(_scrub(text, names)) or "Make this call"


def _stated_text(pairs: _Sequence[tuple[str, _Any]]) -> str:
    if not pairs:
        return ""
    return ": " + ", ".join(f"{name} {_json.dumps(value)}" for name, value in pairs)


def _path_words(path: str) -> str:
    words: list[str] = []
    for part in path.split("."):
        if part.endswith("[]"):
            words.append(f"the first entry of {part[:-2]}")
        else:
            words.append(part)
    return " of ".join(reversed(words)) if len(words) > 1 else words[0]


def _system_prompt(toolset: _OwnToolSet, knob: str) -> str:
    clause = _FAULT_CLAUSES.get(knob, _FAULT_CLAUSE)
    return (
        f"You work with the tools of {toolset.name}. Make one tool call per turn, with its"
        f" arguments as JSON. {clause} Reply in plain text once the request is done, and make"
        " no other change."
    )


# ---------------------------------------------------------------------------
# the design of one task
# ---------------------------------------------------------------------------


@_dataclass
class _Design:
    form: str
    target: _OwnTool
    stated: list[tuple[str, _Any]]
    steps: list[dict[str, _Any]]
    reference: list[tuple[str, dict[str, _Any]]]
    request: str
    named_reads: list[tuple[str, dict[str, _Any], str]]
    block: list[_OwnTool]
    # A baddata task's episode that believed the bad answer, above level 0: the read once and
    # the write with the bad value.
    trusted: list[tuple[str, dict[str, _Any]]] | None = None


def _step(tool: _OwnTool, args: _Mapping[str, _Any], checked: _Sequence[str], *,
          needs: _Sequence[int] = (), serves: _Sequence[tuple[str, _Any]] = (),
          exact: bool = False) -> dict[str, _Any]:
    return {
        "tool": tool.name,
        "effect": _READ if tool.effect == _READ else _WRITE,
        "match": {name: args[name] for name in checked if name in args},
        "needs": list(needs),
        "serves": [[path, value] for path, value in serves],
        "exact": exact,
    }


def _checked(tool: _OwnTool, args: _Mapping[str, _Any], stated: _Sequence[str],
             carried: _Sequence[str] = ()) -> list[str]:
    checkable = _checkable(tool)
    return [name for name in args if name in checkable and (name in stated or name in carried)]


def _base_design(toolset: _OwnToolSet, target: _OwnTool, key: bytes, intents: _Mapping[str, str],
                 names: _Sequence[str], *, account: str | None = None,
                 stated_names: _Sequence[str] | None = None, exact: bool = False) -> _Design:
    values = _arguments_of(target, key, f"values/{target.name}")
    stated = list(stated_names if stated_names is not None else _stated_names(target))
    args = _call_arguments(target, values, stated)
    pairs = [(name, args[name]) for name in stated]
    request = _sentence(target, intents, names)
    if account is not None:
        request += f" for account {account}"
    request += _stated_text(pairs) + "."
    step = _step(target, args, _checked(target, args, stated), exact=exact)
    return _Design(_CALL, target, pairs, [step], [(target.name, args)], request, [],
                   list(toolset.tools))


def _spread_design(toolset: _OwnToolSet, level: int, key: bytes, intents: _Mapping[str, str],
                   names: _Sequence[str]) -> _Design:
    candidates = _spread_targets(toolset)
    target, carried_name = candidates[_pick(key, "spread/target", len(candidates))]
    carried = _spread_value(_properties(target)[carried_name], key, "spread/value")
    if carried is None:
        raise ValueError(f"no value of {target.name}'s {carried_name} can be split across reads")
    reads = _distinct_reads(toolset, key, "spread")
    if len(reads) < _SPREAD_READS:
        raise ValueError("the set cannot make four distinct reads to split a value across")
    parts = _parts(carried, level)
    steps: list[dict[str, _Any]] = []
    reference: list[tuple[str, dict[str, _Any]]] = []
    named: list[tuple[str, dict[str, _Any], str]] = []
    lines: list[str] = []
    for index, (tool, args) in enumerate(reads):
        field = _string_field(tool)
        assert field is not None
        held = parts[index] if index < level else _NONE_PART
        keys = [name for name in args if name in _checkable(tool)]
        steps.append(_step(tool, args, keys, serves=[(field, held)]))
        reference.append((tool.name, args))
        named.append((tool.name, args, field))
        shown = ", ".join(f"{name} {_json.dumps(args[name])}" for name in keys)
        lines.append(f"{index + 1}. {_sentence(tool, intents, names)}, {shown}: the {field} field")
    values = _arguments_of(target, key, f"values/{target.name}")
    stated = _stated_names(target, [carried_name])
    args = _call_arguments(target, values, stated, {carried_name: carried})
    pairs = [(name, args[name]) for name in stated]
    steps.append(_step(target, args, _checked(target, args, stated, [carried_name]),
                       needs=list(range(level))))
    reference.append((target.name, args))
    request = (
        f"{_sentence(target, intents, names)}{_stated_text(pairs)}. The {carried_name} is split"
        " across the answers of these four reads, in the order listed: join the parts. An answer"
        f" that holds no part reads \"{_NONE_PART}\".\n" + "\n".join(lines)
    )
    return _Design(_READ_THEN_CALL if level == 1 else _FLOW, target, pairs, steps, reference,
                   request, named, list(toolset.tools))


# ---------------------------------------------------------------------------
# bad data: a value carried in a read's answer, whose first answer is wrong
# ---------------------------------------------------------------------------


def _near_value(schemas: _Sequence[_Any], value: _Any) -> _Any:
    """The smallest change to `value` that conforms to every one of `schemas`, or `None` where
    there is none: another member of an enum, a number off by one or by a half, a string with
    its last character changed.  A boolean, a list and an object have none, and neither does a
    string no last character can change and conform, a date-time among them, so none of those
    is carried: a far value under the name of a near one would be level 2 again."""
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    first = schemas[0]
    candidates: list[_Any]
    if isinstance(first, dict) and isinstance(first.get("enum"), list):
        candidates = list(first["enum"])
    elif isinstance(value, int | float):
        candidates = [value + 1, value - 1, value + 0.5]
    else:
        candidates = [value[:-1] + letter for letter in "zyxwvutsrq0123456789"] if value else []
    for candidate in candidates:
        if isinstance(candidate, bool) or _sim.same(candidate, value):
            continue
        if all(_sim.conforms(candidate, schema) for schema in schemas):
            return candidate
    return None


def _fresh_value(schemas: _Sequence[_Any], avoid: _Sequence[_Any], key: bytes, salt: str) -> _Any:
    """A value drawn afresh from the first of `schemas` that conforms to them all and is not
    `avoid`'s first value, and where one can be drawn not its others either; `None` when every
    draw is the first."""
    kept: _Any = None
    for attempt in range(_FRESH_DRAWS):
        drawn = _value(schemas[0], key, f"{salt}/{attempt}")
        if drawn is None or isinstance(drawn, bool) or _sim.same(drawn, avoid[0]):
            continue
        if not all(_sim.conforms(drawn, schema) for schema in schemas):
            continue
        if not any(_sim.same(drawn, other) for other in avoid[1:]):
            return drawn
        kept = drawn
    return kept


def _read_arguments(read: _OwnTool, key: bytes, salt: str) -> dict[str, _Any] | None:
    """A keyed read's call, as spread draws its named reads': every required argument and the
    first checkable one, or `None` where one of them has no value."""
    values = _arguments_of(read, key, salt)
    wanted = set(_required(read)) | set(_checkable(read)[:1])
    args = {name: values[name] for name in _properties(read) if name in wanted}
    return None if any(value is None for value in args.values()) else args


def _match_keys(read: _OwnTool) -> list[str]:
    """The arguments of a keyed read's call that identify it: the checkable ones."""
    wanted = set(_required(read)) | set(_checkable(read)[:1])
    checkable = _checkable(read)
    return [name for name in _properties(read) if name in wanted and name in checkable]


def _names_its_key(read: _OwnTool) -> bool:
    """Whether a read's answer can name the key it was asked: it has no output schema, so the
    key shows at the top level, or an output property is named as one of its keys."""
    properties = _output_properties(read)
    return properties is None or any(name in properties for name in _match_keys(read))


def _carrier_field(read: _OwnTool, args: _Mapping[str, _Any], name: str, value: _Any) -> str | None:
    """The field of the read's answer that holds a carried value: a property the value conforms
    to and never one of the read's own arguments, the one named as the carried argument first
    and else the first that conforms; `id` where the read has no output schema.  `None` where
    the answer has no such field."""
    properties = _output_properties(read)
    if properties is None:
        return None if _sim._ID in args else _sim._ID
    fits = [str(field) for field, schema in properties.items()
            if field not in args and _sim.conforms(value, schema)]
    if name in fits:
        return name
    return fits[0] if fits else None


@_dataclass(frozen=True)
class _Carried:
    """What a baddata task carries, every part drawn without the level: the write's arguments,
    the names it states, the read's call, the field that holds the carried value, the value,
    its smallest change (level 3's), another value (levels 1 and 2's), and the other key a
    level-1 answer shows for each key the answer can name."""

    args: dict[str, _Any]
    stated: list[str]
    read_args: dict[str, _Any]
    field: str
    value: _Any
    near: _Any
    older: _Any
    other_key: dict[str, _Any]


def _carried(target: _OwnTool, name: str, read: _OwnTool, key: bytes) -> _Carried | None:
    """A value of `target`'s argument `name` that `read`'s answer can carry, with everything a
    baddata task needs of it, or `None` where no draw of `_CARRY_DRAWS` gives one.  A draw is
    taken again when the value has no smallest change, when the answer has no field for it, when
    no other value can be drawn, or when a read that can name its key was asked a key no other
    can stand in for."""
    schema = _properties(target)[name]
    output = _output_properties(read)
    naming = _names_its_key(read)
    keys = _match_keys(read)
    for attempt in range(_CARRY_DRAWS):
        salt = f"baddata/{attempt}"
        # The carried value alone first, at the salt the write's whole draw gives it below.
        value = _value(schema, key, f"{salt}/values/{name}")
        if value is None or isinstance(value, bool) or not isinstance(value, str | int | float):
            return None
        read_args = _read_arguments(read, key, f"{salt}/read")
        if read_args is None:
            return None
        field = _carrier_field(read, read_args, name, value)
        if field is None:
            continue
        schemas = [schema] if output is None else [schema, output[field]]
        near = _near_value(schemas, value)
        if near is None:
            continue
        older = _fresh_value(schemas, [value, near], key, f"{salt}/older")
        if older is None:
            continue
        other_key: dict[str, _Any] = {}
        failed = False
        for held in keys:
            if held not in read_args:
                continue
            if output is not None and (
                held not in output or not _sim.conforms(read_args[held], output[held])
            ):
                continue
            held_schemas = [_properties(read)[held]]
            if output is not None:
                held_schemas.append(output[held])
            other = _fresh_value(held_schemas, [read_args[held]], key, f"{salt}/key/{held}")
            if other is None:
                failed = True
                break
            other_key[held] = other
        if failed or (naming and not other_key):
            continue
        stated = _stated_names(target, [name])
        values = _arguments_of(target, key, f"{salt}/values")
        args = _call_arguments(target, values, stated, {name: value})
        if any(held is None for held in args.values()):
            continue
        return _Carried(args, stated, read_args, field, value, near, older, other_key)
    return None


def _carrier_pairs(toolset: _OwnToolSet) -> list[tuple[_OwnTool, str, _OwnTool]]:
    """Every write, checkable argument and keyed read of the set a baddata task can be made of,
    in the file's order: the ones a carried value can be drawn for at the set's probe."""
    probe = _key(toolset, _EVAL, 0)
    reads = [read for read in _reads(toolset) if _checkable(read)]
    return [
        (target, name, read)
        for target in _targets(toolset)
        for name in _checkable(target)
        for read in reads
        if _carried(target, name, read, probe) is not None
    ]


def _baddata_design(toolset: _OwnToolSet, level: int, key: bytes, intents: _Mapping[str, str],
                    names: _Sequence[str]) -> _Design:
    pairs = _carrier_pairs(toolset)
    # Where the set has a read that can name its key, the task is drawn from those at every
    # level, so one seed's target, argument and read are the same at all of them.
    named = [pair for pair in pairs if _names_its_key(pair[2])]
    pool = named or pairs
    target, name, read = pool[_pick(key, "baddata/pair", len(pool))]
    held = _carried(target, name, read, key)
    if held is None:
        raise ValueError(
            f"no value of {target.name}'s {name} can be carried in {read.name}'s answer at this"
            " seed"
        )
    keys = [each for each in held.read_args if each in _checkable(read)]
    bad_value = {0: None, _NEAR_LEVEL: held.near}.get(level, held.older)
    read_step = _step(read, held.read_args, keys, serves=[(held.field, held.value)])
    # The bad answer lives in the read step, under two keys only a baddata arm's steps have.
    read_step["bad"] = [[held.field, bad_value]] if level else None
    read_step["bad_key"] = dict(held.other_key) if level == _OTHER_KEY_LEVEL else None
    pairs_stated = [(each, held.args[each]) for each in held.stated]
    write_step = _step(target, held.args, _checked(target, held.args, held.stated, [name]),
                       needs=[0])
    read_call = (read.name, held.read_args)
    reference = [read_call] * (2 if level else 1) + [(target.name, held.args)]
    shown = ", ".join(f"{each} {_json.dumps(held.read_args[each])}" for each in keys)
    request = (
        f"{_sentence(target, intents, names)}{_stated_text(pairs_stated)}. The {name} is in this"
        f" read's answer: {_sentence(read, intents, names)}, {shown}: the {held.field} field."
    )
    trusted = None
    if level:
        trusted = [read_call, (target.name, {**held.args, name: bad_value})]
    return _Design(_READ_THEN_CALL, target, pairs_stated, [read_step, write_step], reference,
                   request, [(read.name, held.read_args, held.field)], list(toolset.tools),
                   trusted)


# ---------------------------------------------------------------------------
# lagged: a write, and a read that checks it
# ---------------------------------------------------------------------------


def _lagged_read_names(read: _OwnTool, target: _OwnTool) -> list[str] | None:
    """The arguments a lagged task's read is called with, each taken from the write: every
    required one and the first checkable one the write also has.  `None` where the read takes
    none of the write's arguments or requires one the write lacks."""
    held = _properties(target)
    shared = [name for name in _checkable(read) if name in held]
    if not shared or any(name not in held for name in _required(read)):
        return None
    wanted = set(_required(read)) | {shared[0]}
    return [name for name in _properties(read) if name in wanted]


def _shows_another(read: _OwnTool, target: _OwnTool) -> bool:
    """Whether the read's answer can show an argument of the write beside the ones it was read
    by: it has no output schema, or an output property is named as such an argument."""
    read_names = _lagged_read_names(read, target)
    if read_names is None:
        return False
    others = [name for name in _stated_names(target) if name not in read_names]
    properties = _output_properties(read)
    if properties is None:
        return bool(others)
    return any(name in properties for name in others)


def _lagged_calls(
    toolset: _OwnToolSet, target: _OwnTool, read: _OwnTool, key: bytes, seed: int, split: str
) -> tuple[dict[str, _Any], dict[str, _Any]] | None:
    """A lagged task's write and the read that checks it, or `None` where no draw gives a pair
    whose read shows the write.  A schema says a field can show the write and a drawn value may
    still not conform to it, so the write's values are drawn again until the read's answer
    before the write and after it differ; the level is no part of it."""
    read_names = _lagged_read_names(read, target)
    if read_names is None:
        return None
    stated = _stated_names(target)
    for attempt in range(_ATTEMPTS):
        values = _arguments_of(target, key, f"lagged/{attempt}/values")
        args = _call_arguments(target, values, stated)
        if any(held is None for held in args.values()):
            continue
        if any(name not in args for name in read_names):
            continue
        read_args = {name: args[name] for name in read_names}
        if not _sim.conforms(read_args, read.input_schema):
            continue
        drawn = _sim.respond(read, read_args, digest=toolset.file_digest, seed=seed, split=split)
        before = _sim._overlaid(drawn, read_args, read.output_schema)
        after = _sim._overlaid(before, args, read.output_schema)
        if before != after:
            return args, read_args
    return None


def _lagged_pairs(toolset: _OwnToolSet) -> list[tuple[_OwnTool, _OwnTool]]:
    """Every write and showing read of the set a lagged task can be made of, in the file's
    order: the ones whose read shows the write at the set's probe."""
    probe = _key(toolset, _EVAL, 0)
    return [
        (target, read)
        for target in _targets(toolset)
        for read in _reads(toolset)
        if _shows_another(read, target)
        and _lagged_calls(toolset, target, read, probe, 0, _EVAL) is not None
    ]


def _lagged_design(toolset: _OwnToolSet, level: int, key: bytes, seed: int, split: str,
                   intents: _Mapping[str, str], names: _Sequence[str]) -> _Design:
    pairs = _lagged_pairs(toolset)
    target, read = pairs[_pick(key, "lagged/pair", len(pairs))]
    calls = _lagged_calls(toolset, target, read, key, seed, split)
    if calls is None:
        raise ValueError(
            f"no write to {target.name} shows in {read.name}'s answer at this seed"
        )
    args, read_args = calls
    stated = _stated_names(target)
    pairs_stated = [(name, args[name]) for name in stated]
    step = _step(target, args, _checked(target, args, stated))
    shown = ", ".join(f"{name} {_json.dumps(value)}" for name, value in read_args.items())
    request = (
        f"{_sentence(target, intents, names)}{_stated_text(pairs_stated)}. Then check it took:"
        f" {_sentence(read, intents, names)}, {shown}. Make the change again only if it did not"
        " take."
    )
    # The reference reads once after the write, and at level 1 once more, right after the read
    # that lags.  The read is no step: it serves nothing, and any read of the set answers.
    reference = [(target.name, args)] + [(read.name, read_args)] * (1 + level)
    return _Design(_CALL, target, pairs_stated, [step], reference, request, [],
                   list(toolset.tools))


def _chain_steps(
    tools: _Sequence[_OwnTool], chain: _Sequence[Flow], calls: _Sequence[_Mapping[str, _Any]],
    *, first: int, needs_first: _Sequence[int] = (),
) -> list[dict[str, _Any]]:
    steps: list[dict[str, _Any]] = []
    for index, (tool, args) in enumerate(zip(tools, calls, strict=True)):
        carried = [chain[index - 1].param] if index > 0 else []
        serves = []
        if index < len(tools) - 1:
            serves.append((chain[index].field, calls[index + 1][chain[index].param]))
        needs = list(needs_first) if index == 0 else [first + index - 1]
        stated = _stated_names(tool, carried)
        steps.append(_step(tool, args, _checked(tool, args, stated, carried), needs=needs,
                           serves=serves))
    return steps


def _chain_words(
    tools: _Sequence[_OwnTool], chain: _Sequence[Flow], calls: _Sequence[_Mapping[str, _Any]],
    intents: _Mapping[str, str], names: _Sequence[str],
) -> str:
    pieces: list[str] = []
    for index, (tool, args) in enumerate(zip(tools, calls, strict=True)):
        carried = [chain[index - 1].param] if index > 0 else []
        stated = _stated_names(tool, carried)
        pairs = [(name, args[name]) for name in stated if name in args]
        words = _sentence(tool, intents, names)
        if index > 0:
            link = chain[index - 1]
            words += f", with {link.param} taken from {_path_words(link.field)} of that answer"
        pieces.append(("First, " if index == 0 and len(tools) > 1 else "Then " if index > 0 else "")
                      + (words if index == 0 else words[:1].lower() + words[1:])
                      + _stated_text(pairs) + ".")
    return " ".join(pieces)


def _depth_design(toolset: _OwnToolSet, level: int, key: bytes, flows: _Sequence[Flow],
                  intents: _Mapping[str, str], names: _Sequence[str]) -> _Design:
    chain = _longest_chain(toolset, flows, keyed_first=False)[-(level - 1):] if level > 1 else []
    whole = _longest_chain(toolset, flows, keyed_first=False)
    tools = _chain_tools(toolset, whole)[-level:]
    calls = _chain_calls(tools, chain, key, "depth")
    if calls is None:
        raise ValueError("no value of the chain's arguments can be drawn")
    steps = _chain_steps(tools, chain, calls, first=0)
    target = tools[-1]
    stated = _stated_names(target, [chain[-1].param] if chain else [])
    pairs = [(name, calls[-1][name]) for name in stated if name in calls[-1]]
    request = _chain_words(tools, chain, calls, intents, names)
    reference = [(tool.name, args) for tool, args in zip(tools, calls, strict=True)]
    return _Design(_FLOW if level > 1 else _CALL, target, pairs, steps, reference, request, [],
                   list(toolset.tools))


_WIDTH_WORDS = {
    1: "Do the jobs one after another, in the order listed: a job's first step waits until the"
       " job before it is done.",
    2: "Jobs 1 and 2 go in order and jobs 3 and 4 go in order; the two pairs are independent.",
    4: "The four jobs are independent and may be done in any order.",
}


def _shape_design(toolset: _OwnToolSet, width: int, key: bytes, flows: _Sequence[Flow],
                  intents: _Mapping[str, str], names: _Sequence[str]) -> _Design:
    chain = _longest_chain(toolset, flows, keyed_first=True)
    tools = _chain_tools(toolset, chain)
    runs = _shape_runs(toolset, chain, key)
    if runs is None:
        raise ValueError("the set cannot make four distinct runs of its chain")
    steps: list[dict[str, _Any]] = []
    reference: list[tuple[str, dict[str, _Any]]] = []
    pairs: list[tuple[str, _Any]] = []
    lines: list[str] = []
    target = tools[-1]
    for run, calls in enumerate(runs):
        first = len(steps)
        if width == 1 and run > 0:
            needs_first: list[int] = [first - 1]
        elif width == 2 and run in (1, 3):
            needs_first = [first - 1]
        else:
            needs_first = []
        steps += _chain_steps(tools, chain, calls, first=first, needs_first=needs_first)
        reference += [(tool.name, args) for tool, args in zip(tools, calls, strict=True)]
        stated = _stated_names(target, [chain[-1].param])
        pairs += [(name, calls[-1][name]) for name in stated if name in calls[-1]]
        lines.append(f"Job {run + 1}: {_chain_words(tools, chain, calls, intents, names)}")
    request = "Four jobs. " + " ".join(lines) + " " + _WIDTH_WORDS[width]
    return _Design(_FLOW, target, pairs, steps, reference, request, [], list(toolset.tools))


def _arguments_design(toolset: _OwnToolSet, level: int, key: bytes, intents: _Mapping[str, str],
                      names: _Sequence[str]) -> _Design:
    target = _best_target(toolset)
    assert target is not None
    checkable = _checkable(target)
    required = [name for name in _required(target) if name in checkable]
    others = [name for name in checkable if name not in required]
    ordered: list[str] = []
    remaining = list(others)
    while remaining:
        ordered.append(remaining.pop(_pick(key, f"arguments/order/{len(ordered)}", len(remaining))))
    stated = (required + ordered)[:level]
    return _base_design(toolset, target, key, intents, names, stated_names=stated, exact=True)


def _block_design(toolset: _OwnToolSet, level: int, key: bytes, intents: _Mapping[str, str],
                  names: _Sequence[str]) -> _Design:
    design = _base_design(toolset, _drawn_target(toolset, key), key, intents, names)
    ranked = sorted(toolset.tools, key=lambda tool: (tool.name != design.target.name,
                                                      _pick(key, f"block/{tool.name}", 2**32),
                                                      tool.name))
    chosen = {tool.name for tool in ranked[:level]}
    design.block = [tool for tool in toolset.tools if tool.name in chosen]
    return design


def _drawn_target(toolset: _OwnToolSet, key: bytes) -> _OwnTool:
    targets = _targets(toolset)
    return targets[_pick(key, "target", len(targets))]


def _drawn_landed_target(toolset: _OwnToolSet, key: bytes) -> _OwnTool:
    """A landed task's target, drawn per seed from the writes that have a check read, so the
    knob's two levels share it."""
    targets = _landed_targets(toolset)
    return targets[_pick(key, "landed/target", len(targets))]


def _history_prompt(toolset: _OwnToolSet, request: str, level: int, key: bytes, seed: int,
                    split: str) -> tuple[dict[str, _Any], ...]:
    reads = _reads(toolset)
    messages: list[dict[str, _Any]] = [{"role": "user", "content": request}]
    total = 0
    index = 0
    while total < level:
        tool = reads[_pick(key, f"history/tool/{index}", len(reads))]
        values = _arguments_of(tool, key, f"history/args/{index}")
        args = {name: values[name] for name in _properties(tool) if name in _required(tool)}
        answer = _sim.success(toolset.source_format, tool, _sim.respond(
            tool, args, digest=toolset.file_digest, seed=seed, split=split)).text
        call_id = f"call_{index}"
        messages.append({
            "role": "assistant",
            "tool_calls": [{
                "id": call_id, "type": "function",
                "function": {"name": tool.name,
                             "arguments": _json.dumps(args, separators=(",", ":"))},
            }],
        })
        messages.append({"role": "tool", "tool_call_id": call_id, "content": answer})
        total += pair_tokens(tool.name, args, answer)
        index += 1
    return tuple(messages)


def pair_tokens(name: str, arguments: _Any, observation: str) -> int:
    """A seeded read pair's tokens, counted as the built-in history knob counts them: the name
    bare, the arguments as one compact JSON object, the observation as it stands."""
    rendered = arguments if isinstance(arguments, str) else _json.dumps(
        arguments, separators=(",", ":"))
    return _count_tokens(name) + _count_tokens(rendered) + _count_tokens(observation)


# ---------------------------------------------------------------------------
# the block as shown, and the controls
# ---------------------------------------------------------------------------


def _cut(name: str) -> str:
    """The name cut to leave room for `_<number>` within 64 characters."""
    room = _MAX_NAME - _NUMBER_WIDTH - 1
    return name[:room] if len(name) > room else name


def _render(
    tool: _OwnTool, name: str | None = None, description: str | None = None
) -> dict[str, _Any]:
    return {
        "name": tool.name if name is None else name,
        "description": tool.description if description is None else description,
        "parameters": dict(tool.input_schema),
    }


def _other_value(schema: _Any, value: _Any, key: bytes, salt: str) -> _Any:
    """A conforming value of `schema` other than `value`, or `None` when none can be drawn."""
    if isinstance(value, bool):
        other: _Any = not value
        return other if _sim.conforms(other, schema) else None
    if isinstance(schema, dict) and isinstance(schema.get("enum"), list):
        for candidate in schema["enum"]:
            if not _sim.same(candidate, value):
                return candidate
        return None
    if isinstance(value, int | float):
        for candidate in (value + 1, value - 1, value + 0.5):
            if _sim.conforms(candidate, schema) and not _sim.same(candidate, value):
                return candidate
        return None
    if isinstance(value, str) and value:
        for letter in "zyxwvutsrq0123456789":
            candidate = value[:-1] + letter
            if candidate != value and _sim.conforms(candidate, schema):
                return candidate
    for attempt in range(8):
        drawn = _value(schema, key, f"{salt}/{attempt}")
        if drawn is not None and not _sim.same(drawn, value):
            return drawn
    return None


def _breaking(tool: _OwnTool) -> dict[str, _Any]:
    """Arguments that break the tool's schema."""
    props = _properties(tool)
    if _required(tool):
        return {}
    for name in _checkable(tool):
        schema = props[name]
        for bad in ({"not": "valid"}, "text", 0.5, [1]):
            if not _sim.conforms(bad, schema):
                return {name: bad}
    raise ValueError(f"no arguments break {tool.name}'s schema")


def _controls(
    design: _Design, reference: list[tuple[str, dict[str, _Any]]], to_shown: dict[str, str],
    block_names: _Sequence[str], key: bytes, copies: _Sequence[str],
) -> dict[str, tuple[tuple[str, _Any], ...]]:
    target = design.target
    shown_target = to_shown[target.name]
    # The target call is the reference's last call to the target: its last call on every knob
    # but lagged, whose reference ends with the read that checks the write.
    target_at = max(index for index, (name, _args) in enumerate(reference) if name == shown_target)
    (_last_tool, last_args) = reference[target_at]
    checked = [step["match"] for step in design.steps if step["tool"] == target.name
               and step["effect"] == _WRITE][-1]
    props = _properties(target)
    stray = dict(last_args)
    for name in checked:
        other = _other_value(props[name], last_args[name], key, f"stray/{name}")
        if other is not None:
            stray[name] = other
            break
    outside = _OUTSIDE
    while outside in block_names:
        outside += "_"
    controls: dict[str, tuple[tuple[str, _Any], ...]] = {
        "wrong_state": tuple(reference[:target_at] + reference[target_at + 1:]),
        "turn_limit": tuple(reference),
        "collateral_mutation": (*reference, (shown_target, stray)),
        "malformed_call_clause_2": ((shown_target, _CLAUSE_2_ARGUMENTS),),
        "malformed_call_clause_3": ((outside, {}),),
        "malformed_call_clause_4": ((shown_target, _breaking(target)),),
    }
    if copies:
        controls["collateral_mutation_lookalike"] = (*reference, (copies[0], dict(last_args)))
    if design.trusted is not None:
        # Every answer it meets is a success and the store takes its write, so only the end
        # state tells: a `wrong_state` control under a key that begins with its label.
        controls["wrong_state_trusted"] = tuple(
            (to_shown[name], args) for name, args in design.trusted
        )
    return controls


# ---------------------------------------------------------------------------
# the generator
# ---------------------------------------------------------------------------


def _refuse_level(toolset: _OwnToolSet, knob: str, level: int, flows: _Sequence[Flow]) -> None:
    found = knob_levels(toolset, knob, flows=flows)
    if level in found:
        return
    if knob in (_DEPTH, _SHAPE) and not flows:
        raise ValueError(f"{knob} is not available on {toolset.name} without flows."
                         f" {UNAVAILABLE_WITHOUT_FLOWS}")
    if not found:
        raise ValueError(f"{toolset.name} reaches no level of {knob}")
    reached = ", ".join(str(each) for each in found)
    raise ValueError(f"{toolset.name} reaches {knob} at {reached}, not {level}")


def generate(
    toolset: _Any,
    arm: _Any,
    seed: int,
    *,
    intents: _Mapping[str, str] | None = None,
    flows: _Sequence[Flow] = (),
) -> OwnBundle:
    """The task on `toolset` for `arm` (a `knobs.ArmSpec` at `GENERATOR_VERSION`) and `seed`."""
    if arm.generator_version != GENERATOR_VERSION:
        raise ValueError(f"the own-tools generator is {GENERATOR_VERSION!r}; the arm is at"
                         f" {arm.generator_version!r}")
    if arm.control is not None:
        raise ValueError(f"{_knobs.arm_id(arm)} is a control arm, and own tools have none")
    if arm.knob not in KNOBS:
        raise ValueError(f"{arm.knob!r} is not a knob on own tools: " + ", ".join(KNOBS))
    intents = dict(intents or {})
    by_name = {tool.name: tool for tool in toolset.tools}
    for name in intents:
        if name not in by_name:
            raise ValueError(f"the intent names {name!r}, which is not a tool of the set")
    flows = tuple(flows)
    _refuse_level(toolset, arm.knob, arm.level, flows)
    knob, level, split = arm.knob, arm.level, arm.split
    rendered = _knobs.arm_id(arm)
    key = _key(toolset, split, seed)
    names = [tool.name for tool in toolset.tools]
    account = _surface.target_number(seed, split) if knob == _SIMILARITY else None
    if knob == _SIMILARITY:
        names = names + [f"{_cut(n)}_{account}" for n in names]
    if knob in (_SIMILARITY, _FAULTS, _HISTORY, _TIMEOUTS, _RATELIMITS):
        design = _base_design(toolset, _drawn_target(toolset, key), key, intents, names,
                              account=account)
    elif knob == _LANDED:
        design = _base_design(toolset, _drawn_landed_target(toolset, key), key, intents, names)
    elif knob == _BADDATA:
        design = _baddata_design(toolset, level, key, intents, names)
    elif knob == _LAGGED:
        design = _lagged_design(toolset, level, key, seed, split, intents, names)
    elif knob == _BLOCK:
        design = _block_design(toolset, level, key, intents, names)
    elif knob == _ARGUMENTS:
        design = _arguments_design(toolset, level, key, intents, names)
    elif knob == _SPREAD:
        design = _spread_design(toolset, level, key, intents, names)
    elif knob == _DEPTH:
        design = _depth_design(toolset, level, key, flows, intents, names)
    else:
        design = _shape_design(toolset, level, key, flows, intents, names)

    # The block as shown: the whole set in file order, or the block arm's choice; similarity's
    # seven numbered tools standing where the target stands.
    to_shown = {tool.name: tool.name for tool in design.block}
    tools: list[dict[str, _Any]] = []
    effects: list[tuple[str, str]] = []
    outputs: list[tuple[str, _Any]] = []
    copies: list[str] = []
    for tool in design.block:
        if knob == _SIMILARITY and tool.name == design.target.name:
            assert account is not None
            numbers = sorted((account, *_surface.lookalike_numbers(seed, split, level)))
            for number in numbers:
                shown = f"{_cut(tool.name)}_{number}"
                tools.append(_render(tool, shown, f"{tool.description} (account {number})"))
                effects.append((shown, tool.effect))
                outputs.append((shown, tool.output_schema))
                if number == account:
                    to_shown[tool.name] = shown
                else:
                    copies.append(shown)
            continue
        tools.append(_render(tool))
        effects.append((tool.name, tool.effect))
        outputs.append((tool.name, tool.output_schema))
    block_names = [str(tool["name"]) for tool in tools]
    steps = tuple({**step, "tool": to_shown[step["tool"]]} for step in design.steps)
    reference = [(to_shown[name], args) for name, args in design.reference]
    named_reads = tuple((to_shown[name], args, field) for name, args, field in design.named_reads)

    path = tuple(dict.fromkeys(name for name, _args in reference))
    fault_plan = _surface.fault_plan(rendered, path) if knob in _PLANNED else {}
    if fault_plan and knob != _LANDED:
        # The reference carries the retries: each planned answer's call, and the same call
        # again.  A landed arm's one planned call goes through, so its reference is the call
        # once and the reply.
        expanded: list[tuple[str, dict[str, _Any]]] = []
        seen: set[str] = set()
        for name, args in reference:
            if name not in seen:
                seen.add(name)
                expanded += [(name, args)] * fault_plan.get(name, 0)
            expanded.append((name, args))
        reference = expanded

    prompt: str | tuple[dict[str, _Any], ...] = design.request
    if knob == _HISTORY and level > 0:
        prompt = _history_prompt(toolset, design.request, level, key, seed, split)

    bundle = OwnBundle(
        task_id="",
        arm_id=rendered,
        seed=seed,
        split=split,
        strictness=arm.strictness,
        set_name=toolset.name,
        source_format=toolset.source_format,
        file_digest=toolset.file_digest,
        generator_hash=generator_hash(),
        form=design.form,
        system_prompt=_system_prompt(toolset, knob),
        request=design.request,
        prompt=prompt,
        tools=tuple(tools),
        target=to_shown[design.target.name],
        target_tool=design.target.name,
        stated=tuple(design.stated),
        named_reads=named_reads,
        fault_plan=dict(fault_plan),
        reference_calls=tuple(reference),
        reference_observations=(),
        negative_controls={},
        effects=tuple(effects),
        output_schemas=tuple(outputs),
        steps=steps,
    )
    _state, answers = _sim.replay(bundle, bundle.reference_calls)
    controls = _controls(design, reference, to_shown, block_names, key, copies)
    bundle = _replace(bundle, reference_observations=tuple(a.text for a in answers),
                      negative_controls=controls)
    turns = tuple(_Turn(content="", calls=(call,), finish_reason="tool_calls")
                  for call in bundle.reference_calls) + (
        _Turn(content="Done.", calls=(), finish_reason="stop"),)
    for strictness in ("strict", "leaky"):
        verdict = _verify(_replace(bundle, strictness=strictness), turns, True, False, _FMT)
        if verdict.strict_label != "passed" or not verdict.leaky_pass:
            raise ValueError(
                f"generation refuses {rendered} at seed {seed} on {toolset.name}: its reference"
                f" verifies as {verdict.strict_label!r}, not 'passed'"
            )
    return _replace(bundle, task_id=_task_id(bundle))

