"""`baddata` and `lagged` on your own tools, and `landed`'s narrowed check read, frozen as tests.

The invariants (the 0.4.0 stale-data spec, BD.11 to BD.15 and BD.19).  A `baddata` task's request is
the target's sentence and stated values less one carried argument, which it says is in one read's
answer; one seed's target, argument, read and field are the same at every level.  The simulator
answers the first matching call from the bad value (level 1 under another key too) and every later
call from the true one; these two knobs' reads echo what they were asked, and no other arm's do.  The
real verdict catches a write that carried the bad value.  What a set reaches is section 5.1's, and a
set that lacks what a level needs says so in one sentence.  `lagged`'s first read that would reflect
the target write answers as if it had not landed, once in an episode.  `landed` draws only a write
whose check read's answer can show one of its arguments.

"The own seeds" are 404, 55 and 2121 on eval.  The fixture sets and helpers are `tests/o2_support.py`'s
and `tests/f2_support.py`'s; the small sets built here are each the fewest tools that show one rule.
The kept digests of the two knobs' own-tools tasks are written by the build session in
`tests/test_bd_kept.py`.

Shapes decided here
-------------------

**1. What a task carries is read off its steps and its reference** (`bd_support.carried`): the one read
step's `serves` gives the field and the true value, and the write's one argument the task does not
state is the carried one.  The bad value is read off the first answer, never off `steps[i]["bad"]`,
whose inner form the spec leaves to the build; only that the key is present on this knob's arms and
absent on every other's is held.

**2. A read's answer differing is held on the named field**, as the brief's trap says, and a lagging
read is held equal, byte for byte, to the same read made before any write.

**3. "The next member of an enum" is "another member"**: section 1.1 says next and section 1.3 says
another, and `_other_value` takes the first other; the test holds another.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import config
from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import generate
from tests.bd_support import (
    ABOVE_ZERO,
    BADDATA_BAD_CASES,
    BADDATA_CASES,
    BADDATA_REACH,
    LAGGED_REACH,
    LAGGED_SETS,
    NEEDS,
    OWN_CLAUSE_BADDATA,
    OWN_CLAUSE_LAGGED,
    OWN_CLAUSE_TODAY,
    OWN_SEEDS,
    SET_LABELS,
    TRUSTED,
    answers_of,
    canonical_write,
    carried,
    echoes,
    has_a_third_value,
    input_properties,
    is_near,
    needs,
    output_properties,
    own_arm,
    own_task,
)
from tests.f2_support import (
    DUPLICATE,
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
from tests.k3_support import records_of
from tests.o1_support import fixture
from tests.o2_support import fixture_sets, generator, judge, label_of, mcp_set, read_tool, simulator, write_tool
from tests.pv_support import invoke_json
from tests.test_f2_card_and_experimental import data_of
from tests.test_o2_cli import QUIET, invoke, work  # noqa: F401 - the fixture is used by name

S12 = {"type": "string", "maxLength": 12}
AB = {"type": "string", "enum": ["a", "b"]}
COUNT = {"type": "integer"}
LAG_SEEDS = (*OWN_SEEDS, *range(40))


def obj(**properties: Any) -> dict[str, Any]:
    return {"type": "object", "properties": properties}


def bad_case_tasks(label: str, level: int) -> list[Any]:
    return [own_task(label, "baddata", level, seed) for seed in OWN_SEEDS]


def first_and_later(bundle: Any) -> tuple[Any, Any, Any]:
    """The read's first three answers, each loaded."""
    read = carried(bundle).read
    first, second, third = answers_of(bundle, [read, read, read])
    return first, second, third


def bad_write(bundle: Any) -> tuple[str, dict[str, Any]]:
    """The write an episode that trusted the first answer makes: the bad value in the carried
    argument."""
    held = carried(bundle)
    first, _second, _third = first_and_later(bundle)
    return held.write[0], {**held.write[1], held.argument: first[held.field]}


