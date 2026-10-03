"""The frozen tests for knobs.py, knobs, control arms and the pin ledger: N1-N18.

Frozen on 2026-09-13, with the design amendments of 2026-09-11 and 2026-09-13
included.  The module is written against this file, which is not edited to suit it.
Where a written requirement could not be used as written, this docstring is
authoritative.

The public surface these tests pin
----------------------------------
`poisson_tasks.knobs.__all__` is exactly, and in this order::

    ArmSpec  PinRow  PinRecord  PinReport
    arm_id  levels  pin_ledger  measure_pins  check_pins

That is the knobs module's interface plus the three type names its signatures use.
Nothing else is public: the internal arm transforms are reached through
`ArmSpec`'s derived values and through `check_pins`, never as their own symbols.

Shapes these tests define
-------------------------
* ``ArmSpec(knob, level, control, strictness, split, generator_version)``, frozen,
  the six fields of an arm.  ``control`` is **not a flag**: it is the reference
  level the control arm stands in for (8 in ``depth:d1+h8`` and in
  ``distractor:r0+len(r8)@k16``), and ``None`` on a plain arm.  The arm id formats
  are the reason - each control id renders exactly that one extra number.
* ``ArmSpec.reference_turns`` is the reference solution's turn count: one call per
  turn plus the reply turn (N16).  ``ArmSpec.max_turns(slack)`` takes the slack
  because ``S`` is a cfg axis and is not one of the arm spec's six fields,
  while A5 writes ``max_turns(arm)`` as though it were nullary.
* ``PinRow(row_id, held, measured, tolerance, on_violation, stage, applies_to)``,
  frozen.  ``stage`` is where the row is enforced - ``generation``, ``engine``,
  ``adapter`` or ``analysis`` - which the ledger table states only in its *On
  violation* column, in prose.  ``applies_to`` is the knobs the row constrains.
* ``PinRecord(arm_id, values, unmeasured)``, frozen.  ``values`` maps a row id to
  its measured value for one bundle; ``unmeasured`` maps a row id to the reason it
  cannot be measured from a bundle at generation time.  Every ledger row appears in
  exactly one of the two.
* ``PinReport(knob, refused, violations, reported, records)``, frozen.  The contract
  is ``check_pins(...) -> PinReport | refusal``; a refusal is a ``PinReport`` whose
  ``refused`` is true, not an exception, because the ledger's job is to report and
  the *On violation* column says **generation** refuses.  ``violations`` and
  ``reported`` are tuples of ``(row_id, detail)``.
* ``check_pins`` raises ``ValueError`` when the arms it is handed do not share one
  knob.  That is a caller error and not a pin violation, so it is not a refusal.
* A **bundle** is anything carrying the fields ``measure_pins`` reads.  tasks.py owns
  ``TaskBundle`` and does not exist yet, so this file builds bundle-shaped objects
  by hand, the way the engine's tests built ``Scenario`` by hand.  The fields are
  the task layer's, plus three these tests need and it does not name -
  ``template_id``, ``prompt_slots`` and ``reference_observations``.  **Those three
  are a drafted amendment to the task layer, not a decision**.  They are the other
  halves of fields the task layer already names, and without them N6 and N9 have no
  measurement.
* Seeded history is the OpenAI chat shape, since N18 pins the endpoint type to
  OpenAI-compatible chat completions: ``{"role": "assistant", "tool_calls":
  [{"function": {"name": ..., "arguments": "<compact json>"}}]}`` followed by
  ``{"role": "tool", "content": "<observation>"}``.

What is deliberately not tested here
------------------------------------
* **N17's scripted `diff`.**  The written test for N17 is a Proofload ``diff`` of the
  lowest arm against the highest, reporting zero truncated rows.  knobs.py may import
  only ``Episode`` and ``Rollout`` from Proofload, so the ``diff`` half runs in the
  Proofload adapter's tests against A5.  knobs.py computes no horizon: N17's
  ``H = max(max_turns)`` over the arm set follows from N16's slack identity, which
  test_n16_1 and test_n16_1b pin.
* **N10 and N13's measurements.**  Both are run-time: N10 compares a serving pin
  across a model's runs and N13 reads server-reported usage from the trace.  A
  bundle carries neither, so these tests pin that ``measure_pins`` *declares* them
  unmeasured with a reason, and that the ledger still carries their rows.
* **N18's revision predicate.**  N18's own *Test:* line assigns it to "the
  pre-registration validator", which is built in the Proofload adapter.  No model
  string reaches a bundle or an arm spec, so knobs.py declares the row through N10
  and validates nothing.  **This and N17's `diff` half are two named gaps owed to
  the Proofload adapter's tests**, and neither is covered by any other module's tests
  today.
* **The band N9 refuses on, as a property of a real generator.**  This file pins
  the band's value and the shape of the comparison.  Whether the task layer's
  generator can always land inside it is G16's structure-census question.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import json
import os
import pathlib
import subprocess
import sys
import textwrap

from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

# --------------------------------------------------------------------------
# frozen literals
# --------------------------------------------------------------------------

DATA = pathlib.Path(__file__).resolve().parent.parent / "src" / "poisson_tasks" / "data"
TABLE_PATH = DATA / "vocabulary-v2.json"
TABLE = json.loads(TABLE_PATH.read_text())
L_OBS = TABLE["L_obs"]
BAND_LO, BAND_HI = TABLE["token_band"]

KNOBS_EXPORTS = (
    "ArmSpec", "PinRow", "PinRecord", "PinReport",
    "arm_id", "levels", "pin_ledger", "measure_pins", "check_pins",
)
# `from __future__ import annotations` binds the name `annotations` in the module.
# It is a compiler directive and not a symbol a caller could use, so SF2 excludes it
# rather than forbidding the import - which would be a style rule dressed as a pin.
FUTURE_NAMES = ("annotations",)

# Candidate levels, not the pilot defaults: the pilot's choice lives in its pre-registration.
DEPTH_LEVELS = (1, 2, 3, 5, 8)
DISTRACTOR_LEVELS = (0, 2, 4, 8, 14)
K_D = 16
K_R = 16
D_R = 2

LEDGER_ROWS = tuple(f"N{i}" for i in range(1, 14))

# Where each row is enforced, and what happens when it fails.  Read off the ledger
# table's *On violation* column: "generation refuses" -> generation/refuse,
# "reported" -> generation/report, "engine test fails" -> engine/engine_test,
# "the adapter stops the run" and "the adapter refuses to start" -> adapter,
# "the contrast is void" -> analysis.
ROW_STAGE = {
    "N1": "generation", "N2": "generation", "N3": "generation", "N4": "generation",
    "N5": "generation", "N6": "generation", "N7": "generation", "N8": "engine",
    "N9": "generation", "N10": "adapter", "N11": "adapter", "N12": "adapter",
    "N13": "analysis",
}
ROW_ACTION = {
    "N1": "refuse", "N2": "refuse", "N3": "refuse", "N4": "refuse",
    "N5": "report", "N6": "refuse", "N7": "refuse", "N8": "engine_test",
    "N9": "refuse", "N10": "stop_run", "N11": "refuse_start", "N12": "refuse_start",
    "N13": "void_contrast",
}
# The rows that constrain one knob only.  N4 is written "(knob D)" and N5 "(knob R)".
# N9 is written "(control arms)", which reads as both - but only knob D's control
# *seeds history*: knob R's control appends a frozen filler passage to the system
# prompt and seeds nothing, and N9's own measurement is written in `(H - dL)`, which
# is depth's notation.  So N9 is knob D's, and saying so here is what stops a build
# from evaluating it against an R control that has no seeded pairs to measure.
ROW_KNOBS = {
    "N4": ("depth",),
    "N5": ("distractor",),
    "N9": ("depth",),
}
# Where a row is enforced is not the same question as whether a *bundle* carries
# what it measures.  N11 and N12 are enforced when the adapter starts, and both are
# measurable at generation: strictness is `bundle.verifier.strictness` and the two
# hashes are bundle fields.  Only N10 and N13 need something no bundle has - a cfg
# and an episode's `meta` for the serving pin, and the trace for realised tokens.
MEASURABLE_ROWS = tuple(f"N{i}" for i in range(1, 10)) + ("N11", "N12")
UNMEASURABLE_ROWS = ("N10", "N13")

# N9's declared band, in reference-tokenizer tokens, over the aggregate.
#
# Minted 2026-09-13.  A seeded pair and a chain pair are each (call name + compact
# JSON arguments + observation).  Measured against the frozen table and the engine as
# first built, with chain tokens the engine emitted under two disjoint token keys:
#
#   chain pair totals      [47, 65], mean 55.7, 1792 pairs, two disjoint scenarios
#   read pair totals       13 to 16 *consecutive* integers inside [51, 66],
#                          depending on how many catalogue items the scenario
#                          makes visible (measured at 2, 3, 4, 6, 8 and 16)
#   7-pair targets         [365, 418] observed; [357, 462] reachable at 16 items,
#                          [364, 448] at the tightest block measured (2 items)
#   best achievable |seeded - expected| over 256 blocks of 7 pairs: 0, every block
#
# So the declared band is +/- 2 against a measured residual of 0 - the same shape
# and the same two-token margin as the engine's observation band, and for the same
# reason: the read pair's reachable set is consecutive, so every integer in its
# 7-pair range is a sum, and the only way to miss is a target outside that range.
# 3.0% of chain pairs (53 of 1792) are below the read floor of 51, and on arguments
# alone 51.4% are, which is why this is an aggregate band and not a per-pair one.
N9_BAND = 2
N9_MEASURED_RESIDUAL = 0
N9_CHAIN_PAIR_RANGE = (47, 65)
N9_READ_PAIR_RANGE = (51, 66)

# The four arm id formats, exactly as written.
ARM_ID_CASES = (
    (("depth", 3, None), "depth:d3"),
    (("depth", 1, 8), "depth:d1+h8"),
    (("distractor", 4, None), "distractor:r4@k16"),
    (("distractor", 0, 8), "distractor:r0+len(r8)@k16"),
)

STRICTNESS = ("strict", "leaky")
SPLITS = ("eval", "train")
GEN_VERSION = "0.0.1"

# --------------------------------------------------------------------------
# the shared helpers
# --------------------------------------------------------------------------


def knobs():
    """The module under test.  Imported here and not at module scope, so this file
    still collects on a bare tree while every test in it fails."""
    import poisson_tasks.knobs as m

    return m


def engine():
    import poisson_tasks.engine as m

    return m


def encoding():
    from poisson_tasks.tokenizer import reference_encoding

    return reference_encoding()


def ntok(text: str) -> int:
    return len(encoding().encode(text))


def spec(knob="depth", level=3, control=None, strictness="strict", split="eval"):
    return knobs().ArmSpec(
        knob=knob, level=level, control=control,
        strictness=strictness, split=split, generator_version=GEN_VERSION,
    )


@dataclasses.dataclass(frozen=True)
class Verifier:
    """The task layer's `VerifierSpec`, reduced to the one field N11 reads."""

    strictness: str


