"""Own tools in 0.3.0: a write echoes what it was sent, the store keeps the writes, a read shows a
written record, and the three new knobs in each format's idiom, frozen as tests.

The invariants (the 0.3.0 faults spec, F2.10 to F2.13; Q3 ruled yes).  An accepted write answers
with every argument it was sent: beside `ok` and a drawn `id` without an output schema (an argument
named `id` winning), in the same-named output property when the value conforms to it with one, and
the values a task serves placed after.  `State.writes` lists every accepted write in order; a
repeated one is a duplicate, and the record says so.  After a write, a read whose checkable
arguments all equal the write's same-named ones answers with the write's values, the latest write
winning; `landed` is offered only on a set with such a read, and its target is drawn from the writes
that have one.  `timeouts` and `ratelimits` reach every level `faults` does; their answers, and
`landed`'s, are in each format's idiom; under `landed:l1` the first call to the target reaches the
store as any call does and is answered the timeout.

The fixture sets and helpers are `tests/o2_support.py`'s; the small sets built here are each the
fewest tools that show one rule.  The kept digests of the three knobs' own-tools tasks are written
by the build session in `tests/test_f2_kept.py`, as every knob's kept file was.

Shapes decided here
-------------------

**1. `State.writes` holds `(tool, simulator.canonical(arguments))` pairs**, the form
`side_effects` already uses for a stray write, in the order the server accepted them.

**2. "Byte for byte today's" is held by a digest measured on `main` at `9474ce4`**: every read in
every fixture set's block, at the three own-tools seeds, answered from a fresh store (so before any
write), and the two errors a faults task answers (the planned `unavailable` and a call that fails
the schema, where the schema refuses it: a write that takes no argument accepts it, and an accepted
write's answer is the echo's).  It holds on `main` by construction and is a guard: a build that changed a read's
answer before any write, or an error, fails it.

**3. A planned answer's idiom is the spec's table, to the byte**: the simulator's own rendering
(`json.dumps` sorted and compact), the error code in `Answer.code`, MCP's `isError` with the
message as the text.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks.arms import arm_from_id
from tests.f2_support import (
    DUPLICATE,
    KINDS,
    NO_CHECK_READ,
    OWN_CLAUSE,
    OWN_CLAUSES,
    OWN_SEEDS,
    field,
    loaded,
    own_contents,
    own_made,
    own_record,
    own_trace_of,
    stepped,
    writes,
    written,
)
from tests.k3_support import episode, made, records_of
from tests.o2_support import fixture_sets, generator, judge, mcp_set, read_tool, simulator, write_tool
from tests.test_o2_cli import QUIET, invoke, work  # noqa: F401 - the fixture is used by name

S12 = {"type": "string", "maxLength": 12}
AB = {"type": "string", "enum": ["a", "b"]}
FORMATS = {"acme-openai": "openai", "acme-mcp": "mcp", "acme-openapi-3.0": "openapi"}
READS_AND_ERRORS_ON_MAIN = "fa46ccadb8f748de63a60bdae74aaaa596aedcce2818fac3f76b92e9d1c59c2c"


def first_write(bundle: Any) -> tuple[str, dict[str, Any]]:
    name, args = bundle.reference_calls[0]
    return str(name), dict(args)


def effects(bundle: Any) -> dict[str, str]:
    return {str(name): str(effect) for name, effect in bundle.effects}


def conforming(tool: dict[str, Any], salt: str) -> dict[str, Any] | None:
    """Arguments drawn from a tool's input schema, or `None` where the draw does not conform."""
    sim = simulator()
    args = sim.draw_value(tool["parameters"], b"f2-reads", salt)
    if isinstance(args, dict) and sim.conforms(args, tool["parameters"]):
        return args
    return None


# --------------------------------------------------------------------------
# the echo (F2.10)
# --------------------------------------------------------------------------