# --------------------------------------------------------------------------
# the design (BD.11)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("label", SET_LABELS)
def test_one_seeds_target_argument_read_and_field_are_the_same_at_every_level(label: str) -> None:
    """At the own seeds and every level the set reaches, and the request with them."""
    for seed in OWN_SEEDS:
        bundles = [own_task(label, "baddata", level, seed) for level in BADDATA_REACH[label]]
        zero = bundles[0]
        held = carried(zero)
        for bundle in bundles[1:]:
            assert carried(bundle) == held, (label, seed, bundle.arm_id)
            assert bundle.request == zero.request and bundle.target_tool == zero.target_tool
            assert bundle.stated == zero.stated and bundle.tools == zero.tools
            assert bundle.prompt == zero.prompt and bundle.system_prompt == zero.system_prompt


@pytest.mark.parametrize("label", SET_LABELS)
def test_the_carried_argument_is_a_checkable_scalar_held_in_a_field_that_is_no_key(label: str) -> None:
    """Shape 1.  The field is the same-named property where the value conforms to it and it is no
    key of the read, else the first property it conforms to that is no key; `id` where the read has
    no output schema; its value conforms."""
    sim = simulator()
    for level in BADDATA_REACH[label]:
        for seed in OWN_SEEDS:
            bundle = own_task(label, "baddata", level, seed)
            held = carried(bundle)
            assert isinstance(held.value, str | int | float), (label, seed, held)
            assert not isinstance(held.value, bool), (label, seed, held)
            (write_step,) = [s for s in bundle.steps if s["effect"] == "write"]
            assert held.argument in write_step["match"], (label, seed, held)
            assert sim.same(held.write[1][held.argument], held.value), (label, seed, held)
            keys = set(held.read[1])
            assert held.field not in keys, (label, seed, held)
            properties = output_properties(bundle, held.read[0])
            if properties is None:
                assert held.field == "id", (label, seed, held)
                continue
            assert sim.conforms(held.value, properties[held.field]), (label, seed, held)
            fits = [name for name, schema in properties.items()
                    if name not in keys and sim.conforms(held.value, schema)]
            wanted = held.argument if held.argument in fits else fits[0]
            assert held.field == wanted, (label, seed, held)


@pytest.mark.parametrize("label", SET_LABELS)
def test_the_request_names_no_tool_and_states_every_other_argument(label: str) -> None:
    """The stated values are the write's arguments less the carried one, each in the request by name
    and value; the carried value is not stated; no tool's name is in the request; the read's key is
    given."""
    for seed in OWN_SEEDS:
        bundle = own_task(label, "baddata", 0, seed)
        held = carried(bundle)
        assert dict(bundle.stated).keys() == {k for k in held.write[1] if k != held.argument}
        for name, value in bundle.stated:
            assert f"{name} {json.dumps(value)}" in bundle.request, (label, seed, name)
        assert f"{held.argument} {json.dumps(held.value)}" not in bundle.request, (label, seed)
        for key, value in held.read[1].items():
            if key in held.keys:
                assert f"{key} {json.dumps(value)}" in bundle.request, (label, seed, key)
        words = bundle.request.replace('"', " ").replace(",", " ").replace(".", " ").split()
        for tool in bundle.tools:
            assert str(tool["name"]) not in words, (label, seed, tool["name"])


@pytest.mark.parametrize("label", SET_LABELS)
def test_the_system_prompt_swaps_its_clause_at_every_level(label: str) -> None:
    """Section 6.2: own tools swap the fault clause, and the unavailable clause does not belong on
    these arms.  `faults` keeps it, as the control."""
    toolset = fixture_sets()[label]
    today = own_made(toolset, "faults", 0, 404).system_prompt
    assert OWN_CLAUSE_TODAY in today
    for level in BADDATA_REACH[label]:
        got = own_task(label, "baddata", level, 404).system_prompt
        assert got == today.replace(OWN_CLAUSE_TODAY, OWN_CLAUSE_BADDATA), (label, level)


