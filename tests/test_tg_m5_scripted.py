"""The Proofload adapter's scripted path: the arm targets, the two scripted policies, the
outcome map and the pre-registration validator, frozen as tests.

The invariants this file is built against are A1-A9 and A12, the two coverage gaps these
tests inherit from knobs.py's tests (N17's scripted `diff`, N18's revision predicate), and
knob R's level axis, which the task layer's build found uncovered.  The model path is for a
later set of tests.  The written requirements are not edited here: where they are silent
this docstring decides, and it is authoritative for the build wherever their text could not
be used as written.  Every decision below carries its reason and an escape hatch.

**The tests drive Proofload's real CLI.**  The scripted path must "run against Proofload end
to end".  A lazily built module-level `world()` builds both registries and runs seventeen real
`proofload sweep`s once (every arm of both knobs, two `faulty` arms over two plant cells, and
one run under another salt); the first test that needs a registered target builds it.
`test_a2_*`, `test_a3_*`, `test_a5_1`, `test_a5_2`, `test_a6_3` and `test_f8` read what those
sweeps stored, `test_a5_4` and `test_a5_5` run `proofload diff` over them, and `test_a5_6` and
`test_a7_5` run the CLI on their own; everything else calls targets or the outcome map in
process.  The stores are read from their files: no public verb prints an episode's `meta`
(gap log, PG-17).  The child interpreters inherit `PYTHONPATH`, so they import the same copy
of the package the tests do.

Decisions
---------

**1. The module is `poisson_tasks.adapter`, with five public names.**  `ArmRegistry`,
`load_registry`, `validate_preregistration`, `Run` and `to_episode`.  The written interface
names arm targets, a registry built from the pre-registration file, an outcome map and (through
N18) a pre-registration validator; each name is one an invariant cannot be tested without.
Every imported name is underscore-aliased, as `knobs.py` and `tasks.py` do, so SF2 holds.
The module imports no `verifiers` (the scripted path has "no verifiers dependency and no
model") and no network module; the model path puts what needs `verifiers` in modules of its own.
*Escape hatch:* rename any of the five; SF1, SF6 and the `adapter()` helper move.

**2. The registration file is TOML and the lock is over its bytes.**  Top level: `knob`,
`strictness`, `split`, `generator_version`, `slack`, `horizon` and `arms` (a list of
canonical arm ids), and optionally `[[models]]` tables of `model`, `vllm_version` and
`endpoint_type`.  Fields nobody here reads are tolerated, because the model path
adds the serve command, the decoding dict and the GPU type to the same file.  One shape
serves as the study's pre-registration *and* as the registration the scripted calibration
stage needs, since that stage runs before any pre-registration exists.
`load_registry(path, *, sha256, sealed=None)` hashes the file's raw bytes and compares the
whole digest, then validates, then builds; a registry *module* is
`REGISTRY = load_registry(...)` followed by `globals().update(REGISTRY.targets)`, which is
what "compiled in" means (A7).  A mismatch is a `RuntimeError` naming both hashes, one of the
four types `proofload sweep` turns into "cannot resolve --target" and exit 2, before any
episode is stored.  *Escape hatch:* a different file format changes `toml_text` and the
tomllib calls in this file and nothing else.

**3. A target is registered as `<policy>_<arm id>` with every run of non-alphanumeric
characters made one underscore.**  `depth:d1+h8` under `reference` is `reference_depth_d1_h8`,
and `distractor:r0+len(r8)@k16` is `reference_distractor_r0_len_r8_k16`.  An arm id holds
`:`, `+`, `(`, `)` and `@`, and `--target module:attr` refuses an attribute with a colon in
it, so "one module-level callable per arm" needs a rule for the name; the two policies
are `reference` and `faulty`, and `faulty` exists only when `load_registry` is given a sealed
file.  Pinned by literals in `test_a7_7` and not by the helper the rest of the file uses.
*Escape hatch:* any injective rule; `attr_of` and `test_a7_6`/`test_a7_7` move.

**4. The cfg contract.**  A target requires `slack`, `horizon`, `strictness` and
`generator_hash` (N10, N11, N12, N17: the sweep file declares them so they enter
`config_hash`), and each must equal the registration's or the generator's, else `ValueError`
naming the key: "the adapter refuses to start" has no start hook to live in, so a rollout
that raises is the only refusal Proofload can store.  A cfg that carries a knob level under
`level`, `depth`, `distractor`, `knob`, `arm`, `arm_id` or `max_turns` is refused too (A3):
a key like that moves `config_hash` and breaks pairing silently, which a target
that ignored it would hide.  **Every other key is tolerated and inert**, `model`,
`serving_pin`, `temperature` and `plant_cell` included: the model path runs the scripted
`reference` target on the model's real sweep file.  Integral floats are accepted, because `inspect`
prints a stored config with every number a float and A6 replays it.  *Escape hatch:* the
refusal set is one tuple; a cfg test moves with it.

**5. `t` is the number of assistant turns.**  A reply is a turn that makes no call, so a
reference episode of `d` calls has `t = d + 1`, N16's own count, and the wrong-state control
(one call fewer, then a reply) has `t = d`.  This is `Trace.num_turns` for a run with no
trace.  `Run` carries `turns` (the task layer's `Turn`s), `tool_messages`, `ended_with_reply`,
`turn_limit_hit`, `fmt` and an optional `instrument`; the model path builds one from a
verifiers trace.  `Run` is a plain record and validates nothing at construction (`test_sf8`),
because a structurally invalid trace has to reach `to_episode` to become a `verifier_error`.

**6. The outcome map's order.**  `to_episode(arm, bundle, run, *, slack, horizon, meta=None)`
assigns, in this order and first match wins: an exception in its own verification (the
replay or the verdict) is `verifier_error`; a replay that does not equal the trace's tool
messages byte for byte is `replay_mismatch`; the harness's `instrument` signal, `api_error` or
`wall_timeout`, is that label; otherwise the outcome is `verify`'s label under the arm's
strictness.  The signal outranks the verdict whatever state the trace shows (A4), and the
adapter never *infers* an instrument label: an unfinished episode with no signal is
the task layer's `verifier_error` (`test_a4_7`).  On an episode the adapter labelled itself,
`leaky_pass` is `False` and `strict_label` is the label.  *Escape hatch:* none needed; the
order is the outcome table's.

**7. `meta`** carries `arm_id`, `knob`, `level`, `control` (a bool: the control flag),
`task_id`, `scenario_hash`, `pins` (the bundle's `PinRecord`, JSON-normalised), `leaky_pass`,
`strict_label`, `sampled_calls`, `format_clause` (the one clause `verify` reports: the task
layer reports the lowest of "the clauses that fired"), `engine_hash`, `generator_hash` and the
caller's own keys (the scripted targets add `policy`).  The two hashes stand for the "engine
and generator versions" asked for: N12 records hashes per task, and a hash moves with any
version change.  What only a model run has (input tokens, the verifiers trace id and path,
the verifiers version and the serving-pin hash) is the model path's to add.

**8. `to_episode` refuses what would break A5 or A3.**  An `arm` that is not the bundle's, an
`instrument` outside the closed vocabulary, more turns than `max_turns(arm)` and a `horizon`
below it each raise `ValueError` naming the offending value, and the boundaries themselves
(`t == max_turns`, `horizon == max_turns`) are accepted.  *Escape hatch:* `test_a5_7`,
`test_map3` and `test_a4_5`.

**9. The scripted targets look the outcome map up by module global, at call time.**  A9
says both paths share the verdict -> Episode code, so `test_a9_2` replaces
`poisson_tasks.adapter.to_episode` and expects both scripted targets to reach it, the way
the task layer's tests fault-inject `verify` and `_check_pins`.  A target that built its own
Episode or captured the function when the registry was built fails it.  The model path's tests add
the same seam for model targets.  *Escape hatch:* any other injectable seam; `test_a9_2` and
`test_a9_3` move.

**10. The validator holds three clauses no other module's tests hold, and refuses by name.**
`validate_preregistration(document)` raises `ValueError` whose message names the offending
key or value (a refusal that did not would pass any test of it for the wrong clause).  N18's
predicate (owed since 2026-09-13): each `model` is `<HF id>@<revision>` with exactly one `@`,
a non-empty id and a revision of 40 hex characters; models on different `vllm_version`s or
`endpoint_type`s are refused; a model that omits either cannot be shown to agree and is
refused.  N15's pre-registration half, which nothing held ("a sweep of a knob without its
control arm is a pre-registration error"): at least one control arm.  N17's declared number:
`horizon` equals `max(max_turns)` over the arms, from `slack` by N16.  Also: `split` is `eval`
(G12, "v0 emits `eval` only", which the task layer left to the pre-registration),
`strictness` is `strict` or `leaky`, `arms` are canonical, distinct arm ids of the
registration's knob, and `slack` is a non-negative integer.  **Deliberately not pinned:**
whether an *uppercase* 40-hex revision is accepted ("40 hex characters" reads either
way, and the model path compares strings byte for byte at run time).  *Escape hatch:* each
clause is one parametrised test.

**11. `faulty` and its sealed file.**  `faulty` "takes planted parameters from a
sealed calibration file, selected by `cfg["plant_cell"]`", is "fully deterministic" from the
seed and "reads history from the bundle's prompt `Messages` plus its own calls".  The sealed
file is TOML: `[cells.<name>]` tables of `step_fail_rate`, `history_fail_rate` and
`overshoot_rate`, each a number in [0, 1], all defaulting to 0, refused *at load* when a key is
unknown or a value is out of range (a mistyped parameter would otherwise be a plant that
silently does nothing).  A `plant_cell` the file does not name is refused, and a cell with no
plant behaves as the reference target exactly.  The three plants are the required three:
**depth** fails each required call independently at `step_fail_rate`; **history** fails a
required call with probability `min(1, history_fail_rate * history tokens)`, the tokens being
those of the seeded prompt messages plus the policy's own calls and observations so far,
counted under the reference tokenizer; **leaky** makes one further stage call past the goal
with probability `overshoot_rate` when the block holds a tool that can (the task layer's rule for
an `overshoot` control).  A *failed* call is made with a wrong token, the engine rejects it,
and the policy replies: two turns, one sampled call, target below its goal.  The tests
exercise the extremes (rates 0 and 1) exactly and a half rate statistically, with margins many
standard deviations wide, so no test depends on which keyed draw a build uses.  These are the
least anchored decisions in the file; the plants' *scoring* is the calibration stage's and is
not here.
*Escape hatch:* the plant semantics are `test_f3` to `test_f7`.

**12. Inherited coverage: knob R's level axis.**  The task layer's tests build one contrast,
`r0` against `r8`, at three seeds, and four of the mutation rows run against its build
survived its 235 tests for that reason.  Every test here that checks what a knob R arm
generates, stores or labels runs over `levels("distractor")` and both R controls, or over
every stored run; the tests of a *rule* (`test_cfg2` to `test_cfg7`, `test_map1`, `test_a4_2`,
`test_a4_6`, `test_a4_7`, `test_a5_7`, `test_a5_8`, `test_a8_5`) fix one to four arms,
`SPEC_D3` and `SPEC_R4` mainly, and claim no level.  `test_ct*` reach the task layer's ledger
through the registered arm sets, `test_ct5` on one pair, `r0` against `r14`, at a dense spread.
`test_ct3` and `test_ct4` did the same on the seeds whose first record-id word a tool name
carried, until vocabulary v2 left them no such seed and its test retrofit retired them; the three
task-layer rows only `test_ct3` caught are pinned in `tests/test_tg_m3_tasks.py`.  **The open
record-id gap is wider than recorded**: measured here at 60 seeds per word, `city` (eval),
`grad` and `port` (train) refuse a knob R contrast at `r14` at every seed, and so does `disc`
(train) at 43 of 60, which the record does not name; `face` and `elect` refuse none, and
nothing below `r14` refuses for any of the six.  The four are excluded from any contrast
that holds `r14` and asserted nowhere: pinning a known defect would need a retrofit the day
it closes.  Every `test_ct*`, `test_a5_6`, `test_a1_3` and `test_h1` are **green before and
after**.

What this file does not freeze
------------------------------
A4's *end-to-end* fault injection (a vLLM server dying mid-episode) and A9's model-path half
belong to the model path: the scripted path has no server, so here the fault is injected where
the label is assigned.  A12's own event loop, env and tool server are the model path's; the
scripted path owns none, and what it can own (no shared state, no running loop, no thread) is
pinned.  The pre-registration's serve command, decoding dict, GPU type, serving-pin hash and
context check are the model path's fields of the same file.  The exact wording of any refusal
beyond the key or value it names is unpinned.
"""

from __future__ import annotations

import ast
import asyncio
import atexit
import copy
import dataclasses
import hashlib
import importlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import tomllib
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from poisson_tasks.engine import apply, init_state
from poisson_tasks.knobs import ArmSpec, arm_id, levels
from poisson_tasks.tasks import (
    OUTCOMES,
    FormatSpec,
    Turn,
    encode_record_id,
    generate,
    generate_contrast,
    scenario_for,
    verify,
)

# ---------------------------------------------------------------------------
# independent constants: every number below is a requirement's, written here again on purpose,
# so that no test compares a build's value with the build's own arithmetic
# ---------------------------------------------------------------------------

GEN_VERSION = "0"
SLACK = 4  # S, the confirmed slack
D_R = 2  # knob R's fixed chain depth
SALT = "0123456789abcdef"
OTHER_SALT = "fedcba9876543210"
MAX_MDE = "0.99"  # the gate's own refusal at N = 8 needs a looser value; it must be in (0, 1)
REPLICATES = 8
DIRECT = FormatSpec(name="direct", markers=())

D_PLAIN = levels("depth")
R_PLAIN = levels("distractor")
D_CONTROLS = ((1, 8), (2, 5))
R_CONTROLS = ((0, 8), (2, 14))

SIMPLE_MODELS = (
    {
        "model": "Qwen/Qwen3.5-9B@c202236235762e1c871ad0ccb60c8ee5ba337b9a",
        "vllm_version": "0.29.0",
        "endpoint_type": "openai-chat-completions",
    },
    {
        "model": "mistralai/Ministral-3-14B-Instruct-2512@29439f81c2be264d8d393273f99e7db9c0961120",
        "vllm_version": "0.29.0",
        "endpoint_type": "openai-chat-completions",
    },
)