def test_a_write_without_an_output_schema_answers_ok_an_id_and_every_argument() -> None:
    """On the OpenAI acme file, which has no output schemas, at the three seeds: the answer is
    `ok`, a drawn sixteen-character `id`, and each argument under its name; the same call after a
    read answers the same bytes.  On a set whose write takes an argument named `id`, that value is
    the answer's `id`."""
    toolset = fixture_sets()["acme-openai"]
    for seed in OWN_SEEDS:
        bundle = own_made(toolset, "faults", 0, seed)
        name, args = first_write(bundle)
        _state, (answer,) = stepped(bundle, [(name, args)])
        got = loaded(answer)
        assert set(got) == {"ok", "id", *args}, (seed, got)
        assert got["ok"] is True and isinstance(got["id"], str) and len(got["id"]) == 16
        assert {key: got[key] for key in args} == args
        read = next(n for n, e in effects(bundle).items() if e == "read")
        _state, (_read, again) = stepped(bundle, [(read, {}), (name, args)])
        assert again.text == answer.text
    tagged = mcp_set(write_tool("tag_item", {"id": S12, "tag": AB}, ["id", "tag"]),
                     read_tool("get_tag", {"id": S12}, ["id"]), name="ids")
    bundle = own_made(tagged, "faults", 0, 7)
    name, args = first_write(bundle)
    got = loaded(stepped(bundle, [(name, args)])[1][0])
    assert got == {"ok": True, **args}, got


def test_a_write_with_an_output_schema_echoes_into_same_named_properties_that_conform() -> None:
    """A write whose output schema names `level` (an integer) and `mode` (a string): `mode` is
    sent as `x` and answered `x`; `level` is sent as a string, which the output's integer does not
    take, and is answered with a drawn integer.  On petstore, every argument of the target whose
    value conforms to the same-named output property is answered back."""
    levels = mcp_set(
        write_tool("set_level", {"level": AB, "mode": {"type": "string", "enum": ["x", "y"]}},
                   ["level", "mode"],
                   output={"type": "object", "required": ["level", "mode"],
                           "properties": {"level": {"type": "integer"},
                                          "mode": {"type": "string", "maxLength": 8}}}),
        read_tool("peek", {"level": AB}, ["level"]), name="levels")
    bundle = own_made(levels, "faults", 0, 7)
    name, args = first_write(bundle)
    got = loaded(stepped(bundle, [(name, args)])[1][0])
    assert got["mode"] == args["mode"] and isinstance(got["level"], int), got
    sim = simulator()
    petstore = fixture_sets()["petstore"]
    checked = 0
    for seed in range(40):
        bundle = own_made(petstore, "faults", 0, seed)
        name, args = first_write(bundle)
        output = dict(bundle.output_schemas).get(name)
        if not output:
            continue
        got = loaded(stepped(bundle, [(name, args)])[1][0])
        for key, value in args.items():
            schema = output.get("properties", {}).get(key)
            if schema is not None and sim.conforms(value, schema):
                assert got[key] == value, (seed, name, key)
                checked += 1
    assert checked >= 3


def test_a_served_value_is_placed_after_the_echo() -> None:
    """A chain of two writes, `open_ticket`'s `ticket_id` flowing into `close_ticket`: the first
    answer carries the value the chain serves under `ticket_id`, not the one sent, and the other
    arguments as sent; the reference verifies `passed`."""
    flow = generator().Flow
    tickets = mcp_set(
        write_tool("open_ticket", {"ticket_id": S12, "title": AB, "note": S12},
                   ["ticket_id", "title", "note"],
                   output={"type": "object", "required": ["ticket_id", "title", "note"],
                           "properties": {"ticket_id": S12, "title": AB, "note": S12}}),
        write_tool("close_ticket", {"ticket_id": S12}, ["ticket_id"]),
        read_tool("get_ticket", {"ticket_id": S12}, ["ticket_id"]), name="tickets")
    flows = (flow("open_ticket", "ticket_id", "close_ticket", "ticket_id"),)
    bundle = own_made(tickets, "depth", 2, 7, flows=flows)
    (opened, sent), (_closed, carried) = bundle.reference_calls
    assert opened == "open_ticket" and sent["ticket_id"] != carried["ticket_id"]
    got = loaded(stepped(bundle, list(bundle.reference_calls))[1][0])
    assert got == {"ticket_id": carried["ticket_id"], "title": sent["title"], "note": sent["note"]}
    assert judge(bundle, list(bundle.reference_calls)).strict_label == "passed"