# --------------------------------------------------------------------------
# the answers (BD.12)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "level"), BADDATA_CASES)
def test_the_first_matching_call_answers_bad_and_every_later_call_true(label: str, level: int) -> None:
    """At the own seeds: at level 0 every answer holds the true value in the field; above it the
    first holds another, the second and third the true one.  Every answer is a success, and fits
    the read's output schema where it has one."""
    sim = simulator()
    for bundle in bad_case_tasks(label, level):
        held = carried(bundle)
        read = held.read
        _state, raw = stepped(bundle, [read, read, read])
        assert all(a.code is None and not a.is_error for a in raw), (label, level, bundle.seed)
        first, second, third = (loaded(a) for a in raw)
        assert sim.same(second[held.field], held.value) and second == third, (label, level, bundle.seed)
        if level:
            assert not sim.same(first[held.field], held.value), (label, level, bundle.seed)
        else:
            assert first == second, (label, level, bundle.seed)
        output = dict(bundle.output_schemas).get(read[0])
        if output is not None:
            for answer in (first, second):
                assert sim.conforms(answer, output), (label, level, bundle.seed, answer)


@pytest.mark.parametrize(("label", "level"), BADDATA_CASES)
def test_the_read_echoes_what_it_was_asked_and_level_1_alone_shows_another_key(
    label: str, level: int
) -> None:
    """At the own seeds: under the same-named output property, or the top level with no output
    schema, where the answer has a place for it (petstore's has none, which is why it has no level
    1); level 1's first answer shows another key and every later one the asked."""
    for bundle in bad_case_tasks(label, level):
        held = carried(bundle)
        first, second, _third = first_and_later(bundle)
        shown = [key for key in held.keys if echoes(bundle, held.read[0], key)]
        if label != "petstore":
            assert shown, (label, bundle.seed)
        for key in shown:
            assert second[key] == held.read[1][key], (label, level, bundle.seed, key)
            if level == 1:
                assert first[key] != held.read[1][key], (label, level, bundle.seed, key)
            else:
                assert first[key] == held.read[1][key], (label, level, bundle.seed, key)


@pytest.mark.parametrize("label", SET_LABELS)
def test_level_3s_value_is_near_and_level_2s_differs_from_the_truth_and_from_it(label: str) -> None:
    """Shape 3.  Level 3: a number off by one or a half, a string with its last character changed,
    another member of an enum.  Level 2: not the truth, and not level 3's where the schema has a
    third value."""
    sim = simulator()
    for seed in OWN_SEEDS:
        near_task = own_task(label, "baddata", 3, seed)
        held = carried(near_task)
        schema = input_properties(near_task, held.write[0])[held.argument]
        near = first_and_later(near_task)[0][held.field]
        assert is_near(schema, held.value, near), (label, seed, held.value, near)
        older = first_and_later(own_task(label, "baddata", 2, seed))[0][held.field]
        assert not sim.same(older, held.value), (label, seed)
        if has_a_third_value(schema):
            assert not sim.same(older, near), (label, seed, older, near)


@pytest.mark.parametrize("label", ["acme-mcp", "acme-openai", "petstore"])
def test_a_read_of_another_key_does_not_spend_the_first_answer(label: str) -> None:
    """A call that does not match the step leaves its first answer unspent, as another page does on
    the built-in tasks."""
    sim = simulator()
    for seed in OWN_SEEDS:
        bundle = own_task(label, "baddata", 2, seed)
        held = carried(bundle)
        key = held.keys[0]
        value = held.read[1][key]
        other = value[:-1] + ("x" if value[-1] != "x" else "y") if isinstance(value, str) else value + 1
        args = {**held.read[1], key: other}
        assert sim.conforms(args, next(t for t in bundle.tools
                                       if t["name"] == held.read[0])["parameters"]), (label, seed)
        answers = answers_of(bundle, [(held.read[0], args), held.read, held.read])
        assert not sim.same(answers[1][held.field], held.value), (label, seed)
        assert sim.same(answers[2][held.field], held.value), (label, seed)


