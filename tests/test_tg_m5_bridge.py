"""MP10, the bridge between the two scorers: on one trace, the export's `strict` reward (X4)
and the adapter's strict label (`to_episode`, through `_judge`) agree on `passed` -- frozen
as tests.

Ruled 2026-09-21 (question 5 of the model path spec): the two must agree on `passed`.  Nothing
pinned it before: X4 is frozen against TG-M3's `verify` on turns the test built, the adapter's
verdict against its own scripted runs, and no test had put them on one trace.  This file does.
It needs the Proofload extra, because `to_episode` returns a `proofload.Episode` and
`poisson_tasks.adapter` imports Proofload at import, which is why it is not in
`tests/test_tg_m5_standalone.py`: `tests/conftest.py` skips it whole without the extra, the way
it skips the scripted path's file.  **Frozen 2026-09-22** with the standalone file, on Taylor's
approval of the mapping and his ruling that MP10 stays in this file.

The traces are synthetic, built as the `null` harness at 0.3.1 leaves one (TG-M4's decision 6):
the seeded prompt, one sampled assistant message per call with its tool message, then a reply.
A call whose arguments are not a JSON object, or whose name is outside the block, gets the
harness's own `error: ...` line and no `seq`, because it never reached the engine (VN-7).
The `Run` is built here, from the trace, by the rule layer 2's mapping will be held to (MP11):
the sampled calls in the order they were made, each with the tool message it got back,
`ended_with_reply` from the last sampled message, `turn_limit_hit` from
`stop_condition == "max_turns"` (ruled 2026-09-21), the export's own empty format spec.

Shapes decided here
-------------------

**1. A8 replays what reached the engine, and not what the harness answered itself: shape
(b).**  The Handoff named three shapes and asked for a measurement before the choice.  Measured
on the whole scripted oracle first (`evidence/model-path-session-a/probes/shape_b_measurement.txt`):
with `_judge` replaying every call except those whose tool message is the harness's own
`error: ...` line, every scripted case stays green -- every scripted observation comes from
`apply`, which numbers every call (E5), so no scripted run has such a message.  A count
difference is a mismatch as before, and every message that is not the harness's shape is
replayed and compared byte for byte as before.  The first cut of the edit, "replay the calls
whose message opens with a `seq`", was measured too and failed 15 cases: a corrupted `seq`
was skipped instead of detected, which is the wrong way round.  `Run` keeps its six fields
(`test_sf4` stands) and `to_episode` its signature.  *Escape hatch:* shape (a), a seventh
field on `Run`, on a scripted-path retrofit branch (Taylor, 2026-09-21: allowed if (b) had not
held).  The tests here pin the label and would survive it.

**2. The invariant is about `passed`, on traces the harness could have left.**  A genuine
divergence -- a tool message whose bytes are not what the engine would have written -- is
`replay_mismatch` for the adapter and invisible to the reward, which scores the calls; that is
the one check the reward does not have, by construction, and `test_mp10_4` records it as a
control rather than an agreement.

Open, and not settled here
--------------------------

1. **Where a harness-refused call sorts under X4** (TG-M4's open point 4).  Such a call
   mutates nothing wherever it sorts, and no test here depends on the answer.
"""

from __future__ import annotations

import asyncio
import dataclasses
import importlib
import json
from collections.abc import Iterable
from typing import Any

import pytest
import verifiers.v1 as vf

from poisson_tasks.engine import apply, init_state
from poisson_tasks.knobs import ArmSpec, arm_id, levels
from poisson_tasks.tasks import FormatSpec, TaskBundle, Turn, generate, scenario_for

GEN_VERSION = "0"
SLACK = 3
HORIZON = 20  # above every arm's `max_turns(SLACK)`; N17's common `H` is the scripted path's
TURN_LIMIT_STOP = "max_turns"
NO_MARKERS = FormatSpec(name="test", markers=())
SEEDS = (404, 55, 2121)

D_PLAIN = levels("depth")
R_PLAIN = levels("distractor")
D_CONTROLS = ((1, 8), (2, 5))
R_CONTROLS = ((0, 8), (2, 14))


def spec_of(knob: str, level: int, control: int | None = None, strictness: str = "strict") -> ArmSpec:
    return ArmSpec(knob=knob, level=level, control=control, strictness=strictness,
                   split="eval", generator_version=GEN_VERSION)


D_SPECS = tuple(spec_of("depth", lvl) for lvl in D_PLAIN) + tuple(spec_of("depth", lvl, ctl) for lvl, ctl in D_CONTROLS)
R_SPECS = tuple(spec_of("distractor", lvl) for lvl in R_PLAIN) + tuple(spec_of("distractor", lvl, ctl) for lvl, ctl in R_CONTROLS)
ALL_SPECS = D_SPECS + R_SPECS + tuple(dataclasses.replace(s, strictness="leaky") for s in (D_SPECS[2], R_SPECS[2]))
SPEC_IDS = [f"{arm_id(s)}{'/leaky' if s.strictness == 'leaky' else ''}" for s in ALL_SPECS]