def test_reads_before_any_write_and_the_errors_answer_as_on_main() -> None:
    """Shape 2: a guard, true on `main` by construction."""
    sim = simulator()
    lines = []
    for label in ("acme-mcp", "acme-openai", "acme-openapi-3.0", "petstore", "everything"):
        for seed in OWN_SEEDS:
            bundle = own_made(fixture_sets()[label], "faults", 1, seed)
            for tool in bundle.tools:
                name = str(tool["name"])
                if effects(bundle)[name] != "read" or (args := conforming(tool, name)) is None:
                    continue
                answer = sim.step(bundle, sim.start(bundle), (name, args))[1]
                lines.append([label, seed, name, answer.text, answer.is_error, answer.code])
            target, _args = first_write(bundle)
            for answer in stepped(bundle, [bundle.reference_calls[0], (target, {"": []})])[1]:
                if answer.code is not None:
                    lines.append([label, seed, target, answer.text, answer.is_error, answer.code])
    digest = hashlib.sha256("\n".join(json.dumps(line) for line in lines).encode()).hexdigest()
    assert digest == READS_AND_ERRORS_ON_MAIN


# --------------------------------------------------------------------------
# the store and the duplicate (F2.11)
# --------------------------------------------------------------------------


def test_the_store_keeps_every_accepted_write_in_order() -> None:
    """Shape 1, on acme at seed 404 under `faults:f1`: the target's planned answer is no write; a
    stray write, the target, the target again and a call its schema refuses leave three writes,
    the second and third equal; the verdict is `malformed_call`, as today.

    Retrofitted 2026-10-29 by the build session: the assertion read `collateral_mutation`, which
    is not today's verdict on these calls.  The last call breaks the target's schema, so format
    clause 4 fires, and `malformed_call` comes before `collateral_mutation` in the frozen label
    order (`tests/test_o2_verdict.py`); measured on the unbuilt tree, where the verdict on this
    call list is `malformed_call` and on the same list without the refused call
    `collateral_mutation`.  The store's three writes and two side effects are held as
    written."""
    sim = simulator()
    bundle = own_made(fixture_sets()["acme-mcp"], "faults", 1, 404)
    target, args = first_write(bundle)
    stray_tool = next(t for t in bundle.tools
                      if effects(bundle)[str(t["name"])] != "read" and t["name"] != target)
    stray = (str(stray_tool["name"]), conforming(stray_tool, "stray"))
    assert stray[1] is not None
    calls = [(target, args), stray, (target, args), (target, args), (target, {"": []})]
    state, _answers = stepped(bundle, calls)
    canonical = sim.canonical
    assert writes(state) == (
        (stray[0], canonical(stray[1])), (target, canonical(args)), (target, canonical(args)))
    assert len(state.side_effects) == 2
    assert judge(bundle, calls).strict_label == "malformed_call"
    assert judge(bundle, calls[:-1]).strict_label == "collateral_mutation"


