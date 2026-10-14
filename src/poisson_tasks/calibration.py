"""Difficulty calibration: what each difficulty level is worth to a named model.

The invariants are CAL1 to CAL23, tested in `tests/test_cal_calibration.py`, and CAL24 with
the phase 1 plumbing gate, tested in `tests/test_cal_calibration_fix.py`; each test's name
carries the invariant it checks.  A cell is `(arm, model)`; its records are `n` independent
attempts at each of `S` generated tasks, and its numbers are pass@1 and pass@k under the
export's own strict reward (X4), with the leaky predicate beside them, a task-clustered
interval (CAL9), a paired difference to the neighbouring level (CAL10, CAL11) and the cost
the attempts burned (CAL15).

**This is not a blind calibration of the instrument.**  That plants bugs in a scripted policy
and asks whether the instrument detects them.  This asks what a level is worth to a model, and
it shares a word with that and no arithmetic.

**A21, the pilot's distinct-instance rule, does not apply to this module.**  The Proofload
pilot salts its replicates apart so that no two are the same instance.  Here the opposite is
required: pass@k is defined over repeated attempts at the same task, so a cell's `n`
attempts share `task_id`, `arm_id`, `seed`, `scenario_hash` and `generator_hash` (CAL3), and
`check_attempts` refuses a cell whose attempts were salted apart.  Carrying the pilot's rule
across computes something that is not pass@k.

**Tasks is standalone.**  Nothing here imports Proofload or the Prove-gated adapter, and the
whole module works with Proofload unimportable (CAL22).  The instrument labels the adapter
would assign are read from the signals the trace already carries instead
(`label_from_signals`), and every published number recomputes from the per-episode records with
no model and no network (CAL19).

Shapes decided here, where the tests leave them open
------------------------------------------------------

* **A cell is a plain sequence of `EpisodeRecord`** and every estimator takes one.  Records
  are grouped into per-task blocks in first-seen order, so a records file recomputes to the
  same bytes.
* **The bootstrap is task-decomposable.**  Resampling tasks with each task's block carried
  whole and recomputing a mean-over-tasks statistic is the mean of the per-task values over
  the resampled indices; `cluster_bootstrap` computes it that way and refuses a statistic
  that is not a mean over tasks.  The draw is `random.Random(seed)` with one `randrange(S)`
  per resampled task, and the quantile rule is the smallest value whose cumulative share
  reaches the quantile, which is the rule that reproduces the enumerated distribution
  exactly.
* **The seed list is derived, not typed.**  Sixty 32-bit seeds from a named derivation
  (`_SEED_DERIVATION`), sorted; the derivation is the declaration and the list is published
  in the artifact with its hash (CAL1).  The seeds come from the eval split.
* **The pilot's seeds are a registry.**  The pilot's stages declare *salts* and Proofload
  derives their seeds at run time, which this module cannot import.  `pilot_seeds` returns
  what the pilot has registered, and today that is nothing: CAL1's disjointness holds in the
  other direction, by the pilot's salt vetting refusing a salt whose seeds meet the published
  sixty.
* **`instrument_rate` reads the tally first.**  A resume drops failed episodes and re-runs
  them, so the records under-count what happened; the tally written at the moment of failure
  is the count, and the denominator is the scored records plus the tally.
* **The runner is the wheel's in-process eval body** with two things between episodes that
  `run_eval` cannot do: the budget check before each episode (CAL20) and the tally at the
  moment of failure.  Its config is `run_config_for`'s, which differs from the
  documented command in exactly the seed list, `-r` and the declared sampling (CAL21), and
  its checkpoint is the wheel's own `traces.jsonl` plus `resume.load` (CAL23).
* **`run_cell` is `run_arm` for any design** (FD3): the seeds, the attempts and the decoding
  are the caller's instead of the published design's, and everything else is the same
  runner, the same run folder name and the same config, so `run_arm` is `run_cell` with
  `seed_list(spec)`, `N` and `DECODING`.  A decoding field declared `"not sent"` is left out
  of the config, so the request carries the provider's own default for it.
* **A dollar figure needs a rate.**  A model whose provenance carries no rate publishes
  `null` dollars, not zero: a locally served model costs compute units, not dollars.
* **A cell that measures whether the model starts refuses to publish (CAL24).**  Model A's
  first card had 72.5% of its episodes end on a first reply that asked for the record id
  and the entry code and called no tool, which is a statement about the prompt and not
  about the level.  Every cell carries the share of scored episodes that made no tool call
  and the share that started and stopped short of the structural minimum; the two are
  disjoint.  Above `NO_CALL_THRESHOLD` of the first, the cell refuses, the way CAL16
  refuses above the instrument threshold.  Stopping short stays a printed column and not a
  gate: giving up partway through a long chain is a difficulty result.
* **Phase 1 is a plumbing gate, not a sample (`plumbing_gate`).**  Every episode scores, no
  instrument label and no tally, every episode makes at least one tool call, and at least
  half reach their arm's structural minimum.  The first two conditions alone passed a phase
  1 whose five of six episodes never called a tool.
* **Knob D's ordering is published on both predicates.**  Every depth arm offers the whole
  eight-stage ladder, so below the top level the model can carry the record past the goal
  (`overshoot`) and strict fails it; at the top level no stage lies above the goal.  Strict
  at the lower levels therefore includes a stop-at-the-goal test the top level cannot have,
  and leaky, which measures reaching the goal at every level, is shown beside it.  Strict
  stays the headline.
* **The two call counts are named for what they count.**  A record's `sampled_calls` is the
  export's metric of that name, the number of tool calls, and its `turns` is
  `trace.num_turns`, the number of model calls.  The record keeps the tests' field names;
  the artifact publishes `tool_calls`, `model_calls` and `model_calls_median`.
* **`docs/calibration.md` is one document with these sections in this order:** the level
  tables per knob, the instrument arms, cost, adjacent levels, ordering, provenance.
  The control arms appear only under the instrument heading.
* **A figure that was not recorded is missing, never zero.**  A record carries the episode's
  time and its first request's size only when the trace measured them
  (`_time_from_trace`); a cell's time figures are over the scored episodes that recorded
  them and are `None` when none did, and the card prints *not recorded*.  Both published
  cards were run before time was kept, so every time figure on them is missing.
* **Time is printed and never compared.**  Seconds belong to the serving and its load as
  much as to the level, so the card prints the run's concurrency wherever it prints
  seconds.  No pair, ordering or verdict reads a time figure, and `concurrency` is not
  among the fields two cards must share (`_COMPARABLE`).
"""

from __future__ import annotations

import asyncio as _asyncio
import dataclasses as _dc
import datetime as _datetime
import functools as _functools
import hashlib as _hashlib
import importlib.metadata as _metadata
import json as _json
import math as _math
import pathlib as _pathlib
import random as _random
import statistics as _statistics
import time as _time
import types as _types
import urllib.parse as _urlparse
from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from typing import Any as _Any
from typing import cast as _cast

from poisson_tasks.arms import DEFAULT_GENERATOR_VERSION as _DEFAULT_GENERATOR_VERSION
from poisson_tasks.arms import arm_from_id as _arm_from_id
from poisson_tasks.engine import EngineSpec as _EngineSpec
from poisson_tasks.engine import engine_hash as _engine_hash
from poisson_tasks.export import MEASURED_HARNESS as _MEASURED_HARNESS
from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.knobs import _render_arm_id
from poisson_tasks.knobs import arm_id as _arm_id
from poisson_tasks.knobs import levels as _levels
from poisson_tasks.tasks import generate as _generate

__all__ = [
    # records and the arithmetic (CAL6 to CAL16)
    "EpisodeRecord",
    "scored",
    "instrument_rate",
    "pass_at_1",
    "pass_at_k",
    "cluster_bootstrap",
    "paired_delta",
    "PairedDelta",
    "call_pair",
    "TOO_SMALL",
    "DISTINGUISHABLE",
    "saturated",
    "ordering",
    "OrderingReport",
    # the artifact and the two renderings (CAL14, CAL17, CAL18, CAL19)
    "Provenance",
    "Artifact",
    "build_artifact",
    "render_document",
    "render_readme_lines",
    "render_combined_document",
    "agreement_rows",
    "write_artifact",
    "read_records",
    "write_records",
    "dollars",
    "INSTRUMENT_TABLE_HEADING",
    "HEADLINE_PREDICATE",
    "NO_CALL_THRESHOLD",
    # phase 1's plumbing gate
    "plumbing_gate",
    "PlumbingVerdict",
    # what runs (CAL1 to CAL5, CAL20 to CAL23)
    "seed_list",
    "pilot_seeds",
    "arm_specs",
    "check_attempts",
    "check_decoding",
    "within_budget",
    "BudgetVerdict",
    "STOP_REASONS",
    "EpisodeSignals",
    "label_from_signals",
    "record_instrument",
    "read_tally",
    "owed_after_interrupt",
    "run_config_for",
    "config_difference",
    "run_arm",
    "run_cell",
    "RunOutcome",
    "records_from_run",
    # cards for any plan (FD4)
    "card_from_run",
    "RunCard",
    "card_verdict",
    "CardVerdict",
    "card_claims",
    "Claims",
    "comparable",
    "Comparison",
    "render_side_by_side",
]

# ---------------------------------------------------------------------------
# the declared design: every number fixed before any run, in one place
# ---------------------------------------------------------------------------

S = 60
"""Seeds per cell."""
N = 5
"""Attempts per task."""
DELTA_STAR = 0.15
"""The resolution, in pass-rate points, declared before any run."""
K_VALUES = (1, 2, 5)
"""The `k` values on the card; every `k <= n` goes in the artifact."""
SPLIT = "eval"
"""Calibrate on the eval split."""
BOOTSTRAP_RESAMPLES = 2000
"""CAL9's resample count."""
BOOTSTRAP_SEED = 20260922
"""CAL9's RNG seed, carried in the artifact so the interval recomputes byte for byte."""
SATURATION_LOW = 0.05
SATURATION_HIGH = 0.95
"""CAL12's inclusive bounds."""
INSTRUMENT_THRESHOLD = 0.02
"""CAL16's instrument-rate gate.  Declared here because a cell that exceeds it refuses to
publish.  Nothing measured supports the number in advance; phase 1 is where it is first read
against a real rate."""
NO_CALL_THRESHOLD = 0.10
"""CAL24's gate: a cell in which more than this share of scored episodes made no tool call
refuses to publish, because it measures whether the model starts and not the level.  Declared
before the rerun; after the prompt fix the probe showed 0 of 16."""
MODEL_A = "gpt-5-nano-2025-08-07"
"""Model A, pinned to a dated snapshot."""
DECODING: dict[str, _Any] = {
    "temperature": 1.0,
    "top_p": 1.0,
    "reasoning_effort": "low",
    "max_tokens": 2048,
}
"""The declared decoding (CAL5): every `SamplingConfig` field pinned, and not deterministic.
Temperature 1.0 is the value the reasoning family accepts; whether the endpoint honours it at
all is an open question, measured for cents in phase 1.  The limit is declared
under `SamplingConfig`'s field name and sent as `max_completion_tokens` (`run_config_for`)."""
DEFAULT_BUDGET: dict[str, _Any] = {"tokens": 100_000_000, "wall_clock_seconds": 12 * 3600}
"""The stop's declared limits (CAL20): tokens and wall clock; the third limit is the
provider saying out of credit, which is read from the episode and needs no number."""
GENERATOR_VERSION = _DEFAULT_GENERATOR_VERSION
"""The generator version a card's arms are generated at: the one a user gets."""
TASKSET_ID = "poisson-tasks"
DOCUMENTED_SEEDS = (404, 55, 2121)
"""The seed list on the documented one-liner in `docs/verifiers-export.md` (CAL21)."""
D_R = 2
"""Knob R's fixed chain depth (`knobs.py`): a distractor arm's minimum calls."""

TOO_SMALL = "too small for this design to call"
DISTINGUISHABLE = "distinguishable"
HEADLINE_PREDICATE = "strict"
INSTRUMENT_TABLE_HEADING = "## Instrument arms (control arms, not difficulty levels)"

STOP_REASONS = ("tokens", "wall_clock", "provider_exhausted")
"""The run stops on whichever arrives first."""

# The task layer's closed outcome vocabulary (`tasks.py`), split into instrument and system.
INSTRUMENT_LABELS = frozenset({"verifier_error", "replay_mismatch", "api_error", "wall_timeout"})
SYSTEM_LABELS = frozenset(
    {"malformed_call", "turn_limit", "overshoot", "wrong_state", "collateral_mutation", "passed"}
)
OUTCOME_LABELS = INSTRUMENT_LABELS | SYSTEM_LABELS
_PASSED = "passed"
_OVERSHOOT = "overshoot"

# The wheel's four SamplingConfig fields.  Each defaults to `None` in the wheel and `wire_args`
# drops it, so an unset field is absent from the request and the provider's default applies.
SAMPLING_FIELDS = ("temperature", "top_p", "reasoning_effort", "max_tokens")
# The settings file's word for a decoding field the run leaves out (`config.py`): the field is
# then not in the config and not in any request, and the provider's own default applies.
_NOT_SENT = "not sent"

# What a locally served model's provenance has to carry beyond `kind`: the same weights
# served differently give different numbers.  A model the user serves (`self_served`: an Ollama
# or vLLM server of their own) carries its endpoint and what the server reported about itself,
# which pins less than `local` does, and the card says so.
SERVING_KINDS = ("hosted", "local", "self_served")
SERVING_FIELDS_LOCAL = ("stack", "stack_version", "flags", "gpu", "revision")
_SELF_SERVED_PROVIDERS = ("ollama", "vllm")
_RATE_FIELDS = ("input_rate", "cached_input_rate", "output_rate")

# The two control arms per knob (`knobs.py`), the same four `tests/test_tg_m5_standalone.py`
# parameterises over.  A control pair names two levels and is not derivable from the axis,
# which is why these are declared and the plain arms are not.
D_CONTROLS = ((1, 8), (2, 5))
R_CONTROLS = ((0, 8), (2, 14))

TALLY_FILE = "instrument-tally.jsonl"
"""The append-only instrument tally.  Deliberately not `traces.jsonl`, which `resume.load`
rewrites."""
TRACES_FILE = "traces.jsonl"
RECORDS_FILE = "episodes.jsonl"
_PLAN_FILE = "plan.json"
_LEDGER_FILE = "spend.jsonl"
_LOG_FILE = "run.log"
"""What a run folder holds beside its arm folders (`runs.run_plan` writes them): the plan a card
is measured under, the ledger of what the run paid, and the run's own log."""

_DEPTH = "depth"
_DISTRACTOR = "distractor"
_KNOBS = (_DEPTH, _DISTRACTOR)

# The knobs whose records get the replay check (`_replay_agrees`): the ones whose tool
# messages are not the engine's answers to the calls as made, because the tools are served
# under names the engine does not know (similarity) or planned failures are answered in front
# of it (faults), or whose answers are numbered from after earlier tool work the prompt holds
# (history), or served under read copies' names the engine does not know (block), or refused
# by the argument check in front of it (arguments), or answered with the parts of a split
# entry code in front of it (spread), so that the tool server and the verifier applying any
# of these differently, or starting their numbers apart, is a failure the records would
# otherwise never show.
_REPLAY_CHECKED = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")
_REPLAY_MISMATCH = "replay_mismatch"
# The own-tools provenance kind, and the keys its block carries (own-tools spec §9).
_OWN_KIND = "own"
_OWN_TOOLS_KEYS = (
    "kind", "name", "tools", "source_format", "file_digest", "intents", "flows", "generator",
)
# The status a planned failure answers with, as the faults knob's system prompt names it.
_UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# records
# ---------------------------------------------------------------------------


@_dc.dataclass(frozen=True, kw_only=True)
class EpisodeRecord:
    """One scored episode: the compact row a published card is recomputed from.

    `strict` is `ExportTask.strict == 1.0` (X4) and `leaky` is the export's `leaky_pass`
    metric; `label` is the task layer's outcome label, instrument or system.  The four token
    fields are `vf.Usage`'s: `prompt_tokens` excludes cache reads and `cached_input_tokens`
    carries them; `reasoning_tokens` is a subset of `completion_tokens` and is never added
    again.

    `sampled_calls` is the number of **tool calls** the model made (the export's metric of
    that name) and `turns` is the number of **model calls** (`trace.num_turns`).  The names
    are the tests' and stay; the artifact publishes them as `tool_calls` and `model_calls`.

    The five fields after `cost` are the episode's time and its first request's size, read
    from the trace (`records_from_run`); each is `None` when it was not recorded, and a
    figure that was not recorded is left out of the written line.  `episode_seconds` is the
    agent phase from start to end, `model_seconds` and `harness_seconds` are its two parts,
    `setup_seconds` is the tool server's start, and `first_request_prompt_tokens` is what the
    model was sent before its first move, cache reads included.

    `gave_up_after_fault` is the faults knob's: whether the episode received an `unavailable`
    from a tool and never called that tool again, `None` on an arm that plans no failure, and
    then left out of the written line too.
    """

    task_id: str
    arm_id: str
    model: str
    seed: int
    attempt: int
    strict: bool
    leaky: bool
    label: str
    turns: int
    sampled_calls: int
    prompt_tokens: int
    cached_input_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost: float | None = None
    episode_seconds: float | None = None
    model_seconds: float | None = None
    harness_seconds: float | None = None
    setup_seconds: float | None = None
    first_request_prompt_tokens: int | None = None
    gave_up_after_fault: bool | None = None

    def __post_init__(self) -> None:
        if self.label not in OUTCOME_LABELS:
            raise ValueError(
                f"{self.label!r} is not an outcome label; the vocabulary is closed: "
                + ", ".join(sorted(OUTCOME_LABELS))
            )
        if self.strict != (self.label == _PASSED):
            raise ValueError(
                f"strict is {self.strict} but the label is {self.label!r}: the strict "
                "indicator is 1.0 exactly when the strict label is `passed`"
            )
        if self.strict and not self.leaky:
            raise ValueError("a strict pass is a leaky pass: strict=True needs leaky=True")
        if self.label in INSTRUMENT_LABELS and self.leaky:
            raise ValueError("an instrument failure is not a pass: leaky must be False")
        for name in ("attempt", "turns", "sampled_calls", "prompt_tokens",
                     "cached_input_tokens", "completion_tokens", "reasoning_tokens"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} is negative")
        if self.reasoning_tokens > self.completion_tokens:
            raise ValueError("reasoning tokens are a subset of completion tokens")
        for name in _OPTIONAL_FIELDS:
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} is negative")

    @staticmethod
    def to_json(row: EpisodeRecord) -> str:
        """The wire format: one JSON object per line, keys sorted.  A time or first-request
        figure that was not recorded is left out, and so is `gave_up_after_fault` on an arm
        that plans no failure, so a record written before those fields existed writes back as
        the line it was; `cost` is always written."""
        line = _dc.asdict(row)
        for name in _LEFT_OUT_WHEN_NONE:
            if line[name] is None:
                del line[name]
        return _json.dumps(line, sort_keys=True)

    @staticmethod
    def from_json(line: str) -> EpisodeRecord:
        return EpisodeRecord(**_json.loads(line))


_SECONDS_FIELDS = ("episode_seconds", "model_seconds", "harness_seconds", "setup_seconds")
_OPTIONAL_FIELDS = (*_SECONDS_FIELDS, "first_request_prompt_tokens")
"""The record's fields that a trace may not have measured: `None` in the record and absent
from its written line."""
_LEFT_OUT_WHEN_NONE = (*_OPTIONAL_FIELDS, "gave_up_after_fault")
"""Every field a written line leaves out when it is `None`: the unmeasured ones, and the
faults knob's verdict on an arm that plans no failure."""

Cell = _Sequence[EpisodeRecord]


