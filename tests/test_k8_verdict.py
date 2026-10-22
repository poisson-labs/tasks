"""How an information-spread episode is judged, and the ledger over the knob's arms, frozen as
tests.

The design: stage 1 accepts only the exact code (the engine's own check), so the final records say
whether the parts were joined right; a model that batches the four reads in one turn needs four
model calls at every level.  The ledger's rows for spread (N1 to N8, N11, N12 and N35) hold over
the knob's arms, and generation refuses a contrast that breaks one.  G4 is the generator's own
gate (it refuses a task whose reference does not verify as `passed`, strict and leaky), so it has
no test of its own here.  The wrong join's half of shape 2 leans on the engine's own exact-code
check; it catches a build whose layer in front of the engine changes what stage 1 accepts.

Shapes decided here
-------------------

**1. The controls**: every task carries B's controls (the reference less its last call, the
reference at the turn limit, the reference with the decoy's first stage after it, and a call
breaking each of format clauses 2, 3 and 4), each giving the label it is named for; a build may add
controls, each named for its label.

**2. Batching, and the join**: the four named reads in one turn, then the two stage calls, then a
reply, is `passed`, leaky true, at every level.  The same episode with stage 1 given the heads of
all four answers joined, `none` included (below level 4, where some answer holds none), or (above
level 1) the parts joined in reverse order, is `wrong_state`, leaky false, and nothing changes: the
record never leaves stage 0.

**3. The contrast**: a test that the four levels are one contrast the ledger refuses nowhere and
reports nothing on was written and removed before the freeze: no deliberate bug failed it that
another `test_k8_*` test did not (the ledger's rows for spread are each held field by field in
`tests/test_k8_fixed.py`, `tests/test_k8_parts.py` and `tests/test_k8_reads.py`, and
`generate_contrast` raises on a refused contrast, so its flag could not fail).
"""

from __future__ import annotations

from typing import Any

from poisson_tasks.tasks import Turn, verify
from tests.k3_support import FMT, SPEC, verdict_of
from tests.k8_support import LEVELS, NONE, SPLITS, heads, named, spread

ENTRY = SPEC.parameter_names["entry"]
NAMED = (
    "wrong_state",
    "turn_limit",
    "collateral_mutation",
    "malformed_call_clause_2",
    "malformed_call_clause_3",
    "malformed_call_clause_4",
)


def label_of(bundle: Any, key: str, calls: Any) -> tuple[str, int | None]:
    if key == "turn_limit":
        verdict = verdict_of(bundle, calls, reply=False, limit=True)
    else:
        verdict = verdict_of(bundle, calls)
    return verdict.label, verdict.format_clause


def named_label(key: str) -> tuple[str, int | None]:
    label, _sep, clause = key.partition("_clause_")
    return label, int(clause) if clause else None


def test_every_control_gives_its_label() -> None:
    """Shape 1."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                where = (level, seed, split)
                assert set(NAMED) <= set(bundle.negative_controls), where
                for key, calls in bundle.negative_controls.items():
                    label, clause = label_of(bundle, key, calls)
                    if key in NAMED:
                        assert (label, clause) == named_label(key), (key, *where)
                    else:
                        assert key.startswith(label), (key, label, *where)


def batched(bundle: Any, code: str | None = None) -> tuple[Turn, ...]:
    """The named reads in one turn, then each stage call in a turn of its own, then a reply; with
    `code`, stage 1 carries it instead of the reference's."""
    stages = [(n, dict(a)) for n, a in bundle.reference_calls if n in SPEC.stage_tools]
    if code is not None:
        stages[0] = (stages[0][0], {**stages[0][1], ENTRY: code})
    turns = [Turn(content="", calls=tuple(named(bundle)), finish_reason="tool_calls")]
    turns += [Turn(content="", calls=(call,), finish_reason="tool_calls") for call in stages]
    return (*turns, Turn(content="Done.", calls=(), finish_reason="stop"))


def test_the_reads_batched_pass_and_a_wrong_join_never_leaves_stage_zero() -> None:
    """Shape 2."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                where = (level, seed, split)
                verdict = verify(bundle, batched(bundle), True, False, FMT)
                assert (verdict.label, verdict.leaky_pass) == ("passed", True), where
                said = heads(bundle)
                wrong = ["".join(said)] if NONE in said else []
                if level > 1:
                    wrong.append("".join(head for head in reversed(said) if head != NONE))
                for code in wrong:
                    verdict = verify(bundle, batched(bundle, code), True, False, FMT)
                    assert (verdict.label, verdict.leaky_pass) == ("wrong_state", False), (
                        code,
                        *where,
                    )
                    assert verdict.mutations == (), (code, *where)