def adapter() -> Any:
    return importlib.import_module("poisson_tasks.adapter")


def export() -> Any:
    return importlib.import_module("poisson_tasks.export")


# --------------------------------------------------------------------------
# a trace as the null harness leaves it, and the Run built from it
# --------------------------------------------------------------------------


def live_observations(bundle: TaskBundle, calls: Iterable[tuple[str, Any]]) -> list[str]:
    state = init_state(scenario_for(bundle.seed, bundle.split), bundle.seq_start)
    names = {str(tool["name"]) for tool in bundle.tools}
    out: list[str] = []
    for name, args in calls:
        if not isinstance(args, dict):
            out.append("error: tool arguments must be a JSON object, got "
                       f"{type(json.loads(json.dumps(args))).__name__}; resend as an object")
        elif name not in names:
            out.append(f"error: unknown tool {name!r}")
        else:
            state, observation = apply(state, (name, args))
            out.append(observation)
    return out


def seeded_nodes(task: Any) -> list[Any]:
    prompt = task.data.prompt
    if isinstance(prompt, str):
        return [vf.MessageNode(parent=None, message=vf.UserMessage(content=prompt), sampled=False)]
    return [vf.MessageNode(parent=index - 1 if index else None, message=message, sampled=False)
            for index, message in enumerate(prompt)]


def trace_of(task: Any, bundle: TaskBundle, calls: Iterable[tuple[str, Any]], *, reply: bool,
             observations: list[str] | None = None) -> Any:
    calls = list(calls)
    observations = observations if observations is not None else live_observations(bundle, calls)
    nodes = seeded_nodes(task)
    for index, ((name, args), observation) in enumerate(zip(calls, observations, strict=True)):
        call_id = f"sampled-{index}"
        arguments = json.dumps(list(args) if isinstance(args, tuple) else args)
        assistant = vf.AssistantMessage(content="", tool_calls=[vf.ToolCall(id=call_id, name=name, arguments=arguments)])
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=assistant, sampled=True))
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=vf.ToolMessage(tool_call_id=call_id, content=observation, name=name), sampled=False))
    if reply:
        nodes.append(vf.MessageNode(parent=len(nodes) - 1, message=vf.AssistantMessage(content="Done."), sampled=True))
    return vf.Trace(
        task=vf.TraceTask(type=type(task).__name__, data=task.data, key=task.key, hash=task.hash),
        agent=vf.AgentInfo(config=vf.AgentConfig()),
        nodes=nodes,
        stop_condition=None if reply else TURN_LIMIT_STOP,
    )


