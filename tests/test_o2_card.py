"""The card on a user's own tools, frozen as tests.

The invariant: the own-tools provenance kind, the first lines and the not-claimed lines, and a
side-by-side with a published card that pools nothing.  And on your tools each knob's card shows its
own table against its first level and says, in words, whether that knob made your tasks harder for
this model at this sample size.

Shapes decided here
-------------------

**1. The own-tools provenance kind** is `Provenance.tools`, a mapping whose `kind` is `"own"`,
holding the set's `name`, its usable `tools` count, its `source_format`, the file's
`file_digest`, the tools that have an intent (`intents`, sorted names), the number of declared
`flows` and the `generator` label `own-1`.  A provenance block of the built-in tasks has none,
and its `as_dict()` holds no `tools` key, so every published block keeps its bytes.  Any other
`kind` is refused.  `Provenance.for_plan` of a plan with `own` writes it, and the block's
`generator_hash` is then the own-tools generator's.

**2. The first lines** are the design's two sentences, the first paragraph after the document's
title: `Measured on your tools (<name>, <n> tool(s) from <an OpenAI tools file | an MCP tool
list | an OpenAPI document>), with responses simulated from your schemas. Your backend was never
called.`  `own.card.first_lines(tools)` renders them.

**3. What it does not claim**: `card_claims(artifact).flags` holds `own_backend`,
`own_not_comparable`, `own_levels` and `own_no_effect` on every own-tools card, and `own_word_match`
unless every tool of the set has an intent; each flag is one line of `not_claimed`, holding a phrase
of the design's words for it (`PHRASES`).  None of the built-in card's lines that compare with the
published cards (`small_sample`, `not_comparable`, `not_covered`, `distractor`) is given: an
own-tools card is not read against them at all.  `stale` reads the card's hash against the own-tools
generator's.  The words of the lines are the build's.

**4. Beside a published card**: `own.card.beside_published(own, published)` holds the line
`DIFFERENT_TASKS` ("different tasks: read each card on its own"), the own card's document and the
published card's document, each whole, and nothing else but headings; a published card of
another model is refused in one line.  `calibration.comparable` names a field on which the two
differ and `calibration.render_side_by_side` refuses them, so nothing pools them.

**5. Against the first level**: `own.card.against_first(cells, provenance)` gives, per knob, one
row per level after the first, `AgainstFirst(knob, level, first, predicate, delta, low, high,
verdict)`: the paired delta of the level against the first (`calibration.paired_delta` on the
row's predicate), called under the two-clause rule (`calibration.call_pair`), or excluded, with no
delta, when both levels are saturated on the same side.  Which predicate depth is read on is the
pending file `test_o2_pending_depth_predicate.py`; every other knob is read on strict.  `own.card.bite(rows)` says per knob whether it made the tasks harder (the pending file
`test_o2_pending_bite_sentence.py` pins the rule), and an own-tools run's card document carries
those sentences.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks import cards
from tests.o2_support import card, generator

MODEL = "gpt-5-nano-2025-08-07"
FIRST = ("Measured on your tools (acme-support, 5 tools from an MCP tool list), with responses "
         "simulated from your schemas. Your backend was never called.")


def tools_block(**extra: Any) -> dict[str, Any]:
    return {"kind": "own", "name": "acme-support", "tools": 5, "source_format": "mcp",
            "file_digest": "f" * 64, "intents": [], "flows": 2, "generator": "own-1", **extra}


def provenance(seeds: int = 10, **extra: Any) -> cal.Provenance:
    seed_list = list(range(500, 500 + seeds))
    fields: dict[str, Any] = dict(
        package_version="0.0.1", engine_hash="e" * 64, generator_hash=generator().generator_hash(),
        vocabulary_hash="v" * 64, verifiers_version="0.3.1", harness_id="null",
        models=[{"id": MODEL, "revision": MODEL, "endpoint_host": "api.openai.com"}],
        decoding=dict(cal.DECODING), seed_list=seed_list,
        seed_list_hash=hashlib.sha256(json.dumps(seed_list).encode("utf-8")).hexdigest(),
        S=seeds, n=1, k_values=[1], bootstrap_resamples=200, bootstrap_seed=20260922,
        delta_star=0.15, saturation_high=0.95, saturation_low=0.05, instrument_threshold=1.0,
        rate_read_date="2026-10-13", serving={MODEL: {"kind": "hosted", "endpoint_host": "api.openai.com"}},
        budget=dict(cal.DEFAULT_BUDGET), tools=tools_block(),
    )
    fields.update(extra)
    return cal.Provenance(**fields)


def record(arm: str, seed: int, passed: bool, *, leaky: bool | None = None) -> cal.EpisodeRecord:
    reached = passed if leaky is None else leaky
    return cal.EpisodeRecord(
        task_id=f"{arm}-{seed}", arm_id=arm, model=MODEL, seed=seed, attempt=0, strict=passed,
        leaky=reached, label="passed" if passed else ("collateral_mutation" if reached else "wrong_state"),
        turns=3, sampled_calls=2, prompt_tokens=100, cached_input_tokens=0, completion_tokens=10,
        reasoning_tokens=0, cost=None)


def cells_of(rates: dict[str, float], seeds: int = 10) -> dict[tuple[str, str], list[cal.EpisodeRecord]]:
    out = {}
    for arm, rate in rates.items():
        passing = round(rate * seeds)
        out[(arm, MODEL)] = [record(arm, 500 + i, i < passing) for i in range(seeds)]
    return out


def artifact(rates: dict[str, float] | None = None, **extra: Any) -> cal.Artifact:
    prov = provenance(**extra)
    return cal.build_artifact(cells_of(rates or {"faults:f0": 0.8, "faults:f2": 0.5}), prov)


# --------------------------------------------------------------------------
# the provenance kind
# --------------------------------------------------------------------------


def test_the_own_tools_kind_travels_in_the_provenance_and_a_built_in_block_keeps_its_bytes() -> None:
    prov = provenance()
    assert prov.as_dict()["tools"] == tools_block()
    no_tools: dict[str, Any] = {"tools": None}
    built_in = dataclasses.replace(prov, **no_tools)
    assert "tools" not in built_in.as_dict()
    with pytest.raises(ValueError):
        provenance(tools=tools_block(kind="published"))


def test_for_plan_writes_the_kind_and_the_own_generators_hash(tmp_path: Any) -> None:
    """Retrofitted 2026-10-29 for 0.3.0: the own-tools generator label moved from "own-1" to "own-2" with the ruled change to the frozen generator (the faults spec's Q4)."""
    from tests.o1_support import fixture
    from tests.o2_support import config

    (tmp_path / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    flags = ["--provider", "openai", "--no-price", "--token-cap", "1000", "--recipe", "first-look",
             "--own-file", "tools.json", "--own-name", "acme-support",
             "--own-intent", "refund_order=refund a customer's order",
             "--own-flow", "search_orders.orders[].order_id:get_order.order_id",
             "--own-flow", "get_order.order_id:refund_order.order_id"]
    plan = config().resolve_plan(config().config_from_init_args(flags), root=tmp_path)
    prov = cal.Provenance.for_plan(plan, serving={MODEL: {"kind": "hosted", "endpoint_host": "h"}},
                                   rate_read_date="2026-10-13")
    assert prov.generator_hash == generator().generator_hash()
    assert prov.as_dict()["tools"] == {
        "kind": "own", "name": "acme-support", "tools": 5, "source_format": "mcp",
        "file_digest": hashlib.sha256(fixture("acme-mcp-tools-list.json")).hexdigest(),
        "intents": ["refund_order"], "flows": 2, "generator": "own-2"}


# --------------------------------------------------------------------------
# the first lines and what the card does not claim
# --------------------------------------------------------------------------


@pytest.mark.parametrize("fmt, words", [("mcp", "an MCP tool list"), ("openai", "an OpenAI tools file"),
                                        ("openapi", "an OpenAPI document")])
def test_the_first_lines_are_spec_9s(fmt: str, words: str) -> None:
    block = tools_block(source_format=fmt, tools=23)
    assert card().first_lines(block) == (
        f"Measured on your tools (acme-support, 23 tools from {words}), with responses simulated "
        "from your schemas. Your backend was never called.")
    assert card().first_lines(tools_block(tools=1)).startswith("Measured on your tools (acme-support, 1 tool from")


def test_the_document_opens_with_the_first_lines() -> None:
    document = cal.render_document(artifact(), claims=True)
    lines = [line for line in document.splitlines() if line.strip()]
    assert lines[0].startswith("# ") and lines[1] == FIRST
    built_in = cal.render_document(artifact(tools=None), claims=True)
    assert "Measured on your tools" not in built_in


PHRASES = {
    "own_backend": "real tools",
    "own_not_comparable": "published cards",
    "own_levels": "levels compare with each other",
    "own_word_match": "word match",
    "own_no_effect": "no effect",
}


def test_every_line_that_applies_is_said_and_no_published_card_comparison() -> None:
    claims = cal.card_claims(artifact())
    always = {"own_backend", "own_not_comparable", "own_levels", "own_no_effect"}
    assert always | {"own_word_match"} <= claims.flags
    for flag, phrase in PHRASES.items():
        assert sum(phrase in line for line in claims.not_claimed) == 1, flag
    assert not claims.flags & {"small_sample", "not_comparable", "not_covered", "distractor"}
    assert len(claims.not_claimed) == len(claims.flags)
    assert all(line.strip() and "\n" not in line for line in claims.not_claimed)
    document = cal.render_document(artifact(), claims=True)
    for line in claims.not_claimed:
        assert f"- {line}" in document


def test_the_word_match_line_goes_only_when_every_tool_has_an_intent() -> None:
    names = ["get_order", "search_orders", "refund_order", "notify_customer", "list_channels"]
    partly = cal.card_claims(artifact(tools=tools_block(intents=names[:4])))
    whole = cal.card_claims(artifact(tools=tools_block(intents=sorted(names))))
    assert "own_word_match" in partly.flags and "own_word_match" not in whole.flags
    assert len(whole.not_claimed) == len(partly.not_claimed) - 1


def test_stale_reads_the_own_tools_generators_hash() -> None:
    assert "stale" not in cal.card_claims(artifact()).flags
    assert "stale" in cal.card_claims(artifact(generator_hash="0" * 64)).flags
    from tests.test_frozen_generator import FROZEN_GENERATOR_HASH

    assert "stale" in cal.card_claims(artifact(generator_hash=FROZEN_GENERATOR_HASH)).flags


def test_a_self_served_models_line_is_still_said_on_own_tools() -> None:
    serving = {MODEL: {"kind": "self_served", "stack": "vllm", "endpoint": "http://127.0.0.1:8000/v1",
                       "reported_by_server": []}}
    claims = cal.card_claims(artifact(serving=serving))
    assert "self_served" in claims.flags and len(claims.not_claimed) == len(claims.flags)


# --------------------------------------------------------------------------
# beside the published card
# --------------------------------------------------------------------------


def published_artifact(name: str) -> cal.Artifact:
    (found,) = [c for c in cards.published() if c.name == name]
    return cards.recompute(found).artifact


def test_beside_the_published_card_each_is_whole_and_nothing_is_pooled() -> None:
    own_card = artifact({"depth:d1": 0.9, "depth:d2": 0.6})
    published = published_artifact("gpt-5-nano")
    shown = card().beside_published(own_card, published)
    assert card().DIFFERENT_TASKS == "different tasks: read each card on its own"
    own_document = cal.render_document(own_card, claims=True)
    published_document = cal.render_document(published)
    assert card().DIFFERENT_TASKS in shown
    assert own_document in shown and published_document in shown
    rest = shown.replace(own_document, "").replace(published_document, "").replace(card().DIFFERENT_TASKS, "")
    assert all(not line.strip() or line.startswith("#") for line in rest.splitlines()), rest


def test_beside_a_published_card_of_another_model_is_refused() -> None:
    with pytest.raises(ValueError) as refused:
        card().beside_published(artifact(), published_artifact("qwen3-8b"))
    assert "\n" not in str(refused.value)


def test_the_comparison_of_the_built_in_cards_will_not_read_an_own_tools_card_beside_one() -> None:
    """A guard: the card's side-by-side, which pools levels across cards measured alike, never takes
    an own-tools card and a published one as alike."""
    own_card = artifact({"depth:d1": 0.9, "depth:d2": 0.6})
    published = published_artifact("gpt-5-nano")
    assert cal.comparable(own_card, published).field is not None
    with pytest.raises(ValueError):
        cal.render_side_by_side({"mine": own_card, "published": published})


# --------------------------------------------------------------------------
# each level against the first
# --------------------------------------------------------------------------


def test_each_level_is_read_against_the_first_paired_under_the_two_clause_rule() -> None:
    rates = {"faults:f0": 0.9, "faults:f1": 0.8, "faults:f2": 0.3, "faults:f4": 0.1,
             "history:t0": 0.9, "history:t600": 0.5}
    cells = cells_of(rates, seeds=20)
    prov = provenance(seeds=20)
    rows = card().against_first(cells, prov)
    assert [(r.knob, r.level, r.first) for r in rows] == [
        ("faults", 1, 0), ("faults", 2, 0), ("faults", 4, 0), ("history", 600, 0)]
    for row in rows:
        letter = "f" if row.knob == "faults" else "t"
        level_arm, first_arm = f"{row.knob}:{letter}{row.level}", f"{row.knob}:{letter}{row.first}"
        predicate = "strict"
        assert row.predicate == predicate
        delta = cal.paired_delta(cells[(level_arm, MODEL)], cells[(first_arm, MODEL)],
                                 resamples=prov.bootstrap_resamples, seed=prov.bootstrap_seed,
                                 predicate=predicate)
        assert (row.delta, row.low, row.high) == (delta.point, delta.low, delta.high)
        assert row.verdict == cal.call_pair(delta, prov)
    said = card().bite(rows)
    assert set(said) == {"faults", "history"} and all("\n" not in line for line in said.values())


def test_a_pair_saturated_on_one_side_is_excluded_and_on_opposite_sides_is_read() -> None:
    rates = {"history:t0": 1.0, "history:t300": 1.0, "history:t600": 0.0,
             "spread:p1": 0.0, "spread:p2": 0.0, "spread:p4": 1.0}
    rows = {(r.knob, r.level): r for r in card().against_first(cells_of(rates), provenance())}
    assert rows[("history", 300)].delta is None and rows[("spread", 2)].delta is None
    assert rows[("history", 300)].verdict == rows[("spread", 2)].verdict != cal.DISTINGUISHABLE
    assert rows[("history", 600)].delta == -1.0 and rows[("history", 600)].verdict == cal.DISTINGUISHABLE
    assert rows[("spread", 4)].delta == 1.0
