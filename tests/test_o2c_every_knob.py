"""Every knob on a user's own tools, with the probe's status beside, frozen as tests.

The decision of 2026-10-13 23:26, carried to the own-tools build: every knob stays available on
own tools in launch one.  The own-tools design's sentence "A knob that did not
ship as a difficulty control (it failed its probe) is not offered here either" is withdrawn.  The
knob probe ran on two small models, and every dial is to be revisited in v2 on current models.

Shapes decided here
-------------------

**1. All nine knobs are offered on own tools**, within each set's limits as the earlier decisions
say (depth and shape only with flows, block to the set's size, and so on), whatever
`arms.SHIPPED_KNOBS` holds: `own.recipes.offered_knobs(toolset, flows=...)` is every knob of
`generator.KNOBS` the set reaches, in that order, with or without a `shipped` list given.

**2. Recipes still lead with the knobs that shipped** (as decided): a recipe is
offered when one of its knobs shipped and the set reaches it, and runs arms of those knobs only;
`own.recipes.shipped_knobs(toolset, flows=..., shipped=None)` is that list, read from
`arms.SHIPPED_KNOBS` when none is given, and `default_recipe` is as before.

**3. Each knob carries its measured status on each probe model**, read only from
`poisson_tasks.arms.knob_status()`: `own.card.probe_statuses(knobs)` maps each knob the table
holds to `{model's short name: status}` exactly as the table gives them (bites, does not bite, top
easier, cannot tell), nothing copied, re-derived or hard-coded; a knob the table does not hold
(depth, which the published cards measured) is left out.

**4. The own-tools card states that status beside its own per-set table** (the design's table,
each level against the first, stays exactly as specced): under the table, one line per knob with
its status on each model as the table gives it, and `own.card.PROBE_SENTENCE`, which says plainly
that the probe's statuses come from the built-in tasks on two models while the per-set table is
measured on the user's own tools.  A built-in card carries neither.

What `custom` offers and what `init` leads with on own tools are the settings file's and the
command's (`tests/test_o2d_b2.py`): `custom` offers every knob and `init` leads with the shipped
ones.
"""

from __future__ import annotations

from typing import Any

import pytest

from poisson_tasks import arms as arms_module
from poisson_tasks import calibration as cal
from tests.o2_support import KNOBS, acme_flows, card, fixture_sets, flows_for, generator, recipes
from tests.test_o2_card import artifact, provenance, tools_block

SHIPPABLE = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")
SHIPPED_CASES = [(), ("faults",), ("block",), ("faults", "history", "shape"), SHIPPABLE]
SETS = ["acme-mcp", "acme-openai", "petstore", "everything"]


def reached(label: str) -> tuple[str, ...]:
    toolset, flows = fixture_sets()[label], flows_for(label)
    return tuple(knob for knob in KNOBS if generator().knob_levels(toolset, knob, flows=flows))


# --------------------------------------------------------------------------
# every knob is offered
# --------------------------------------------------------------------------