def _blocks(cell: Cell) -> list[list[EpisodeRecord]]:
    """The cell's records grouped by task, in first-seen order.

    CAL3's shape is checked on the way: the records of one task share its seed, arm and
    model, or they are not attempts at one task.
    """
    grouped: dict[str, list[EpisodeRecord]] = {}
    for row in cell:
        block = grouped.setdefault(row.task_id, [])
        if block and (block[0].seed, block[0].arm_id, block[0].model) != (
            row.seed, row.arm_id, row.model
        ):
            raise ValueError(
                f"the records of task {row.task_id} do not share one seed, arm and model; "
                "attempts are attempts at one task"
            )
        block.append(row)
    return list(grouped.values())


def scored(cell: Cell) -> list[EpisodeRecord]:
    """CAL16: an episode carrying an instrument label leaves the denominator."""
    return [row for row in cell if row.label not in INSTRUMENT_LABELS]


def instrument_rate(cell: Cell, tally: _Mapping[str, int] | None = None) -> float:
    """The share of attempts that failed for instrument reasons.

    Where a tally exists it is the count, because a resume has re-run what failed and
    the records alone under-count.  The denominator is the scored records plus the failures,
    which is every attempt that ran.
    """
    labelled = sum(1 for row in cell if row.label in INSTRUMENT_LABELS)
    failures = max(labelled, sum(tally.values())) if tally else labelled
    attempts = (len(cell) - labelled) + failures
    return failures / attempts if attempts else 0.0


# ---------------------------------------------------------------------------
# the estimators (CAL6 to CAL8)
# ---------------------------------------------------------------------------


def _block_rate(block: _Sequence[EpisodeRecord], key: _Callable[[EpisodeRecord], bool]) -> float:
    return sum(1 for row in block if key(row)) / len(block)


def _block_pass_at_k(
    block: _Sequence[EpisodeRecord], k: int, key: _Callable[[EpisodeRecord], bool]
) -> float:
    """CAL7's unbiased estimator for one task: `1 - C(n-c, k)/C(n, k)`."""
    n = len(block)
    if k < 1:
        raise ValueError(f"pass@{k} needs k >= 1")
    if k > n:
        raise ValueError(
            f"pass@{k} needs k <= n, and task {block[0].task_id} has n = {n} scored attempts"
        )
    c = sum(1 for row in block if key(row))
    return 1.0 - _math.comb(n - c, k) / _math.comb(n, k)


def _strict(row: EpisodeRecord) -> bool:
    return row.strict


def _leaky(row: EpisodeRecord) -> bool:
    return row.leaky


def _mean(values: _Sequence[float]) -> float:
    if not values:
        raise ValueError("a cell with no scored task has no rate")
    return sum(values) / len(values)


def pass_at_1(cell: Cell) -> float:
    """CAL6: the mean over tasks of each task's mean strict indicator.  Task-weighted: every
    seed counts once, whatever `n` it kept."""
    return _mean([_block_rate(block, _strict) for block in _blocks(cell)])


def pass_at_k(cell: Cell, k: int) -> float:
    """CAL7: the unbiased estimator averaged over tasks; refuses `k > n` naming both.  At
    `k = 1` it is `pass_at_1` exactly."""
    return _mean([_block_pass_at_k(block, k, _strict) for block in _blocks(cell)])


def _pass_at_k_statistic(k: int) -> _Callable[[Cell], float]:
    def statistic(cell: Cell) -> float:
        return pass_at_k(cell, k)

    return statistic


def _leaky_at_1(cell: Cell) -> float:
    return _mean([_block_rate(block, _leaky) for block in _blocks(cell)])


def _leaky_at_k(cell: Cell, k: int) -> float:
    return _mean([_block_pass_at_k(block, k, _leaky) for block in _blocks(cell)])


# ---------------------------------------------------------------------------
# the interval (CAL9) and the paired difference (CAL10, CAL11, CAL12)
# ---------------------------------------------------------------------------


def _quantile(sorted_values: _Sequence[float], q: float) -> float:
    """The smallest value whose cumulative share reaches `q`.  Not the nearest-rank rule and
    not the floor rule: on a distribution with few atoms both report the atom below."""
    index = _math.ceil(q * len(sorted_values)) - 1
    return sorted_values[min(len(sorted_values) - 1, max(0, index))]


def _resampled_means(
    values: _Sequence[float], *, resamples: int, seed: int
) -> list[float]:
    """The bootstrap distribution of a mean over tasks: `resamples` draws of `S` task indices
    with replacement, one `randrange(S)` per drawn task."""
    if resamples < 1:
        raise ValueError("the bootstrap needs at least one resample")
    rng = _random.Random(seed)
    size = len(values)
    out: list[float] = []
    for _ in range(resamples):
        total = 0.0
        for _position in range(size):
            total += values[rng.randrange(size)]
        out.append(total / size)
    out.sort()
    return out


def cluster_bootstrap(
    cell: Cell,
    statistic: _Callable[[Cell], float],
    *,
    resamples: int,
    seed: int,
) -> tuple[float, float]:
    """CAL9: the 95% interval of `statistic` under resampling of *tasks*, each task's block of
    attempts carried whole, at a declared resample count and RNG seed.

    `statistic` must be a mean over tasks of a per-task value, which pass@1 and pass@k both
    are; a statistic that is not decomposes differently and is refused rather than
    estimated wrongly.
    """
    blocks = _blocks(cell)
    values = [statistic(block) for block in blocks]
    whole = statistic(cell)
    if not _math.isclose(whole, _mean(values), abs_tol=1e-9):
        raise ValueError(
            "cluster_bootstrap needs a statistic that is a mean over tasks; this one is "
            f"{whole} on the cell and {_mean(values)} as a mean of per-task values"
        )
    distribution = _resampled_means(values, resamples=resamples, seed=seed)
    return _quantile(distribution, 0.025), _quantile(distribution, 0.975)


@_dc.dataclass(frozen=True)
class PairedDelta:
    """`pass@1(a) - pass@1(b)` with its paired 95% interval (CAL10)."""

    point: float
    low: float
    high: float


def _by_seed(cell: Cell) -> dict[int, list[EpisodeRecord]]:
    out: dict[int, list[EpisodeRecord]] = {}
    for block in _blocks(cell):
        seed = block[0].seed
        if seed in out:
            raise ValueError(f"two tasks in one cell carry seed {seed}")
        out[seed] = block
    return out


def paired_delta(
    a: Cell,
    b: Cell,
    *,
    resamples: int,
    seed: int,
    provenance: Provenance | None = None,
    predicate: str = "strict",
) -> PairedDelta:
    """CAL10: resample the shared seeds once, recompute both cells on that resample, and take
    the difference, so the pairing is inside the interval.  Two cells with different seed sets
    refuse, naming the symmetric difference.  With a provenance block, a saturated cell
    refuses (CAL12).  `predicate` is `strict` (the headline) or `leaky` (reaching the goal),
    and saturation is read on the rate being compared."""
    if predicate not in ("strict", "leaky"):
        raise ValueError(f"predicate is {predicate!r}; it is 'strict' or 'leaky'")
    indicator = _strict if predicate == "strict" else _leaky
    rate_of = pass_at_1 if predicate == "strict" else _leaky_at_1
    left, right = _by_seed(a), _by_seed(b)
    if set(left) != set(right):
        symmetric = sorted(set(left) ^ set(right))
        raise ValueError(
            "the two cells do not share a seed set, so the difference would compare "
            f"marginals; the symmetric difference is {symmetric}"
        )
    if provenance is not None:
        for name, cell in (("a", a), ("b", b)):
            rate = rate_of(cell)
            if saturated(rate, provenance):
                raise ValueError(
                    f"cell {name} is saturated at {predicate} pass@1 = {rate:.3f} and appears "
                    "in no distinguishability claim"
                )
    order = sorted(left)
    differences = [
        _block_rate(left[key], indicator) - _block_rate(right[key], indicator) for key in order
    ]
    distribution = _resampled_means(differences, resamples=resamples, seed=seed)
    return PairedDelta(
        point=rate_of(a) - rate_of(b),
        low=_quantile(distribution, 0.025),
        high=_quantile(distribution, 0.975),
    )


def call_pair(delta: PairedDelta, provenance: Provenance) -> str:
    """CAL11's two clauses: the paired interval excludes zero **and** `|delta| >= delta*`,
    with delta* read from the provenance block.  Anything else is `TOO_SMALL`, never "no
    difference"."""
    excludes_zero = not (delta.low <= 0.0 <= delta.high)
    if excludes_zero and abs(delta.point) >= provenance.delta_star:
        return DISTINGUISHABLE
    return TOO_SMALL


def saturated(pass_rate: float, provenance: Provenance) -> bool:
    """CAL12: at or above the high bound, or at or below the low one.  Both inclusive."""
    return pass_rate >= provenance.saturation_high or pass_rate <= provenance.saturation_low


# ---------------------------------------------------------------------------
# ordering (CAL13)
# ---------------------------------------------------------------------------


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


@_dc.dataclass(frozen=True)
class OrderingReport:
    """Per model and knob: whether pass@1 is non-increasing across the level axis, and each
    adjacent pair's difference.  `agreement` is a count, never a statistic."""

    levels: tuple[int, ...]
    rates: tuple[float, ...]
    pairs: tuple[tuple[int, int, float], ...]
    non_increasing: bool

    def agreement(self, other: OrderingReport) -> int:
        """The number of adjacent pairs on which two families put the harder level on the
        same side."""
        if self.levels != other.levels:
            raise ValueError("ordering reports over different level axes cannot be compared")
        return sum(
            1 for mine, theirs in zip(self.pairs, other.pairs, strict=True)
            if _sign(mine[2]) == _sign(theirs[2])
        )


def ordering(cells: _Mapping[int, Cell], axis: _Sequence[int]) -> OrderingReport:
    """CAL13 over the whole axis, never a pair: `axis` is `levels(knob)` and every level must
    have a cell."""
    missing = [level for level in axis if level not in cells]
    if missing:
        raise ValueError(f"no cell for level(s) {missing}; ordering needs the whole axis")
    rates = tuple(pass_at_1(cells[level]) for level in axis)
    pairs = tuple(
        (axis[i], axis[i + 1], rates[i] - rates[i + 1]) for i in range(len(axis) - 1)
    )
    return OrderingReport(
        levels=tuple(axis),
        rates=rates,
        pairs=pairs,
        non_increasing=all(difference >= 0.0 for _, _, difference in pairs),
    )


# ---------------------------------------------------------------------------
# provenance (CAL18)
# ---------------------------------------------------------------------------


def _seed_list_digest(seeds: _Sequence[int]) -> str:
    return _hashlib.sha256(_json.dumps(list(seeds)).encode("utf-8")).hexdigest()


def _require_keys(block: _Mapping[str, _Any], keys: _Iterable[str], what: str) -> None:
    missing = [key for key in keys if key not in block]
    if missing:
        raise ValueError(f"{what} is incomplete; missing " + ", ".join(missing))