@dataclasses.dataclass(frozen=True)
class Bundle:
    """A bundle-shaped object, built by hand.  The task layer's fields that knobs.py
    reads, plus the three named in this file's docstring as a drafted amendment."""

    arm_id: str
    seed: int
    split: str
    scenario_hash: str
    system_prompt: str
    prompt: object
    tools: tuple
    seq_start: int
    reference_calls: tuple
    reference_observations: tuple
    verifier: Verifier
    engine_hash: str
    generator_hash: str
    template_id: str
    prompt_slots: tuple


def tool_schema(name: str, params: tuple[str, ...], description: str = "d") -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": {p: {"type": "string"} for p in params}},
    }


def stage_tool(stage_name: str, qualifier: str) -> str:
    return f"{TABLE['write_verb']}_{stage_name}_{qualifier}"


def read_tool(verb: str, facet: str) -> str:
    return f"{verb}_{facet}"


def all_read_tools() -> list[str]:
    return [read_tool(v, f) for v, f in zip(TABLE["read_verbs"], TABLE["facets"])]


def block(qualifier: str = "invoice", n_reads: int = 8) -> tuple:
    """Knob D's block: the target class's 8 stage tools plus 8 reads, K_D = 16."""
    stage = [tool_schema(stage_tool(s, qualifier), ("record_id", "chain_token"))
             for s in TABLE["stage_names"]]
    reads = [tool_schema(t, ("item_code", "page_key")) for t in all_read_tools()[:n_reads]]
    return tuple(stage + reads)


def chain_of(level: int, qualifier: str = "invoice", record: str = "able-account"):
    """The reference calls and observations for a depth-`level` task, from the engine."""
    e = engine()
    es = e.EngineSpec.from_mapping(TABLE)
    entry = TABLE["entry_codes"][0]
    sc = e.Scenario(records={(qualifier, record): entry},
                    token_key=b"oracle-m2-key",
                    visible_items=tuple(TABLE["catalogue_items"][:4]))
    tools = {i: nm for nm, (i, q) in es.stage_tools.items() if q == qualifier}
    calls = []
    state = e.init_state(sc, 1)
    token = None
    for s in range(level):
        if s == 0:
            call = (tools[0], {"record_id": record, "entry_code": entry})
        else:
            call = (tools[s], {"record_id": record, "chain_token": token})
        state, obs = e.apply(state, call)
        calls.append(call)
        token = obs.split()[-1]
    _, observations = e.replay(sc, calls, 1)
    return tuple(calls), tuple(observations)