@pytest.mark.parametrize("shipped", SHIPPED_CASES, ids=lambda s: "+".join(s) or "none")
@pytest.mark.parametrize("label", SETS)
def test_every_knob_the_set_reaches_is_offered_whatever_shipped(
    label: str, shipped: tuple[str, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arms_module, "SHIPPED_KNOBS", shipped)
    toolset, flows = fixture_sets()[label], flows_for(label)
    rec = recipes()
    assert rec.offered_knobs(toolset, flows=flows) == reached(label)
    assert rec.offered_knobs(toolset, flows=flows, shipped=shipped) == reached(label)
    assert rec.offered_knobs(toolset, flows=flows, shipped=()) == reached(label)


def test_the_offer_is_within_each_sets_limits_as_ruled() -> None:
    """The earlier decisions stand: depth and shape only with flows, block to the set's size, spread
    with a keyed read; what a set does not reach is not offered."""
    rec, gen = recipes(), generator()
    acme = fixture_sets()["acme-mcp"]
    assert "depth" not in rec.offered_knobs(acme) and "shape" not in rec.offered_knobs(acme)
    assert {"depth", "shape"} <= set(rec.offered_knobs(acme, flows=acme_flows()))
    assert "block" not in rec.offered_knobs(acme) and "block" in rec.offered_knobs(fixture_sets()["petstore"])
    for label in SETS:
        toolset, flows = fixture_sets()[label], flows_for(label)
        for knob in rec.offered_knobs(toolset, flows=flows):
            assert gen.knob_levels(toolset, knob, flows=flows), (label, knob)


# --------------------------------------------------------------------------
# recipes lead with the shipped knobs, unchanged
# --------------------------------------------------------------------------


@pytest.mark.parametrize("shipped", SHIPPED_CASES, ids=lambda s: "+".join(s) or "none")
@pytest.mark.parametrize("label", ["acme-mcp", "petstore"])
def test_recipes_lead_with_the_shipped_knobs_as_before(label: str, shipped: tuple[str, ...]) -> None:
    toolset, flows = fixture_sets()[label], flows_for(label)
    rec, gen = recipes(), generator()
    lead = tuple(knob for knob in reached(label) if knob == "depth" or knob in shipped)
    assert rec.shipped_knobs(toolset, flows=flows, shipped=shipped) == lead
    table = rec.recipes_for(toolset, flows=flows, shipped=shipped)
    built_in = arms_module.recipe_table(SHIPPABLE)
    assert list(table) == list(arms_module.RECIPES)
    for name, recipe in table.items():
        if name == "card":
            assert not recipe.offered and recipe.arms == ()
            continue
        mine = [knob for knob in built_in[name].knobs if knob in lead]
        assert recipe.offered == bool(mine), name
        used = [arms_module.arm_from_id(a, generator_version="own-1") for a in recipe.arms]
        assert {spec.knob for spec in used} == set(mine), name
        for spec in used:
            assert spec.level in gen.knob_levels(toolset, spec.knob, flows=flows), (name, spec)
    offered = [name for name, recipe in table.items() if recipe.offered]
    expected = "tool-choice" if "tool-choice" in offered else (offered[0] if offered else None)
    assert rec.default_recipe(toolset, flows=flows, shipped=shipped) == expected


def test_the_lead_reads_arms_shipped_knobs_when_none_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = recipes()
    toolset = fixture_sets()["petstore"]
    for shipped in ((), ("block",), ("faults", "history", "shape")):
        monkeypatch.setattr(arms_module, "SHIPPED_KNOBS", shipped)
        assert rec.shipped_knobs(toolset) == rec.shipped_knobs(toolset, shipped=shipped)
        assert dict(rec.recipes_for(toolset)) == dict(rec.recipes_for(toolset, shipped=shipped))
        assert rec.default_recipe(toolset) == rec.default_recipe(toolset, shipped=shipped)
    monkeypatch.setattr(arms_module, "SHIPPED_KNOBS", ("block",))
    assert rec.default_recipe(toolset) == "tool-choice"


# --------------------------------------------------------------------------
# the probe's status, read from the table and nowhere else
# --------------------------------------------------------------------------


def expected_statuses(table: dict[str, Any], knobs: tuple[str, ...]) -> dict[str, dict[str, str]]:
    return {
        knob: {str(table["models"][model]): str(entry["status"])
               for model, entry in table["knobs"][knob]["models"].items()}
        for knob in knobs if knob in table["knobs"]
    }


def test_each_knobs_probe_status_is_the_tables_exactly() -> None:
    table = arms_module.knob_status()
    found = card().probe_statuses(KNOBS)
    assert found == expected_statuses(table, KNOBS)
    assert set(found) == set(table["knobs"]) and "depth" not in found
    assert card().probe_statuses(("depth",)) == {}
    assert card().probe_statuses(("faults",)) == {"faults": found["faults"]}
    statuses = {status for by_model in found.values() for status in by_model.values()}
    assert statuses <= {"bites", "does not bite", "top easier", "cannot tell"}


def test_the_status_follows_the_table_and_is_not_copied(monkeypatch: pytest.MonkeyPatch) -> None:
    """A guard for the decision's "read only from knob_status()": another table, another answer."""
    table = arms_module.knob_status()
    moved: dict[str, Any] = {
        "models": {"m-one@r": "one", "m-two@r": "two"},
        "knobs": {knob: {"shipped": False, "models": {
            "m-one@r": {"status": "cannot tell"}, "m-two@r": {"status": "top easier"}}}
            for knob in table["knobs"]},
    }
    monkeypatch.setattr(arms_module, "knob_status", lambda: moved)
    found = card().probe_statuses(KNOBS)
    assert found == {knob: {"one": "cannot tell", "two": "top easier"} for knob in table["knobs"]}
    document = cal.render_document(artifact({"faults:f0": 0.8, "faults:f2": 0.5}), claims=True)
    assert "cannot tell on one" in document and "top easier on two" in document


# --------------------------------------------------------------------------
# the card: the per-set table as specced, the probe's statuses beside it
# --------------------------------------------------------------------------


def status_lines(document: str) -> dict[str, str]:
    """The probe-status lines of a card, by knob."""
    out: dict[str, str] = {}
    for line in document.splitlines():
        for knob in KNOBS:
            if line.startswith(f"- {knob}:") and " on " in line:
                out[knob] = line
    return out


def test_the_own_card_states_the_probes_statuses_beside_its_own_table() -> None:
    rates = {"faults:f0": 0.9, "faults:f2": 0.4, "similarity:s0": 0.8, "similarity:s3": 0.7,
             "depth:d1": 0.9, "depth:d3": 0.5}
    own_artifact = artifact(rates, seeds=20)
    document = cal.render_document(own_artifact, claims=True)
    sentence = card().PROBE_SENTENCE
    assert sentence in document and "\n" not in sentence
    assert "built-in tasks on two models" in sentence and "measured on your own tools" in sentence
    table = arms_module.knob_status()
    lines = status_lines(document)
    for knob in ("faults", "similarity"):
        for model, entry in table["knobs"][knob]["models"].items():
            assert f"{entry['status']} on {table['models'][model]}" in lines[knob], (knob, lines)
    assert "depth" in lines and "published cards" in lines["depth"]
    # the design's table stays exactly as specced: each level against the first, strict, unchanged
    cells: dict[tuple[str, str], list[Any]] = {}
    rows = card().rows_from_artifact(own_artifact)
    assert [(r.knob, r.level, r.first, r.predicate) for r in rows] == [
        ("similarity", 3, 0, "strict"), ("faults", 2, 0, "strict"), ("depth", 3, 1, "strict")]
    said = card().bite(rows)
    assert set(said) == {"similarity", "faults", "depth"} and all(line in document for line in said.values())
    # the statuses come after the per-set table and its sentences, not in them
    assert document.index(sentence) > document.index("## Each level against the first")
    assert all(document.index(line) < document.index(sentence) for line in said.values())
    del cells


def test_a_built_in_card_carries_no_probe_status_lines() -> None:
    built_in = cal.render_document(artifact({"depth:d1": 0.9, "depth:d2": 0.6}, tools=None), claims=True)
    assert card().PROBE_SENTENCE not in built_in and status_lines(built_in) == {}
    prov = provenance(tools=tools_block())
    assert prov.tools is not None and tools_block()["kind"] == "own"
