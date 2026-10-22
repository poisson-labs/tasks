"""The simulator: responses shaped by a user's schemas, errors in each format's idiom, and the
state a task's calls move, frozen as tests.

The invariants:
- simulated responses conform to the tool's output schema when it has one (a
  property-based sweep), respect formats, enums and bounds, and repeat for the same call in one
  episode;
- each format's error idiom renders as the design says, and a planned fault changes nothing.
And the design's other clauses: a tool with no output schema answers `{"ok": true, "id": ...}`; an
MCP tool with one answers in `structuredContent` with its text form beside it; the values a task
needs are placed in a named string field of the response; reads change nothing, the expected
write moves its record, any other accepted write is a side effect, and every call advances a
counter; nothing reads a clock but a fixed one, nor the network.

Shapes decided here
-------------------

**1. `poisson_tasks.own.simulator`** is a module of its own, pure, and it holds:
`respond(tool, arguments, *, digest, seed, split)`, the object an accepted call to `tool` answers
with before any value the task needs is placed in it; `success(source_format, tool, value)` and
`error(source_format, code, message)`, each an `Answer(text, structured, is_error)`; and the
state machine over a generated task, `start(task)`, `step(task, state, call)` and
`replay(task, calls)`.  `Answer.text` is what the tool message carries; `structured` is the MCP
result's `structuredContent` or `None`; `is_error` is the MCP result's `isError`.

**2. The draw is keyed on the call's content**: `respond` is a function of the file's digest,
the task's seed and split, the tool's name and the arguments, and of nothing else, so the same
call in one episode gets the same answer, and the arm does not enter it.  The design names "(file
digest, seed, tool, arguments)"; a task's seed is a seed of its split (the built-in draw keys on
both), so the split is part of the seed here.

**3. `ERROR_CODES` is the design's four, in its order**: `not_found`, `invalid_arguments`,
`not_ready`, `unavailable`.  In the OpenAI idiom an error is Tasks' own tool result
`{"error": {"code": ..., "message": ...}}`, not flagged; in the MCP idiom the message is the
text and `is_error` is true; in the OpenAPI idiom it is `{"status": ..., "detail": ...}`, 503 for
`unavailable` and a 4xx for the others (which 4xx is the pending file
`test_o2_pending_openapi_status.py`).  The words of a message are not pinned.

**4. `State`** carries at least `calls` (every call the server received, the counter),
`side_effects` (the accepted writes the task did not expect) and `done` (one flag per write the
task expects, in the task's order).

**5. The state machine's order for a call that reaches the server**: the counter moves; a planned
failure answers `unavailable`; arguments that break the tool's schema answer
`invalid_arguments`; a read of a tool the task keys its records by answers `not_found` for a
key it does not hold; a write the task expects, made before the step that serves the value it
carries, answers `not_ready`; otherwise the call is accepted.  Only an accepted write changes the
store.  A call the harness answers itself (a name outside the block, arguments that are not an
object) never reaches the server and `replay` passes over it.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from poisson_tasks import own
from tests.o2_support import acme, make, simulator

DIGEST = "d" * 64
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DATE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def tool(output: Any, name: str = "probe", effect: str = "read") -> own.OwnTool:
    return own.OwnTool(name, "Probes.", {"type": "object", "properties": {"q": {"type": "string"}}},
                       output, effect)


def respond(output: Any, arguments: Any = None, **key: Any) -> Any:
    where = {"digest": DIGEST, "seed": 7, "split": "eval", **key}
    return simulator().respond(tool(output, where.pop("name", "probe")), arguments or {"q": "a"},
                               **where)


# --------------------------------------------------------------------------
# responses conform to the output schema
# --------------------------------------------------------------------------

NAMES = st.text(alphabet="abcdefghijklmnop_", min_size=1, max_size=8)


def _strings() -> st.SearchStrategy[dict[str, Any]]:
    bounded = st.tuples(st.integers(0, 12), st.integers(0, 12)).map(
        lambda pair: {"type": "string", "minLength": pair[0], "maxLength": pair[0] + pair[1]})
    formats = st.sampled_from(["email", "uuid", "date-time", "date"]).map(
        lambda f: {"type": "string", "format": f})
    enums = st.lists(st.text(alphabet="abcdefgh", min_size=1, max_size=6), min_size=1, max_size=4,
                     unique=True).map(lambda values: {"type": "string", "enum": values})
    return st.one_of(st.just({"type": "string"}), bounded, formats, enums)


def _numbers() -> st.SearchStrategy[dict[str, Any]]:
    integers = st.tuples(st.integers(-1000, 1000), st.integers(0, 50)).map(
        lambda pair: {"type": "integer", "minimum": pair[0], "maximum": pair[0] + pair[1]})
    open_numbers = st.tuples(st.integers(-1000, 1000), st.integers(1, 50)).map(
        lambda pair: {"type": "number", "exclusiveMinimum": pair[0],
                      "exclusiveMaximum": pair[0] + pair[1]})
    lower_only = st.integers(-50, 50).map(lambda low: {"type": "number", "minimum": low})
    return st.one_of(integers, open_numbers, lower_only, st.just({"type": "integer"}))


def _leaves() -> st.SearchStrategy[dict[str, Any]]:
    return st.one_of(
        _strings(), _numbers(),
        st.just({"type": "boolean"}), st.just({"type": "null"}),
        st.sampled_from([{"const": 3}, {"const": "fixed"}, {"type": ["string", "null"]},
                         {"enum": [1, "two", None]}]),
    )


def _one_of_types() -> st.SearchStrategy[dict[str, Any]]:
    """A `oneOf` whose branches take different types, so exactly one branch can hold a value."""
    return st.lists(st.sampled_from(["string", "integer", "boolean", "null"]), min_size=2,
                    max_size=4, unique=True).map(lambda kinds: {"oneOf": [{"type": k} for k in kinds]})


def _objects(children: st.SearchStrategy[dict[str, Any]]) -> st.SearchStrategy[dict[str, Any]]:
    def build(properties: dict[str, Any], data: st.DataObject) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "object", "properties": properties}
        required = data.draw(st.lists(st.sampled_from(sorted(properties)), unique=True)) if properties else []
        if required:
            out["required"] = required
        if data.draw(st.booleans()):
            out["additionalProperties"] = False
        return out

    return st.builds(build, st.dictionaries(NAMES, children, max_size=4), st.data())


def _schemas() -> st.SearchStrategy[dict[str, Any]]:
    return st.recursive(
        _leaves(),
        lambda children: st.one_of(
            _objects(children),
            st.tuples(children, st.integers(0, 3), st.integers(0, 3)).map(
                lambda t: {"type": "array", "items": t[0], "minItems": t[1], "maxItems": t[1] + t[2]}),
            st.lists(children, min_size=1, max_size=3).map(lambda bs: {"anyOf": bs}),
            _one_of_types(),
        ),
        max_leaves=10,
    )


def _formats_hold(value: Any, schema: Any) -> list[str]:
    """Formats the validator may not check where its optional libraries are missing, checked here
    by pattern: every string under a `format` the simulator draws holds it."""
    wrong: list[str] = []
    if isinstance(schema, dict) and isinstance(value, str):
        fmt = schema.get("format")
        if fmt == "email" and not EMAIL.match(value):
            wrong.append(f"email {value!r}")
        if fmt == "uuid":
            try:
                uuid.UUID(value)
            except ValueError:
                wrong.append(f"uuid {value!r}")
        if fmt == "date-time" and not DATE_TIME.match(value):
            wrong.append(f"date-time {value!r}")
        if fmt == "date" and not DATE.match(value):
            wrong.append(f"date {value!r}")
    if isinstance(schema, dict) and isinstance(value, dict):
        for key, sub in (schema.get("properties") or {}).items():
            if key in value:
                wrong += _formats_hold(value[key], sub)
    if isinstance(schema, dict) and isinstance(value, list) and isinstance(schema.get("items"), dict):
        for item in value:
            wrong += _formats_hold(item, schema["items"])
    return wrong


def conforms(value: Any, schema: Any) -> bool:
    validator = jsonschema.Draft202012Validator(
        schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)
    return not list(validator.iter_errors(value)) and not _formats_hold(value, schema)


SWEEP = settings(max_examples=400, deadline=None, derandomize=True,
                 suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])


@SWEEP
@given(output=_objects(_schemas()), seed=st.integers(0, 2**32 - 1),
       q=st.text(alphabet="xyz", max_size=4))
def test_a_response_conforms_to_the_output_schema(output: dict[str, Any], seed: int, q: str) -> None:
    value = respond(output, {"q": q}, seed=seed)
    assert conforms(value, output), (output, value)


@pytest.mark.parametrize("fixture", ["acme-mcp", "petstore", "everything"])
def test_every_fixture_tools_response_conforms_over_many_calls(fixture: str) -> None:
    """The recorded sets' own output schemas, every tool, a hundred calls each."""
    from tests.o2_support import fixture_sets

    toolset = fixture_sets()[fixture]
    sim = simulator()
    for item in toolset.tools:
        for seed in range(100):
            value = sim.respond(item, {}, digest=toolset.file_digest, seed=seed, split="eval")
            if item.output_schema is None:
                assert set(value) == {"ok", "id"} and value["ok"] is True, value
                assert isinstance(value["id"], str) and value["id"]
            else:
                assert conforms(value, item.output_schema), (item.name, value)