def seeded_pairs(count: int, seq_start: int = 1) -> list[dict]:
    """`count` (assistant tool call, tool observation) pairs, from real read calls."""
    e = engine()
    sc = e.Scenario(records={}, token_key=b"oracle-m2-key",
                    visible_items=tuple(TABLE["catalogue_items"][:4]))
    state = e.init_state(sc, seq_start)
    reads = all_read_tools()
    msgs: list[dict] = []
    for i in range(count):
        args = {"item_code": TABLE["catalogue_items"][i % 4],
                "page_key": sorted(TABLE["page_keys"])[i % 16]}
        name = reads[i % len(reads)]
        state, obs = e.apply(state, (name, args))
        msgs.append({"role": "assistant", "tool_calls": [
            {"function": {"name": name, "arguments": json.dumps(args, separators=(",", ":"))}}]})
        msgs.append({"role": "tool", "content": obs})
    return msgs


def bundle(arm, *, seed=7, scenario_hash="s0", system_prompt="sys", prompt="do the thing",
           tools=None, seq_start=1, template_id="depth.v1", prompt_slots=(("goal", "bundle"),),
           engine_hash="e0", generator_hash="g0", level=None, control_pairs=None):
    """A bundle for `arm`.  Every default is shared across arms, so a test that wants
    a pin to differ has to say so."""
    k = knobs()
    a = arm if isinstance(arm, str) else k.arm_id(arm)
    lvl = level if level is not None else (arm.level if not isinstance(arm, str) else 1)
    calls, obs = chain_of(lvl)
    if control_pairs is not None:
        prompt = [{"role": "user", "content": "do the thing"}] + seeded_pairs(control_pairs)
        seq_start = control_pairs + 1
    return Bundle(
        arm_id=a, seed=seed, split="eval", scenario_hash=scenario_hash,
        system_prompt=system_prompt, prompt=prompt,
        tools=tools if tools is not None else block(),
        seq_start=seq_start, reference_calls=calls, reference_observations=obs,
        verifier=Verifier(strictness="strict"), engine_hash=engine_hash,
        generator_hash=generator_hash, template_id=template_id, prompt_slots=prompt_slots,
    )


def depth_contrast(low=1, high=8, control=True, residual=0):
    """The pilot's shape: d1, d8 and the d1+h8 control, all on one scenario.

    The control's seeded history is balanced to `residual` tokens by default, because
    an unbalanced one makes every test in this file that asserts `refused is False`
    fail on N9 whatever row it is actually about.  The stand-in run found exactly
    that: the fixture, not the shim.
    """
    k = knobs()
    arms = {}
    for lvl in (low, high):
        s = spec(level=lvl)
        arms[k.arm_id(s)] = bundle(s, level=lvl)
    if control:
        s = spec(level=low, control=high)
        arms[k.arm_id(s)] = bundle(s, level=low, control_pairs=high - low)
        arms[k.arm_id(s)] = control_with_residual(arms, low, high, residual)
    return arms


def replaced(b: Bundle, **fields) -> Bundle:
    return dataclasses.replace(b, **fields)


def pair_tokens(name: str, args: dict, observation: str) -> int:
    """One (assistant tool call, tool observation) pair, in reference-tokenizer tokens.

    The call side is the tool name plus its arguments as the wire carries them - one
    compact JSON object, which is what an OpenAI-compatible chat completion sends.
    """
    return ntok(name) + ntok(json.dumps(args, separators=(",", ":"))) + ntok(observation)


def read_pair_totals(n_reads: int = 8, n_items: int = 4) -> tuple[int, ...]:
    """Every pair total a seeded read pair can reach, for a block with `n_reads` read
    tools over `n_items` visible catalogue items.  The generator's whole choice set."""
    e = engine()
    vis = tuple(TABLE["catalogue_items"][:n_items])
    sc = e.Scenario(records={}, token_key=b"oracle-m2-key", visible_items=vis)
    state = e.init_state(sc, 1)
    out = set()
    for name in all_read_tools()[:n_reads]:
        for item in vis:
            for page in sorted(TABLE["page_keys"]):
                args = {"item_code": item, "page_key": page}
                _, obs = e.apply(state, (name, args))
                if obs.split()[1] == "ok":
                    out.add(pair_tokens(name, args, obs))
    return tuple(sorted(out))


def read_pair_by_total(n_reads: int = 8, n_items: int = 4) -> dict[int, tuple]:
    """One concrete (tool, item, page key) per reachable total."""
    e = engine()
    vis = tuple(TABLE["catalogue_items"][:n_items])
    sc = e.Scenario(records={}, token_key=b"oracle-m2-key", visible_items=vis)
    state = e.init_state(sc, 1)
    out: dict[int, tuple] = {}
    for name in all_read_tools()[:n_reads]:
        for item in vis:
            for page in sorted(TABLE["page_keys"]):
                args = {"item_code": item, "page_key": page}
                _, obs = e.apply(state, (name, args))
                if obs.split()[1] == "ok":
                    out.setdefault(pair_tokens(name, args, obs), (name, args))
    return out


def seeded_history_totalling(target: int, pairs: int, seq_start: int = 1) -> list[dict]:
    """A seeded history of `pairs` real read pairs whose token total is exactly
    `target`.  Possible because the reachable set is consecutive (N9.4): fill at the
    floor, then walk pairs up one token at a time until the remainder is spent."""
    by_total = read_pair_by_total()
    reachable = tuple(sorted(by_total))
    lo, hi = reachable[0], reachable[-1]
    assert pairs * lo <= target <= pairs * hi, (target, pairs, lo, hi)
    reachable_set = set(reachable)
    chosen = [lo] * pairs
    remainder = target - pairs * lo
    for i in range(pairs):
        step = min(remainder, hi - lo)
        while step and (lo + step) not in reachable_set:
            step -= 1
        chosen[i] += step
        remainder -= step
    assert remainder == 0 and sum(chosen) == target, (target, pairs, chosen)
    e = engine()
    sc = e.Scenario(records={}, token_key=b"oracle-m2-key",
                    visible_items=tuple(TABLE["catalogue_items"][:4]))
    state = e.init_state(sc, seq_start)
    msgs: list[dict] = []
    for total in chosen:
        name, args = by_total[total]
        state, obs = e.apply(state, (name, args))
        msgs.append({"role": "assistant", "tool_calls": [
            {"function": {"name": name,
                          "arguments": json.dumps(args, separators=(",", ":"))}}]})
        msgs.append({"role": "tool", "content": obs})
    return msgs


def chain_pair_totals(b: Bundle) -> tuple[int, ...]:
    """Per-pair token totals for a bundle's reference solution, in call order."""
    return tuple(pair_tokens(name, args, obs)
                 for (name, args), obs in zip(b.reference_calls, b.reference_observations))


def control_with_residual(arms: dict, low: int, high: int, residual: int) -> Bundle:
    """Rebuild the `dL+hH` control so its seeded history is exactly `residual` tokens
    away from the chain pairs it stands in for.

    The control runs pairs 1..dL itself, so its seeded block stands in for the high
    arm's pairs dL+1..H - every one of them a chain pair, which is why the single
    cheap stage-1 call cancels out of N9's aggregate comparison.
    """
    k = knobs()
    control_id = k.arm_id(spec(level=low, control=high))
    high_id = k.arm_id(spec(level=high))
    expected = sum(chain_pair_totals(arms[high_id])[low:])
    prompt = [{"role": "user", "content": "do the thing"}]
    prompt += seeded_history_totalling(expected + residual, high - low)
    return replaced(arms[control_id], prompt=prompt, seq_start=high - low + 1)