def test_the_echo_is_on_these_two_knobs_arms_and_on_no_other() -> None:
    """Q9.  On acme at seed 404, `get_order` asked for an order under `faults` names another order
    (the spec's M7) and under `baddata:b0` the one asked.  Every read of a `baddata` task's block
    echoes, the read the task does not name among them, and `bad` and `bad_key` are on this knob's
    read steps and no other's."""
    toolset = fixture_sets()["acme-mcp"]
    asked = {"order_id": "swphup"}
    plain = own_made(toolset, "faults", 0, 404)
    assert loaded(stepped(plain, [("get_order", asked)])[1][0])["order_id"] != "swphup"
    assert all("bad" not in step and "bad_key" not in step for step in plain.steps)
    spread = own_made(toolset, "spread", 1, 404)
    assert all("bad" not in step and "bad_key" not in step for step in spread.steps)
    bundle = own_task("acme-openai", "baddata", 0, 404)
    (read_step,) = [s for s in bundle.steps if s["effect"] == "read"]
    assert "bad" in read_step and "bad_key" in read_step
    two_reads = mcp_set(
        write_tool("set_status", {"status": AB}, ["status"]),
        read_tool("get_one", {"key": S12}, ["key"], output=obj(key=S12, status=AB)),
        read_tool("get_two", {"key": S12}, ["key"], output=obj(key=S12, status=AB)),
        name="built",
    )
    for seed in range(4):
        task = own_task(two_reads, "baddata", 0, seed)
        unnamed = next(name for name in ("get_one", "get_two") if name != carried(task).read[0])
        assert answers_of(task, [(unnamed, {"key": "asked"})])[0]["key"] == "asked", seed
    lagged = own_task("acme-openai", "lagged", 0, 404)
    assert all("bad" not in step and "bad_key" not in step for step in lagged.steps)


@pytest.mark.parametrize(("label", "level"), [("acme-mcp", 2), ("acme-openai", 1), ("petstore", 3)])
def test_the_replay_check_holds_every_baddata_answer(label: str, level: int, tmp_path: Path) -> None:
    """The reference, answered by the simulator, reads `passed`; a planted change to any answer is
    `replay_mismatch`."""
    bundle = own_task(label, "baddata", level, 404)
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


# --------------------------------------------------------------------------
# the verdict (BD.13)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("label", "level"), BADDATA_CASES)
def test_every_reference_passes_and_every_control_earns_its_label(label: str, level: int) -> None:
    """By real `own.verify`, strict and leaky: the reference is the read, once at level 0 and twice
    above it, then the write, 3 and 4 turns.  The write waits on the read: made first, it answers
    `not_ready`, which is loud (section 1.3)."""
    for seed in OWN_SEEDS:
        bundle = own_task(label, "baddata", level, seed)
        held = carried(bundle)
        assert list(bundle.reference_calls) == [held.read] * (2 if level else 1) + [held.write], (
            label, level, seed)
        assert judge(bundle, list(bundle.reference_calls)).strict_label == "passed", (label, seed)
        made_first = stepped(bundle, [held.write])[1][0]
        assert made_first.code == "not_ready", (label, level, seed, made_first)
        leaky = own_task(label, "baddata", level, seed, strictness="leaky")
        assert judge(leaky, list(leaky.reference_calls)).leaky_pass is True, (label, seed)
        for key, calls in bundle.negative_controls.items():
            wanted = label_of(key)
            got = (judge(bundle, list(calls), reply=False, turn_limit=True) if wanted == "turn_limit"
                   else judge(bundle, list(calls)))
            assert got.strict_label == wanted, (label, level, seed, key, got)
        assert (TRUSTED in bundle.negative_controls) is (level > 0), (label, level, seed)


@pytest.mark.parametrize(("label", "level"), BADDATA_BAD_CASES)
def test_a_write_carrying_the_bad_value_is_wrong_state_and_with_the_right_one_collateral(
    label: str, level: int
) -> None:
    """A stray write the store accepts: `wrong_state`, leaky false; it and the right write,
    `collateral_mutation`, leaky true.  `wrong_state_trusted` is the read once and that write."""
    for seed in OWN_SEEDS:
        bundle = own_task(label, "baddata", level, seed)
        held = carried(bundle)
        trusting = bad_write(bundle)
        state, answers = stepped(bundle, [held.read, trusting])
        assert answers[1].code is None and writes(state) == (canonical_write(trusting),), (label, seed)
        got = judge(bundle, [held.read, trusting])
        assert (got.strict_label, got.leaky_pass) == ("wrong_state", False), (label, level, seed, got)
        both = judge(bundle, [held.read, trusting, held.write])
        assert (both.strict_label, both.leaky_pass) == ("collateral_mutation", True), (
            label, level, seed, both)
        assert list(bundle.negative_controls[TRUSTED]) == [held.read, trusting], (label, level, seed)


