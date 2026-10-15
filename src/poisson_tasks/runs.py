"""Runs: what a plan will cost, the folder it runs in, and the run itself, with its cap, its
ledger, Ctrl-C, the start-up watchdog and the failure-streak stop.

The library side of `poisson-tasks run` (spec §8).  The CLI shows the estimate, asks, and prints
the result; everything it shows comes from here.  `tests/test_fd3_*.py` say what each name does.

**The order a run takes** (spec §8.1): `config.resolve_plan`, then `find_run`, then the free key
check (`providers.check_key`), then `estimate`; nothing is sent to the model before `run_plan`.

**The estimate** (spec §8.2) is read from the published cards' records: the card whose records
name the plan's model (matched without its `@revision`), else model A's, or the one `reference`
names.  Until the cards ship inside the wheel, the records are read from `poisson_tasks/cards/`
when it is there and otherwise from the checkout's `calibration/` folder beside the package.

**The run folder** (spec §8.5) is `runs/<preset>-<model>/`, then `-2`, `-3`, with no hash in its
name.  It holds `plan.json` (the resolved plan and its `plan_hash`, by which the folder that holds
a plan is found), `spend.jsonl` (the ledger: one line per episode that ended), `run.log`, and one
wheel run folder per arm, named as `calibration.run_arm` names it (`depth-d1/`).  `find_run` only
reads: whether a folder is complete is read off the whole, well-formed `ok` rows of each arm's
`traces.jsonl`, never by asking the wheel's resume, which rewrites the file.

**The cap is a bound** (spec §8.4): the final spend is at most the cap plus the cost of the model
calls in flight when it was reached.  Model calls pass through verifiers' interception server in
the run's own process (`EvalClient.get_response`), so the run checks the cap before each call,
and the bound is c calls at concurrency c.  Before an episode is dispatched, the measured spend
plus a reservation for each episode in flight must stay within the cap; the reservation is the
largest episode this folder has seen, and before any, the published card's 95th percentile for
the arm.  A call the cap refuses ends its episode: that episode is not recorded, not an
instrument failure and owed again, and what its earlier calls cost goes in the ledger.

**The ledger** is this package's own file and is append only: a torn last line, left by a process
that died while writing it, is dropped when the ledger is opened, and every whole line keeps its
bytes.  A run in flight is accounted call by call, and the ledger's total plus the calls in flight
is what the cap is checked against, so the cap holds the folder's total across every `run`.

**Ctrl-C** (spec §8.5): the first interrupt stops dispatching and gives the episodes in flight up
to 10 seconds to finish and be recorded; a second stops at once, and `run_plan` then raises
`KeyboardInterrupt` once nothing it started is running.  Both reach the run through the event
loop's own signal handler, installed for the run's length when the run is in the main thread.

**Stops** (spec §8.7): the spend or token cap; the provider out of credit; five episodes in a row
failed before any was scored, and a run whose every episode failed is never done; and no model
call and no finished episode within the watchdog's limit, which stops the run and whatever it
started, quoting the last lines of `run.log`.

**The key** never shows, and nothing else is masked.  A key's public prefix, the one every key of
its kind starts with (`sk-proj-`), is not secret; what follows it is the secret part.  Where a
provider can put the key, the texts that can carry it, every run of four or more characters of the
secret part is masked: each provider error a trace records (its message and its traceback), the
first error the run reports, and every line of `run.log`.  Every other byte of a trace line is the
wheel's own, as the run produced it, even where it happens to share characters with the key (the
tasks' item codes hold `-pro`, as every `sk-proj-` key does).  A run of twelve or more characters of
the secret part is the key's: no text a run makes for itself holds one by chance, so a trace line
that holds one anywhere else is masked there too, string by string, and stays JSON.

**The machine** (spec §8.6): the harness's environment carries `PIP_REQUIRE_VIRTUALENV=1` and
`UV_NO_MODIFY_PATH=1`, set in this process for the run's length.

**A plan on the user's own tools** (own-tools spec §8, §11) runs the same way: its eval config
names the taskset `poisson-tasks-own` and carries the plan's `own` whole, its `plan.json` holds
`own`, its task hashes are the own export's, and its estimate scales the published card's
per-call figures by each task's block over the built-in block (ruled 2026-10-13, yes/no 28).
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import functools
import json
import logging
import os
import re
import signal
import statistics
import threading
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from poisson_tasks import calibration
from poisson_tasks.config import Plan, PriceConfig, plan_hash
from poisson_tasks.knobs import ArmSpec, arm_id
from poisson_tasks.providers import _secret_part

__all__ = [
    "Estimate",
    "estimate",
    "RunFolder",
    "find_run",
    "RunResult",
    "run_plan",
    "SpendLedger",
    "verifiers_config",
    "own_bundles",
]

_logger = logging.getLogger(__name__)

_PLAN_FILE = "plan.json"
_LEDGER_FILE = "spend.jsonl"
_LOG_FILE = "run.log"
_TRACES_FILE = calibration.TRACES_FILE
_NOT_SENT = "not sent"
_GRACE_SECONDS = 10.0
"""How long the first Ctrl-C lets the episodes in flight finish (spec §8.5)."""
_STREAK = 5
"""Failed episodes in a row, before any was scored, that stop a run (spec §8.7)."""
_LOG_TAIL_LINES = 20
_MASK = "****"
_MASKED_RUN = 4
"""In a text that can carry the key, a run of this many characters of its secret part is masked."""
_KEY_RUN = 12
"""A run of this many characters of the key's secret part is the key's, wherever it is."""
_RESERVATION_QUANTILE = 0.95

# The published cards by their short names (ruled 2026-10-03, spec §4.4) and the folders their
# records live in.  FD4's `cards.published()` takes this over.
_CARDS: dict[str, str] = {
    "gpt-5-nano": "gpt-5-nano-2025-08-07",
    "qwen3-8b": "qwen3-8b-b968826d",
}
_MODEL_A_CARD = "gpt-5-nano"

_EPS = 1e-12


# ---------------------------------------------------------------------------
# the estimate (spec §8.2)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Estimate:
    """What a plan is expected to cost, from a published card's records.

    `episodes` = arms × seeds × attempts; `calls_min` sums each task's reference turns (its
    reference solution's tool calls and a reply) over the plan's tasks and attempts;
    `calls_at_cap` = episodes × the turn cap; `calls_expected`, `tokens_expected` and
    `dollars_expected` are the card's per-arm means (over every record of the arm) times the
    plan's counts, the dollars at the plan's prices through `calibration.dollars`, `None`
    without a price.  `source` is the card's short name (`gpt-5-nano` or `qwen3-8b`), and
    `same_model` says whether that card measured the plan's model.
    """

    episodes: int
    calls_min: int
    calls_expected: float
    calls_at_cap: int
    tokens_expected: float
    dollars_expected: float | None
    source: str
    same_model: bool


def _cards_root() -> Path:
    """Where the published cards' records are read from: inside the package once they ship
    there, and until then the checkout's `calibration/` folder beside the package's source."""
    package = Path(__file__).resolve().parent
    shipped = package / "cards"
    if shipped.is_dir():
        return shipped
    return package.parents[1] / "calibration"


@functools.cache
def _card_records(name: str) -> tuple[Any, ...]:
    """Every record of the published card `name`, read once per process.  An install without
    the records (a wheel built before the cards ship inside it) is a `FileNotFoundError` of one
    line naming where they were looked for."""
    if name not in _CARDS:
        raise ValueError(f"{name!r} is not a published card; the cards are " + ", ".join(_CARDS))
    path = _cards_root() / _CARDS[name] / calibration.RECORDS_FILE
    if not path.is_file():
        raise FileNotFoundError(
            f"the published {name} card's records are not in this install (looked for {path}); "
            "until the cards ship inside the package, run from a checkout of the repository"
        )
    return tuple(calibration.read_records(path))


def _card_model(records: Sequence[Any]) -> str:
    """The model a card measured, without its `@revision`."""
    return str(records[0].model).split("@", 1)[0]


def _card_for(model: str) -> str:
    """The published card of `model`, or model A's card for a model no card measured."""
    for name in _CARDS:
        if _card_model(_card_records(name)) == model:
            return name
    return _MODEL_A_CARD


