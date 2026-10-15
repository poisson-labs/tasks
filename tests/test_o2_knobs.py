"""The knobs on a user's own tools, frozen as tests.

The invariant is O2.4 of the knobs plan (spec §6): each knob of §6.1 applies as written, within
the set's limits; depth and shape are offered only with flows, and refused with the spec's
sentence without them.  And §6.3 as Taylor ruled it on 2026-10-13 23:26 (a recorded
retrofit of this file after the freeze, O2 Session B1's second follow-up): every knob stays
available on own tools in launch one, and the sentence that a knob which did not ship is not offered
is withdrawn; the recipes still lead with the knobs that shipped, read from `arms.SHIPPED_KNOBS`
whatever that list holds.

Shapes decided here
-------------------

**1. `generator.KNOBS`** is §6.1's knobs that have levels, in the table's order: similarity,
faults, history, block, arguments, spread, depth, shape.  Every one the set reaches is offered on own
tools (`recipes.offered_knobs`); the ones that shipped lead the recipes (`recipes.shipped_knobs`).  Cost and time is on every card and is
no knob.  `knob_levels(toolset, knob, *, flows=())` is the levels this set reaches, empty where
it reaches none; `generate` refuses any other level in one line (`ValueError`), and refuses depth
and shape without flows with `UNAVAILABLE_WITHOUT_FLOWS`, §6.2's sentence, in its line.

**2. Single factor.**  For one seed, the levels of a knob share the target tool and the values
the request states, except where the knob itself is the values (arguments) or carries the target
value through reads (spread) or a chain (depth).  On the knobs whose task is one call to a target
(similarity, faults, history, block) the target is drawn per seed from the set's writes that can
be a target, and the level does not enter the draw.  `OwnBundle.target` is the target as the block
shows it and `OwnBundle.target_tool` its name in the set.

**3. Similarity** shows the target and six copies of it, each taking its arguments and each
carrying a four-digit number in its name or description: the numbers are `surface.target_number`
and `surface.lookalike_numbers` (the knobs spec's ledger numbers), each copy's sharing exactly
`level` digits in place with the target's, and the request names the target's number and no
copy's.  How a copy is named and described is the pending file
`test_o2_pending_similarity_names.py`.

**4. Faults** plans `surface.fault_plan(arm id, the reference's tools)`'s failures; the reference
makes each planned call again until it works.

**5. History** seeds, after the request, calls to the set's read tools with their simulated
answers, counted per pair as the built-in knob counts them (`pair_tokens`: the name, the
arguments as compact JSON, the answer, each in the reference tokenizer); how many pairs is the
pending file `test_o2_pending_history_total.py`.

**6. Block** offers, at level k, k tools of the set, the target among them, and nothing else;
its levels are those of 8, 16, 32 and 64 the set reaches, and a block is the next level's first
tools.  What every other arm offers is the pending file `test_o2_pending_base_block.py`.

**7. Spread** splits the target value over the answers of named reads, `level` of them holding a
part, in order; level 1 is spec §5.1's "read then call".  How many reads, what the others hold and
which reads count are the pending file `test_o2_pending_spread_reads.py`.

**8. Depth** follows the longest declared chain that ends at a write that can be a target: level d
is its last d calls, each call's linked argument carrying the value the call before it was
answered with in the linked field.
"""

from __future__ import annotations

import itertools
import json
import re
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest

from poisson_tasks import arms as arms_module
from poisson_tasks import knobs, surface
from poisson_tasks.tokenizer import count_tokens
from tests.o2_support import (
    KNOBS,
    acme,
    answers,
    acme_flows,
    arm,
    fixture_sets,
    flows_for,
    generator,
    judge,
    make,
    mcp_set,
    names,
    petstore,
    read_tool,
    recipes,
    simulator,
    wide_set,
    write_tool,
)


def target_call(bundle: Any) -> tuple[str, dict[str, Any]]:
    calls = [c for c in bundle.reference_calls if c[0] == bundle.target]
    return (str(calls[-1][0]), dict(calls[-1][1]))


def unavailable(bundle: Any, answer: Any) -> bool:
    """Whether an answer is a planned failure, read in the set's own error idiom."""
    if bundle.source_format == "mcp":
        return bool(answer.is_error)
    body = json.loads(answer.text)
    if bundle.source_format == "openai":
        return isinstance(body, dict) and body.get("error", {}).get("code") == "unavailable"
    return isinstance(body, dict) and body.get("status") == 503


