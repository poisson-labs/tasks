"""The knob probe: whether each new knob makes tasks harder, per model.

The probe is pre-registered in the knobs spec, in its section on the probes, and this module builds
exactly what that section states.  Seven knobs are read at their base and their top level, four of
them with a control arm too, on sixty eval-split tasks that no published card measures, two attempts
at each, for gpt-5-nano and for Qwen3-8B, on the frozen generator.  Here are the probe's design, its
phase 1 gate, its analysis and its outcomes, and the driver of the gpt-5-nano run
(`python -m poisson_tasks.knob_probe`).  Qwen3-8B's run is the Colab notebook's probe design
(`calibration_run`'s `--design knob-probe`), which takes its design and its gates from here.  None
of it is a command of the command-line tool.

The design
----------
* **Seeds.**  Seed `i` of the named derivation `poisson-tasks/knob-probe/seeds/v1` is the first four
  bytes of `sha256("poisson-tasks/knob-probe/seeds/v1:<i>")`, the shape the cards' own seeds have;
  a seed in the cards' published sixty, or one already drawn, is skipped.  The first three are phase
  1's, in the order drawn, and the next sixty, sorted, are the probe's.  Both lists' hashes are the
  cards' seed-list digest.
* **Arms.**  The eighteen of `ARMS`: the seven bases, then the seven tops, then the four controls,
  run in that order, so a stop costs tops and controls and never a base.
* **Episodes.**  Two attempts at each of the sixty tasks, 120 an arm and 2,160 a model, each capped
  at 32 model calls, through the `null` harness, with the run's concurrency recorded.

Phase 1
-------
One attempt at each of phase 1's three seeds, every arm, before anything else.  The cards' plumbing
gate applies to the seven base arms, pooled, with its no-call clause read as the cards' share rule:
phase 1 stops when more than 0.10 of the 21 base episodes made no tool call, so 3 or more.  That
clause is a new pre-registration, made on 2026-10-13 after the first gpt-5-nano run's phase 1 had
stopped on 1 of 21 under "any one"; every other check is as first registered.  The other eleven
arms are checked for plumbing only (every planned episode recorded and scored, no instrument
label, an empty tally), because "half reach the structural minimum" and "at least one tool call"
could stop the probe on a knob that bites hard.  If phase 1 fails the probe stops there and
reports what it spent.

A folder whose phase 1 failed may be re-gated once (`regate_phase1`): its recorded episodes are
read again under the amended clause, with a reason written down, no episode run and no call made.
The first verdict stays in `phase1.json`, the new one is written beside it, and the outcome says
so in a line of its own.

The run (gpt-5-nano)
--------------------
Every episode goes through the run engine (`runs.run_plan`): its arm runner is the calibration
runner's body, with the run engine's dollar cap and ledger woven in, and the config it runs an arm
with is `calibration.run_config_for`'s field for field, at the run's concurrency.  The cap is the
run engine's own, over phase 1 and the probe together: the probe's is the cap less what phase 1
spent.  Before the first paid call the driver refuses a generator that is not the frozen one,
loads the key from a `.env` file without printing it, checks it with the one free request the
front door makes, and writes the probe's record: the frozen generator's hash, both seed lists and
their hashes, the arms, the settings, the cap and the concurrency.  Run again, it resumes a stopped
run; a failed phase 1 and a finished probe are not run again, so no failed episode is quietly run
twice, and only a recorded re-run of a void arm reopens a finished probe.  After a passing re-gate
it goes on with the probe in the same folder, within the same cap, phase 1's spend counted.

The analysis
------------
Per knob and model, Δ is strict pass@1 at the base minus at the top, paired over the sixty seeds:
`calibration.paired_delta` with no provenance block (2,000 resamples, seed 20260922, the cards'
quantile rule), so the cards' refusal of a saturated cell does not apply.  The two clauses are
applied here: the interval excludes zero, and Δ is at least 0.15 and positive.  A base at 1.000 can
still bite.  Faults, block size and argument difficulty need their control contrast too; shape is
two-sided and needs its control to differ from `w1` by less than 0.15.

Outcomes, voids and stops
-------------------------
An arm whose instrument rate is above 0.02 is void, and so is one whose no-call share is above 0.10
when its knob's base arm's is too.  A knob is decided on complete arms only.  `knob_outcome` reads
both models: a knob ships when it bites on one and the top is easier on neither; shape ships when it
bites on one.  A void arm may be re-run once when its cause is the instrument, and the re-run is
recorded (`start_rerun`).
"""

from __future__ import annotations

import argparse as _argparse
import dataclasses as _dc
import datetime as _datetime
import hashlib as _hashlib
import importlib.metadata as _metadata
import json as _json
import os as _os
import pathlib as _pathlib
import shutil as _shutil
import sys as _sys
import types as _types
from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from typing import Any as _Any

from poisson_tasks import calibration as _cal
from poisson_tasks import calibration_run as _run
from poisson_tasks.export import MEASURED_HARNESS as _HARNESS
from poisson_tasks.tasks import generate as _generate
from poisson_tasks.taskset import MAX_MODEL_CALLS as _MAX_MODEL_CALLS

__all__ = [
    "DERIVATION",
    "derive_seeds",
    "PHASE1_SEEDS",
    "PROBE_SEEDS",
    "PHASE1_SEED_LIST_HASH",
    "PROBE_SEED_LIST_HASH",
    "Knob",
    "KNOBS",
    "BASES",
    "TOPS",
    "CONTROLS",
    "ARMS",
    "Design",
    "DESIGN",
    "ATTEMPTS",
    "EPISODES_PER_ARM",
    "EPISODES_PER_MODEL",
    "MAX_MODEL_CALLS",
    "MODEL",
    "BASE_URL",
    "DECODING",
    "EXPECTED_MODELS",
    "FROZEN_GENERATOR_HASH",
    "GeneratorMoved",
    "check_generator",
    "PHASE1_NO_CALL",
    "Phase1Verdict",
    "phase1_verdict",
    "notebook_verdict",
    "ArmResult",
    "arm_results",
    "Contrast",
    "contrast",
    "KnobResult",
    "knob_result",
    "KnobOutcome",
    "knob_outcome",
    "analyse",
    "render_outcome",
    "write_model_records",
    "write_outcome",
    "probe_record",
    "check_record",
    "probe_plan",
    "card_rates",
    "read_model_records",
    "RerunRefused",
    "start_rerun",
    "REGATE_FILE",
    "regate_phase1",
    "phase1_disclosure",
    "KeyMissing",
    "load_key",
    "run_probe",
    "rerun_void",
    "build_parser",
    "main",
]

# ---------------------------------------------------------------------------
# the seeds
# ---------------------------------------------------------------------------

DERIVATION = "poisson-tasks/knob-probe/seeds/v1"
"""The probe's named seed derivation: its first three seeds are phase 1's, the next sixty the
probe's."""