PLANTS = {
    "clean": {},
    "planted": {"step_fail_rate": 1.0},
    "depth_half": {"step_fail_rate": 0.5},
    "history_full": {"history_fail_rate": 1.0},
    "overshoot_full": {"overshoot_rate": 1.0},
}

STORE_ROW_KEYS = ("config_hash", "replicate_index", "seed", "outcome", "t", "horizon", "error")


def spec_of(knob: str, level: int, control: int | None = None, strictness: str = "strict") -> ArmSpec:
    return ArmSpec(
        knob=knob,
        level=level,
        control=control,
        strictness=strictness,
        split="eval",
        generator_version=GEN_VERSION,
    )


D_SPECS = tuple(spec_of("depth", lvl) for lvl in D_PLAIN) + tuple(
    spec_of("depth", lvl, ctl) for lvl, ctl in D_CONTROLS
)
R_SPECS = tuple(spec_of("distractor", lvl) for lvl in R_PLAIN) + tuple(
    spec_of("distractor", lvl, ctl) for lvl, ctl in R_CONTROLS
)
ALL_SPECS = D_SPECS + R_SPECS


def aid(spec: ArmSpec) -> str:
    return arm_id(spec)


def spec_ids(specs: Iterable[ArmSpec]) -> list[str]:
    return [aid(s) for s in specs]


def expected_max_turns(spec: ArmSpec, slack: int = SLACK) -> int:
    """N16, written again: the reference solution's turns plus the one slack constant.
    A depth arm needs `d + 1` (its control needs its own `dL + 1`); every R arm needs
    `d_R + 1`."""
    needed = spec.level + 1 if spec.knob == "depth" else D_R + 1
    return needed + slack


H_D = max(expected_max_turns(s) for s in D_SPECS)
H_R = max(expected_max_turns(s) for s in R_SPECS)


def horizon_of(spec: ArmSpec) -> int:
    return H_D if spec.knob == "depth" else H_R


GEN_HASH = generate(D_SPECS[0], 0).generator_hash


def attr_of(policy: str, arm: str) -> str:
    """The module attribute a target is registered under: the policy, then the arm id with
    every run of non-alphanumeric characters made one underscore.  Written again here
    rather than imported, and pinned by literals in `test_a7_7`."""
    return policy + "_" + re.sub(r"[^0-9A-Za-z]+", "_", arm)


def cfg_of(spec: ArmSpec, **over: Any) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "slack": SLACK,
        "horizon": horizon_of(spec),
        "strictness": "strict",
        "generator_hash": GEN_HASH,
    }
    cfg.update(over)
    return cfg


def adapter() -> Any:
    return importlib.import_module("poisson_tasks.adapter")


def run_of(**kw: Any) -> Any:
    return adapter().Run(**kw)


@cache
def bundle_of(spec: ArmSpec, seed: int) -> Any:
    return generate(spec, seed)


# ---------------------------------------------------------------------------
# seeds: a spread over the 32-bit space, and the seeds whose first record-id word is one
# some tool name carries (measured against the task layer's build), which `test_ct3` and `test_ct4`
# used until vocabulary v2's test retrofit retired them.  Vocabulary v2 draws no such word, so
# `RISKY_WORDS` and the helpers that read it find no seed and are unused; `GAP_WORDS` still
# filters `test_ct2`'s and `test_ct5`'s seeds.
# ---------------------------------------------------------------------------


def spaced(count: int, offset: int = 7) -> tuple[int, ...]:
    step = 2**32 // count
    return tuple((offset + i * step) % 2**32 for i in range(count))


SPREAD = (0, 1, 2, 55, 404, 2121, 65535, 2**24, 2**31 - 1, 2**32 - 1)
SPACED = spaced(24)
RISKY_WORDS = {"eval": ("city", "face"), "train": ("disc", "elect", "grad", "port")}
# The open record-id gap: these words refuse a knob R contrast that holds `r14`.  The gap's
# record names three (`city`, `grad`, `port`); measured here at 60 seeds per word, a fourth
# does too -- `disc` refuses 43 of 60 -- while `face` and `elect` refuse none, and nothing
# below `r14` refuses for any of the six.  They are excluded from any contrast that holds
# an `r14` arm and are not asserted anywhere.
GAP_WORDS = {"eval": ("city",), "train": ("disc", "grad", "port")}


@cache
def word_seed(word: str, split: str, k: int = 0) -> int:
    for index in range(256):
        if encode_record_id(index << 24, split).split("-")[0] == word:
            return (index << 24) + k
    raise LookupError(word)


def risky_seeds(split: str = "eval", per_word: int = 6) -> tuple[int, ...]:
    return tuple(
        word_seed(word, split, k * 7919)
        for word in RISKY_WORDS[split]
        for k in range(per_word)
    )


# ---------------------------------------------------------------------------
# registration, sealed and sweep files
# ---------------------------------------------------------------------------


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    return json.dumps(value)


def toml_text(doc: Mapping[str, Any]) -> str:
    """The flat registration schema as TOML: scalars and arrays first, then `[[models]]`."""
    lines = [f"{key} = {toml_value(value)}" for key, value in doc.items() if key != "models"]
    for model in doc.get("models", ()):
        lines.append("")
        lines.append("[[models]]")
        lines.extend(f"{key} = {toml_value(value)}" for key, value in model.items())
    return "\n".join(lines) + "\n"


def reg_doc(
    knob: str, specs: Iterable[ArmSpec], *, models: Iterable[Mapping[str, str]] = SIMPLE_MODELS, **over: Any
) -> dict[str, Any]:
    specs = tuple(specs)
    doc: dict[str, Any] = {
        "knob": knob,
        "strictness": "strict",
        "split": "eval",
        "generator_version": GEN_VERSION,
        "slack": SLACK,
        "horizon": max(expected_max_turns(s) for s in specs),
        "arms": [aid(s) for s in specs],
    }
    models = tuple(models)
    if models:
        doc["models"] = [dict(m) for m in models]
    doc.update(over)
    return doc


def sealed_text(cells: Mapping[str, Mapping[str, float]]) -> str:
    lines: list[str] = []
    for name, params in cells.items():
        lines.append(f"[cells.{name}]")
        lines.extend(f"{key} = {toml_value(value)}" for key, value in params.items())
        lines.append("")
    return "\n".join(lines)


def sweep_text(horizon: int, plant_cells: Iterable[str] | None = None) -> str:
    """One sweep file per knob, with every axis single-valued (the required cfg shape); the
    two-cell variant adds `plant_cell`, which is the calibration stage's way of naming a plant."""
    text = (
        'target_id = "tg-m5-scripted@test"\n'
        't_unit = "turns"\n'
        f"replicates = {REPLICATES}\n\n"
        f'[axes.slack]\ntype = "continuous"\nvalues = [{SLACK}]\n\n'
        f'[axes.horizon]\ntype = "continuous"\nvalues = [{horizon}]\n\n'
        '[axes.strictness]\ntype = "categorical"\nvalues = ["strict"]\n\n'
        f'[axes.generator_hash]\ntype = "categorical"\nvalues = ["{GEN_HASH}"]\n'
    )
    if plant_cells is not None:
        text += f'\n[axes.plant_cell]\ntype = "categorical"\nvalues = {json.dumps(list(plant_cells))}\n'
    return text


def sha_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def registry_module_text(reg: Path, sha: str, sealed: Path | None) -> str:
    return (
        "from poisson_tasks.adapter import load_registry\n"
        f"REGISTRY = load_registry({str(reg)!r}, sha256={sha!r}, "
        f"sealed={None if sealed is None else str(sealed)!r})\n"
        "globals().update(REGISTRY.targets)\n"
    )


# ---------------------------------------------------------------------------
# the real CLI, and the store's files
# ---------------------------------------------------------------------------


def child_env(extra: Path | None = None, **more: str) -> dict[str, str]:
    env = dict(os.environ)
    parts = [str(extra)] if extra is not None else []
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    if parts:
        env["PYTHONPATH"] = os.pathsep.join(parts)
    env.update(more)
    return env


def cli(store: Path, *args: str, mods: Path | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "proofload", "--store", str(store), *args],
        env=child_env(mods),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def sweep(
    store: Path,
    spec: Path,
    target: str,
    *,
    mods: Path,
    salt: str | None = SALT,
    pair_with: str | None = None,
) -> str:
    args = ["sweep", str(spec), "--target", target, "--max-mde", MAX_MDE, "--yes"]
    args += ["--pair-with", pair_with] if pair_with is not None else ["--salt", str(salt)]
    done = cli(store, *args, mods=mods)
    found = re.search(r"^run_id: (\S+)$", done.stdout, re.M)
    if done.returncode != 0 or found is None:
        raise AssertionError(
            f"sweep {target} exited {done.returncode}\n--- stdout\n{done.stdout}\n--- stderr\n{done.stderr}"
        )
    return found.group(1)


def read_rows(store: Path, run_id: str) -> list[dict[str, Any]]:
    """A run's rows, read from the store's own files.  Proofload's public verbs print no
    episode `meta` (`inspect` prints traces, `diff` never reads it), so A2, A3 and A6 have
    no public route to what they assert.  The files are the route PG-13 already asks
    Proofload to document; the `Store` class is the workaround not taken (gap log, PG-17)."""
    import pyarrow.parquet as pq

    rows: list[dict[str, Any]] = []
    for part in sorted((store / run_id / "episodes").glob("part-*.parquet")):
        rows.extend(pq.read_table(part).to_pylist())
    for row in rows:
        row["meta"] = json.loads(row["meta"])
        row["config"] = json.loads(row["config"])
    return sorted(rows, key=lambda r: (r["config_hash"], r["replicate_index"]))