# --------------------------------------------------------------------------
# what a set reaches, and what it says (BD.14)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("label", SET_LABELS)
def test_knob_levels_is_the_specs_on_every_fixture_set(label: str) -> None:
    gen = generator()
    toolset = fixture_sets()[label]
    assert gen.knob_levels(toolset, "baddata") == BADDATA_REACH[label]
    assert gen.knob_levels(toolset, "lagged") == LAGGED_REACH[label]


def named_set(output: Any) -> Any:
    return mcp_set(write_tool("set_status", {"item_id": S12, "status": AB}, ["item_id", "status"]),
                   read_tool("get_item", {"item_id": S12}, ["item_id"], output=output), name="built")


@pytest.mark.parametrize(
    ("toolset", "reach"),
    [
        (lambda: named_set(obj(item_id=S12, label=S12)), (0, 1, 2, 3)),
        (lambda: named_set(obj(label=S12)), (0, 2, 3)),
        (lambda: named_set(None), (0, 1, 2, 3)),
        (lambda: named_set(obj(item_id=S12)), ()),
        (lambda: named_set(obj(count=COUNT)), ()),
        (lambda: mcp_set(write_tool("set_flag", {"flag": {"type": "boolean"}}, ["flag"]),
                         read_tool("look", {"key": S12}, ["key"]), name="built"), ()),
        (lambda: mcp_set(write_tool("set_tags", {"tags": {"type": "array", "items": S12}}, ["tags"]),
                         read_tool("look", {"key": S12}, ["key"]), name="built"), ()),
        (lambda: mcp_set(write_tool("set_status", {"status": AB}, ["status"]),
                         read_tool("look_all", {}, []), name="built"), ()),
        (lambda: mcp_set(write_tool("set_status", {"status": AB}, ["status"]),
                         write_tool("set_other", {"other": AB}, ["other"]), name="built"), ()),
    ],
    ids=["names-its-key", "does-not-name-its-key", "no-output-schema", "field-only-the-key",
         "no-field-fits", "boolean-write", "list-write", "read-with-no-key", "no-read"],
)
def test_baddata_needs_a_carrier_and_level_1_needs_a_named_key(toolset: Any, reach: tuple[int, ...]) -> None:
    """Section 5.2 on the fewest tools: a write with a checkable scalar argument, and a keyed read
    whose answer has a field for it other than its keys; the same read naming its key for level 1."""
    assert generator().knob_levels(toolset(), "baddata") == reach


def test_generation_at_a_level_the_set_does_not_reach_is_refused_naming_its_levels() -> None:
    """The control is level 2 on the same set and seed."""
    own_task("petstore", "baddata", 2, 404)
    with pytest.raises(ValueError) as refused:
        own_task("petstore", "baddata", 1, 404)
    said = str(refused.value)
    assert "\n" not in said and all(digit in said for digit in "023"), said
    with pytest.raises(ValueError):
        own_task("acme-mcp", "lagged", 0, 404)
    with pytest.raises(ValueError):
        own_task("acme-mcp", "lagged", 1, 404)


NO_CARRIER = json.dumps({"tools": [
    write_tool("set_flag", {"flag": {"type": "boolean"}}, ["flag"]),
    read_tool("look", {"key": S12}, ["key"]),
]}).encode()
SAYS = {
    "mcp-everything-tools-list.json": {"LAGGED_NEEDS_A_SHOWING_READ"},
    "acme-mcp-tools-list.json": {"LAGGED_NEEDS_A_SHOWING_READ"},
    "petstore-openapi-3.0.json": {"BADDATA_NEEDS_A_NAMED_KEY"},
    "no-carrier": {"BADDATA_NEEDS_A_CARRIER", "LAGGED_NEEDS_A_SHOWING_READ"},
}


