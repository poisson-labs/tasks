"""Runs: what a plan will cost, the folder it runs in, and the run itself, with its cap, its
ledger, Ctrl-C, the start-up watchdog and the failure-streak stop.

The library side of `poisson-tasks run` (spec §8).  The CLI shows the estimate, asks, and prints
the result; everything it shows comes from here.  `tests/test_fd3_*.py` say what each name does.

**The order a run takes** (spec §8.1): `config.resolve_plan`, then `find_run`, then the free key
check (`providers.check_key`), then `estimate`; nothing is sent to the model before `run_plan`.

**The run folder** (spec §8.5) is `runs/<preset>-<model>/`, then `-2`, `-3`, with no hash in its
name.  It holds `plan.json` (the resolved plan and its `plan_hash`, by which the folder that holds
a plan is found), `spend.jsonl` (the ledger: one line per episode that ended), `run.log`, and one
wheel run folder per arm, named as `calibration.run_arm` names it (`depth-d1/`).

**The cap is a bound** (spec §8.4): the final spend is at most the cap plus the cost of the model
calls in flight when it was reached.  Model calls pass through verifiers' interception server in
the run's own process, so the run can check before each call, and the bound is c calls at
concurrency c.

**Ctrl-C** (spec §8.5): the first interrupt stops dispatching and gives the episodes in flight up
to 10 seconds to finish and be recorded; a second stops at once.

**Stops** (spec §8.7): the spend or token cap; the provider out of credit; five episodes in a row
failed before any was scored; no model call and no finished episode within the watchdog's limit.

**The machine** (spec §8.6): the harness's environment carries `PIP_REQUIRE_VIRTUALENV=1` and
`UV_NO_MODIFY_PATH=1`.

Names only: every function raises `NotImplementedError`.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from poisson_tasks.config import Plan, PriceConfig
from poisson_tasks.knobs import ArmSpec

__all__ = [
    "Estimate",
    "estimate",
    "RunFolder",
    "find_run",
    "RunResult",
    "run_plan",
    "SpendLedger",
    "verifiers_config",
]


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


def estimate(plan: Plan, *, reference: str | None = None) -> Estimate:
    """The plan's estimate, from the published card of the plan's model (matched without the
    card's `@revision`), else model A's; or from the card `reference` names.  A name that is not
    a published card's is a `ValueError`.  Opens no socket and writes no file."""
    raise NotImplementedError("runs.estimate")


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
    raise NotImplementedError("runs.find_run")


# ---------------------------------------------------------------------------
# the ledger (spec §8.4)
# ---------------------------------------------------------------------------


class SpendLedger:
    """A run folder's `spend.jsonl`: one JSON line per episode that ended, with `arm`, `seed`,
    `attempt`, `tokens` (prompt, cached input and completion tokens) and `dollars` (`null`
    without a price).  A torn last line is dropped when the ledger is opened."""

    def __init__(self, folder: str | os.PathLike[str], *, price: PriceConfig | None) -> None:
        raise NotImplementedError("runs.SpendLedger")

    def lines(self) -> list[dict[str, Any]]:
        raise NotImplementedError("runs.SpendLedger.lines")

    @property
    def total_dollars(self) -> float | None:
        raise NotImplementedError("runs.SpendLedger.total_dollars")

    @property
    def total_tokens(self) -> int:
        raise NotImplementedError("runs.SpendLedger.total_tokens")

    def append(
        self, *, arm: str, seed: int, attempt: int, usage: Mapping[str, int]
    ) -> dict[str, Any]:
        """One line for an episode, `usage` in the card's names (`prompt_tokens`,
        `cached_input_tokens`, `completion_tokens`), priced at the ledger's price."""
        raise NotImplementedError("runs.SpendLedger.append")


# ---------------------------------------------------------------------------
# the eval config (spec §8.9)
# ---------------------------------------------------------------------------


def verifiers_config(plan: Plan, arm: ArmSpec) -> dict[str, Any]:
    """The verifiers eval config for one arm of the plan, as a mapping `eval @` reads: the taskset
    id, the arm as its six-field mapping, the seeds, the attempts, the model, the endpoint and
    the key's variable's name, the declared decoding without its "not sent" fields, the turn cap
    and `push = false`.  `run_plan` runs each arm with this config, apart from `run.*`,
    `output_dir` and `max_concurrent`."""
    raise NotImplementedError("runs.verifiers_config")


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
    raise NotImplementedError("runs.run_plan")
