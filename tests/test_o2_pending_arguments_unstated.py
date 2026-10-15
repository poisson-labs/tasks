"""Pending a yes/no: on an arguments arm, a checkable argument the request did not state, given a
value, keeps the call from being the expected write.

**Why it is open.**  Spec §5.2: "an argument the request did not state is ignored unless the knob says
otherwise (§6)"; §6.1, arguments: the level is how many parameters "the request states and the
verifier checks; the rest are left out".  Whether "left out" binds the model is not said.  The
built-in knob rules the call carries exactly the stated values (knobs spec §14.2, ruling 48).

**Recommendation: yes.**  As the built-in knob: on an arguments arm the target call must carry the
stated checkable arguments and no other checkable argument; one more makes it another write (a side
effect), so the episode is short of its goal.  Free text and every other arm are as §5.2 says.  A no
ignores unstated arguments on an arguments arm too, so the level would only count what is checked.
"""

from __future__ import annotations

from tests.o2_support import arm, fixture_sets, generator, judge


def test_an_unstated_checkable_argument_given_a_value_misses_the_goal_on_an_arguments_arm() -> None:
    toolset = fixture_sets()["petstore"]
    found = generator().knob_levels(toolset, "arguments")
    low = found[0]
    for seed in range(6):
        bundle = generator().generate(toolset, arm("arguments", low), seed)
        tool, args = next(c for c in bundle.reference_calls if c[0] == bundle.target)
        top = generator().generate(toolset, arm("arguments", found[-1]), seed)
        _t, more = next(c for c in top.reference_calls if c[0] == top.target)
        extra = {k: v for k, v in more.items() if k not in dict(bundle.stated) and k not in args}
        assert extra
        name, value = next(iter(extra.items()))
        calls = tuple((t, {**a, name: value}) if t == tool else (t, a) for t, a in bundle.reference_calls)
        assert judge(bundle, calls).strict_label == "wrong_state"