def _figures(row: Any) -> dict[str, int]:
    return {
        "prompt_tokens": int(row.prompt_tokens),
        "cached_input_tokens": int(row.cached_input_tokens),
        "completion_tokens": int(row.completion_tokens),
    }


def _rates(price: PriceConfig | None) -> dict[str, float] | None:
    if price is None:
        return None
    return {
        "input_rate": float(price.input),
        "cached_input_rate": float(price.cached_input),
        "output_rate": float(price.output),
    }


def _arm_records(records: Sequence[Any], spec: ArmSpec, card: str) -> list[Any]:
    """The card's records of an arm, matched by the arm's id: a leaky arm, or one at another
    generator version, is estimated from the card's arm of the same id."""
    rows = [row for row in records if row.arm_id == arm_id(spec)]
    if not rows:
        raise ValueError(f"the {card} card has no records of the arm {arm_id(spec)}")
    return rows


def _reference_turns(spec: ArmSpec, seed: int) -> int:
    """A task's structural minimum of model calls: its reference solution's tool calls and
    the reply that ends the episode."""
    from poisson_tasks.tasks import generate

    return len(generate(spec, seed).reference_calls) + 1


def estimate(plan: Plan, *, reference: str | None = None) -> Estimate:
    """The plan's estimate, from the published card of the plan's model (matched without the
    card's `@revision`), else model A's; or from the card `reference` names.  A name that is not
    a published card's is a `ValueError`.  Opens no socket and writes no file."""
    name = reference if reference is not None else _card_for(plan.model.name)
    records = _card_records(name)
    rates = _rates(plan.model.price)
    per_task = len(plan.seeds) * plan.attempts
    episodes = len(plan.arms) * per_task
    if plan.own is not None:
        return _own_estimate(plan, name, records, rates, episodes)
    calls_min = (
        sum(_reference_turns(spec, seed) for spec in plan.arms for seed in plan.seeds)
        * plan.attempts
    )
    calls = tokens = dollars = 0.0
    for spec in plan.arms:
        rows = _arm_records(records, spec, name)
        calls += statistics.fmean(row.turns for row in rows) * per_task
        tokens += statistics.fmean(sum(_figures(row).values()) for row in rows) * per_task
        if rates is not None:
            each = [calibration.dollars(_figures(row), rates) or 0.0 for row in rows]
            dollars += statistics.fmean(each) * per_task
    return Estimate(
        episodes=episodes,
        calls_min=calls_min,
        calls_expected=calls,
        calls_at_cap=episodes * plan.max_model_calls,
        tokens_expected=tokens,
        dollars_expected=dollars if rates is not None else None,
        source=name,
        same_model=_card_model(records) == plan.model.name,
    )


def _own_estimate(
    plan: Plan, name: str, records: Sequence[Any], rates: Mapping[str, float] | None, episodes: int
) -> Estimate:
    """The estimate of a plan on the user's own tools (own-tools spec §8.1; ruled 2026-10-13,
    yes/no 28): per model call, the published card's mean figures over all its records (prompt,
    cached input and completion tokens, each summed and divided by the card's model calls); per
    task, its reference turns (the reference calls and the reply) times those figures, the prompt
    and the cached input scaled by the task's block tokens over the built-in block's (the tools of
    `depth:d1` at the first published seed, both as JSON in the reference tokenizer), the output
    not scaled; the dollars at the plan's prices; summed over the plan's tasks and attempts."""
    from poisson_tasks.arms import arm_from_id
    from poisson_tasks.tasks import generate
    from poisson_tasks.tokenizer import count_tokens

    fields = ("prompt_tokens", "cached_input_tokens", "completion_tokens")
    card_calls = sum(int(row.turns) for row in records)
    per_call = {
        field: (sum(float(getattr(row, field)) for row in records) / card_calls if card_calls
                else 0.0)
        for field in fields
    }
    built_in = count_tokens(
        json.dumps(list(generate(arm_from_id("depth:d1"), calibration.seed_list()[0]).tools))
    )
    calls = tokens = dollars = 0.0
    calls_min = 0
    for spec in plan.arms:
        for bundle in own_bundles(plan, spec, plan.seeds):
            turns = len(bundle.reference_calls) + 1
            scale = count_tokens(json.dumps(list(bundle.tools))) / built_in
            figures = {
                field: per_call[field] * turns * (scale if field in fields[:2] else 1.0)
                for field in fields
            }
            calls_min += turns * plan.attempts
            calls += turns * plan.attempts
            tokens += sum(figures.values()) * plan.attempts
            if rates is not None:
                dollars += (calibration.dollars(figures, rates) or 0.0) * plan.attempts
    return Estimate(
        episodes=episodes,
        calls_min=calls_min,
        calls_expected=calls,
        calls_at_cap=episodes * plan.max_model_calls,
        tokens_expected=tokens,
        dollars_expected=dollars if rates is not None else None,
        source=name,
        same_model=_card_model(records) == plan.model.name,
    )