def test_formats_enums_and_bounds_are_respected_on_every_draw() -> None:
    output = {"type": "object", "required": ["email", "id", "at", "day", "state", "n", "x", "code", "long"],
              "properties": {
                  "email": {"type": "string", "format": "email"},
                  "id": {"type": "string", "format": "uuid"},
                  "at": {"type": "string", "format": "date-time"},
                  "day": {"type": "string", "format": "date"},
                  "state": {"type": "string", "enum": ["open", "shipped"]},
                  "n": {"type": "integer", "minimum": 3, "maximum": 5},
                  "x": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
                  "code": {"type": "string", "minLength": 6, "maxLength": 6},
                  "long": {"type": "string", "minLength": 20, "maxLength": 30}}}
    seen: dict[str, set[Any]] = {key: set() for key in output["properties"]}
    for seed in range(300):
        value = respond(output, seed=seed)
        assert conforms(value, output), value
        for key in seen:
            seen[key].add(value[key])
    assert seen["state"] == {"open", "shipped"}
    assert seen["n"] == {3, 4, 5}
    assert all(0 < x < 1 for x in seen["x"]) and len(seen["x"]) > 1
    assert len(seen["id"]) == 300 and len(seen["email"]) > 1


def test_a_tool_with_no_output_schema_answers_ok_and_an_id() -> None:
    values = [respond(None, seed=seed) for seed in range(50)]
    for value in values:
        assert set(value) == {"ok", "id"} and value["ok"] is True
        assert isinstance(value["id"], str) and value["id"]
    assert len({value["id"] for value in values}) == 50