def field_value(answer_text: str, path: str) -> Any:
    node: Any = json.loads(answer_text)
    for part in path.split("."):
        node = node[part.removesuffix("[]")]
        if part.endswith("[]"):
            node = node[0]
    return node


# --------------------------------------------------------------------------
# the knobs, the levels and the refusals
# --------------------------------------------------------------------------


def test_the_knobs_are_spec_6_1s_with_levels() -> None:
    assert generator().KNOBS == KNOBS


@pytest.mark.parametrize("label", ["acme-mcp", "acme-openai", "petstore", "everything"])
def test_a_level_past_what_the_set_reaches_is_refused_and_every_level_it_reaches_is_built(label: str) -> None:
    """Every level `knob_levels` gives is built; a level past its last, and a card level past what
    the set reaches, is refused.  Whether a level between two of a knob's card levels is taken is
    the pending file `test_o2_pending_card_levels.py`."""
    toolset = fixture_sets()[label]
    flows = flows_for(label)
    gen = generator()
    for knob in KNOBS:
        found = gen.knob_levels(toolset, knob, flows=flows)
        past = [level for level in knobs.levels(knob) if not found or level > found[-1]]
        if found:
            past.append(found[-1] + 1)
        for level in found:
            assert gen.generate(toolset, arm(knob, level), 3, flows=flows).arm_id == knobs.arm_id(arm(knob, level))
        for level in past:
            try:
                spec = arm(knob, level)
            except ValueError:
                continue
            with pytest.raises(ValueError):
                gen.generate(toolset, spec, 3, flows=flows)


def test_a_knob_that_is_not_on_own_tools_is_refused() -> None:
    from poisson_tasks.arms import arm_from_id

    spec = arm_from_id("distractor:r2@k16", generator_version="own-1")
    with pytest.raises(ValueError):
        generator().generate(acme(), spec, 1)
    with pytest.raises(ValueError):
        generator().knob_levels(acme(), "distractor")


def test_a_set_with_no_write_a_task_can_target_has_no_levels() -> None:
    """Spec §3: a task's target is a write with an argument Tasks can check.  A set of reads and a
    write taking only free text reaches no level of any knob; the same set with a checkable write
    reaches some."""
    reads = (read_tool("look_case", {"code": {"type": "string", "minLength": 8, "maxLength": 8}}, ["code"]),
             read_tool("list_all", {}))
    untargetable = mcp_set(write_tool("add_note", {"text": {"type": "string"}}, ["text"]), *reads)
    for knob in KNOBS:
        assert generator().knob_levels(untargetable, knob) == (), knob
    targetable = mcp_set(write_tool("open_case", {"code": {"type": "string", "minLength": 8, "maxLength": 8}},
                                    ["code"]), *reads)
    assert any(generator().knob_levels(targetable, knob) for knob in KNOBS)


def test_depth_and_shape_need_flows_and_are_refused_with_the_specs_sentence_without_them() -> None:
    gen = generator()
    assert gen.UNAVAILABLE_WITHOUT_FLOWS == (
        "Depth and shape need the model to carry a value from one tool's output into another's "
        "input in a way that makes sense for your domain. Tasks will not guess that."
    )
    for knob in ("depth", "shape"):
        assert gen.knob_levels(acme(), knob) == ()
        assert gen.knob_levels(acme(), knob, flows=acme_flows()) != ()
        level = 2 if knob == "depth" else 1
        with pytest.raises(ValueError) as refused:
            gen.generate(acme(), arm(knob, level), 1)
        assert gen.UNAVAILABLE_WITHOUT_FLOWS in str(refused.value)
        assert "\n" not in str(refused.value)