def test_a_repeated_write_is_recorded_as_a_duplicate(tmp_path: Path) -> None:
    """`duplicate_write` on the record: `True` when the expected write is made twice, `False` on
    the reference alone and when the same tool was written with other arguments first, and on a
    built-in arm `None` and left out of the written line."""
    bundle = own_made(fixture_sets()["acme-mcp"], "faults", 0, 404)
    reference = list(bundle.reference_calls)
    twice = own_record(tmp_path / "twice", bundle, [*reference, reference[-1]])
    once = own_record(tmp_path / "once", bundle, reference)
    name, args = reference[-1]
    other = {**args, "order_id": str(args["order_id"]) + "x"}
    apart = own_record(tmp_path / "apart", bundle, [(name, other), *reference])
    assert [field(r, DUPLICATE) for r in (twice, once, apart)] == [True, False, False]
    assert written(twice)[DUPLICATE] is True and written(once)[DUPLICATE] is False
    (tmp_path / "built-in").mkdir()
    b = made("faults:f0", 404)
    built_in = episode(tmp_path / "built-in", b, list(b.reference_calls))
    assert field(built_in, DUPLICATE) is None and DUPLICATE not in written(built_in)


# --------------------------------------------------------------------------
# a read shows a written record (F2.12, Q3)
# --------------------------------------------------------------------------


def test_a_read_after_a_write_shows_the_written_values_and_the_latest_wins() -> None:
    """On a set where `get_item` takes `item_id` and answers `item_id`, `status` and `size`: before
    any write, and after a write to another item, it answers as before; after `set_status` to it,
    with the write's `item_id` and `status`; after a second write, with that one's.  `get_other`,
    which shares no argument name, answers as before throughout.  On acme's OpenAI file, which has
    no output schemas, the read after the target answers its object with every argument of the
    write beside it."""
    items = mcp_set(
        write_tool("set_status", {"item_id": S12, "status": AB}, ["item_id", "status"]),
        read_tool("get_item", {"item_id": S12}, ["item_id"],
                  output={"type": "object", "required": ["item_id", "status", "size"],
                          "properties": {"item_id": S12, "status": AB, "size": {"type": "integer"}}}),
        read_tool("get_other", {"key": S12}, ["key"]), name="items")
    bundle = own_made(items, "faults", 0, 7)
    item = "itemone"
    read, other = ("get_item", {"item_id": item}), ("get_other", {"key": item})
    a = ("set_status", {"item_id": item, "status": "a"})
    b = ("set_status", {"item_id": item, "status": "b"})
    elsewhere = ("set_status", {"item_id": "itemtwo", "status": "b"})
    _state, answers = stepped(bundle, [read, other, elsewhere, read, a, read, other, b, read])
    before, other_before, _w, after_elsewhere, _a, after_a, other_after, _b, after_b = (
        loaded(answer) for answer in answers)
    assert after_elsewhere == before and other_after == other_before
    assert after_a == {**before, "item_id": item, "status": "a"}
    assert after_b == {**before, "item_id": item, "status": "b"}
    openai = own_made(fixture_sets()["acme-openai"], "faults", 0, 404)
    target, args = first_write(openai)
    look = ("get_order", {"order_id": args["order_id"]})
    _state, (first, _write, second) = stepped(openai, [look, (target, args), look])
    assert loaded(second) == {**loaded(first), **args}


def test_landed_reaches_its_levels_only_on_a_set_with_a_check_read() -> None:
    """acme (`get_order` takes `order_id`) and petstore reach `(0, 1)`; the Everything server,
    whose reads share no argument name with its writes, and a set whose one read takes another
    name reach `()`, and both reach every faults level."""
    gen = generator()
    sets = fixture_sets()
    assert gen.knob_levels(sets["acme-mcp"], "landed") == (0, 1)
    assert gen.knob_levels(sets["petstore"], "landed") == (0, 1)
    apart = mcp_set(write_tool("set_flag", {"flag": AB}, ["flag"]),
                    read_tool("look", {"key": S12}, ["key"]), name="apart")
    for toolset in (sets["everything"], apart):
        assert gen.knob_levels(toolset, "landed") == ()
        assert gen.knob_levels(toolset, "faults") == (0, 1, 2, 4)