def in_child(source: str, env_extra: dict | None = None) -> str:
    """Run `source` in a fresh interpreter that imports from this tree."""
    root = pathlib.Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env.update(env_extra or {})
    out = subprocess.run([sys.executable, "-c", textwrap.dedent(source)],
                         capture_output=True, text=True, env=env, cwd=str(root))
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def knobs_source() -> str:
    return pathlib.Path(inspect.getsourcefile(knobs())).read_text()


def module_tree() -> ast.Module:
    return ast.parse(knobs_source())


def imported_names() -> set[str]:
    """Every module name the module imports, at any depth.  An `ast` walk, never a
    substring match on source."""
    names: set[str] = set()
    for node in ast.walk(module_tree()):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


# --------------------------------------------------------------------------
# SF - the public surface
# --------------------------------------------------------------------------


def test_sf1_all_is_exactly_the_specs_interface_list():
    """SF1: `__all__` is the documented interface plus its three type names, in order."""
    assert tuple(knobs().__all__) == KNOBS_EXPORTS


def test_sf2_no_public_symbol_beyond_all():
    """SF2: nothing public leaks past `__all__`.  An extra public symbol is a contract
    violation, so the module's non-underscore names are exactly `__all__` plus
    whatever it imports under a private alias."""
    m = knobs()
    public = {n for n in vars(m) if not n.startswith("_")}
    extra = public - set(KNOBS_EXPORTS) - set(FUTURE_NAMES)
    assert extra == set(), f"public symbols outside __all__: {sorted(extra)}"


def test_sf3_the_four_types_are_frozen():
    """SF3: `ArmSpec` is frozen by its own definition, and the three record types carry
    measurements that a caller must not edit after the fact."""
    m = knobs()
    for name in ("ArmSpec", "PinRow", "PinRecord", "PinReport"):
        cls = getattr(m, name)
        assert dataclasses.is_dataclass(cls), name
        assert cls.__dataclass_params__.frozen, name


def test_sf4_arm_spec_carries_exactly_the_six_fields():
    """SF4: an arm spec is written `(knob, level, control, strictness, split,
    generator version)`.  Six, and no seventh: `S` is a cfg axis and
    `seq_start` rides `init_state`, so neither may appear here."""
    fields = tuple(f.name for f in dataclasses.fields(knobs().ArmSpec))
    assert fields == ("knob", "level", "control", "strictness", "split",
                      "generator_version")


def test_sf5_generation_imports_no_network_and_no_verifiers():
    """SF5: the engine, knobs.py and tasks.py make no model call and no network call,
    import neither `verifiers` nor any network library, and from `proofload` import only
    `Episode` and `Rollout`.  knobs.py needs none of those, so the list is empty."""
    banned = {"verifiers", "openai", "requests", "httpx", "urllib", "urllib3",
              "socket", "aiohttp", "http", "proofload", "random", "time", "datetime"}
    assert imported_names() & banned == set()


def test_sf6_n8_cites_tg_m1s_literals_and_does_not_re_mint_them():
    """SF6: `L_obs` and the token band are pin-ledger literals; knobs.py's N8 cites
    them and doesn't re-mint them (a constraint carried over from the engine).  So
    N8's tolerance carries the frozen table's numbers, and the module contains no
    second copy of them as literals of its own."""
    row = {r.row_id: r for r in knobs().pin_ledger("depth")}["N8"]
    assert str(L_OBS) in row.tolerance
    assert f"{BAND_LO}" in row.tolerance and f"{BAND_HI}" in row.tolerance
    minted = [n.value for n in ast.walk(module_tree())
              if isinstance(n, ast.Constant) and isinstance(n.value, int)]
    assert minted.count(L_OBS) == 0, "L_obs is re-minted as a literal in the module"


# --------------------------------------------------------------------------
# P - purity and determinism
# --------------------------------------------------------------------------


def test_p1_every_entry_point_is_pure_within_one_process():
    """P1: two calls over equal inputs give equal results.  No clock, RNG or env."""
    k = knobs()
    s = spec()
    assert k.arm_id(s) == k.arm_id(s)
    assert k.levels("depth") == k.levels("depth")
    assert k.pin_ledger("depth") == k.pin_ledger("depth")
    arms = depth_contrast()
    one, two = k.check_pins(arms), k.check_pins(arms)
    assert one == two


def test_p2_determinism_across_processes_and_hash_seeds():
    """P2: the ledger and an arm id are byte-identical in two fresh interpreters at
    different `PYTHONHASHSEED`.  A set iteration order reaching either would show
    here and nowhere else."""
    src = """
        import json
        from poisson_tasks.knobs import ArmSpec, arm_id, pin_ledger, levels
        rows = [(r.row_id, r.held, r.measured, r.tolerance, r.on_violation, r.stage,
                 tuple(r.applies_to)) for k in ("depth", "distractor") for r in pin_ledger(k)]
        ids = [arm_id(ArmSpec("depth", 1, 8, "strict", "eval", "0.0.1")),
               arm_id(ArmSpec("distractor", 0, 8, "leaky", "train", "0.0.1"))]
        print(json.dumps([rows, ids, list(levels("depth")), list(levels("distractor"))]))
    """
    a = in_child(src, {"PYTHONHASHSEED": "0"})
    b = in_child(src, {"PYTHONHASHSEED": "1"})
    assert a == b


def test_p3_measure_pins_does_not_mutate_its_bundle():
    """P3: measuring is a read.  A bundle handed to `measure_pins` is unchanged, so a
    caller may measure the same bundle under two ledgers."""
    k = knobs()
    b = bundle(spec())
    before = dataclasses.astuple(b)
    k.measure_pins(b)
    assert dataclasses.astuple(b) == before


# --------------------------------------------------------------------------
# ID - arm identity
# --------------------------------------------------------------------------


def test_id1_arm_id_renders_the_specs_four_formats():
    """ID1: the four documented formats, exactly."""
    k = knobs()
    for (knob, level, control), expected in ARM_ID_CASES:
        assert k.arm_id(spec(knob=knob, level=level, control=control)) == expected


def test_id2_arm_id_is_canonical_over_the_fields_it_does_not_render():
    """ID2: `arm_id` is canonical.  Canonical means one id per
    `(knob, level, control)`: strictness, split and generator version are pinned by
    N11, G12 and N12 and do not enter the id, so two arms differing only there share
    an id.  Stated as a test because the opposite reading - an id that renders all
    six fields - would silently break `diff`'s cell matching."""
    k = knobs()
    base = spec(knob="depth", level=3)
    for strictness in STRICTNESS:
        for split in SPLITS:
            other = spec(knob="depth", level=3, strictness=strictness, split=split)
            assert k.arm_id(other) == k.arm_id(base)