def deep_tuple(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return tuple(deep_tuple(item) for item in value)
    return value


def run_of(trace: Any) -> Any:
    """The `Run` layer 2's mapping will build (MP11), written here from the trace: sampled
    calls in the order made, each paired with the tool message that answered it."""
    calls: list[tuple[str, tuple[str, Any]]] = []
    messages: list[str] = []
    for node in trace.nodes:
        message = node.message
        if node.sampled and isinstance(message, vf.AssistantMessage):
            for call in message.tool_calls or []:
                try:
                    arguments: Any = json.loads(call.arguments or "{}")
                except ValueError:
                    arguments = call.arguments
                calls.append((call.id, (call.name, deep_tuple(arguments) if isinstance(arguments, list) else arguments)))
        elif isinstance(message, vf.ToolMessage) and len(messages) < len(calls):
            if message.tool_call_id == calls[len(messages)][0]:
                messages.append(str(message.content))
    sampled = trace.assistant_messages
    ended_with_reply = bool(sampled) and not sampled[-1].tool_calls
    turns = [Turn(content="", calls=(call,), finish_reason="tool_calls") for _id, call in calls]
    if ended_with_reply:
        turns.append(Turn(content=sampled[-1].content or "", calls=(), finish_reason="stop"))
    return adapter().Run(
        turns=tuple(turns), tool_messages=tuple(messages), ended_with_reply=ended_with_reply,
        turn_limit_hit=trace.stop_condition == TURN_LIMIT_STOP, fmt=NO_MARKERS,
    )


def reward_of(task: Any, trace: Any) -> float:
    asyncio.run(task.score(trace, None))
    return float(trace.rewards["strict"].score)


def episode_of(spec: ArmSpec, bundle: TaskBundle, trace: Any) -> Any:
    return adapter().to_episode(spec, bundle, run_of(trace), slack=SLACK, horizon=HORIZON)


def both(spec: ArmSpec, bundle: TaskBundle, task: Any, trace: Any) -> tuple[float, Any]:
    return reward_of(task, trace), episode_of(spec, bundle, trace)


def off_block_name(bundle: TaskBundle) -> str:
    names = {str(tool["name"]) for tool in bundle.tools}
    candidate = "probe_nonexistent"
    while candidate in names:
        candidate += "_x"
    return candidate


def trace_kinds(task: Any, bundle: TaskBundle) -> dict[str, Any]:
    """Every trace the agreement is held on: the reference, each negative control, the
    reference cut short, and the two live rows -- a clause 2 and a clause 3 call inside an
    episode that otherwise passes."""
    ref = list(bundle.reference_calls)
    kinds = {"reference": trace_of(task, bundle, ref, reply=True),
             "reference, no reply": trace_of(task, bundle, ref, reply=False)}
    for label, calls in bundle.negative_controls.items():
        kinds[f"control {label}"] = trace_of(task, bundle, list(calls), reply=True)
    kinds["clause 2 inside a pass"] = trace_of(task, bundle, [ref[0], (ref[0][0], (1, 2)), *ref[1:]], reply=True)
    kinds["clause 3 inside a pass"] = trace_of(task, bundle, [ref[0], (off_block_name(bundle), {"x": 1}), *ref[1:]], reply=True)
    return kinds


# --------------------------------------------------------------------------
# MP10
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_mp10_1_the_reward_is_one_exactly_when_the_strict_label_is_passed(spec, seed):
    bundle = generate(spec, seed)
    task = export().task_from_bundle(bundle)
    for kind, trace in trace_kinds(task, bundle).items():
        reward, episode = both(spec, bundle, task, trace)
        assert (reward == 1.0) == (episode.meta["strict_label"] == "passed"), (kind, reward, episode.outcome)
        if spec.strictness == "strict":
            assert (reward == 1.0) == (episode.outcome == "passed"), (kind, reward, episode.outcome)


@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_mp10_2_the_two_live_rows_a_harness_refused_call_inside_a_pass(spec):
    """MP12's two rows, seen from the bridge: the reward is 1.0 (the pass predicate is
    decided before the format check, TG-M3's decision 4) and the adapter must agree -- which
    it can only do if it does not replay the call the engine never saw (A8, shape (b)).  The
    clause is reported by both."""
    bundle = generate(spec, SEEDS[0])
    task = export().task_from_bundle(bundle)
    kinds = trace_kinds(task, bundle)
    for clause, kind in ((2, "clause 2 inside a pass"), (3, "clause 3 inside a pass")):
        reward, episode = both(spec, bundle, task, kinds[kind])
        assert reward == 1.0, kind
        assert episode.meta["strict_label"] == "passed", (kind, episode.outcome)
        assert episode.outcome == "passed", kind
        assert episode.meta["format_clause"] == clause, kind
        assert episode.meta["sampled_calls"] == len(bundle.reference_calls) + 1


@pytest.mark.parametrize("spec", (D_SPECS[0], D_SPECS[5], R_SPECS[4], R_SPECS[6]), ids=arm_id)
def test_mp10_3_the_controls_own_label_is_malformed_call_and_not_replay_mismatch(spec):
    """The same hole from the label's side (A8's warning in 2.5): a clause 2 or clause 3
    control that falls short of `passed` is `malformed_call`, a system label, and never
    `replay_mismatch`, an instrument one."""
    bundle = generate(spec, SEEDS[0])
    task = export().task_from_bundle(bundle)
    for label, calls in bundle.negative_controls.items():
        if not label.startswith("malformed_call"):
            continue
        episode = episode_of(spec, bundle, trace_of(task, bundle, list(calls), reply=True))
        assert episode.outcome != "replay_mismatch", label
        assert episode.meta["strict_label"] == "malformed_call", (label, episode.outcome)


@pytest.mark.parametrize("spec", (D_SPECS[2], R_SPECS[3]), ids=arm_id)
def test_mp10_4_control_a_genuine_divergence_is_replay_mismatch_and_the_reward_cannot_see_it(spec):
    """The one place the two differ by construction.  A live observation whose bytes are not
    the engine's is an instrument failure the adapter labels and the reward, which scores the
    calls, does not have a check for.  Both halves are pinned so the difference is declared."""
    bundle = generate(spec, SEEDS[0])
    task = export().task_from_bundle(bundle)
    ref = list(bundle.reference_calls)
    good = live_observations(bundle, ref)
    for index in (0, len(good) - 1):
        bad = list(good)
        bad[index] = bad[index][:-1] + ("0" if bad[index][-1] != "0" else "1")
        trace = trace_of(task, bundle, ref, reply=True, observations=bad)
        reward, episode = both(spec, bundle, task, trace)
        assert episode.outcome == "replay_mismatch", index
        assert reward == 1.0, index
    # and a message the harness did not write but that carries no `seq` is a divergence too --
    # on the last message, where skipping it would leave every other message matching
    for index in (0, len(good) - 1):
        bad = list(good)
        bad[index] = "xx" + bad[index][2:]
        trace = trace_of(task, bundle, ref, reply=True, observations=bad)
        assert episode_of(spec, bundle, trace).outcome == "replay_mismatch", index


def test_mp10_5_the_adapters_run_keeps_its_six_fields():
    """Shape (b) costs the frozen scripted tests nothing: `Run` is the record `test_sf4` pins."""
    fields = dataclasses.fields(adapter().Run)
    assert [f.name for f in fields] == ["turns", "tool_messages", "ended_with_reply", "turn_limit_hit", "fmt", "instrument"]
