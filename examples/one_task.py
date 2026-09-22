"""Generate one task, look at it, and run the verifier over every answer it ships with.

    python examples/one_task.py [SEED]

No model, no network, no Proofload. Everything printed below is a pure function of the
arm, the seed and the frozen vocabulary table: run it twice and you get the same bytes.
"""

from __future__ import annotations

import json
import sys

from poisson_tasks.knobs import ArmSpec, arm_id
from poisson_tasks.tasks import FormatSpec, Turn, generate, verify

SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 7

# One arm of the depth knob: three chained stage calls to reach the goal, the strict
# verifier, the eval split, and the generator version the task is pinned to.
ARM = ArmSpec(
    knob="depth",
    level=3,
    control=None,
    strictness="strict",
    split="eval",
    generator_version="tg-m3-v1",
)

# The format spec is the parser the harness uses. A scripted run parses nothing, so it
# declares no markers and the format check's first clause cannot fire.
DIRECT = FormatSpec(name="direct", markers=())


def turns_for(calls, *, reply: bool = True) -> tuple[Turn, ...]:
    """One call per turn, then a plain-text reply -- the episode shape the tasks assume."""
    turns = tuple(Turn(content="", calls=(call,), finish_reason="tool_calls") for call in calls)
    if reply:
        turns += (Turn(content="Done.", calls=(), finish_reason="stop"),)
    return turns


def main() -> None:
    bundle = generate(ARM, SEED)

    print(f"arm {arm_id(ARM)}   seed {SEED}   split {ARM.split}")
    print(f"task_id      {bundle.task_id}")
    print(f"engine hash  {bundle.engine_hash}")
    print(f"turns needed {ARM.reference_turns}, budget at slack 4: {ARM.max_turns(4)}")

    print("\n--- the system prompt ---")
    print(bundle.system_prompt)

    print("\n--- the task ---")
    print(bundle.prompt)

    print(f"\n--- the tool block: {len(bundle.tools)} tools ---")
    for tool in bundle.tools:
        params = ", ".join(tool["parameters"]["properties"])
        print(f"  {tool['name']:<26} ({params})")
    print("\n  one of them in full:")
    print("  " + json.dumps(bundle.tools[0], indent=2).replace("\n", "\n  "))

    cls, record, stage = bundle.goal
    print(f"\n--- the goal: raise {record} of the {cls} ledger to stage {stage} ---")

    print("\n--- the reference solution, and what the domain returns ---")
    for call, obs in zip(bundle.reference_calls, bundle.reference_observations, strict=True):
        name, args = call
        print(f"  {name}({json.dumps(args)})")
        print(f"    -> {obs!r}")

    print("\n--- the verdict on each answer the bundle ships ---")
    verdict = verify(bundle, turns_for(bundle.reference_calls), True, False, DIRECT)
    print(f"  {'reference solution':<26} -> {verdict.label}")

    stops_early = turns_for(bundle.reference_calls[:-1])
    verdict = verify(bundle, stops_early, True, False, DIRECT)
    print(f"  {'one call short':<26} -> {verdict.label}")

    # Each negative control is generated with the task, and is named for the outcome it
    # is supposed to earn. A control that earns some other label is a generator bug --
    # which is what `test_g8_*` in the test suite checks, on far more than one seed.
    for name, calls in bundle.negative_controls.items():
        hit_limit = name == "turn_limit"
        verdict = verify(
            bundle, turns_for(calls, reply=not hit_limit), not hit_limit, hit_limit, DIRECT
        )
        clause = "" if verdict.format_clause is None else f" (clause {verdict.format_clause})"
        print(f"  {name:<26} -> {verdict.label}{clause}")


if __name__ == "__main__":
    main()