def _reservation(plan: Plan, spec: ArmSpec) -> tuple[float, int]:
    """What one episode of `spec` is reserved before any episode of the folder has been seen:
    the published card's 95th percentile of the arm's episodes, in dollars at the plan's prices
    (zero without a price) and in tokens (spec §8.4).  Without the card's records (an install
    the cards do not ship in yet) nothing is reserved, which `run.log` says; the cap's bound
    still holds, call by call."""
    try:
        card = _card_for(plan.model.name)
        # An arm on the user's own tools has no published records of its own: every record of
        # the card stands in for it.
        rows = (list(_card_records(card)) if plan.own is not None
                else _arm_records(_card_records(card), spec, card))
    except (OSError, ValueError) as reason:
        _logger.warning("no reservation before the first episode of %s: %s", arm_id(spec), reason)
        return 0.0, 0
    rates = _rates(plan.model.price)
    tokens = sorted(sum(_figures(row).values()) for row in rows)
    dollars = 0.0
    if rates is not None:
        each = sorted(calibration.dollars(_figures(row), rates) or 0.0 for row in rows)
        dollars = calibration._quantile(each, _RESERVATION_QUANTILE)
    return dollars, int(calibration._quantile(tokens, _RESERVATION_QUANTILE))


# ---------------------------------------------------------------------------
# the run folder (spec §8.5)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RunFolder:
    """Where a plan runs.  `status` is `"new"`, `"resume"` or `"complete"`.  For a new folder
    made because the plan changed, `changed` names the plan's fields that differ from the folder
    `previous` names (out of `arms`, `generator_version`, `seeds`, `attempts`, `model`,
    `base_url`, `decoding` and `max_model_calls`); otherwise `changed` is empty and `previous`
    is `None`."""

    path: Path
    name: str
    status: str
    changed: tuple[str, ...] = ()
    previous: str | None = None


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(model: str) -> str:
    """A model's name as one folder-safe path component: every run of characters a path or a
    shell reads specially becomes one `-`, and the name starts with a letter or a digit."""
    name = _UNSAFE.sub("-", model)
    name = re.sub(r"-{2,}", "-", name).strip("-.")
    return name or "model"


def _base_name(plan: Plan) -> str:
    return f"{plan.preset}-{_safe(plan.model.name)}"


def _plan_document(plan: Plan) -> dict[str, Any]:
    """`plan.json`: the resolved plan as JSON, and its hash; `own` when the plan is on the user's
    own tools."""
    model = dataclasses.asdict(plan.model)
    held: dict[str, Any] = {
        "preset": plan.preset,
        "arms": [dataclasses.asdict(spec) for spec in plan.arms],
        "seeds": list(plan.seeds),
        "attempts": plan.attempts,
        "model": model,
        "decoding": dict(plan.decoding),
        "max_model_calls": plan.max_model_calls,
    }
    if plan.own is not None:
        held["own"] = dict(plan.own)
    return {"plan": held, "plan_hash": plan_hash(plan)}


def _read_plan(folder: Path) -> dict[str, Any] | None:
    """The plan a folder holds, or `None` for a folder with no well-formed `plan.json`."""
    path = folder / _PLAN_FILE
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        not isinstance(held, dict)
        or not isinstance(held.get("plan_hash"), str)
        or not isinstance(held.get("plan"), dict)
    ):
        return None
    return held


def _written_at(folder: Path) -> int:
    try:
        return (folder / _PLAN_FILE).stat().st_mtime_ns
    except OSError:
        return 0


def _changes(old: Mapping[str, Any], new: Mapping[str, Any]) -> tuple[str, ...]:
    """The plan's fields that moved its identity between two `plan.json` documents, by name,
    with an arm's generator version named on its own."""

    def strip(arms: Any) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in dict(arm).items() if key != "generator_version"}
            for arm in arms
        ]

    def versions(arms: Any) -> set[Any]:
        return {dict(arm).get("generator_version") for arm in arms}

    out: list[str] = []
    if strip(old["arms"]) != strip(new["arms"]):
        out.append("arms")
    if versions(old["arms"]) != versions(new["arms"]):
        out.append("generator_version")
    if list(old["seeds"]) != list(new["seeds"]):
        out.append("seeds")
    if old["attempts"] != new["attempts"]:
        out.append("attempts")
    if old["model"]["name"] != new["model"]["name"]:
        out.append("model")
    if old["model"]["base_url"] != new["model"]["base_url"]:
        out.append("base_url")
    if dict(old["decoding"]) != dict(new["decoding"]):
        out.append("decoding")
    if old["max_model_calls"] != new["max_model_calls"]:
        out.append("max_model_calls")
    return tuple(out)


def _task_hashes(spec: ArmSpec, seeds: Sequence[int], plan: Plan | None = None) -> list[str]:
    """Each task's wire hash, the key the wheel's trace rows and its resume use; on a plan on the
    user's own tools, the own export's."""
    if plan is not None and plan.own is not None:
        from poisson_tasks.own.export import task_from_bundle as own_task_from_bundle

        bundles = own_bundles(plan, spec, seeds)
        return [str(own_task_from_bundle(bundle).hash) for bundle in bundles]
    from poisson_tasks.export import task_from_bundle
    from poisson_tasks.tasks import generate

    return [str(task_from_bundle(generate(spec, seed)).hash) for seed in seeds]


def own_bundles(plan: Plan, spec: ArmSpec, seeds: Sequence[int]) -> list[Any]:
    """The tasks of an arm of a plan on the user's own tools, one per seed."""
    from poisson_tasks.config import plan_flows, plan_toolset
    from poisson_tasks.own import generator

    assert plan.own is not None
    toolset = plan_toolset(plan)
    flows = plan_flows(plan)
    intents = {str(k): str(v) for k, v in dict(plan.own["intents"]).items()}
    return [generator.generate(toolset, spec, seed, intents=intents, flows=flows) for seed in seeds]


def _kept_rows(arm_folder: Path) -> Counter[str]:
    """The episodes an arm's `traces.jsonl` keeps, per task hash: whole lines that parse and
    ended well.  A torn or malformed line is owed again, as the wheel's resume owes it."""
    kept: Counter[str] = Counter()
    path = arm_folder / _TRACES_FILE
    if not path.exists():
        return kept
    for line in path.read_bytes().splitlines(keepends=True):
        if not line.endswith(b"\n"):
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or not row.get("ok"):
            continue
        task = row.get("task")
        if isinstance(task, dict) and isinstance(task.get("hash"), str):
            kept[task["hash"]] += 1
    return kept


