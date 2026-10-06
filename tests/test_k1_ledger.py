"""The pin ledger grown to thirty rows for the seven new knobs, frozen as tests.

The ledger is what holds a knob's levels equal in everything but the knob.  The new knobs bring
seventeen rows, N19 to N35, and the old thirteen keep their text.  Every new row is measured on
every bundle from the fields the ledger already reads (the arm id, the tools, the prompt, the
system prompt, the reference calls and their observations), and only N10 and N13 stay
unmeasured.  `tests/test_tg_m2_knobs.py` pins each row's id, place, stage, action and the knobs it
applies to; this file pins what each new row measures, when it holds and when it refuses, and
the old rows' three recorded exceptions.

How the bundles are made
------------------------

The generator does not make the new knobs' tasks yet.  So each test builds them the way the
knob's design says the generator will, from one real task of the base design
(`distractor:r0@k16` at seed 404, whose two right tools sit in slots 0 and 2): renamed tools for
similarity, retried calls answering `unavailable` for faults, seeded read pairs for history and
the faults control, more tools for block, optional parameters and stated values for arguments,
four stage calls for shape, and four named reads for spread.  Observations come from the engine,
or are written in its own layout where the knob answers in front of it.  Each knob's clean
contrast refuses nothing, and each refusal test changes one thing in it, so a row that refuses
is refusing for that change.

Shapes decided here
-------------------

**1. Which tools are the right tools.**  The tools the reference solution calls, in the order it
first calls them.  The target ledger's number is the four-digit number in the first one's name;
a lookalike is a tool whose name carries any other four-digit number.

**2. N24's "a read tool".**  A tool the engine answers as a read.  The knobs that seed history
(history, and the faults control) seed it from the base task's block, whose reads are the
engine's own.

**3. N25's plan.**  The planned failures of each right tool, counted as the `unavailable`
answers among its reference observations; the level split over the right tools as evenly as it
goes, the earlier taking the extra, so with two the first stage takes the odd one.

**4. The control rows compare a control with the high arm it stands in for**, when that arm is
in the contrast, as N9 does: N26 the control's seeded pairs against the high arm's failed calls
(less any the control fails itself); N29 the control's system-prompt filler against the high
arm's extra block; N32 and N34 the control's whole request against the high arm's.  Every
"plus or minus two tokens" is the same band.

**5. Rows that report as well as refuse.**  N29 and N33 carry the action `refuse`, which is what
a caller acting on the row needs to know; the block's growth they report goes in the report's
`reported` list beside any refusal.  N7 on a shape contrast goes in `reported`, never in
`violations`.

**6. The knob's own prompt slots.**  The user-prompt row (N6) leaves out the slot named
`stated_values` on an arguments arm and `goal_lines` on a shape arm, the slots that are the knob;
on any other knob a difference there refuses.
"""

from __future__ import annotations

import ast
import dataclasses
import gzip
import hashlib
import json
import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks.arms import arm_from_id
from poisson_tasks.engine import EngineSpec, apply, init_state
from poisson_tasks.knobs import check_pins, measure_pins, pin_ledger
from poisson_tasks.tasks import generate, scenario_for
from poisson_tasks.tokenizer import count_tokens

from tests.helpers import INTERNAL

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "k1" / "published-tasks.json.gz"
SPEC = EngineSpec.load()
LAYOUT = SPEC.layout
SEED = 404
BASE_ARM = "distractor:r0@k16"
KNOBS = ("depth", "distractor", "similarity", "faults", "history", "block", "arguments",
         "shape", "spread")
TARGET_NUMBER = "4417"
FILLER = ("quiet", "plain", "steady", "gentle", "narrow", "hollow", "silver", "distant")
EXTRAS = (("lot_code", "amber"), ("batch_code", "pearl"), ("bin_code", "walnut"),
          ("crate_code", "willow"), ("dock_code", "ember"), ("bay_code", "jasper"))
PATTERN = re.compile(INTERNAL.pattern + r"|\bKC\d+\b|\bVN-\d+\b|\(\d\.\d\b")


# --------------------------------------------------------------------------
# what the new knobs' bundles look like
# --------------------------------------------------------------------------


@lru_cache(maxsize=1)
def base() -> Any:
    bundle = generate(arm_from_id(BASE_ARM), SEED)
    names = [tool["name"] for tool in bundle.tools]
    assert [names.index(call[0]) for call in bundle.reference_calls] == [0, 2]
    return bundle


def line(seq: int, status: str, payload: str) -> str:
    """An observation in the engine's own fixed-width layout."""
    return str(LAYOUT["separator"]).join((
        str(seq).rjust(LAYOUT["seq_width"], LAYOUT["seq_fill"]),
        status.ljust(LAYOUT["status_width"], LAYOUT["status_fill"]),
        payload,
    ))