def pairs_of(rows: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    return {(r["config_hash"], r["replicate_index"]): r for r in rows}


# ---------------------------------------------------------------------------
# the test-side live executor: the engine, run directly, as a harness would.  It is how a
# `Run` is built for the outcome map, and it uses nothing from the adapter but the `Run`
# type it hands in.
# ---------------------------------------------------------------------------


def make_run(
    bundle: Any,
    calls: Iterable[tuple[str, Any]],
    *,
    reply: bool = True,
    turn_limit: bool = False,
    instrument: str | None = None,
    fmt: FormatSpec = DIRECT,
) -> Any:
    state = init_state(scenario_for(bundle.seed, bundle.split), bundle.seq_start)
    turns: list[Turn] = []
    messages: list[str] = []
    for call in calls:
        state, observation = apply(state, call)
        messages.append(observation)
        turns.append(Turn(content="", calls=(call,), finish_reason="tool_calls"))
    if reply:
        turns.append(Turn(content="Done.", calls=(), finish_reason="stop"))
    return run_of(
        turns=tuple(turns),
        tool_messages=tuple(messages),
        ended_with_reply=reply,
        turn_limit_hit=turn_limit,
        fmt=fmt,
        instrument=instrument,
    )


def controls_of(bundle: Any) -> dict[str, tuple[Any, bool, bool]]:
    """Every episode shape the bundle can express: label -> (calls, reply, turn_limit_hit).
    `passed` is the reference itself; the rest are the task layer's negative controls."""
    out: dict[str, tuple[Any, bool, bool]] = {"passed": (bundle.reference_calls, True, False)}
    for label, calls in bundle.negative_controls.items():
        if label == "turn_limit":
            out[label] = (calls, False, True)
        else:
            out[label] = (calls, True, False)
    return out


def system_label(control: str) -> str:
    return "malformed_call" if control.startswith("malformed_call") else control


def episode_of(spec: ArmSpec, bundle: Any, run: Any, *, slack: int = SLACK, horizon: int | None = None) -> Any:
    return adapter().to_episode(
        spec, bundle, run, slack=slack, horizon=horizon if horizon is not None else horizon_of(spec)
    )


def json_norm(value: Any) -> Any:
    return json.loads(json.dumps(value))


def episode_dict(episode: Any) -> dict[str, Any]:
    return json_norm(episode.to_dict())


# ---------------------------------------------------------------------------
# the world: registries, registry modules, sweep files and every real run the end-to-end
# tests read.  Built once, lazily, and inside a test body, so a missing module is a test
# failure with one cause rather than a setup error.
# ---------------------------------------------------------------------------


@dataclass
class World:
    root: Path
    store: Path
    mods: Path
    d_reg: Path
    d_sha: str
    r_reg: Path
    r_sha: str
    sealed: Path
    d_sweep: Path
    r_sweep: Path
    f_sweep: Path
    d_registry: Any
    r_registry: Any
    runs: dict[tuple[str, str], str]
    paired_arm: str


_WORLD: dict[str, Any] = {}


def world() -> World:
    if "world" in _WORLD:
        return _WORLD["world"]
    if "error" in _WORLD:
        raise AssertionError(_WORLD["error"])
    try:
        built = _build_world()
    except AssertionError as exc:
        _WORLD["error"] = str(exc)
        raise
    except ModuleNotFoundError as exc:
        _WORLD["error"] = f"ModuleNotFoundError: {exc}"
        raise
    _WORLD["world"] = built
    return built


def _build_world() -> World:
    root = Path(tempfile.mkdtemp(prefix="tg-m5-"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    store, mods = root / "store", root / "mods"
    mods.mkdir()
    d_reg, r_reg, sealed = root / "depth.toml", root / "distractor.toml", root / "sealed.toml"
    d_reg.write_text(toml_text(reg_doc("depth", D_SPECS)))
    r_reg.write_text(toml_text(reg_doc("distractor", R_SPECS)))
    sealed.write_text(sealed_text(PLANTS))
    d_sha, r_sha = sha_of(d_reg), sha_of(r_reg)
    mod = adapter()
    d_registry = mod.load_registry(d_reg, sha256=d_sha, sealed=sealed)
    r_registry = mod.load_registry(r_reg, sha256=r_sha, sealed=sealed)
    (mods / "regd.py").write_text(registry_module_text(d_reg, d_sha, sealed))
    (mods / "regr.py").write_text(registry_module_text(r_reg, r_sha, sealed))
    d_sweep, r_sweep, f_sweep = root / "sweep_d.toml", root / "sweep_r.toml", root / "sweep_f.toml"
    d_sweep.write_text(sweep_text(H_D))
    r_sweep.write_text(sweep_text(H_R))
    f_sweep.write_text(sweep_text(H_D, plant_cells=("planted", "clean")))

    runs: dict[tuple[str, str], str] = {}
    first = D_SPECS[0]
    first_id = aid(first)
    runs[("reference", first_id)] = sweep(
        store, d_sweep, f"regd:{attr_of('reference', first_id)}", mods=mods
    )
    paired_arm = aid(D_SPECS[3])  # the run that reaches the shared salt through --pair-with

    jobs: list[tuple[tuple[str, str], Path, str, str, str | None]] = []
    for spec in D_SPECS[1:]:
        a = aid(spec)
        pair = runs[("reference", first_id)] if a == paired_arm else None
        jobs.append((("reference", a), d_sweep, f"regd:{attr_of('reference', a)}", SALT, pair))
    for spec in R_SPECS:
        a = aid(spec)
        jobs.append((("reference", a), r_sweep, f"regr:{attr_of('reference', a)}", SALT, None))
    for spec in (D_SPECS[2], D_SPECS[5]):  # d3 and the d1+h8 control, two plant cells each
        a = aid(spec)
        jobs.append((("faulty", a), f_sweep, f"regd:{attr_of('faulty', a)}", SALT, None))
    jobs.append((("unpaired", first_id), d_sweep, f"regd:{attr_of('reference', first_id)}", OTHER_SALT, None))

    def go(job: tuple[tuple[str, str], Path, str, str, str | None]) -> tuple[tuple[str, str], str]:
        key, spec_file, target, salt, pair = job
        return key, sweep(store, spec_file, target, mods=mods, salt=salt, pair_with=pair)

    with ThreadPoolExecutor(max_workers=6) as pool:
        for key, run_id in pool.map(go, jobs):
            runs[key] = run_id
    return World(
        root=root, store=store, mods=mods, d_reg=d_reg, d_sha=d_sha, r_reg=r_reg, r_sha=r_sha,
        sealed=sealed, d_sweep=d_sweep, r_sweep=r_sweep, f_sweep=f_sweep, d_registry=d_registry,
        r_registry=r_registry, runs=runs, paired_arm=paired_arm,
    )


def target_of(policy: str, spec: ArmSpec) -> Any:
    w = world()
    registry = w.d_registry if spec.knob == "depth" else w.r_registry
    return registry.targets[attr_of(policy, aid(spec))]


def rows_of(policy: str, spec: ArmSpec) -> list[dict[str, Any]]:
    w = world()
    return read_rows(w.store, w.runs[(policy, aid(spec))])


def spec_by_id(arm: str) -> ArmSpec:
    return next(s for s in ALL_SPECS if aid(s) == arm)


HYP = settings(
    max_examples=40,
    deadline=None,
    derandomize=True,
    database=None,
    suppress_health_check=list(HealthCheck),
)


# ===========================================================================
# SF · the public surface
# ===========================================================================

PUBLIC = ["ArmRegistry", "load_registry", "validate_preregistration", "Run", "to_episode"]


def test_sf1_all_is_exactly_the_five_names_in_order():
    """The written interface names arm targets, a registry built from the pre-registration file, a
    pre-registration validator (N18) and an episode mapping.  Five public names carry them;
    an extra public symbol is a contract violation, so each is justified in the module docstring."""
    assert list(adapter().__all__) == PUBLIC


def test_sf2_no_public_symbol_beyond_all():
    mod = adapter()
    leaked = sorted(
        n for n in vars(mod) if not n.startswith("_") and n not in set(mod.__all__) and n != "annotations"
    )
    assert leaked == []


def test_sf3_the_two_types_are_frozen_dataclasses():
    mod = adapter()
    for cls in (mod.Run, mod.ArmRegistry):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen, cls


def test_sf4_run_carries_the_six_fields_in_order():
    fields = dataclasses.fields(adapter().Run)
    assert [f.name for f in fields] == [
        "turns", "tool_messages", "ended_with_reply", "turn_limit_hit", "fmt", "instrument",
    ]
    assert fields[-1].default is None
    assert all(f.default is dataclasses.MISSING for f in fields[:-1])


def test_sf5_arm_registry_carries_four_fields():
    assert [f.name for f in dataclasses.fields(adapter().ArmRegistry)] == [
        "arms", "slack", "horizon", "targets",
    ]


def test_sf6_the_three_signatures_are_the_ones_the_docstring_states():
    mod = adapter()
    load = inspect.signature(mod.load_registry).parameters
    assert list(load) == ["path", "sha256", "sealed"]
    assert load["sha256"].kind is inspect.Parameter.KEYWORD_ONLY
    assert load["sealed"].kind is inspect.Parameter.KEYWORD_ONLY and load["sealed"].default is None
    to = inspect.signature(mod.to_episode).parameters
    assert list(to) == ["arm", "bundle", "run", "slack", "horizon", "meta"]
    assert all(to[n].kind is inspect.Parameter.KEYWORD_ONLY for n in ("slack", "horizon", "meta"))
    assert to["meta"].default is None
    assert list(inspect.signature(mod.validate_preregistration).parameters) == ["document"]




def adapter_tree() -> ast.Module:
    return ast.parse(Path(adapter().__file__).read_text(encoding="utf-8"))


def imports_of(tree: ast.AST) -> list[tuple[str, list[str], int]]:
    """Every import as (module, imported names, relative level).  An `ast` walk, never a
    substring match on source."""
    found: list[tuple[str, list[str], int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((a.name, [], 0) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", [a.name for a in node.names], node.level))
    return found


def test_sf7_the_scripted_path_has_no_verifiers_and_no_network():
    """The scripted path runs "with no verifiers dependency and no model", and no episode
    may touch the network.  The model path puts anything
    that needs `verifiers` in its own modules, so this module stays free of it."""
    banned = {"verifiers", "socket", "urllib", "http", "requests", "httpx", "aiohttp", "openai"}
    roots = {module.split(".")[0] for module, _names, _level in imports_of(adapter_tree())}
    assert not roots & banned, sorted(roots & banned)


def test_sf8_a_run_is_a_plain_record_and_validates_nothing_at_construction():
    """A `Run` is what a harness hands the outcome map, and the map decides what to make of
    it.  Building one from a structurally invalid trace must not raise: `test_a4_6` needs the
    invalid trace to reach `to_episode`, where it is a `verifier_error` and not an exception
    at the caller."""
    bad = Turn(content="", calls=(5,), finish_reason="tool_calls")
    run = adapter().Run(turns=(bad,), tool_messages=(), ended_with_reply=False, turn_limit_hit=False, fmt=DIRECT)
    assert run.turns == (bad,) and run.instrument is None


# ===========================================================================
# A1 · public API only
# ===========================================================================

_ALLOWED_PROOFLOAD = {"Episode", "Rollout"}
_DOTTED = re.compile(r"^proofload\.[A-Za-z_][\w.]*$")  # "proofload" alone is the CLI's name


def proofload_violations(tree: ast.AST) -> list[str]:
    """A1: "From `proofload`, only `Episode` and `Rollout` are imported, plus the CLI."  So a
    `from proofload import` of those two names is the one permitted shape: `import proofload`,
    a deep `from proofload.x import`, any other name, and a dynamic import of a proofload
    module by string are each a violation."""
    bad: list[str] = []
    for module, names, level in imports_of(tree):
        if level == 0 and module.split(".")[0] == "proofload":
            if module != "proofload" or not names or not set(names) <= _ALLOWED_PROOFLOAD:
                bad.append(f"{module}: {names}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _DOTTED.match(node.value):
            bad.append(f"string {node.value!r}")
    return bad


def test_a1_1_only_episode_and_rollout_are_imported_from_proofload():
    assert proofload_violations(adapter_tree()) == []


def test_a1_2_the_walker_sees_the_import_the_adapter_must_make():
    """The control for A1.1: a walker that found no imports at all would pass it.  The
    adapter builds `proofload.Episode`, so the one permitted import has to be there."""
    seen = [(m, n) for m, n, level in imports_of(adapter_tree()) if m == "proofload" and level == 0]
    assert seen and all(set(n) <= _ALLOWED_PROOFLOAD for _m, n in seen)
    assert any("Episode" in n for _m, n in seen)


@pytest.mark.parametrize(
    "source",
    [
        "from proofload.store import config_hash",
        "import proofload.store",
        "import proofload",
        "from proofload import Episode, derive_seed",
        "from proofload.episode import Episode",
        "import importlib\nimportlib.import_module('proofload.store')",
    ],
)
def test_a1_3_the_walker_flags_every_shape_that_is_not_the_one_permitted(source):
    """Green before and after: it tests this file's own walker, which is
    what makes A1.1 able to fail."""
    assert proofload_violations(ast.parse(source)) != []
    assert proofload_violations(ast.parse("from proofload import Episode, Rollout")) == []


# ===========================================================================
# CFG · what a target accepts, and refuses
# ===========================================================================

REQUIRED_CFG = ("slack", "horizon", "strictness", "generator_hash")
LEVEL_KEYS = ("level", "depth", "distractor", "knob", "arm", "arm_id", "max_turns")
SPEC_D3, SPEC_R4 = spec_of("depth", 3), spec_of("distractor", 4)
EXTRA_CFG = {
    "model": "Qwen/Qwen3.5-9B@c202236235762e1c871ad0ccb60c8ee5ba337b9a",
    "serving_pin": "abc123",
    "harness": "null",
    "harness_version": "0.3.1",
    "endpoint_type": "openai-chat-completions",
    "temperature": 0.7,
    "max_input_tokens": 20480,
}


def test_cfg1_a_complete_cfg_gives_an_episode_for_every_arm_under_both_policies():
    """The control for everything below: a target that refused every cfg would pass all of
    the refusal tests."""
    for spec in ALL_SPECS:
        ref = target_of("reference", spec)(cfg_of(spec), 404)
        assert ref.outcome == "passed", aid(spec)
        clean = target_of("faulty", spec)(cfg_of(spec, plant_cell="clean"), 404)
        assert clean.outcome == "passed", aid(spec)


@pytest.mark.parametrize("missing", REQUIRED_CFG)
def test_cfg2_a_cfg_missing_a_required_key_is_refused_by_name(missing):
    spec = SPEC_D3
    cfg = cfg_of(spec)
    del cfg[missing]
    with pytest.raises(ValueError, match=re.escape(missing)):
        target_of("reference", spec)(cfg, 404)


@pytest.mark.parametrize("key", LEVEL_KEYS)
def test_cfg3_a_cfg_that_carries_a_knob_level_is_refused_by_name(key):
    """A3: "cfg carries no knob level": the level lives in the target, because
    a cfg key moves `config_hash`, which moves seeds and breaks `diff`'s cell matching.  A
    target that ignored such a key would look fine while its arms could not pair."""
    for spec in (SPEC_D3, SPEC_R4):
        with pytest.raises(ValueError, match=re.escape(key)):
            target_of("reference", spec)(cfg_of(spec, **{key: 3}), 404)


@pytest.mark.parametrize(
    ("key", "bad"),
    [("slack", 5), ("horizon", 99), ("strictness", "leaky"), ("generator_hash", "0" * 64)],
)
def test_cfg4_a_cfg_that_disagrees_with_the_registration_is_refused_by_name(key, bad):
    """N10, N11 and N12: slack, horizon, strictness and the generator hash are pins the
    sweep file declares and the registration froze.  A disagreement means the sweep file was
    written against another registration, and every episode would carry numbers that are not
    the ones it ran under."""
    spec = SPEC_D3
    with pytest.raises(ValueError, match=re.escape(key)):
        target_of("reference", spec)(cfg_of(spec, **{key: bad}), 404)


def test_cfg5_model_path_keys_are_tolerated_and_change_nothing():
    """The model path runs "the scripted `reference` target on that run's sweep file" — the
    model's real one, which carries `model`, `serving_pin`, `harness`, `temperature` and the
    token limits.  The scripted path does not read them, and must not refuse them."""
    for spec in (SPEC_D3, SPEC_R4):
        plain = target_of("reference", spec)(cfg_of(spec), 2121)
        wide = target_of("reference", spec)(cfg_of(spec, **EXTRA_CFG, plant_cell="anything"), 2121)
        assert episode_dict(plain) == episode_dict(wide)


def test_cfg6_the_integral_floats_a_stored_config_carries_are_accepted():
    """`inspect` prints a stored row's config with every number a float, and A6's "any
    episode can be regenerated" runs that config back through the target."""
    for spec in (SPEC_D3, SPEC_R4):
        ints = target_of("reference", spec)(cfg_of(spec), 55)
        floats = target_of("reference", spec)(
            cfg_of(spec, slack=float(SLACK), horizon=float(horizon_of(spec))), 55
        )
        assert episode_dict(ints) == episode_dict(floats)


def test_cfg7_a_call_never_mutates_its_cfg():
    spec = SPEC_D3
    for policy, cfg in (("reference", cfg_of(spec)), ("faulty", cfg_of(spec, plant_cell="depth_half"))):
        before = copy.deepcopy(cfg)
        target_of(policy, spec)(cfg, 404)
        assert cfg == before


# ===========================================================================
# the real runs: A2, A3, A5, A6 read what `proofload sweep` actually stored
# ===========================================================================


def policy_of(key: str) -> str:
    return "reference" if key == "unpaired" else key


def every_run() -> Iterable[tuple[str, ArmSpec, str, list[dict[str, Any]]]]:
    w = world()
    for (key, arm), run_id in sorted(w.runs.items()):
        yield policy_of(key), spec_by_id(arm), run_id, read_rows(w.store, run_id)


def assert_pairs(by_arm: dict[str, list[dict[str, Any]]]) -> None:
    """One cell, `REPLICATES` replicates, and at every `(config_hash, replicate_index)`: one
    seed and one `scenario_hash` across every arm, and one distinct `task_id` per arm."""
    keysets = [set(pairs_of(rows)) for rows in by_arm.values()]
    assert all(k == keysets[0] for k in keysets), "the arms ran different (cell, replicate) pairs"
    assert len(keysets[0]) == REPLICATES and len({k[0] for k in keysets[0]}) == 1
    tables = {arm: pairs_of(rows) for arm, rows in by_arm.items()}
    for key in sorted(keysets[0]):
        seen = {arm: table[key] for arm, table in tables.items()}
        assert len({r["seed"] for r in seen.values()}) == 1, key
        assert len({r["meta"]["scenario_hash"] for r in seen.values()}) == 1, key
        assert len({r["meta"]["task_id"] for r in seen.values()}) == len(seen), key


# ---------------------------------------------------------------------------
# A2 · pairing
# ---------------------------------------------------------------------------


def test_a2_1_every_depth_arm_pairs_on_seed_and_scenario():
    """A2: "For two arms of one knob, swept from the same file with the same salt, the
    episode at `(config_hash, replicate_index)` has equal `scenario_hash`."  All seven depth
    arms, both controls included, one of them reached through `--pair-with`.  Test: two
    scripted runs, with the stores compared."""
    assert_pairs({aid(s): rows_of("reference", s) for s in D_SPECS})


def test_a2_2_every_distractor_level_pairs_on_seed_and_scenario():
    """The same over **every** knob R level and both R controls, and not over one pair: this
    is the coverage gap filed against the task layer's build, whose tests contrasted `r0` with
    `r8` alone."""
    assert_pairs({aid(s): rows_of("reference", s) for s in R_SPECS})


def test_a2_3_the_equality_is_the_salts_and_not_a_constant():
    """The control for A2.1 and A2.2.  An adapter that ignored the seed would give every arm
    one scenario and pass them both.  Within a run the replicates carry distinct scenarios
    (G14, G15), and another salt moves every one of them."""
    w = world()
    base = pairs_of(rows_of("reference", D_SPECS[0]))
    other = pairs_of(read_rows(w.store, w.runs[("unpaired", aid(D_SPECS[0]))]))
    assert set(base) == set(other)
    assert len({r["meta"]["scenario_hash"] for r in base.values()}) == REPLICATES
    assert len({r["meta"]["task_id"] for r in base.values()}) == REPLICATES
    for key in base:
        assert base[key]["seed"] != other[key]["seed"]
        assert base[key]["meta"]["scenario_hash"] != other[key]["meta"]["scenario_hash"]


# ---------------------------------------------------------------------------
# A3 · arms outside cfg
# ---------------------------------------------------------------------------


def test_a3_1_meta_carries_the_arm_identity_on_every_episode():
    """A3: "`meta` carries [the level] on every episode."  Every stored row, every arm, both
    policies: the arm id, the knob, the level and the control flag are the target's own."""
    count = 0
    for policy, spec, _run_id, rows in every_run():
        for row in rows:
            assert row["error"] is None and row["outcome"] is not None, (aid(spec), row["error"])
            meta = row["meta"]
            assert meta["arm_id"] == aid(spec)
            assert meta["knob"] == spec.knob
            assert meta["level"] == spec.level
            assert meta["control"] == (spec.control is not None)
            assert meta["policy"] == policy
            count += 1
    assert count == 8 * (len(ALL_SPECS) + 1) + 2 * 2 * REPLICATES


def test_a3_3_the_recorded_task_is_the_generators_task_at_the_proofload_seed():
    """A3's third clause, and G12's "the task seed is the Proofload seed itself, with no
    remapping": the `task_id` an episode records is the one `generate(arm, seed)` gives for an
    arm spec built here and the seed the store holds.  `task_id` covers every other bundle
    field (the task layer's G1.4), so this is the whole bundle, and it is what makes two arms fed
    the same `(cfg, seed)` differ only in the fields N14 names."""
    for _policy, spec, _run_id, rows in every_run():
        for row in rows:
            bundle = bundle_of(spec, row["seed"])
            meta = row["meta"]
            assert meta["task_id"] == bundle.task_id, (aid(spec), row["seed"])
            assert meta["scenario_hash"] == bundle.scenario_hash
            assert meta["engine_hash"] == bundle.engine_hash
            assert meta["generator_hash"] == bundle.generator_hash


REQUIRED_META = {
    "arm_id": str, "knob": str, "level": int, "control": bool, "task_id": str,
    "scenario_hash": str, "pins": dict, "leaky_pass": bool, "strict_label": str,
    "sampled_calls": int, "engine_hash": str, "generator_hash": str, "policy": str,
}


def test_a3_4_meta_carries_every_field_2_5_names_that_a_scripted_episode_has():
    """The required `meta` list, less what only a model run has (input tokens, the verifiers trace
    id and path, the serving-pin hash).  `format_clause` is the singular clause `verify`
    reports: the task layer reports the lowest of "the clauses that fired"."""
    for _policy, _spec, _run_id, rows in every_run():
        for row in rows:
            meta = row["meta"]
            for key, kind in REQUIRED_META.items():
                assert isinstance(meta[key], kind), (key, meta.get(key))
                assert not (kind is int and isinstance(meta[key], bool)), key
            assert "format_clause" in meta
            assert meta["format_clause"] is None or isinstance(meta["format_clause"], int)


# ---------------------------------------------------------------------------
# A5 · time
# ---------------------------------------------------------------------------


def test_a5_1_every_stored_row_sits_inside_t_max_turns_horizon():
    """A5: `0 <= t <= max_turns(arm) <= horizon = H`, and `H` is one number for every arm of
    the knob (N17).  `max_turns` and `H` are computed here from N16 and N17 and not read from
    the build."""
    seen_horizons: dict[str, set[float]] = {"depth": set(), "distractor": set()}
    for _policy, spec, _run_id, rows in every_run():
        for row in rows:
            assert 0 <= row["t"] <= expected_max_turns(spec) <= row["horizon"], (aid(spec), row)
            assert row["horizon"] == horizon_of(spec)
            seen_horizons[spec.knob].add(row["horizon"])
    assert seen_horizons == {"depth": {float(H_D)}, "distractor": {float(H_R)}}


def test_a5_2_a_reference_episode_takes_its_reference_turns_and_passes():
    """One call per turn, plus the reply turn (N16): `d + 1` for a depth arm and its control
    (which follows its own `dL`), `d_R + 1` for every R arm."""
    for policy, spec, _run_id, rows in every_run():
        if policy != "reference":
            continue
        want = spec.level + 1 if spec.knob == "depth" else D_R + 1
        for row in rows:
            assert row["outcome"] == "passed", (aid(spec), row["seed"])
            assert row["t"] == want, (aid(spec), row["t"])
            # `reference` "executes the reference calls": all of them, and no others
            assert row["meta"]["sampled_calls"] == len(bundle_of(spec, row["seed"]).reference_calls) == want - 1


def test_a5_3_the_registered_slack_and_horizon_are_n16_and_n17_arithmetic():
    w = world()
    assert (w.d_registry.slack, w.d_registry.horizon) == (SLACK, H_D) == (SLACK, 13)
    assert (w.r_registry.slack, w.r_registry.horizon) == (SLACK, H_R) == (SLACK, 7)


# ---------------------------------------------------------------------------
# A6 · determinism of mapping
# ---------------------------------------------------------------------------


def test_a6_1_the_same_arm_cfg_and_seed_give_the_same_episode():
    for policy, plant in (("reference", None), ("faulty", "depth_half")):
        for spec in ALL_SPECS:
            cfg = cfg_of(spec) if plant is None else cfg_of(spec, plant_cell=plant)
            for seed in SPREAD[:4]:
                one = target_of(policy, spec)(cfg, seed)
                two = target_of(policy, spec)(dict(cfg), seed)
                assert episode_dict(one) == episode_dict(two), (policy, aid(spec), seed)


def test_a6_2_two_processes_and_two_hash_seeds_agree_byte_for_byte():
    """The dynamic half of A6, and the only place a `set` or `dict` order leaking into a
    recorded field would show: two fresh interpreters at `PYTHONHASHSEED` 0 and 1."""
    w = world()
    jobs = [
        (attr_of(p, aid(s)), 0 if s.knob == "depth" else 1, dict(cfg_of(s, plant_cell="depth_half")), seed)
        for s in (D_SPECS[2], D_SPECS[5], R_SPECS[1], R_SPECS[4], R_SPECS[5])
        for p in ("reference", "faulty")
        for seed in (404, 2**32 - 1)
    ]
    script = (
        "import json, sys\n"
        "from poisson_tasks.adapter import load_registry\n"
        "a = json.loads(sys.argv[1])\n"
        "regs = [load_registry(a['paths'][i], sha256=a['shas'][i], sealed=a['sealed']) for i in (0, 1)]\n"
        "out = [regs[k].targets[attr](cfg, seed).to_dict() for attr, k, cfg, seed in a['jobs']]\n"
        "print(json.dumps(out, sort_keys=True))\n"
    )
    args = json.dumps({
        "paths": [str(w.d_reg), str(w.r_reg)], "shas": [w.d_sha, w.r_sha], "sealed": str(w.sealed), "jobs": jobs,
    })
    outputs = []
    for hash_seed in ("0", "1"):
        done = subprocess.run(
            [sys.executable, "-c", script, args], env=child_env(None, PYTHONHASHSEED=hash_seed),
            capture_output=True, text=True, timeout=300,
        )
        assert done.returncode == 0, done.stderr
        outputs.append(done.stdout)
    assert outputs[0] == outputs[1]
    here = json.dumps(
        [target_of_registry(w, k, attr)(cfg, seed).to_dict() for attr, k, cfg, seed in jobs], sort_keys=True
    )
    assert json_norm(json.loads(outputs[0])) == json_norm(json.loads(here))


def target_of_registry(w: World, index: int, attr: str) -> Any:
    return (w.d_registry, w.r_registry)[index].targets[attr]


def test_a6_3_any_stored_episode_can_be_regenerated_from_its_row():
    """A6: "the same `(arm, cfg, seed)` gives the same `task_id`, recorded, so any episode
    can be regenerated."  `inspect` prints a row's config (every number a float) and seed;
    calling the target with those reproduces the stored outcome, time, horizon and `meta`
    exactly, for every row of every run."""
    for policy, spec, _run_id, rows in every_run():
        for row in rows:
            again = target_of(policy, spec)(row["config"], row["seed"])
            stored = {
                "outcome": row["outcome"], "t": row["t"], "horizon": row["horizon"],
                "confidence": None, "meta": row["meta"],
            }
            assert episode_dict(again) == stored, (policy, aid(spec), row["seed"])


# ===========================================================================
# the outcome map: A4, A5's guards, A8 and A9, driven with hand-built runs
# ===========================================================================

ADAPTERS_LABELS = ("replay_mismatch", "api_error", "wall_timeout")
INSTRUMENT_LABELS = ("verifier_error", *ADAPTERS_LABELS)
SPEC_IDS = spec_ids(ALL_SPECS)


def flip(observation: str) -> str:
    """One character changed: the last one, made another hex digit."""
    return observation[:-1] + ("1" if observation[-1] != "1" else "2")


def grid(spec: ArmSpec, seeds: Iterable[int] = (404, 2121)) -> Iterable[tuple[Any, str, Any]]:
    for seed in seeds:
        bundle = bundle_of(spec, seed)
        for control, (calls, reply, limit) in controls_of(bundle).items():
            yield bundle, control, make_run(bundle, calls, reply=reply, turn_limit=limit)


# ---------------------------------------------------------------------------
# A9 · one outcome path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_a9_1_every_shape_the_bundle_can_express_gets_the_verifiers_label(spec):
    """A9: scripted and model targets share the verdict -> Episode path, so the map's label is
    `verify`'s label under the arm's strictness, for `passed`, every negative control and
    both `t` and `meta`.  Over every level of both knobs and both controls of each."""
    for bundle, control, run in grid(spec):
        episode = episode_of(spec, bundle, run)
        verdict = verify(bundle, run.turns, run.ended_with_reply, run.turn_limit_hit, run.fmt)
        assert episode.outcome == verdict.label == system_label(control), (aid(spec), control)
        assert episode.t == len(run.turns) and episode.horizon == horizon_of(spec)
        meta = episode.meta
        assert meta["strict_label"] == verdict.strict_label
        assert meta["leaky_pass"] == verdict.leaky_pass
        assert meta["format_clause"] == verdict.format_clause
        assert meta["sampled_calls"] == sum(len(turn.calls) for turn in run.turns)


def test_a9_2_both_scripted_targets_reach_the_outcome_map_through_the_module_global(monkeypatch):
    """A9's seam, named like the task layer's `_check_pins`: the scripted targets look
    `to_episode` up in the module at call time.  A target that built its own Episode, or that
    captured the function when the registry was built, would leave the model path a second
    outcome path."""
    from proofload import Episode

    mod, spec = adapter(), SPEC_D3
    real, sentinel, seen = mod.to_episode, Episode(outcome="passed", t=1, horizon=13), []

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(inspect.signature(real).bind(*args, **kwargs).arguments)
        return sentinel

    monkeypatch.setattr(mod, "to_episode", spy)
    for policy, cfg in (("reference", cfg_of(spec)), ("faulty", cfg_of(spec, plant_cell="clean"))):
        assert target_of(policy, spec)(cfg, 404) is sentinel
    assert len(seen) == 2
    for args in seen:
        assert args["arm"] == spec and args["slack"] == SLACK and args["horizon"] == H_D
        assert args["bundle"].task_id == bundle_of(spec, 404).task_id


def test_a9_3_the_targets_episode_is_the_maps_pure_function_of_what_it_was_handed(monkeypatch):
    mod = adapter()
    real, seen = mod.to_episode, []

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(inspect.signature(real).bind(*args, **kwargs).arguments)
        return real(*args, **kwargs)

    monkeypatch.setattr(mod, "to_episode", spy)
    for spec in (SPEC_D3, SPEC_R4, D_SPECS[5]):
        got = target_of("reference", spec)(cfg_of(spec), 2121)
        again = real(**seen[-1])
        assert episode_dict(got) == episode_dict(again)


@pytest.mark.parametrize("control", ["overshoot", "collateral_mutation"])
def test_a9_4_the_arms_strictness_decides_the_label_and_both_predicates_are_recorded(control):
    """The rule: "`outcome` = the verdict label under the arm's strictness", with the leaky verdict
    in `meta` (PG-5).  The same episode is `overshoot` or `collateral_mutation` under a strict
    arm and `passed` under a leaky one, and both record `leaky_pass` and the strict label."""
    strict, leaky = spec_of("depth", 3), spec_of("depth", 3, strictness="leaky")
    results = {}
    for spec in (strict, leaky):
        bundle = bundle_of(spec, 404)
        run = make_run(bundle, bundle.negative_controls[control])
        results[spec.strictness] = episode_of(spec, bundle, run, horizon=H_D)
    assert results["strict"].outcome == control
    assert results["leaky"].outcome == "passed"
    for episode in results.values():
        assert episode.meta["strict_label"] == control and episode.meta["leaky_pass"] is True


def test_a9_5_the_runs_format_spec_is_what_the_verifier_reads_its_markers_from():
    """Format clause 1: "The content carries `fmt`'s call markers, but the turn has no parsed
    call."  `fmt` is part of the serving pin and rides the run, so the same content is a
    `malformed_call` under the family whose markers it carries and not under one that has
    none.  A map that used a format spec of its own would pass every other test in this file."""
    spec = SPEC_D3
    bundle = bundle_of(spec, 404)
    good = make_run(bundle, bundle.reference_calls)
    marked = Turn(content="<tool_call>{}", calls=(), finish_reason="stop")
    body = dataclasses.replace(good, turns=(*good.turns[:-1], marked, good.turns[-1]))
    qwen = FormatSpec(name="qwen3_coder", markers=("<tool_call>", "<function="))
    under_qwen = episode_of(spec, bundle, dataclasses.replace(body, fmt=qwen))
    under_direct = episode_of(spec, bundle, dataclasses.replace(body, fmt=DIRECT))
    # a marker in a turn that made no call is a format failure, but the episode still reached
    # its goal: the task layer decides pass before format, so it is `passed`, clause named
    assert under_qwen.meta["format_clause"] == 1 and under_direct.meta["format_clause"] is None
    assert under_qwen.outcome == under_direct.outcome == "passed"


# ---------------------------------------------------------------------------
# A4 · instrument never becomes system
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_a4_1_an_instrument_signal_decides_the_label_whatever_the_state_says(spec):
    """A4: a dead server, a server error or a malformed response must produce `api_error`, and
    a wall-clock expiry `wall_timeout`.  On the scripted path there is no server to kill, so
    the fault is injected where the label is assigned, and it is injected against every state
    an episode can be in: a perfect one, every system failure, an unfinished one and an empty
    one.  Whatever state the trace shows, the label is the instrument's, and `leaky_pass`
    is never true on an episode the instrument ended."""
    bundle = bundle_of(spec, 404)
    for signal in ("api_error", "wall_timeout"):
        for control, (calls, reply, limit) in controls_of(bundle).items():
            run = make_run(bundle, calls, reply=reply, turn_limit=limit, instrument=signal)
            episode = episode_of(spec, bundle, run)
            assert episode.outcome == signal, (aid(spec), control, signal)
            assert episode.meta["leaky_pass"] is False
            assert episode.meta["strict_label"] == signal
            assert episode.t == len(run.turns)
        for calls in (bundle.reference_calls[:1], ()):
            run = make_run(bundle, calls, reply=False, instrument=signal)
            episode = episode_of(spec, bundle, run)
            assert episode.outcome == signal and episode.t == len(calls)


def test_a4_2_a_leaky_arm_never_passes_an_episode_the_instrument_ended():
    """The one place the leaky rule could swallow an instrument label: under a leaky arm any
    episode leaky accepts and that has no instrument label is `passed`.  Here it has one."""
    spec = spec_of("depth", 3, strictness="leaky")
    bundle = bundle_of(spec, 404)
    for signal in ("api_error", "wall_timeout"):
        run = make_run(bundle, bundle.reference_calls, instrument=signal)
        episode = episode_of(spec, bundle, run, horizon=H_D)
        assert episode.outcome == signal and episode.meta["leaky_pass"] is False


def test_a4_3_the_adapter_never_assigns_an_instrument_label_of_its_own_accord():
    """"Every label-assignment site is tested, not only the declared set" (`defining-outcomes.md`,
    checklist item 3).  With no signal and a faithful trace, the sites the adapter owns — the
    replay check, the two instrument signals, the exception guard — never fire, over every
    arm and every shape; and the six system labels `verify` assigns are all reached."""
    reached: set[str] = set()
    for spec in ALL_SPECS:
        for bundle, control, run in grid(spec, seeds=(404,)):
            outcome = episode_of(spec, bundle, run).outcome
            assert outcome in OUTCOMES
            assert outcome not in INSTRUMENT_LABELS, (aid(spec), control, outcome)
            reached.add(outcome)
    assert reached == {"passed", "wrong_state", "overshoot", "collateral_mutation", "turn_limit", "malformed_call"}


def test_a4_4_replay_mismatch_precedes_the_two_instrument_signals():
    """The outcome table: "The first label that matches wins", and `replay_mismatch` is
    listed above `api_error` and `wall_timeout`."""
    spec = SPEC_D3
    bundle = bundle_of(spec, 404)
    good = make_run(bundle, bundle.reference_calls)
    messages = (flip(good.tool_messages[0]), *good.tool_messages[1:])
    for signal in ("api_error", "wall_timeout"):
        bad = dataclasses.replace(good, tool_messages=messages, instrument=signal)
        assert episode_of(spec, bundle, bad).outcome == "replay_mismatch"




def test_a4_5_an_instrument_signal_outside_the_closed_vocabulary_is_refused():
    """The vocabulary is closed at ten, and an unlisted label stored under `outcome` would be
    a new instrument label nobody declared."""
    spec = SPEC_D3
    bundle = bundle_of(spec, 404)
    run = make_run(bundle, bundle.reference_calls, instrument="crashed")
    with pytest.raises(ValueError, match="crashed"):
        episode_of(spec, bundle, run)


@pytest.mark.parametrize("strictness", ["strict", "leaky"])
@pytest.mark.parametrize("bad_call", [5, ("only_a_name",)], ids=["not_a_tuple", "one_element"])
def test_a4_6_an_exception_inside_the_adapters_verification_is_verifier_error(strictness, bad_call):
    """G10 at the adapter's own sites: "there is no default-to-pass path".  A structurally
    invalid call makes the replay check and the verdict raise; the episode is
    `verifier_error`, an instrument label, under either strictness — it neither raises
    out of the map nor becomes a system label or `passed`."""
    spec = spec_of("depth", 3, strictness=strictness)
    bundle = bundle_of(spec, 404)
    good = make_run(bundle, bundle.reference_calls)
    broken = Turn(content="", calls=(bad_call,), finish_reason="tool_calls")
    run = dataclasses.replace(good, turns=(broken, *good.turns), tool_messages=("x", *good.tool_messages))
    episode = episode_of(spec, bundle, run, horizon=H_D)
    assert episode.outcome == "verifier_error"
    assert episode.meta["leaky_pass"] is False and episode.meta["strict_label"] == "verifier_error"


@pytest.mark.parametrize("spec", [SPEC_D3, SPEC_R4, D_SPECS[5]], ids=lambda s: aid(s))
def test_a4_7_an_unfinished_episode_with_no_signal_is_not_guessed_to_be_an_instrument_failure(spec):
    """An episode that neither replied nor hit the turn limit fits no system label, and the
    adapter must not infer `api_error` or `wall_timeout` from that: only the harness knows
    *why* a run stopped.  The task layer's OV4 makes it `verifier_error`, and so it stays, on both a
    short run and one that used every turn it had."""
    bundle = bundle_of(spec, 404)
    limit = expected_max_turns(spec)
    for calls in (bundle.reference_calls, [bundle.reference_calls[0]] * limit):
        run = make_run(bundle, calls, reply=False, turn_limit=False)
        outcome = episode_of(spec, bundle, run).outcome
        assert outcome == "verifier_error", (aid(spec), len(calls), outcome)


# ---------------------------------------------------------------------------
# A8 · replay check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_a8_1_one_changed_character_in_any_tool_message_is_a_replay_mismatch(spec):
    """A8: replay's observations equal the trace's tool messages "byte for byte", "otherwise the
    outcome is `replay_mismatch`."  The untouched run is the control (`passed`, and never a
    mismatch); the first, a middle and the last message are each altered in turn, since a
    check of one position would pass a test of another."""
    bundle = bundle_of(spec, 404)
    run = make_run(bundle, bundle.reference_calls)
    assert episode_of(spec, bundle, run).outcome == "passed"
    count = len(run.tool_messages)
    for index in sorted({0, count // 2, count - 1}):
        messages = list(run.tool_messages)
        messages[index] = flip(messages[index])
        episode = episode_of(spec, bundle, dataclasses.replace(run, tool_messages=tuple(messages)))
        assert episode.outcome == "replay_mismatch", (aid(spec), index)
        assert episode.meta["leaky_pass"] is False and episode.meta["strict_label"] == "replay_mismatch"


@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_a8_2_a_message_dropped_added_or_reordered_is_a_replay_mismatch(spec):
    bundle = bundle_of(spec, 404)
    run = make_run(bundle, bundle.reference_calls)
    messages = run.tool_messages
    variants = {
        "drop_last": messages[:-1],
        "drop_first": messages[1:],
        "extra": (*messages, messages[-1]),
    }
    if len(messages) > 1:
        variants["swap"] = (messages[1], messages[0], *messages[2:])
    for name, changed in variants.items():
        episode = episode_of(spec, bundle, dataclasses.replace(run, tool_messages=changed))
        assert episode.outcome == "replay_mismatch", (aid(spec), name)


@pytest.mark.parametrize(
    "edit",
    [
        lambda s: s + " ",
        lambda s: " " + s,
        lambda s: s.replace(" ", "\t", 1),
        lambda s: s.replace("ok", "OK", 1),
        lambda s: s.replace("o", "о", 1),  # a Cyrillic lookalike
        lambda s: s + "\n",
    ],
    ids=["trailing_space", "leading_space", "tab", "upper_case", "homoglyph", "newline"],
)
def test_a8_3_byte_for_byte_means_no_normalisation(edit):
    """Whitespace, case and a lookalike character all differ as bytes.  A check that stripped,
    folded or normalised before comparing would let each of them through."""
    spec = SPEC_D3
    bundle = bundle_of(spec, 404)
    run = make_run(bundle, bundle.reference_calls)
    changed = (edit(run.tool_messages[0]), *run.tool_messages[1:])
    assert changed != run.tool_messages
    episode = episode_of(spec, bundle, dataclasses.replace(run, tool_messages=changed))
    assert episode.outcome == "replay_mismatch"


@pytest.mark.parametrize("spec", [s for s in D_SPECS if s.control is not None], ids=lambda s: aid(s))
def test_a8_4_a_control_episode_numbers_its_observations_from_the_arms_seq_start(spec):
    """The D control seeds `1 ... (H - dL)`, after which the live server starts at `seq_start =
    H - dL + 1`, so its genuine observations are numbered from there.  A trace
    numbered from 1 — the plain arm's — is not the control's and must not replay clean; the
    control's own is a `passed` (A8.1's control), so a replay run from `seq_start = 1` would
    have flagged every genuine control episode instead."""
    bundle = bundle_of(spec, 404)
    plain = bundle_of(spec_of("depth", spec.level), 404)
    assert bundle.seq_start > 1 and plain.seq_start == 1
    assert bundle.reference_calls == plain.reference_calls
    numbered_from_one = make_run(plain, plain.reference_calls).tool_messages
    run = dataclasses.replace(make_run(bundle, bundle.reference_calls), tool_messages=numbered_from_one)
    assert episode_of(spec, bundle, run).outcome == "replay_mismatch"


def test_a8_5_a_replay_mismatch_outranks_the_verdict_under_either_strictness():
    for strictness in ("strict", "leaky"):
        spec = spec_of("depth", 3, strictness=strictness)
        bundle = bundle_of(spec, 404)
        run = make_run(bundle, bundle.reference_calls)
        bad = dataclasses.replace(run, tool_messages=(flip(run.tool_messages[0]), *run.tool_messages[1:]))
        assert episode_of(spec, bundle, run, horizon=H_D).outcome == "passed"
        assert episode_of(spec, bundle, bad, horizon=H_D).outcome == "replay_mismatch"




@HYP
@given(
    spec=st.sampled_from(ALL_SPECS),
    seed=st.sampled_from(SPREAD),
    where=st.integers(min_value=0, max_value=10**6),
    char=st.characters(min_codepoint=32, max_codepoint=126),
)
def test_a8_6_any_single_character_change_to_any_message_is_detected(spec, seed, where, char):
    bundle = bundle_of(spec, seed)
    run = make_run(bundle, bundle.reference_calls)
    index = where % len(run.tool_messages)
    message = run.tool_messages[index]
    position = (where // 7) % len(message)
    if message[position] == char:
        return
    changed = message[:position] + char + message[position + 1 :]
    messages = list(run.tool_messages)
    messages[index] = changed
    episode = episode_of(spec, bundle, dataclasses.replace(run, tool_messages=tuple(messages)))
    assert episode.outcome == "replay_mismatch"


def test_a8_7_the_replay_is_of_the_calls_actually_made_and_not_of_the_reference():
    """E8: "`replay` reproduces the live toolset's observations byte for byte" for *any* call
    sequence.  A check that compared tool messages with the bundle's `reference_observations`
    would call every non-reference episode a mismatch: a wrong-state episode is `wrong_state`."""
    spec = SPEC_D3
    bundle = bundle_of(spec, 404)
    run = make_run(bundle, bundle.negative_controls["wrong_state"])
    assert tuple(run.tool_messages) != tuple(bundle.reference_observations)
    assert episode_of(spec, bundle, run).outcome == "wrong_state"


@pytest.mark.parametrize(
    "control",
    ["wrong_state", "overshoot", "collateral_mutation", "malformed_call_clause_2", "malformed_call_clause_3",
     "malformed_call_clause_4", "turn_limit"],
)
def test_a8_8_a_replay_mismatch_outranks_every_system_label_too(control):
    """The outcome table: "The first label that matches wins", and `replay_mismatch` is
    listed above all six system labels.  A trace that failed *and* does not replay is a
    mismatch: a check that ran only on episodes that would otherwise pass would let every
    failure hide one."""
    spec = SPEC_D3
    bundle = bundle_of(spec, 404)
    calls, reply, limit = controls_of(bundle)[control]
    run = make_run(bundle, calls, reply=reply, turn_limit=limit)
    assert episode_of(spec, bundle, run).outcome == system_label(control)
    bad = dataclasses.replace(run, tool_messages=(flip(run.tool_messages[0]), *run.tool_messages[1:]))
    assert episode_of(spec, bundle, bad).outcome == "replay_mismatch"


# ---------------------------------------------------------------------------
# to_episode: what it records, and what it will not accept
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", [SPEC_D3, D_SPECS[5], SPEC_R4, R_SPECS[5]], ids=lambda s: aid(s))
def test_map1_meta_is_the_bundles_identity_and_the_verdicts_predicates(spec):
    from proofload import Episode

    bundle = bundle_of(spec, 2121)
    run = make_run(bundle, bundle.reference_calls)
    episode = episode_of(spec, bundle, run)
    assert isinstance(episode, Episode)
    verdict = verify(bundle, run.turns, run.ended_with_reply, run.turn_limit_hit, run.fmt)
    meta = json_norm(dict(episode.meta))
    expected = {
        "arm_id": aid(spec), "knob": spec.knob, "level": spec.level, "control": spec.control is not None,
        "task_id": bundle.task_id, "scenario_hash": bundle.scenario_hash,
        "engine_hash": bundle.engine_hash, "generator_hash": bundle.generator_hash,
        "pins": json_norm(dataclasses.asdict(bundle.pins)), "strict_label": verdict.strict_label,
        "leaky_pass": verdict.leaky_pass, "format_clause": verdict.format_clause,
        "sampled_calls": len(bundle.reference_calls),
    }
    assert {k: meta[k] for k in expected} == expected
    assert episode.t == len(bundle.reference_calls) + 1 and episode.horizon == horizon_of(spec)


def test_map2_a_caller_meta_is_merged_and_does_not_displace_the_required_keys():
    spec = SPEC_D3
    bundle = bundle_of(spec, 404)
    run = make_run(bundle, bundle.reference_calls)
    plain = adapter().to_episode(spec, bundle, run, slack=SLACK, horizon=H_D)
    extra = adapter().to_episode(spec, bundle, run, slack=SLACK, horizon=H_D, meta={"policy": "reference", "note": 7})
    assert extra.meta["policy"] == "reference" and extra.meta["note"] == 7
    assert {k: v for k, v in dict(extra.meta).items() if k not in ("policy", "note")} == dict(plain.meta)


def test_map3_an_arm_that_is_not_the_bundles_arm_is_refused():
    """A level mix-up between a target and its bundle would record one arm's episode under
    another's `max_turns`."""
    bundle = bundle_of(SPEC_D3, 404)
    run = make_run(bundle, bundle.reference_calls)
    with pytest.raises(ValueError, match=re.escape(aid(SPEC_D3))):
        adapter().to_episode(spec_of("depth", 5), bundle, run, slack=SLACK, horizon=H_D)


@pytest.mark.parametrize("spec", [SPEC_D3, SPEC_R4], ids=lambda s: aid(s))
def test_a5_7_a_trace_longer_than_max_turns_or_a_horizon_below_it_is_refused(spec):
    """A5: `0 <= t <= max_turns(arm) <= horizon`.  The map refuses to store an episode that
    breaks it, and the boundary itself is accepted: `t == max_turns` (an episode that hit
    its turn limit) and `horizon == max_turns` are both inside the invariant."""
    bundle = bundle_of(spec, 404)
    limit = expected_max_turns(spec)
    call = bundle.reference_calls[0]
    at_limit = make_run(bundle, [call] * limit, reply=False, turn_limit=True)
    over = make_run(bundle, [call] * (limit + 1), reply=False, turn_limit=True)
    episode = episode_of(spec, bundle, at_limit)
    assert episode.t == limit and episode.outcome == "turn_limit"
    with pytest.raises(ValueError, match="turns"):
        episode_of(spec, bundle, over)
    run = make_run(bundle, bundle.reference_calls)
    assert episode_of(spec, bundle, run, horizon=limit).horizon == limit
    with pytest.raises(ValueError, match="horizon"):
        episode_of(spec, bundle, run, horizon=limit - 1)


def test_a5_8_t_is_the_number_of_turns_and_not_the_number_of_calls():
    """`t = Trace.num_turns`: a reply is a turn that makes no call, so a reference
    episode of `d` calls takes `d + 1`, and the wrong-state control (one call fewer, then a
    reply) takes `d`."""
    for spec in (SPEC_D3, SPEC_R4):
        bundle = bundle_of(spec, 404)
        d = len(bundle.reference_calls)
        assert episode_of(spec, bundle, make_run(bundle, bundle.reference_calls)).t == d + 1
        wrong = make_run(bundle, bundle.negative_controls["wrong_state"])
        assert episode_of(spec, bundle, wrong).t == d


# ===========================================================================
# A7 · the pre-registration lock
# ===========================================================================

PILOT = (spec_of("depth", 1), spec_of("depth", 3), spec_of("depth", 8), spec_of("depth", 1, 8))
PILOT_ATTRS = [
    "faulty_depth_d1", "faulty_depth_d1_h8", "faulty_depth_d3", "faulty_depth_d8",
    "reference_depth_d1", "reference_depth_d1_h8", "reference_depth_d3", "reference_depth_d8",
]


def pilot_files(tmp_path: Path) -> tuple[Path, str, Path]:
    reg, sealed = tmp_path / "prereg.toml", tmp_path / "sealed.toml"
    reg.write_text(toml_text(reg_doc("depth", PILOT)))
    sealed.write_text(sealed_text({"clean": {}, "planted": {"step_fail_rate": 1.0}}))
    return reg, sha_of(reg), sealed


def import_module_from(directory: Path, name: str) -> Any:
    sys.path.insert(0, str(directory))
    importlib.invalidate_caches()
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(directory))
        sys.modules.pop(name, None)


def write_registry(directory: Path, name: str, reg: Path, sha: str, sealed: Path | None = None) -> None:
    (directory / f"{name}.py").write_text(registry_module_text(reg, sha, sealed))


def test_a7_1_a_registry_whose_compiled_hash_matches_imports_and_its_targets_run(tmp_path):
    reg, sha, sealed = pilot_files(tmp_path)
    write_registry(tmp_path, "lock_ok", reg, sha, sealed)
    module = import_module_from(tmp_path, "lock_ok")
    episode = module.reference_depth_d3(cfg_of(spec_of("depth", 3)), 404)
    assert episode.outcome == "passed" and episode.meta["arm_id"] == "depth:d3"


def test_a7_2_a_hash_that_disagrees_with_the_file_raises_at_import_naming_both(tmp_path):
    """A7: "Importing an arm target whose registry hash disagrees with the pre-registration
    file raises at import."  The `import` statement is the whole test: nothing is called,
    and the error names the hash the file has and the hash the module was compiled with, so
    an operator can tell a stale registry from an edited file.  A `RuntimeError` is one of the
    four types `proofload sweep` turns into a refusal to resolve the target."""
    reg, sha, sealed = pilot_files(tmp_path)
    wrong = "0" * 64
    write_registry(tmp_path, "lock_bad", reg, wrong, sealed)
    with pytest.raises(RuntimeError) as info:
        import_module_from(tmp_path, "lock_bad")
    assert wrong in str(info.value) and sha in str(info.value)


@pytest.mark.parametrize(
    "edit",
    [
        lambda text: text + "# a comment\n",
        lambda text: text + "\n",
        lambda text: "\n".join([*text.split("\n")[1::-1], *text.split("\n")[2:]]),
    ],
    ids=["comment", "trailing_newline", "reordered_keys"],
)
def test_a7_3_the_hash_is_over_the_files_bytes_so_any_edit_after_freezing_raises(tmp_path, edit):
    """An edit that leaves the *parsed* registration identical — a comment, a newline, two
    keys swapped — changes the bytes, and the frozen document is the bytes.  A lock over
    parsed content would let all three through."""
    reg, sha, sealed = pilot_files(tmp_path)
    write_registry(tmp_path, "lock_edit", reg, sha, sealed)
    original = reg.read_text()
    edited = edit(original)
    assert edited != original and tomllib.loads(edited) == tomllib.loads(original)
    reg.write_text(edited)
    with pytest.raises(RuntimeError):
        import_module_from(tmp_path, "lock_edit")


def test_a7_4_a_registry_that_was_loaded_once_is_checked_again_on_the_next_load(tmp_path):
    """No cache between loads (A12): a file edited between two loads with the same compiled
    hash must fail the second, or the lock would hold only for a process's first import."""
    reg, sha, _ = pilot_files(tmp_path)
    first = adapter().load_registry(reg, sha256=sha)
    reg.write_text(reg.read_text() + "# edited after the first load\n")
    with pytest.raises(RuntimeError):
        adapter().load_registry(reg, sha256=sha)
    assert first is not None






def test_a7_5_the_refusal_surfaces_as_a_target_resolution_failure_before_any_episode(tmp_path):
    """"That surfaces as target resolution failure, before any episode."  Through the real
    CLI: a registry that raises at import is `cannot resolve --target`, exit 2, and nothing is
    stored — while the same command against the good registry runs (the control, without
    which a refusal of everything would pass)."""
    reg, sha, sealed = pilot_files(tmp_path)
    write_registry(tmp_path, "lock_good", reg, sha, sealed)
    write_registry(tmp_path, "lock_stale", reg, "f" * 64, sealed)
    sweep_file = tmp_path / "sweep.toml"
    sweep_file.write_text(sweep_text(H_D))
    store = tmp_path / "store"
    args = ["sweep", str(sweep_file), "--salt", SALT, "--max-mde", MAX_MDE, "--yes"]
    bad = cli(store, *args, "--target", "lock_stale:reference_depth_d1", mods=tmp_path)
    assert bad.returncode == 2
    assert "cannot resolve --target" in bad.stdout + bad.stderr
    assert not store.exists() or not [p for p in store.iterdir() if p.is_dir()]
    good = cli(store, *args, "--target", "lock_good:reference_depth_d1", mods=tmp_path)
    assert good.returncode == 0, good.stderr
    assert len([p for p in store.iterdir() if p.is_dir()]) == 1


def test_a7_6_an_arm_that_was_not_pre_registered_has_no_target(tmp_path):
    reg, sha, sealed = pilot_files(tmp_path)
    write_registry(tmp_path, "lock_arms", reg, sha, sealed)
    module = import_module_from(tmp_path, "lock_arms")
    for name in ("reference_depth_d4", "reference_depth_d2", "faulty_depth_d5", "reference_distractor_r0_k16"):
        assert not hasattr(module, name), name
    with pytest.raises(AttributeError):
        module.reference_depth_d4  # noqa: B018


def test_a7_7_the_registered_names_are_the_policy_then_the_arm_id_with_runs_of_punctuation_as_underscores(tmp_path):
    """Pinned by literals and not by `attr_of`, so the rule is stated in two places that
    must agree: an arm id holds `:`, `+`, `(`, `)` and `@`, none of which `--target
    module:attr` can carry, so a target's attribute is the policy, then the id with every run
    of non-alphanumerics made one underscore."""
    reg, sha, sealed = pilot_files(tmp_path)
    registry = adapter().load_registry(reg, sha256=sha, sealed=sealed)
    assert sorted(registry.targets) == PILOT_ATTRS
    w = world()
    for name in (
        "reference_distractor_r0_k16", "reference_distractor_r14_k16", "faulty_distractor_r2_k16",
        "reference_distractor_r0_len_r8_k16", "faulty_distractor_r2_len_r14_k16",
    ):
        assert name in w.r_registry.targets, name
    assert len(w.r_registry.targets) == 2 * len(R_SPECS) and len(w.d_registry.targets) == 2 * len(D_SPECS)


def test_a7_8_the_faulty_targets_exist_only_when_a_sealed_file_is_given(tmp_path):
    reg, sha, sealed = pilot_files(tmp_path)
    without = adapter().load_registry(reg, sha256=sha)
    assert sorted(without.targets) == [n for n in PILOT_ATTRS if n.startswith("reference")]
    assert sorted(adapter().load_registry(reg, sha256=sha, sealed=sealed).targets) == PILOT_ATTRS


def test_a7_9_the_registry_carries_the_registrations_arms_slack_and_horizon(tmp_path):
    reg, sha, _ = pilot_files(tmp_path)
    registry = adapter().load_registry(reg, sha256=sha)
    assert registry.arms == PILOT and (registry.slack, registry.horizon) == (SLACK, 13)


def test_a7_10_a_registration_that_fails_validation_raises_at_load_even_with_the_right_hash(tmp_path):
    """The validator is wired in: N18's predicate is worth nothing if `load_registry` never
    calls it.  The hash here is the file's own, so only the revision is wrong."""
    doc = reg_doc("depth", PILOT)
    doc["models"][0]["model"] = "Qwen/Qwen3.5-9B@main"
    reg = tmp_path / "bad.toml"
    reg.write_text(toml_text(doc))
    with pytest.raises(ValueError, match="(?i)revision"):
        adapter().load_registry(reg, sha256=sha_of(reg))
    write_registry(tmp_path, "lock_invalid", reg, sha_of(reg))
    with pytest.raises(ValueError, match="(?i)revision"):
        import_module_from(tmp_path, "lock_invalid")


@pytest.mark.parametrize("where", ["first", "last", "middle"])
def test_a7_11_a_compiled_hash_that_differs_in_one_character_is_refused(tmp_path, where):
    """The comparison is over the whole digest.  A check of a prefix, or of a length, would
    accept a hash that is right everywhere but one place, and `0` * 64 (the other tests'
    wrong hash) differs from any real digest at the start and would never show it."""
    reg, sha, sealed = pilot_files(tmp_path)
    index = {"first": 0, "last": 63, "middle": 31}[where]
    other = "1" if sha[index] != "1" else "2"
    near = sha[:index] + other + sha[index + 1 :]
    assert near != sha and len(near) == 64
    write_registry(tmp_path, "lock_near", reg, near, sealed)
    with pytest.raises(RuntimeError):
        import_module_from(tmp_path, "lock_near")


def test_h1_the_registration_writer_round_trips_through_tomllib():
    """Green before and after: the writer every registry test relies on.  A
    writer that rendered a document wrongly would turn a registry test's failure into a
    question about the writer."""
    for doc in (reg_doc("depth", D_SPECS), reg_doc("distractor", R_SPECS), reg_doc("depth", PILOT, models=())):
        assert tomllib.loads(toml_text(doc)) == doc
    cells = {"a": {"step_fail_rate": 0.5}, "b": {}}
    assert tomllib.loads(sealed_text(cells)) == {"cells": cells}


# ===========================================================================
# A12 · self-contained calls
# ===========================================================================


def battery() -> list[tuple[str, ArmSpec, dict[str, Any], int]]:
    items = [
        ("reference", spec, cfg_of(spec), seed) for spec in ALL_SPECS for seed in (0, 404, 2**32 - 1)
    ]
    for spec in (D_SPECS[0], D_SPECS[2], D_SPECS[5], R_SPECS[1], R_SPECS[5]):
        for cell in ("depth_half", "history_full", "overshoot_full"):
            items.extend(("faulty", spec, cfg_of(spec, plant_cell=cell), seed) for seed in (7, 404))
    return items


def run_battery(items: list[tuple[str, ArmSpec, dict[str, Any], int]], *, refuse_between: bool = False) -> list[Any]:
    out = []
    for policy, spec, cfg, seed in items:
        if refuse_between:
            broken = {k: v for k, v in cfg.items() if k != "slack"}
            with pytest.raises(ValueError):
                target_of(policy, spec)(broken, seed)
        out.append(episode_dict(target_of(policy, spec)(dict(cfg), seed)))
    return out


def test_a12_1_no_call_depends_on_the_calls_before_it():
    """A12: "No module-level mutable state is shared across calls."  A counter, a cache keyed
    on too little or a leaked engine state would make a result depend on what ran before it.
    The same battery of 72 calls runs in three orders — as listed, reversed, and shuffled — and
    with a *refused* call between every pair, and every result is the same each time."""
    import random

    items = battery()
    forward = run_battery(items)
    assert run_battery(list(reversed(items)))[::-1] == forward
    order = list(range(len(items)))
    random.Random(5).shuffle(order)
    shuffled = run_battery([items[i] for i in order])
    assert [shuffled[order.index(i)] for i in range(len(items))] == forward
    assert run_battery(items, refuse_between=True) == forward


def test_a12_2_a_call_from_inside_a_running_event_loop_is_refused():
    """A12: "The adapter refuses to be called from inside a running event loop."  Both
    policies; the model path runs its own loop per call, and nesting one in another is how a
    harness deadlocks."""
    for policy, cfg in (("reference", cfg_of(SPEC_D3)), ("faulty", cfg_of(SPEC_D3, plant_cell="clean"))):
        target = target_of(policy, SPEC_D3)

        async def inside(target: Any = target, cfg: dict[str, Any] = cfg) -> Any:
            return target(cfg, 404)

        with pytest.raises(RuntimeError, match="(?i)loop"):
            asyncio.run(inside())


def test_a12_3_a_refused_call_poisons_nothing_and_the_target_still_works_outside_a_loop():
    target, cfg = target_of("reference", SPEC_D3), cfg_of(SPEC_D3)
    before = episode_dict(target(cfg, 404))

    async def inside() -> Any:
        return target(cfg, 404)

    with pytest.raises(RuntimeError):
        asyncio.run(inside())
    assert episode_dict(target(cfg, 404)) == before


def test_a12_4_a_call_starts_no_thread_and_leaves_no_loop():
    """Each call owns what it uses.  On the scripted path that is nothing that outlives it: no
    thread, and no event loop left running or set on the calling thread."""
    before = {t.ident for t in threading.enumerate()}
    for policy, spec, cfg, seed in battery()[:12]:
        target_of(policy, spec)(cfg, seed)
    assert {t.ident for t in threading.enumerate()} == before
    with pytest.raises(RuntimeError):
        asyncio.get_running_loop()


def test_a12_5_the_adapter_source_declares_no_global():
    """The static half, deliberately weak: a `global` statement is how a function rebinds
    module state, so its absence rules out the commonest shape of what A12 forbids.  The
    behavioural tests above carry the weight."""
    assert not [n for n in ast.walk(adapter_tree()) if isinstance(n, ast.Global)]


def test_a12_6_two_loads_of_one_registration_are_two_registries():
    w = world()
    one = adapter().load_registry(w.d_reg, sha256=w.d_sha, sealed=w.sealed)
    two = adapter().load_registry(w.d_reg, sha256=w.d_sha, sealed=w.sealed)
    assert one is not two and one.targets is not two.targets
    spec = SPEC_D3
    key = attr_of("reference", aid(spec))
    assert episode_dict(one.targets[key](cfg_of(spec), 404)) == episode_dict(two.targets[key](cfg_of(spec), 404))


# ===========================================================================
# VAL · the pre-registration validator: N18's predicate, and the pre-registration halves of
# N15 and N17 that no other module's tests hold
# ===========================================================================

GOOD_REVISION = "c202236235762e1c871ad0ccb60c8ee5ba337b9a"


def validate(doc: Mapping[str, Any]) -> Any:
    return adapter().validate_preregistration(doc)


def refused(doc: Mapping[str, Any], *needles: str) -> None:
    """The validator raises `ValueError`, and its message names what it refused: a refusal that
    did not would pass any test of it for the wrong clause."""
    with pytest.raises(ValueError) as info:
        validate(doc)
    text = str(info.value).lower()
    for needle in needles:
        assert needle.lower() in text, (needle, str(info.value))


def with_models(*models: Mapping[str, Any]) -> dict[str, Any]:
    return reg_doc("depth", PILOT, models=models)


def model(revision: str = GOOD_REVISION, **over: Any) -> dict[str, Any]:
    entry = {
        "model": f"Qwen/Qwen3.5-9B@{revision}",
        "vllm_version": "0.29.0",
        "endpoint_type": "openai-chat-completions",
    }
    entry.update(over)
    return entry


def test_val1_the_pilots_own_registration_and_a_calibration_one_are_valid():
    """The controls for every refusal below: a validator that refused everything would pass
    them.  The pilot's two real models; the same with one; a knob R registration; and a
    calibration registration with no models at all (the scripted calibration stage has none)."""
    assert validate(reg_doc("depth", PILOT)) is None
    assert validate(with_models(model())) is None
    assert validate(reg_doc("distractor", R_SPECS)) is None
    assert validate(reg_doc("depth", PILOT, models=())) is None
    assert validate(reg_doc("depth", D_SPECS)) is None


BAD_REVISIONS = {
    "39_hex": GOOD_REVISION[:-1],
    "41_hex": GOOD_REVISION + "0",
    "non_hex_letter": GOOD_REVISION[:-1] + "g",
    "branch": "main",
    "tag": "v1.0.0",
    "empty": "",
    "sha256_length": GOOD_REVISION + GOOD_REVISION[:24],
    "short_sha": GOOD_REVISION[:7],
    "trailing_newline": GOOD_REVISION + "\n",
    "trailing_space": GOOD_REVISION + " ",
    "leading_space": " " + GOOD_REVISION,
    "prefixed": "0x" + GOOD_REVISION[:38],
}


@pytest.mark.parametrize("position", [0, 1])
@pytest.mark.parametrize("name", sorted(BAD_REVISIONS))
def test_n18_1_a_revision_that_is_not_forty_hex_characters_is_refused(name, position):
    """N18: "the pre-registration validator refuses a revision that isn't 40 hex characters",
    a full commit hash "never a branch or tag".  Either model's; twelve ways to be wrong,
    including a trailing newline (which a `$`-anchored pattern lets through) and a 41st
    character (which a `{40,}` lets through).  Owed to this module since 2026-09-13."""
    models = [model(), model(f"{GOOD_REVISION}", model=f"mistralai/Ministral-3-14B@{GOOD_REVISION}")]
    models[position] = dict(models[position], model=models[position]["model"].split("@")[0] + "@" + BAD_REVISIONS[name])
    refused(with_models(*models), "revision")


@pytest.mark.parametrize(
    "value",
    ["Qwen/Qwen3.5-9B", f"@{GOOD_REVISION}", f"a@b@{GOOD_REVISION}", 123],
    ids=["no_at", "empty_id", "two_ats", "not_a_string"],
)
def test_n18_2_a_model_that_is_not_an_id_at_a_revision_is_refused(value):
    refused(with_models(model(model=value)), "model")


def test_n18_3_models_on_different_vllm_versions_are_refused():
    """N18: "Both models are served by the same vLLM version".  Two models, and three with
    only the last one apart."""
    refused(with_models(model(), model(vllm_version="0.30.0")), "vllm_version")
    refused(with_models(model(), model(), model(vllm_version="0.28.9")), "vllm_version")
    assert validate(with_models(model(), model(), model())) is None


def test_n18_4_models_on_different_endpoint_types_are_refused():
    """"...through the same endpoint type."  The validator does not name which type: it asks
    only that the models agree."""
    refused(with_models(model(), model(endpoint_type="completions")), "endpoint_type")
    refused(with_models(model(), model(), model(endpoint_type="responses")), "endpoint_type")


@pytest.mark.parametrize("key", ["vllm_version", "endpoint_type"])
def test_n18_5_a_model_that_omits_what_the_pin_compares_is_refused(key):
    """Two models cannot be shown to agree on a value one of them does not state."""
    omitted = model()
    del omitted[key]
    refused(with_models(omitted, model()), key)
    refused(with_models(model(), omitted), key)


def test_n18_6_a_model_table_may_carry_fields_this_path_does_not_read():
    """The serve command, the decoding dict and the GPU type belong to the model path, and its
    tests add them to the same file.  This validator must not refuse them."""
    assert validate(with_models(model(gpu_type="L4", serve_command="vllm serve ...", temperature=0.7), model())) is None


@pytest.mark.parametrize("knob, specs", [("depth", (spec_of("depth", 1), spec_of("depth", 3))),
                                         ("distractor", (spec_of("distractor", 0), spec_of("distractor", 8)))])
def test_n15_1_a_sweep_of_a_knob_without_its_control_arm_is_refused(knob, specs):
    """N15: "Asking for a sweep of a knob without its control arm is a pre-registration
    error."  knobs.py's tests hold the constructor's totality; nothing held this half."""
    refused(reg_doc(knob, specs), "control")
    with_control = (*specs, spec_of(knob, specs[0].level, 14 if knob == "distractor" else 8))
    assert validate(reg_doc(knob, with_control)) is None


@pytest.mark.parametrize("horizon", [12, 14, 1, 0])
def test_n17_1_a_declared_horizon_that_is_not_the_largest_max_turns_is_refused(horizon):
    """N17: `H = max(max_turns)` over the pre-registered arms, one number.  Below it, the
    highest arm's late passes are truncated away by `diff`; above it, the horizon is not the
    one the arithmetic gives.  For the pilot arms and slack 4 it is 13."""
    refused(reg_doc("depth", PILOT, horizon=horizon), "horizon")


def test_n17_2_the_horizon_follows_the_slack_and_the_arm_set():
    assert validate(reg_doc("depth", PILOT, slack=6, horizon=15)) is None
    refused(reg_doc("depth", PILOT, slack=6, horizon=13), "horizon")
    assert validate(reg_doc("depth", (spec_of("depth", 1), spec_of("depth", 3), spec_of("depth", 1, 3)), horizon=8)) is None
    assert validate(reg_doc("distractor", R_SPECS, horizon=H_R)) is None
    refused(reg_doc("distractor", R_SPECS, horizon=H_R + 1), "horizon")


# `horizon` is N17's number for the pilot arms at the slack the case sets: 13 at slack 4, 8 at -1, 10 at `True`
# (which counts as 1).  Left at the pilot's 13, the -1 and `True` documents also break N17, so a validator that
# lacked the slack clause would refuse them for their horizon, in a message that names the slack, and the test
# would pass on those words.  No integer agrees with a slack of 4.5, which keeps 13, and the two horizon cases
# replace the horizon they are given.
#
# `slack-4.0` and `horizon-13.0` are the two cases that isolate the *type* half of each clause, and they are
# why the three cases beside them can stay as they are.  A value that is not an integer is refused twice
# wherever it can also be compared: a slack of 4.5 makes N17's number 13.5, which no integer horizon equals, so
# a build without the slack clause's type check refuses the document for its horizon instead, in a message that
# names the slack; `"13"` and `None` are refused by the horizon's type clause and again by N17's equality
# clause, and both messages name `horizon`.  Neither can be isolated by any document, because a string, a
# `None` and a non-integral float can never compare equal to N17's integer -- what isolates the type clause is
# a value that is not an `int` and *does* compare equal, which is what `4.0` and `13.0` are.  Measured in the
# mutation pass: `4.0` is accepted by two mutants and refused by every other row, and `13.0` by three.
@pytest.mark.parametrize(
    "field, value, horizon",
    [("horizon", "13", 13), ("horizon", None, 13), ("horizon", 13.0, 13), ("slack", "4", 13), ("slack", -1, 8),
     ("slack", 4.0, 13), ("slack", 4.5, 13), ("slack", True, 10)],
    ids=["horizon-13", "horizon-None", "horizon-13.0", "slack-4", "slack--1", "slack-4.0", "slack-4.5", "slack-True"],
)
def test_n17_3_slack_and_horizon_are_integers_and_slack_is_not_negative(field, value, horizon):
    doc = reg_doc("depth", PILOT, horizon=horizon)
    doc[field] = value
    refused(doc, field)


@pytest.mark.parametrize("field", ["knob", "strictness", "split", "generator_version", "slack", "horizon", "arms"])
def test_val2_every_field_the_registry_reads_is_required(field):
    doc = reg_doc("depth", PILOT)
    del doc[field]
    refused(doc, field)


def test_val3_v0_emits_the_eval_split_only():
    """G12: "v0 emits `eval` only."  The task layer's `generate` offers both splits and leaves
    "eval only" to the pre-registration; this is where it is held."""
    refused(reg_doc("depth", PILOT, split="train"), "split")
    refused(reg_doc("depth", PILOT, split="test"), "split")


def test_val4_strictness_and_knob_are_from_the_closed_sets():
    refused(reg_doc("depth", PILOT, strictness="lenient"), "strictness")
    assert validate(reg_doc("depth", PILOT, strictness="leaky")) is None
    doc = reg_doc("depth", PILOT)
    doc["knob"] = "tools"
    refused(doc, "knob")


@pytest.mark.parametrize(
    "arms, needle, horizon",
    [
        (["depth:d1", "depth:d1", "depth:d1+h8"], "depth:d1", 6),
        (["depth:d1", "depth:d1+h8", "distractor:r0@k16"], "distractor:r0@k16", 7),
        (["depth:d1", "depth:d03", "depth:d1+h8"], "depth:d03", 8),
        (["depth:d1", "depth:d3+h3"], "depth:d3+h3", 13),
        (["depth:d1", "depth:d8+h1"], "depth:d8+h1", 13),
        (["depth:d1", "depth:D1", "depth:d1+h8"], "depth:D1", 13),
        (["depth:d1", " depth:d3", "depth:d1+h8"], "depth:d3", 13),
        (["depth:d1", "depth:x", "depth:d1+h8"], "depth:x", 13),
        (["depth:d1", "depth:d3+h8 ", "depth:d1+h8"], "depth:d3+h8", 13),
    ],
    ids=["duplicate", "another_knob", "leading_zero", "control_equal", "control_lower", "capital",
         "leading_space", "not_an_arm", "trailing_space"],
)
def test_val5_an_arm_must_be_a_canonical_distinct_arm_id_of_the_registrations_knob(arms, needle, horizon):
    """Every arm names itself as `arm_id` renders it — one id per `(knob, level, control)`,
    which is what keeps two registered targets from being one arm — belongs to the
    registration's knob, and is listed once.  knobs.py's constructor refuses `d3+h3` and
    `d8+h1` (N15); here the same refusal is reached from a registration file.

    Where the listed arms are all valid, `horizon` is N17's number for them: 6 for the
    duplicate (its arms need at most 6 turns), 7 for the other knob's `r0` (which needs 7)
    and 8 for the leading zero (`d3` needs 8).  Each of the three documents then breaks one
    clause only, so a build without that clause accepts it.  Left at the pilot's 13, N17
    refuses it too, and the test would pass or fail on whether that message names the arm.
    The other six are refused while their arms are read, before any horizon is computed, and
    keep 13.

    `leading_zero` also had to stop naming an arm the document already lists: `d01` renders
    as `depth:d1`, so a build without the canonical clause refused it as a duplicate of the
    `depth:d1` beside it, in a message naming `depth:d1` and not `depth:d01`.  `d03` renders
    as `depth:d3`, which no other listed arm is, so the canonical clause is the only clause
    that can refuse the document."""
    doc = reg_doc("depth", PILOT, horizon=horizon)
    doc["arms"] = arms
    refused(doc, needle)


@pytest.mark.parametrize("arms", [[], "depth:d1", [1, 2]], ids=["empty", "a_string", "not_strings"])
def test_val6_arms_is_a_non_empty_list_of_strings(arms):
    doc = reg_doc("depth", PILOT)
    doc["arms"] = arms
    refused(doc, "arms")


def test_val7_a_non_canonical_distractor_id_is_refused_because_its_k_is_fixed():
    """`@k16` is fixed and the renderer is the only thing that writes it, so `@k8` is
    not another arm: it is an id `arm_id` would never produce.

    `distractor:r4@k8` takes the place of `distractor:r4@k16`, the arm it renders as, rather
    than of the last arm in the list.  It used to take the last one's place, which left the
    `r4@k16` it renders as still listed, so a build without the canonical clause refused the
    document as a duplicate, in a message naming `distractor:r4@k16`.  Swapped for the arm it
    renders as, the arm set such a build reads is exactly `R_SPECS` -- every arm once, a
    control arm among them, and `reg_doc`'s horizon still N17's number for it -- so the
    canonical clause is the only clause that can refuse the document."""
    doc = reg_doc("distractor", R_SPECS)
    doc["arms"] = ["distractor:r4@k8" if a == "distractor:r4@k16" else a for a in doc["arms"]]
    refused(doc, "distractor:r4@k8")


def test_val8_the_validator_reads_and_never_writes_its_document():
    doc = reg_doc("depth", PILOT)
    before = copy.deepcopy(doc)
    validate(doc)
    assert doc == before


def test_val9_top_level_fields_this_path_does_not_read_are_tolerated():
    assert validate(reg_doc("depth", PILOT, serve_command="vllm serve ...", primary_event="passed")) is None


def test_val10_models_is_a_list_of_tables():
    doc = reg_doc("depth", PILOT)
    doc["models"] = "Qwen/Qwen3.5-9B@" + GOOD_REVISION
    refused(doc, "models")


# ===========================================================================
# F · the `faulty` scripted policy
# ===========================================================================


def faulty(spec: ArmSpec, cell: str, seed: int) -> Any:
    return target_of("faulty", spec)(cfg_of(spec, plant_cell=cell), seed)


def strip_policy(episode: Any) -> dict[str, Any]:
    d = episode_dict(episode)
    d["meta"].pop("policy")
    return d


def test_f1_a_plant_cell_with_no_plant_behaves_as_the_reference_target():
    """`faulty` reads its planted parameters from a sealed file, selected by
    `cfg["plant_cell"]`; the scripted calibration stage plants one of two cells so that
    "naming can be scored", and the other cell is the one with none.  It must then be the
    reference target exactly."""
    for spec in ALL_SPECS:
        for seed in (0, 404, 2**32 - 1):
            plain = target_of("reference", spec)(cfg_of(spec), seed)
            clean = faulty(spec, "clean", seed)
            assert strip_policy(clean) == strip_policy(plain), (aid(spec), seed)
            assert clean.meta["policy"] == "faulty" and plain.meta["policy"] == "reference"


@pytest.mark.parametrize("cell", ["absent", "", "Planted"])
def test_f2_a_plant_cell_that_the_sealed_file_does_not_name_is_refused(cell):
    """Never silently "no plant": a typo in a cell name would score a planted cell as clean."""
    with pytest.raises(ValueError, match="plant_cell"):
        faulty(SPEC_D3, cell, 404)
    with pytest.raises(ValueError, match="plant_cell"):
        target_of("faulty", SPEC_D3)(cfg_of(SPEC_D3), 404)


@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_f3_a_step_failure_rate_of_one_fails_the_first_required_call_and_the_episode_ends(spec):
    """"Each required call fails at a fixed per-step rate."  At rate 1 the first one does: the
    call is made wrongly, the engine rejects it (E4, so the record does not move), and the
    policy replies.  One sampled call, two turns, and the target record is below its goal."""
    for seed in (404, 2121):
        episode = faulty(spec, "planted", seed)
        assert episode.outcome == "wrong_state", (aid(spec), seed)
        assert episode.t == 2 and episode.meta["sampled_calls"] == 1
        assert episode.meta["leaky_pass"] is False


def test_f4_the_depth_plant_lowers_the_pass_rate_with_depth_and_not_with_history():
    """"A pure-depth plant ... so the pass rate falls with `d` and doesn't depend on
    history."  At rate 0.5 the pass rate is about 0.5, 0.125 and 0.004 at `d1`, `d3` and
    `d8`, and the same at `d1+h8` as at `d1`.  Counted over 300 seeds; the margins are many
    standard deviations, so they do not depend on which keyed draw a build uses."""
    counts = {}
    for spec in (D_SPECS[0], D_SPECS[2], D_SPECS[4], D_SPECS[5]):
        counts[aid(spec)] = sum(faulty(spec, "depth_half", s).outcome == "passed" for s in range(300))
    d1, d3, d8, control = (counts[a] for a in ("depth:d1", "depth:d3", "depth:d8", "depth:d1+h8"))
    assert 100 < d1 < 200
    assert 10 < d3 < 90
    assert d8 <= 15
    assert d1 > d3 > d8
    assert abs(d1 - control) <= 60


def expected_history_full(spec: ArmSpec) -> tuple[str, int, int]:
    """(outcome, t, sampled calls) under a history rate that makes any history fatal: a step
    fails exactly when some history precedes it.  A depth control seeds `H - dL` pairs, so it
    fails its first call; every other arm has none before its first call and its own after.
    Knob R's control seeds nothing (its filler is a system prompt, not history)."""
    if spec.knob == "depth":
        if spec.control is not None:
            return "wrong_state", 2, 1
        return ("passed", 2, 1) if spec.level == 1 else ("wrong_state", 3, 2)
    return "wrong_state", D_R + 1, D_R


@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_f5_the_history_plant_fires_on_the_history_the_policy_can_see(spec):
    """"A pure-history plant. The failure probability rises with the history tokens present,
    counted under the reference tokenizer, and doesn't depend on depth."  `faulty` "reads
    history from the bundle's prompt `Messages` plus its own calls".  So `d1` — no history
    before its one call — passes at a rate that would fail anything with history, a control
    fails its first call on the seeded pairs alone, and every arm of depth two or more fails
    its second, on its own first pair."""
    outcome, t, calls = expected_history_full(spec)
    for seed in (404, 2121, 65535):
        episode = faulty(spec, "history_full", seed)
        assert (episode.outcome, episode.t, episode.meta["sampled_calls"]) == (outcome, t, calls), (aid(spec), seed)


@pytest.mark.parametrize("spec", ALL_SPECS, ids=SPEC_IDS)
def test_f6_the_leaky_plant_overshoots_where_the_block_allows_and_only_there(spec):
    """"A leaky-only plant. The policy overshoots at a fixed rate. Leaky passes these
    episodes and strict fails them."  At rate 1 it overshoots whenever the block holds a tool
    that carries the target past its goal — which the task layer states as the presence of an
    `overshoot` negative control — and otherwise is the reference."""
    for seed in (404, 2121):
        bundle = bundle_of(spec, seed)
        episode = faulty(spec, "overshoot_full", seed)
        calls = len(bundle.reference_calls)
        if "overshoot" in bundle.negative_controls:
            assert episode.outcome == "overshoot", (aid(spec), seed)
            assert episode.meta["leaky_pass"] is True and episode.meta["strict_label"] == "overshoot"
            assert episode.t == calls + 2 and episode.meta["sampled_calls"] == calls + 1
        else:
            assert episode.outcome == "passed" and episode.t == calls + 1


def test_f7_a_faulty_episode_is_a_function_of_cfg_and_seed_alone():
    """"Its per-step error is driven by the Proofload seed, so it is fully deterministic": one
    seed always gives one episode, and across seeds a half-rate plant gives both outcomes.
    At `d1` and rate 0.5 either outcome has probability one half per seed, so sixty seeds all
    giving one of them is a one-in-10^17 event under any keyed draw."""
    outcomes = set()
    for seed in range(60):
        one, two = faulty(D_SPECS[0], "depth_half", seed), faulty(D_SPECS[0], "depth_half", seed)
        assert episode_dict(one) == episode_dict(two)
        outcomes.add(one.outcome)
    assert outcomes == {"passed", "wrong_state"}


def test_f8_two_plant_cells_of_one_sweep_are_named_by_their_rows():
    """Stage 0a's naming score is read off the store: over a real two-cell sweep, every
    episode of the planted cell fails and every episode of the clean cell passes."""
    w = world()
    for (key, arm), run_id in sorted(w.runs.items()):
        if key != "faulty":
            continue
        rows = read_rows(w.store, run_id)
        by_cell = {"planted": set(), "clean": set()}
        for row in rows:
            by_cell[row["config"]["plant_cell"]].add(row["outcome"])
        assert by_cell == {"planted": {"wrong_state"}, "clean": {"passed"}}, arm


def sealed_file(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "sealed_under_test.toml"
    path.write_text(text)
    return path


@pytest.mark.parametrize(
    "text, needle",
    [
        ("[cells.a]\nstep_fail_rat = 0.3\n", "step_fail_rat"),
        ("[cells.a]\nstep_fail_rate = 1.5\n", "step_fail_rate"),
        ("[cells.a]\nhistory_fail_rate = -0.1\n", "history_fail_rate"),
        ("[cells.a]\novershoot_rate = \"half\"\n", "overshoot_rate"),
        ("[cells.a]\novershoot_rate = true\n", "overshoot_rate"),
        ("[cells]\n", "cells"),
        ("plants = 1\n", "cells"),
        ("cells = 1\n", "cells"),
        ("[cells]\nzeta = 1\n", "zeta"),
        ("[cells.a\n", ""),
    ],
    ids=["typo_key", "rate_above_one", "rate_below_zero", "string_rate", "bool_rate", "no_cells",
         "no_cells_table", "cells_not_a_table", "cell_not_a_table", "malformed_toml"],
)
def test_f9_a_sealed_file_that_cannot_be_read_as_plants_is_refused_at_load(tmp_path, text, needle):
    """Before any episode, and by name: a mistyped parameter would otherwise be a plant that
    silently does nothing, and a calibration scored against a plant that never fired."""
    reg, sha, _ = pilot_files(tmp_path)
    with pytest.raises(ValueError, match=re.escape(needle) if needle else None):
        adapter().load_registry(reg, sha256=sha, sealed=sealed_file(tmp_path, text))


# ===========================================================================
# CT · inherited coverage: the task layer's knob R level axis, at the contrast the adapter pairs.
#
# The task layer's tests build one knob R contrast, `r0` against `r8`, at three seeds, and four rows
# of the mutation pass against its build survive its whole 235-test suite for that reason.  These
# tests are task-layer behaviour reached through the registered arm sets — the arms this adapter
# runs against one salt and compares — over every level, both splits, and the seeds whose
# first record-id word a tool name carries.  Every one is **green before and after**:
# none of them imports the adapter.  The open record-id gap (`city`, `disc`, `grad` and
# `port` refuse a contrast that holds `r14`) is excluded and not asserted.
# ===========================================================================


def first_word(seed: int, split: str) -> str:
    return encode_record_id(seed, split).split("-")[0]


def contrast_ok(specs: Iterable[ArmSpec], seeds: Iterable[int], split: str = "eval") -> int:
    arms = tuple(dataclasses.replace(s, split=split) for s in specs)
    made = 0
    for seed in seeds:
        generate_contrast(arms, seed)  # raises ValueError if the ledger refuses
        made += 1
    return made


R_NO_14 = tuple(s for s in R_SPECS if s.level != 14 and s.control != 14)
R_TOP = (spec_of("distractor", 0), spec_of("distractor", 14))
NON_GAP = tuple(s for s in SPREAD + SPACED if first_word(s, "eval") not in GAP_WORDS["eval"])


def test_ct1_every_registered_depth_arm_holds_the_ledger_across_the_seed_space():
    assert contrast_ok(D_SPECS, SPREAD + SPACED) == len(SPREAD + SPACED)


def test_ct2_every_registered_distractor_arm_holds_the_ledger_across_the_seed_space():
    """Every level `r0` to `r14` and both controls at once: nothing here is one pair."""
    assert contrast_ok(R_SPECS, NON_GAP) == len(NON_GAP)


def test_ct5_the_top_level_holds_the_ledger_across_a_dense_spread_of_seeds():
    """`r14` keeps no read tool at all, so the prose and the entry-code draw are all that
    hold N7's set still there.  The mutation pass against the task layer's build measured
    248 of 1,216 refusals against 0 with the prose rule off, and 10 with the entry-code rule
    off, all at `r14`: a sample this size sees both."""
    seeds = [s for s in spaced(160, offset=3) if first_word(s, "eval") not in GAP_WORDS["eval"]]
    assert len(seeds) >= 150
    assert contrast_ok(R_TOP, seeds) == len(seeds)