# --------------------------------------------------------------------------
# the draw is keyed on the call's content
# --------------------------------------------------------------------------

KEYED = {"type": "object", "properties": {"id": {"type": "string", "format": "uuid"}},
         "required": ["id"]}


def test_the_same_call_gets_the_same_answer_and_each_part_of_the_key_moves_it() -> None:
    base = respond(KEYED, {"q": "a"})
    assert respond(KEYED, {"q": "a"}) == base
    assert respond(KEYED, {"q": "b"}) != base
    assert respond(KEYED, {"q": "a"}, seed=8) != base
    assert respond(KEYED, {"q": "a"}, split="train") != base
    assert respond(KEYED, {"q": "a"}, digest="e" * 64) != base
    assert respond(KEYED, {"q": "a"}, name="other") != base


def test_the_arguments_are_keyed_by_content_not_by_how_they_were_written() -> None:
    sim = simulator()
    probe = tool(KEYED)
    one = sim.respond(probe, {"q": "a", "r": 1}, digest=DIGEST, seed=7, split="eval")
    two = sim.respond(probe, dict(reversed(list({"q": "a", "r": 1}.items()))), digest=DIGEST, seed=7,
                      split="eval")
    assert one == two


CLOCK_PROBE = """
import datetime, json, sys, time
if sys.argv[1] == "moved":
    real_datetime, real_date = datetime.datetime, datetime.date

    class MovedDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(1999, 1, 1, tzinfo=tz)

        @classmethod
        def utcnow(cls):
            return real_datetime(1999, 1, 1)

        @classmethod
        def today(cls):
            return real_datetime(1999, 1, 1)

    class MovedDate(real_date):
        @classmethod
        def today(cls):
            return real_date(1999, 1, 1)

    datetime.datetime, datetime.date = MovedDateTime, MovedDate
    time.time, time.time_ns, time.monotonic = (lambda: 0.0), (lambda: 0), (lambda: 0.0)
from poisson_tasks import own
from poisson_tasks.own import simulator
output = {"type": "object", "properties": {"at": {"type": "string", "format": "date-time"},
                                           "day": {"type": "string", "format": "date"}},
          "required": ["at", "day"]}
probe = own.OwnTool("probe", "Probes.", {"type": "object", "properties": {}}, output, "read")
print(json.dumps([simulator.respond(probe, {}, digest="d" * 64, seed=s, split="eval") for s in range(20)]))
"""