def test_id3_arm_id_is_injective_over_knob_level_and_control():
    """ID3: distinct `(knob, level, control)` give distinct ids, over every candidate
    level and every control that N15 admits."""
    k = knobs()
    seen = {}
    for knob in ("depth", "distractor"):
        for level in k.levels(knob):
            for control in (None, *[c for c in k.levels(knob) if c > level]):
                s = spec(knob=knob, level=level, control=control)
                key = k.arm_id(s)
                assert key not in seen, f"{key} collides: {seen.get(key)} and {(knob, level, control)}"
                seen[key] = (knob, level, control)


def test_id4_an_unknown_knob_is_refused():
    """ID4: there are two knobs, and tool count is deferred.  A third knob name is not
    a level question, so it raises rather than rendering an id nothing can consume."""
    k = knobs()
    for bad in ("tools", "depth ", "Depth", "", "toolcount"):
        try:
            k.arm_id(spec(knob=bad, level=1))
        except (ValueError, KeyError):
            continue
        raise AssertionError(f"arm_id accepted knob {bad!r}")


def test_id5_levels_are_the_specs_candidate_sets():
    """ID5: `levels(knob)` is the candidate set, not the pilot default.  The pilot
    picks {1, 3, 8} out of depth's five candidates, and the pilot's
    choice lives in the pre-registration, not here."""
    k = knobs()
    assert k.levels("depth") == DEPTH_LEVELS
    assert k.levels("distractor") == DISTRACTOR_LEVELS


# --------------------------------------------------------------------------
# N-rows - the ledger is declared
# --------------------------------------------------------------------------


def test_nrows_1_the_ledger_is_thirteen_rows_in_order_for_both_knobs():
    """N-rows: "Every row above has a frozen test."  First the table itself: thirteen
    rows, N1 to N13, in the ledger's own order, for each knob.  The same ledger is
    used for both knobs, so the row set does not vary with the knob."""
    k = knobs()
    for knob in ("depth", "distractor"):
        ids = tuple(r.row_id for r in k.pin_ledger(knob))
        assert ids == LEDGER_ROWS, knob


def test_nrows_2_every_row_states_its_stage_and_its_action():
    """N-rows: the ledger's *On violation* column in prose becomes two fields, so a
    caller can act on it.  A row that refuses at generation and one that voids a
    contrast at analysis are not interchangeable."""
    k = knobs()
    for row in k.pin_ledger("depth"):
        assert row.stage == ROW_STAGE[row.row_id], row.row_id
        assert row.on_violation == ROW_ACTION[row.row_id], row.row_id


def test_nrows_3_the_two_knob_specific_rows_say_so():
    """N-rows: three rows are knob-specific - N4 "(knob D)", N5 "(knob R)", and N9,
    which is written "(control arms)" but measures seeded history in `(H - dL)`, and
    only knob D's control seeds any.  Every other row applies to both."""
    k = knobs()
    for knob in ("depth", "distractor"):
        for row in k.pin_ledger(knob):
            expected = ROW_KNOBS.get(row.row_id, ("depth", "distractor"))
            assert tuple(row.applies_to) == expected, (knob, row.row_id)


def test_nrows_4_every_row_is_measured_or_declared_unmeasurable_exactly_once():
    """N-rows: a `PinRecord` accounts for all thirteen.  A row that is silently absent
    from both halves is a pin nobody checks, which is the failure the ledger exists to
    prevent."""
    k = knobs()
    rec = k.measure_pins(bundle(spec()))
    assert set(rec.values) | set(rec.unmeasured) == set(LEDGER_ROWS)
    assert set(rec.values) & set(rec.unmeasured) == set()


def test_nrows_5_the_unmeasurable_rows_are_exactly_n10_and_n13_and_each_gives_a_reason():
    """N-rows: only the serving pin and the realised token count need something no
    bundle carries.  Naming them here stops a later build from quietly widening the
    set and calling a pin unmeasurable because measuring it was awkward.

    This is N10's and N13's test at generation.  N10 compares a serving pin "across all
    of a model's runs", from cfg, the arm spec and every episode's `meta`; N13 reads
    server-reported usage from the trace, per episode.  A bundle has none of those, so
    each is declared unmeasured with a reason rather than a pin that silently measures
    nothing.  Where each is enforced, and what its violation does, is test_nrows_2's."""
    k = knobs()
    rec = k.measure_pins(bundle(spec()))
    assert tuple(sorted(rec.unmeasured, key=lambda r: int(r[1:]))) == UNMEASURABLE_ROWS
    assert tuple(sorted(rec.values, key=lambda r: int(r[1:]))) == MEASURABLE_ROWS
    for row_id, reason in rec.unmeasured.items():
        assert isinstance(reason, str) and reason.strip(), row_id


# --------------------------------------------------------------------------
# N1 to N13 - the rows behave
# --------------------------------------------------------------------------


def failed_rows(report) -> set[str]:
    return {row for row, _ in report.violations}


def reported_rows(report) -> set[str]:
    return {row for row, _ in report.reported}


def test_n1_2_a_differing_scenario_hash_refuses():
    """N1: the pin the whole design rests on.  If the arms are not the same scenario,
    the contrast is between two tasks and not between two levels."""
    k = knobs()
    arms = depth_contrast()
    victim = sorted(arms)[0]
    arms[victim] = replaced(arms[victim], scenario_hash="a-different-scenario")
    report = k.check_pins(arms)
    assert "N1" in failed_rows(report)
    assert report.refused is True


def test_n2_1_required_tool_slots_are_read_from_the_reference_calls():
    """N2: "slot indices per seed, across arms".  The required tools are the ones the
    reference solution calls, so their slot indices are their positions in `tools`.
    Measured that way, N2 needs no field the task layer does not already name."""
    k = knobs()
    b = bundle(spec(level=3))
    rec = k.measure_pins(b)
    names = {c[0] for c in b.reference_calls}
    expected = tuple(sorted((t["name"], i) for i, t in enumerate(b.tools)
                            if t["name"] in names))
    assert tuple(sorted(rec.values["N2"])) == expected
    # Name *and* index, not indices alone: d1 requires one tool and d8 requires eight,
    # so a bare index set legitimately differs between levels and could not be compared.
    assert len(expected) == len(names)


def test_n2_2_moving_a_required_tool_between_arms_refuses():
    """N2: the required tools' slots are a function of the seed only, so a level that
    moves one has made position a confound with depth."""
    k = knobs()
    arms = depth_contrast()
    victim = sorted(arms)[0]
    b = arms[victim]
    shuffled = (b.tools[-1],) + b.tools[:-1]
    arms[victim] = replaced(b, tools=shuffled)
    report = k.check_pins(arms)
    assert "N2" in failed_rows(report)
    assert report.refused is True


def test_n3_1_a_differing_system_prompt_refuses():
    """N3: sha256 across arms, equal."""
    k = knobs()
    arms = depth_contrast()
    victim = sorted(arms)[0]
    arms[victim] = replaced(arms[victim], system_prompt="sys, but longer")
    report = k.check_pins(arms)
    assert "N3" in failed_rows(report)