def schema(name: str, description: str | None = None,
           extra: tuple[str, ...] = ()) -> dict[str, Any]:
    """An engine tool's schema as a block carries it, optionally renamed or widened."""
    tool = next(t for t in SPEC.tools if t.name == name)
    params = sorted(tool.parameters)
    return {
        "name": name,
        "description": tool.description if description is None else description,
        "parameters": {
            "type": "object",
            "properties": {p: {"type": "string"} for p in sorted((*params, *extra))},
            "required": params,
            "additionalProperties": False,
        },
    }


def at(bundle: Any, arm: str, **fields: Any) -> Any:
    return dataclasses.replace(bundle, arm_id=arm, **fields)


def failed(report: Any) -> set[str]:
    return {row for row, _detail in report.violations}


def reported(report: Any) -> set[str]:
    return {row for row, _detail in report.reported}


def contrast(*bundles: Any) -> Any:
    return check_pins({bundle.arm_id: bundle for bundle in bundles})


def instruction(bundle: Any) -> str:
    return bundle.prompt if isinstance(bundle.prompt, str) else bundle.prompt[0]["content"]


def with_filler(text: str, tokens: int) -> str:
    """`text` with neutral words appended until it is exactly `tokens` tokens longer."""
    want = count_tokens(text) + tokens
    words: list[str] = []
    while count_tokens(text + "\n\n" + " ".join(words)) < want:
        words.append(FILLER[len(words) % len(FILLER)])
    out = text + "\n\n" + " ".join(words)
    assert count_tokens(out) == want, (count_tokens(out), want)
    return out


def read_options(seq: int, reads: tuple[str, ...]) -> dict[int, tuple[str, dict[str, str], str]]:
    """One read pair per reachable token total, at sequence number `seq`."""
    scenario = scenario_for(SEED, "eval")
    state = dataclasses.replace(init_state(scenario, 1), next_seq=seq)
    options: dict[int, tuple[str, dict[str, str], str]] = {}
    for name in reads:
        for item in SPEC.table["catalogue_items"]:
            for page in sorted(SPEC.page_keys):
                args = {"item_code": item, "page_key": page}
                _after, obs = apply(state, (name, args))
                if obs.split()[1] == "ok":
                    total = (count_tokens(name) + count_tokens(json.dumps(args, separators=(",", ":")))
                             + count_tokens(obs))
                    options.setdefault(total, (name, args, obs))
    return options