def test_no_clock_but_a_fixed_one() -> None:
    """The clocks are moved before the simulator is imported, so a module that reads one however
    it imports it (`from datetime import datetime`, `from time import time`) draws other values."""
    runs = [subprocess.run([sys.executable, "-c", CLOCK_PROBE, mode], capture_output=True, text=True,
                           check=True).stdout for mode in ("real", "moved")]
    assert runs[0] == runs[1] and json.loads(runs[0])
    assert isinstance(simulator().CLOCK, str) and DATE_TIME.match(simulator().CLOCK)


# --------------------------------------------------------------------------
# MCP's structured content
# --------------------------------------------------------------------------


def test_an_mcp_tool_with_an_output_schema_answers_in_structured_content_with_its_text_beside() -> None:
    sim = simulator()
    probe = tool(KEYED)
    value = sim.respond(probe, {"q": "a"}, digest=DIGEST, seed=7, split="eval")
    mcp = sim.success("mcp", probe, value)
    assert mcp.structured == value and json.loads(mcp.text) == value and mcp.is_error is False
    for fmt in ("openai", "openapi"):
        other = sim.success(fmt, probe, value)
        assert other.structured is None and json.loads(other.text) == value and not other.is_error
    plain = tool(None)
    ok = sim.respond(plain, {"q": "a"}, digest=DIGEST, seed=7, split="eval")
    answer = sim.success("mcp", plain, ok)
    assert answer.structured is None and json.loads(answer.text) == ok


# --------------------------------------------------------------------------
# errors in each format's idiom
# --------------------------------------------------------------------------


def test_the_error_codes_are_spec_4s() -> None:
    assert simulator().ERROR_CODES == ("not_found", "invalid_arguments", "not_ready", "unavailable")


@pytest.mark.parametrize("code", ["not_found", "invalid_arguments", "not_ready", "unavailable"])
def test_each_format_renders_an_error_in_its_own_idiom(code: str) -> None:
    sim = simulator()
    message = f"the {code} message"
    openai = sim.error("openai", code, message)
    assert json.loads(openai.text) == {"error": {"code": code, "message": message}}
    assert openai.structured is None and openai.is_error is False
    mcp = sim.error("mcp", code, message)
    assert (mcp.text, mcp.structured, mcp.is_error) == (message, None, True)
    openapi = sim.error("openapi", code, message)
    body = json.loads(openapi.text)
    assert set(body) == {"status", "detail"} and body["detail"] == message
    assert openapi.structured is None and openapi.is_error is False
    if code == "unavailable":
        assert body["status"] == 503
    else:
        assert isinstance(body["status"], int) and 400 <= body["status"] <= 499


def test_an_error_code_outside_the_four_is_refused() -> None:
    with pytest.raises(ValueError):
        simulator().error("openai", "teapot", "no")


@pytest.mark.parametrize("shape", ["mcp", "openai", "openapi-3.0"])
def test_a_planned_fault_answers_unavailable_in_the_formats_idiom_and_changes_nothing(shape: str) -> None:
    bundle = make(acme(shape), "faults", 2)
    sim = simulator()
    first = bundle.reference_calls[0]
    state = sim.start(bundle)
    after, answer = sim.step(bundle, state, first)
    if bundle.source_format == "mcp":
        assert answer.is_error is True
    elif bundle.source_format == "openai":
        assert json.loads(answer.text)["error"]["code"] == "unavailable"
    else:
        assert json.loads(answer.text)["status"] == 503
    assert after.done == state.done and after.side_effects == state.side_effects
    assert after.calls == state.calls + 1


# --------------------------------------------------------------------------
# the state a task's calls move
# --------------------------------------------------------------------------


def test_reads_change_nothing_and_repeat_their_answer_in_one_episode() -> None:
    bundle = make(acme("mcp"), "similarity", 0)
    sim = simulator()
    state = sim.start(bundle)
    read: tuple[str, dict[str, Any]] = ("list_channels", {})
    after_one, first = sim.step(bundle, state, read)
    after_two, second = sim.step(bundle, after_one, read)
    assert first.text == second.text and not first.is_error
    assert after_two.done == state.done and after_two.side_effects == state.side_effects
    assert (after_one.calls, after_two.calls) == (state.calls + 1, state.calls + 2)