def test_n3_2_the_r_control_filler_is_the_one_permitted_difference():
    """N3: "The only permitted difference is the R control filler", which the R control
    appends "at the end of the system prompt".  So the control's prompt is a plain
    arm's plus a suffix, and that suffix is the only shape N3 lets through - measured
    without a new bundle field, because a suffix is visible in the string itself."""
    k = knobs()
    arms = {}
    for level in (0, 8):
        s = spec(knob="distractor", level=level)
        arms[k.arm_id(s)] = bundle(s, level=1, system_prompt="sys")
    s = spec(knob="distractor", level=0, control=8)
    arms[k.arm_id(s)] = bundle(s, level=1, system_prompt="sys" + " filler words here")
    report = k.check_pins(arms)
    assert "N3" not in failed_rows(report)


def test_n3_3_a_prefix_difference_is_not_the_filler_and_refuses():
    """N3: the filler goes at the end.  A control whose system prompt differs anywhere
    else is not carrying a filler, and the suffix rule is what tells them apart."""
    k = knobs()
    arms = {}
    for level in (0, 8):
        s = spec(knob="distractor", level=level)
        arms[k.arm_id(s)] = bundle(s, level=1, system_prompt="sys")
    s = spec(knob="distractor", level=0, control=8)
    arms[k.arm_id(s)] = bundle(s, level=1, system_prompt="filler words here sys")
    report = k.check_pins(arms)
    assert "N3" in failed_rows(report)


def test_n4_1_knob_ds_tool_block_is_identical_at_every_level():
    """N4: "`K_D` = 16 tools, identical at every level" - sha256 of the rendered
    schemas in slot order.  This is the row that makes depth a depth knob: if the
    block moved with `d`, the contrast would be block-against-block."""
    k = knobs()
    arms = depth_contrast()
    assert "N4" not in failed_rows(k.check_pins(arms))
    victim = sorted(arms)[0]
    b = arms[victim]
    arms[victim] = replaced(b, tools=b.tools[:-1] + (tool_schema("extra_tool", ("x",)),))
    report = k.check_pins(arms)
    assert "N4" in failed_rows(report)
    assert report.refused is True


def test_n4_2_the_ledgers_n4_row_states_the_fixed_block_size():
    """N4: "`K_D` = 16 tools, identical at every level".  tasks.py builds the block, so
    what knobs.py can pin is the number the row holds it to.  The fixture agrees, and that
    half is green the moment the fixture is committed - it is written down here so it
    is not read as evidence."""
    k = knobs()
    row = {r.row_id: r for r in k.pin_ledger("depth")}["N4"]
    assert str(K_D) in (row.held + row.tolerance + row.measured)
    assert len(block()) == K_D


