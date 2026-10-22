"""Pending a decision: the expected write made a second time is a side effect.

**Why it is open.**  The design: "a write the task expects moves its record; any other accepted
write is recorded as a side effect".  Whether the same write made again is "another" write is not
said.  The built-in engine refuses a stage advance made twice; a user's write may or may not be
idempotent (a refund made twice is two refunds; setting a flag twice is one).

**Recommended.**  The second time the expected write is made it is accepted and recorded as a side
effect, so an episode that does it ends `collateral_mutation` (leaky passes it), since Tasks cannot
know a user's write is idempotent and the safe reading counts it.  If it is declined, the build
answers it as done and changes nothing, which would let a model that loops on the goal call pass
strict.
"""

from __future__ import annotations

from tests.o2_support import acme, judge, make, simulator


def test_the_expected_write_made_again_is_a_side_effect() -> None:
    for seed in range(6):
        bundle = make(acme(), "faults", 0, seed=seed)
        last = bundle.reference_calls[-1]
        found = judge(bundle, bundle.reference_calls + (last,))
        assert (found.strict_label, found.leaky_pass) == ("collateral_mutation", True)
        state, answers = simulator().replay(bundle, bundle.reference_calls + (last,))
        assert len(state.side_effects) == 1 and not answers[-1].is_error