def _kept(plan: Plan, folder: Path) -> int:
    """The episodes a resume of `plan` in `folder` keeps: per task, at most the attempts."""
    kept = 0
    for spec in plan.arms:
        rows = _kept_rows(folder / calibration._run_dir_name(spec))
        for key in _task_hashes(spec, plan.seeds, plan):
            kept += min(rows[key], plan.attempts)
    return kept


def _total(plan: Plan) -> int:
    return len(plan.arms) * len(plan.seeds) * plan.attempts


def _status(plan: Plan, folder: Path) -> str:
    return "complete" if _kept(plan, folder) >= _total(plan) else "resume"


def find_run(
    plan: Plan,
    runs_dir: str | os.PathLike[str],
    *,
    again: bool = False,
    name: str | None = None,
) -> RunFolder:
    """The folder of `runs_dir` that holds `plan`, found by the `plan_hash` in each folder's
    `plan.json` (the newest when several do), or a new one: `<preset>-<model>` with the model
    made folder-safe, then the next free `-2`, `-3`.  `again` makes a new folder even when one
    holds the plan.  `name` takes the folder of that name, and refuses (`ValueError`) a name
    that holds another plan, a name nothing holds, and one that is not a folder's name.  Reads
    only: makes no folder and changes no byte."""
    root = Path(runs_dir)
    wanted = plan_hash(plan)
    if name is not None:
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"{name} is not the name of a folder in {root}")
        folder = root / name
        held = _read_plan(folder) if folder.is_dir() else None
        if held is None:
            raise ValueError(f"there is no run folder named {name} in {root}")
        if held["plan_hash"] != wanted:
            raise ValueError(
                f"the run folder {name} holds another plan; leave --run out to find this "
                "plan's folder"
            )
        return RunFolder(path=folder, name=name, status=_status(plan, folder))

    holders: list[tuple[tuple[int, str], Path]] = []
    others: list[tuple[tuple[int, str], Path]] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            held = _read_plan(child)
            if held is None:
                continue
            others.append(((_written_at(child), child.name), child))
            if held["plan_hash"] == wanted:
                holders.append(((_written_at(child), child.name), child))
    if holders and not again:
        folder = max(holders)[1]
        return RunFolder(path=folder, name=folder.name, status=_status(plan, folder))

    base = _base_name(plan)
    new = base
    suffix = 2
    while (root / new).exists():
        new = f"{base}-{suffix}"
        suffix += 1
    changed: tuple[str, ...] = ()
    previous: str | None = None
    if others and not again:
        newest = max(others)[1]
        previous = newest.name
        held = _read_plan(newest)
        if held is not None:
            changed = _changes(held["plan"], _plan_document(plan)["plan"])
    return RunFolder(path=root / new, name=new, status="new", changed=changed, previous=previous)


# ---------------------------------------------------------------------------
# the ledger (spec §8.4)
# ---------------------------------------------------------------------------