def test_n4_3_n4_does_not_fire_on_knob_r():
    """N4: knob R's block changes by definition - `r` distractors replace `14 - r`
    reads - so a row that demanded an identical block would refuse every R arm."""
    k = knobs()
    arms = {}
    for level in (0, 4):
        s = spec(knob="distractor", level=level)
        arms[k.arm_id(s)] = bundle(s, level=1, tools=block(n_reads=8 - level // 2))
    s = spec(knob="distractor", level=0, control=4)
    arms[k.arm_id(s)] = bundle(s, level=1, tools=block())
    assert "N4" not in failed_rows(k.check_pins(arms))


def test_n5_1_knob_rs_block_token_count_is_reported_and_never_refuses():
    """N5: "declared band; the difference is reported" and "reported.  The R control
    arm carries it".  The one row in the ledger whose failure is not a refusal, and
    the distinction is the point: R's block *must* change, so its token count is
    described, not held equal."""
    k = knobs()
    arms = {}
    for level, reads in ((0, 8), (4, 6)):
        s = spec(knob="distractor", level=level)
        arms[k.arm_id(s)] = bundle(s, level=1, tools=block(n_reads=reads))
    s = spec(knob="distractor", level=0, control=4)
    arms[k.arm_id(s)] = bundle(s, level=1, tools=block(n_reads=8))
    report = k.check_pins(arms)
    assert "N5" in reported_rows(report)
    assert "N5" not in failed_rows(report)
    assert report.refused is False


def test_n6_1_a_different_template_id_refuses():
    """N6: "template id equal".  One fixed template per knob, so two
    arms on two templates are two prompts, whatever their token counts say."""
    k = knobs()
    arms = depth_contrast()
    victim = sorted(arms)[0]
    arms[victim] = replaced(arms[victim], template_id="depth.v2")
    assert "N6" in failed_rows(k.check_pins(arms))


def test_n6_2_a_slot_whose_token_count_differs_refuses():
    """N6: "token count of the variable slots under the reference tokenizer", equal.
    The only slot that varies with `d` is the goal stage name, and stage names have an
    equal token count by construction (the engine's coverage list), so a difference here
    means the table's equal-count guarantee has been broken or a slot was added."""
    k = knobs()
    arms = depth_contrast()
    victim = sorted(arms)[0]
    long_slot = (("goal", "bundle bundle bundle bundle"),)
    arms[victim] = replaced(arms[victim], prompt_slots=long_slot)
    report = k.check_pins(arms)
    assert "N6" in failed_rows(report)
    assert report.refused is True


def test_n6_3_equal_counts_pass_even_when_the_slot_values_differ():
    """N6: it is the *token count* that is pinned, not the value.  The goal stage name
    is supposed to differ between levels; that is the knob."""
    k = knobs()
    arms = depth_contrast()
    stage_names = TABLE["stage_names"]
    assert len({ntok(s) for s in stage_names}) == 1, "the table's equal-count premise"
    for i, name in enumerate(sorted(arms)):
        arms[name] = replaced(arms[name], prompt_slots=(("goal", stage_names[i]),))
    assert "N6" not in failed_rows(k.check_pins(arms))


def test_n7_2_a_prompt_that_names_a_tool_in_one_arm_only_refuses():
    """N7: the set is measured over the prompt against the block's names, so adding a
    qualifier to one arm's prompt moves that arm's set and nothing else."""
    k = knobs()
    arms = depth_contrast()
    victim = sorted(arms)[0]
    arms[victim] = replaced(arms[victim], prompt="do the thing invoice")
    report = k.check_pins(arms)
    assert "N7" in failed_rows(report)
    assert report.refused is True


def test_n8_1_observation_size_is_cited_from_the_engines_frozen_literals():
    """N8: "`L_obs` exact; tokens in band", measured by E2.  The bundle's reference
    observations are engine output, so the row is measurable here; what it must not do
    is mint a second `L_obs` (a constraint carried over from the engine)."""
    k = knobs()
    b = bundle(spec(level=3))
    rec = k.measure_pins(b)
    widths, (tok_lo, tok_hi) = rec.values["N8"]
    assert tuple(widths) == (L_OBS,)
    assert BAND_LO <= tok_lo <= tok_hi <= BAND_HI
    for obs in b.reference_observations:
        assert len(obs.encode("ascii")) == L_OBS
        assert BAND_LO <= ntok(obs) <= BAND_HI


def test_n8_2_an_observation_of_the_wrong_width_refuses():
    """N8: "engine test fails" is the ledger's action, and it is not a report - a
    generation that has seen a wrong-width observation must not emit the task."""
    k = knobs()
    arms = depth_contrast()
    victim = sorted(arms)[0]
    b = arms[victim]
    arms[victim] = replaced(b, reference_observations=tuple(o[:-1] for o in b.reference_observations))
    report = k.check_pins(arms)
    assert "N8" in failed_rows(report)
    assert report.refused is True


def test_n9_1_the_seeded_history_is_compared_as_an_aggregate_not_per_pair():
    """N9: an aggregate band.  The comparison is the sum over the `H - dL` pairs against the
    sum over the chain pairs they stand in for, and **not** a per-pair equality.  A
    per-pair equality cannot be satisfied: 51.4% of chain calls are cheaper on
    arguments than any read call, and 3.0% of chain *pairs* are below the read pair
    floor, both measured against this table.  A pin that can never pass is worse than
    no pin, because generation would refuse every control arm ever built."""
    k = knobs()
    low, high = 1, 8
    arms = depth_contrast(low=low, high=high)
    control = k.arm_id(spec(level=low, control=high))
    high_arm = k.arm_id(spec(level=high))

    seeded = k.measure_pins(arms[control]).values["N9"]
    chain = k.measure_pins(arms[high_arm]).values["N9"]
    # One measured value per pair, so `check_pins` can sum and nothing else has to.
    assert len(seeded) == high - low
    assert len(chain) == high
    assert tuple(chain) == chain_pair_totals(arms[high_arm])
    # The comparison is over sums, and the stage-1 pair is outside it on both sides.
    assert isinstance(sum(seeded) - sum(chain[low:]), int)


def test_n9_2_the_declared_band_is_two_tokens_on_the_aggregate():
    """N9: the band this file freezes.  Minted at a measured residual of 0 over 256
    blocks of seven pairs across two disjoint scenarios, declared at +/- 2 - the same
    two-token margin, and the same empirical footing, as the engine's observation band."""
    k = knobs()
    row = {r.row_id: r for r in k.pin_ledger("depth")}["N9"]
    assert str(N9_BAND) in row.tolerance


def test_n9_3_a_control_inside_the_band_passes_and_one_outside_refuses():
    """N9: the band's two directions.  A seeded history two tokens off is admitted; one
    three tokens off is not, and it refuses rather than reporting, because a history
    that does not match is the confound the control arm exists to remove."""
    k = knobs()
    low, high = 1, 8
    for residual in (0, N9_BAND, -N9_BAND):
        clean = k.check_pins(depth_contrast(low=low, high=high, residual=residual))
        assert "N9" not in failed_rows(clean), residual
    for residual in (N9_BAND + 1, -(N9_BAND + 1)):
        report = k.check_pins(depth_contrast(low=low, high=high, residual=residual))
        assert "N9" in failed_rows(report), residual
        assert report.refused is True, residual


def test_n9_4_the_read_pairs_reachable_set_is_what_makes_the_aggregate_attainable():
    """N9: the structural fact the band rests on.  A read pair's reachable totals are
    *consecutive* integers, so every integer in their `(H - dL)`-fold sum is reachable
    and the aggregate can land exactly; the chain pair's range sits inside it but for
    a thin low tail.  Asserted against the ledger's own declared band, so the two
    cannot drift apart: if a later table breaks the consecutiveness, the band stops
    being justifiable and this test says so."""
    k = knobs()
    reachable = read_pair_totals()
    assert (min(reachable), max(reachable)) == N9_READ_PAIR_RANGE
    # The premise, stated over the sum and not over one pair: every integer in the
    # seven-fold range is a sum of seven reachable pair totals, so a generator can land
    # on the target exactly whenever the target is inside that range.
    sums = {0}
    for _ in range(7):
        sums = {a + b for a in sums for b in reachable}
    span = range(7 * min(reachable), 7 * max(reachable) + 1)
    assert set(span) - sums == set(), "the seven-fold sumset has a gap"
    # And the thin low tail that makes a *per-pair* equality impossible.
    chain_lo, chain_hi = N9_CHAIN_PAIR_RANGE
    assert chain_lo < min(reachable) <= chain_hi <= max(reachable)
    row = {r.row_id: r for r in k.pin_ledger("depth")}["N9"]
    assert row.on_violation == "refuse"


def test_n11_1_a_strictness_difference_refuses_the_start():
    """N11: "Verifier strictness, from the arm spec, equal".  Both predicates are always
    computed (by the task layer), so a strictness that varies by arm would change which label the
    confirmatory event uses mid-contrast."""
    k = knobs()
    arms = depth_contrast()
    victim = sorted(arms)[0]
    arms[victim] = replaced(arms[victim], verifier=Verifier(strictness="leaky"))
    report = k.check_pins(arms)
    assert "N11" in failed_rows(report)
    assert report.refused is True


def test_n12_1_the_engine_and_generator_hashes_are_held_equal():
    """N12: "Engine, vocabulary and generator hashes, recorded per task", equal.  The
    vocabulary is inside `engine_hash` by E10, so two fields carry three hashes."""
    k = knobs()
    for field in ("engine_hash", "generator_hash"):
        arms = depth_contrast()
        victim = sorted(arms)[0]
        arms[victim] = replaced(arms[victim], **{field: "moved"})
        report = k.check_pins(arms)
        assert "N12" in failed_rows(report), field
        assert report.refused is True


# --------------------------------------------------------------------------
# N14 to N18
# --------------------------------------------------------------------------


def test_n14_1_knob_d_changes_only_the_goal_stage_and_the_required_count():
    """N14: "generate the same seed under two arms and diff the bundles field by field.
    Only the named fields may differ."  For knob D the named fields are the goal stage
    and the required count, so every pinned field is equal between d1 and d8."""
    k = knobs()
    arms = depth_contrast(control=False)
    report = k.check_pins(arms)
    assert report.refused is False
    assert failed_rows(report) == set()


def test_n14_3_a_control_that_moves_a_field_outside_its_list_refuses():
    """N14: the list is exhaustive.  A control arm that also moved the block, the
    scenario or a hash would be changing what it claims to hold fixed, and the reason
    to name the fields is so that case is a refusal and not a judgment call."""
    k = knobs()
    low, high = 1, 8
    for field, value in (("scenario_hash", "other"), ("engine_hash", "other"),
                         ("system_prompt", "other sys"), ("template_id", "depth.v2")):
        arms = depth_contrast(low=low, high=high)
        control = k.arm_id(spec(level=low, control=high))
        arms[control] = replaced(control_with_residual(arms, low, high, 0), **{field: value})
        report = k.check_pins(arms)
        assert report.refused is True, field


def test_n14_4_knob_r_changes_only_the_designated_slots():
    """N14: "knob R: the contents of the designated slots".  The required tools' slots
    are a function of the seed only, so an R level that moved one is
    an N2 refusal, and the ledger says so rather than N14 needing its own machinery."""
    k = knobs()
    arms = {}
    for level in (0, 4):
        s = spec(knob="distractor", level=level)
        arms[k.arm_id(s)] = bundle(s, level=1, tools=block(n_reads=8 - level // 2))
    s = spec(knob="distractor", level=0, control=4)
    arms[k.arm_id(s)] = bundle(s, level=1, tools=block())
    assert "N2" not in failed_rows(k.check_pins(arms))
    victim = k.arm_id(spec(knob="distractor", level=4))
    b = arms[victim]
    arms[victim] = replaced(b, tools=(b.tools[-1],) + b.tools[:-1])
    assert "N2" in failed_rows(k.check_pins(arms))


def test_n15_1_each_knob_has_exactly_one_control_shape():
    """N15: "Every knob has exactly one control-arm constructor."  The control is an
    arm spec whose `control` field is set; there is no second way to build one, so the
    invariant is that a control's id is a function of `(knob, level, control)` alone
    and every knob renders exactly one control format."""
    k = knobs()
    formats = {}
    for knob in ("depth", "distractor"):
        ids = {k.arm_id(spec(knob=knob, level=lvl, control=c))
               for lvl in k.levels(knob) for c in k.levels(knob) if c > lvl}
        shapes = {_shape(i) for i in ids}
        formats[knob] = shapes
        assert len(shapes) == 1, (knob, shapes)
    assert formats["depth"] != formats["distractor"]


def _shape(arm_id_str: str) -> str:
    """An arm id with every run of digits replaced by `#`, so two ids of the same
    format compare equal."""
    out, prev_digit = [], False
    for ch in arm_id_str:
        if ch.isdigit():
            if not prev_digit:
                out.append("#")
            prev_digit = True
        else:
            out.append(ch)
            prev_digit = False
    return "".join(out)


def test_n15_3_a_control_against_a_level_that_is_not_higher_is_refused():
    """N15: a control stands in for a *higher* level's history.  `d3+h3` seeds nothing
    and `d8+h1` seeds a negative number of pairs, so both are construction errors
    rather than arms that generate and then fail a pin."""
    k = knobs()
    for low, high in ((3, 3), (8, 1), (8, 3)):
        try:
            k.arm_id(spec(level=low, control=high))
        except ValueError:
            continue
        raise AssertionError(f"a control d{low}+h{high} was accepted")


def test_n16_1_max_turns_is_the_reference_turns_plus_the_slack():
    """N16: "for every generated arm, `max_turns - reference_turns == S`", and the
    reference turn count is "one call per turn, plus the reply turn"."""
    k = knobs()
    for slack in (0, 1, 4):
        for level in k.levels("depth"):
            s = spec(level=level)
            assert s.reference_turns == level + 1
            assert s.max_turns(slack) - s.reference_turns == slack
        for level in k.levels("distractor"):
            s = spec(knob="distractor", level=level)
            assert s.reference_turns == D_R + 1
            assert s.max_turns(slack) - s.reference_turns == slack


@settings(max_examples=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(slack=st.integers(min_value=0, max_value=64),
       level=st.sampled_from(DEPTH_LEVELS),
       control=st.one_of(st.none(), st.sampled_from(DEPTH_LEVELS)))
@example(slack=4, level=1, control=8)
def test_n16_1b_the_slack_identity_holds_over_every_slack_and_level(slack, level, control):
    """N16, as a property: `max_turns(S) - reference_turns == S` for every slack and
    every candidate level, and the control's turn count follows `dL` and never `H`.
    Three hand-picked slacks cannot tell an identity from a table of three answers.

    "The depth control gets `dL + 1 + S`."  Seeded history uses no turns, so a `d1+h8`
    control needs two turns plus slack and not nine, which is the whole reason the turn
    budget is pinned as slack rather than as a total.  The explicit example is that
    control at S = 4."""
    if control is not None and control <= level:
        return
    s = spec(level=level, control=control)
    assert s.max_turns(slack) - s.reference_turns == slack
    assert s.reference_turns == level + 1


def test_n18_1_the_serving_pin_row_carries_n18s_requirements():
    """N18 is an invariant and not a ledger row; the ledger reaches it through N10,
    whose *Held fixed* text opens with "model id and revision (N18)".  So knobs.py's
    obligation is that the row states what the pin covers and where it is enforced."""
    k = knobs()
    rows = {r.row_id: r for r in k.pin_ledger("depth")}
    assert "N18" not in rows
    held = rows["N10"].held
    for piece in ("N18", "vLLM", "endpoint", "GPU"):
        assert piece in held, piece


# --------------------------------------------------------------------------
# CP - check_pins' own contract
# --------------------------------------------------------------------------


def test_cp1_arms_from_two_knobs_raise_rather_than_refuse():
    """CP1: `check_pins(bundles_by_arm)` runs over the arms of one knob - the
    ledger holds things fixed "across a contrast's arms".  Two knobs in one call is a
    caller error, not a pin violation, so it raises and does not come back as a report
    that a reader would file as a failed pin."""
    k = knobs()
    arms = depth_contrast(control=False)
    s = spec(knob="distractor", level=4)
    arms[k.arm_id(s)] = bundle(s, level=1)
    try:
        k.check_pins(arms)
    except ValueError:
        return
    raise AssertionError("check_pins accepted arms from two knobs")


def test_cp2_a_single_arm_is_not_a_contrast():
    """CP2: every ledger row is an equality *across* arms.  One arm satisfies all of
    them vacuously, so a one-arm call is refused rather than returning a clean report
    that says nothing."""
    k = knobs()
    s = spec(level=3)
    try:
        k.check_pins({k.arm_id(s): bundle(s, level=3)})
    except ValueError:
        return
    raise AssertionError("check_pins accepted a single arm as a contrast")


def test_cp3_the_report_names_the_knob_and_carries_every_arms_record():
    """CP3: the report is the artefact a pre-registration files, so it carries what a
    reader needs to re-check it: the knob, and one `PinRecord` per arm."""
    k = knobs()
    arms = depth_contrast()
    report = k.check_pins(arms)
    assert report.knob == "depth"
    assert set(report.records) == set(arms)
    for arm, rec in report.records.items():
        assert rec.arm_id == arm


def test_cp5_a_clean_contrast_refuses_nothing_and_reports_nothing():
    """CP5: the control case.  If the pilot's own three arms tripped a row, every test
    above that asserts a *specific* row fired would still pass while the ledger was
    refusing everything.

    It is also N14's D control case: the control's prompt `Messages` and its
    `seq_start` of `H - dL + 1` ride the arm, not the scenario, and neither may be read
    as an N1, N3, N6 or N7 violation."""
    k = knobs()
    low, high = 1, 8
    arms = depth_contrast(low=low, high=high)
    arms[k.arm_id(spec(level=low, control=high))] = control_with_residual(arms, low, high, 0)
    report = k.check_pins(arms)
    assert report.refused is False
    assert report.violations == ()
    assert report.reported == ()