@pytest.mark.parametrize(
    "flow, ok",
    [
        (("search_orders", "orders[].order_id", "get_order", "order_id"), True),
        (("get_order", "order_id", "refund_order", "order_id"), True),
        (("no_such_tool", "order_id", "refund_order", "order_id"), False),
        (("get_order", "order_id", "no_such_tool", "order_id"), False),
        (("get_order", "no_such_field", "refund_order", "order_id"), False),
        (("search_orders", "orders.order_id", "get_order", "order_id"), False),
        (("get_order", "order_id", "refund_order", "no_such_param"), False),
        (("notify_customer", "note", "refund_order", "order_id"), False),
        (("notify_customer", "id", "refund_order", "order_id"), True),
    ],
    ids=["array-path", "plain-path", "unknown-from", "unknown-to", "unknown-field",
         "array-not-marked", "unknown-param", "no-output-not-id", "no-output-id"],
)
def test_a_flow_names_a_path_in_the_from_tools_output_and_an_argument_of_the_to_tool(
    flow: tuple[str, str, str, str], ok: bool
) -> None:
    gen = generator()
    declared = (gen.Flow(*flow),)
    if ok:
        gen.check_flows(acme(), declared)
    else:
        with pytest.raises(ValueError):
            gen.check_flows(acme(), declared)



# --------------------------------------------------------------------------
# what is offered follows the probe
# --------------------------------------------------------------------------

SHIPPABLE = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")
SHIPPED_CASES = [(), *[(knob,) for knob in SHIPPABLE], SHIPPABLE]


@pytest.mark.parametrize("shipped", SHIPPED_CASES, ids=lambda s: "+".join(s) or "none")
@pytest.mark.parametrize("label", ["acme-mcp", "petstore", "everything"])
def test_every_knob_the_set_reaches_is_offered_on_own_tools_whatever_shipped(
    label: str, shipped: tuple[str, ...]
) -> None:
    """Retrofitted 2026-10-14 under Taylor's ruling of 2026-10-13 23:26: this test held the offer to
    depth and the shipped knobs; every knob the set reaches is offered, whatever shipped."""
    toolset = fixture_sets()[label]
    flows = flows_for(label)
    gen, rec = generator(), recipes()
    expected = tuple(knob for knob in KNOBS if gen.knob_levels(toolset, knob, flows=flows))
    assert rec.offered_knobs(toolset, flows=flows, shipped=shipped) == expected