def derive_seeds(
    derivation: str = DERIVATION,
    *,
    skip: _Iterable[int] | None = None,
    phase1: int = 3,
    probe: int = 60,
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Phase 1's seeds, in the order drawn, and the probe's, sorted.  Seed `i` is the first four
    bytes of `sha256("<derivation>:<i>")`; a seed in `skip` (the cards' published sixty) or one
    already drawn is passed over, so no probe task is a card task."""
    skipped = set(_cal.seed_list() if skip is None else skip)
    drawn: list[int] = []
    index = 0
    while len(drawn) < phase1 + probe:
        digest = _hashlib.sha256(f"{derivation}:{index}".encode()).digest()
        seed = int.from_bytes(digest[:4], "big")
        if seed not in skipped and seed not in drawn:
            drawn.append(seed)
        index += 1
    return tuple(drawn[:phase1]), tuple(sorted(drawn[phase1:]))


PHASE1_SEEDS, PROBE_SEEDS = derive_seeds()
PHASE1_SEED_LIST_HASH = _cal._seed_list_digest(PHASE1_SEEDS)
PROBE_SEED_LIST_HASH = _cal._seed_list_digest(PROBE_SEEDS)

# ---------------------------------------------------------------------------
# the arms
# ---------------------------------------------------------------------------


@_dc.dataclass(frozen=True)
class Knob:
    """A knob as the probe reads it: its base arm, its top arm and its control, if it has one."""

    name: str
    base: str
    top: str
    control: str | None = None

    @property
    def arms(self) -> tuple[str, ...]:
        return (self.base, self.top) + ((self.control,) if self.control else ())


KNOBS: tuple[Knob, ...] = (
    Knob("similarity", "similarity:s0", "similarity:s3"),
    Knob("faults", "faults:f0", "faults:f4", "faults:f0+len(f4)"),
    Knob("history", "history:t0", "history:t2400"),
    Knob("block", "block:k8", "block:k64", "block:k8+len(k64)"),
    Knob("arguments", "arguments:a2", "arguments:a8", "arguments:a2+len(a8)"),
    Knob("shape", "shape:w1", "shape:w4", "shape:w1+len(w4)"),
    Knob("spread", "spread:p1", "spread:p4"),
)
"""The seven knobs in the spec's table order.  Depth is not re-probed: both cards show it moves
pass rates."""
BASES: tuple[str, ...] = tuple(knob.base for knob in KNOBS)
TOPS: tuple[str, ...] = tuple(knob.top for knob in KNOBS)
CONTROLS: tuple[str, ...] = tuple(knob.control for knob in KNOBS if knob.control)
ARMS: tuple[str, ...] = BASES + TOPS + CONTROLS
"""The eighteen arms in the order they run: the bases, then the tops, then the controls."""

ATTEMPTS = 2
PHASE1_ATTEMPTS = 1
EPISODES_PER_ARM = ATTEMPTS * len(PROBE_SEEDS)
EPISODES_PER_MODEL = EPISODES_PER_ARM * len(ARMS)
MAX_MODEL_CALLS = _MAX_MODEL_CALLS
"""Every episode ends after 32 model calls: the taskset's own turn limit."""


@_dc.dataclass(frozen=True)
class Design:
    """What a probe run runs.  `DESIGN` is the pre-registered one; a smaller one is for tests."""

    arms: tuple[str, ...]
    phase1_seeds: tuple[int, ...]
    probe_seeds: tuple[int, ...]
    attempts: int = ATTEMPTS
    phase1_attempts: int = PHASE1_ATTEMPTS

    @property
    def episodes_per_arm(self) -> int:
        return self.attempts * len(self.probe_seeds)

    @property
    def phase1_episodes_per_arm(self) -> int:
        return self.phase1_attempts * len(self.phase1_seeds)


DESIGN = Design(arms=ARMS, phase1_seeds=PHASE1_SEEDS, probe_seeds=PROBE_SEEDS)

# ---------------------------------------------------------------------------
# the models and their settings
# ---------------------------------------------------------------------------

MODEL = _cal.MODEL_A
"""gpt-5-nano at its dated snapshot, as its card was run."""
BASE_URL = "https://api.openai.com/v1"
DECODING: _Mapping[str, _Any] = _types.MappingProxyType(dict(_cal.DECODING))
"""Temperature 1.0, top_p 1.0, reasoning effort low, 2,048 completion tokens: the cards'."""
QWEN = _run.QWEN3_8B.served_name
EXPECTED_MODELS: tuple[str, ...] = (MODEL, QWEN)
"""The two models the outcome reads, in the order it prints them."""
KEY_VAR = "MODEL_API_KEY"
"""The variable the key is read from in the `.env` file, as model A's card read it."""
CONCURRENCY = 128
"""Episodes in flight at once: the calibration runner's own default, which both cards ran at."""
ESTIMATE_DOLLARS = 1.67
"""The spec's estimate for 2,160 gpt-5-nano episodes, from the published per-call figures."""

FROZEN_GENERATOR_HASH = _run.EXPECTED_GENERATOR_HASH
"""The generator frozen when information spread merged.  The probe runs on it and on no other."""

# ---------------------------------------------------------------------------
# the rule's constants: the cards'
# ---------------------------------------------------------------------------

DELTA_STAR = _cal.DELTA_STAR
RESAMPLES = _cal.BOOTSTRAP_RESAMPLES
BOOTSTRAP_SEED = _cal.BOOTSTRAP_SEED
VOID_INSTRUMENT = _cal.INSTRUMENT_THRESHOLD
VOID_NO_CALL = _cal.NO_CALL_THRESHOLD
PHASE1_NO_CALL = _cal.NO_CALL_THRESHOLD
"""Phase 1 stops when more than this share of the base arms' episodes, pooled, made no tool call:
3 or more of 21.  The cards' own refusal threshold, as pre-registered for phase 1 on 2026-10-13."""
PHASE1_NO_CALL_DATE = "2026-10-13"
"""When phase 1's no-call clause became the share rule, after the first gpt-5-nano run's phase 1."""
_EXACT = 1e-9
"""Pass rates here are multiples of 1/120, so Δ = 0.15 is 18/120 exactly; a comparison with 0.15
allows for the last bit of floating point, so 0.7 - 0.55 is not read as below it."""

# statuses of a knob on one model
BITES = "bites"
DOES_NOT_BITE = "does not bite"
TOP_EASIER = "top easier"
VOID = "void"
UNDECIDED = "undecided"
NOT_RUN = "not run"

# outcomes of a knob
SHIPS = "ships"
DOES_NOT_SHIP = "does not ship"
BACK = "back for a decision"
WAITING = "waiting"

# ---------------------------------------------------------------------------
# the generator
# ---------------------------------------------------------------------------


class GeneratorMoved(RuntimeError):
    """The package's generator is not the frozen one."""


def check_generator(arms: _Sequence[str] = ARMS, seed: int | None = None) -> str:
    """The frozen generator's hash, read off one task of every arm; refuses any other."""
    at = PROBE_SEEDS[0] if seed is None else seed
    for arm in arms:
        found = _generate(_run.spec_for(arm), at).generator_hash
        if found != FROZEN_GENERATOR_HASH:
            raise GeneratorMoved(
                f"this package's generator is {found}, not the frozen {FROZEN_GENERATOR_HASH}; "
                "the probe runs only on the frozen generator"
            )
    return FROZEN_GENERATOR_HASH


# ---------------------------------------------------------------------------
# phase 1, and the notebook's own gate
# ---------------------------------------------------------------------------


def _by_arm(records: _Iterable[_cal.EpisodeRecord]) -> dict[str, list[_cal.EpisodeRecord]]:
    out: dict[str, list[_cal.EpisodeRecord]] = {}
    for row in records:
        out.setdefault(row.arm_id, []).append(row)
    return out


def _merged(tallies: _Iterable[_Mapping[str, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for tally in tallies:
        for label, count in tally.items():
            out[label] = out.get(label, 0) + int(count)
    return out


@_dc.dataclass(frozen=True)
class Phase1Verdict:
    """Phase 1's gate: the plumbing gate on the base arms, pooled, its no-call clause read as the
    share rule, and plumbing alone on every other arm.  `bases` is the base arms' gate as phase 1
    reads it; `plumbing` holds the reasons each arm failed on, by arm."""

    passed: bool
    reasons: tuple[str, ...]
    bases: _cal.PlumbingVerdict
    plumbing: dict[str, tuple[str, ...]]


def _plumbing(
    rows: _Sequence[_cal.EpisodeRecord], tally: _Mapping[str, int], planned: int
) -> tuple[str, ...]:
    reasons: list[str] = []
    if len(rows) < planned:
        reasons.append(f"{len(rows)} of its {planned} episodes were recorded")
    labelled = sum(1 for row in rows if row.label in _cal.INSTRUMENT_LABELS)
    if labelled:
        reasons.append(f"{labelled} of its episodes carry an instrument label")
    if sum(tally.values()):
        reasons.append(f"its instrument tally is not empty: {dict(tally)}")
    return tuple(reasons)


def _shared_no_call(gate: _cal.PlumbingVerdict) -> _cal.PlumbingVerdict:
    """The cards' gate with its no-call clause read as the share rule: its reason for any episode
    without a tool call is dropped, and one for a share above `PHASE1_NO_CALL` takes its place."""
    if not gate.no_call:
        return gate
    theirs = f"{gate.no_call} of {gate.episodes} episodes made no tool call"
    share = gate.no_call / gate.episodes
    ours = (
        f"{gate.no_call} of {gate.episodes} episodes made no tool call, a share of {share:.3f}, "
        f"above {PHASE1_NO_CALL}"
    )
    reasons = [
        ours if reason == theirs else reason
        for reason in gate.reasons
        if reason != theirs or share > PHASE1_NO_CALL
    ]
    return _dc.replace(gate, passed=not reasons, reasons=tuple(reasons))


def phase1_verdict(
    records: _Mapping[str, _Sequence[_cal.EpisodeRecord]],
    tallies: _Mapping[str, _Mapping[str, int]],
    *,
    design: Design = DESIGN,
) -> Phase1Verdict:
    """Phase 1 passes when the seven base arms pass the plumbing gate, pooled, and every arm has
    every planned episode recorded and scored with an empty tally.  Of the gate's clauses, the
    no-call one alone is read as the cards' share rule: the base arms stop phase 1 when more than
    `PHASE1_NO_CALL` of their episodes made no tool call, not on any one."""
    planned = design.phase1_episodes_per_arm
    bases = [arm for arm in design.arms if arm in BASES]
    base_rows = [row for arm in bases for row in records.get(arm, ())]
    gate = _shared_no_call(
        _cal.plumbing_gate(base_rows, _merged(tallies.get(arm, {}) for arm in bases))
    )
    reasons = [f"base arms: {reason}" for reason in gate.reasons]
    plumbing: dict[str, tuple[str, ...]] = {}
    for arm in design.arms:
        found = _plumbing(records.get(arm, ()), tallies.get(arm, {}), planned)
        if found:
            plumbing[arm] = found
            reasons += [f"{arm}: {reason}" for reason in found]
    return Phase1Verdict(passed=not reasons, reasons=tuple(reasons), bases=gate, plumbing=plumbing)


def notebook_verdict(
    records: _Mapping[str, _Sequence[_cal.EpisodeRecord]],
    tallies: _Mapping[str, _Mapping[str, int]],
    facts: _Mapping[str, _Mapping[str, int]],
    *,
    prompt_cap: int,
) -> _run.ProbeVerdict:
    """The notebook's own gates for Qwen, read on phase 1's episodes: the instrument check and the
    context checks (no episode ended at the context cap, no prompt past the headroom) on every arm,
    the leaky floor and the no-call stop on the seven base arms only."""
    base_rows = [row for arm in BASES for row in records.get(arm, ())]
    verdict = _run.probe_verdict(
        base_rows,
        _merged(tallies.get(arm, {}) for arm in BASES),
        max_prompt_tokens=max(
            (int(f.get("max_prompt_tokens", 0)) for f in facts.values()), default=0
        ),
        context_stops=sum(int(f.get("context_stops", 0)) for f in facts.values()),
        prompt_cap=prompt_cap,
        floor_arms=BASES,
    )
    others = [arm for arm in records if arm not in BASES]
    labelled = sum(
        1 for arm in others for row in records[arm] if row.label in _cal.INSTRUMENT_LABELS
    )
    tallied = sum(sum(tallies.get(arm, {}).values()) for arm in others)
    failures = max(labelled, tallied)
    if not failures:
        return verdict
    reasons = (
        *verdict.reasons,
        f"{failures} instrument failure(s) on the other arms: the plumbing is not clean",
    )
    return _dc.replace(verdict, proceed=False, reasons=reasons)


# ---------------------------------------------------------------------------
# the analysis
# ---------------------------------------------------------------------------


@_dc.dataclass(frozen=True)
class ArmResult:
    """One arm on one model: whether it is complete, whether it is void and why, and the measures
    reported beside the primary one."""

    arm: str
    model: str
    episodes: int
    planned: int
    complete: bool
    instrument_failures: int
    instrument_rate: float
    no_call_share: float | None
    void: tuple[str, ...]
    measures: dict[str, _Any]
    rerun: dict[str, _Any] | None = None

    @property
    def is_void(self) -> bool:
        return bool(self.void)


def _seed_counts(rows: _Sequence[_cal.EpisodeRecord]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for row in rows:
        counts[row.seed] = counts.get(row.seed, 0) + 1
    return counts


def _measures(
    rows: _Sequence[_cal.EpisodeRecord], rates: _Mapping[str, _Any] | None
) -> dict[str, _Any]:
    """Strict pass@1, the primary measure, and what the spec reports beside it: leaky, the
    no-call share, gave up after a fault, cost and time.  Each a figure the cards compute."""
    kept = _cal.scored(rows)
    out: dict[str, _Any] = {"scored": len(kept)}
    spent = {
        "prompt_tokens": sum(row.prompt_tokens for row in rows),
        "cached_input_tokens": sum(row.cached_input_tokens for row in rows),
        "completion_tokens": sum(row.completion_tokens for row in rows),
    }
    out["dollars"] = _cal.dollars(spent, rates)
    out["tokens"] = sum(spent.values())
    if not kept:
        return out
    strict = _cal.pass_at_1(kept)
    out["strict"] = strict
    out["strict_interval"] = list(
        _cal.cluster_bootstrap(kept, _cal.pass_at_1, resamples=RESAMPLES, seed=BOOTSTRAP_SEED)
    )
    out["leaky"] = _cal._leaky_at_1(kept)
    out["leaky_interval"] = list(
        _cal.cluster_bootstrap(kept, _cal._leaky_at_1, resamples=RESAMPLES, seed=BOOTSTRAP_SEED)
    )
    out["no_call_share"] = sum(1 for row in kept if _cal._made_no_call(row)) / len(kept)
    judged = [row for row in kept if row.gave_up_after_fault is not None]
    if judged:
        out["gave_up_after_fault"] = sum(1 for row in judged if row.gave_up_after_fault)
        out["gave_up_after_fault_share"] = out["gave_up_after_fault"] / len(judged)
    out.update(_cal._cost_and_time(kept, strict))
    return out


def arm_results(
    records: _Mapping[str, _Sequence[_cal.EpisodeRecord]],
    tallies: _Mapping[str, _Mapping[str, int]],
    *,
    model: str,
    design: Design = DESIGN,
    rates: _Mapping[str, _Any] | None = None,
    reruns: _Sequence[_Mapping[str, _Any]] = (),
) -> dict[str, ArmResult]:
    """Every arm of the design on one model.  An arm is complete when each of the probe's seeds
    has its attempts recorded, scored or not.  It is void when its instrument rate is above 0.02,
    or when its no-call share is above 0.10 and its knob's base arm's is too."""
    planned = design.episodes_per_arm
    rerun_of = {str(entry["arm"]): dict(entry) for entry in reruns}
    shares: dict[str, float | None] = {}
    partial: dict[str, ArmResult] = {}
    for arm in design.arms:
        rows = list(records.get(arm, ()))
        tally = tallies.get(arm, {})
        counts = _seed_counts(rows)
        complete = all(counts.get(seed, 0) >= design.attempts for seed in design.probe_seeds)
        kept = _cal.scored(rows)
        labelled = len(rows) - len(kept)
        failures = max(labelled, sum(tally.values())) if tally else labelled
        share = (sum(1 for row in kept if _cal._made_no_call(row)) / len(kept)) if kept else None
        shares[arm] = share
        partial[arm] = ArmResult(
            arm=arm,
            model=model,
            episodes=len(rows),
            planned=planned,
            complete=complete,
            instrument_failures=failures,
            instrument_rate=_cal.instrument_rate(rows, tally),
            no_call_share=share,
            void=(),
            measures=_measures(rows, rates),
            rerun=rerun_of.get(arm),
        )
    out: dict[str, ArmResult] = {}
    base_of = {arm: knob.base for knob in KNOBS for arm in knob.arms}
    for arm, result in partial.items():
        void: list[str] = []
        if result.instrument_rate > VOID_INSTRUMENT:
            void.append(
                f"its instrument rate {result.instrument_rate:.3f} is above {VOID_INSTRUMENT}"
            )
        base_share = shares.get(base_of.get(arm, arm))
        if (
            result.no_call_share is not None
            and result.no_call_share > VOID_NO_CALL
            and base_share is not None
            and base_share > VOID_NO_CALL
        ):
            void.append(
                f"its no-call share {result.no_call_share:.3f} is above {VOID_NO_CALL}"
                + (
                    ""
                    if base_of.get(arm, arm) == arm
                    else f", and so is its base arm's ({base_share:.3f})"
                )
            )
        out[arm] = _dc.replace(result, void=tuple(void))
    return out


@_dc.dataclass(frozen=True)
class Contrast:
    """`a` minus `b` in strict pass@1, paired over the seeds, with the cards' bootstrap.  When the
    pair cannot be computed, `reason` says why and the figures are `None`."""

    a: str
    b: str
    delta: float | None
    low: float | None
    high: float | None
    reason: str | None = None

    @property
    def computed(self) -> bool:
        return self.delta is not None

    @property
    def excludes_zero(self) -> bool:
        return self.low is not None and self.high is not None and not (self.low <= 0.0 <= self.high)

    @property
    def meets(self) -> bool:
        """The rule: the interval excludes zero, and `a - b` is positive and at least 0.15."""
        return (
            self.delta is not None
            and self.excludes_zero
            and self.delta > 0.0
            and self.delta >= DELTA_STAR - _EXACT
        )

    @property
    def reversed(self) -> bool:
        """The rule the other way: `b - a` meets it, so `b` is the easier."""
        return (
            self.delta is not None
            and self.excludes_zero
            and self.delta < 0.0
            and -self.delta >= DELTA_STAR - _EXACT
        )

    @property
    def two_sided(self) -> bool:
        """Shape's rule: the interval excludes zero and the size is at least 0.15 either way."""
        return self.meets or self.reversed

    def as_dict(self) -> dict[str, _Any]:
        return {
            "a": self.a,
            "b": self.b,
            "delta": self.delta,
            "low": self.low,
            "high": self.high,
            "excludes_zero": self.excludes_zero,
            "meets": self.meets,
            "reversed": self.reversed,
            "reason": self.reason,
        }


def contrast(a: str, b: str, records: _Mapping[str, _Sequence[_cal.EpisodeRecord]]) -> Contrast:
    """`paired_delta` on the two arms' scored episodes, with no provenance block."""
    left, right = _cal.scored(records.get(a, ())), _cal.scored(records.get(b, ()))
    empty = [arm for arm, cell in ((a, left), (b, right)) if not cell]
    if empty:
        return Contrast(
            a, b, None, None, None, reason=" and ".join(empty) + " has no scored episode"
        )
    try:
        found = _cal.paired_delta(left, right, resamples=RESAMPLES, seed=BOOTSTRAP_SEED)
    except ValueError as error:
        return Contrast(a, b, None, None, None, reason=str(error))
    return Contrast(a, b, found.point, found.low, found.high)


@_dc.dataclass(frozen=True)
class KnobResult:
    """One knob on one model: its status, the contrasts it was read on, and why.  `harder` is
    shape's: the width that was harder, when its contrast was computed."""

    knob: str
    model: str
    status: str
    contrasts: tuple[Contrast, ...] = ()
    reasons: tuple[str, ...] = ()
    void_arms: tuple[str, ...] = ()
    harder: str | None = None

    def as_dict(self) -> dict[str, _Any]:
        return {
            "knob": self.knob,
            "model": self.model,
            "status": self.status,
            "contrasts": [c.as_dict() for c in self.contrasts],
            "reasons": list(self.reasons),
            "void_arms": list(self.void_arms),
            "harder": self.harder,
        }


def knob_result(
    knob: Knob,
    model: str,
    arms: _Mapping[str, ArmResult],
    records: _Mapping[str, _Sequence[_cal.EpisodeRecord]],
) -> KnobResult:
    """The knob on one model, read only on complete arms that are not void."""
    incomplete = [arm for arm in knob.arms if arm not in arms or not arms[arm].complete]
    if incomplete:
        return KnobResult(
            knob.name,
            model,
            UNDECIDED,
            reasons=tuple(
                f"{arm} is not complete: "
                f"{arms[arm].episodes if arm in arms else 0} of its episodes were recorded"
                for arm in incomplete
            ),
        )
    void = [arm for arm in knob.arms if arms[arm].is_void]
    if void:
        return KnobResult(
            knob.name,
            model,
            VOID,
            void_arms=tuple(void),
            reasons=tuple(f"{arm} is void: " + "; ".join(arms[arm].void) for arm in void),
        )
    primary = contrast(knob.base, knob.top, records)
    contrasts = [primary]
    if knob.control is not None:
        second = (
            contrast(knob.base, knob.control, records)
            if knob.name == "shape"
            else contrast(knob.control, knob.top, records)
        )
        contrasts.append(second)
    missing = [c for c in contrasts if not c.computed]
    if missing:
        return KnobResult(
            knob.name,
            model,
            UNDECIDED,
            contrasts=tuple(contrasts),
            reasons=tuple(f"{c.a} against {c.b} cannot be computed: {c.reason}" for c in missing),
        )
    if knob.name == "shape":
        assert primary.delta is not None and contrasts[1].delta is not None
        harder = (knob.top if primary.delta > 0 else knob.base) if primary.delta else None
        control_small = abs(contrasts[1].delta) < DELTA_STAR - _EXACT
        bites = primary.two_sided and control_small
        reasons = (
            ()
            if bites
            else tuple(
                reason
                for reason, failed in (
                    (
                        f"{knob.base} against {knob.top} does not meet the rule either way",
                        not primary.two_sided,
                    ),
                    (
                        f"{knob.control} differs from {knob.base} by "
                        f"{abs(contrasts[1].delta):.3f}, not less than {DELTA_STAR}",
                        not control_small,
                    ),
                )
                if failed
            )
        )
        return KnobResult(
            knob.name,
            model,
            BITES if bites else DOES_NOT_BITE,
            contrasts=tuple(contrasts),
            reasons=reasons,
            harder=harder,
        )
    if all(c.meets for c in contrasts):
        return KnobResult(knob.name, model, BITES, contrasts=tuple(contrasts))
    if primary.reversed:
        return KnobResult(
            knob.name,
            model,
            TOP_EASIER,
            contrasts=tuple(contrasts),
            reasons=(f"{knob.top} is easier than {knob.base} by the rule",),
        )
    return KnobResult(
        knob.name,
        model,
        DOES_NOT_BITE,
        contrasts=tuple(contrasts),
        reasons=tuple(
            f"{c.a} against {c.b} does not meet the rule" for c in contrasts if not c.meets
        ),
    )


@_dc.dataclass(frozen=True)
class KnobOutcome:
    """What the probe says of a knob across both models."""

    knob: str
    outcome: str
    per_model: dict[str, KnobResult | None]
    reasons: tuple[str, ...]
    read_traces_first: bool = False

    def as_dict(self) -> dict[str, _Any]:
        return {
            "knob": self.knob,
            "outcome": self.outcome,
            "per_model": {
                model: None if result is None else result.as_dict()
                for model, result in self.per_model.items()
            },
            "reasons": list(self.reasons),
            "read_traces_first": self.read_traces_first,
        }


def knob_outcome(
    knob: Knob,
    per_model: _Mapping[str, KnobResult | None],
    models: _Sequence[str] = EXPECTED_MODELS,
) -> KnobOutcome:
    """Ships, does not ship, back for a decision, or waiting for a model not yet run.

    A knob ships when it bites on at least one model and on neither is the top easier by the same
    rule; shape, which has no easier direction, ships when it bites on one.  A knob void on one
    model is decided on the other alone.  Void on both, a void faults control, or a knob left
    undecided by a stop goes back for a decision with its cause; so does a knob that does not ship,
    which is redesigned or documented, and a wrong-direction result is read in the traces first."""
    ordered = {model: per_model.get(model) for model in models}
    present = {m: r for m, r in ordered.items() if r is not None}
    missing = [m for m, r in ordered.items() if r is None]

    def status(*wanted: str) -> list[str]:
        return [m for m, r in present.items() if r.status in wanted]

    if knob.control is not None and knob.name == "faults":
        control_void = [m for m, r in present.items() if knob.control in r.void_arms]
        if control_void:
            return KnobOutcome(
                knob.name,
                BACK,
                dict(ordered),
                tuple(
                    f"the faults control {knob.control} is void on {m}: "
                    + "; ".join(present[m].reasons)
                    for m in control_void
                ),
            )
    undecided = [f"undecided on {m}: " + "; ".join(present[m].reasons) for m in status(UNDECIDED)]
    void_all = bool(present) and not missing and len(status(VOID)) == len(present)
    if knob.name == "shape":
        biting = status(BITES)
        if biting:
            return KnobOutcome(
                knob.name,
                SHIPS,
                dict(ordered),
                tuple(f"bites on {m}; {present[m].harder} is the harder width" for m in biting),
            )
    else:
        easier = status(TOP_EASIER)
        if easier:
            return KnobOutcome(
                knob.name,
                DOES_NOT_SHIP,
                dict(ordered),
                tuple(f"the top is easier on {m}; read its traces before deciding" for m in easier),
                read_traces_first=True,
            )
    if missing:
        return KnobOutcome(
            knob.name,
            WAITING,
            dict(ordered),
            tuple(f"{m} has not run" for m in missing) + tuple(undecided),
        )
    if undecided:
        return KnobOutcome(knob.name, BACK, dict(ordered), tuple(undecided))
    if void_all:
        return KnobOutcome(
            knob.name,
            BACK,
            dict(ordered),
            tuple(f"void on {m}: " + "; ".join(r.reasons) for m, r in present.items()),
        )
    biting = status(BITES)
    if biting:
        return KnobOutcome(knob.name, SHIPS, dict(ordered), tuple(f"bites on {m}" for m in biting))
    return KnobOutcome(
        knob.name,
        DOES_NOT_SHIP,
        dict(ordered),
        ("bites on neither model" if len(present) > 1 else "bites on no model it was read on",),
    )


def analyse(
    models: _Mapping[str, _Mapping[str, _Any]],
    *,
    design: Design = DESIGN,
    expected: _Sequence[str] = EXPECTED_MODELS,
) -> dict[str, _Any]:
    """The outcome of every knob, from each model's records (`read_model_records`'s mapping:
    `records`, `tallies`, `reruns`, `facts`), as one JSON-ready mapping."""
    per_knob: dict[str, dict[str, KnobResult | None]] = {k.name: {} for k in KNOBS}
    arms_out: dict[str, dict[str, _Any]] = {}
    checks: dict[str, _Any] = {}
    for model in expected:
        given = models.get(model)
        if given is None:
            for knob in KNOBS:
                per_knob[knob.name][model] = None
            continue
        records = _by_arm(given["records"])
        facts = dict(given.get("facts") or {})
        results = arm_results(
            records,
            given.get("tallies") or {},
            model=model,
            design=design,
            rates=facts.get("rates"),
            reruns=given.get("reruns") or (),
        )
        arms_out[model] = {arm: _dc.asdict(result) for arm, result in results.items()}
        for knob in KNOBS:
            if all(arm in design.arms for arm in knob.arms):
                per_knob[knob.name][model] = knob_result(knob, model, results, records)
        if {"faults:f0", "history:t0"} <= set(design.arms):
            check = contrast("faults:f0", "history:t0", records)
            checks[model] = {
                **check.as_dict(),
                "note": "faults:f0 against history:t0, the same task but one "
                "system sentence: a check, and it decides nothing",
            }
    outcomes = [
        knob_outcome(knob, per_knob[knob.name], expected)
        for knob in KNOBS
        if all(arm in design.arms for arm in knob.arms)
    ]
    result: dict[str, _Any] = {
        "frozen_generator_hash": FROZEN_GENERATOR_HASH,
        "probe_seed_list_hash": _cal._seed_list_digest(design.probe_seeds),
        "models": list(expected),
        "facts": {m: dict(models[m].get("facts") or {}) for m in expected if m in models},
        "outcomes": [outcome.as_dict() for outcome in outcomes],
        "arms": arms_out,
        "check": checks,
    }
    # As the file holds it, so what is read back equals what was computed.
    normal: dict[str, _Any] = _json.loads(_json.dumps(result))
    return normal


def _fmt(value: _Any, digits: int = 3) -> str:
    if value is None:
        return "–"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _stops_at(episodes: int, threshold: float) -> int:
    """The fewest of `episodes` without a tool call that stop phase 1 under the share rule."""
    return next(n for n in range(episodes + 1) if n / episodes > threshold)


def phase1_disclosure(model: str, regated: _Mapping[str, _Any]) -> str:
    """The outcome's line for a model whose phase 1 was re-gated: what changed, when and why,
    with the counts, from the re-gate's record (`facts["phase1_regate"]`)."""
    episodes, threshold = int(regated["episodes"]), float(regated["threshold"])
    first = "; ".join(regated["original_reasons"])
    now = "; ".join(regated["reasons"]) or "no reason to stop"
    return (
        f"**Phase 1 re-gated ({model}).** Phase 1's no-call check on the base arms was changed "
        f"after this run's phase 1. As first registered it stopped the probe on any base-arm "
        f"episode without a tool call, and this run's phase 1 stopped on it ({first}). On "
        f"{regated['rule_date']}, after seeing that result, the check was changed to the cards' "
        f"own rule: stop when more than {threshold:.0%} of the {episodes} base episodes, pooled, "
        f"made no tool call ({_stops_at(episodes, threshold)} or more). The recorded phase 1 was "
        f"read again under it on {regated['when']}: {regated['no_call']} of {episodes} "
        f"made no tool call, so it {'passed' if regated['passed'] else 'failed'} ({now}). "
        f"No episode was run again. The reason recorded: {' '.join(str(regated['reason']).split())}"
    )


def render_outcome(result: _Mapping[str, _Any]) -> str:
    """The outcome as a page to read: each knob's outcome, each knob on each model, every arm's
    measures, the check, and what each model's run recorded."""
    lines = ["# The knob probe's outcome", ""]
    lines.append(
        f"Generator `{result['frozen_generator_hash']}`; probe seed list "
        f"`{result['probe_seed_list_hash']}`."
    )
    for model, facts in result["facts"].items():
        regated = facts.get("phase1_regate")
        if isinstance(regated, dict):
            lines += ["", "> " + phase1_disclosure(model, regated)]
    lines += ["", "## Each knob", "", "| knob | outcome | why |", "|---|---|---|"]
    for row in result["outcomes"]:
        why = "; ".join(row["reasons"])
        lines.append(f"| {row['knob']} | {row['outcome']} | {why} |")
    lines += [
        "",
        "## Each knob on each model",
        "",
        "| knob | model | status | contrast | Δ | 95% interval | meets the rule |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in result["outcomes"]:
        for model, found in row["per_model"].items():
            if found is None:
                lines.append(f"| {row['knob']} | {model} | not run | | | | |")
                continue
            if not found["contrasts"]:
                lines.append(
                    f"| {row['knob']} | {model} | {found['status']} | "
                    f"{'; '.join(found['reasons'])} | | | |"
                )
            for c in found["contrasts"]:
                interval = "–" if c["low"] is None else f"[{c['low']:.3f}, {c['high']:.3f}]"
                lines.append(
                    f"| {row['knob']} | {model} | {found['status']} | {c['a']} − {c['b']} | "
                    f"{_fmt(c['delta'])} | {interval} | "
                    f"{'yes' if c['meets'] else 'the other way' if c['reversed'] else 'no'} |"
                )
    for model, arms in result["arms"].items():
        facts = result["facts"].get(model, {})
        lines += ["", f"## {model}", ""]
        lines.append(
            f"Concurrency: {_fmt(facts.get('concurrency'))} episodes at once; "
            f"spent: {_fmt(facts.get('dollars'), 4)} dollars."
        )
        lines += [
            "",
            "| arm | episodes | complete | strict pass@1 | leaky pass@1 | no call | "
            "gave up after a fault | instrument rate | void | model calls | tokens | "
            "dollars | seconds (median) |",
            "|" + "---|" * 13,
        ]
        for arm, found in arms.items():
            m = found["measures"]
            gave_up = (
                f"{m['gave_up_after_fault']} ({m['gave_up_after_fault_share']:.3f})"
                if "gave_up_after_fault" in m
                else "–"
            )
            lines.append(
                f"| {arm} | {found['episodes']} of {found['planned']} | "
                f"{'yes' if found['complete'] else 'no'} | {_fmt(m.get('strict'))} | "
                f"{_fmt(m.get('leaky'))} | {_fmt(m.get('no_call_share'))} | {gave_up} | "
                f"{found['instrument_rate']:.3f} | {'; '.join(found['void']) or 'no'} | "
                f"{_fmt(m.get('model_calls_mean'), 2)} | {_fmt(m.get('tokens_mean'), 0)} | "
                f"{_fmt(m.get('dollars'), 4)} | {_fmt(m.get('episode_seconds_median'), 1)} |"
            )
        check = result["check"].get(model)
        if check is not None:
            lines += [
                "",
                f"Check (decides nothing): {check['a']} − {check['b']} = "
                f"{_fmt(check['delta'])}, interval [{_fmt(check['low'])}, "
                f"{_fmt(check['high'])}].",
            ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# a model's records, on disk
# ---------------------------------------------------------------------------

RECORDS_FILE = "episodes.jsonl"
TALLIES_FILE = "tallies.json"
RERUNS_FILE = "reruns.json"
FACTS_FILE = "facts.json"


def _write_json(path: _pathlib.Path, value: _Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(_json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _os.replace(tmp, path)


def _read_json(path: _pathlib.Path) -> _Any:
    return _json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write_model_records(
    folder: _pathlib.Path,
    records: _Iterable[_cal.EpisodeRecord],
    tallies: _Mapping[str, _Mapping[str, int]],
    *,
    reruns: _Sequence[_Mapping[str, _Any]],
    facts: _Mapping[str, _Any],
) -> None:
    """One model's probe in the four files `analyse` reads, whichever driver ran it."""
    folder.mkdir(parents=True, exist_ok=True)
    _cal.write_records(records, folder / RECORDS_FILE)
    _write_json(folder / TALLIES_FILE, {arm: dict(t) for arm, t in tallies.items()})
    _write_json(folder / RERUNS_FILE, [dict(entry) for entry in reruns])
    _write_json(folder / FACTS_FILE, dict(facts))


def read_model_records(folder: _pathlib.Path) -> dict[str, _Any]:
    """What `write_model_records` wrote, as `analyse` takes it."""
    return {
        "records": _cal.read_records(folder / RECORDS_FILE),
        "tallies": _read_json(folder / TALLIES_FILE) or {},
        "reruns": _read_json(folder / RERUNS_FILE) or [],
        "facts": _read_json(folder / FACTS_FILE) or {},
    }


def _model_of(folder: _pathlib.Path) -> str:
    records = _cal.read_records(folder / RECORDS_FILE)
    if not records:
        raise ValueError(f"{folder} holds no episode")
    models = {row.model for row in records}
    if len(models) != 1:
        raise ValueError(f"{folder} holds the records of {sorted(models)}; one model a folder")
    return models.pop()


def write_outcome(folder: _pathlib.Path, result: _Mapping[str, _Any]) -> None:
    _write_json(folder / "outcome.json", result)
    (folder / "outcome.md").write_text(render_outcome(result), encoding="utf-8")


# ---------------------------------------------------------------------------
# the one re-run a void arm may have
# ---------------------------------------------------------------------------


class RerunRefused(ValueError):
    """A re-run the pre-registration does not allow."""


def start_rerun(
    arm: str,
    result: ArmResult,
    *,
    cause: str,
    reruns: _Sequence[_Mapping[str, _Any]],
    folders: _Sequence[tuple[_pathlib.Path, _pathlib.Path]],
) -> dict[str, _Any]:
    """Set a void arm aside for its one re-run, and return the entry that records it.

    Allowed only for an arm void by its instrument rate (the server, the key or the provider failed,
    not the model), only once, and only with a cause written down.  Each of `folders` is a pair:
    where the arm's run folder is, and where it is kept instead; the next run of the probe then
    runs the arm again from nothing.  Anything else is a new pre-registration."""
    if not cause.strip():
        raise RerunRefused(
            "a re-run records its cause: say what failed (the server, the key or the provider)"
        )
    if any(str(entry.get("arm")) == arm for entry in reruns):
        raise RerunRefused(f"{arm} has had its one re-run; another is a new pre-registration")
    if not result.complete:
        raise RerunRefused(f"{arm} is not complete; finish the run before deciding it is void")
    if result.instrument_rate <= VOID_INSTRUMENT:
        raise RerunRefused(
            f"{arm} is not void by its instrument rate ({result.instrument_rate:.3f}, the limit "
            f"is {VOID_INSTRUMENT}); a re-run for any other cause is a new pre-registration"
        )
    for source, target in folders:
        if source.exists():
            if target.exists():
                raise RerunRefused(f"{target} already exists; it is not overwritten")
            target.parent.mkdir(parents=True, exist_ok=True)
            _shutil.move(str(source), str(target))
    return {
        "arm": arm,
        "cause": cause.strip(),
        "instrument_rate": result.instrument_rate,
        "instrument_failures": result.instrument_failures,
        "episodes": result.episodes,
        "kept_at": [str(target) for _, target in folders],
        "when": _now(),
    }


# ---------------------------------------------------------------------------
# the key
# ---------------------------------------------------------------------------


class KeyMissing(RuntimeError):
    """No key where the driver looked."""


def load_key(env_file: _pathlib.Path, variable: str = KEY_VAR) -> str:
    """The key from a `.env` file's `<variable>=` line, quotes taken off.  Never printed."""
    path = _pathlib.Path(env_file).resolve()
    if not path.is_file():
        raise KeyMissing(f"no {variable}: there is no file at {path}")
    for line in path.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and name.strip() == variable:
            key = value.strip().strip('"').strip("'")
            if key:
                return key
    raise KeyMissing(f"no {variable} line with a value in {path}")


# ---------------------------------------------------------------------------
# the gpt-5-nano driver
# ---------------------------------------------------------------------------


def _now() -> str:
    return _datetime.datetime.now(_datetime.UTC).isoformat(timespec="seconds")


def _say(message: str) -> None:
    print(message, flush=True)


def _refuse(sentence: str) -> int:
    print(f"error: {sentence}", file=_sys.stderr, flush=True)
    return 1


def card_rates() -> tuple[dict[str, float], str]:
    """gpt-5-nano's rates as its published card declares them, in dollars per million tokens,
    and the date they were read: the prices the cap is counted in."""
    from poisson_tasks import cards as _cards

    folder = next(card.folder for card in _cards.published() if card.name == "gpt-5-nano")
    path = folder / "artifact.json"
    provenance = _json.loads(path.read_text(encoding="utf-8"))["provenance"]
    entry = provenance["models"][0]
    return (
        {name: float(entry[name]) for name in _cal._RATE_FIELDS},
        str(provenance["rate_read_date"]),
    )


def probe_record(
    design: Design, *, model: str, base_url: str, extra: _Mapping[str, _Any]
) -> dict[str, _Any]:
    """The probe's record, written into the run folder before the first episode: the frozen
    generator's hash, both seed lists and their hashes, the arms and the settings, and what the
    driver adds (`extra`: a hosted model's rates, a served model's pin)."""
    return {
        "frozen_generator_hash": FROZEN_GENERATOR_HASH,
        "derivation": DERIVATION,
        "split": _cal.SPLIT,
        "phase1_seeds": list(design.phase1_seeds),
        "phase1_seed_list_hash": _cal._seed_list_digest(design.phase1_seeds),
        "probe_seeds": list(design.probe_seeds),
        "probe_seed_list_hash": _cal._seed_list_digest(design.probe_seeds),
        "arms": list(design.arms),
        "attempts": design.attempts,
        "phase1_attempts": design.phase1_attempts,
        "episodes_per_arm": design.episodes_per_arm,
        "model": model,
        "base_url": base_url,
        "pre_registered_endpoint": model == MODEL and base_url == BASE_URL,
        "decoding": dict(DECODING),
        "max_model_calls": MAX_MODEL_CALLS,
        "harness": _HARNESS,
        "package_version": _metadata.version("poisson-tasks"),
        "verifiers_version": _metadata.version("verifiers"),
        **dict(extra),
    }


_SETTLED = (
    "frozen_generator_hash",
    "derivation",
    "split",
    "phase1_seeds",
    "probe_seeds",
    "arms",
    "attempts",
    "phase1_attempts",
    "model",
    "base_url",
    "decoding",
    "max_model_calls",
    "harness",
)


def check_record(
    path: _pathlib.Path, record: _Mapping[str, _Any], invocation: _Mapping[str, _Any]
) -> dict[str, _Any]:
    """Write the record before the first episode, or check a folder's own against it: a resume
    on other settings is refused.  Each run of the driver is added to its `invocations`."""
    held = _read_json(path)
    if held is None:
        written = {**record, "written": _now(), "invocations": [dict(invocation)]}
        _write_json(path, written)
        return written
    differ = [name for name in _SETTLED if held.get(name) != record.get(name)]
    if differ:
        raise ValueError(
            f"{path.parent} holds a probe run with other settings ("
            + ", ".join(differ)
            + "); use a new folder"
        )
    held["invocations"] = [*held.get("invocations", []), dict(invocation)]
    _write_json(path, held)
    return dict(held)


def probe_plan(
    design: Design,
    seeds: _Sequence[int],
    attempts: int,
    *,
    model: str,
    base_url: str,
    rates: _Mapping[str, float],
    read_on: str,
    key_var: str,
) -> _Any:
    """A phase as the run engine's plan: the design's arms in its order, the seeds, the attempts,
    the model at its endpoint and prices, the cards' decoding and the 32-call cap."""
    from poisson_tasks import config as _config

    return _config.Plan(
        preset="knob-probe",
        arms=tuple(_run.spec_for(arm) for arm in design.arms),
        seeds=tuple(seeds),
        attempts=attempts,
        model=_config.ModelConfig(
            provider="openai",
            name=model,
            base_url=base_url,
            api_key_env=key_var,
            price=_config.PriceConfig(
                input=rates["input_rate"],
                cached_input=rates["cached_input_rate"],
                output=rates["output_rate"],
                read_on=read_on,
            ),
        ),
        decoding=_types.MappingProxyType(dict(DECODING)),
        max_model_calls=MAX_MODEL_CALLS,
    )


def _arm_rows(
    folder: _pathlib.Path, arm: str, model: str
) -> tuple[list[_cal.EpisodeRecord], dict[str, int]]:
    run_dir = folder / _run._arm_dir(arm)
    if not (run_dir / _cal.TRACES_FILE).exists():
        return [], {}
    return _cal.records_from_run(run_dir, model=model), _cal.read_tally(run_dir)


def _collect(
    folder: _pathlib.Path, design: Design, model: str
) -> tuple[dict[str, list[_cal.EpisodeRecord]], dict[str, dict[str, int]]]:
    records: dict[str, list[_cal.EpisodeRecord]] = {}
    tallies: dict[str, dict[str, int]] = {}
    for arm in design.arms:
        records[arm], tallies[arm] = _arm_rows(folder, arm, model)
    return records, tallies


def _progress(phase: str) -> _Callable[[_Mapping[str, _Any]], None]:
    seen: dict[str, _Any] = {"arm": None}

    def report(event: _Mapping[str, _Any]) -> None:
        done = int(event["episodes_done"])
        if event["arm"] != seen["arm"] or done % 60 == 0 or done == event["episodes_total"]:
            seen["arm"] = event["arm"]
            spend = event.get("spend")
            _say(
                f"[{phase}] {event['arm']}: {done} of {event['episodes_total']} episodes"
                + ("" if spend is None else f", ${spend:.4f} spent in this phase")
            )

    return report


def run_probe(
    folder: _pathlib.Path,
    *,
    cap: float,
    concurrency: int = CONCURRENCY,
    env_file: _pathlib.Path = _pathlib.Path(".env"),
    key_var: str = KEY_VAR,
    model: str = MODEL,
    base_url: str = BASE_URL,
    design: Design = DESIGN,
) -> int:
    """The gpt-5-nano probe into `folder`: phase 1, then the eighteen arms, then the outcome.

    Run again, it resumes: phase 1 is not repeated, and the run engine runs only what is owed.
    Returns 0 when every arm is complete, 2 when phase 1 failed, 4 when a stop left arms owed, and
    1 when it refused to start."""
    from poisson_tasks import providers as _providers
    from poisson_tasks import runs as _runs
    from poisson_tasks.config import ModelConfig

    if cap <= 0:
        return _refuse(f"the cap is ${cap}; give a cap above zero, in dollars")
    from poisson_tasks import _open_files

    try:
        # before the key is read or anything is written; the run engine makes the room
        _open_files.check(
            min(max(1, concurrency), max(design.episodes_per_arm, design.phase1_episodes_per_arm))
        )
    except _open_files.OpenFilesRefused as error:
        return _refuse(str(error))
    try:
        generator = check_generator(design.arms, design.probe_seeds[0])
    except GeneratorMoved as error:
        return _refuse(str(error))
    try:
        key = load_key(env_file, key_var)
    except KeyMissing as error:
        return _refuse(f"{error}; the probe reads the key from there")
    _os.environ[key_var] = key
    del key
    check = _providers.check_key(
        ModelConfig(provider="openai", name=model, base_url=base_url, api_key_env=key_var)
    )
    if check.status not in (_providers.ACCEPTED, _providers.NOT_CHECKABLE):
        return _refuse(
            f"{check.detail} (the key was read from {_pathlib.Path(env_file).resolve()})"
        )
    rates, read_on = card_rates()
    folder = _pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    invocation = {"when": _now(), "cap": cap, "concurrency": concurrency}
    try:
        check_record(
            folder / "record.json",
            probe_record(
                design,
                model=model,
                base_url=base_url,
                extra={"rates": rates, "rates_read": read_on},
            ),
            invocation,
        )
    except ValueError as error:
        return _refuse(str(error))
    _say(
        f"generator {generator} (frozen); probe seed list "
        f"{_cal._seed_list_digest(design.probe_seeds)}"
    )
    _say(
        f"{len(design.arms)} arms x {len(design.probe_seeds)} tasks x {design.attempts} attempts "
        f"= {len(design.arms) * design.episodes_per_arm} episodes, after phase 1's "
        f"{len(design.arms) * design.phase1_episodes_per_arm}; about ${ESTIMATE_DOLLARS} for "
        f"2,160 episodes, cap ${cap:.2f}, {concurrency} at once"
    )

    phase1_path = folder / "phase1.json"
    phase1 = _read_json(phase1_path)
    regated = None
    if isinstance(phase1, dict) and not phase1.get("passed"):
        regated = _read_json(folder / REGATE_FILE)
        if not isinstance(regated, dict):
            _say(
                "STOP: phase 1 failed in this folder, so the probe does not run: "
                + "; ".join(phase1.get("reasons", []))
            )
            return 2
        if not regated.get("passed"):
            _say(
                "STOP: phase 1 failed in this folder and its re-gate failed too, so the probe "
                "does not run: " + "; ".join(regated.get("reasons", []))
            )
            return 2
    if not isinstance(phase1, dict):
        plan1 = probe_plan(
            design,
            design.phase1_seeds,
            design.phase1_attempts,
            model=model,
            base_url=base_url,
            rates=rates,
            read_on=read_on,
            key_var=key_var,
        )
        where = _runs.RunFolder(path=folder / "phase1", name="phase1", status="new")
        result = _runs.run_plan(
            plan1,
            where,
            caps={"spend_usd": cap, "tokens": None},
            concurrency=concurrency,
            events=_progress("phase 1"),
        )
        spent = float(result.spend or 0.0)
        if result.verdict != "done":
            _write_json(
                folder / "status.json",
                {
                    "phase": 1,
                    "verdict": result.verdict,
                    "stop": result.stop_reason,
                    "spent": spent,
                    "owed": result.episodes_owed,
                },
            )
            _say(
                f"STOP: phase 1 stopped ({result.stop_reason}) with {result.episodes_owed} "
                f"episodes owed; ${spent:.4f} spent. Run the same command again to resume."
            )
            if result.first_error:
                _say(f"first error: {result.first_error}")
            return 4
        records, tallies = _collect(folder / "phase1", design, model)
        verdict = phase1_verdict(records, tallies, design=design)
        phase1 = {
            "passed": verdict.passed,
            "reasons": list(verdict.reasons),
            "spent": spent,
            "episodes": sum(len(rows) for rows in records.values()),
            "per_episode": list(verdict.bases.per_episode),
            "plumbing": verdict.plumbing,
            "tallies": tallies,
        }
        _write_json(phase1_path, phase1)
        if not verdict.passed:
            _say(f"STOP: phase 1 failed, so the probe stops here; ${spent:.4f} spent")
            for reason in verdict.reasons:
                _say(f"  {reason}")
            return 2
    if isinstance(regated, dict):
        _say(
            f"phase 1 passed on its re-gate of {regated['when']} ({regated['no_call']} of "
            f"{regated['episodes']} base episodes made no tool call; first gated: "
            + "; ".join(phase1.get("reasons", []))
            + f"): {phase1['episodes']} episodes, ${float(phase1['spent']):.4f}"
        )
    else:
        _say(f"phase 1 passed: {phase1['episodes']} episodes, ${float(phase1['spent']):.4f}")

    status = _read_json(folder / "status.json")
    if (
        isinstance(status, dict)
        and status.get("phase") == "probe"
        and status.get("verdict") == "done"
    ):
        # A finished probe is not run again: running it again would re-run the episodes that
        # failed for instrument reasons.  Only a re-run of a void arm reopens it (`rerun_void`).
        _say("the probe finished in this folder; nothing to run, the outcome is written again")
        spent, stop, first_error = float(status["spent"]), None, None
    else:
        plan = probe_plan(
            design,
            design.probe_seeds,
            design.attempts,
            model=model,
            base_url=base_url,
            rates=rates,
            read_on=read_on,
            key_var=key_var,
        )
        where = _runs.RunFolder(path=folder / "probe", name="probe", status="new")
        left = max(0.0, cap - float(phase1["spent"]))
        result = _runs.run_plan(
            plan,
            where,
            caps={"spend_usd": left, "tokens": None},
            concurrency=concurrency,
            events=_progress("probe"),
        )
        spent = float(phase1["spent"]) + float(result.spend or 0.0)
        stop, first_error = result.stop_reason, result.first_error
        _write_json(
            folder / "status.json",
            {
                "phase": "probe",
                "verdict": result.verdict,
                "stop": stop,
                "owed": result.episodes_owed,
                "spent": spent,
                "cap": cap,
            },
        )
    records, tallies = _collect(folder / "probe", design, model)
    reruns = _read_json(folder / RERUNS_FILE) or []
    concurrencies = sorted(
        {
            int(entry["concurrency"])
            for entry in (_read_json(folder / "record.json") or {}).get("invocations", [])
        }
    )
    facts = {
        "model": model,
        "base_url": base_url,
        "concurrency": concurrencies[-1],
        "concurrencies": concurrencies,
        "dollars": spent,
        "rates": rates,
        "stop": stop,
    }
    if isinstance(regated, dict):
        facts["phase1_regate"] = {
            name: regated[name]
            for name in (
                "when", "reason", "rule_date", "threshold", "no_call", "episodes", "passed",
                "reasons",
            )
        } | {"original_reasons": list(phase1.get("reasons", []))}
    write_model_records(
        folder / "records",
        [row for arm in design.arms for row in records[arm]],
        tallies,
        reruns=reruns,
        facts=facts,
    )
    outcome = analyse(
        {model: read_model_records(folder / "records")},
        design=design,
        expected=(model, *[m for m in EXPECTED_MODELS if m != model]),
    )
    write_outcome(folder, outcome)
    for row in outcome["outcomes"]:
        statuses = ", ".join(
            f"{r['status']} on {m}" for m, r in row["per_model"].items() if r is not None
        )
        _say(f"{row['knob']}: {statuses}; {row['outcome']}")
    failed = sum(r["instrument_failures"] for r in outcome["arms"][model].values())
    if failed:
        _say(
            f"{failed} episode(s) failed for instrument reasons; each counts in its arm's "
            "instrument rate"
        )
    void = [arm for arm, r in outcome["arms"][model].items() if r["void"]]
    if void:
        _say(
            f"void: {', '.join(void)}; an arm void by its instrument rate may be run once more "
            "(rerun-void)"
        )
    _say(f"spent ${spent:.4f} of the ${cap:.2f} cap; outcome in {folder / 'outcome.md'}")
    if stop is not None:
        complete = [a for a, r in outcome["arms"][model].items() if r["complete"]]
        _say(
            f"STOPPED ({stop}): {len(complete)} of {len(design.arms)} arms complete; the "
            "knobs without both arms are undecided. Run the same command again to resume."
        )
        if first_error:
            _say(f"first error: {first_error}")
        return 4
    return 0


def rerun_void(
    folder: _pathlib.Path, arm: str, cause: str, *, model: str = MODEL, design: Design = DESIGN
) -> int:
    """Set a void arm of a gpt-5-nano run aside for its one re-run; `run` then runs it again."""
    folder = _pathlib.Path(folder)
    if arm not in design.arms:
        return _refuse(f"{arm} is not one of the probe's arms")
    records, tallies = _collect(folder / "probe", design, model)
    reruns = list(_read_json(folder / RERUNS_FILE) or [])
    result = arm_results(records, tallies, model=model, design=design, reruns=reruns)[arm]
    source = folder / "probe" / _run._arm_dir(arm)
    try:
        entry = start_rerun(
            arm,
            result,
            cause=cause,
            reruns=reruns,
            folders=[(source, folder / "void" / f"{_run._arm_dir(arm)}-1")],
        )
    except RerunRefused as error:
        return _refuse(str(error))
    _write_json(folder / RERUNS_FILE, [*reruns, entry])
    status = _read_json(folder / "status.json") or {}
    _write_json(folder / "status.json", {**status, "verdict": "rerun"})
    _say(f"{arm} is set aside in {entry['kept_at'][0]}; run the probe again to re-run it once")
    return 0


# ---------------------------------------------------------------------------
# the one re-gate a failed phase 1 may have
# ---------------------------------------------------------------------------

REGATE_FILE = "phase1-regate.json"
"""Where a folder's re-gate is recorded, beside the first verdict (`phase1.json`)."""


def regate_phase1(folder: _pathlib.Path, reason: str, *, design: Design = DESIGN) -> int:
    """Read a failed phase 1's recorded episodes again under the amended no-call clause.

    Runs no episode and makes no call: it reads the folder's phase 1 traces, gates them with
    `phase1_verdict`, and writes the result to `REGATE_FILE`, with the first verdict copied
    beside it; `phase1.json` is left as it is.  Refused without a reason, a second time, on a
    folder with no phase 1 verdict or one that passed, on a folder of another design, and when the
    episodes found are not the ones the first verdict read.  Returns 0 when the re-gate passes
    (`run` then goes on in the folder), 2 when it fails (the folder is final), 1 when refused."""
    folder = _pathlib.Path(folder)
    if not reason.strip():
        return _refuse("a re-gate records its reason: say why phase 1 is read again")
    held = _read_json(folder / "record.json")
    if not isinstance(held, dict):
        return _refuse(
            f"{folder} holds no probe run (no record.json); there is no phase 1 to re-gate"
        )
    phase1 = _read_json(folder / "phase1.json")
    if not isinstance(phase1, dict):
        return _refuse(
            f"{folder} holds no phase 1 verdict (no phase1.json): phase 1 did not finish, and the "
            "same run command resumes it"
        )
    earlier = _read_json(folder / REGATE_FILE)
    if earlier is not None:
        when = earlier.get("when") if isinstance(earlier, dict) else None
        return _refuse(f"phase 1 in {folder} was re-gated on {when}; a folder is re-gated once")
    if phase1.get("passed"):
        return _refuse(f"phase 1 passed in {folder}; there is nothing to re-gate")
    model, base_url = str(held.get("model")), str(held.get("base_url"))
    expected = probe_record(design, model=model, base_url=base_url, extra={})
    differ = [name for name in _SETTLED if held.get(name) != expected.get(name)]
    if differ:
        return _refuse(
            f"{folder} holds a probe run with other settings than this design's ("
            + ", ".join(differ)
            + ")"
        )
    records, tallies = _collect(folder / "phase1", design, model)
    verdict = phase1_verdict(records, tallies, design=design)
    episodes = sum(len(rows) for rows in records.values())
    if episodes != phase1.get("episodes") or list(verdict.bases.per_episode) != phase1.get(
        "per_episode"
    ):
        return _refuse(
            f"the phase 1 episodes in {folder} are not the ones its verdict read ({episodes} "
            f"found, {phase1.get('episodes')} gated); it is not re-gated"
        )
    entry = {
        "when": _now(),
        "reason": reason.strip(),
        "rule_date": PHASE1_NO_CALL_DATE,
        "threshold": PHASE1_NO_CALL,
        "passed": verdict.passed,
        "reasons": list(verdict.reasons),
        "no_call": verdict.bases.no_call,
        "episodes": verdict.bases.episodes,
        "per_episode": list(verdict.bases.per_episode),
        "plumbing": verdict.plumbing,
        "original": {
            "passed": phase1.get("passed"),
            "reasons": phase1.get("reasons"),
            "spent": phase1.get("spent"),
            "episodes": phase1.get("episodes"),
        },
    }
    _write_json(folder / REGATE_FILE, entry)
    _say("phase 1 first gated: failed: " + "; ".join(phase1.get("reasons", [])))
    _say(
        f"phase 1 re-gated under the share rule of {PHASE1_NO_CALL_DATE} (stop above "
        f"{PHASE1_NO_CALL} of the base episodes): {verdict.bases.no_call} of "
        f"{verdict.bases.episodes} made no tool call; "
        + ("passed" if verdict.passed else "failed: " + "; ".join(verdict.reasons))
    )
    _say(f"both verdicts are kept: phase1.json and {REGATE_FILE}; no episode was run")
    if verdict.passed:
        _say("run the same run command, with the same cap, to go on with the probe in this folder")
        return 0
    _say("STOP: the re-gate failed too; phase 1 is final for this folder")
    return 2


# ---------------------------------------------------------------------------
# the command line (a module, not a command of the tool)
# ---------------------------------------------------------------------------


def build_parser() -> _argparse.ArgumentParser:
    parser = _argparse.ArgumentParser(
        prog="python -m poisson_tasks.knob_probe",
        description="The knob probe: gpt-5-nano's run, a void arm's one re-run, a failed phase "
        "1's one re-gate, and the outcome from both models' records (see the module docstring).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="phase 1, the eighteen arms and the outcome; resumes")
    p.add_argument(
        "--folder",
        type=_pathlib.Path,
        required=True,
        help="the run's folder: its record, both phases, the records and the outcome",
    )
    p.add_argument("--cap", type=float, required=True, help="the spend cap, in dollars")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY)
    p.add_argument(
        "--env-file",
        type=_pathlib.Path,
        default=_pathlib.Path(".env"),
        help=f"the file the key is read from, as a {KEY_VAR}= line",
    )
    p.add_argument("--base-url", default=BASE_URL, help=_argparse.SUPPRESS)
    p.add_argument("--model", default=MODEL, help=_argparse.SUPPRESS)
    p = sub.add_parser("rerun-void", help="set a void arm aside for its one re-run")
    p.add_argument("--folder", type=_pathlib.Path, required=True)
    p.add_argument("--arm", required=True)
    p.add_argument(
        "--cause", required=True, help="what failed: the server, the key or the provider"
    )
    p.add_argument("--model", default=MODEL, help=_argparse.SUPPRESS)
    p = sub.add_parser(
        "regate", help="read a failed phase 1 again under the share rule, once; runs nothing"
    )
    p.add_argument("--folder", type=_pathlib.Path, required=True)
    p.add_argument("--reason", required=True, help="why phase 1 is read again, recorded with it")
    p = sub.add_parser("analyse", help="the outcome from one or both models' records")
    p.add_argument(
        "--records",
        type=_pathlib.Path,
        action="append",
        required=True,
        help="a folder of one model's records (episodes.jsonl, tallies.json, ...)",
    )
    p.add_argument("--out", type=_pathlib.Path, required=True)
    return parser


def main(argv: _Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(_sys.argv[1:] if argv is None else argv))
    if args.command == "run":
        return run_probe(
            args.folder,
            cap=args.cap,
            concurrency=args.concurrency,
            env_file=args.env_file,
            model=args.model,
            base_url=args.base_url,
        )
    if args.command == "rerun-void":
        return rerun_void(args.folder, args.arm, args.cause, model=args.model)
    if args.command == "regate":
        return regate_phase1(args.folder, args.reason)
    if args.command == "analyse":
        models: dict[str, dict[str, _Any]] = {}
        for folder in args.records:
            models[_model_of(folder)] = read_model_records(folder)
        expected = (*EXPECTED_MODELS, *[m for m in models if m not in EXPECTED_MODELS])
        result = analyse(models, expected=expected)
        write_outcome(args.out, result)
        for row in result["outcomes"]:
            _say(f"{row['knob']}: {row['outcome']}")
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    _sys.exit(main())