@_dc.dataclass(frozen=True, kw_only=True)
class Provenance:
    """CAL18's block: everything a number depends on.  A missing field refuses construction,
    and so does a field that cannot be what it says it is.

    `models` is one mapping per model with `id`, `revision` and `endpoint_host`, and either
    all three of `input_rate`, `cached_input_rate` and `output_rate` (dollars per million
    tokens) or none.  `serving` is keyed by model id; a `local` entry carries the five
    `SERVING_FIELDS_LOCAL` and a `hosted` one carries `endpoint_host`.  A model with no
    `serving` entry is hosted at its `endpoint_host`.
    """

    package_version: str
    engine_hash: str
    generator_hash: str
    vocabulary_hash: str
    verifiers_version: str
    harness_id: str
    models: _Sequence[_Mapping[str, _Any]]
    decoding: _Mapping[str, _Any]
    seed_list: _Sequence[int]
    seed_list_hash: str
    S: int
    n: int
    k_values: _Sequence[int]
    bootstrap_resamples: int
    bootstrap_seed: int
    delta_star: float
    saturation_high: float
    saturation_low: float
    instrument_threshold: float
    rate_read_date: str
    serving: _Mapping[str, _Mapping[str, _Any]]
    budget: _Mapping[str, _Any]
    no_call_threshold: float = NO_CALL_THRESHOLD
    max_model_calls: int | None = None
    """The run's turn limit, when it had one.  Model A's run had none; a run through the
    taskset's own config has `poisson_tasks.taskset.MAX_MODEL_CALLS`."""
    concurrency: int | None = None
    """How many episodes the run had in flight at once, when it recorded that.  Time depends
    on it, so the card prints it wherever it prints seconds; it decides nothing."""
    arms: _Sequence[str] | None = None
    """The arm ids the run's plan asked for, in the plan's order, when the card was built for a
    plan: an arm here with no cell is one the run never reached, listed as not run.  A block for
    the published design has none."""
    strictness: str | None = None
    """The plan's strictness when it is not the published design's (`strict`): `leaky`, or the
    kinds joined by commas when its arms differ.  A leaky arm scores another predicate, so two
    cards must share this to be read side by side."""
    split: str | None = None
    """The plan's split when it is not the published design's (`eval`): the train split's tasks
    are other tasks, so two cards must share this too."""
    resumed: bool | None = None
    """True when some of the run's attempts were made by a later run of its folder than others;
    absent otherwise, so a block for the published design keeps its bytes."""
    tools: _Mapping[str, _Any] | None = None
    """The own-tools provenance kind (own-tools spec §9): `kind` `own`, the set's `name`, its
    usable `tools` count, its `source_format`, the file's `file_digest`, the tools that have an
    intent (`intents`, sorted names), the number of declared `flows` and the own-tools
    `generator` label.  A block for the built-in tasks has none, and `as_dict` leaves it out,
    so every published block keeps its bytes."""

    def __post_init__(self) -> None:
        if self.tools is not None:
            if not isinstance(self.tools, _Mapping) or self.tools.get("kind") != _OWN_KIND:
                found = dict(self.tools).get("kind") if isinstance(self.tools, _Mapping) else None
                raise ValueError(
                    f"tools.kind must be {_OWN_KIND!r}, the own-tools provenance kind; got "
                    f"{found!r}"
                )
            _require_keys(self.tools, _OWN_TOOLS_KEYS, "tools")
        for name in ("package_version", "engine_hash", "generator_hash", "vocabulary_hash",
                     "verifiers_version", "seed_list_hash"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"{name} must be a non-empty string")
        if self.harness_id != _MEASURED_HARNESS:
            raise ValueError(
                f"harness_id is {self.harness_id!r}; every pinned measurement is under "
                f"{_MEASURED_HARNESS!r}"
            )
        if self.S < 1 or self.n < 1:
            raise ValueError("S and n are at least 1")
        if len(self.seed_list) != self.S or len(set(self.seed_list)) != self.S:
            raise ValueError(
                f"seed_list must hold S = {self.S} distinct seeds; it holds "
                f"{len(set(self.seed_list))} distinct of {len(self.seed_list)}"
            )
        if not self.k_values or any(
            not isinstance(k, int) or k < 1 or k > self.n for k in self.k_values
        ):
            raise ValueError(f"k_values must be integers in 1..n = {self.n}: {self.k_values}")
        if self.bootstrap_resamples < 1:
            raise ValueError("bootstrap_resamples is at least 1")
        if not 0.0 < self.delta_star < 1.0:
            raise ValueError("delta_star is a pass-rate difference strictly inside (0, 1)")
        if not 0.0 <= self.saturation_low < self.saturation_high <= 1.0:
            raise ValueError("saturation_low < saturation_high, both inside [0, 1]")
        if not 0.0 <= self.instrument_threshold <= 1.0:
            raise ValueError("instrument_threshold is a rate in [0, 1]")
        if not 0.0 <= self.no_call_threshold <= 1.0:
            raise ValueError("no_call_threshold is a rate in [0, 1]")
        if self.concurrency is not None and (
            isinstance(self.concurrency, bool) or not isinstance(self.concurrency, int)
            or self.concurrency < 1
        ):
            raise ValueError(
                f"concurrency is {self.concurrency!r}; it is a whole number of episodes, at "
                "least 1, or absent when the run did not record it"
            )
        try:
            _datetime.date.fromisoformat(self.rate_read_date)
        except ValueError as error:
            raise ValueError(
                f"rate_read_date is not an ISO date: {self.rate_read_date!r}"
            ) from error
        check_decoding(self.decoding)
        _require_keys(self.budget, ("tokens", "wall_clock_seconds"), "budget")
        if not self.models:
            raise ValueError("models names no model")
        for entry in self.models:
            _require_keys(
                entry, ("id", "revision", "endpoint_host"), f"models[{entry.get('id')!r}]"
            )
            declared = [field for field in _RATE_FIELDS if field in entry]
            if declared and len(declared) != len(_RATE_FIELDS):
                raise ValueError(
                    f"models[{entry['id']!r}] declares {declared}; the three rates are "
                    "declared together or not at all"
                )
        for model_id, entry in self.serving.items():
            kind = entry.get("kind")
            if kind not in SERVING_KINDS:
                raise ValueError(f"serving[{model_id!r}].kind must be one of {SERVING_KINDS}")
            if kind == "local":
                _require_keys(entry, SERVING_FIELDS_LOCAL, f"serving[{model_id!r}] (local)")
                revision = str(entry["revision"])
                if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
                    raise ValueError(
                        f"serving[{model_id!r}].revision must be a 40-character commit hash"
                    )
            elif kind == "self_served":
                endpoint = entry.get("endpoint")
                if not isinstance(endpoint, str) or not endpoint:
                    raise ValueError(f"serving[{model_id!r}] (self_served) needs its endpoint")
            else:
                _require_keys(entry, ("endpoint_host",), f"serving[{model_id!r}] (hosted)")
        if self.arms is not None and (
            not self.arms or any(not isinstance(arm, str) or not arm for arm in self.arms)
        ):
            raise ValueError(
                f"arms names the plan's arms by their ids, or is absent: {self.arms!r}"
            )
        for name in ("strictness", "split"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{name} is a non-empty string, or absent: {value!r}")
        if self.resumed is not None and not isinstance(self.resumed, bool):
            raise ValueError(f"resumed is true, or absent: {self.resumed!r}")

    def as_dict(self) -> dict[str, _Any]:
        out: dict[str, _Any] = _json.loads(_json.dumps(_dc.asdict(self)))
        for name in ("arms", "strictness", "split", "resumed"):
            if out.get(name) is None:
                # A block for the published design has none of these; its bytes stay.
                out.pop(name, None)
        if out.get("max_model_calls") is None:
            # A run with no turn limit serialises exactly as it did before the field existed.
            out.pop("max_model_calls", None)
        if out.get("concurrency") is None:
            # Nor does a run that recorded no concurrency: a published block keeps its bytes.
            out.pop("concurrency", None)
        if out.get("tools") is None:
            # A block for the built-in tasks has no own-tools kind: its bytes stay.
            out.pop("tools", None)
        return out

    def rates_for(self, model: str) -> _Mapping[str, _Any] | None:
        entry = self.model_entry(model)
        if all(field in entry for field in _RATE_FIELDS):
            return entry
        return None

    def model_entry(self, model: str) -> _Mapping[str, _Any]:
        for entry in self.models:
            if entry["id"] == model:
                return entry
        raise ValueError(f"model {model!r} is not declared in the provenance block's models")

    @classmethod
    def for_run(
        cls,
        *,
        models: _Sequence[_Mapping[str, _Any]],
        serving: _Mapping[str, _Mapping[str, _Any]],
        rate_read_date: str,
        decoding: _Mapping[str, _Any] | None = None,
        budget: _Mapping[str, _Any] | None = None,
        instrument_threshold: float = INSTRUMENT_THRESHOLD,
        no_call_threshold: float = NO_CALL_THRESHOLD,
        max_model_calls: int | None = None,
        concurrency: int | None = None,
    ) -> Provenance:
        """The block for a real run, with every hash and version read from the package and
        the wheel rather than typed.  `concurrency` is how many episodes the run has in
        flight at once; a run that does not say records none."""
        seeds = seed_list()
        spec = _EngineSpec.load()
        bundle = _generate(arm_specs()[0], seeds[0])
        return cls(
            package_version=_metadata.version("poisson-tasks"),
            engine_hash=_engine_hash(spec),
            generator_hash=bundle.generator_hash,
            vocabulary_hash=_vocabulary_hash(),
            verifiers_version=_metadata.version("verifiers"),
            harness_id=_MEASURED_HARNESS,
            models=list(models),
            decoding=dict(DECODING if decoding is None else decoding),
            seed_list=list(seeds),
            seed_list_hash=_seed_list_digest(seeds),
            S=S,
            n=N,
            k_values=list(K_VALUES),
            bootstrap_resamples=BOOTSTRAP_RESAMPLES,
            bootstrap_seed=BOOTSTRAP_SEED,
            delta_star=DELTA_STAR,
            saturation_high=SATURATION_HIGH,
            saturation_low=SATURATION_LOW,
            instrument_threshold=instrument_threshold,
            rate_read_date=rate_read_date,
            serving={key: dict(value) for key, value in serving.items()},
            budget=dict(DEFAULT_BUDGET if budget is None else budget),
            no_call_threshold=no_call_threshold,
            max_model_calls=max_model_calls,
            concurrency=concurrency,
        )

    @classmethod
    def for_plan(
        cls,
        plan: _Any,
        *,
        serving: _Mapping[str, _Mapping[str, _Any]],
        rate_read_date: str,
        budget: _Mapping[str, _Any] | None = None,
        concurrency: int | None = None,
    ) -> Provenance:
        """The block for a run of `plan` (a `config.Plan`), under the plan's own design: its
        seeds and their hash, `S` = its tasks per level, `n` = its attempts, `k_values` those of
        1, 2 and 5 that are at most `n`, its decoding as declared, its turn cap, its model and
        prices, and `serving`.  Every hash and version is read from the package and the wheel.

        The generator hash is the plan's own arms', so a plan at another generator version is
        measured under it and is stale against the package.  The model entry's `endpoint_host`
        is the endpoint's host and port, and its rates the plan's price when it has one.  A run
        of a plan has caps, not the published design's budget, and its caps are in no file of
        its folder, so without `budget` the block records none and the card prints it as not
        recorded.  The plan's arms, and its strictness and split when they are not the
        published design's, travel in the block: a card read back from its own files still
        knows what the plan asked for."""
        seeds = [int(seed) for seed in plan.seeds]
        if not seeds or not plan.arms:
            raise ValueError("a plan with no seed or no arm has no design to measure under")
        n = int(plan.attempts)
        spec = plan.arms[0]
        own = getattr(plan, "own", None)
        tools: dict[str, _Any] | None = None
        if own is not None:
            # A plan on a user's own tools: the own-tools generator's hash, and the kind.
            from poisson_tasks.own import generator as _own_generator

            generator_hash = _own_generator.generator_hash()
            tools = {
                "kind": _OWN_KIND,
                "name": str(own["name"]),
                "tools": int(own["tools"]),
                "source_format": str(own["source_format"]),
                "file_digest": str(own["file_digest"]),
                "intents": sorted(str(name) for name in dict(own["intents"])),
                "flows": len(list(own["flows"])),
                "generator": _own_generator.GENERATOR_VERSION,
            }
        else:
            generator_hash = _generate(spec, seeds[0]).generator_hash
        entry: dict[str, _Any] = {
            "id": plan.model.name,
            "revision": plan.model.name,
            "endpoint_host": _urlparse.urlsplit(plan.model.base_url).netloc,
        }
        price = plan.model.price
        if price is not None:
            entry.update(
                input_rate=float(price.input),
                cached_input_rate=float(price.cached_input),
                output_rate=float(price.output),
            )
        strict = {str(arm.strictness) for arm in plan.arms}
        splits = {str(arm.split) for arm in plan.arms}
        return cls(
            package_version=_metadata.version("poisson-tasks"),
            engine_hash=_engine_hash(_EngineSpec.load()),
            generator_hash=generator_hash,
            vocabulary_hash=_vocabulary_hash(),
            verifiers_version=_metadata.version("verifiers"),
            harness_id=_MEASURED_HARNESS,
            models=[entry],
            decoding=dict(plan.decoding),
            seed_list=seeds,
            seed_list_hash=_seed_list_digest(seeds),
            S=len(seeds),
            n=n,
            k_values=[k for k in K_VALUES if k <= n],
            bootstrap_resamples=BOOTSTRAP_RESAMPLES,
            bootstrap_seed=BOOTSTRAP_SEED,
            delta_star=DELTA_STAR,
            saturation_high=SATURATION_HIGH,
            saturation_low=SATURATION_LOW,
            instrument_threshold=INSTRUMENT_THRESHOLD,
            rate_read_date=rate_read_date,
            serving={key: dict(value) for key, value in serving.items()},
            budget=dict({"tokens": None, "wall_clock_seconds": None} if budget is None
                        else budget),
            no_call_threshold=NO_CALL_THRESHOLD,
            max_model_calls=int(plan.max_model_calls),
            concurrency=concurrency,
            arms=[_arm_id(arm) for arm in plan.arms],
            strictness=None if strict == {"strict"} else ",".join(sorted(strict)),
            split=None if splits == {SPLIT} else ",".join(sorted(splits)),
            tools=tools,
        )


def _vocabulary_hash() -> str:
    """A digest over the frozen vocabulary table's bytes, as shipped."""
    root = _pathlib.Path(__file__).resolve().parent
    return _hashlib.sha256((root / "data" / "vocabulary-v2.json").read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# cost (CAL15)
# ---------------------------------------------------------------------------


def dollars(figures: _Mapping[str, _Any], rates: _Mapping[str, _Any] | None) -> float | None:
    """CAL15: tokens times a rate carried in the artifact, cached input at its own rate and
    reasoning tokens never added a second time.  No rate, no dollar figure."""
    if rates is None:
        return None
    return (
        float(figures["prompt_tokens"]) * float(rates["input_rate"])
        + float(figures["cached_input_tokens"]) * float(rates["cached_input_rate"])
        + float(figures["completion_tokens"]) * float(rates["output_rate"])
    ) / 1_000_000


# ---------------------------------------------------------------------------
# the artifact (CAL14, CAL16 to CAL20)
# ---------------------------------------------------------------------------


@_dc.dataclass(frozen=True)
class Artifact:
    """The machine-readable artifact: one record per cell, the adjacent-level pairs, the
    orderings, and the provenance block every figure was computed under."""

    cells: list[dict[str, _Any]]
    pairs: list[dict[str, _Any]]
    orderings: list[dict[str, _Any]]
    provenance: Provenance
    reach_pairs: list[dict[str, _Any]] = _dc.field(default_factory=list)
    """Depth's adjacent levels compared on leaky pass@1, reaching the goal.  Every depth arm
    offers the whole ladder, so strict below the top level also asks the model to stop at the
    goal; depth is read on these, with each cell's overshoot share beside them."""

    def as_dict(self) -> dict[str, _Any]:
        return {
            "cells": _json.loads(_json.dumps(self.cells)),
            "pairs": _json.loads(_json.dumps(self.pairs)),
            "reach_pairs": _json.loads(_json.dumps(self.reach_pairs)),
            "orderings": _json.loads(_json.dumps(self.orderings)),
            "provenance": self.provenance.as_dict(),
        }


CellKey = tuple[str, str]


def _spec_for(arm: str) -> _ArmSpec | None:
    """The arm an id names, as a card generates it, or `None` for text that is no arm's id.

    Read from the id itself and not looked up in `arm_specs()`, so an arm outside the card
    design has its knob, its control and its minimum calls, and a card keeps its arms' when
    the design changes.
    """
    try:
        return _arm_from_id(
            arm, strictness="strict", split=SPLIT, generator_version=GENERATOR_VERSION
        )
    except ValueError:
        return None


def _is_control(arm: str) -> bool:
    spec = _spec_for(arm)
    return spec is not None and spec.control is not None


def _minimum_calls(arm: str) -> int | None:
    """G5's structural number, the fewest tool calls that solve the arm's task: its
    reference turns less the reply.  `d` for a depth arm and `d_R` for a distractor arm."""
    spec = _spec_for(arm)
    if spec is None:
        return None
    return spec.reference_turns - 1


def _made_no_call(row: EpisodeRecord) -> bool:
    """CAL24: the episode ended without a single tool call."""
    return row.sampled_calls == 0


def _stopped_short(row: EpisodeRecord, minimum: int | None) -> bool:
    """CAL24: the episode started and made fewer tool calls than its structural minimum.
    Disjoint from `_made_no_call`, so no call, short and reached partition the episodes."""
    return minimum is not None and 0 < row.sampled_calls < minimum


def _cell_tally(
    key: CellKey,
    cells: _Mapping[CellKey, Cell],
    tally: _Mapping[str, int] | _Mapping[CellKey, _Mapping[str, int]] | None,
) -> _Mapping[str, int] | None:
    """The tally for one cell.  A flat label-to-count tally is accepted only for a
    single-cell artifact; otherwise it is keyed by cell."""
    if tally is None:
        return None
    if all(isinstance(name, str) for name in tally):
        if len(cells) != 1:
            raise ValueError("a flat tally cannot be attributed across several cells")
        flat = _cast(_Mapping[str, int], tally)
        return {name: int(count) for name, count in flat.items()}
    keyed = _cast(_Mapping[CellKey, _Mapping[str, int]], tally)
    found = keyed.get(key)
    return None if found is None else {name: int(count) for name, count in found.items()}


def _check_cell(
    key: CellKey, cell: Cell, provenance: Provenance, tally: _Mapping[str, int] | None
) -> None:
    """The refusals that name a cell: two models in one record (CAL14), a model or arm the
    key does not name, a model the block does not declare, an instrument rate over the
    threshold (CAL16), no scored episode at all, and a no-call share over its threshold
    (CAL24)."""
    arm, model = key
    models = sorted({row.model for row in cell})
    if len(models) > 1:
        raise ValueError(
            "no published number pools models; this record holds " + ", ".join(models)
        )
    if models and models[0] != model:
        raise ValueError(f"cell {key} holds records of model {models[0]!r}")
    arms = sorted({row.arm_id for row in cell})
    if arms and arms != [arm]:
        raise ValueError(f"cell {key} holds records of arm(s) {arms}")
    provenance.model_entry(model)
    rate = instrument_rate(cell, tally)
    if rate > provenance.instrument_threshold:
        raise ValueError(
            f"cell {key} refuses to publish: its instrument rate {rate:.3f} exceeds the "
            f"declared threshold {provenance.instrument_threshold}"
        )
    kept = scored(cell)
    if not kept:
        raise ValueError(f"cell {key} has no scored episode")
    share = sum(1 for row in kept if _made_no_call(row)) / len(kept)
    if share > provenance.no_call_threshold:
        raise ValueError(
            f"cell {key} refuses to publish: {share:.3f} of its scored episodes made no tool "
            f"call, above the declared {provenance.no_call_threshold}; it measures whether "
            "the model starts, not the level"
        )


def _recorded(kept: Cell, name: str) -> list[float]:
    """The scored episodes' values of an optional field, over those that recorded it."""
    return sorted(value for row in kept if (value := getattr(row, name)) is not None)


def _median_or_none(values: _Sequence[float]) -> float | None:
    return _statistics.median(values) if values else None


def _p90_or_none(sorted_values: _Sequence[float]) -> float | None:
    return _quantile(sorted_values, 0.9) if sorted_values else None


def _cost_and_time(kept: Cell, strict_1: float) -> dict[str, _Any]:
    """What the cell's scored episodes cost in calls and tokens, and what they took in
    seconds.  Calls and tokens are over every scored episode.  A time or first-request figure
    is over the scored episodes that recorded it and is `None` when none did, never zero.  The
    90th percentile is the module's quantile rule.  Tokens per strict pass is the mean tokens
    over strict pass@1, and `None` when nothing passed."""
    tokens = sorted(
        row.prompt_tokens + row.cached_input_tokens + row.completion_tokens for row in kept
    )
    tokens_mean = sum(tokens) / len(tokens)
    out: dict[str, _Any] = {
        "model_calls_mean": sum(row.turns for row in kept) / len(kept),
        "tool_calls_mean": sum(row.sampled_calls for row in kept) / len(kept),
        "tool_calls_median": _statistics.median(row.sampled_calls for row in kept),
        "tokens_mean": tokens_mean,
        "tokens_p90": _quantile(tokens, 0.9),
        "tokens_per_strict_pass": tokens_mean / strict_1 if strict_1 > 0 else None,
        "first_request_prompt_tokens_median": _median_or_none(
            _recorded(kept, "first_request_prompt_tokens")
        ),
    }
    for name in ("episode_seconds", "model_seconds", "harness_seconds"):
        values = _recorded(kept, name)
        out[f"{name}_median"] = _median_or_none(values)
        out[f"{name}_p90"] = _p90_or_none(values)
    out["setup_seconds_median"] = _median_or_none(_recorded(kept, "setup_seconds"))
    return out


def _cell_figures(
    key: CellKey,
    cell: Cell,
    provenance: Provenance,
    tally: _Mapping[str, int] | None,
) -> dict[str, _Any]:
    arm, model = key
    rate = instrument_rate(cell, tally)
    kept = scored(cell)
    blocks = _blocks(kept)
    n_min = min(len(block) for block in blocks)
    strict_1 = pass_at_1(kept)
    interval_1 = cluster_bootstrap(
        kept, pass_at_1, resamples=provenance.bootstrap_resamples, seed=provenance.bootstrap_seed
    )
    leaky_interval = cluster_bootstrap(
        kept, _leaky_at_1, resamples=provenance.bootstrap_resamples, seed=provenance.bootstrap_seed
    )
    pass_k = {str(k): pass_at_k(kept, k) for k in range(1, n_min + 1)}
    leaky_k = {str(k): _leaky_at_k(kept, k) for k in range(1, n_min + 1)}
    pass_k_interval: dict[str, list[float]] = {}
    for k in provenance.k_values:
        if k <= n_min:
            low, high = cluster_bootstrap(
                kept,
                _pass_at_k_statistic(k),
                resamples=provenance.bootstrap_resamples,
                seed=provenance.bootstrap_seed,
            )
            pass_k_interval[str(k)] = [low, high]
    labelled = len(cell) - len(kept)
    failures = max(labelled, sum(tally.values())) if tally else labelled
    # A task on a user's own tools has its own structural minimum, which the built-in arm's
    # reference turns do not give; the figure is not recorded there.
    minimum = None if provenance.tools is not None else _minimum_calls(arm)
    no_call = sum(1 for row in kept if _made_no_call(row))
    short = sum(1 for row in kept if _stopped_short(row, minimum))
    # Reached the goal and carried the record past it: a stop-at-the-goal failure.
    overshoot = sum(1 for row in kept if row.label == _OVERSHOOT)
    completion = sum(row.completion_tokens for row in kept)
    reasoning = sum(row.reasoning_tokens for row in kept)
    prompt = sum(row.prompt_tokens for row in kept)
    cached = sum(row.cached_input_tokens for row in kept)
    figures: dict[str, _Any] = {
        "arm_id": arm,
        "model": model,
        "control": _is_control(arm),
        "minimum_calls": minimum,
        "seeds": sorted(block[0].seed for block in blocks),
        "S_declared": provenance.S,
        "S_observed": len(blocks),
        "n_declared": provenance.n,
        # Fewer scored attempts than the design asks for, whatever the reason: a task the run
        # never reached, or an attempt that failed and was not run again.  A failed attempt is
        # counted by the instrument figures, never as an attempt the level has.
        "incomplete": len(blocks) < provenance.S
        or any(len(block) < provenance.n for block in blocks),
        "pass_at_1": strict_1,
        "pass_at_1_interval": [interval_1[0], interval_1[1]],
        "pass_at_k": pass_k,
        "pass_at_k_interval": pass_k_interval,
        "leaky_at_1": _leaky_at_1(kept),
        "leaky_at_1_interval": [leaky_interval[0], leaky_interval[1]],
        "leaky_at_k": leaky_k,
        "overshoot_count": overshoot,
        "overshoot_share": overshoot / len(kept),
        "saturated": saturated(strict_1, provenance),
        "outcome_mix": {label: sum(1 for row in cell if row.label == label)
                        for label in sorted(OUTCOME_LABELS)
                        if any(row.label == label for row in cell)},
        "instrument_count": failures,
        "instrument_rate": rate,
        "episodes_scored": len(kept),
        "no_call_count": no_call,
        "no_call_share": no_call / len(kept),
        "stopped_short_count": short,
        "stopped_short_share": short / len(kept),
        "model_calls": sum(row.turns for row in kept),
        "model_calls_median": _statistics.median(row.turns for row in kept),
        "tool_calls": sum(row.sampled_calls for row in kept),
        "prompt_tokens": prompt,
        "cached_input_tokens": cached,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
        "tokens_median": _statistics.median(
            row.prompt_tokens + row.cached_input_tokens + row.completion_tokens for row in kept
        ),
        "cached_input_share": cached / (prompt + cached) if prompt + cached else 0.0,
        "reasoning_share": reasoning / completion if completion else 0.0,
        "reported_cost": (
            sum(row.cost for row in kept if row.cost is not None)
            if any(row.cost is not None for row in kept)
            else None
        ),
    }
    figures["dollars"] = dollars(figures, provenance.rates_for(model))
    figures.update(_cost_and_time(kept, strict_1))
    # The faults knob's figure, on a cell whose scored episodes carry a verdict: how many
    # received an `unavailable` and never called that tool again, and their share of the
    # episodes judged.  Printed by a card with a faults section and never gated; a cell whose
    # records carry no verdict has neither key, so no published artifact moves.
    judged = [row for row in kept if row.gave_up_after_fault is not None]
    if judged:
        gave_up = sum(1 for row in judged if row.gave_up_after_fault)
        figures["gave_up_after_fault_count"] = gave_up
        figures["gave_up_after_fault_share"] = gave_up / len(judged)
    return figures


def _pair_rows(
    cells: _Mapping[CellKey, Cell],
    figures: _Mapping[CellKey, dict[str, _Any]],
    provenance: Provenance,
) -> list[dict[str, _Any]]:
    """One row per model, knob and adjacent pair of plain levels (CAL10 to CAL12), over the
    whole axis and never a chosen pair.  On a user's own tools, each level against the knob's
    first (own-tools spec §6.3), through `own.card.against_first`."""
    rows: list[dict[str, _Any]] = []
    models = sorted({model for _, model in cells})
    if provenance.tools is not None:
        from poisson_tasks.own import card as _own_card

        by_model = {model: {key: cell for key, cell in cells.items() if key[1] == model}
                    for model in models}
        for model in models:
            for against in _own_card.against_first(by_model[model], provenance):
                excluded = against.verdict == _own_card.EXCLUDED
                rows.append({
                    "model": model, "knob": against.knob, "level_a": against.level,
                    "level_b": against.first, "arm_a": _level_arm(against.knob, against.level),
                    "arm_b": _level_arm(against.knob, against.first),
                    "predicate": against.predicate, "delta": against.delta,
                    "low": against.low, "high": against.high, "verdict": against.verdict,
                    "reason": "saturated on the same side" if excluded else None,
                })
        return rows
    for model in models:
        for knob in _KNOBS:
            axis = _levels(knob)
            for a, b in zip(axis, axis[1:], strict=False):
                key_a = (_arm_id(_plain(knob, a)), model)
                key_b = (_arm_id(_plain(knob, b)), model)
                if key_a not in cells or key_b not in cells:
                    continue
                row: dict[str, _Any] = {
                    "model": model, "knob": knob, "level_a": a, "level_b": b,
                    "arm_a": key_a[0], "arm_b": key_b[0],
                    "delta": None, "low": None, "high": None,
                }
                saturated_arms = [
                    key[0] for key in (key_a, key_b) if figures[key]["saturated"]
                ]
                if saturated_arms:
                    row["verdict"] = "excluded"
                    row["reason"] = "saturated: " + ", ".join(saturated_arms)
                    rows.append(row)
                    continue
                try:
                    delta = paired_delta(
                        scored(cells[key_a]), scored(cells[key_b]),
                        resamples=provenance.bootstrap_resamples, seed=provenance.bootstrap_seed,
                    )
                except ValueError as error:
                    row["verdict"] = "refused"
                    row["reason"] = str(error)
                    rows.append(row)
                    continue
                row.update(delta=delta.point, low=delta.low, high=delta.high)
                row["verdict"] = call_pair(delta, provenance)
                row["reason"] = None
                rows.append(row)
    return rows


def _reach_pair_rows(
    cells: _Mapping[CellKey, Cell],
    figures: _Mapping[CellKey, dict[str, _Any]],
    provenance: Provenance,
) -> list[dict[str, _Any]]:
    """Depth's adjacent plain levels compared on leaky pass@1, reaching the goal, by the same
    pairing and two-clause rule as the strict comparisons, with saturation read on the leaky
    rate.  The distractor knob has none: every level needs the same calls, and its question
    is choosing the tool, not stopping."""
    rows: list[dict[str, _Any]] = []
    if provenance.tools is not None:
        # On a user's own tools depth is read on strict, as every knob there: no overshoot.
        return rows
    axis = _levels(_DEPTH)
    for model in sorted({model for _, model in cells}):
        for a, b in zip(axis, axis[1:], strict=False):
            key_a = (_arm_id(_plain(_DEPTH, a)), model)
            key_b = (_arm_id(_plain(_DEPTH, b)), model)
            if key_a not in cells or key_b not in cells:
                continue
            row: dict[str, _Any] = {
                "model": model, "knob": _DEPTH, "level_a": a, "level_b": b,
                "arm_a": key_a[0], "arm_b": key_b[0], "predicate": "leaky",
                "delta": None, "low": None, "high": None,
            }
            saturated_arms = [key[0] for key in (key_a, key_b)
                              if saturated(figures[key]["leaky_at_1"], provenance)]
            if saturated_arms:
                row["verdict"] = "excluded"
                row["reason"] = "saturated on leaky: " + ", ".join(saturated_arms)
                rows.append(row)
                continue
            try:
                delta = paired_delta(
                    scored(cells[key_a]), scored(cells[key_b]), predicate="leaky",
                    resamples=provenance.bootstrap_resamples, seed=provenance.bootstrap_seed,
                )
            except ValueError as error:
                row["verdict"] = "refused"
                row["reason"] = str(error)
                rows.append(row)
                continue
            row.update(delta=delta.point, low=delta.low, high=delta.high)
            row["verdict"] = call_pair(delta, provenance)
            row["reason"] = None
            rows.append(row)
    return rows


def _own_axes(cells: _Mapping[CellKey, Cell]) -> dict[str, tuple[int, ...]]:
    """On a user's own tools, each knob's axis is the levels its cells hold, in order; a knob
    with one level has no ordering to read."""
    from poisson_tasks.own.generator import KNOBS as _OWN_KNOBS

    found: dict[str, set[int]] = {}
    for arm, _model in cells:
        spec = _spec_for(arm)
        if spec is not None and spec.control is None and spec.knob in _OWN_KNOBS:
            found.setdefault(spec.knob, set()).add(spec.level)
    return {knob: tuple(sorted(found[knob])) for knob in _OWN_KNOBS
            if knob in found and len(found[knob]) > 1}


def _ordering_rows(cells: _Mapping[CellKey, Cell], own: bool = False) -> list[dict[str, _Any]]:
    """CAL13 per model and knob, and the family agreement count where two models share a
    complete axis.  Each ordering row carries leaky pass@1 across the axis beside the strict
    rates; the agreement count stays on the strict headline.  On a user's own tools the axis
    of a knob is the levels the card holds."""
    rows: list[dict[str, _Any]] = []
    reports: dict[tuple[str, str], OrderingReport] = {}
    axes = _own_axes(cells) if own else {knob: _levels(knob) for knob in _KNOBS}
    for model in sorted({model for _, model in cells}):
        for knob, axis in axes.items():
            keyed = {level: (_level_arm(knob, level), model) for level in axis}
            if not all(key in cells for key in keyed.values()):
                continue
            report = ordering({level: scored(cells[key]) for level, key in keyed.items()}, axis)
            reports[(model, knob)] = report
            leaky = [_leaky_at_1(scored(cells[keyed[level]])) for level in axis]
            rows.append({
                "kind": "ordering", "model": model, "knob": knob,
                "levels": list(report.levels), "pass_at_1": list(report.rates),
                "non_increasing": report.non_increasing,
                "pairs": [list(pair) for pair in report.pairs],
                "leaky_at_1": leaky,
                "leaky_non_increasing": all(
                    leaky[i] >= leaky[i + 1] for i in range(len(leaky) - 1)
                ),
            })
    for knob, axis in axes.items():
        families = sorted(model for model, k in reports if k == knob)
        for i, first in enumerate(families):
            for second in families[i + 1:]:
                rows.append({
                    "kind": "agreement", "knob": knob, "models": [first, second],
                    "agreeing_pairs": reports[(first, knob)].agreement(reports[(second, knob)]),
                    "of": len(axis) - 1,
                })
    return rows


def build_artifact(
    cells: _Mapping[CellKey, Cell],
    provenance: Provenance,
    tally: _Mapping[str, int] | _Mapping[CellKey, _Mapping[str, int]] | None = None,
) -> Artifact:
    """Every published figure, computed from the records under one provenance block.

    Refuses: a seed list whose hash is not the list's; a cell holding two models (CAL14) or
    a model the block does not declare; a cell over the instrument threshold (CAL16); a
    locally served model without its serving stack (checked at `Provenance`).
    """
    tallies = {key: _cell_tally(key, cells, tally) for key in cells}
    for key, cell in cells.items():
        _check_cell(key, cell, provenance, tallies[key])
    expected = _seed_list_digest(provenance.seed_list)
    if provenance.seed_list_hash != expected:
        raise ValueError(
            "the seed list and its seed_list_hash disagree: the list hashes to "
            f"{expected} and the block declares {provenance.seed_list_hash}"
        )
    figures = {
        key: _cell_figures(key, cell, provenance, tallies[key]) for key, cell in cells.items()
    }
    return Artifact(
        cells=list(figures.values()),
        pairs=_pair_rows(cells, figures, provenance),
        orderings=_ordering_rows(cells, own=provenance.tools is not None),
        provenance=provenance,
        reach_pairs=_reach_pair_rows(cells, figures, provenance),
    )


def _artifact_text(artifact: Artifact) -> str:
    """`artifact.json`'s text: keys sorted, so two writes of one artifact are one file, and
    what `cards.recompute` compares a rebuilt card with."""
    return _json.dumps(artifact.as_dict(), indent=2, sort_keys=True) + "\n"


def write_artifact(artifact: Artifact, path: _pathlib.Path) -> _pathlib.Path:
    """The machine-readable file, keys sorted, so two writes of one artifact are one file."""
    path = _pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_artifact_text(artifact), encoding="utf-8")
    return path


def write_records(records: _Iterable[EpisodeRecord], path: _pathlib.Path) -> _pathlib.Path:
    path = _pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in records:
            handle.write(EpisodeRecord.to_json(row) + "\n")
    return path


def read_records(path: _pathlib.Path) -> list[EpisodeRecord]:
    lines = _pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    return [EpisodeRecord.from_json(line) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# the renderings (CAL13, CAL17)
# ---------------------------------------------------------------------------


def _fmt(value: _Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _interval(value: _Sequence[float] | None) -> str:
    if value is None:
        return "n/a"
    return f"[{value[0]:.3f}, {value[1]:.3f}]"


NOT_RECORDED = "not recorded"
"""What the card prints for a figure the run did not record.  Never a zero."""


def _seconds(value: float | None) -> str:
    return NOT_RECORDED if value is None else f"{value:.1f}"


def _concurrency(prov: Provenance) -> str:
    if prov.concurrency is None:
        return NOT_RECORDED
    return f"{prov.concurrency} episode{'' if prov.concurrency == 1 else 's'} at once"


def _level_header(k_values: _Sequence[int]) -> tuple[str, str]:
    columns = ["arm", "model", "strict pass@1", "95% interval", "leaky pass@1",
               "leaky 95% interval", "overshoot"]
    columns += [f"strict pass@{k}" for k in k_values if k != 1]
    columns += ["median model calls", "median tokens", "median episode seconds"]
    columns += ["min calls", "no tool call", "stopped short", "saturated", "instrument",
                "incomplete"]
    return "| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)


def _level_row(cell: _Mapping[str, _Any], k_values: _Sequence[int]) -> str:
    values = [
        f"`{cell['arm_id']}`", cell["model"], _fmt(cell["pass_at_1"]),
        _interval(cell["pass_at_1_interval"]), _fmt(cell["leaky_at_1"]),
        _interval(cell["leaky_at_1_interval"]), _fmt(cell["overshoot_share"]),
    ]
    values += [_fmt(cell["pass_at_k"].get(str(k))) for k in k_values if k != 1]
    values += [
        _fmt(cell["model_calls_median"]), _fmt(cell["tokens_median"]),
        _seconds(cell["episode_seconds_median"]), _fmt(cell["minimum_calls"]),
        _fmt(cell["no_call_share"]), _fmt(cell["stopped_short_share"]),
        _fmt(cell["saturated"]), str(cell["instrument_count"]), _fmt(cell["incomplete"]),
    ]
    return "| " + " | ".join(values) + " |"


def _level_arm(knob: str, level: int) -> str:
    """The plain arm id of a knob's level, as an own-tools card names its arms."""
    return _render_arm_id(knob, level, None)


def _plain(knob: str, level: int) -> _ArmSpec:
    return _ArmSpec(knob=knob, level=level, control=None, strictness="strict",
                    split=SPLIT, generator_version=GENERATOR_VERSION)


def _depth_stop_note(axis: _Sequence[int]) -> str:
    """The depth ordering's note, from the axis: every depth arm offers the whole stage ladder, so
    below the top level strict also asks the model to stop at the goal, and at the top level
    no stage lies above it."""
    lower, top = list(axis[:-1]), axis[-1]
    below = f"d{lower[0]} to d{lower[-1]}" if len(lower) > 1 else f"d{lower[0]}"
    return (
        f"Strict at {below} includes a stop-at-the-goal test that d{top} cannot have: every "
        "depth arm offers the whole stage ladder, so below the top level the model can carry "
        f"the record past the goal (overshoot), and at d{top} no stage lies above the goal. "
        "Leaky measures reaching the goal at every level and is comparable across the whole "
        "axis, so depth is read on leaky, with the overshoot column showing how often the model "
        "did not stop at the goal."
    )


def render_document(artifact: Artifact, *, claims: bool = False) -> str:
    """`docs/calibration.md`: rendered from the artifact and never typed (CAL17).  Every
    sentence is a single-model difficulty claim; nothing here ranks models or claims a
    rank statistic (CAL13, CAL14).

    With `claims`, the document also carries the card's claims block (`_claims_block`): what
    ran when the card is partial, what the card means and what it does not claim, after the
    provenance.  A run's card is rendered that way; the published page is not, and every line
    of this rendering is in the other, in order."""
    prov = artifact.provenance
    own = prov.tools is not None
    k_values = list(prov.k_values)
    header, rule = _level_header(k_values)
    lines: list[str] = ["# What each difficulty level is worth", ""]
    if own:
        from poisson_tasks.own import card as _own_card

        # Own-tools spec §9: the first lines, before anything else the card says.
        lines += [_own_card.first_lines(prov.tools or {}), ""]
    lines += [
        f"Rendered from the calibration artifact for poisson-tasks {prov.package_version} "
        f"(domain `{prov.engine_hash}`, generator `{prov.generator_hash}`, vocabulary "
        f"`{prov.vocabulary_hash}`), run through the `{prov.harness_id}` harness at verifiers "
        f"{prov.verifiers_version} over S = {prov.S} seeds from the {SPLIT} split "
        f"(seed list `{prov.seed_list_hash}`) at n = {prov.n} independent attempts per task.",
        "",
        "**This card is pinned to the generator hash above and is stale the moment "
        "the generator changes.** It is not regenerated automatically; a card whose "
        "generator hash differs from the package's is stale and says so here.",
        "",
        "**A resumed run is the same run in this sense and no other.** A run that was "
        "interrupted and resumed serves the same tasks, each with its full number of "
        "attempts, none run twice and none skipped. It does not reproduce the interrupted "
        "attempts byte for byte: the decoding is deliberately not deterministic, so a resumed "
        "attempt is a fresh attempt and not an identical copy of the one it replaces.",
        "",
        "Every number is one model's. No figure pools or ranks models, and a difference "
        "between two levels is printed only under the two-clause rule below.",
        "",
        "## Levels",
        "",
        "The **strict** rate is the headline: the episode reached the goal state exactly and "
        "ended with a reply. The **leaky** rate beside it also accepts overshoot and "
        "collateral damage. They are two different difficulty claims and both are published, "
        "so a rate is never read without knowing which one it is. The interval is a "
        "task-clustered bootstrap at "
        f"{prov.bootstrap_resamples} resamples (seed {prov.bootstrap_seed}). *min calls* is "
        "the structural minimum, which needs no model. *no tool call* is the share of scored "
        "episodes that ended without a single tool call, and *stopped short* the share that "
        "started and made fewer calls than the minimum; the two are disjoint. A cell whose "
        f"no-call share is above {prov.no_call_threshold} is not published at all, "
        "because it would measure whether the model starts rather than the level; stopping "
        "short is a difficulty result and is printed, not gated. A saturated level is one "
        "this model cannot see past and it appears in no claim below.",
        "",
        (
            "*overshoot* is never reached on your tools: a tool of yours has no stage past its "
            "goal, so what the leaky rate accepts beyond the strict one is a side effect. **Every "
            "knob here, depth included, is read on strict pass@1 against its first level.** The "
            "*leaky 95% interval* is the same task-clustered bootstrap on the leaky rate."
        ) if own else (
            "*overshoot* is the share of scored episodes that reached the goal and carried the "
            "record past it, and the *leaky 95% interval* is the same task-clustered bootstrap on "
            "the leaky rate. **Depth is read on leaky pass@1, reaching the goal.** Every depth "
            "level offers the whole stage ladder, so below the top level the strict rate also asks "
            "the model to stop at the goal; the overshoot column shows how often it did not. The "
            "strict rate is published beside it and is first in each table."
        ),
        "",
        "Beside the rates is what the level cost: *median model calls*, *median tokens* "
        "(prompt, cached input and completion) and *median episode seconds* over the scored "
        "episodes. Episode seconds run from the start of the model's work on the task to its "
        f"end, and a row whose episodes kept no time prints *{NOT_RECORDED}*. Seconds belong "
        "to the serving and its load as much as to the level; they are printed and decide "
        "nothing here.",
        "",
        f"Concurrency of this run: {_concurrency(prov)}.",
    ]
    level_cells = [cell for cell in artifact.cells if not cell["control"]]
    control_cells = [cell for cell in artifact.cells if cell["control"]]
    knob_order: tuple[str, ...] = _KNOBS
    if own:
        from poisson_tasks.own.generator import KNOBS as _OWN_KNOBS

        knob_order = _OWN_KNOBS
    for knob in knob_order:
        rows = [cell for cell in level_cells if _spec_for(cell["arm_id"]) is not None
                and _spec_for(cell["arm_id"]).knob == knob]  # type: ignore[union-attr]
        if not rows:
            continue
        lines += ["", f"### {knob}", "", header, rule]
        lines += [_level_row(cell, k_values) for cell in rows]
    if not own:
        # Own tools have no control arms (ruled 2026-10-13, yes/no 8).
        lines += [
            "",
            INSTRUMENT_TABLE_HEADING,
            "",
            "These are instrument arms. A control such as `depth:d1+h8` exists to separate "
            "depth from history, not to be a difficulty level, and it must not be read as one.",
            "",
            f"Concurrency of this run: {_concurrency(prov)}.",
            "",
            header,
            rule,
        ]
        lines += [_level_row(cell, k_values) for cell in control_cells]
    lines += [
        "",
        "## Cost per episode",
        "",
        "Measured from each episode's own usage, never estimated. Cached and uncached input "
        "are billed at different rates and are kept apart; reasoning tokens are part of the "
        f"completion tokens and are not added again. Dollars are tokens times the rate read on "
        f"{prov.rate_read_date}; a model with no rate declared has no dollar figure, and a "
        "provider-reported cost is printed beside the computed one and never reconciled.",
        "",
        "### Calls and tokens per episode",
        "",
        "Over each arm's scored episodes. Tokens are prompt, cached input and completion "
        "together. The 90th percentile is the smallest value that at least nine episodes in "
        "ten stay at or under. *tokens per strict pass* is the mean tokens divided by strict "
        "pass@1, what one strict pass costs at this level, and is n/a where nothing passed.",
        "",
        "| arm | model | mean model calls | median model calls | mean tool calls | median tool "
        "calls | mean tokens | median tokens | 90th percentile tokens | tokens per strict pass |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cell in artifact.cells:
        lines.append(
            f"| `{cell['arm_id']}` | {cell['model']} | {_fmt(cell['model_calls_mean'])} | "
            f"{_fmt(cell['model_calls_median'])} | {_fmt(cell['tool_calls_mean'])} | "
            f"{_fmt(cell['tool_calls_median'])} | {_fmt(cell['tokens_mean'])} | "
            f"{_fmt(cell['tokens_median'])} | {_fmt(cell['tokens_p90'])} | "
            f"{_fmt(cell['tokens_per_strict_pass'])} |"
        )
    lines += [
        "",
        "### Time per episode",
        "",
        "Over each arm's scored episodes that kept time. *episode seconds* run from the start "
        "of the model's work on the task to its end; *model seconds* are the part spent "
        "waiting on the model and *harness seconds* the rest, the tool calls and the harness "
        "between them. *setup seconds* are the tool server's start before the episode: what "
        f"the instrument costs, not the task. An arm whose episodes kept no time prints "
        f"*{NOT_RECORDED}*; no figure here is a guess or a zero standing in for one.",
        "",
        "Time belongs to the serving and its load as much as to the task. It is this run's "
        "own, and is not to be compared with another card's unless both were served the same "
        "way at the same concurrency.",
        "",
        f"Concurrency of this run: {_concurrency(prov)}.",
        "",
        "| arm | model | median episode seconds | 90th percentile episode seconds | median "
        "model seconds | 90th percentile model seconds | median harness seconds | 90th "
        "percentile harness seconds | median setup seconds |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for cell in artifact.cells:
        lines.append(
            f"| `{cell['arm_id']}` | {cell['model']} | "
            + " | ".join(_seconds(cell[key]) for key in (
                "episode_seconds_median", "episode_seconds_p90", "model_seconds_median",
                "model_seconds_p90", "harness_seconds_median", "harness_seconds_p90",
                "setup_seconds_median"))
            + " |"
        )
    lines += [
        "",
        "### Token totals and dollars",
        "",
        "| arm | model | prompt tokens | cached input tokens | completion tokens | reasoning "
        "share | computed $ | reported $ |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for cell in artifact.cells:
        lines.append(
            f"| `{cell['arm_id']}` | {cell['model']} | {cell['prompt_tokens']} | "
            f"{cell['cached_input_tokens']} | {cell['completion_tokens']} | "
            f"{_fmt(cell['reasoning_share'])} | {_fmt(cell['dollars'])} | "
            f"{_fmt(cell['reported_cost'])} |"
        )
    if own:
        from poisson_tasks.own import card as _own_card

        rows_against_first = _own_card.rows_from_artifact(artifact)
        lines += [
            "",
            "## Each level against the first",
            "",
            "On your tools each knob is read against its own first level: "
            "the difference is paired over the shared seeds inside each resample, on strict "
            f"pass@1. A level is *{DISTINGUISHABLE}* from the first only when its paired 95% "
            "interval excludes zero **and** the difference is at least delta* = "
            f"{prov.delta_star:.2f} pass-rate points; otherwise it reads *{TOO_SMALL}*, with its "
            "difference and interval shown; a pair saturated on the same side is "
            f"*{_own_card.EXCLUDED}*.",
            "",
            "| model | knob | level vs first | delta strict pass@1 | 95% paired interval | "
            "verdict |",
            "|---|---|---|---|---|---|",
        ]
        for pair in artifact.pairs:
            verdict = pair["verdict"]
            if pair["reason"] is not None:
                verdict = f"{verdict}: {pair['reason']}"
            interval = None if pair["low"] is None else (pair["low"], pair["high"])
            lines.append(
                f"| {pair['model']} | {pair['knob']} | {pair['level_a']} vs {pair['level_b']} | "
                f"{_fmt(pair['delta'])} | {_interval(interval)} | {verdict} |"
            )
        lines += ["", "### What each knob did, in words", ""]
        said = _own_card.bite(rows_against_first)
        lines += [f"- {line}" for line in said.values()] or [
            "- No knob has two levels on this card, so none is read against its first."]
        # Every knob stays available on own tools (ruled 2026-10-13 23:26); each carries the
        # knob probe's status on each probe model, said apart from the per-set table above.
        knobs_here = list(dict.fromkeys(
            spec.knob for cell in artifact.cells
            if (spec := _spec_for(cell["arm_id"])) is not None and spec.control is None
        ))
        lines += ["", "### What the knob probe measured on the built-in tasks", "",
                  _own_card.PROBE_SENTENCE, ""]
        lines += _own_card.probe_lines(knobs_here) or [
            "- No knob of the probe's is on this card."]
    else:
        lines += [
            "",
            "## Adjacent levels",
            "",
            "A difference is paired over the shared seeds inside each resample. A pair is "
            f"*{DISTINGUISHABLE}* only when its paired 95% interval excludes zero **and** the "
            f"difference is at least delta* = {prov.delta_star:.2f} pass-rate points; otherwise "
            f"it reads *{TOO_SMALL}*, with its difference and interval shown.",
        ]
    if artifact.reach_pairs:
        lines += [
            "",
            "### depth, on reaching the goal (leaky pass@1)",
            "",
            "How depth is read. The same pairing and rule, on the leaky rate, with saturation "
            "judged on that rate.",
            "",
            "| model | knob | levels | delta leaky pass@1 | 95% paired interval | verdict |",
            "|---|---|---|---|---|---|",
        ]
        for pair in artifact.reach_pairs:
            verdict = pair["verdict"]
            if pair["reason"] is not None:
                verdict = f"{verdict}: {pair['reason']}"
            interval = None if pair["low"] is None else (pair["low"], pair["high"])
            lines.append(
                f"| {pair['model']} | {pair['knob']} | {pair['level_a']} vs {pair['level_b']} | "
                f"{_fmt(pair['delta'])} | {_interval(interval)} | {verdict} |"
            )
        lines += ["", "### every knob, strict pass@1"]
    if not own:
        lines += [
            "",
            "| model | knob | levels | delta strict pass@1 | 95% paired interval | verdict |",
            "|---|---|---|---|---|---|",
        ]
        for pair in artifact.pairs:
            verdict = pair["verdict"]
            if pair["reason"] is not None:
                verdict = f"{verdict}: {pair['reason']}"
            interval = None if pair["low"] is None else (pair["low"], pair["high"])
            lines.append(
                f"| {pair['model']} | {pair['knob']} | {pair['level_a']} vs {pair['level_b']} | "
                f"{_fmt(pair['delta'])} | {_interval(interval)} | {verdict} |"
            )
    lines += ["", "## Ordering", ""]
    for row in artifact.orderings:
        if row["kind"] == "ordering":
            lines.append(
                f"- {row['model']}, {row['knob']}: strict pass@1 across levels "
                f"{row['levels']} is {', '.join(_fmt(rate) for rate in row['pass_at_1'])}; "
                f"non-increasing: {_fmt(row['non_increasing'])}."
            )
            lines.append(
                f"  - leaky pass@1 across levels {row['levels']} is "
                f"{', '.join(_fmt(rate) for rate in row['leaky_at_1'])}; "
                f"non-increasing: {_fmt(row['leaky_non_increasing'])}."
            )
            if row["knob"] == _DEPTH and not own:
                lines.append("  - " + _depth_stop_note(row["levels"]))
        else:
            lines.append(
                f"- {row['knob']}: {row['models'][0]} and {row['models'][1]} put the harder "
                f"level on the same side for {row['agreeing_pairs']} of {row['of']} adjacent "
                "pairs. A count, not a test."
            )
    if not artifact.orderings:
        lines.append("- No model has a cell at every level of a knob yet.")
    lines += [
        "",
        "## Provenance",
        "",
        "- models: " + "; ".join(
            f"{entry['id']}@{entry['revision']} at {entry['endpoint_host']}"
            for entry in prov.models
        ),
        "- decoding: " + ", ".join(f"{k}={prov.decoding[k]}" for k in SAMPLING_FIELDS),
        f"- S = {prov.S}, n = {prov.n}, k on the card: {', '.join(str(k) for k in k_values)}; "
        "every k up to n is in the artifact",
        f"- bootstrap: {prov.bootstrap_resamples} resamples, seed {prov.bootstrap_seed}",
        f"- delta* = {prov.delta_star}; saturation at or below {prov.saturation_low} and at or "
        f"above {prov.saturation_high}; instrument threshold {prov.instrument_threshold}; "
        f"no-call threshold {prov.no_call_threshold}",
        _budget_line(prov),
        f"- rates read on {prov.rate_read_date}",
        f"- concurrency: {_concurrency(prov)}",
    ]
    if prov.max_model_calls is not None:
        lines.append(
            f"- each episode capped at {prov.max_model_calls} model calls; an episode that "
            "reaches the cap ends as `turn_limit`, the model's own failure"
        )
    for model_id, entry in prov.serving.items():
        if entry.get("kind") == "local":
            lines.append(
                f"- {model_id} served locally: {entry['stack']} {entry['stack_version']} on "
                f"{entry['gpu']}, revision {entry['revision']}, flags "
                + " ".join(str(flag) for flag in entry["flags"])
            )
        elif entry.get("kind") == "self_served":
            lines.append(_self_served_line(model_id, entry))
        else:
            lines.append(f"- {model_id} hosted at {entry.get('endpoint_host')}")
    if claims:
        lines += _claims_block(artifact)
    return "\n".join(lines) + "\n"


def _budget_line(prov: Provenance) -> str:
    """The published design's budget as it has always been printed; a run of a plan has caps,
    not a budget, and its block records none, which prints as not recorded, never as a limit
    the run did not have."""
    tokens = prov.budget.get("tokens")
    wall = prov.budget.get("wall_clock_seconds")
    if tokens is None and wall is None:
        return f"- budget: {NOT_RECORDED}"
    return (
        f"- budget: {tokens} tokens, {wall} s wall "
        "clock, or the provider out of credit, whichever first"
    )


_SERVER_FACT_WORDS = {
    "stack_version": "version", "model_digest": "model digest", "served_model": "served model",
}


def _self_served_line(model_id: str, entry: _Mapping[str, _Any]) -> str:
    """A model the user serves: its stack and endpoint, and each fact the server reported, by
    name; or that it reported nothing."""
    reported = [str(name) for name in (entry.get("reported_by_server") or [])]
    told = "; ".join(f"{_SERVER_FACT_WORDS.get(name, name)} {entry.get(name)}" for name in reported)
    stack = entry.get("stack") or "a server of their own"
    return (
        f"- {model_id} served by its user with {stack} at {entry.get('endpoint')}; the server "
        f"reported {told if told else 'nothing'}"
    )


def render_readme_lines(artifact: Artifact) -> str:
    """The README's difficulty lines: one per level, naming the model, from the same
    artifact."""
    out: list[str] = []
    for cell in artifact.cells:
        if cell["control"]:
            continue
        low, high = cell["pass_at_1_interval"]
        out.append(
            f"- `{cell['arm_id']}`: {cell['model']} strict pass@1 {cell['pass_at_1']:.3f} "
            f"[{low:.3f}, {high:.3f}], leaky pass@1 {cell['leaky_at_1']:.3f}, overshoot "
            f"{cell['overshoot_share']:.3f}, over {cell['S_observed']} tasks at "
            f"{artifact.provenance.n} attempts each"
            + (" (incomplete)" if cell["incomplete"] else "")
        )
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# phase 1's plumbing gate
# ---------------------------------------------------------------------------


@_dc.dataclass(frozen=True)
class PlumbingVerdict:
    """What phase 1's plumbing pass found: whether it passed, why not, and every episode's
    tool calls against its arm's structural minimum."""

    passed: bool
    reasons: tuple[str, ...]
    episodes: int
    no_call: int
    reached_minimum: int
    per_episode: tuple[dict[str, _Any], ...]


def plumbing_gate(
    records: _Sequence[EpisodeRecord], tally: _Mapping[str, int] | None = None
) -> PlumbingVerdict:
    """Phase 1 passes only if the path works end to end **and** the model acted on the task.

    Every episode is scored, none carries an instrument label and the tally is empty (the
    gate phase 1 already had); every episode makes at least one tool call; and at least half
    of them reach their arm's structural minimum.  The first conditions alone passed the
    2026-09-25 re-run, whose five of six episodes asked for the record id and the entry code
    and never called a tool.
    """
    reasons: list[str] = []
    rows: list[dict[str, _Any]] = []
    for row in records:
        rows.append({
            "task_id": row.task_id, "arm_id": row.arm_id, "seed": row.seed,
            "attempt": row.attempt, "label": row.label, "tool_calls": row.sampled_calls,
            "minimum_calls": _minimum_calls(row.arm_id),
        })
    if not records:
        reasons.append("no episode was recorded")
    labelled = [row for row in records if row.label in INSTRUMENT_LABELS]
    if labelled:
        reasons.append(f"{len(labelled)} of {len(records)} episodes carry an instrument label")
    if tally and sum(tally.values()):
        reasons.append(f"the instrument tally is not empty: {dict(tally)}")
    unknown = sorted({row["arm_id"] for row in rows if row["minimum_calls"] is None})
    if unknown:
        reasons.append(f"no structural minimum for arm(s) {unknown}")
    no_call = sum(1 for row in records if _made_no_call(row))
    if no_call:
        reasons.append(f"{no_call} of {len(records)} episodes made no tool call")
    reached = sum(
        1 for row in rows
        if row["minimum_calls"] is not None and row["tool_calls"] >= row["minimum_calls"]
    )
    if records and 2 * reached < len(records):
        reasons.append(
            f"{reached} of {len(records)} episodes reached their structural minimum; at least "
            "half must"
        )
    return PlumbingVerdict(
        passed=not reasons,
        reasons=tuple(reasons),
        episodes=len(records),
        no_call=no_call,
        reached_minimum=reached,
        per_episode=tuple(rows),
    )


# ---------------------------------------------------------------------------
# what runs (CAL1 to CAL5)
# ---------------------------------------------------------------------------

_SEED_DERIVATION = "poisson-tasks/calibration/seeds/v0"
"""The declaration behind the seed list: seed `i` is the first four bytes of
`sha256("<derivation>:<i>")`, the same 32-bit shape as Proofload's, sorted."""


def _derive_seeds() -> tuple[int, ...]:
    seeds: list[int] = []
    for index in range(S):
        digest = _hashlib.sha256(f"{_SEED_DERIVATION}:{index}".encode()).digest()
        seeds.append(int.from_bytes(digest[:4], "big"))
    if len(set(seeds)) != S:
        raise RuntimeError("the seed derivation collided; change the derivation string")
    return tuple(sorted(seeds))


_SEEDS = _derive_seeds()

PILOT_SEEDS: dict[int, tuple[int, ...]] = {2: (), 3: (), 5: ()}
"""The pilot's registered seeds per stage.  The pilot declares salts and Proofload derives
their seeds at run time; none is registered yet.  The disjointness CAL1 asks for is kept by
the pilot's salt vetting against the published sixty, and by this registry once a stage's
seeds exist."""


def seed_list(spec: _ArmSpec | None = None) -> tuple[int, ...]:
    """CAL1: the same declared list at every arm."""
    return _SEEDS


def pilot_seeds(stage: int) -> tuple[int, ...]:
    if stage not in PILOT_SEEDS:
        raise ValueError(f"the pilot's seed-bearing stages are {sorted(PILOT_SEEDS)}")
    return PILOT_SEEDS[stage]


def arm_specs() -> tuple[_ArmSpec, ...]:
    """CAL2: every level of each knob through `levels(knob)`, plus both control arms."""
    out: list[_ArmSpec] = []
    for knob, controls in ((_DEPTH, D_CONTROLS), (_DISTRACTOR, R_CONTROLS)):
        for level in _levels(knob):
            out.append(_plain(knob, level))
        for level, control in controls:
            out.append(_dc.replace(_plain(knob, level), control=control))
    return tuple(out)


def check_attempts(cell: Cell, *, S: int, n: int) -> bool:
    """CAL3: the records group to exactly `S` tasks, each with `n` attempts."""
    blocks = _blocks(cell)
    if len(blocks) != S:
        raise ValueError(
            f"a cell holds S = {S} tasks with n = {n} attempts at the same task each; this "
            f"one groups to {len(blocks)} task(s).  Attempts are repeated attempts at one "
            "task, never salted apart into distinct instances."
        )
    for block in blocks:
        if len(block) != n:
            raise ValueError(
                f"task {block[0].task_id} has {len(block)} attempts, not n = {n}"
            )
    return True


def check_decoding(declared: _Mapping[str, _Any]) -> bool:
    """CAL5: every `SamplingConfig` field declared, and the decoding not deterministic."""
    missing = [name for name in SAMPLING_FIELDS if name not in declared or declared[name] is None]
    if missing:
        raise ValueError(
            "the decoding is undeclared: " + ", ".join(missing) + ".  An unset sampling "
            "field is absent from the request and the provider's own default applies."
        )
    temperature = declared["temperature"]
    if not isinstance(temperature, (int, float)) or temperature <= 0:
        raise ValueError(
            f"temperature {temperature!r} makes the n attempts one attempt repeated, so "
            "pass@k collapses onto pass@1; the decoding must not be deterministic"
        )
    return True


# ---------------------------------------------------------------------------
# the stop (CAL20)
# ---------------------------------------------------------------------------


@_dc.dataclass(frozen=True)
class BudgetVerdict:
    ok: bool
    reason: str | None


def within_budget(
    *,
    tokens: int,
    elapsed_seconds: float,
    provider_exhausted: bool,
    budget: _Mapping[str, _Any],
) -> BudgetVerdict:
    """Checked before each episode.  The run stops on whichever limit arrives first: the
    token budget, the wall clock, or the provider saying out of credit.  Every stop is
    the same clean stop: the episodes already paid for are kept and the cell is marked
    incomplete."""
    if tokens >= int(budget["tokens"]):
        return BudgetVerdict(False, "tokens")
    if elapsed_seconds >= float(budget["wall_clock_seconds"]):
        return BudgetVerdict(False, "wall_clock")
    if provider_exhausted:
        return BudgetVerdict(False, "provider_exhausted")
    return BudgetVerdict(True, None)


# ---------------------------------------------------------------------------
# instrument labels from the trace's own signals, without importing the adapter
# ---------------------------------------------------------------------------


@_dc.dataclass(frozen=True)
class EpisodeSignals:
    """What an episode carries on the stranger's path: `Episode.ok`, `Episode.errors`, and
    its trace's `has_error` and `stop_condition`."""

    ok: bool
    errors: tuple[str, ...]
    has_error: bool
    stop_condition: str | None


_MODEL_STOPS = frozenset({
    "agent_completed", "max_turns", "context_length",
    "max_input_tokens", "max_output_tokens", "max_total_tokens",
})
_DEADLINE_WORDS = ("timeout", "timed out", "deadline")


def label_from_signals(signals: EpisodeSignals) -> str | None:
    """The instrument label for an episode, or `None` when the outcome is the model's own.

    A wall-clock deadline is `wall_timeout`.  An episode that did not finish cleanly for any
    other reason ended without a completed model response, which is `api_error`.  A clean
    end is no label, and so is a stop at `max_turns` or a token limit: a model that ran out
    of budget is a fact about difficulty, and the verdict labels it.
    """
    if signals.stop_condition == "wall_timeout":
        return "wall_timeout"
    if any(word in message.lower() for message in signals.errors for word in _DEADLINE_WORDS):
        return "wall_timeout"
    if signals.has_error or not signals.ok:
        if signals.stop_condition in _MODEL_STOPS and not signals.has_error and not signals.errors:
            return None
        return "api_error"
    return None


# ---------------------------------------------------------------------------
# the tally
# ---------------------------------------------------------------------------


def record_instrument(
    run_dir: _pathlib.Path,
    *,
    task_id: str,
    seed: int,
    attempt: int,
    label: str,
    episode_id: str | None = None,
) -> None:
    """Append one instrument failure at the moment it happens, to a file the resume never
    touches.  `resume.load` rewrites `traces.jsonl` to the rows it kept and the rows it drops
    are exactly the failed ones, so a count taken from the traces afterwards is lower than
    what happened and CAL16's gate could never fire."""
    if label not in INSTRUMENT_LABELS:
        raise ValueError(f"{label!r} is not an instrument label")
    path = _pathlib.Path(run_dir) / TALLY_FILE
    row = {"task_id": task_id, "seed": seed, "attempt": attempt, "label": label}
    if episode_id is not None:
        row["episode_id"] = episode_id
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_json.dumps(row, sort_keys=True) + "\n")


def _tally_rows(run_dir: _pathlib.Path) -> list[dict[str, _Any]]:
    path = _pathlib.Path(run_dir) / TALLY_FILE
    if not path.exists():
        return []
    rows: list[dict[str, _Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(_json.loads(line))
    return rows


def read_tally(run_dir: _pathlib.Path) -> dict[str, int]:
    """The counts per instrument label."""
    out: dict[str, int] = {}
    for row in _tally_rows(run_dir):
        out[row["label"]] = out.get(row["label"], 0) + 1
    return out


# ---------------------------------------------------------------------------
# checkpoint and resume (CAL23)
# ---------------------------------------------------------------------------


def owed_after_interrupt(run_dir: _pathlib.Path, keys: _Sequence[str], n: int) -> dict[str, int]:
    """What a resume still owes per `task.hash`, by the wheel's own resume.

    Not a query: `resume.load` rewrites `traces.jsonl` to the rows it keeps, dropping the
    errored ones it owes again.  Anything that needs the failed rows reads them first (the
    tally does).  The key is `task.hash`, the wire content hash, which is stable only while
    `TaskData.idx` stays `None`."""
    from verifiers.v1.cli.eval import resume as _resume

    _, owed = _resume.load(_pathlib.Path(run_dir), list(keys), n)
    return dict(owed)


# ---------------------------------------------------------------------------
# the stranger's path (CAL21)
# ---------------------------------------------------------------------------


def _env_config(spec: _ArmSpec, seeds: _Sequence[int]) -> _Any:
    import verifiers.v1 as _vf

    return _vf.resolve_env_config(
        {"taskset": {"id": TASKSET_ID, "arm": _dc.asdict(spec), "seeds": list(seeds)}}
    )


def _sampling_fields(decoding: _Mapping[str, _Any]) -> dict[str, _Any]:
    """The `SamplingConfig` fields a declared decoding sends: every field declared, the ones
    declared `"not sent"` left out, and the token limit as `max_completion_tokens` in
    `extra_body` (the reason is at `run_config_for`).  CAL5's check applies: every field is
    declared, and the temperature is a number above zero."""
    check_decoding(decoding)
    fields: dict[str, _Any] = {
        name: decoding[name]
        for name in SAMPLING_FIELDS
        if name != "max_tokens" and decoding[name] != _NOT_SENT
    }
    limit = decoding["max_tokens"]
    if limit != _NOT_SENT:
        fields["extra_body"] = {"max_completion_tokens": int(limit)}
    return fields


def _run_dir_name(spec: _ArmSpec) -> str:
    """An arm's run folder under `output_dir`: its id made folder-safe (`depth-d1`)."""
    return _arm_id(spec).replace("/", "-").replace(":", "-").replace("@", "-")


def run_config_for(
    spec: _ArmSpec,
    *,
    model: str = MODEL_A,
    client: _Any = None,
    output_dir: _pathlib.Path | None = None,
    run_dir: str | None = None,
) -> tuple[_Any, _Any]:
    """The documented command's config and the calibration run's, so the difference is
    enumerable: exactly the seed list, `-r` and the declared sampling fields."""
    import verifiers.v1 as _vf
    from verifiers.v1.configs.cli.eval import EvalConfig

    shared: dict[str, _Any] = {"model": model, "push": False}
    if client is not None:
        shared["client"] = client
    if output_dir is not None:
        shared["output_dir"] = _pathlib.Path(output_dir)
    documented = EvalConfig(env=_env_config(spec, DOCUMENTED_SEEDS), **shared)
    if run_dir is not None:
        shared["run"] = {"name": run_dir, "dir": run_dir}
    check_decoding(DECODING)
    # The token limit goes out as `max_completion_tokens`: OpenAI's reasoning models refuse
    # `max_tokens` with a 400, and vLLM's chat endpoint takes either, reading this one first.
    # `SamplingConfig.max_tokens` serialises as `max_tokens` whichever alias fills it, so the
    # limit rides `extra_body`, which `wire_args` flattens into the request unchanged.
    declared = {name: value for name, value in DECODING.items() if name != "max_tokens"}
    calibration = EvalConfig(
        env=_env_config(spec, seed_list(spec)),
        num_rollouts=N,
        sampling=_vf.SamplingConfig(
            **declared, extra_body={"max_completion_tokens": DECODING["max_tokens"]}
        ),
        **shared,
    )
    return documented, calibration


def _flatten(node: _Any, prefix: str = "") -> dict[str, _Any]:
    out: dict[str, _Any] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            out.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    else:
        out[prefix] = node
    return out


def config_difference(documented: _Any, calibration: _Any) -> dict[str, _Any]:
    """Every field on which the two configs differ, from their serialised forms and not from
    a list of what the build expects to differ.  The run's own identity (`run.*`) is not a
    difference in what runs."""
    left = _flatten(_json.loads(documented.model_dump_json()))
    right = _flatten(_json.loads(calibration.model_dump_json()))
    out: dict[str, _Any] = {}
    for key in sorted(set(left) | set(right)):
        if key.startswith("run.") or left.get(key) == right.get(key):
            continue
        if key == "env.taskset.seeds":
            out["seeds"] = right[key]
        elif key == "num_rollouts":
            out["num_rollouts"] = right[key]
        elif key.startswith("sampling"):
            out.setdefault("sampling", {})[key.removeprefix("sampling.")] = right.get(key)
        else:
            out[key] = right.get(key)
    return out


# ---------------------------------------------------------------------------
# the runner (CAL20, CAL21, CAL23)
# ---------------------------------------------------------------------------


@_dc.dataclass(frozen=True)
class RunOutcome:
    run_dir: _pathlib.Path
    episodes_kept: int
    episodes_run: int
    episodes_owed: int
    tokens: int
    stop: BudgetVerdict | None


def _episode_errors(episode: _Any) -> list[_Any]:
    """Every error the episode carries: its own, then each trace's.  A failed model call
    lands on the trace (`Trace.errors`, `stop_condition == "error"`), not on the episode."""
    errors = list(getattr(episode, "errors", []) or [])
    for trace in getattr(episode, "traces", []) or []:
        errors.extend(getattr(trace, "errors", []) or [])
    return errors


def _episode_signals(episode: _Any) -> EpisodeSignals:
    traces = list(getattr(episode, "traces", []) or [])
    trace = traces[0] if traces else None
    return EpisodeSignals(
        ok=bool(getattr(episode, "ok", False)),
        errors=tuple(str(getattr(error, "message", error)) for error in _episode_errors(episode)),
        has_error=bool(trace.has_error) if trace is not None else True,
        stop_condition=getattr(trace, "stop_condition", None) if trace is not None else None,
    )


def _episode_tokens(episode: _Any) -> int:
    usage = getattr(episode, "usage", None)
    if usage is None:
        return 0
    return (
        int(usage.prompt_tokens)
        + int(usage.cached_input_tokens or 0)
        + int(usage.completion_tokens)
    )


_EXHAUSTED_WORDS = ("insufficient_quota", "quota", "billing", "credit", "balance")


def _provider_exhausted(episode: _Any) -> bool:
    """The provider saying out of credit: a payment-required status, or a 429
    whose message names the quota or the balance rather than the rate."""
    for error in _episode_errors(episode):
        status = getattr(error, "status_code", None)
        message = str(getattr(error, "message", "")).lower()
        if status == 402:
            return True
        if status == 429 and any(word in message for word in _EXHAUSTED_WORDS):
            return True
    return False


def _tally_failures_on_disk(run_dir: _pathlib.Path) -> int:
    """Before a resume prunes them: every failed row in `traces.jsonl` not yet in the tally
    is tallied, keyed by episode id so a second restart does not count it twice."""
    path = _pathlib.Path(run_dir) / TRACES_FILE
    if not path.exists():
        return 0
    seen = {row.get("episode_id") for row in _tally_rows(run_dir)}
    added = 0
    with path.open("rb") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = _json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or row.get("ok", False) or row.get("id") in seen:
                continue
            label = label_from_signals(_row_signals(row))
            if label is None:
                continue
            data = row.get("task", {}).get("data", {})
            record_instrument(
                run_dir, task_id=str(data.get("task_id", row.get("task", {}).get("hash"))),
                seed=int(data.get("seed", 0)), attempt=-1, label=label, episode_id=row.get("id"),
            )
            added += 1
    return added


def _row_signals(row: _Mapping[str, _Any]) -> EpisodeSignals:
    traces = row.get("traces") or []
    trace = traces[0] if traces else None
    errors = list(row.get("errors") or [])
    for entry in traces:
        errors.extend(entry.get("errors") or [])
    return EpisodeSignals(
        ok=bool(row.get("ok", False)),
        errors=tuple(str(error.get("message", "")) for error in errors),
        has_error=(not bool(trace.get("ok", False))) if trace is not None else True,
        stop_condition=trace.get("stop_condition") if trace is not None else None,
    )


async def _run_arm(config: _Any, budget: _Mapping[str, _Any]) -> RunOutcome:
    import verifiers.v1 as _vf
    from verifiers.v1.cli.eval import resume as _resume
    from verifiers.v1.cli.output import append_episode, output_path, save_config
    from verifiers.v1.cli.resume import distribute
    from verifiers.v1.episode import EvalRunInfo
    from verifiers.v1.utils.loaders import load_environment

    env = load_environment(config.env)
    tasks = list(env.taskset)
    out = _pathlib.Path(output_path(config))
    out.mkdir(parents=True, exist_ok=True)
    keys = [task.hash for task in tasks]
    if (out / TRACES_FILE).exists():
        _tally_failures_on_disk(out)
        kept, owed = _resume.load(out, keys, config.num_rollouts, env.complete)
        counts = distribute(keys, owed, config.num_rollouts)
    else:
        save_config(config, out)
        kept, owed, counts = [], {}, [config.num_rollouts] * len(tasks)
    plan = [(task, count) for task, count in zip(tasks, counts, strict=True) if count]
    attempts = {key: 0 for key in keys}
    for episode in kept:
        attempts[episode.task.hash] = attempts.get(episode.task.hash, 0) + 1
    state: dict[str, _Any] = {
        "tokens": sum(_episode_tokens(episode) for episode in kept),
        "exhausted": False, "stop": None, "run": 0,
    }
    start = _time.monotonic()
    lock = _asyncio.Lock()
    ctx = _vf.ModelContext(client=config.client, model=config.model, sampling=config.sampling)
    semaphore = _asyncio.Semaphore(config.max_concurrent or 128)

    async def on_complete(episode: _Any) -> None:
        episode.record_run(EvalRunInfo(id=config.run.id, name=config.run.name))
        await append_episode(out, episode, lock)
        attempt = attempts.get(episode.task.hash, 0)
        attempts[episode.task.hash] = attempt + 1
        state["tokens"] += _episode_tokens(episode)
        state["run"] += 1
        if _provider_exhausted(episode):
            state["exhausted"] = True
        label = label_from_signals(_episode_signals(episode))
        if label is not None:
            record_instrument(
                out, task_id=str(episode.task.data.task_id), seed=int(episode.task.data.seed),
                attempt=attempt, label=label, episode_id=episode.id,
            )

    async def guarded(slot: _Any) -> None:
        async with semaphore:
            if state["stop"] is not None:
                return
            verdict = within_budget(
                tokens=state["tokens"], elapsed_seconds=_time.monotonic() - start,
                provider_exhausted=state["exhausted"], budget=budget,
            )
            if not verdict.ok:
                state["stop"] = verdict
                return
            await env.run_slot(slot, ctx, None, on_complete)

    async with env.serving():
        planned = [slot for task, count in plan for slot in env.slots(task, count)]
        await _asyncio.gather(*(guarded(slot) for slot in planned))
    return RunOutcome(
        run_dir=out,
        episodes_kept=len(kept),
        episodes_run=state["run"],
        episodes_owed=len(planned) - state["run"],
        tokens=state["tokens"],
        stop=state["stop"],
    )


def run_arm(
    spec: _ArmSpec,
    *,
    output_dir: _pathlib.Path,
    model: str = MODEL_A,
    client: _Any = None,
    budget: _Mapping[str, _Any] | None = None,
) -> RunOutcome:
    """One arm's cell through the stranger's path, resumable and capped.

    The config is `run_config_for`'s (CAL21).  The run directory is `output_dir / <arm id>`,
    so a second call resumes the first: the failed rows on disk are tallied before the
    wheel's resume prunes them, the owed rollouts are re-run (CAL23), and the budget is
    checked before each episode is dispatched (CAL20).  Nothing is pushed.
    """
    _, config = run_config_for(
        spec,
        model=model,
        client=client,
        output_dir=output_dir,
        run_dir=_run_dir_name(spec),
    )
    return _asyncio.run(_run_arm(config, DEFAULT_BUDGET if budget is None else budget))


def _cell_config(
    spec: _ArmSpec,
    *,
    seeds: _Sequence[int],
    attempts: int,
    decoding: _Mapping[str, _Any],
    output_dir: _pathlib.Path,
    model: str,
    client: _Any,
) -> _Any:
    """The eval config of one arm's cell for the design given: `run_config_for`'s calibration
    config with the design's seeds, attempts and decoding in place of the published ones, and
    the same run folder name."""
    import verifiers.v1 as _vf
    from verifiers.v1.configs.cli.eval import EvalConfig

    run_dir = _run_dir_name(spec)
    shared: dict[str, _Any] = {
        "model": model,
        "push": False,
        "output_dir": _pathlib.Path(output_dir),
        "run": {"name": run_dir, "dir": run_dir},
    }
    if client is not None:
        shared["client"] = client
    return EvalConfig(
        env=_env_config(spec, seeds),
        num_rollouts=int(attempts),
        sampling=_vf.SamplingConfig(**_sampling_fields(decoding)),
        **shared,
    )


def run_cell(
    spec: _ArmSpec,
    *,
    seeds: _Sequence[int],
    attempts: int,
    decoding: _Mapping[str, _Any],
    output_dir: _pathlib.Path,
    model: str = MODEL_A,
    client: _Any = None,
    budget: _Mapping[str, _Any] | None = None,
) -> RunOutcome:
    """One arm's cell for any design: `run_arm` with the seeds, attempts and decoding given
    instead of the published design's (FD3).  `run_arm(spec, ...)` is `run_cell` with
    `seed_list(spec)`, `N` and `DECODING`: the same runner, the same run folder name under
    `output_dir`, the same config apart from the design, resumable and capped the same way."""
    config = _cell_config(
        spec,
        seeds=seeds,
        attempts=attempts,
        decoding=decoding,
        output_dir=output_dir,
        model=model,
        client=client,
    )
    return _asyncio.run(_run_arm(config, DEFAULT_BUDGET if budget is None else budget))


def _span_seconds(span: _Any) -> float | None:
    """A phase's `end - start`, or `None` when the phase never ended.  verifiers 0.3.1 leaves
    `end` at its `0.0` default until the phase ends; a phase that reads as ending before it
    started was not measured either."""
    if not span.end:
        return None
    seconds = float(span.end) - float(span.start)
    return seconds if seconds >= 0.0 else None


def _time_from_trace(trace: _Any) -> dict[str, _Any]:
    """The record's five optional fields, from one trace's `timing` and its first model call.

    verifiers 0.3.1 defaults every timing field to `0.0` rather than leaving it out, so a
    default has to be told from a measurement:

    * a phase whose `end` is `0.0` never ended, and none of its figures was recorded.  Model
      and harness seconds are the agent phase's two parts and are split only once it has
      ended, so they go with it;
    * a zero in an episode that made no model call is a default; a zero in an episode that
      made one was measured and stays zero.

    The first request is the first entry of `calls` alone: its prompt tokens with its cache
    reads added back, what the model was sent before its first move.  When that call carries
    no usage the figure was not recorded, and a later call's does not stand in for it.
    """
    timing = trace.timing
    calls = list(trace.calls)
    agent = _span_seconds(timing.agent)
    seconds: dict[str, float | None] = {
        "episode_seconds": agent,
        "model_seconds": None if agent is None else float(timing.agent.model.duration),
        "harness_seconds": None if agent is None else float(timing.agent.harness.duration),
        "setup_seconds": _span_seconds(timing.setup),
    }
    if not calls:
        seconds = {name: value or None for name, value in seconds.items()}
    usage = calls[0].usage if calls else None
    first = None if usage is None else (
        int(usage.prompt_tokens) + int(usage.cached_input_tokens or 0)
    )
    return {**seconds, "first_request_prompt_tokens": first}


def _replay_agrees(data: _Any, trace: _Any) -> bool:
    """Whether the observations the tool server sent are the ones the verdict replays.

    Every sampled call whose tool message carries the engine's `seq` reached the server; a
    call the harness refused is answered with the harness's own line, which carries no
    number, and is not replayed.  The calls that reached it, in the order the server numbered
    them and each under the engine name its shown name stands for, are replayed through the
    engine with the arm's planned failures, its named reads' answers and its argument check
    applied in front of it, by the one function the server and the verifier apply them with,
    and every observation must equal its tool
    message byte for byte: the adapter's own replay check, applied to a run's traces.
    """
    from poisson_tasks import surface as _surface
    from poisson_tasks.engine import init_state as _init_state
    from poisson_tasks.export import _sampled_exchanges, _seq_of, bundle_from_data
    from poisson_tasks.tasks import scenario_for as _scenario_for

    bundle = bundle_from_data(data)
    reached = sorted(
        (
            (seq, content, call)
            for content, call in _sampled_exchanges(trace)
            if (seq := _seq_of(content)) is not None
        ),
        key=lambda row: row[0],
    )
    shown = _surface.display_map(
        bundle.seed, bundle.split, bundle.arm_id, bundle.goal,
        tuple(str(tool["name"]) for tool in bundle.tools),
    )
    calls = [
        (_surface.engine_name(shown, name), arguments)
        for _seq, _content, (name, arguments) in reached
    ]
    plan = _surface.reference_plan(bundle.arm_id, shown, bundle.reference_calls)
    stated = _surface.stated_values(bundle.arm_id, shown, bundle.reference_calls)
    spread = _surface.spread_answers(
        bundle.arm_id, shown, bundle.reference_calls, bundle.reference_observations
    )
    state = _init_state(_scenario_for(bundle.seed, bundle.split), bundle.seq_start)
    counts: dict[str, int] = {}
    observations: list[str] = []
    for call in calls:
        state, counts, observation = _surface.apply_planned(
            state, counts, call, plan, stated=stated, spread=spread
        )
        observations.append(observation)
    return observations == [content for _seq, content, _call in reached]


def _gave_up_after_fault(data: _Any, trace: _Any) -> bool | None:
    """Whether the episode received an `unavailable` from a tool and never called that tool
    again, by the name it called it; `None` on an arm that plans no failure.

    A fault received is a tool message whose line carries `unavailable` as its status (the
    harness's own `error:` lines carry none).  Calling the tool again is any later sampled
    call by that name, whether or not the harness forwarded it: a model that met the failure
    and wrote its retry badly did not give up, and the bad call already shows as
    `malformed_call`.  Judged per failure received, so a tool given up on after a retry that
    failed again counts.
    """
    from poisson_tasks import surface as _surface
    from poisson_tasks.export import _sampled_exchanges, bundle_from_data

    bundle = bundle_from_data(data)
    shown = _surface.display_map(
        bundle.seed, bundle.split, bundle.arm_id, bundle.goal,
        tuple(str(tool["name"]) for tool in bundle.tools),
    )
    if not _surface.reference_plan(bundle.arm_id, shown, bundle.reference_calls):
        return None
    exchanges = _sampled_exchanges(trace)
    for index, (content, (name, _arguments)) in enumerate(exchanges):
        fields = content.split() if isinstance(content, str) else []
        if len(fields) > 1 and fields[0].isdigit() and fields[1] == _UNAVAILABLE:
            if not any(later == name for _c, (later, _a) in exchanges[index + 1 :]):
                return True
    return False


def _is_own_task(dumped: _Mapping[str, _Any]) -> bool:
    """Whether an episode's task data is an own-tools task's: it names the tool file's digest
    and the set, which no built-in task data carries."""
    return "file_digest" in dumped and "set_name" in dumped and "steps" in dumped


def _own_record(
    episode: _Any, dumped: _Mapping[str, _Any], attempts: dict[str, int], model: str
) -> EpisodeRecord:
    """One own-tools episode's record: the own verdict re-read through the own export, the
    replay check on every arm (the simulator's answers to the calls that reached the server must
    be the tool messages byte for byte), and the faults figure read from the simulator's own
    answers."""
    from poisson_tasks.export import _sampled_exchanges
    from poisson_tasks.own import simulator as _own_sim
    from poisson_tasks.own.export import OwnTaskData, _verdict, bundle_from_data

    data = OwnTaskData.model_validate(dict(dumped))
    attempt = attempts.get(episode.task.hash, 0)
    attempts[episode.task.hash] = attempt + 1
    trace = episode.traces[0] if episode.traces else None
    instrument = label_from_signals(_episode_signals(episode))
    usage = trace.usage if trace is not None else None
    gave_up: bool | None = None
    if instrument is not None or trace is None:
        strict, leaky, label = False, False, instrument or "api_error"
    else:
        reward = trace.rewards.get("strict")
        leaky_metric = trace.metrics.get("leaky_pass")
        if reward is None or leaky_metric is None:
            strict, leaky, label = False, False, "verifier_error"
        else:
            verdict = _verdict(data, trace)
            strict = float(reward.value) == 1.0
            leaky = float(leaky_metric) == 1.0
            label = verdict.strict_label
            bundle = bundle_from_data(data)
            block = {str(tool["name"]): tool for tool in bundle.tools}
            exchanges = _sampled_exchanges(trace)
            reached = [(content, call) for content, call in exchanges
                       if _own_sim.reaches_the_server(call[0], call[1], block)]
            _state, answers = _own_sim.replay(bundle, [call for _c, call in reached])
            if [answer.text for answer in answers] != [content for content, _c in reached]:
                strict, leaky, label = False, False, _REPLAY_MISMATCH
            elif strict != (label == _PASSED) or leaky != verdict.leaky_pass:
                raise ValueError(
                    f"episode {episode.id}: the recorded reward and the re-read verdict "
                    f"disagree (strict={strict}, leaky={leaky}, label={label!r})"
                )
            if bundle.fault_plan:
                gave_up = False
                for index, answer in enumerate(answers):
                    if answer.code == _UNAVAILABLE:
                        name = reached[index][1][0]
                        later = [call[0] for _c, call in exchanges][
                            exchanges.index(reached[index]) + 1:]
                        if name not in later:
                            gave_up = True
    return EpisodeRecord(
        task_id=str(data.task_id), arm_id=str(data.arm_id), model=model,
        seed=int(data.seed), attempt=attempt, strict=strict, leaky=leaky, label=label,
        turns=int(trace.num_turns) if trace is not None else 0,
        sampled_calls=int(trace.metrics.get("sampled_calls") or 0) if trace is not None else 0,
        prompt_tokens=int(usage.prompt_tokens) if usage else 0,
        cached_input_tokens=int(usage.cached_input_tokens or 0) if usage else 0,
        completion_tokens=int(usage.completion_tokens) if usage else 0,
        reasoning_tokens=int(usage.reasoning_tokens or 0) if usage else 0,
        cost=float(usage.cost) if usage and usage.cost is not None else None,
        **(_time_from_trace(trace) if trace is not None else {}),
        gave_up_after_fault=gave_up,
    )


def records_from_run(run_dir: _pathlib.Path, *, model: str) -> list[EpisodeRecord]:
    """The per-episode records of a finished run, from its `traces.jsonl`.

    `strict` and `leaky` are what the wheel scored (X4's reward and the `leaky_pass`
    metric); the outcome label is `tasks.verify`'s own verdict on the trace, re-read through the
    export so that one ordering of the sampled calls exists; an instrument label from the
    episode's signals overrides it, and so does a replay that disagrees with the tool messages
    on an arm the replay check covers (`_REPLAY_CHECKED`), which scores nothing.  Attempts
    are numbered by position in the file.  Each record's time and first request are its
    trace's (`_time_from_trace`); an episode with no trace recorded none.
    """
    import verifiers.v1 as _vf
    from verifiers.v1.cli.output import read_episodes

    from poisson_tasks.export import ExportTaskData, _verdict

    episodes = read_episodes(_pathlib.Path(run_dir), _vf.Trace)
    attempts: dict[str, int] = {}
    out: list[EpisodeRecord] = []
    for episode in episodes:
        dumped = episode.task.data.model_dump(mode="json")
        if _is_own_task(dumped):
            out.append(_own_record(episode, dumped, attempts, model))
            continue
        data = ExportTaskData.model_validate(dumped)
        attempt = attempts.get(episode.task.hash, 0)
        attempts[episode.task.hash] = attempt + 1
        trace = episode.traces[0] if episode.traces else None
        instrument = label_from_signals(_episode_signals(episode))
        usage = trace.usage if trace is not None else None
        if instrument is not None or trace is None:
            strict, leaky, label = False, False, instrument or "api_error"
        else:
            reward = trace.rewards.get("strict")
            leaky_metric = trace.metrics.get("leaky_pass")
            if reward is None or leaky_metric is None:
                strict, leaky, label = False, False, "verifier_error"
            else:
                verdict = _verdict(data, trace)
                strict = float(reward.value) == 1.0
                leaky = float(leaky_metric) == 1.0
                label = verdict.strict_label
                spec = _spec_for(str(data.arm_id))
                if (
                    spec is not None
                    and spec.knob in _REPLAY_CHECKED
                    and not _replay_agrees(data, trace)
                ):
                    strict, leaky, label = False, False, _REPLAY_MISMATCH
                elif strict != (label == _PASSED) or leaky != verdict.leaky_pass:
                    raise ValueError(
                        f"episode {episode.id}: the recorded reward and the re-read verdict "
                        f"disagree (strict={strict}, leaky={leaky}, label={label!r})"
                    )
        out.append(EpisodeRecord(
            task_id=str(data.task_id), arm_id=str(data.arm_id), model=model,
            seed=int(data.seed), attempt=attempt, strict=strict, leaky=leaky, label=label,
            turns=int(trace.num_turns) if trace is not None else 0,
            sampled_calls=int(trace.metrics.get("sampled_calls") or 0) if trace is not None else 0,
            prompt_tokens=int(usage.prompt_tokens) if usage else 0,
            cached_input_tokens=int(usage.cached_input_tokens or 0) if usage else 0,
            completion_tokens=int(usage.completion_tokens) if usage else 0,
            reasoning_tokens=int(usage.reasoning_tokens or 0) if usage else 0,
            cost=float(usage.cost) if usage and usage.cost is not None else None,
            **(_time_from_trace(trace) if trace is not None else {}),
            gave_up_after_fault=_gave_up_after_fault(data, trace) if trace is not None else None,
        ))
    return out


# ---------------------------------------------------------------------------
# one page for every calibrated model
# ---------------------------------------------------------------------------

_COMPARABLE = (
    "generator_hash", "engine_hash", "vocabulary_hash", "seed_list_hash", "S", "n",
    "decoding", "harness_id", "delta_star", "saturation_high", "saturation_low",
    "bootstrap_resamples", "bootstrap_seed", "strictness", "split", "tools",
)
"""What two cards must share to be read side by side: the same tasks, the same attempts and
decoding, the same rule for calling a difference, and the same strictness and split (an arm's
id names neither, a leaky arm scores another predicate, and the train split is other tasks; a
block for the published design leaves both unset).  Serving, budget, rates and the turn cap
are each model's own and are printed on each card.  So are time and the run's concurrency:
neither is here, and nothing on the page compares them."""

AGREE = "agree"
DISAGREE = "disagree"
CANNOT_TELL = "cannot tell"


def _models_of(artifact: Artifact) -> list[str]:
    return sorted({cell["model"] for cell in artifact.cells})


def _comparable(artifacts: _Sequence[Artifact]) -> list[Artifact]:
    """The artifacts in model order, after refusing a set that was not measured the same way
    or that holds one model twice."""
    if not artifacts:
        raise ValueError("no card to render")
    first = artifacts[0].provenance
    for artifact in artifacts[1:]:
        for name in _COMPARABLE:
            if getattr(artifact.provenance, name) != getattr(first, name):
                raise ValueError(
                    f"these cards were not measured the same way ({name} differs), so they "
                    "cannot be read side by side"
                )
    seen: dict[str, int] = {}
    for index, artifact in enumerate(artifacts):
        for model in _models_of(artifact):
            if model in seen:
                raise ValueError(f"model {model!r} has more than one card here")
            seen[model] = index
    return sorted(artifacts, key=lambda artifact: _models_of(artifact))


def agreement_rows(artifacts: _Sequence[Artifact]) -> list[dict[str, _Any]]:
    """Per knob, predicate and adjacent pair of levels, each model's own comparison and whether
    the models agree.  They agree when every card calls the pair distinguishable in the same
    direction, and disagree when every card calls it distinguishable but not all in one
    direction; otherwise at least one card cannot call it.  A raw sign is never counted."""
    ordered = _comparable(artifacts)
    tables: list[tuple[str, str, list[dict[str, _Any]]]] = []
    for knob in _KNOBS:
        if knob == _DEPTH:
            tables.append((knob, "leaky", [row for a in ordered for row in a.reach_pairs]))
        tables.append((knob, "strict",
                       [row for a in ordered for row in a.pairs if row["knob"] == knob]))
    rows: list[dict[str, _Any]] = []
    models = [model for artifact in ordered for model in _models_of(artifact)]
    for knob, predicate, pairs in tables:
        axis = _levels(knob)
        for a, b in zip(axis, axis[1:], strict=False):
            per_model = {row["model"]: row for row in pairs
                         if (row["level_a"], row["level_b"]) == (a, b)}
            if set(per_model) != set(models):
                continue
            called = [per_model[m] for m in models if per_model[m]["verdict"] == DISTINGUISHABLE]
            if len(called) < len(models):
                agreement = CANNOT_TELL
            elif len({_sign(row["delta"]) for row in called}) == 1:
                agreement = AGREE
            else:
                agreement = DISAGREE
            rows.append({
                "knob": knob, "predicate": predicate, "level_a": a, "level_b": b,
                "models": {m: {key: per_model[m][key]
                               for key in ("delta", "low", "high", "verdict", "reason")}
                           for m in models},
                "agreement": agreement,
            })
    return rows


def _table_title(knob: str, predicate: str) -> str:
    if predicate == "leaky":
        return f"{knob}, on reaching the goal (leaky pass@1)"
    return f"{knob}, strict pass@1"


def render_combined_document(artifacts: _Sequence[Artifact]) -> str:
    """`docs/calibration.md`: every calibrated model's card in full, and before them where the
    models' difficulty orderings agree, read from each card's own verdicts.  Rendered from the
    artifacts and never typed (CAL17); nothing here ranks models."""
    ordered = _comparable(artifacts)
    prov = ordered[0].provenance
    models = [model for artifact in ordered for model in _models_of(artifact)]
    rows = agreement_rows(ordered)
    lines: list[str] = [
        "# What each difficulty level is worth",
        "",
        f"Calibration cards for {len(models)} models, measured the same way: generator "
        f"`{prov.generator_hash}`, the same {prov.S} tasks from the {SPLIT} split (seed list "
        f"`{prov.seed_list_hash}`), {prov.n} attempts per task, the same decoding, and a "
        f"difference called only when its paired 95% interval excludes zero and it is at "
        f"least {prov.delta_star:.2f}. Each model's own card follows in full.",
        "",
        "Every number is one model's. This page does not rank models or pool their numbers: "
        "it says where their difficulty orderings agree.",
        "",
        "Time is each card's own. Seconds depend on the serving and on the run's concurrency "
        "as much as on the task, so this page does not compare one card's time with "
        "another's.",
        "",
        "## Where the models agree",
        "",
        f"For each pair of adjacent levels, each model's own comparison. The models *{AGREE}* "
        "when every card calls the pair distinguishable in the same direction, and "
        f"*{DISAGREE}* when every card calls it distinguishable but not in one direction. "
        f"Otherwise at least one card cannot call it (*{CANNOT_TELL}*): a level is saturated "
        "for that model, or the difference is too small for this design. A difference is "
        "level a minus level b. Depth is read on reaching the goal; the strict comparison also "
        "asks the model to stop at the goal.",
    ]
    header = ["levels"]
    for model in models:
        header += [f"{model} delta", f"{model} verdict"]
    header.append("agreement")
    for knob in _KNOBS:
        for predicate in (("leaky", "strict") if knob == _DEPTH else ("strict",)):
            table = [row for row in rows
                     if row["knob"] == knob and row["predicate"] == predicate]
            if not table:
                continue
            title = _table_title(knob, predicate)
            counts = {kind: sum(1 for row in table if row["agreement"] == kind)
                      for kind in (AGREE, DISAGREE, CANNOT_TELL)}
            lines += [
                "",
                f"### {title}",
                "",
                f"{title}: the models {AGREE} on {counts[AGREE]}, {DISAGREE} on "
                f"{counts[DISAGREE]}, and {CANNOT_TELL} on {counts[CANNOT_TELL]}, of "
                f"{len(table)} adjacent pairs.",
                "",
                "| " + " | ".join(header) + " |",
                "|" + "---|" * len(header),
            ]
            for row in table:
                values = [f"{row['level_a']} vs {row['level_b']}"]
                for model in models:
                    mine = row["models"][model]
                    values += [_fmt(mine["delta"]), mine["verdict"]]
                values.append(row["agreement"])
                lines.append("| " + " | ".join(values) + " |")
    for artifact in ordered:
        card = render_document(artifact)
        nested = "\n".join("##" + line if line.startswith("#") else line
                            for line in card.splitlines())
        lines += ["", f"## {', '.join(_models_of(artifact))}", "", nested]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# cards for any plan (FD4): a run's card, its verdict and its claims, and reading it beside
# the published cards
# ---------------------------------------------------------------------------


@_dc.dataclass(frozen=True)
class CardVerdict:
    """What a card's first line says.

    `word` is `"ok"` or `"refused"`.  `refused` names each cell that may not be published and
    the gate it fails, as `(arm id, "instrument" | "no_call")`.  `partial` is true when the card
    holds fewer scored attempts than its design asks for; `owed` counts them; `incomplete` names
    the arms whose cells are marked incomplete and `not_run` the arms the run never recorded an
    episode of, which have no cell and so no figure."""

    word: str
    model: str
    partial: bool
    owed: int
    incomplete: tuple[str, ...]
    not_run: tuple[str, ...]
    refused: tuple[tuple[str, str], ...]


@_dc.dataclass(frozen=True)
class Claims:
    """What a card says it means (`meaning`, one paragraph), what it does not claim (one line
    each), and the conditions those lines were chosen by (`flags`)."""

    meaning: str
    not_claimed: tuple[str, ...]
    flags: frozenset[str]


@_dc.dataclass(frozen=True)
class RunCard:
    """A run folder's card: every arm's records, each arm's instrument tally, and, unless the
    verdict refuses, the artifact, the document and the claims."""

    records: tuple[EpisodeRecord, ...]
    tally: _Mapping[str, _Mapping[str, int]]
    artifact: Artifact | None
    document: str | None
    claims: Claims | None
    verdict: CardVerdict


@_dc.dataclass(frozen=True)
class Comparison:
    """Whether two cards can be read side by side.  `field` is the first thing they were
    measured differently by, or `None`; `reason` says it in words; `same_model` says whether
    both measured one model; `shared_arms` are the arms both cards hold a cell of."""

    field: str | None
    reason: str | None
    same_model: bool
    shared_arms: tuple[str, ...]


# ---- a run folder, read without the run engine --------------------------------------------


def _plan_of(folder: _pathlib.Path) -> _Any:
    """The plan a run folder's `plan.json` holds, made again as `config.Plan`.  Not a run folder
    is one line naming the folder."""
    from poisson_tasks import config as _config

    try:
        held = _json.loads((folder / _PLAN_FILE).read_text(encoding="utf-8"))["plan"]
        model = dict(held["model"])
        if model.get("price") is not None:
            model["price"] = _config.PriceConfig(**model["price"])
        extra: dict[str, _Any] = {}
        if held.get("own") is not None:
            # A plan on a user's own tools carries its `own` table; `config.Plan` takes it.
            extra["own"] = dict(held["own"])
        return _config.Plan(
            preset=str(held["preset"]),
            arms=tuple(_ArmSpec(**arm) for arm in held["arms"]),
            seeds=tuple(int(seed) for seed in held["seeds"]),
            attempts=int(held["attempts"]),
            model=_config.ModelConfig(**model),
            decoding=_types.MappingProxyType(dict(held["decoding"])),
            max_model_calls=int(held["max_model_calls"]),
            **extra,
        )
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f"{folder} is not a run folder: it holds no plan") from error


def _ledger_lines(folder: _pathlib.Path) -> list[dict[str, _Any]]:
    """The whole lines of the run folder's ledger that parse; a torn or malformed line is
    skipped, as the run engine skips it."""
    path = folder / _LEDGER_FILE
    if not path.exists():
        return []
    out: list[dict[str, _Any]] = []
    for piece in path.read_bytes().splitlines(keepends=True):
        if not piece.endswith(b"\n"):
            continue
        try:
            line = _json.loads(piece)
        except ValueError:
            continue
        if isinstance(line, dict):
            out.append(line)
    return out


def _run_ids(arm_folder: _pathlib.Path) -> set[str]:
    """The ids of the runs that wrote an arm's trace lines (the wheel stamps each episode with
    its run's)."""
    path = arm_folder / TRACES_FILE
    ids: set[str] = set()
    if not path.exists():
        return ids
    for piece in path.read_bytes().splitlines(keepends=True):
        if not piece.endswith(b"\n"):
            continue
        try:
            row = _json.loads(piece)
        except ValueError:
            continue
        run = row.get("run") if isinstance(row, dict) else None
        if isinstance(run, dict) and run.get("id") is not None:
            ids.add(str(run["id"]))
    return ids


def _resumed(folder: _pathlib.Path, plan: _Any) -> bool:
    """Whether a later run of the folder made some of its attempts.  Two signs, either enough:
    an arm's trace lines stamped by more than one run, or a ledger line repeated for one
    attempt, which is an attempt run again after it failed or was cut short."""
    for spec in plan.arms:
        if len(_run_ids(folder / _run_dir_name(spec))) > 1:
            return True
    seen: set[tuple[_Any, _Any, _Any]] = set()
    for line in _ledger_lines(folder):
        key = (line.get("arm"), line.get("seed"), line.get("attempt"))
        if key in seen:
            return True
        seen.add(key)
    return False


def _run_date(folder: _pathlib.Path) -> str:
    """The day the run started, from the first dated line of its log, else from its plan file:
    the rates' date for a model with no price, read from the folder so the card recomputes."""
    log = folder / _LOG_FILE
    if log.exists():
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                return _datetime.date.fromisoformat(line[:10]).isoformat()
            except ValueError:
                continue
    stamp = (folder / _PLAN_FILE).stat().st_mtime
    return _datetime.datetime.fromtimestamp(stamp, _datetime.UTC).date().isoformat()


def _serving_entry(plan: _Any, given: _Mapping[str, _Any] | None) -> dict[str, _Any]:
    """The plan's model's serving entry.  A model of a provider the user serves is `self_served`
    at the plan's endpoint, with what `given` (a `providers.server_facts` mapping) says the
    server reported, or nothing reported; facts for another endpoint describe a server this run
    did not use and are refused.  Any other model is `hosted` at the endpoint's host and port,
    and has no server of the user's to report."""
    name = plan.model.name
    if plan.model.provider in _SELF_SERVED_PROVIDERS:
        entry: dict[str, _Any] = {
            "kind": "self_served",
            "stack": plan.model.provider,
            "endpoint": plan.model.base_url,
            "reported_by_server": [],
        }
        if given is not None:
            if given.get("endpoint") not in (None, plan.model.base_url):
                raise ValueError(
                    f"the server facts are for {given.get('endpoint')}, and this run used "
                    f"{plan.model.base_url}; a card records its own run's server"
                )
            if given.get("kind") not in (None, "self_served"):
                raise ValueError(
                    f"the server facts say {name} is {given.get('kind')!r}; a model served by "
                    "its user is self_served"
                )
            entry.update(given)
        return entry
    if given is not None:
        raise ValueError(
            f"{name} is hosted ({plan.model.provider}); it has no server of the user's whose "
            "facts a card could record"
        )
    return {"kind": "hosted", "endpoint_host": _urlparse.urlsplit(plan.model.base_url).netloc}


def _gate(cell: Cell, tally: _Mapping[str, int] | None, prov: Provenance) -> str | None:
    """The gate a cell fails, by the arithmetic `_check_cell` refuses it with: `instrument`
    when its instrument rate is over the threshold or it has no scored episode, `no_call` when
    more than the declared share of its scored episodes made no tool call; else `None`."""
    if instrument_rate(cell, tally or None) > prov.instrument_threshold:
        return "instrument"
    kept = scored(cell)
    if not kept:
        return "instrument"
    if sum(1 for row in kept if _made_no_call(row)) / len(kept) > prov.no_call_threshold:
        return "no_call"
    return None


def card_from_run(
    folder: _pathlib.Path, *, serving: _Mapping[str, _Any] | None = None
) -> RunCard:
    """The card of the run folder `folder`, built from what the run left in it and nothing
    else: per arm of its plan, in the plan's order, `records_from_run` over the arm's folder and
    the arm's instrument tally; then the artifact under `Provenance.for_plan` of that plan,
    its verdict, its claims and its document with the claims block.  It only reads the folder,
    and opens no socket: a self-served model's server facts come from `serving` or are not
    recorded.  A cell over a gate refuses the card: records and tally only, and the verdict
    names the cell and the gate.  Not a run folder, or a run that recorded no episode, is a
    `ValueError` of one line naming the folder."""
    folder = _pathlib.Path(folder)
    plan = _plan_of(folder)
    name = str(plan.model.name)
    records: list[EpisodeRecord] = []
    tally: dict[str, dict[str, int]] = {}
    cells: dict[CellKey, Cell] = {}
    tallies: dict[CellKey, _Mapping[str, int]] = {}
    for spec in plan.arms:
        arm = _arm_id(spec)
        arm_folder = folder / _run_dir_name(spec)
        tally[arm] = read_tally(arm_folder) if arm_folder.exists() else {}
        rows = (
            records_from_run(arm_folder, model=name)
            if (arm_folder / TRACES_FILE).exists() else []
        )
        records += rows
        if rows:
            cells[(arm, name)] = rows
            tallies[(arm, name)] = tally[arm]
    if not records:
        raise ValueError(f"the run folder {folder} holds no recorded episode")
    entry = _serving_entry(plan, serving)
    price = plan.model.price
    read_on = str(price.read_on) if price is not None else _run_date(folder)
    prov = Provenance.for_plan(plan, serving={name: entry}, rate_read_date=read_on)
    if _resumed(folder, plan):
        prov = _dc.replace(prov, resumed=True)
    refused = tuple(
        (arm, gate) for (arm, _), rows in cells.items()
        if (gate := _gate(rows, tallies[(arm, name)], prov)) is not None
    )
    if refused:
        design = prov.S * prov.n
        owed = sum(design - len(scored(rows)) for rows in cells.values())
        not_run = tuple(arm for arm in (prov.arms or ()) if (arm, name) not in cells)
        owed += len(not_run) * design
        verdict = CardVerdict(
            word="refused", model=name, partial=owed > 0, owed=owed, incomplete=(),
            not_run=not_run, refused=refused,
        )
        return RunCard(records=tuple(records), tally=tally, artifact=None, document=None,
                       claims=None, verdict=verdict)
    artifact = build_artifact(cells, prov, tally=tallies)
    return RunCard(
        records=tuple(records), tally=tally, artifact=artifact,
        document=render_document(artifact, claims=True), claims=card_claims(artifact),
        verdict=card_verdict(artifact),
    )


def card_verdict(artifact: Artifact) -> CardVerdict:
    """The verdict an artifact's own cells and provenance give, so a card read back from its
    files says what its first line said.  A cell is refused by the share its figures already
    carry against the thresholds its block declares.  What is owed is every attempt the design
    asks for that no cell holds a scored record of: the shortfall of each cell, and the whole
    design of each arm the plan asked for that has no cell, which is listed as not run."""
    prov = artifact.provenance
    models = sorted({str(cell["model"]) for cell in artifact.cells})
    if not models:
        raise ValueError("the artifact holds no cell, so there is no card to judge")
    refused: list[tuple[str, str]] = []
    for cell in artifact.cells:
        if cell["instrument_rate"] > prov.instrument_threshold:
            refused.append((str(cell["arm_id"]), "instrument"))
        elif cell["no_call_share"] > prov.no_call_threshold:
            refused.append((str(cell["arm_id"]), "no_call"))
    design = prov.S * prov.n
    held = {str(cell["arm_id"]) for cell in artifact.cells}
    not_run = tuple(arm for arm in (prov.arms or ()) if arm not in held)
    owed = sum(max(0, design - int(cell["episodes_scored"])) for cell in artifact.cells)
    owed += len(not_run) * design
    incomplete = tuple(str(cell["arm_id"]) for cell in artifact.cells if cell["incomplete"])
    return CardVerdict(
        word="refused" if refused else "ok", model=models[0], partial=owed > 0, owed=owed,
        incomplete=incomplete, not_run=not_run, refused=tuple(refused),
    )


# ---- the claims (FD4.4) ---------------------------------------------------------------------


@_functools.cache
def _package_generator_hash() -> str:
    """The generator hash this install's package gives: what a card is stale against."""
    return str(_generate(arm_specs()[0], seed_list()[0]).generator_hash)


@_functools.cache
def _published_blocks() -> tuple[tuple[Provenance, frozenset[str]], ...]:
    """Each published card's provenance block and the arms it holds a cell of, read from the
    artifact it ships as (`cards.published`); empty where an install has no cards."""
    from poisson_tasks import cards as _cards

    out: list[tuple[Provenance, frozenset[str]]] = []
    for card in _cards.published():
        stored = _json.loads((card.folder / "artifact.json").read_text(encoding="utf-8"))
        out.append((Provenance(**stored["provenance"]),
                    frozenset(str(cell["arm_id"]) for cell in stored["cells"])))
    return tuple(out)


def _differing(a: Provenance, b: Provenance) -> list[str]:
    """The fields of `_COMPARABLE` two blocks differ in, in that tuple's order."""
    return [name for name in _COMPARABLE if getattr(a, name, None) != getattr(b, name, None)]


def _where(prov: Provenance, model: str) -> str:
    """Where the model was served, in words: the endpoint of a model the user serves, the stack
    and machine of one served locally, the host and port of a hosted one."""
    entry = dict(prov.serving.get(model) or {})
    kind = entry.get("kind")
    if kind == "self_served":
        return f"served by its user at {entry.get('endpoint')}"
    if kind == "local":
        return (
            f"served locally with {entry.get('stack')} {entry.get('stack_version')} on "
            f"{entry.get('gpu')}"
        )
    host = entry.get("endpoint_host") or prov.model_entry(model).get("endpoint_host")
    return f"hosted at {host}"


_LINE_ALWAYS = (
    "It is one model's result on these tasks: it ranks no models, and it says nothing about "
    "another model or about tasks other than these."
)
_LINE_NOT_COMPARABLE = (
    "It is not comparable with the published cards: it was not measured the same way, so none "
    "of its figures reads against theirs."
)
_LINE_NOT_COVERED = (
    "No published card covers this plan: none holds any of its levels, so nothing here can "
    "be read beside a published figure."
)
_LINE_SELF_SERVED = (
    "Its model was served by its user: how it was served is not pinned beyond what the server "
    "reported, so a later run of the same weights served differently is not the same "
    "measurement."
)
_LINE_DISTRACTOR = (
    "The distractor knob is experimental: it did not make tasks harder for either calibrated "
    "model."
)
_LINE_STALE = (
    "It is pinned to the generator it was made with, which is not the one this install has, so "
    "it is stale."
)
_LINE_RESUMED = (
    "Some of its attempts were made by a later run of its folder: a resumed attempt is a fresh "
    "attempt, not a copy of the one it replaces."
)


def card_claims(artifact: Artifact) -> Claims:
    """What the card means and what it does not claim, rendered from the artifact.

    The meaning names the model, where it was served, and the design's tasks and attempts per
    level, and says how a rate and a difference are read.  Each not-claimed line follows one
    condition, read from the block and the cells against the published cards' blocks: fewer
    tasks per level than they have (`small_sample`); not measured as they were
    (`not_comparable`); a model the user serves (`self_served`); a distractor cell
    (`distractor`); a generator other than the package's (`stale`); attempts from a later run
    of the folder (`resumed`); no published card holding any of its levels (`not_covered`).
    The first line, that it is one model's result and ranks nothing, needs no condition."""
    prov = artifact.provenance
    models = sorted({str(cell["model"]) for cell in artifact.cells})
    model = models[0] if models else str(prov.models[0]["id"])
    arms = {str(cell["arm_id"]) for cell in artifact.cells}
    if prov.tools is not None:
        return _own_claims(artifact, model)
    published = _published_blocks()
    flags: set[str] = set()
    if published and prov.S < min(other.S for other, _ in published):
        flags.add("small_sample")
    if published and any(_differing(prov, other) for other, _ in published):
        flags.add("not_comparable")
    if any(dict(entry).get("kind") == "self_served" for entry in prov.serving.values()):
        flags.add("self_served")
    if any((spec := _spec_for(arm)) is not None and spec.knob == _DISTRACTOR for arm in arms):
        flags.add("distractor")
    if prov.generator_hash != _package_generator_hash():
        flags.add("stale")
    if prov.resumed:
        flags.add("resumed")
    if published and not any(arms & held for _, held in published):
        flags.add("not_covered")
    meaning = (
        f"This card is {model}, {_where(prov, model)}, over {prov.S} "
        f"task{'' if prov.S == 1 else 's'} per level with {prov.n} "
        f"attempt{'' if prov.n == 1 else 's'} at each. A rate is the share of this model's "
        "attempts on these tasks that reached the goal and stopped there (strict) or reached it "
        "at all (leaky). Each interval resamples tasks. Two levels are called different only "
        "when the paired interval excludes zero and the gap is at least "
        f"{prov.delta_star:.2f}."
    )
    if published and "not_comparable" not in flags:
        meaning += (
            " It was measured the same way as the published cards and can be read beside them."
        )
    lines = [_LINE_ALWAYS]
    if "small_sample" in flags:
        fewest = min(other.S for other, _ in published)
        lines.append(
            f"With fewer than the published {fewest} tasks per level, the intervals are wide "
            "and most pairs of levels will read too small to call; that is the design's "
            "resolution, not evidence that the levels are the same."
        )
    for flag, line in (
        ("not_comparable", _LINE_NOT_COMPARABLE), ("not_covered", _LINE_NOT_COVERED),
        ("self_served", _LINE_SELF_SERVED), ("distractor", _LINE_DISTRACTOR),
        ("stale", _LINE_STALE), ("resumed", _LINE_RESUMED),
    ):
        if flag in flags:
            lines.append(line)
    return Claims(meaning=meaning, not_claimed=tuple(lines), flags=frozenset(flags))


_OWN_LINES = (
    ("own_backend", (
        "It says nothing about your real tools' outputs, errors or latency, or about your app: "
        "every response in these episodes was simulated from your schemas."
    )),
    ("own_not_comparable", (
        "It is not comparable with the published cards or with built-in runs: the tasks differ, "
        "so none of its figures reads against theirs."
    )),
    ("own_levels", (
        "Within this card, levels compare with each other; across two cards, only when the tool "
        "file, the settings and the seeds are the same."
    )),
    ("own_word_match", (
        "Without an intent for every tool, choosing a tool was partly a word match with its "
        "description."
    )),
    ("own_no_effect", (
        "A knob that shows no effect here may still matter in your app, and the reverse."
    )),
)


def _own_claims(artifact: Artifact, model: str) -> Claims:
    """What an own-tools card means and does not claim (own-tools spec §9): its lines are
    `_OWN_LINES`, every one that applies, `stale` against the own-tools generator, and the
    self-served and resumed lines as on any card; none of the published cards' comparisons."""
    from poisson_tasks.own import generator as _own_generator

    prov = artifact.provenance
    tools = dict(prov.tools or {})
    flags: set[str] = {"own_backend", "own_not_comparable", "own_levels", "own_no_effect"}
    if len(list(tools.get("intents") or [])) < int(tools.get("tools") or 0):
        flags.add("own_word_match")
    if any(dict(entry).get("kind") == "self_served" for entry in prov.serving.values()):
        flags.add("self_served")
    if prov.generator_hash != _own_generator.generator_hash():
        flags.add("stale")
    if prov.resumed:
        flags.add("resumed")
    meaning = (
        f"This card is {model}, {_where(prov, model)}, on your tools ({tools.get('name')}, "
        f"{tools.get('tools')} tool{'' if tools.get('tools') == 1 else 's'}) with responses "
        f"simulated from your schemas, over {prov.S} task{'' if prov.S == 1 else 's'} per level "
        f"with {prov.n} attempt{'' if prov.n == 1 else 's'} at each. A rate is the share of this "
        "model's attempts on these tasks that reached the goal with no other change and ended "
        "with a reply (strict) or reached it at all (leaky). Each interval resamples tasks. A "
        "level is called different from its knob's first level only when the paired interval "
        f"excludes zero and the gap is at least {prov.delta_star:.2f}."
    )
    lines = [line for flag, line in _OWN_LINES if flag in flags]
    for flag, line in (("self_served", _LINE_SELF_SERVED), ("stale", _LINE_STALE),
                       ("resumed", _LINE_RESUMED)):
        if flag in flags:
            lines.append(line)
    return Claims(meaning=meaning, not_claimed=tuple(lines), flags=frozenset(flags))


def _claims_block(artifact: Artifact) -> list[str]:
    """The lines a run's card carries after its provenance: what ran, when the card is partial
    (what it owes, the levels not run, the levels incomplete); what it means; what it does not
    claim.  An insertion: the published renderer's lines are not touched."""
    verdict = card_verdict(artifact)
    claims = card_claims(artifact)
    prov = artifact.provenance
    out: list[str] = []
    if verdict.partial:
        design = prov.S * prov.n
        asked = len(prov.arms) if prov.arms else len(artifact.cells)
        cells = {str(cell["arm_id"]): cell for cell in artifact.cells}
        out += [
            "",
            "## What ran",
            "",
            f"This card is partial: the run owes {verdict.owed} of the {design * asked} attempts "
            "its design asks for, and a run of the same plan in the same folder makes them.",
        ]
        out += [f"- `{arm}` was not run: it has no figures." for arm in verdict.not_run]
        out += [
            f"- `{arm}` is incomplete: {cells[arm]['episodes_scored']} of {design} attempts "
            f"over {cells[arm]['S_observed']} of {cells[arm]['S_declared']} tasks."
            for arm in verdict.incomplete
        ]
    out += ["", "## What this card means", "", claims.meaning, "", "## What it does not claim", ""]
    out += [f"- {line}" for line in claims.not_claimed]
    return out


# ---- reading a card beside the published ones (FD4.5, FD4.6) -------------------------------


def _bare(model: str) -> str:
    """A model's id without its `@revision`: how a run names the model a card recorded with
    one."""
    return model.split("@", 1)[0]


_RULE_FIELDS = {
    "delta_star": "the smallest difference called",
    "saturation_high": "the upper saturation bound",
    "saturation_low": "the lower saturation bound",
    "bootstrap_resamples": "the number of resamples",
    "bootstrap_seed": "the resampling seed",
}


def _differs(field: str, a: Provenance, b: Provenance) -> str:
    """One line saying what the first differing field means."""
    if field == "tools":
        return "the tasks differ: a card on a user's own tools is read on its own"
    if field == "generator_hash":
        return "the generators differ: the cards' tasks were made by different generator versions"
    if field == "engine_hash":
        return "the domains differ: the cards' tasks were made over different engines"
    if field == "vocabulary_hash":
        return "the vocabularies differ: the cards' tasks were worded from different tables"
    if field in ("seed_list_hash", "S"):
        if a.S != b.S:
            return (
                f"the seed lists differ: one card used {a.S} tasks per level and the other "
                f"{b.S}"
            )
        return "the seed lists differ: the cards did not use the same tasks"
    if field == "n":
        return f"the attempts differ: one card made {a.n} per task and the other {b.n}"
    if field == "decoding":
        return "the decoding differs: the cards did not send the same sampling settings"
    if field == "harness_id":
        return "the harnesses differ: the cards' episodes were run through different harnesses"
    if field == "strictness":
        return (
            f"the strictness differs: one card scores {a.strictness or 'strict'} arms and the "
            f"other {b.strictness or 'strict'}"
        )
    if field == "split":
        return (
            f"the splits differ: one card's tasks are from the {a.split or SPLIT} split and the "
            f"other's from the {b.split or SPLIT}"
        )
    return f"the rule for calling a difference differs: {_RULE_FIELDS.get(field, field)}"


def comparable(a: Artifact, b: Artifact) -> Comparison:
    """Whether `a` and `b` were measured the same way, and what they share: the first field of
    `_COMPARABLE` they differ in, said in words, or none; whether both measured one model
    (matched without a revision); and the arms both hold a cell of, in `a`'s order."""
    differ = _differing(a.provenance, b.provenance)
    field = differ[0] if differ else None
    a_models = {_bare(str(cell["model"])) for cell in a.cells}
    b_models = {_bare(str(cell["model"])) for cell in b.cells}
    b_arms = {str(cell["arm_id"]) for cell in b.cells}
    return Comparison(
        field=field,
        reason=None if field is None else _differs(field, a.provenance, b.provenance),
        same_model=a_models == b_models,
        shared_arms=tuple(str(cell["arm_id"]) for cell in a.cells if cell["arm_id"] in b_arms),
    )


def _verdict_words(verdict: CardVerdict) -> str:
    if verdict.word == "refused":
        return "refused: " + ", ".join(f"{arm} ({gate})" for arm, gate in verdict.refused)
    if verdict.partial:
        return f"partial, {verdict.owed} attempts owed"
    return "complete"


def render_side_by_side(cards: _Mapping[str, Artifact]) -> str:
    """Cards keyed by a label, each read on its own verdicts, side by side: one table per level
    more than one card holds, a row per card, and each card's own adjacent-level calls.  Nothing
    is pooled.  Refused in one line naming the two labels when `comparable` names a field for
    any pair, or when a pair shares no level, since nothing can be read side by side there."""
    labels = list(cards)
    if not labels:
        raise ValueError("no card to render")
    for index, first in enumerate(labels):
        for second in labels[index + 1:]:
            answer = comparable(cards[first], cards[second])
            if answer.field is not None:
                raise ValueError(
                    f"{first} and {second} cannot be read side by side: {answer.reason}")
            if not answer.shared_arms:
                raise ValueError(
                    f"{first} and {second} cannot be read side by side: no level is on both")
    prov = cards[labels[0]].provenance
    lines: list[str] = [
        "# Cards side by side",
        "",
        f"{len(labels)} cards measured the same way: generator `{prov.generator_hash}`, the same "
        f"{prov.S} tasks per level from the {prov.split or SPLIT} split (seed list "
        f"`{prov.seed_list_hash}`), {prov.n} attempts per task, the same decoding, and a "
        "difference called only when its paired 95% interval excludes zero and it is at least "
        f"{prov.delta_star:.2f}.",
        "",
        "Every number is one card's own, read from that card's artifact. Nothing here pools or "
        "ranks: a level is shown where more than one card holds it, one row per card, and a "
        "card's time is not compared with another's.",
        "",
        "## Cards",
        "",
    ]
    for label in labels:
        artifact = cards[label]
        verdict = card_verdict(artifact)
        lines.append(
            f"- **{label}**: {verdict.model}, {_where(artifact.provenance, verdict.model)}; "
            f"{_verdict_words(verdict)}"
        )
    held: dict[str, list[str]] = {}
    for label in labels:
        for cell in cards[label].cells:
            held.setdefault(str(cell["arm_id"]), []).append(label)
    shared = [arm for arm, who in held.items() if len(who) > 1]
    alone = [arm for arm, who in held.items() if len(who) == 1]
    lines += ["", "## Levels", ""]
    if alone:
        lines += [
            "On one card only, so not shown here: "
            + ", ".join(f"`{arm}` ({held[arm][0]})" for arm in alone) + ".",
            "",
        ]
    header = (
        "| level | card | model | strict pass@1 | 95% interval | leaky pass@1 | leaky 95% "
        "interval | overshoot | tasks | attempts | incomplete |"
    )
    rule = "|" + "---|" * 11
    for arm in shared:
        lines += ["", f"### `{arm}`", "", header, rule]
        for label in held[arm]:
            cell = next(c for c in cards[label].cells if c["arm_id"] == arm)
            lines.append(
                f"| `{arm}` | {label} | {cell['model']} | {_fmt(cell['pass_at_1'])} | "
                f"{_interval(cell['pass_at_1_interval'])} | {_fmt(cell['leaky_at_1'])} | "
                f"{_interval(cell['leaky_at_1_interval'])} | {_fmt(cell['overshoot_share'])} | "
                f"{cell['S_observed']} of {cell['S_declared']} | {cell['n_declared']} | "
                f"{_fmt(cell['incomplete'])} |"
            )
    pair_rows: list[str] = []
    for label in labels:
        artifact = cards[label]
        for predicate, pairs in (("leaky", artifact.reach_pairs), ("strict", artifact.pairs)):
            for pair in pairs:
                a_arm = f"{pair['knob']}:{_level_id(pair['knob'], pair['level_a'])}"
                b_arm = f"{pair['knob']}:{_level_id(pair['knob'], pair['level_b'])}"
                if a_arm not in shared or b_arm not in shared:
                    continue
                call = str(pair["verdict"])
                if pair["reason"] is not None:
                    call = f"{call}: {pair['reason']}"
                interval = None if pair["low"] is None else (pair["low"], pair["high"])
                pair_rows.append(
                    f"| {label} | {pair['knob']} | {predicate} | {pair['level_a']} vs "
                    f"{pair['level_b']} | {_fmt(pair['delta'])} | {_interval(interval)} | "
                    f"{call} |"
                )
    lines += [
        "",
        "## Adjacent levels, each card's own call",
        "",
        "Each row is one card's comparison of two adjacent levels both cards hold, by its own "
        f"paired interval and delta* = {prov.delta_star:.2f}; depth is read on leaky pass@1. "
        "No row pools cards or says the cards agree.",
        "",
        "| card | knob | predicate | levels | delta | 95% paired interval | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += pair_rows if pair_rows else ["| | | | no two adjacent levels are on more than "
                                           "one card | | | |"]
    return "\n".join(lines) + "\n"


def _level_id(knob: str, level: int) -> str:
    """A knob's level as its arm id's level part (`d3`, `r2@k16`), from the arm an id names."""
    try:
        return _arm_id(_plain(knob, level)).split(":", 1)[1]
    except ValueError:
        return str(level)