class SpendLedger:
    """A run folder's `spend.jsonl`: one JSON line per episode that ended, with `arm`, `seed`,
    `attempt`, `tokens` (prompt, cached input and completion tokens) and `dollars` (`null`
    without a price).  A torn last line is dropped when the ledger is opened."""

    def __init__(self, folder: str | os.PathLike[str], *, price: PriceConfig | None) -> None:
        self.path = Path(folder) / _LEDGER_FILE
        self._rates = _rates(price)
        self._lines: list[dict[str, Any]] = []
        if not self.path.exists():
            return
        raw = self.path.read_bytes()
        good = 0
        for piece in raw.splitlines(keepends=True):
            if not piece.endswith(b"\n"):
                break
            try:
                line = json.loads(piece)
            except ValueError:
                break
            if not isinstance(line, dict):
                break
            self._lines.append(line)
            good += len(piece)
        if good != len(raw):
            with self.path.open("r+b") as handle:
                handle.truncate(good)

    def lines(self) -> list[dict[str, Any]]:
        return [dict(line) for line in self._lines]

    @property
    def total_dollars(self) -> float | None:
        if self._rates is None:
            return None
        return float(sum(float(line["dollars"] or 0.0) for line in self._lines))

    @property
    def total_tokens(self) -> int:
        return sum(int(line.get("tokens") or 0) for line in self._lines)

    @property
    def largest(self) -> tuple[float, int]:
        """The costliest episode this folder has seen, in dollars and in tokens."""
        dollars = max((float(line.get("dollars") or 0.0) for line in self._lines), default=0.0)
        tokens = max((int(line.get("tokens") or 0) for line in self._lines), default=0)
        return dollars, tokens

    def append(
        self, *, arm: str, seed: int, attempt: int, usage: Mapping[str, int]
    ) -> dict[str, Any]:
        """One line for an episode, `usage` in the card's names (`prompt_tokens`,
        `cached_input_tokens`, `completion_tokens`), priced at the ledger's price."""
        figures = {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "cached_input_tokens": int(usage.get("cached_input_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
        }
        line: dict[str, Any] = {
            "arm": arm,
            "seed": int(seed),
            "attempt": int(attempt),
            "tokens": sum(figures.values()),
            "dollars": calibration.dollars(figures, self._rates),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line) + "\n")
            handle.flush()
        self._lines.append(line)
        return dict(line)


# ---------------------------------------------------------------------------
# the eval config (spec §8.9)
# ---------------------------------------------------------------------------


def verifiers_config(plan: Plan, arm: ArmSpec) -> dict[str, Any]:
    """The verifiers eval config for one arm of the plan, as a mapping `eval @` reads: the taskset
    id, the arm as its six-field mapping, the seeds, the attempts, the model, the endpoint and
    the key's variable's name, the declared decoding without its "not sent" fields, the turn cap
    and `push = false`.  `run_plan` runs each arm with this config, apart from `run.*`,
    `output_dir` and `max_concurrent`.  On a plan on the user's own tools the taskset is
    `poisson-tasks-own` and its config carries the plan's `own` whole (own-tools spec §11)."""
    taskset: dict[str, Any] = {
        "id": calibration.TASKSET_ID,
        "arm": dataclasses.asdict(arm),
        "seeds": list(plan.seeds),
    }
    if plan.own is not None:
        from poisson_tasks.own.export import OWN_TASKSET_ID

        taskset = {
            "id": OWN_TASKSET_ID,
            "arm": dataclasses.asdict(arm),
            "seeds": list(plan.seeds),
            "own": dict(plan.own),
        }
    return {
        "env": {
            "taskset": taskset,
            "agent": {"max_turns": plan.max_model_calls},
        },
        "model": plan.model.name,
        "client": {
            "type": "eval",
            "base_url": plan.model.base_url,
            "api_key_var": plan.model.api_key_env,
        },
        "sampling": calibration._sampling_fields(plan.decoding),
        "num_rollouts": plan.attempts,
        "push": False,
        "output_dir": "export",
    }


def _arm_config(plan: Plan, arm: ArmSpec, folder: Path, concurrency: int) -> Any:
    """The config `run_plan` runs an arm with: `verifiers_config`'s, in the run folder, named
    as `run_arm` names an arm's folder, at the run's concurrency."""
    from verifiers.v1.configs.cli.eval import EvalConfig

    mapping = verifiers_config(plan, arm)
    name = calibration._run_dir_name(arm)
    mapping["output_dir"] = str(folder)
    mapping["run"] = {"name": name, "dir": name}
    mapping["max_concurrent"] = int(concurrency)
    return EvalConfig.model_validate(mapping)


# ---------------------------------------------------------------------------
# the run (spec §8.3 to §8.7)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class RunResult:
    """How a run ended.

    `verdict` is `"done"` or `"stopped"`; `stop_reason` is `None` when done, else one of
    `"spend_cap"`, `"token_cap"`, `"provider_exhausted"`, `"failure_streak"`, `"watchdog"` and
    `"interrupted"`.  `episodes_kept` were kept from earlier runs of the folder when this one
    started; `episodes_run` this call ran to their end and recorded; `episodes_owed` a resume
    would still run.  `spend` and `tokens` are the run folder's totals from its ledger (`spend`
    is `None` without a price).  `first_error` carries the first failed episode's status and the
    provider's own words; `log_tail` the lines of `run.log` the watchdog quotes."""

    verdict: str
    stop_reason: str | None
    episodes_kept: int
    episodes_run: int
    episodes_owed: int
    spend: float | None
    tokens: int
    first_error: str | None = None
    log_tail: str | None = None


def _secret_forms(key: str) -> list[str]:
    """The key's secret part, without its public prefix (`providers._secret_part`, the key
    check's rule too), as written and JSON-escaped once and twice: a provider's error quotes the
    key escaped once as verifiers keeps it, and a trace line holds that text escaped again."""
    secret = _secret_part(key)
    once = json.dumps(secret)[1:-1]
    return list(dict.fromkeys([secret, once, json.dumps(once)[1:-1]]))


class _Runs:
    """Every run of `length` or more characters of one of `forms`, found and masked; a form
    shorter than `length` is a run whole."""

    def __init__(self, forms: Sequence[str], length: int) -> None:
        self._forms = [form for form in forms if len(form) >= _MASKED_RUN]
        self._grams: dict[int, set[str]] = {}
        for form in self._forms:
            size = min(length, len(form))
            self._grams.setdefault(size, set()).update(
                form[i : i + size] for i in range(len(form) - size + 1)
            )

    def found(self, text: str) -> bool:
        return any(gram in text for grams in self._grams.values() for gram in grams)

    def mask(self, text: str) -> str:
        if not self.found(text):
            return text
        out: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            size = next(
                (size for size, grams in self._grams.items() if text[i : i + size] in grams), 0
            )
            if size:
                j = i + size
                while j < n and any(text[i : j + 1] in form for form in self._forms):
                    j += 1
                out.append(_MASK)
                i = j
            else:
                out.append(text[i])
                i += 1
        return "".join(out)


class _Scrub:
    """The key's secret part in a run's texts: `text` masks every run of four or more of its
    characters, for a text that can carry the key; `holds_key` finds a run of twelve or more,
    the key's wherever it is, and `key_masked` masks those alone."""

    def __init__(self, secrets: Sequence[str]) -> None:
        forms = [form for secret in secrets for form in _secret_forms(secret)]
        self._masked = _Runs(forms, _MASKED_RUN)
        self._key = _Runs(forms, _KEY_RUN)

    def text(self, text: str) -> str:
        return self._masked.mask(text)

    def holds_key(self, text: str) -> bool:
        return self._key.found(text)

    def key_masked(self, text: str) -> str:
        return self._key.mask(text)


class _ScrubbingFormatter(logging.Formatter):
    def __init__(self, scrub: _Scrub) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s: %(message)s")
        self._scrub = scrub

    def format(self, record: logging.LogRecord) -> str:
        return self._scrub.text(super().format(record))


class _LogFilter(logging.Filter):
    """The run's own lines at every level, and everything else from warning up."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == _logger.name or record.name.startswith(_logger.name + "."):
            return True
        return record.levelno >= logging.WARNING


@contextlib.contextmanager
def _run_log(folder: Path, scrub: _Scrub) -> Iterator[logging.Handler]:
    """`run.log` for the run's length: the run's own progress, verifiers' records of warning
    level and above, and any traceback, with the key masked."""
    handler = logging.FileHandler(folder / _LOG_FILE, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(_ScrubbingFormatter(scrub))
    handler.addFilter(_LogFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    previous_level = _logger.level
    _logger.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        _logger.setLevel(previous_level)
        root.removeHandler(handler)
        handler.close()


def _tail(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-_LOG_TAIL_LINES:])


_UPSTREAM = re.compile(r"upstream (\d+): (\{.*\})\s*$", re.S)


def _error_text(error: Any) -> str:
    """One failed episode's error as one string: the provider's status and its own words
    (`401 invalid_api_key: Incorrect API key provided ...`), or the error's own text."""
    message = str(getattr(error, "message", error))
    match = _UPSTREAM.search(message)
    if match:
        status = match.group(1)
        try:
            body = json.loads(match.group(2))
        except ValueError:
            body = None
        detail = body.get("error") if isinstance(body, dict) else None
        if isinstance(detail, dict):
            words = str(detail.get("message") or "").strip()
            code = str(detail.get("code") or "").strip()
            return f"{status} {code}: {words}" if code else f"{status}: {words}"
    return message


def _usage_of(episode: Any) -> dict[str, int]:
    """An episode's usage in the card's names, summed over its calls."""
    usage = getattr(episode, "usage", None)
    if usage is None:
        return {"prompt_tokens": 0, "cached_input_tokens": 0, "completion_tokens": 0}
    return {
        "prompt_tokens": int(usage.prompt_tokens),
        "cached_input_tokens": int(usage.cached_input_tokens or 0),
        "completion_tokens": int(usage.completion_tokens),
    }


def _usage_figures(usage: Any) -> dict[str, int]:
    return {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "cached_input_tokens": int(getattr(usage, "cached_input_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
    }


def _add(into: dict[str, int], figures: Mapping[str, int]) -> None:
    for name, value in figures.items():
        into[name] = into.get(name, 0) + int(value)


class _Meter:
    """The cap, checked against measured spend: the ledger's total plus every call the
    episodes in flight have made, call by call (spec §8.4)."""

    def __init__(
        self,
        *,
        ledger: SpendLedger,
        rates: Mapping[str, float] | None,
        spend_cap: float | None,
        token_cap: int | None,
    ) -> None:
        self.ledger = ledger
        self.rates = rates
        self.spend_cap = spend_cap if rates is not None else None
        self.token_cap = token_cap
        self.in_flight: dict[str, dict[str, int]] = {}
        self.episodes_in_flight = 0
        self.largest_dollars, self.largest_tokens = ledger.largest
        self.seen = bool(ledger.lines())
        self.reserve_dollars = 0.0
        self.reserve_tokens = 0

    def reserve_for(self, plan: Plan, spec: ArmSpec) -> None:
        """The reservation for an episode of `spec`: the largest episode this folder has
        seen, and before any, the card's 95th percentile for the arm."""
        if self.seen:
            self.reserve_dollars, self.reserve_tokens = self.largest_dollars, self.largest_tokens
            return
        if self.spend_cap is None and self.token_cap is None:
            return
        self.reserve_dollars, self.reserve_tokens = _reservation(plan, spec)

    def _spent(self) -> tuple[float, int]:
        dollars = self.ledger.total_dollars or 0.0
        tokens = self.ledger.total_tokens
        for figures in self.in_flight.values():
            tokens += sum(figures.values())
            if self.rates is not None:
                dollars += calibration.dollars(figures, self.rates) or 0.0
        return dollars, tokens

    def blocks_dispatch(self) -> str | None:
        """The cap that leaves no room for one more episode beside the ones in flight, or
        `None`."""
        dollars, tokens = self._spent()
        episodes = self.episodes_in_flight + 1
        if self.spend_cap is not None:
            if dollars + episodes * self.reserve_dollars > float(self.spend_cap) + _EPS:
                return "spend_cap"
        if self.token_cap is not None:
            if tokens + episodes * self.reserve_tokens > int(self.token_cap):
                return "token_cap"
        return None

    def refuses_call(self) -> str | None:
        """The cap the measured spend has reached, or `None` when one more call is admitted."""
        dollars, tokens = self._spent()
        if self.spend_cap is not None and dollars + _EPS >= float(self.spend_cap):
            return "spend_cap"
        if self.token_cap is not None and tokens >= int(self.token_cap):
            return "token_cap"
        return None

    def add_call(self, session_id: str, usage: Any) -> None:
        _add(self.in_flight.setdefault(session_id, {}), _usage_figures(usage))

    def take(self, session_ids: Sequence[str]) -> dict[str, int]:
        """The usage the calls of these sessions made, taken out of the in-flight account."""
        out: dict[str, int] = {}
        for session_id in session_ids:
            _add(out, self.in_flight.pop(session_id, {}))
        return out

    def saw_episode(self, line: Mapping[str, Any]) -> None:
        self.seen = True
        self.largest_dollars = max(self.largest_dollars, float(line.get("dollars") or 0.0))
        self.largest_tokens = max(self.largest_tokens, int(line.get("tokens") or 0))
        self.reserve_dollars, self.reserve_tokens = self.largest_dollars, self.largest_tokens


@dataclasses.dataclass
class _State:
    stop_reason: str | None = None
    first_error: str | None = None
    error: BaseException | None = None
    hard: bool = False
    run: int = 0
    kept_this_run: int = 0
    scored: int = 0
    failed_in_a_row: int = 0
    finished: int = 0
    calls_made: int = 0
    cut: set[str] = dataclasses.field(default_factory=set)
    running: set[asyncio.Task[None]] = dataclasses.field(default_factory=set)

    def stop(self, reason: str) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason

    def cancel_all(self) -> None:
        for task in list(self.running):
            task.cancel()


@contextlib.contextmanager
def _metered_client(meter: _Meter, state: _State) -> Iterator[None]:
    """For the run's length, every model call passes the cap's check before it is relayed, and
    what it cost is counted the moment it returns."""
    from verifiers.v1.clients import eval as eval_client
    from verifiers.v1.errors import ProviderError

    real = eval_client.EvalClient.get_response

    async def metered(self: Any, *args: Any, **kwargs: Any) -> Any:
        session_id = str(kwargs.get("session_id") or "")
        if session_id in state.cut:
            raise ProviderError("this episode was cut by the run's cap", status_code=400)
        reason = meter.refuses_call()
        if reason is not None:
            state.cut.add(session_id)
            state.stop(reason)
            raise ProviderError(f"the run's {reason} is reached", status_code=400)
        state.calls_made += 1
        response = await real(self, *args, **kwargs)
        usage = getattr(response, "usage", None)
        if usage is not None:
            meter.add_call(session_id, usage)
        return response

    eval_client.EvalClient.get_response = metered
    try:
        yield
    finally:
        eval_client.EvalClient.get_response = real


@contextlib.contextmanager
def _harness_environment() -> Iterator[None]:
    """The harness's environment for the run's length (spec §8.6): pip kept to a virtualenv, so
    the bootstrap takes uv's installer every time, and that installer told not to edit shell
    start-up files."""
    saved = {name: os.environ.get(name) for name in ("PIP_REQUIRE_VIRTUALENV", "UV_NO_MODIFY_PATH")}
    os.environ["PIP_REQUIRE_VIRTUALENV"] = "1"
    os.environ["UV_NO_MODIFY_PATH"] = "1"
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _write_plan(path: Path, plan: Plan) -> None:
    """`plan.json`, whole or not at all, before the first request."""
    tmp = path / (_PLAN_FILE + ".tmp")
    tmp.write_text(json.dumps(_plan_document(plan), indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path / _PLAN_FILE)


def _errors_masked(value: Any, scrub: _Scrub) -> Any:
    """`value` with every provider error in it masked, its message and its traceback, and every
    other field the same object; `value` itself when no error in it holds part of the key."""
    from pydantic import BaseModel
    from verifiers.v1.trace import Error

    changed: dict[str, Any] = {}
    if isinstance(value, Error):
        for name in ("message", "traceback"):
            text = getattr(value, name)
            if text is not None and (masked := scrub.text(text)) != text:
                changed[name] = masked
        return value.model_copy(update=changed) if changed else value
    if isinstance(value, BaseModel):
        for name, info in type(value).model_fields.items():
            item = getattr(value, name)
            if not info.exclude and (masked := _errors_masked(item, scrub)) is not item:
                changed[name] = masked
        return value.model_copy(update=changed) if changed else value
    if isinstance(value, (list, tuple)):
        items = [_errors_masked(item, scrub) for item in value]
        if all(new is old for new, old in zip(items, value, strict=True)):
            return value
        return items if isinstance(value, list) else tuple(items)
    if isinstance(value, dict):
        entries = {key: _errors_masked(item, scrub) for key, item in value.items()}
        if all(entries[key] is item for key, item in value.items()):
            return value
        return entries
    return value


def _key_masked(line: str, scrub: _Scrub) -> str:
    """A trace line that holds the key outside its errors, with the key masked in every string
    of it, names included; still one JSON document."""

    def masked(value: Any) -> Any:
        if isinstance(value, str):
            return scrub.key_masked(value)
        if isinstance(value, list):
            return [masked(item) for item in value]
        if isinstance(value, dict):
            return {masked(key): masked(item) for key, item in value.items()}
        return value

    return json.dumps(masked(json.loads(line)), ensure_ascii=False, separators=(",", ":"))


async def _append_trace(out: Path, episode: Any, lock: asyncio.Lock, scrub: _Scrub) -> None:
    """One finished episode as one line of the arm's `traces.jsonl`, as the wheel writes it,
    with the key masked in its provider errors, and anywhere else it is whole; written whole
    even under cancellation."""
    from verifiers.v1.cli.output import type_adapter
    from verifiers.v1.utils.aio import run_shielded

    shown = _errors_masked(episode, scrub)
    text = type_adapter(type(shown)).dump_json(shown, exclude_none=True).decode("utf-8")
    if scrub.holds_key(text):
        text = _key_masked(text, scrub)

    def write() -> None:
        with (out / _TRACES_FILE).open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")

    async def persist() -> None:
        async with lock:
            await asyncio.to_thread(write)

    await run_shielded(persist())


def _secrets(plan: Plan) -> list[str]:
    key = os.environ.get(plan.model.api_key_env) if plan.model.api_key_env else None
    return [key] if key else []


def run_plan(
    plan: Plan,
    folder: RunFolder,
    *,
    caps: Mapping[str, float | int | None],
    concurrency: int,
    events: Callable[[Mapping[str, Any]], None] | None = None,
    watchdog_seconds: float = 600,
) -> RunResult:
    """Run the plan's owed episodes into `folder`, arm by arm in the plan's order.

    `caps` holds `spend_usd` and `tokens` (either may be `None`), over the run folder's total.
    `events` is called once for each episode that finishes, with `arm`, `episodes_done`,
    `episodes_total` and `spend`.  After the first SIGINT it returns the interrupted result;
    after a second it raises `KeyboardInterrupt`.  An exception that is not the run's own is
    written to `run.log` with its traceback and raised.  A plan with no arm or no seeds is a
    `ValueError`, before anything is written.
    """
    if not plan.arms or not plan.seeds:
        raise ValueError("a run needs at least one arm and one seed")
    path = Path(folder.path)
    path.mkdir(parents=True, exist_ok=True)
    if _read_plan(path) is None:
        _write_plan(path, plan)
    scrub = _Scrub(_secrets(plan))
    with _run_log(path, scrub) as handler:
        return asyncio.run(
            _run(
                plan,
                path,
                caps=caps,
                concurrency=max(1, int(concurrency)),
                events=events,
                watchdog_seconds=float(watchdog_seconds),
                scrub=scrub,
                handler=handler,
            )
        )


async def _run(
    plan: Plan,
    path: Path,
    *,
    caps: Mapping[str, float | int | None],
    concurrency: int,
    events: Callable[[Mapping[str, Any]], None] | None,
    watchdog_seconds: float,
    scrub: _Scrub,
    handler: logging.Handler,
) -> RunResult:
    ledger = SpendLedger(path, price=plan.model.price)
    total = _total(plan)
    kept_before = _kept(plan, path)
    if kept_before >= total:
        _logger.info("every one of the %d episodes is kept; nothing to run", total)
        return RunResult(
            verdict="done",
            stop_reason=None,
            episodes_kept=total,
            episodes_run=0,
            episodes_owed=0,
            spend=ledger.total_dollars,
            tokens=ledger.total_tokens,
        )
    spend_cap = caps.get("spend_usd")
    token_cap = caps.get("tokens")
    meter = _Meter(
        ledger=ledger,
        rates=_rates(plan.model.price),
        spend_cap=None if spend_cap is None else float(spend_cap),
        token_cap=None if token_cap is None else int(token_cap),
    )
    state = _State()
    loop = asyncio.get_running_loop()
    grace: asyncio.TimerHandle | None = None

    def on_sigint() -> None:
        nonlocal grace
        if state.stop_reason == "interrupted" or state.hard:
            state.hard = True
            _logger.info("a second interrupt: stopping at once")
            state.cancel_all()
            return
        state.stop_reason = "interrupted"
        _logger.info(
            "interrupted: no more episodes start; the ones in flight have %g seconds to finish",
            _GRACE_SECONDS,
        )
        grace = loop.call_later(_GRACE_SECONDS, state.cancel_all)

    signals = threading.current_thread() is threading.main_thread()
    if signals:
        loop.add_signal_handler(signal.SIGINT, on_sigint)

    async def watchdog() -> None:
        await asyncio.sleep(watchdog_seconds)
        if state.calls_made == 0 and state.finished == 0:
            _logger.error(
                "no model call and no finished episode within %g s: stopping", watchdog_seconds
            )
            state.stop("watchdog")
            state.cancel_all()

    watch = loop.create_task(watchdog())
    _logger.info("run of %d episodes, %d kept, at concurrency %d", total, kept_before, concurrency)
    try:
        with _harness_environment(), _metered_client(meter, state):
            for spec in plan.arms:
                if state.stop_reason is not None or state.error is not None:
                    break
                await _run_arm_of_plan(
                    plan,
                    spec,
                    path,
                    ledger=ledger,
                    meter=meter,
                    state=state,
                    events=events,
                    scrub=scrub,
                    concurrency=concurrency,
                    kept_before=kept_before,
                    total=total,
                )
    finally:
        watch.cancel()
        if grace is not None:
            grace.cancel()
        if signals:
            loop.remove_signal_handler(signal.SIGINT)
    if state.error is not None:
        _logger.error("the run stopped on an unexpected failure", exc_info=state.error)
        handler.flush()
        raise state.error
    if state.hard:
        handler.flush()
        raise KeyboardInterrupt
    owed = total - kept_before - state.kept_this_run
    if state.stop_reason is None and owed and state.run and state.scored == 0:
        state.stop("failure_streak")
    if state.stop_reason is None:
        _logger.info("done: %d of %d episodes", kept_before + state.kept_this_run, total)
    else:
        _logger.info("stopped: %s, %d episodes owed", state.stop_reason, owed)
    handler.flush()
    return RunResult(
        verdict="done" if state.stop_reason is None else "stopped",
        stop_reason=state.stop_reason,
        episodes_kept=kept_before,
        episodes_run=state.run,
        episodes_owed=owed,
        spend=ledger.total_dollars,
        tokens=ledger.total_tokens,
        first_error=state.first_error,
        log_tail=_tail(path / _LOG_FILE) if state.stop_reason == "watchdog" else None,
    )


async def _run_arm_of_plan(
    plan: Plan,
    spec: ArmSpec,
    path: Path,
    *,
    ledger: SpendLedger,
    meter: _Meter,
    state: _State,
    events: Callable[[Mapping[str, Any]], None] | None,
    scrub: _Scrub,
    concurrency: int,
    kept_before: int,
    total: int,
) -> None:
    """One arm of the plan, into its own wheel run folder: the owed episodes, dispatched while
    the cap leaves room, recorded as they end."""
    import verifiers.v1 as vf
    from verifiers.v1.cli.eval import resume as wheel_resume
    from verifiers.v1.cli.output import output_path, save_config
    from verifiers.v1.cli.resume import distribute
    from verifiers.v1.episode import EvalRunInfo
    from verifiers.v1.utils.loaders import load_environment

    config = _arm_config(plan, spec, path, concurrency)
    env = load_environment(config.env)
    tasks = list(env.taskset)
    out = Path(output_path(config))
    out.mkdir(parents=True, exist_ok=True)
    keys = [task.hash for task in tasks]
    if (out / _TRACES_FILE).exists():
        calibration._tally_failures_on_disk(out)
        kept, owed = wheel_resume.load(out, keys, config.num_rollouts, env.complete)
        counts = distribute(keys, owed, config.num_rollouts)
    else:
        save_config(config, out)
        kept, counts = [], [config.num_rollouts] * len(tasks)
    schedule = [(task, count) for task, count in zip(tasks, counts, strict=True) if count]
    attempts: dict[str, int] = {key: 0 for key in keys}
    for episode in kept:
        attempts[episode.task.hash] = attempts.get(episode.task.hash, 0) + 1
    meter.reserve_for(plan, spec)
    lock = asyncio.Lock()
    ctx = vf.ModelContext(client=config.client, model=config.model, sampling=config.sampling)
    name = arm_id(spec)
    _logger.info("serving %s: %d episodes", name, sum(count for _, count in schedule))
    if not schedule:
        return

    async def on_complete(episode: Any) -> None:
        episode.record_run(EvalRunInfo(id=config.run.id, name=config.run.name))
        sessions = [str(trace.id) for trace in getattr(episode, "traces", []) or []]
        meter.take(sessions)
        cut = any(session in state.cut for session in sessions)
        key = str(episode.task.hash)
        seed = int(episode.task.data.seed)
        attempt = attempts.get(key, 0)
        if not cut:
            # Taken before the first await: two attempts at one task can end together.
            attempts[key] = attempt + 1
        line = ledger.append(arm=name, seed=seed, attempt=attempt, usage=_usage_of(episode))
        meter.saw_episode(line)
        state.finished += 1
        if cut:
            _logger.info("an episode of %s cut by the %s", name, state.stop_reason)
            return
        await _append_trace(out, episode, lock, scrub)
        state.run += 1
        if episode.ok:
            state.kept_this_run += 1
        label = calibration.label_from_signals(calibration._episode_signals(episode))
        if label is not None:
            calibration.record_instrument(
                out,
                task_id=str(episode.task.data.task_id),
                seed=seed,
                attempt=attempt,
                label=label,
                episode_id=episode.id,
            )
            state.failed_in_a_row += 1
            if state.first_error is None:
                errors = calibration._episode_errors(episode)
                state.first_error = scrub.text(_error_text(errors[0])) if errors else label
            if calibration._provider_exhausted(episode):
                state.stop("provider_exhausted")
            elif state.scored == 0 and state.failed_in_a_row >= _STREAK:
                state.stop("failure_streak")
        else:
            state.scored += 1
            state.failed_in_a_row = 0
        done = kept_before + state.run
        _logger.info("%d/%d episodes · %s", done, total, name)
        if events is not None:
            events(
                {
                    "arm": name,
                    "episodes_done": done,
                    "episodes_total": total,
                    "spend": ledger.total_dollars,
                }
            )

    async def run_one(slot: Any) -> None:
        meter.episodes_in_flight += 1
        try:
            await env.run_slot(slot, ctx, None, on_complete)
        except asyncio.CancelledError:
            sessions = [str(trace.id) for trace in slot.traces]
            usage = meter.take(sessions)
            if sum(usage.values()):
                key = str(slot.task.hash)
                ledger.append(
                    arm=name,
                    seed=int(slot.task.data.seed),
                    attempt=attempts.get(key, 0),
                    usage=usage,
                )
                _logger.info(
                    "an episode of %s abandoned after %d tokens", name, sum(usage.values())
                )
            raise
        except Exception as error:  # noqa: BLE001 - a failure that is not the run's own
            if state.error is None:
                state.error = error
            state.stop("error")
            state.cancel_all()
        finally:
            meter.episodes_in_flight -= 1

    pending = [slot for task, count in schedule for slot in env.slots(task, count)]
    async with env.serving():
        while True:
            if state.stop_reason is None and pending and len(state.running) < concurrency:
                blocked = meter.blocks_dispatch()
                if blocked is None:
                    task = asyncio.get_running_loop().create_task(run_one(pending.pop(0)))
                    state.running.add(task)
                    continue
                if not state.running:
                    _logger.info("the %s leaves no room for another episode", blocked)
                    state.stop(blocked)
            if not state.running:
                break
            done, _ = await asyncio.wait(state.running, return_when=asyncio.FIRST_COMPLETED)
            state.running -= done
            for task in done:
                if not task.cancelled() and task.exception() is not None:
                    error = task.exception()
                    if state.error is None and error is not None:
                        state.error = error
                    state.stop("error")
                    state.cancel_all()
