"""Pending a decision: the shape knob on a user's own tools.

**Why it is open.**  The design: shape runs "chains of your declared links, run in sequence or side
by side; needs two independent declared chains for the parallel forms".  The built-in knob keeps
four stage calls at every width (one record through four stages; two records two stages each; four
records one stage each), so a width changes how the calls are arranged and nothing else.  A user's
chains are as long as they declared them, so four calls at every width cannot be kept, and "two
independent declared chains" does not say how widths 1, 2 and 4 are made from them.

**Recommended.**  Shape takes the longest declared chain whose first call takes a checkable argument
(so its runs can be told apart) and runs it four times, each run on values of its own:  width 1 is
the four runs one after another, width 2 two such sequences of two side by side, width 4 all four
side by side.  A run that must follow another is held by the simulator (`not_ready`) until the
other's last write is done.  Every width makes the same calls; only their order is constrained
differently, which is the knob.  If it is declined, the build reads "two independent declared
chains" literally: widths 1 and 2 only, from two chains the user declared, which most tool sets will
not have.
"""

from __future__ import annotations

from tests.o2_support import acme, acme_flows, arm, generator, judge


def test_shape_runs_a_keyed_chain_four_times_and_width_only_changes_what_must_wait() -> None:
    gen = generator()
    flows = acme_flows()
    assert gen.knob_levels(acme(), "shape", flows=flows) == (1, 2, 4)
    only_free = (gen.Flow("search_orders", "orders[].order_id", "refund_order", "order_id"),)
    assert gen.knob_levels(acme(), "depth", flows=only_free) == (1, 2)
    assert gen.knob_levels(acme(), "shape", flows=only_free) == ()
    for seed in range(8):
        made = {width: gen.generate(acme(), arm("shape", width), seed, flows=flows) for width in (1, 2, 4)}
        calls = {width: sorted(map(repr, bundle.reference_calls)) for width, bundle in made.items()}
        assert calls[1] == calls[2] == calls[4]
        chain = ["get_order", "refund_order"]
        assert [name for name, _a in made[1].reference_calls] == chain * 4
        targets = [c for c in made[1].reference_calls if c[0] == "refund_order"]
        assert len({repr(c) for c in targets}) == 4
        for width, bundle in made.items():
            reference = list(bundle.reference_calls)
            assert judge(bundle, reference).strict_label == "passed"
            runs = [reference[i:i + 2] for i in range(0, 8, 2)]
            swapped = runs[0] + runs[2] + runs[1] + runs[3]
            found = judge(bundle, swapped).strict_label
            assert found == ("wrong_state" if width == 1 else "passed"), (width, found)
            backwards = [call for run in reversed(runs) for call in run]
            found = judge(bundle, backwards).strict_label
            assert found == ("passed" if width == 4 else "wrong_state"), (width, found)
