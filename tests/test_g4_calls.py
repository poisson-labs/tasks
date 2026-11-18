"""How a spread episode is judged from 0.5.0, and that every level still needs the same six calls,
frozen as tests.

The 0.5.0 change takes a word out of the answers and changes one sentence of the request.  It
changes neither what a task asks a model to do nor how many calls that takes: the design chose to
keep the three empty answers at level 1 (ruled 2026-11-15) because naming only P reads at level P
would make the levels differ in calls and in the request, and the dial would no longer vary one
thing.

Shapes decided here
-------------------

**1. Six calls at every level**: at each of the sixty card seeds on both splits, the reference of
levels 1, 2, 3 and 4 is the same six calls, four named reads and then the two stage calls, and each
level's arm budgets seven reference turns, a call a turn and the reply.

**2. The right join passes**: the four reads in one turn, then stage 1 with the four heads joined
in the listed order, then stage 2, then a reply, is `passed`, leaky true, at every level.  The code
is sent as the join of what the answers say before their full stops, not copied from the reference.

**3. A join that keeps filler is refused**: the same episode with stage 1 given the code and
something an answer says after its full stop is `wrong_state`, leaky false, and changes nothing:
the record never leaves stage 0.  Four such joins, each at every level it exists at: the four
payloads joined whole; the heads joined with each answer's full stop kept; the code and then the
fill of the first answer that holds no part (below level 4); and the code and then the last
answer's fill.  The second is the shape the old failure takes now: with an empty head, a model that
keeps the separators sends two full stops side by side.

Before 0.5.0 the wrong join `tests/test_k8_verdict.py` tested was the heads joined with `none`
among them.  With empty heads that join is the code itself, so that file's wrong join is
retrofitted to a filler join; the joins here are this release's own.
"""

from __future__ import annotations

from typing import Any

from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import Turn, verify
from tests.g4_support import LEVELS, READS, STOP, holds_no_part, payloads, split_payloads
from tests.k3_support import FMT, SPEC
from tests.k8_support import SPLITS, arm, entry_code, named, spread

ENTRY = SPEC.parameter_names["entry"]
CALLS = 6
TURNS = CALLS + 1


def test_every_level_makes_the_same_six_calls_in_seven_reference_turns() -> None:
    """Shape 1."""
    assert {arm_from_id(arm(level)).reference_turns for level in LEVELS} == {TURNS}
    for split, seeds in SPLITS:
        for seed in seeds:
            references = [spread(level, seed, split).reference_calls for level in LEVELS]
            where = (seed, split)
            assert all(reference == references[0] for reference in references), where
            names = [name for name, _args in references[0]]
            assert len(names) == CALLS, where
            assert all(name in SPEC.read_tools for name in names[:READS]), where
            assert all(name in SPEC.stage_tools for name in names[READS:]), where


def batched(bundle: Any, code: str) -> tuple[Turn, ...]:
    """The named reads in one turn, then stage 1 carrying `code`, then stage 2, then a reply."""
    stages = [(n, dict(a)) for n, a in bundle.reference_calls if n in SPEC.stage_tools]
    stages[0] = (stages[0][0], {**stages[0][1], ENTRY: code})
    turns = [Turn(content="", calls=tuple(named(bundle)), finish_reason="tool_calls")]
    turns += [Turn(content="", calls=(call,), finish_reason="tool_calls") for call in stages]
    return (*turns, Turn(content="Done.", calls=(), finish_reason="stop"))


def filler_joins(bundle: Any) -> dict[str, str]:
    """Each join that keeps something an answer says after its full stop, by a name."""
    texts = payloads(bundle)
    cut = split_payloads(bundle)
    code = "".join(head for head, _fill in cut)
    joins = {
        "the payloads whole": "".join(texts),
        "the heads with their stops": "".join(head + STOP for head, _fill in cut),
        "the code and the last fill": code + cut[-1][1],
    }
    empty = [fill for text, (_head, fill) in zip(texts, cut) if holds_no_part(text)]
    if empty:
        joins["the code and the first empty answer's fill"] = code + empty[0]
    return joins


def test_the_heads_joined_pass_and_a_join_that_keeps_filler_never_leaves_stage_zero() -> None:
    """Shapes 2 and 3."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                where = (level, seed, split)
                code = "".join(head for head, _fill in split_payloads(bundle))
                assert code == entry_code(bundle), where
                verdict = verify(bundle, batched(bundle, code), True, False, FMT)
                assert (verdict.label, verdict.leaky_pass) == ("passed", True), where
                joins = filler_joins(bundle)
                assert len(joins) == (4 if level < READS else 3), where
                for name, wrong in joins.items():
                    assert wrong != code, (name, *where)
                    verdict = verify(bundle, batched(bundle, wrong), True, False, FMT)
                    assert (verdict.label, verdict.leaky_pass) == ("wrong_state", False), (
                        name,
                        wrong,
                        *where,
                    )
                    assert verdict.mutations == (), (name, *where)