def seeded(total: int, reads: tuple[str, ...]) -> list[tuple[str, dict[str, str], str]]:
    """Read pairs whose tokens sum to exactly `total`, as few as reach it."""
    if total == 0:
        return []
    count = max(1, round(total / 58))
    rows = [read_options(index + 1, reads) for index in range(count)]
    chosen = [sorted(row)[len(row) // 2] for row in rows]
    for _ in range(4000):
        residual = sum(chosen) - total
        if residual == 0:
            break
        step = -1 if residual > 0 else 1
        for index, row in enumerate(rows):
            if chosen[index] + step in row:
                chosen[index] += step
                break
        else:
            raise AssertionError(f"no read pairs total {total}")
    return [rows[index][value] for index, value in enumerate(chosen)]


def messages(text: str, pairs: list[tuple[str, dict[str, str], str]]) -> Any:
    if not pairs:
        return text
    out: list[dict[str, Any]] = [{"role": "user", "content": text}]
    for index, (name, args, obs) in enumerate(pairs):
        out.append({"role": "assistant", "tool_calls": [{
            "id": f"call_{index}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, separators=(",", ":"))}}]})
        out.append({"role": "tool", "tool_call_id": f"call_{index}", "content": obs})
    return tuple(out)


def reads_of(bundle: Any) -> tuple[str, ...]:
    return tuple(t["name"] for t in bundle.tools if t["name"] in SPEC.read_tools)


# similarity ---------------------------------------------------------------


def numbers_at(level: int, count: int = 6, skip: int = 0) -> list[str]:
    """`count` distinct four-digit numbers sharing exactly `level` digits in place with the
    target's, none starting with 0."""
    out = []
    for n in range(1000 + skip, 10000):
        text = str(n)
        if sum(a == b for a, b in zip(text, TARGET_NUMBER)) == level and text not in out:
            out.append(text)
        if len(out) == count:
            return out
    raise AssertionError(level)


def numbered(name: str, number: str) -> dict[str, Any]:
    """An engine stage tool shown under a ledger number in its name and its description."""
    tool = schema(name)
    cls = SPEC.stage_tools[name][1]
    tool["name"] = name.rsplit("_", 1)[0] + "_" + number
    tool["description"] = (tool["description"].replace(f"a {cls} record", f"a ledger {number} record")
                           .replace(f"_{cls}", f"_{number}"))
    return tool


def similarity(level: int, numbers: list[str] | None = None) -> Any:
    b = base()
    review, sample = (call[0] for call in b.reference_calls)
    others = numbers if numbers is not None else numbers_at(level)
    lookalikes = [numbered(name, number) for number in others for name in (review, sample)]
    right = [numbered(review, TARGET_NUMBER), numbered(sample, TARGET_NUMBER)]
    reads = [t for t in b.tools if t["name"] in SPEC.read_tools][:2]
    tools = [right[0], lookalikes[0], right[1], *lookalikes[1:], *reads]
    cls = b.goal[0]
    rename = {review: right[0]["name"], sample: right[1]["name"]}
    calls = tuple((rename[name], args) for name, args in b.reference_calls)
    text = instruction(b).replace(f"of the {cls} ledger", f"of ledger {TARGET_NUMBER}")
    slots = tuple(("ledger_number", TARGET_NUMBER) if k == "ledger_class" else (k, v)
                  for k, v in b.prompt_slots)
    return at(b, f"similarity:s{level}", tools=tuple(tools), reference_calls=calls, prompt=text,
              template_id="ledger-number/v1", prompt_slots=slots)


# faults -------------------------------------------------------------------


def faulted(plan: tuple[int, ...], seq_start: int = 1) -> tuple[tuple[Any, ...], tuple[str, ...]]:
    """The base reference solution with each right tool failing `plan[i]` times first."""
    b = base()
    state = init_state(scenario_for(SEED, "eval"), seq_start)
    calls: list[Any] = []
    observations: list[str] = []
    for (name, args), fails in zip(b.reference_calls, plan, strict=True):
        for _ in range(fails):
            calls.append((name, args))
            observations.append(line(state.next_seq, "unavailable", LAYOUT["error_payload"]))
            state = dataclasses.replace(state, next_seq=state.next_seq + 1)
        state, obs = apply(state, (name, args))
        calls.append((name, args))
        observations.append(obs)
    return tuple(calls), tuple(observations)


def fault_tokens(level: int) -> int:
    calls, observations = faulted(split(level))
    return sum(
        count_tokens(name) + count_tokens(json.dumps(args, separators=(",", ":")))
        + count_tokens(obs)
        for (name, args), obs in zip(calls, observations, strict=True)
        if obs.split()[1] == "unavailable"
    )


def split(level: int) -> tuple[int, int]:
    return ((level + 1) // 2, level // 2)


def faults(level: int, plan: tuple[int, ...] | None = None) -> Any:
    calls, observations = faulted(plan if plan is not None else split(level))
    return at(base(), f"faults:f{level}", reference_calls=calls,
              reference_observations=observations)


def faults_control(high: int = 4, off: int = 0, pairs: Any = None) -> Any:
    b = base()
    chosen = pairs if pairs is not None else seeded(fault_tokens(high) + off, reads_of(b))
    calls, observations = faulted((0, 0), seq_start=len(chosen) + 1)
    return at(b, f"faults:f0+len(f{high})", prompt=messages(instruction(b), chosen),
              seq_start=len(chosen) + 1, reference_calls=calls,
              reference_observations=observations)


# history ------------------------------------------------------------------


def history(level: int, total: int | None = None, pairs: Any = None) -> Any:
    b = base()
    chosen = pairs if pairs is not None else seeded(level if total is None else total,
                                                    reads_of(b))
    calls, observations = faulted((0, 0), seq_start=len(chosen) + 1)
    return at(b, f"history:t{level}", prompt=messages(instruction(b), chosen),
              seq_start=len(chosen) + 1, reference_calls=calls,
              reference_observations=observations)


# block --------------------------------------------------------------------


def aliases() -> list[dict[str, Any]]:
    """Read copies under (verb, facet) names the table does not use."""
    table = set(SPEC.read_tools)
    out = []
    for verb in SPEC.table["read_verbs"]:
        for facet in SPEC.table["facets"]:
            name = f"{verb}_{facet}"
            if name not in table:
                tool = schema(next(iter(SPEC.read_tools)))
                tool["name"] = name
                tool["description"] = f"{verb.capitalize()}s the {facet} field of the named catalogue item"
                out.append(tool)
    return out


def block_tools(size: int) -> tuple[dict[str, Any], ...]:
    tools = list(base().tools) + aliases()
    return tuple(tools[:size])


def block(level: int, tools: Any = None) -> Any:
    return at(base(), f"block:k{level}",
              tools=block_tools(level) if tools is None else tuple(tools))


def rendered_tokens(tools: Any) -> int:
    return count_tokens(json.dumps(list(tools), sort_keys=True, separators=(",", ":")))


def block_control(high: int = 64, off: int = 0) -> Any:
    b = base()
    extra = rendered_tokens(block_tools(high)) - rendered_tokens(block_tools(8))
    return at(b, f"block:k8+len(k{high})", tools=block_tools(8),
              system_prompt=with_filler(b.system_prompt, extra + off))


# arguments ----------------------------------------------------------------


def arguments(level: int, stated: int | None = None, per_call: Any = None,
              text_values: Any = None) -> Any:
    b = base()
    count = level - 2 if stated is None else stated
    names = tuple(name for name, _value in EXTRAS)
    tools = tuple(schema(t["name"], t["description"], names) if t["name"] in
                  {call[0] for call in b.reference_calls} else t for t in b.tools)
    carried = dict(EXTRAS[:count])
    calls = []
    for index, (name, args) in enumerate(b.reference_calls):
        extra = carried if per_call is None else per_call[index]
        calls.append((name, {**args, **extra}))
    values = carried if text_values is None else text_values
    stated_text = ", ".join(f'{key.replace("_", " ")} "{value}"' for key, value in values.items())
    text = instruction(b) + (f"\nCarry {stated_text}." if stated_text else "")
    slots = b.prompt_slots + (("stated_values", stated_text),)
    return at(b, f"arguments:a{level}", tools=tools, reference_calls=tuple(calls), prompt=text,
              prompt_slots=slots)


def arguments_control(high: int = 8, off: int = 0) -> Any:
    low = arguments(2)
    target = count_tokens(instruction(arguments(high)))
    text = with_filler(instruction(low), target - count_tokens(instruction(low)) + off)
    return at(low, f"arguments:a2+len(a{high})", prompt=text)


# shape --------------------------------------------------------------------


def stage_tool(cls: str, index: int) -> str:
    return next(n for n, (i, q) in SPEC.stage_tools.items() if q == cls and i == index)


def shape(width: int, calls_made: int = 4, size: int = 16) -> Any:
    b = base()
    cls, record, _goal = b.goal
    decoy = next(r for c, r, _s, _t in b.initial_state if c == cls and r != record)
    scenario = scenario_for(SEED, "eval")
    if width == 1:
        plan = [(cls, record, index) for index in range(4)]
    elif width == 2:
        plan = [(cls, record, 0), (cls, record, 1), (cls, decoy, 0), (cls, decoy, 1)]
    else:
        others = [q for q in SPEC.qualifiers if q != cls][:3]
        plan = [(q, record, 0) for q in (cls, *others)]
    state = init_state(scenario, 1)
    calls: list[Any] = []
    observations: list[str] = []
    tokens: dict[tuple[str, str], str] = {}
    for q, r, index in plan[:calls_made]:
        name = stage_tool(q, index)
        if index == 0:
            args = {"record_id": r, "entry_code": scenario.records[(q, r)]}
        else:
            args = {"record_id": r, "chain_token": tokens[(q, r)]}
        state, obs = apply(state, (name, args))
        tokens[(q, r)] = obs.split()[2]
        calls.append((name, args))
        observations.append(obs)
    stage_names = list(dict.fromkeys(stage_tool(q, i) for q, _r, i in plan))
    reads = [t for t in b.tools if t["name"] in SPEC.read_tools]
    tools = [schema(name) for name in stage_names] + reads
    last: dict[tuple[str, str], int] = {}
    for q, r, i in plan:
        last[(q, r)] = i
    goals = "\n".join(f"Raise {r} of the {q} ledger through {SPEC.stage_names[i]}."
                      for (q, r), i in last.items())
    return at(b, f"shape:w{width}", tools=tuple(tools[:size]), reference_calls=tuple(calls),
              reference_observations=tuple(observations), prompt=instruction(b) + "\n" + goals,
              prompt_slots=b.prompt_slots + (("goal_lines", goals),))


def shape_control(off: int = 0) -> Any:
    low = shape(1)
    tokens = count_tokens(instruction(shape(4))) - count_tokens(instruction(low)) + off
    return at(low, "shape:w1+len(w4)", prompt=with_filler(instruction(low), tokens))


# spread -------------------------------------------------------------------


def parts_of(code: str, level: int) -> list[str]:
    size, extra = divmod(len(code), level)
    out, start = [], 0
    for index in range(level):
        length = size + (1 if index < extra else 0)
        out.append(code[start:start + length])
        start += length
    return out


def answer(part: str, salt: str) -> str:
    head = (part or "none") + "."
    fill = hashlib.sha256(salt.encode()).hexdigest()
    return head + fill[: LAYOUT["payload_width"] - len(head)]


def spread(level: int, parts: list[str] | None = None, named: Any = None) -> Any:
    b = base()
    code = dict(b.prompt_slots)["entry_code"]
    held = parts if parts is not None else parts_of(code, level) + [""] * (4 - level)
    reads = named if named is not None else [
        (name, {"item_code": SPEC.table["catalogue_items"][index], "page_key": sorted(SPEC.page_keys)[index]})
        for index, name in enumerate(reads_of(b)[:4])
    ]
    state = init_state(scenario_for(SEED, "eval"), 1)
    calls, observations = [], []
    for index, (name, args) in enumerate(reads):
        calls.append((name, args))
        observations.append(line(state.next_seq, "ok", answer(held[index], f"{name}{index}")))
        state = dataclasses.replace(state, next_seq=state.next_seq + 1)
    for call in b.reference_calls:
        state, obs = apply(state, call)
        calls.append(call)
        observations.append(obs)
    return at(b, f"spread:p{level}", reference_calls=tuple(calls),
              reference_observations=tuple(observations))


CLEAN: dict[str, Callable[[], list[Any]]] = {
    "similarity": lambda: [similarity(level) for level in (0, 1, 2, 3)],
    "faults": lambda: [faults(level) for level in (0, 1, 2, 4)] + [faults_control()],
    "history": lambda: [history(level) for level in (0, 300, 600, 1200)],
    "block": lambda: [block(level) for level in (8, 16, 32, 64)] + [block_control()],
    "arguments": lambda: [arguments(level) for level in (2, 4, 6, 8)] + [arguments_control()],
    "shape": lambda: [shape(width) for width in (1, 2, 4)] + [shape_control()],
    "spread": lambda: [spread(level) for level in (1, 2, 4)],
}
REPORTED = {"block": {"N29"}, "shape": {"N7", "N33"}}


# --------------------------------------------------------------------------
# the ledger's text and its two unmeasured reasons
# --------------------------------------------------------------------------


@lru_cache(maxsize=1)
def old_ledger() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(gzip.decompress(FIXTURE.read_bytes()))["ledger"]
    return rows


# Texts the build may reword to say what the rule now is: N3's says the R control's filler is the
# only difference it lets through, and the block control's is too; N7's says equal, and a shape
# contrast's difference is reported.
REWORDABLE: set[tuple[str, str]] = {("N3", "measured"), ("N7", "tolerance")}


@pytest.mark.parametrize("knob", KNOBS)
def test_the_thirteen_old_rows_keep_their_text(knob: str) -> None:
    """Every field but `applies_to`, as the ledger had it before the change (the fixture holds
    that tree's ledger; see `tests/test_k1_content.py`)."""
    rows = {row.row_id: row for row in pin_ledger(knob)}
    for old in old_ledger():
        row = rows[old["row_id"]]
        for field in ("held", "measured", "tolerance", "on_violation", "stage"):
            if (old["row_id"], field) in REWORDABLE:
                continue
            assert getattr(row, field) == old[field], (old["row_id"], field)


def test_every_knob_reads_the_one_ledger() -> None:
    rows = pin_ledger("depth")
    assert len(rows) == 30
    for knob in KNOBS:
        assert pin_ledger(knob) == rows, knob


def test_the_unmeasured_reasons_are_in_plain_words_and_reworded() -> None:
    old = {row["row_id"] for row in old_ledger()}
    assert old == {f"N{i}" for i in range(1, 14)}
    stored = json.loads(gzip.decompress(FIXTURE.read_bytes()))["tasks"][0]["bundle"]["pins"]
    reasons = measure_pins(base()).unmeasured
    assert set(reasons) == {"N10", "N13"}
    for row, reason in reasons.items():
        assert reason.strip() and reason != stored["unmeasured"][row], row
        assert not PATTERN.search(reason), reason


@pytest.mark.parametrize("module, banned", [
    ("knobs.py", {"poisson_tasks.tasks", "poisson_tasks.surface"}),
    ("surface.py", {"poisson_tasks.tasks"}),
])
def test_the_ledger_and_the_shared_surface_never_import_the_generator(module: str,
                                                                      banned: set[str]) -> None:
    """The ledger measures what a bundle carries and nothing it would need the generator for;
    the shared surface is read by the generator, the verifier and the tool server alike."""
    tree = ast.parse((REPO / "src" / "poisson_tasks" / module).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported |= {f"{node.module}.{alias.name}" for alias in node.names}
        elif isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
    assert not imported & banned, imported & banned


# --------------------------------------------------------------------------
# each new knob's clean contrast holds
# --------------------------------------------------------------------------


@pytest.mark.parametrize("knob", sorted(CLEAN))
def test_a_clean_contrast_of_each_new_knob_refuses_nothing(knob: str) -> None:
    bundles = CLEAN[knob]()
    report = contrast(*bundles)
    assert report.knob == knob
    assert not report.refused, report.violations
    assert reported(report) == REPORTED.get(knob, set()), report.reported


def test_every_bundle_measures_every_row_but_the_two_run_time_ones() -> None:
    expected = {f"N{i}" for i in (*range(1, 10), 11, 12, *range(19, 36))}
    for knob, make in CLEAN.items():
        for bundle in make():
            record = measure_pins(bundle)
            assert set(record.values) == expected, (knob, bundle.arm_id)
            assert set(record.unmeasured) == {"N10", "N13"}


# --------------------------------------------------------------------------
# similarity: N19 to N22
# --------------------------------------------------------------------------


def swap_tool(bundle: Any, index: int, tool: dict[str, Any]) -> Any:
    tools = list(bundle.tools)
    tools[index] = tool
    return dataclasses.replace(bundle, tools=tuple(tools))


def test_n19_eleven_lookalikes_refuse() -> None:
    low = similarity(0)
    short = swap_tool(similarity(2), 3, dict(base().tools[-1]))
    assert "N19" in failed(contrast(low, short))
    assert "N19" not in failed(contrast(low, similarity(2)))


def test_n20_a_block_whose_tokens_move_with_the_level_refuses() -> None:
    longer = similarity(3)
    tool = dict(longer.tools[-1])
    tool["description"] += " and nothing else"
    assert "N20" in failed(contrast(similarity(0), swap_tool(longer, len(longer.tools) - 1, tool)))


@pytest.mark.parametrize("last", [numbers_at(3, 1)[0], "0419"],
                         ids=["one-ledger-a-digit-closer", "a-number-starting-with-0"])
def test_n21_a_lookalike_ledger_at_the_wrong_distance_or_starting_with_0_refuses(
    last: str
) -> None:
    report = contrast(similarity(0), similarity(2, numbers_at(2, 5) + [last]))
    assert "N21" in failed(report) and "N19" not in failed(report)


def test_n21_twelve_lookalikes_from_seven_ledgers_refuse() -> None:
    b = similarity(2)
    first = numbers_at(2)[0]
    index = next(i for i, t in enumerate(b.tools) if t["name"] == f"submit_sample_{first}")
    seventh = numbered(base().reference_calls[1][0], numbers_at(2, 7)[6])
    report = contrast(similarity(0), swap_tool(b, index, seventh))
    assert "N21" in failed(report) and "N19" not in failed(report)


def test_n21_the_level_is_the_digits_shared_in_place() -> None:
    """Six ledgers sharing exactly one digit pass at s1 and refuse at s2."""
    assert "N21" not in failed(contrast(similarity(0), similarity(1, numbers_at(1))))
    assert "N21" in failed(contrast(similarity(0), at(similarity(1, numbers_at(1)), "similarity:s2")))


def test_n22_a_right_tool_whose_schema_moves_with_the_level_refuses() -> None:
    b = similarity(1)
    tool = json.loads(json.dumps(b.tools[0]))
    tool["description"] = tool["description"].replace("entry code", "entry  code")
    assert "N22" in failed(contrast(similarity(0), swap_tool(b, 0, tool)))


# --------------------------------------------------------------------------
# history and faults: N23 to N26
# --------------------------------------------------------------------------


@pytest.mark.parametrize("total, refuses", [(298, False), (302, False), (297, True), (303, True)])
def test_n23_seeded_history_is_held_to_its_level_within_two_tokens(total: int,
                                                                   refuses: bool) -> None:
    report = contrast(history(0), history(300, total=total))
    assert ("N23" in failed(report)) is refuses


def test_n24_a_seeded_call_that_is_not_a_read_answered_ok_in_the_block_refuses() -> None:
    b = base()
    good = seeded(300, reads_of(b))
    outside = [r for r in SPEC.read_tools if r not in reads_of(b)][0]
    name, args, obs = good[0]
    stage_name = b.reference_calls[0][0]
    error = line(1, "no_such_item", LAYOUT["error_payload"])
    for bad in ((outside, args, obs), (stage_name, b.reference_calls[0][1], obs), (name, args, error)):
        pairs = [bad] + good[1:]
        assert "N24" in failed(contrast(history(0), history(300, pairs=pairs))), bad[0]
    assert "N24" not in failed(contrast(history(0), history(300, pairs=good)))


def test_n24_holds_the_faults_controls_seeded_pairs_too() -> None:
    b = base()
    good = seeded(fault_tokens(4), reads_of(b))
    stage_name = b.reference_calls[0][0]
    bad = [(stage_name, b.reference_calls[0][1], good[0][2])] + good[1:]
    assert "N24" in failed(contrast(faults(0), faults(4), faults_control(pairs=bad)))


@pytest.mark.parametrize("level, plan", [(2, (2, 0)), (1, (0, 1)), (4, (2, 1)), (4, (1, 3))])
def test_n25_the_plan_must_split_the_level_with_the_first_stage_taking_the_odd_one(
    level: int, plan: tuple[int, int]
) -> None:
    assert "N25" in failed(contrast(faults(0), faults(level, plan)))
    assert "N25" not in failed(contrast(faults(0), faults(level)))


@pytest.mark.parametrize("off, refuses", [(2, False), (-2, False), (3, True), (-3, True)])
def test_n26_the_faults_control_seeds_the_high_arms_fault_pairs_within_two_tokens(
    off: int, refuses: bool
) -> None:
    report = contrast(faults(0), faults(4), faults_control(off=off))
    assert ("N26" in failed(report)) is refuses


def test_n26_needs_the_high_arm_to_compare_against() -> None:
    assert "N26" not in failed(contrast(faults(0), faults_control(off=9)))


# --------------------------------------------------------------------------
# block: N27 to N29
# --------------------------------------------------------------------------


def test_n27_a_block_one_tool_short_of_its_level_refuses() -> None:
    assert "N27" in failed(contrast(block(8), block(32, block_tools(31))))


def test_n28_the_right_tools_stay_inside_the_first_eight_slots() -> None:
    def moved(level: int) -> Any:
        tools = list(block_tools(level))
        tools[2], tools[8] = tools[8], tools[2]
        return block(level, tools)
    report = contrast(moved(16), moved(32))
    assert "N28" in failed(report) and "N2" not in failed(report)


def test_n28_a_right_tool_that_moves_between_levels_refuses() -> None:
    tools = list(block_tools(32))
    tools[2], tools[5] = tools[5], tools[2]
    assert "N28" in failed(contrast(block(16), block(32, tools)))


@pytest.mark.parametrize("off, refuses", [(2, False), (-2, False), (3, True), (-3, True)])
def test_n29_the_block_controls_filler_matches_the_high_arms_extra_within_two_tokens(
    off: int, refuses: bool
) -> None:
    report = contrast(block(8), block(64), block_control(off=off))
    assert ("N29" in failed(report)) is refuses
    assert "N29" in reported(report)


# --------------------------------------------------------------------------
# arguments: N30 to N32
# --------------------------------------------------------------------------


def test_n30_a_stage_tool_whose_schema_moves_with_the_level_refuses() -> None:
    b = arguments(4)
    tool = json.loads(json.dumps(b.tools[0]))
    del tool["parameters"]["properties"]["bay_code"]
    report = contrast(arguments(2), swap_tool(b, 0, tool))
    assert "N30" in failed(report)


@pytest.mark.parametrize("case", ["one-short", "calls-differ", "not-stated", "carried-by-a-name"])
def test_n31_the_stated_values_are_the_level_less_two_and_opaque(case: str) -> None:
    if case == "one-short":
        b = arguments(8, stated=5)
    elif case == "calls-differ":
        values = dict(EXTRAS[:4])
        other = {**values, "lot_code": "harbor"}
        b = arguments(6, per_call=(values, other), text_values={**values, "spare_code": "harbor"})
    elif case == "not-stated":
        b = arguments(6, text_values=dict(EXTRAS[:3]))
    else:
        named = {**dict(EXTRAS[:4]), "lot_code": base().reference_calls[0][0].split("_")[1]}
        b = arguments(6, per_call=(named, named), text_values=named)
    assert "N31" in failed(contrast(arguments(2), b)), case


@pytest.mark.parametrize("off, refuses", [(2, False), (-2, False), (3, True), (-3, True)])
def test_n32_the_arguments_controls_request_matches_the_high_arms_within_two_tokens(
    off: int, refuses: bool
) -> None:
    report = contrast(arguments(2), arguments(8), arguments_control(off=off))
    assert ("N32" in failed(report)) is refuses


# --------------------------------------------------------------------------
# shape: N33, N34
# --------------------------------------------------------------------------


@pytest.mark.parametrize("make", [lambda: shape(2, calls_made=3), lambda: shape(2, size=15)],
                         ids=["three-stage-calls", "fifteen-tools"])
def test_n33_four_stage_calls_and_sixteen_tools_at_every_width(make: Any) -> None:
    report = contrast(shape(1), make())
    assert "N33" in failed(report)


@pytest.mark.parametrize("off, refuses", [(2, False), (-2, False), (3, True), (-3, True)])
def test_n34_the_shape_controls_request_matches_the_widest_within_two_tokens(
    off: int, refuses: bool
) -> None:
    report = contrast(shape(1), shape(4), shape_control(off=off))
    assert ("N34" in failed(report)) is refuses


# --------------------------------------------------------------------------
# spread: N35
# --------------------------------------------------------------------------


def test_n35_the_named_reads_are_the_same_at_every_level() -> None:
    b = base()
    other = [(name, {"item_code": SPEC.table["catalogue_items"][0], "page_key": sorted(SPEC.page_keys)[5]})
             for name in reads_of(b)[:4]]
    assert "N35" in failed(contrast(spread(1), spread(2, named=other)))


@pytest.mark.parametrize("level, parts", [
    (2, ["p", "a", "rt", ""]),
    (2, ["pa", "", "tr", ""]),
    (4, ["p", "a", "r", ""]),
], ids=["three-parts-at-two", "parts-out-of-order", "code-short"])
def test_n35_the_parts_are_the_levels_number_joining_to_the_code(level: int,
                                                                 parts: list[str]) -> None:
    assert dict(base().prompt_slots)["entry_code"] == "part"
    assert "N35" in failed(contrast(spread(1), spread(level, parts=parts)))


def test_n35_four_reads_are_named() -> None:
    b = base()
    three = [(name, {"item_code": SPEC.table["catalogue_items"][i], "page_key": sorted(SPEC.page_keys)[i]})
             for i, name in enumerate(reads_of(b)[:3])]
    report = contrast(spread(1, parts=["part", "", ""], named=three),
                      spread(2, parts=["pa", "rt", ""], named=three))
    assert "N35" in failed(report)


# --------------------------------------------------------------------------
# the old rows' three exceptions, and N4's reach
# --------------------------------------------------------------------------


def test_n3_lets_a_block_controls_suffix_through_and_no_other_difference() -> None:
    control = block_control()
    prefixed = dataclasses.replace(control, system_prompt="Note.\n" + base().system_prompt)
    assert "N3" in failed(contrast(block(8), block(64), prefixed))
    control = faults_control()
    suffixed = dataclasses.replace(control, system_prompt=base().system_prompt + "\n\nquiet plain")
    assert "N3" not in failed(contrast(faults(0), faults(4), control))
    assert "N3" in failed(contrast(faults(0), faults(4), suffixed))


def test_n4_holds_the_block_equal_for_faults_history_arguments_and_spread() -> None:
    def changed(bundle: Any) -> Any:
        tools = list(bundle.tools)
        tools[-1], tools[-2] = tools[-2], tools[-1]
        return dataclasses.replace(bundle, tools=tuple(tools))
    for low, high in ((faults(0), faults(2)), (history(0), history(300)),
                      (arguments(2), arguments(4)), (spread(1), spread(2))):
        assert "N4" in failed(contrast(low, changed(high))), high.arm_id


def test_n6_lets_the_knobs_own_slot_move_and_no_other() -> None:
    """The stated values move on an arguments contrast; on a faults contrast the same slot
    moving refuses; and another slot moving refuses on an arguments contrast."""
    assert "N6" not in failed(contrast(arguments(2), arguments(8)))
    b = faults(2)
    widened = dataclasses.replace(b, prompt_slots=b.prompt_slots + (("stated_values", "x y z"),))
    plain = dataclasses.replace(faults(0), prompt_slots=b.prompt_slots + (("stated_values", ""),))
    assert "N6" in failed(contrast(plain, widened))
    a = arguments(4)
    slots = tuple((k, v + " again") if k == "entry_code" else (k, v) for k, v in a.prompt_slots)
    assert "N6" in failed(contrast(arguments(2), dataclasses.replace(a, prompt_slots=slots)))


def test_n7_is_reported_for_shape_and_refused_for_any_other_knob() -> None:
    report = contrast(shape(1), shape(4))
    assert "N7" in reported(report) and "N7" not in failed(report)
    b = faults(2)
    named = dataclasses.replace(b, prompt=instruction(b) + "\nlookup region")
    report = contrast(faults(0), at(named, "faults:f2"))
    assert "N7" in failed(report) and "N7" not in reported(report)