@pytest.mark.parametrize("name", list(SAYS))
def test_init_and_doctor_say_each_sentence_word_for_word_and_doctor_json_carries_it(
    name: str, work: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """`init` as a warning line; `doctor` as a note row under its own label, not a knob's name;
    `doctor --json` under the same label in its checks.  A set that does not lack it says nothing of
    it: each file is held to its own sentences and to the other sentences' absence."""
    (work / "tools.json").write_bytes(NO_CARRIER if name == "no-carrier" else fixture(name))
    made = invoke(["init", *QUIET, "--own-file", "tools.json"], monkeypatch)
    assert made.code == 0, made
    doctor = invoke(["doctor", "--offline"], monkeypatch)
    _ran, document = invoke_json(["doctor", "--offline"], monkeypatch)
    checks = data_of(document)["checks"]
    for constant, (row, sentence) in NEEDS.items():
        assert needs(constant) == sentence
        expected = constant in SAYS[name]
        assert (sentence in made.said) is expected, (name, constant, made.said)
        assert (sentence in doctor.said) is expected, (name, constant, doctor.said)
        assert (row in checks) is expected, (name, row, list(checks))
        if expected:
            assert sentence in checks[row]["text"] and checks[row]["status"] == "note", checks[row]
            lines = [text for text in doctor.said.splitlines() if text.split()[:2] == row.split()]
            assert len(lines) == 1 and sentence in lines[0], (row, doctor.said)


# --------------------------------------------------------------------------
# lagged (BD.15)
# --------------------------------------------------------------------------


def lag_calls(bundle: Any) -> tuple[tuple[str, dict[str, Any]], tuple[str, dict[str, Any]]]:
    """The write and the read of a `lagged` task's reference."""
    write, read = bundle.reference_calls[:2]
    return (write[0], dict(write[1])), (read[0], dict(read[1]))


def shows(answer: Any, write: tuple[str, dict[str, Any]], keys: set[str]) -> list[str]:
    """The non-key arguments of the write the answer holds, under their names."""
    sim = simulator()
    return [name for name, value in write[1].items()
            if name not in keys and name in answer and sim.same(answer[name], value)]


@pytest.mark.parametrize("level", [0, 1])
def test_the_built_in_tasks_and_a_settings_file_refuse_lagged_in_one_line_naming_own_tools(
    level: int, tmp_path: Path
) -> None:
    """The control is `baddata` at the same seed and level, which both take."""
    from tests.test_f2_card_and_experimental import planned_arms

    generate(arm_from_id(f"baddata:b{level}"), 404)
    planned_arms('preset = "custom"\nknob = "baddata"', tmp_path)
    with pytest.raises(ValueError) as refused:
        generate(arm_from_id(f"lagged:g{level}"), 404)
    said = str(refused.value)
    assert "\n" not in said and "own tools" in said, said
    with pytest.raises(config.ConfigError) as settings:
        planned_arms('preset = "custom"\nknob = "lagged"', tmp_path)
    words = str(settings.value)
    assert settings.value.key == "measure.knob"
    assert "\n" not in words and "own tools" in words, words


@pytest.mark.parametrize("toolset, reach", [
    (lambda: named_set(obj(item_id=S12, status=AB)), (0, 1)),
    (lambda: named_set(None), (0, 1)),
    (lambda: named_set(obj(item_id=S12, label=S12)), ()),
    (lambda: mcp_set(write_tool("set_status", {"item_id": S12, "status": AB}, ["item_id", "status"]),
                     read_tool("look", {"item_id": S12, "page": COUNT}, ["item_id", "page"]),
                     name="built"), ()),
    (lambda: mcp_set(write_tool("set_status", {"item_id": S12, "status": AB}, ["item_id", "status"]),
                     read_tool("look", {"key": S12}, ["key"]), name="built"), ()),
], ids=["shows-another-argument", "no-output-schema", "shows-only-its-key", "requires-more",
        "shares-no-argument"])
def test_lagged_needs_a_read_that_takes_an_argument_and_shows_another(
    toolset: Any, reach: tuple[int, ...]
) -> None:
    """Section 5.2 on the fewest tools."""
    assert generator().knob_levels(toolset(), "lagged") == reach


@pytest.mark.parametrize("label", LAGGED_SETS)
def test_the_first_reflecting_read_answers_as_if_unwritten_and_the_next_shows_the_write(label: str) -> None:
    """Shape 2, at the own seeds and forty more, since a drawn value may not show: the reference is
    the write and one read at level 0, and two at level 1; level 1's first read after the write is,
    byte for byte, the read before any write, under the asked key where it has a place for it; the
    next shows a non-key argument of the write and differs; both levels share the task."""
    sim = simulator()
    for seed in LAG_SEEDS:
        zero = own_task(label, "lagged", 0, seed)
        one = own_task(label, "lagged", 1, seed)
        assert (zero.request, zero.target_tool, zero.stated) == (one.request, one.target_tool, one.stated)
        write, read = lag_calls(one)
        assert list(one.reference_calls) == [write, read, read], (label, seed)
        assert list(zero.reference_calls) == [write, read], (label, seed)
        keys = set(read[1])
        assert keys and all(sim.same(write[1][key], value) for key, value in read[1].items())
        before = answers_of(one, [read])[0]
        _written, lagging, after, later = answers_of(one, [write, read, read, read])
        assert lagging == before, (label, seed)
        assert shows(after, write, keys), (label, seed, write, after)
        assert lagging != after and after == later, (label, seed)
        for key in keys:
            if echoes(one, read[0], key):
                assert lagging[key] == read[1][key], (label, seed, key)
        assert answers_of(zero, [write, read])[1] == after, (label, seed)


@pytest.mark.parametrize("label", LAGGED_SETS)
def test_a_read_before_any_write_answers_as_level_0s_and_does_not_use_up_the_lag(label: str) -> None:
    for seed in OWN_SEEDS:
        zero = own_task(label, "lagged", 0, seed)
        one = own_task(label, "lagged", 1, seed)
        write, read = lag_calls(one)
        early = answers_of(one, [read])[0]
        assert early == answers_of(zero, [read])[0], (label, seed)
        _early, _written, lagging, after = answers_of(one, [read, write, read, read])
        assert lagging == early and shows(after, write, set(read[1])), (label, seed)


@pytest.mark.parametrize("label", LAGGED_SETS)
def test_only_one_read_lags_in_an_episode(label: str) -> None:
    """A second write does not arm it again, and a further read keeps showing the write."""
    for seed in OWN_SEEDS:
        one = own_task(label, "lagged", 1, seed)
        write, read = lag_calls(one)
        _w, lagging, after, _w2, again = answers_of(one, [write, read, read, write, read])
        assert lagging != after and again == after, (label, seed)
        _w, first, _w2, second = answers_of(one, [write, read, write, read])
        assert first == lagging and second == after, (label, seed)


@pytest.mark.parametrize("label", LAGGED_SETS)
def test_lagged_passes_on_the_reference_and_write_read_write_is_a_duplicate(
    label: str, tmp_path: Path
) -> None:
    """By real `own.verify`: the reference passes, strict and leaky, in 3 and 4 turns.
    Write-read-write is `collateral_mutation`, leaky true (leaky does not catch it), and the record's
    `duplicate_write` is true where the reference's is false.  The clause is at both levels, in place
    of the unavailable clause; the plan is empty, the level being read from the arm id."""
    toolset = fixture_sets()[label]
    today = own_made(toolset, "faults", 0, 404).system_prompt
    for seed in OWN_SEEDS:
        for level in (0, 1):
            bundle = own_task(label, "lagged", level, seed)
            assert bundle.system_prompt == today.replace(OWN_CLAUSE_TODAY, OWN_CLAUSE_LAGGED)
            assert bundle.fault_plan == {}, (label, seed, level)
            assert judge(bundle, list(bundle.reference_calls)).strict_label == "passed"
            leaky = own_task(label, "lagged", level, seed, strictness="leaky")
            assert judge(leaky, list(leaky.reference_calls)).leaky_pass is True
            assert own_arm("lagged", level).reference_turns == len(bundle.reference_calls) + 1
        one = own_task(label, "lagged", 1, seed)
        write, read = lag_calls(one)
        got = judge(one, [write, read, write])
        assert (got.strict_label, got.leaky_pass) == ("collateral_mutation", True), (label, seed, got)
        twice = own_record(tmp_path / f"twice-{seed}", one, [write, read, write])
        once = own_record(tmp_path / f"once-{seed}", one, list(one.reference_calls))
        assert field(twice, DUPLICATE) is True and written(twice)[DUPLICATE] is True
        assert field(once, DUPLICATE) is False and once.label == "passed"


# --------------------------------------------------------------------------
# landed's check read (BD.19)
# --------------------------------------------------------------------------

# Measured on `main` at `acc3144`: what `landed` draws on acme at the own seeds, which Q14 leaves.
ACME_DRAWS = {
    "acme-mcp": {404: "refund_order", 55: "notify_customer", 2121: "refund_order"},
    "acme-openai": {404: "notify_customer", 55: "refund_order", 2121: "notify_customer"},
    "acme-openapi-3.0": {404: "refund_order", 55: "notify_customer", 2121: "refund_order"},
}


def test_landed_on_petstore_draws_no_write_its_check_read_cannot_show() -> None:
    """Over two hundred seeds, the two the spec measured among them (on `main`, 55 draws `deleteOrder`
    and 2121 `deletePet`, and their check reads answer the same before and after): neither is drawn."""
    for seed in (*OWN_SEEDS, *range(200)):
        drawn = own_made(fixture_sets()["petstore"], "landed", 1, seed).target_tool
        assert drawn not in {"deleteOrder", "deletePet"}, (seed, drawn)


@pytest.mark.parametrize("label", list(ACME_DRAWS))
def test_landed_on_acme_draws_as_it_did(label: str) -> None:
    """The key counts as a thing the answer can show, which keeps acme.  Paired with the narrowing:
    the rule is what moves, and it must move petstore's and not these (their digests are
    `tests/test_f2_kept.py`'s).  The private name is read for what it holds, the rule's result."""
    toolset = fixture_sets()[label]
    assert {t.name for t in generator()._landed_targets(toolset)} == {"refund_order", "notify_customer"}
    assert generator().knob_levels(fixture_sets()["petstore"], "landed") == (0, 1)
    names = {t.name for t in generator()._landed_targets(fixture_sets()["petstore"])}
    assert "deleteOrder" not in names and "deletePet" not in names, names
    for seed, wanted in ACME_DRAWS[label].items():
        assert own_made(toolset, "landed", 1, seed).target_tool == wanted, (label, seed)


def test_landed_keeps_a_write_only_with_a_read_whose_answer_can_show_one_of_its_arguments() -> None:
    """Section 5.4 on the fewest tools: an answer that holds the key, and one with no output schema,
    can show; one that holds nothing of the write cannot, though the read takes the write's key, and
    on `main` that set reached `landed`."""
    reach = generator().knob_levels
    assert reach(named_set(obj(item_id=S12, size=COUNT)), "landed") == (0, 1)
    assert reach(named_set(None), "landed") == (0, 1)
    assert reach(named_set(obj(size=COUNT)), "landed") == ()


@pytest.mark.parametrize("level", ABOVE_ZERO)
def test_a_seeds_read_can_name_its_key_where_the_set_has_such_a_read(level: int) -> None:
    """Section 1.3: the draw is from the pairs whose read can name its key where the set has any, at
    every level.  On a set with one read that can and one that cannot, the task uses the one that
    can, at every seed."""
    toolset = mcp_set(
        write_tool("set_status", {"status": AB}, ["status"]),
        read_tool("get_quiet", {"key": S12}, ["key"], output=obj(status=AB)),
        read_tool("get_named", {"key": S12}, ["key"], output=obj(key=S12, status=AB)),
        name="built",
    )
    for seed in range(12):
        assert carried(own_task(toolset, "baddata", level, seed)).read[0] == "get_named", seed