def test_arguments_that_break_the_schema_answer_invalid_arguments_and_change_nothing() -> None:
    bundle = make(acme("openai"), "faults", 0)
    sim = simulator()
    state = sim.start(bundle)
    for bad in ({}, {"order_id": "short", "amount": 1.0}, {"order_id": "A-3317", "amount": -1},
                {"order_id": "A-3317", "amount": "ten"}):
        after, answer = sim.step(bundle, state, ("refund_order", bad))
        assert json.loads(answer.text)["error"]["code"] == "invalid_arguments", bad
        assert after.done == state.done and after.side_effects == state.side_effects
        assert after.calls == state.calls + 1


def test_a_named_read_answers_not_found_for_a_key_the_task_does_not_hold() -> None:
    bundle = make(acme("openai"), "spread", 2)
    sim = simulator()
    named_tool, named_args, _field = bundle.named_reads[0]
    state = sim.start(bundle)
    _after, answer = sim.step(bundle, state, (named_tool, named_args))
    assert "error" not in json.loads(answer.text)
    unknown = {key: "QQQQQQ" for key in named_args}
    after, missing = sim.step(bundle, state, (named_tool, unknown))
    assert json.loads(missing.text)["error"]["code"] == "not_found"
    assert after.done == state.done and after.side_effects == state.side_effects


def test_a_write_made_before_the_step_that_serves_its_value_answers_not_ready() -> None:
    bundle = make(acme("openai"), "spread", 2)
    sim = simulator()
    (target_call,) = [call for call in bundle.reference_calls if call[0] == bundle.target]
    state = sim.start(bundle)
    early, answer = sim.step(bundle, state, target_call)
    assert json.loads(answer.text)["error"]["code"] == "not_ready"
    assert early.done == state.done and early.side_effects == ()
    full, _answers = sim.replay(bundle, bundle.reference_calls)
    assert all(full.done) and full.side_effects == ()


def test_replay_passes_over_what_the_harness_answers_itself() -> None:
    bundle = make(acme("mcp"), "faults", 0)
    sim = simulator()
    noise = [("not_offered", {}), (bundle.target, ["not", "an", "object"])]
    state, replayed = sim.replay(bundle, [*noise, *bundle.reference_calls])
    assert [a.text for a in replayed] == list(bundle.reference_observations)
    assert state.calls == len(bundle.reference_calls)


def test_openapi_3_0s_nullable_and_boolean_exclusive_bounds_are_read_as_3_0_means() -> None:
    """A 3.0 document's `nullable: true` lets a value be null, and `exclusiveMinimum: true` makes
    `minimum` exclusive, where a 2020-12 reader would ignore the one and misread the other."""
    document = {
        "openapi": "3.0.3", "info": {"title": "t", "version": "1"},
        "paths": {"/charge": {"post": {"operationId": "charge", "requestBody": {"content": {
            "application/json": {"schema": {"type": "object", "required": ["amount", "note"],
                                            "properties": {
                                                "amount": {"type": "number", "minimum": 0,
                                                           "exclusiveMinimum": True},
                                                "note": {"type": "string", "nullable": True,
                                                         "maxLength": 8}}}}}},
            "responses": {"200": {"description": "ok"}}}},
                  "/other": {"post": {"operationId": "other", "requestBody": {"content": {
                      "application/json": {"schema": {"type": "object", "properties": {
                          "n": {"type": "integer"}}, "required": ["n"]}}}},
                      "responses": {"200": {"description": "ok"}}}}},
    }
    toolset = own.read_tools(json.dumps(document).encode(), name="charges").toolset
    bundle = make(toolset, "faults", 0, seed=3)
    sim = simulator()
    state = sim.start(bundle)

    def status(arguments: dict[str, Any]) -> int | None:
        _after, answer = sim.step(bundle, state, ("charge", arguments))
        body = json.loads(answer.text)
        return body.get("status") if isinstance(body, dict) else None

    assert status({"amount": 0.5, "note": None}) is None
    assert status({"amount": 0.5, "note": "fine"}) is None
    assert status({"amount": 0, "note": "fine"}) is not None
    assert status({"amount": 0.5, "note": 12}) is not None


def test_the_simulator_opens_no_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """A guard: the design's "no network", over a whole replay."""
    import socket

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the simulator opened a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    bundle = make(acme("mcp"), "history", 600)
    state, replayed = simulator().replay(bundle, bundle.reference_calls)
    assert all(state.done) and len(replayed) == len(bundle.reference_calls)
