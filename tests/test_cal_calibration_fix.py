"""The calibration fix: the card measures the level, not whether the model starts.

Model A's first card measured how often `gpt-5-nano-2025-08-07` got started.  The task prompt
gave the record id and the entry code as bare English words, the model did not read them as
values, and in 3,045 of 4,200 episodes its first reply asked for them and called no tool.
Quoting the two values fixed it in a probe: 16 of 16 first replies made the reference call.

These tests pin Taylor's rulings of 2026-09-25, and are written before the change:

1. The prompt template puts the record id and the entry code in double quotes.  The entry
   codes stay the vocabulary table's words, and `template_id` stays `ledger-chain/v1`.
3. A plumbing gate: phase 1 fails unless every episode makes at least one tool call and at
   least half of them reach their structural minimum number of calls.
4. CAL24: every card cell carries the share of episodes that made no tool call and the share
   that stopped short of the minimum, and a cell whose no-call share is above 0.10 refuses to
   publish.
5. Knob D's ordering is shown on the leaky rate beside the strict one, with a note that
   strict at every depth below the top includes a stop-at-the-goal test the top cannot have.
   Strict stays the headline (R15).

Also pinned: the two figures that were named for the wrong thing.  The records' `sampled_calls`
counts tool calls and their `turns` counts model calls, so the artifact and the card name them
`tool_calls` and model calls.

`tests/test_cal_calibration.py` is the frozen oracle and is not edited here.  No test in this
file calls a model, loads a key or leaves loopback.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import json
import os
import shutil
import threading
from collections.abc import Iterator, Sequence
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks.knobs import ArmSpec, arm_id, levels
from poisson_tasks.tasks import generate

MODEL_A = cal.MODEL_A
S = 60
N = 5
KEY_VAR = "POISSON_TASKS_CAL_FIX_TEST_KEY"


def spec_of(knob: str, level: int, control: int | None = None) -> ArmSpec:
    return ArmSpec(knob=knob, level=level, control=control, strictness="strict",
                   split=cal.SPLIT, generator_version=cal.GENERATOR_VERSION)


def record(
    *,
    task_id: str,
    seed: int,
    attempt: int,
    arm: str = "depth:d3",
    strict: bool = False,
    leaky: bool | None = None,
    label: str | None = None,
    sampled_calls: int = 3,
    turns: int = 4,
    prompt_tokens: int = 3000,
    completion_tokens: int = 60,
) -> cal.EpisodeRecord:
    if label is None:
        label = "passed" if strict else "wrong_state"
    return cal.EpisodeRecord(
        task_id=task_id, arm_id=arm, model=MODEL_A, seed=seed, attempt=attempt,
        strict=strict, leaky=strict if leaky is None else leaky, label=label,
        turns=turns, sampled_calls=sampled_calls, prompt_tokens=prompt_tokens,
        cached_input_tokens=0, completion_tokens=completion_tokens, reasoning_tokens=0,
    )


def provenance(**over: Any) -> cal.Provenance:
    seeds = list(range(1000, 1000 + S))
    base: dict[str, Any] = {
        "package_version": "0.1.0",
        "engine_hash": "e" * 64,
        "generator_hash": "g" * 64,
        "vocabulary_hash": "v" * 64,
        "verifiers_version": "0.3.1",
        "harness_id": "null",
        "models": [{"id": MODEL_A, "revision": MODEL_A, "endpoint_host": "api.openai.com"}],
        "decoding": dict(cal.DECODING),
        "seed_list": seeds,
        "seed_list_hash": hashlib.sha256(json.dumps(seeds).encode("utf-8")).hexdigest(),
        "S": S,
        "n": N,
        "k_values": [1, 2, 5],
        "bootstrap_resamples": 200,
        "bootstrap_seed": 20260922,
        "delta_star": 0.15,
        "saturation_high": 0.95,
        "saturation_low": 0.05,
        "instrument_threshold": 0.02,
        "rate_read_date": "2026-09-25",
        "serving": {MODEL_A: {"kind": "hosted", "endpoint_host": "api.openai.com"}},
        "budget": dict(cal.DEFAULT_BUDGET),
    }
    base.update(over)
    return cal.Provenance(**base)


def calls_cell(calls: Sequence[int], *, arm: str = "depth:d3") -> list[cal.EpisodeRecord]:
    """One task per entry of `calls`, `N` attempts each, every attempt making that many tool
    calls.  Every attempt at a task with no call is a clarification reply, `wrong_state`."""
    out: list[cal.EpisodeRecord] = []
    for index, made in enumerate(calls):
        for attempt in range(N):
            out.append(record(task_id=f"t{index:03d}", seed=1000 + index, attempt=attempt,
                              arm=arm, strict=made > 0 and attempt == 0, sampled_calls=made))
    return out


def table(document: str, heading: str) -> list[str]:
    """The markdown table lines under the first `### heading`."""
    lines = document.splitlines()
    start = lines.index(heading)
    out: list[str] = []
    for line in lines[start + 1:]:
        if line.startswith("|"):
            out.append(line)
        elif out:
            break
    return out


def columns_of(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


# ---------------------------------------------------------------------------
# ruling 1: the record id and the entry code go out in quotes
# ---------------------------------------------------------------------------


def user_text(prompt: Any) -> str:
    """The user-facing text of a bundle's prompt: the string itself, or every user message
    of a seeded history (knob D's controls)."""
    if isinstance(prompt, str):
        return prompt
    return "\n".join(str(message.get("content")) for message in prompt
                     if message.get("role") == "user")


@pytest.mark.parametrize("spec", cal.arm_specs(), ids=lambda spec: arm_id(spec))
def test_fix1_1_every_arms_prompt_quotes_the_record_id_and_the_entry_code(spec: ArmSpec) -> None:
    """Ruling 1, at every one of the fourteen arms: the value the model has to copy is
    delimited, so it cannot be read as a word of the sentence."""
    for seed in cal.DOCUMENTED_SEEDS:
        bundle = generate(spec, seed)
        slots = dict(bundle.prompt_slots)
        text = user_text(bundle.prompt)
        assert f'"{slots["record_id"]}"' in text, text
        assert f'"{slots["entry_code"]}"' in text, text


def test_fix1_2_the_slots_carry_the_bare_values_and_the_template_id_is_unchanged() -> None:
    """Ruling 1's other half and ruling 2: the quotes are the template's, not the value's.
    The slot is what G15 masks and what the ledger checks, so it stays the bare word, and
    `template_id` stays `ledger-chain/v1` (the generator hash records the change)."""
    bundle = generate(spec_of("depth", 3), 404)
    slots = dict(bundle.prompt_slots)
    assert '"' not in slots["record_id"] and '"' not in slots["entry_code"], slots
    assert bundle.template_id == "ledger-chain/v1"
    assert any(slots["entry_code"] in str(call) for call in bundle.reference_calls[:1]), (
        slots, bundle.reference_calls[:1])


@contextlib.contextmanager
def recording_endpoint() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """An OpenAI-compatible chat endpoint on loopback that ends every episode on its first
    turn and keeps each request body whole."""
    bodies: list[dict[str, Any]] = []

    class Stub(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            bodies.append(body)
            out = {
                "id": "chatcmpl-stub", "object": "chat.completion", "created": 0,
                "model": body.get("model"),
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": "Done."}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
            data = json.dumps(out).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", bodies
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.skipif(
    shutil.which("uv") is None, reason="the `null` harness launches its program through uv"
)
def test_fix1_3_the_served_task_carries_the_record_id_and_the_entry_code_in_quotes() -> None:
    """**The test that fails on today's prompt, at the point the model reads it.**  One
    calibration episode through the wheel, with `run_config_for`'s sampling, against a
    loopback endpoint that keeps the request: the user message the model receives carries
    both values in double quotes."""
    import verifiers.v1 as vf

    spec = spec_of("depth", 3)
    bundle = generate(spec, 404)
    slots = dict(bundle.prompt_slots)
    _, calibration = cal.run_config_for(spec, model=MODEL_A)
    config = vf.resolve_env_config({
        "taskset": {"id": cal.TASKSET_ID, "arm": dataclasses.asdict(spec), "seeds": [404]}
    })
    env = vf.load_environment(config)
    task = next(iter(env.taskset.load()))
    saved = os.environ.get(KEY_VAR)
    os.environ[KEY_VAR] = "stub-secret"
    try:
        with recording_endpoint() as (base_url, bodies):
            ctx = vf.ModelContext(
                model=MODEL_A,
                client=vf.EvalClientConfig(base_url=base_url, api_key_var=KEY_VAR),
                sampling=calibration.sampling,
            )

            async def run() -> Any:
                async with env.serving():
                    return await env.run_episode(task, ctx)

            episode = asyncio.run(run())
    finally:
        if saved is None:
            os.environ.pop(KEY_VAR, None)
        else:
            os.environ[KEY_VAR] = saved
    assert episode.ok, episode.errors
    assert bodies, "the episode sent no request"
    served = "\n".join(str(message.get("content")) for message in bodies[0]["messages"]
                       if message.get("role") == "user")
    assert f'"{slots["record_id"]}"' in served, served
    assert f'"{slots["entry_code"]}"' in served, served


# ---------------------------------------------------------------------------
# ruling 3: the plumbing gate
# ---------------------------------------------------------------------------


def todays_phase1() -> list[cal.EpisodeRecord]:
    """The six records of the decoding fix's phase 1 re-run (2026-09-25, `8470a1a`), as they
    were written to its `episodes.jsonl`: depth d3, seeds 404, 55 and 2121, two attempts
    each.  Five replies asked for the record id and the entry code and called no tool; the
    sixth made 8 calls and overshot.  It passed the gate it had, which checked scoring and
    instrument labels only."""
    rows = [
        # (seed, attempt, sampled_calls, turns, label, leaky)
        (404, 0, 0, 1, "wrong_state", False),
        (404, 1, 0, 1, "wrong_state", False),
        (55, 0, 0, 1, "wrong_state", False),
        (55, 1, 0, 1, "wrong_state", False),
        (2121, 0, 0, 1, "wrong_state", False),
        (2121, 1, 8, 9, "overshoot", True),
    ]
    return [
        record(task_id=f"task-{seed}", seed=seed, attempt=attempt, arm="depth:d3",
               sampled_calls=calls, turns=turns, label=label, leaky=leaky)
        for seed, attempt, calls, turns, label, leaky in rows
    ]


def test_fix3_1_todays_phase1_fails_the_gate() -> None:
    """Ruling 3's own motivating case: 5 of 6 episodes made no tool call.  Every one was
    scored and none carried an instrument label, so the old gate passed it."""
    rows = todays_phase1()
    assert all(row.label not in cal.INSTRUMENT_LABELS for row in rows)
    verdict = cal.plumbing_gate(rows)
    assert verdict.passed is False
    assert verdict.no_call == 5
    assert verdict.reached_minimum == 1
    assert verdict.episodes == 6
    joined = " ".join(verdict.reasons).lower()
    assert "no tool call" in joined, verdict.reasons


def test_fix3_2_every_episode_calling_and_reaching_the_minimum_passes() -> None:
    """The gate's control: without it a gate that always fails is green on 3_1."""
    rows = [record(task_id=f"t{i}", seed=i, attempt=a, arm="depth:d3", sampled_calls=3)
            for i in range(3) for a in range(2)]
    verdict = cal.plumbing_gate(rows)
    assert verdict.passed is True, verdict.reasons
    assert verdict.reasons == ()


def test_fix3_3_one_episode_with_no_call_fails_even_when_the_rest_reach_the_minimum() -> None:
    """"every episode makes at least one tool call": one silent episode is enough."""
    rows = [record(task_id=f"t{i}", seed=i, attempt=0, arm="depth:d3", sampled_calls=5)
            for i in range(5)]
    rows.append(record(task_id="t5", seed=5, attempt=0, arm="depth:d3", sampled_calls=0))
    verdict = cal.plumbing_gate(rows)
    assert verdict.passed is False
    assert verdict.no_call == 1


def test_fix3_4_exactly_half_at_the_minimum_passes_and_fewer_fails() -> None:
    """"at least half reach their structural minimum": the boundary is inclusive, and the
    minimum is the arm's own (3 at d3), so a call count between 1 and 2 starts but falls
    short."""
    half = [record(task_id=f"t{i}", seed=i, attempt=0, arm="depth:d3",
                   sampled_calls=3 if i < 3 else 2) for i in range(6)]
    verdict = cal.plumbing_gate(half)
    assert verdict.passed is True, verdict.reasons
    assert verdict.reached_minimum == 3
    short = [record(task_id=f"t{i}", seed=i, attempt=0, arm="depth:d3",
                    sampled_calls=3 if i < 2 else 2) for i in range(6)]
    verdict = cal.plumbing_gate(short)
    assert verdict.passed is False
    assert verdict.reached_minimum == 2
    assert "minimum" in " ".join(verdict.reasons).lower(), verdict.reasons


def test_fix3_5_the_minimum_is_read_per_arm() -> None:
    """d8's minimum is 8 and a distractor arm's is `d_R` = 2: 3 calls reaches the second and
    not the first."""
    d8 = [record(task_id=f"t{i}", seed=i, attempt=0, arm="depth:d8", sampled_calls=3)
          for i in range(4)]
    assert cal.plumbing_gate(d8).passed is False
    r4 = [record(task_id=f"t{i}", seed=i, attempt=0, arm="distractor:r4@k16", sampled_calls=3)
          for i in range(4)]
    assert cal.plumbing_gate(r4).passed is True


def test_fix3_6_the_earlier_conditions_still_hold() -> None:
    """The gate the phase 1 pass already had stays in it: an instrument label, a non-empty
    tally, or no records at all fails."""
    good = [record(task_id=f"t{i}", seed=i, attempt=0, arm="depth:d3", sampled_calls=3)
            for i in range(4)]
    assert cal.plumbing_gate(good).passed is True
    labelled = [*good, record(task_id="t9", seed=9, attempt=0, arm="depth:d3",
                              label="api_error", sampled_calls=3)]
    assert cal.plumbing_gate(labelled).passed is False
    assert cal.plumbing_gate(good, tally={"api_error": 1}).passed is False
    assert cal.plumbing_gate([]).passed is False


def test_fix3_7_the_verdict_lists_each_episodes_calls_against_its_minimum() -> None:
    """The report names every episode's tool calls against its minimum, so a pass is
    readable and not a single bit."""
    verdict = cal.plumbing_gate(todays_phase1())
    assert [(row["seed"], row["attempt"], row["tool_calls"], row["minimum_calls"])
            for row in verdict.per_episode] == [
        (404, 0, 0, 3), (404, 1, 0, 3), (55, 0, 0, 3), (55, 1, 0, 3),
        (2121, 0, 0, 3), (2121, 1, 8, 3),
    ]


# ---------------------------------------------------------------------------
# ruling 4: CAL24, the no-call and stopped-short columns and the publish refusal
# ---------------------------------------------------------------------------


def test_cal24_1_a_cell_above_the_no_call_threshold_refuses_to_publish() -> None:
    """Three of twenty tasks never start: 0.15 of the scored episodes made no tool call,
    above 0.10, so the cell refuses, the way CAL16 refuses above the instrument threshold."""
    cell = calls_cell([0, 0, 0] + [3] * 17)
    with pytest.raises(ValueError) as caught:
        cal.build_artifact({("depth:d3", MODEL_A): cell}, provenance())
    message = str(caught.value).lower()
    assert "no tool call" in message and "0.150" in message, message


def test_cal24_2_a_cell_at_the_threshold_publishes_with_its_shares() -> None:
    """The control, at the boundary: exactly 0.10 is not above 0.10.  The figures carry the
    no-call share and the stopped-short share, which are disjoint: stopped short is started
    and below the minimum."""
    cell = calls_cell([0, 0] + [1] * 3 + [2] * 2 + [3] * 13)
    figures = cal.build_artifact({("depth:d3", MODEL_A): cell}, provenance()).cells[0]
    assert figures["no_call_share"] == pytest.approx(0.10)
    assert figures["stopped_short_share"] == pytest.approx(5 / 20)
    assert figures["no_call_count"] == 2 * N
    assert figures["stopped_short_count"] == 5 * N


def test_cal24_3_the_share_is_over_scored_episodes() -> None:
    """An instrument failure made no call because the call failed, not because the model
    did not start.  It leaves the denominator here as it does for pass@1 (CAL16), in the
    published share and in the refusal: one task in twenty never starts (0.05 of the scored
    episodes), and ten failed calls with no tool call would lift a share over every episode
    to 15 of 110, above 0.10."""
    cell = calls_cell([0] + [3] * 19)
    for attempt in range(10):
        cell.append(record(task_id="t001", seed=1001, attempt=N + attempt, arm="depth:d3",
                           label="api_error", sampled_calls=0))
    assert sum(1 for row in cell if row.sampled_calls == 0) / len(cell) > 0.10
    figures = cal.build_artifact(
        {("depth:d3", MODEL_A): cell}, provenance(instrument_threshold=0.5)
    ).cells[0]
    assert figures["no_call_share"] == pytest.approx(0.05)
    assert figures["no_call_count"] == N


def test_cal24_4_the_threshold_is_declared_and_carried_in_the_provenance() -> None:
    """0.10 is Taylor's number (ruling 4).  It is carried in the block, like CAL16's, so a
    card says what it was held to, and it is a rate."""
    assert cal.NO_CALL_THRESHOLD == 0.10
    block = provenance()
    assert block.no_call_threshold == 0.10
    assert block.as_dict()["no_call_threshold"] == 0.10
    with pytest.raises(ValueError):
        provenance(no_call_threshold=1.5)
    loose = provenance(no_call_threshold=0.2)
    cell = calls_cell([0, 0, 0] + [3] * 17)
    assert cal.build_artifact({("depth:d3", MODEL_A): cell}, loose).cells[0][
        "no_call_share"] == pytest.approx(0.15)


def test_cal24_5_the_card_prints_both_shares_in_their_columns() -> None:
    """The two columns are on every level row and every instrument-arm row, read by the
    position the header gives them, not by searching the row (the lesson of m56)."""
    cells = {}
    for spec in cal.arm_specs():
        arm = arm_id(spec)
        minimum = spec.level if spec.knob == "depth" else cal.D_R
        started_short = max(1, minimum - 1) if minimum > 1 else minimum
        cells[(arm, MODEL_A)] = calls_cell([0] + [started_short] * 4 + [minimum] * 15, arm=arm)
    artifact = cal.build_artifact(cells, provenance())
    document = cal.render_document(artifact)
    for heading in ("### depth", "### distractor"):
        lines = table(document, heading)
        columns = [column.lower() for column in columns_of(lines[0])]
        assert "no tool call" in columns and "stopped short" in columns, columns
        no_at, short_at = columns.index("no tool call"), columns.index("stopped short")
        for line in lines[2:]:
            values = columns_of(line)
            assert len(values) == len(columns), line
            figures = next(cell for cell in artifact.cells
                           if f"`{cell['arm_id']}`" == values[0])
            assert values[no_at] == f"{figures['no_call_share']:.3f}", line
            assert values[short_at] == f"{figures['stopped_short_share']:.3f}", line
    instrument = document.partition(cal.INSTRUMENT_TABLE_HEADING)[2]
    header = next(line for line in instrument.splitlines() if line.startswith("| arm |"))
    assert "no tool call" in header.lower() and "stopped short" in header.lower()
    d8 = next(cell for cell in artifact.cells if cell["arm_id"] == "depth:d8")
    assert d8["no_call_share"] == pytest.approx(0.05)
    assert d8["stopped_short_share"] == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# ruling 5: knob D's ordering on the leaky rate beside the strict one
# ---------------------------------------------------------------------------

# Per depth level: (strict passes, leaky passes) per task, of N.  Strict dips then rises at
# d8, where overshoot is impossible; leaky falls steadily.  The d1 to d5 gap is overshoot.
DEPTH_PROFILE = {1: (1, 5), 2: (1, 5), 3: (1, 4), 5: (0, 4), 8: (3, 3)}


def depth_cells() -> dict[tuple[str, str], list[cal.EpisodeRecord]]:
    cells: dict[tuple[str, str], list[cal.EpisodeRecord]] = {}
    for level in levels("depth"):
        strict_n, leaky_n = DEPTH_PROFILE[level]
        arm = arm_id(spec_of("depth", level))
        rows: list[cal.EpisodeRecord] = []
        for index in range(8):
            for attempt in range(N):
                if attempt < strict_n:
                    label, strict, leaky = "passed", True, True
                elif attempt < leaky_n:
                    label, strict, leaky = "overshoot", False, True
                else:
                    label, strict, leaky = "wrong_state", False, False
                rows.append(record(task_id=f"d{level}-{index}", seed=1000 + index,
                                   attempt=attempt, arm=arm, strict=strict, leaky=leaky,
                                   label=label, sampled_calls=level))
        cells[(arm, MODEL_A)] = rows
    return cells


def test_fix5_1_the_depth_ordering_row_carries_the_leaky_rates() -> None:
    """The artifact's ordering row for knob D carries leaky pass@1 across the axis and its
    own non-increasing flag beside the strict ones, which are unchanged."""
    artifact = cal.build_artifact(depth_cells(), provenance())
    row = next(r for r in artifact.orderings if r["kind"] == "ordering" and r["knob"] == "depth")
    axis = list(levels("depth"))
    assert row["levels"] == axis
    assert row["pass_at_1"] == pytest.approx([DEPTH_PROFILE[lvl][0] / N for lvl in axis])
    assert row["non_increasing"] is False
    assert row["leaky_at_1"] == pytest.approx([DEPTH_PROFILE[lvl][1] / N for lvl in axis])
    assert row["leaky_non_increasing"] is True


def test_fix5_2_the_card_shows_leaky_beside_strict_with_the_stop_at_goal_note() -> None:
    """On the card: the strict line first (R15's headline), the leaky line beside it, and a
    sentence saying strict below the top depth includes a stop-at-the-goal test the top
    cannot have."""
    document = cal.render_document(cal.build_artifact(depth_cells(), provenance()))
    ordering = document.partition("## Ordering")[2].partition("## Provenance")[0]
    lowered = ordering.lower()
    strict_at = lowered.index("strict pass@1 across levels")
    leaky_at = lowered.index("leaky pass@1 across levels")
    assert strict_at < leaky_at, ordering
    leaky_line = next(line for line in ordering.splitlines()
                      if "leaky pass@1 across levels" in line.lower())
    assert "1.000, 1.000, 0.800, 0.800, 0.600" in leaky_line, leaky_line
    assert "non-increasing: yes" in leaky_line.lower(), leaky_line
    assert "stop" in lowered and "goal" in lowered, ordering
    assert "d1 to d5" in lowered and "d8" in lowered, ordering


# ---------------------------------------------------------------------------
# the two figures named for what they count
# ---------------------------------------------------------------------------


def test_labels_1_the_artifact_names_tool_calls_and_model_calls() -> None:
    """`sampled_calls` on a record is the export's metric of that name, the number of tool
    calls; `turns` is `trace.num_turns`, the number of model calls.  The artifact publishes
    them under those names, and not under names that read as each other."""
    cell = calls_cell([3] * 20)
    figures = cal.build_artifact({("depth:d3", MODEL_A): cell}, provenance()).cells[0]
    assert figures["tool_calls"] == 3 * 20 * N
    assert figures["model_calls"] == 4 * 20 * N
    assert figures["model_calls_median"] == 4
    for old in ("sampled_calls", "turns", "turns_median"):
        assert old not in figures, old


def test_labels_2_the_cost_table_says_model_calls() -> None:
    cell = calls_cell([3] * 20)
    document = cal.render_document(
        cal.build_artifact({("depth:d3", MODEL_A): cell}, provenance()))
    cost = document.partition("## Cost per episode")[2].partition("## Adjacent levels")[0]
    assert "median model calls" in cost.lower(), cost
    assert "median turns" not in document.lower()