@pytest.mark.parametrize("shipped", [(), ("faults",), SHIPPABLE], ids=["none", "faults", "all"])
def test_the_default_reads_arms_shipped_knobs_whatever_it_holds(
    shipped: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A guard for the ruling of 2026-10-13: with no list given, what is offered is read from
    `arms.SHIPPED_KNOBS` when asked, whatever it holds then."""
    monkeypatch.setattr(arms_module, "SHIPPED_KNOBS", shipped)
    rec = recipes()
    for label in ("acme-mcp", "petstore"):
        toolset, flows = fixture_sets()[label], flows_for(label)
        assert rec.offered_knobs(toolset, flows=flows) == rec.offered_knobs(
            toolset, flows=flows, shipped=shipped)
        assert dict(rec.recipes_for(toolset, flows=flows)) == dict(
            rec.recipes_for(toolset, flows=flows, shipped=shipped))


@pytest.mark.parametrize("shipped", SHIPPED_CASES, ids=lambda s: "+".join(s) or "none")
@pytest.mark.parametrize("label", ["acme-mcp", "acme-openai", "petstore"])
def test_the_recipes_on_own_tools_are_those_whose_knobs_work_on_the_set(
    label: str, shipped: tuple[str, ...]
) -> None:
    """Knobs spec §17.4: on your own tools the list shows only the recipes whose knobs work on that
    set.  As a built-in recipe that mixes a shipped and an unshipped knob drops the unshipped arms
    (§17.2), a recipe is offered here when one of its knobs is offered on the set, and runs arms of
    those knobs only, at levels the set reaches, every such knob with at least one.  Which levels is
    the pending file `test_o2_pending_recipe_levels.py`; the `card` recipe is
    `test_o2_pending_recipe_card.py`'s."""
    toolset, flows = fixture_sets()[label], flows_for(label)
    gen, rec = generator(), recipes()
    # Retrofitted 2026-10-14 (the ruling of 2026-10-13 23:26): the recipes lead with the knobs that
    # shipped and the set reaches, `shipped_knobs`, while `offered_knobs` is every knob it reaches.
    offered = rec.shipped_knobs(toolset, flows=flows, shipped=shipped)
    table = rec.recipes_for(toolset, flows=flows, shipped=shipped)
    built_in = arms_module.recipe_table(SHIPPABLE)
    assert list(table) == list(arms_module.RECIPES)
    for name, recipe in table.items():
        if name == "card":
            continue
        mine = [knob for knob in built_in[name].knobs if knob in offered]
        assert recipe.offered == bool(mine), name
        used = [arms_module.arm_from_id(a, generator_version="own-1") for a in recipe.arms]
        assert {spec.knob for spec in used} == set(mine), name
        for spec in used:
            assert spec.level in gen.knob_levels(toolset, spec.knob, flows=flows), (name, spec)
        assert (recipe.tasks_per_level, recipe.attempts) == (
            built_in[name].tasks_per_level, built_in[name].attempts)


# --------------------------------------------------------------------------
# single factor
# --------------------------------------------------------------------------


@pytest.mark.parametrize("knob", ["similarity", "faults", "history", "block"])
def test_across_a_knobs_levels_the_target_and_the_stated_values_stay_put(knob: str) -> None:
    toolset = petstore()
    gen = generator()
    for seed in range(12):
        bundles = [gen.generate(toolset, arm(knob, level), seed)
                   for level in gen.knob_levels(toolset, knob)]
        assert len(bundles) > 1
        originals = {b.target_tool for b in bundles}
        assert len(originals) == 1, (knob, seed, originals)
        assert len({json.dumps(b.stated, sort_keys=True) for b in bundles}) == 1, (knob, seed)
        assert len({b.system_prompt for b in bundles}) == 1


def test_the_target_is_drawn_per_seed_from_the_writes_that_can_be_a_target() -> None:
    toolset = petstore()
    gen = generator()
    from poisson_tasks import own

    targets = {tool.name for tool in toolset.tools if own.is_write(tool) and own.can_target(tool)}
    drawn = {gen.generate(toolset, arm("faults", 0), seed).target for seed in range(60)}
    assert drawn <= targets and len(drawn) > 1


# --------------------------------------------------------------------------
# similarity
# --------------------------------------------------------------------------


@pytest.mark.parametrize("level", [0, 1, 2, 3])
def test_similarity_shows_the_target_and_six_numbered_copies_sharing_level_digits(level: int) -> None:
    toolset = acme()
    for seed in range(20):
        bundle = make(toolset, "similarity", level, seed=seed)
        source = next(t for t in toolset.tools if t.name == bundle.target_tool)
        target_number = surface.target_number(seed, "eval")
        copies = surface.lookalike_numbers(seed, "eval", level)
        added = [t for t in bundle.tools if str(t["name"]) not in {x.name for x in toolset.tools}]
        assert bundle.target in {str(t["name"]) for t in added} and len(added) == 7
        found = []
        for tool in added:
            numbers = set(re.findall(r"(?<!\d)\d{4}(?!\d)", f"{tool['name']} {tool['description']}"))
            assert len(numbers) == 1, tool
            found.append(numbers.pop())
            assert tool["parameters"] == source.input_schema
        assert sorted(found) == sorted((target_number, *copies))
        for number in copies:
            assert sum(a == b for a, b in zip(number, target_number, strict=True)) == level
        assert target_number in bundle.request
        assert not any(number in bundle.request for number in copies)


def test_a_write_to_a_copy_is_a_side_effect_and_leaves_the_goal_short() -> None:
    bundle = make(acme(), "similarity", 3, seed=4)
    control = bundle.negative_controls["collateral_mutation_lookalike"]
    assert judge(bundle, control).strict_label == "collateral_mutation"
    copy_name, copy_args = control[-1]
    instead = tuple((copy_name, copy_args) if c[0] == bundle.target else c for c in bundle.reference_calls)
    found = judge(bundle, instead)
    assert (found.strict_label, found.leaky_pass) == ("wrong_state", False)


# --------------------------------------------------------------------------
# faults
# --------------------------------------------------------------------------


@pytest.mark.parametrize("level", [0, 1, 2, 4])
def test_faults_plans_surfaces_failures_and_the_reference_makes_the_call_again(level: int) -> None:
    for label in ("acme-mcp", "petstore"):
        toolset = fixture_sets()[label]
        for seed in range(10):
            bundle = make(toolset, "faults", level, seed=seed)
            path = tuple(dict.fromkeys(name for name, _args in bundle.reference_calls))
            assert bundle.fault_plan == surface.fault_plan(bundle.arm_id, path)
            assert sum(bundle.fault_plan.values()) == level
            for name in path:
                made = [c for c in bundle.reference_calls if c[0] == name]
                assert len(made) == bundle.fault_plan.get(name, 0) + 1
                assert len({json.dumps(args, sort_keys=True) for _n, args in made}) == 1
            replies = answers(bundle, bundle.reference_calls)
            assert [r.text for r in replies] == list(bundle.reference_observations)
            assert sum(unavailable(bundle, r) for r in replies) == level, (label, seed)
            assert not unavailable(bundle, replies[-1])


# --------------------------------------------------------------------------
# history
# --------------------------------------------------------------------------


@pytest.mark.parametrize("level", [0, 300, 600, 1200, 2400])
def test_history_seeds_simulated_calls_to_the_sets_reads_after_the_request(level: int) -> None:
    toolset = acme()
    reads = {t.name for t in toolset.tools if t.effect == "read"}
    sim, gen = simulator(), generator()
    for seed in range(5):
        bundle = make(toolset, "history", level, seed=seed)
        if level == 0:
            assert bundle.prompt == bundle.request
            continue
        first, *rest = bundle.prompt
        assert first == {"role": "user", "content": bundle.request}
        assert len(rest) % 2 == 0 and rest
        total = 0
        for call, result in zip(rest[0::2], rest[1::2], strict=True):
            (made,) = call["tool_calls"]
            assert call["role"] == "assistant" and result["role"] == "tool"
            assert result["tool_call_id"] == made["id"]
            name, args = made["function"]["name"], json.loads(made["function"]["arguments"])
            assert name in reads
            source = next(t for t in toolset.tools if t.name == name)
            assert jsonschema.Draft202012Validator(source.input_schema).is_valid(args)
            expected = sim.success(toolset.source_format, source, sim.respond(
                source, args, digest=toolset.file_digest, seed=seed, split="eval")).text
            assert result["content"] == expected
            total += gen.pair_tokens(name, args, result["content"])
        assert total >= level


def test_pair_tokens_counts_as_the_built_in_knob_does() -> None:
    args = {"order_id": "A-3317"}
    answer = '{"order_id":"A-3317","status":"open","total":12.5}'
    assert generator().pair_tokens("get_order", args, answer) == (
        count_tokens("get_order") + count_tokens(json.dumps(args, separators=(",", ":")))
        + count_tokens(answer))


def test_history_needs_a_read_tool() -> None:
    writes_only = mcp_set(
        write_tool("open_case", {"kind": {"type": "string", "enum": ["a", "b"]}}, ["kind"]),
        write_tool("close_case", {"kind": {"type": "string", "enum": ["a", "b"]}}, ["kind"]),
    )
    assert generator().knob_levels(writes_only, "history") == ()
    assert generator().knob_levels(writes_only, "faults") == knobs.levels("faults")


# --------------------------------------------------------------------------
# block
# --------------------------------------------------------------------------


@pytest.mark.parametrize("size, levels", [(64, (8, 16, 32, 64)), (40, (8, 16, 32)), (20, (8, 16)),
                                          (8, (8,)), (7, ())])
def test_block_levels_are_those_of_8_16_32_64_the_set_reaches(size: int, levels: tuple[int, ...]) -> None:
    assert generator().knob_levels(wide_set(size), "block") == levels


def test_a_block_offers_level_many_of_the_sets_own_tools_the_target_among_them_and_grows_by_adding() -> None:
    toolset = wide_set(64)
    schemas = {t.name: t.input_schema for t in toolset.tools}
    for seed in range(15):
        blocks = []
        for level in (8, 16, 32, 64):
            bundle = make(toolset, "block", level, seed=seed)
            shown = names(bundle)
            assert len(shown) == len(set(shown)) == level
            assert bundle.target in shown
            assert all(str(t["name"]) in schemas and t["parameters"] == schemas[str(t["name"])]
                       for t in bundle.tools)
            blocks.append(set(shown))
        assert blocks[0] < blocks[1] < blocks[2] < blocks[3]


# --------------------------------------------------------------------------
# arguments
# --------------------------------------------------------------------------


def test_the_arguments_level_is_how_many_of_the_targets_arguments_the_request_states() -> None:
    toolset = petstore()
    gen = generator()
    found = gen.knob_levels(toolset, "arguments")
    assert found
    for seed in range(10):
        for level in found:
            bundle = gen.generate(toolset, arm("arguments", level), seed)
            stated = dict(bundle.stated)
            assert len(stated) == level
            tool, args = target_call(bundle)
            assert all(args[name] == value for name, value in stated.items())
            for name in stated:
                moved = tuple((t, {**a, name: "QQQQQQQQ" if not isinstance(a[name], str) else a[name] + "Q"})
                              if t == tool else (t, a) for t, a in bundle.reference_calls)
                assert judge(bundle, moved).strict_label != "passed", (level, name)
        assert len({gen.generate(toolset, arm("arguments", level), seed).target for level in found}) == 1


# --------------------------------------------------------------------------
# spread
# --------------------------------------------------------------------------


@pytest.mark.parametrize("level", [1, 2, 4])
def test_spread_splits_the_target_value_across_level_of_the_named_reads_answers(level: int) -> None:
    for label in ("acme-mcp", "acme-openai", "petstore"):
        toolset = fixture_sets()[label]
        for seed in range(10):
            bundle = make(toolset, "spread", level, seed=seed)
            reads = len(bundle.named_reads)
            for (tool_name, read_args, _path), (called, called_args) in zip(
                    bundle.named_reads, bundle.reference_calls, strict=False):
                assert called == tool_name and read_args.items() <= called_args.items()
            values = [field_value(obs, path) for obs, (_t, _a, path) in
                      zip(bundle.reference_observations[:reads], bundle.named_reads, strict=True)]
            _tool, args = target_call(bundle)
            stated = dict(bundle.stated)
            carried = [value for name, value in args.items() if name not in stated]
            joins = [(value, combo) for value in carried for combo in itertools.combinations(range(reads), level)
                     if "".join(str(values[i]) for i in combo) == value]
            assert joins, (label, seed, values, carried)
            if level == 1:
                assert bundle.form == "read then call"


def test_spread_needs_a_read_tool_that_takes_an_argument() -> None:
    write = write_tool("open_case", {"code": {"type": "string", "minLength": 8, "maxLength": 8}}, ["code"])
    no_argument_reads = mcp_set(write, read_tool("list_all", {}), read_tool("list_some", {}))
    assert generator().knob_levels(no_argument_reads, "spread") == ()
    keyed = mcp_set(write, read_tool("list_all", {}),
                    read_tool("look_case", {"code": {"type": "string", "minLength": 8, "maxLength": 8}}, ["code"]))
    assert generator().knob_levels(keyed, "spread") == knobs.levels("spread")


def test_the_target_value_is_not_stated_on_a_spread_arm() -> None:
    bundle = make(acme(), "spread", 2, seed=9)
    _tool, args = target_call(bundle)
    stated = dict(bundle.stated)
    carried = [name for name, value in args.items() if name not in stated]
    assert carried
    for name in carried:
        assert json.dumps(args[name]) not in bundle.request


# --------------------------------------------------------------------------
# depth
# --------------------------------------------------------------------------


def test_depth_follows_the_declared_chain_and_its_levels_reach_its_length() -> None:
    gen = generator()
    flows = acme_flows()
    assert gen.knob_levels(acme(), "depth", flows=flows) == (1, 2, 3)
    assert gen.knob_levels(acme("openai"), "depth", flows=acme_flows("openai")) == (1, 2)
    by_name = {f"{f.from_tool}>{f.to_tool}": f for f in flows}
    for seed in range(10):
        targets = set()
        for level in (1, 2, 3):
            bundle = gen.generate(acme(), arm("depth", level), seed, flows=flows)
            calls = list(bundle.reference_calls)
            assert len(calls) == level
            assert [c[0] for c in calls] == ["search_orders", "get_order", "refund_order"][-level:]
            for (before, after), answer in zip(zip(calls, calls[1:], strict=False),
                                                bundle.reference_observations, strict=False):
                link = by_name[f"{before[0]}>{after[0]}"]
                assert after[1][link.param] == field_value(answer, link.field)
            targets.add(bundle.target)
            assert judge(bundle, calls).strict_label == "passed"
        assert targets == {"refund_order"}


def test_a_chain_step_made_before_its_link_answers_not_ready() -> None:
    bundle = make(acme(), "depth", 3, seed=2, flows=acme_flows())
    last = bundle.reference_calls[-1]
    found = judge(bundle, (last,) + bundle.reference_calls[:-1])
    assert found.strict_label == "wrong_state"