def test_init_and_doctor_say_why_landed_is_not_offered(
    work: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """On the Everything server's list `init` and `doctor` print the sentence; on acme neither
    does."""
    from tests.o1_support import fixture

    for name, said in (("mcp-everything-tools-list.json", True), ("acme-mcp-tools-list.json", False)):
        (work / "tasks.toml").unlink(missing_ok=True)
        (work / "tools.json").write_bytes(fixture(name))
        made_it = invoke(["init", *QUIET, "--own-file", "tools.json"], monkeypatch)
        assert made_it.code == 0, made_it
        doctor = invoke(["doctor", "--offline"], monkeypatch)
        assert (NO_CHECK_READ in made_it.said, NO_CHECK_READ in doctor.said) == (said, said), name


def test_the_landed_target_has_a_check_read_and_both_levels_share_it() -> None:
    gen = generator()
    for label in ("acme-mcp", "petstore"):
        toolset = fixture_sets()[label]
        for seed in OWN_SEEDS:
            zero = own_made(toolset, "landed", 0, seed)
            one = own_made(toolset, "landed", 1, seed)
            assert (zero.target_tool, zero.stated) == (one.target_tool, one.stated), (label, seed)
            target = next(t for t in toolset.tools if t.name == one.target_tool)
            names = set(target.input_schema.get("properties") or {})
            assert any(
                t.effect == "read" and names & set(t.input_schema.get("properties") or {})
                for t in toolset.tools
            ), (label, seed, target.name)
    assert gen.knob_levels(fixture_sets()["acme-mcp"], "landed") == (0, 1)


# --------------------------------------------------------------------------
# the kinds on own tools (F2.13)
# --------------------------------------------------------------------------


def test_timeouts_and_ratelimits_reach_every_faults_level_on_every_set() -> None:
    gen = generator()
    for label, toolset in fixture_sets().items():
        reached = gen.knob_levels(toolset, "faults")
        assert reached == (0, 1, 2, 4), label
        assert gen.knob_levels(toolset, "timeouts") == reached
        assert gen.knob_levels(toolset, "ratelimits") == reached


def idiom(fmt: str, knob: str, tool: str) -> tuple[str, bool, str]:
    """Section 1.2's table: the text, `isError`, and the code."""
    kind = KINDS.get(knob, KINDS["timeouts"])
    message = f"{tool} {kind.tail}"
    retry = {"retry_after": 1} if knob == "ratelimits" else {}
    if fmt == "mcp":
        return message, True, kind.word
    if fmt == "openapi":
        body: dict[str, Any] = {"status": kind.status, "detail": message, **retry}
    else:
        body = {"error": {"code": kind.word, "message": message, **retry}}
    return json.dumps(body, sort_keys=True, separators=(",", ":")), False, kind.word


@pytest.mark.parametrize("label", list(FORMATS))
@pytest.mark.parametrize("knob", ["timeouts", "ratelimits", "landed"])
def test_a_planned_answer_is_in_the_formats_idiom_and_the_same_call_then_answers(
    knob: str, label: str
) -> None:
    """Shape 3, at level 1 and seed 404; the two new codes join the four."""
    assert set(simulator().ERROR_CODES) == {
        "not_found", "invalid_arguments", "not_ready", "unavailable", "timeout", "rate_limited"}
    bundle = own_made(fixture_sets()[label], knob, 1, 404)
    target, args = first_write(bundle)
    _state, (planned, again) = stepped(bundle, [(target, args), (target, args)])
    assert (planned.text, planned.is_error, planned.code) == idiom(FORMATS[label], knob, target)
    assert (again.is_error, again.code) == (False, None)


def test_under_landed_the_reference_is_one_call_and_a_blind_retry_is_a_duplicate() -> None:
    """At the three seeds on acme and petstore: the reference is the target once and a reply, its
    observation the timeout, and it verifies `passed` at both strictnesses; the store after it
    holds the goal; the same call again is accepted as a second, equal write and is
    `collateral_mutation` on strict."""
    assert arm_from_id("landed:l1").reference_turns == 3
    for label in ("acme-mcp", "petstore"):
        for seed in OWN_SEEDS:
            bundle = own_made(fixture_sets()[label], "landed", 1, seed)
            (call,) = bundle.reference_calls
            state, (answer,) = stepped(bundle, [call])
            assert answer.code == "timeout" and bundle.reference_observations == (answer.text,)
            assert all(state.done) and len(writes(state)) == 1
            assert judge(bundle, [call]).strict_label == "passed"
            leaky = own_made(fixture_sets()[label], "landed", 1, seed, strictness="leaky")
            assert judge(leaky, [call]).leaky_pass is True
            again, (_a, second) = stepped(bundle, [call, call])
            assert second.code is None and writes(again)[0] == writes(again)[1]
            assert judge(bundle, [call, call]).strict_label == "collateral_mutation"


def test_under_landed_the_first_call_reaches_the_store_whatever_it_is() -> None:
    """On acme at seed 404: a first call its schema refuses is answered the timeout and moves
    nothing, and the right call after it is not planned and is accepted; a first call that is a
    stray write is applied as one and answered the timeout.

    Retrofitted 2026-10-29 by the build session: the stray write's `order_id` was the target's
    with a character appended, which acme's schema refuses (`minLength` and `maxLength` are
    both 6), so that call was the first case again and not a stray write.  The stray write now
    takes the target's `order_id` with its last character changed, a value the schema takes
    that names another order."""
    bundle = own_made(fixture_sets()["acme-mcp"], "landed", 1, 404)
    (target, args), = bundle.reference_calls
    state, (refused, right) = stepped(bundle, [(target, {"": []}), (target, args)])
    assert refused.code == "timeout" and right.code is None
    assert all(state.done) and len(writes(state)) == 1
    order = str(args["order_id"])
    stray_args = {**args, "order_id": order[:-1] + ("x" if order[-1] != "x" else "y")}
    state, (stray,) = stepped(bundle, [(target, stray_args)])
    assert stray.code == "timeout"
    assert not any(state.done) and len(state.side_effects) == 1 and len(writes(state)) == 1


def test_the_own_system_prompt_swaps_its_fault_clause_on_the_new_knobs_only() -> None:
    toolset = fixture_sets()["acme-mcp"]
    today = own_made(toolset, "faults", 0, 404).system_prompt
    assert OWN_CLAUSE in today
    assert own_made(toolset, "similarity", 0, 404).system_prompt == today
    for knob, clause in OWN_CLAUSES.items():
        for level in (0, 1):
            got = own_made(toolset, knob, level, 404).system_prompt
            assert got == today.replace(OWN_CLAUSE, clause), (knob, level)


@pytest.mark.parametrize("arm", [("timeouts", 4), ("ratelimits", 4), ("landed", 1)],
                         ids=["timeouts", "ratelimits", "landed"])
def test_the_replay_check_holds_every_answer_on_the_new_arms(
    arm: tuple[str, int], tmp_path: Path
) -> None:
    """The reference, answered by the simulator, reads `passed`; a planted change to any answer
    is `replay_mismatch`."""
    bundle = own_made(fixture_sets()["acme-mcp"], arm[0], arm[1], 404)
    calls = list(bundle.reference_calls)
    sent = own_contents(bundle, calls)
    record = own_record(tmp_path / "reference", bundle, calls)
    assert (record.label, record.strict) == ("passed", True)
    for index, text in enumerate(sent):
        changed = list(sent)
        changed[index] = text[:-1] + ("0" if text[-1] != "0" else "1")
        (tmp_path / str(index)).mkdir()
        (planted,) = records_of(tmp_path / str(index), own_trace_of(bundle, calls, changed))
        assert (planted.label, planted.strict) == ("replay_mismatch", False), index
