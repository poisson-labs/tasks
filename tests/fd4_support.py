"""Shared ground for the `tests/test_fd4_*.py` tests: run folders made by the run engine, the
published cards read off the files they ship as, and the checks the card tests share.  Frozen with
them.

**Run folders are made, never written by hand.**  Each scenario below is a plan run by
`runs.run_plan` against the fixture model (`tests/fixtures/model_server.py`), the way the
`test_fd3_*` tests run one: the do-nothing `pip` first on `PATH`, the fixture's key in its variable,
inside the network guard.  So a card is built from exactly what the run engine leaves in a folder:
`plan.json`, the ledger, `run.log`, each arm's `traces.jsonl` and instrument tally.  Each scenario
is made once per test session, the first time a test asks for it, in a folder of the session's own;
the card tests only read it, and `test_fd4_card.py` checks that building a card changes no byte of
it.  The session's folders are held by this module, not by each test module that imports the
fixture, so a scenario is run once however many files read it.

**`FD4_RUN_FOLDERS`.**  When this variable names a folder, a scenario already there is copied from
it instead of being run again, and a scenario not there is run and then kept there.  Nothing in the
card tests changes what the run engine writes, so a folder made once stands for every later run; the
mutation pass sets it so that each mutant does not wait on the same runs again.  Unset, as in every
gate, every scenario is run afresh.

**The published cards are read off the files they ship as** (`calibration/<folder>/` in the
checkout): every folder there holding an `artifact.json`, rebuilt from its own records under the
provenance it recorded (`tests.helpers.rebuild_committed_card`).  No test pins how many there are,
their folder names or their figures, so the tests hold when the cards are replaced by the new
design; the few assertions that must name them are listed in the lab's private notes.

**What every expectation is computed from.**  A test's expectation comes from the plan, the folder
(its ledger, its trace lines, its tally) or the shipped files, never from the code under test.
"""

from __future__ import annotations

import dataclasses
import functools
import hashlib
import json
import math
import os
import shutil
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import network_guard
from tests.fd3_support import (
    KEY,
    KEY_VAR,
    PRICE_FIELDS,
    arm_dir,

    calibration,
    call_dollars,
    make_plan,
    ok_lines,
    runs,
    stub_bin,
    trace_lines,
)
from tests.fixtures.model_server import FixtureModel
from tests.helpers import rebuild_committed_card

REPO = Path(__file__).resolve().parents[1]
SHIPPED = REPO / "calibration"
CACHE_VARIABLE = "FD4_RUN_FOLDERS"

NOT_SENT = "not sent"
"""The settings file's word for a decoding field the run leaves out (`config.py`)."""


# ---------------------------------------------------------------------------
# the scenarios
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Scenario:
    """One plan, run once against the fixture model."""

    arms: tuple[str, ...]
    seeds: int
    """How many of the published seeds, from the first."""
    attempts: int = 1
    model: str = "fixture-reference"
    concurrency: int = 4
    priced: bool = True
    decoding: Mapping[str, Any] | None = None
    strictness: str = "strict"
    split: str = "eval"
    generator_version: str | None = None
    provider: str = "openai-compatible"
    preset: str = "custom"
    spend_cap: float | str = 100.0
    """Dollars, or `"cut"` or `"partial"`: a cap worked out from the published card the run
    reserves from (`cut_design`, `partial_design`)."""


UNCOVERED = "<a depth level no published card holds>"


def uncovered_arm() -> str:
    """The first depth level from 1 to 8 that no shipped card holds a cell of."""
    held = {cell["arm_id"] for artifact in shipped_artifacts() for cell in artifact.cells}
    for level in range(1, 9):
        if f"depth:d{level}" not in held:
            return f"depth:d{level}"
    raise AssertionError("every depth level is on a shipped card")


SCENARIOS: dict[str, Scenario] = {
    # A first look as `init` would make one, smaller: depth at 1, 3 and 8, three tasks per level,
    # two attempts, against a model that has a published card.  Every episode passes.
    "first_look": Scenario(arms=("depth:d1", "depth:d3", "depth:d8"), seeds=3, attempts=2,
                           model="gpt-5-nano-2025-08-07", concurrency=8, preset="first-look"),
    # Every episode ran and exactly one failed: the fixture serves 103 completions and refuses the
    # 104th, the last of the run's 104 calls, so one episode ends `api_error` whatever the order.
    # One failure in 52 attempts is under the instrument threshold, so the card is not refused.
    "failed_once": Scenario(arms=("depth:d1",), seeds=26, attempts=2,
                            model="fixture-429-after-103", concurrency=8),
    # The same folder after the fixture forgets its count and the run is run again.
    "failed_once_resumed": Scenario(arms=("depth:d1",), seeds=26, attempts=2,
                                    model="fixture-429-after-103", concurrency=8),
    # The cap cuts the first episode of depth:d8 short; depth:d8 then has no recorded episode.
    "cut": Scenario(arms=("depth:d1", "depth:d8"), seeds=0, concurrency=1, spend_cap="cut"),
    # The cap stops the run after one depth:d3 task of several: a partial cell (the card design's
    # own example), owed tasks it never reached, and no episode cut short.
    "partial": Scenario(arms=("depth:d1", "depth:d3"), seeds=0, concurrency=1,
                        spend_cap="partial"),
    # A reply with no tool call, every time: the no-call gate.
    "silent": Scenario(arms=("depth:d1",), seeds=2, model="fixture-silent"),
    # Every call refused: every episode an instrument failure.
    "all_failed": Scenario(arms=("depth:d1",), seeds=2, model="fixture-429", concurrency=1),
    "distractor": Scenario(arms=("distractor:r2@k16",), seeds=2),
    # A model the user serves, with two decoding fields left to the server.
    "self_served": Scenario(arms=("depth:d1",), seeds=2, provider="vllm", priced=False,
                            decoding={"temperature": 1.0, "top_p": NOT_SENT,
                                      "reasoning_effort": "low", "max_tokens": NOT_SENT}),
    # One arm, two tasks, one attempt, run four ways that the card must tell apart.
    "strict": Scenario(arms=("depth:d1",), seeds=2),
    "strict_again": Scenario(arms=("depth:d1",), seeds=2),
    "leaky": Scenario(arms=("depth:d1",), seeds=2, strictness="leaky"),
    "train": Scenario(arms=("depth:d1",), seeds=2, split="train"),
    "generator_0": Scenario(arms=("depth:d1",), seeds=2, generator_version="0"),
    # A level no published card measured (the first depth level none holds, read off the shipped
    # cards), alone and beside one they did.
    "uncovered": Scenario(arms=(UNCOVERED,), seeds=2),
    "partly_covered": Scenario(arms=("depth:d3", UNCOVERED), seeds=1),
    # The model of the second published card, by the name a vLLM server serves it under.
    "qwen": Scenario(arms=("depth:d1",), seeds=2, model="Qwen/Qwen3-8B"),
    # A cap below the first reservation: nothing is dispatched, so nothing is recorded.
    "empty": Scenario(arms=("depth:d1",), seeds=2, spend_cap=0.0001),
}


@dataclasses.dataclass(frozen=True)
class Made:
    """A scenario's run folder, the plan run into it, and how the last run of it ended."""

    folder: Path
    plan: Any
    result: Any


def published_seeds(count: int) -> tuple[int, ...]:
    seeds: tuple[int, ...] = calibration().seed_list()[:count]
    return seeds


def plan_of(scenario: Scenario, base_url: str, seeds: Sequence[int]) -> Any:
    arms = tuple(uncovered_arm() if arm == UNCOVERED else arm for arm in scenario.arms)
    plan = make_plan(
        base_url, model=scenario.model, arms=arms, seeds=seeds,
        attempts=scenario.attempts, priced=scenario.priced, decoding=scenario.decoding,
        preset=scenario.preset, strictness=scenario.strictness,
        generator_version=scenario.generator_version,
    )
    if scenario.split != "eval":
        plan = dataclasses.replace(plan, arms=tuple(
            dataclasses.replace(spec, split=scenario.split) for spec in plan.arms))
    if scenario.provider != plan.model.provider:
        plan = dataclasses.replace(
            plan, model=dataclasses.replace(plan.model, provider=scenario.provider))
    return plan


def model_a_records() -> list[Any]:
    """Model A's published records, found by the model they name, not by the folder's name."""
    for folder in shipped_folders():
        rows = calibration().read_records(folder / "episodes.jsonl")
        if rows and rows[0].model == calibration().MODEL_A:
            return list(rows)
    raise AssertionError("no shipped card measured model A")


def first_reservation() -> float:
    """What a run of a model no card measured reserves before its first depth:d1 episode, at the
    tests' prices: the 95th percentile of model A's published depth:d1 episodes."""
    rows = [row for row in model_a_records() if row.arm_id == "depth:d1"]
    rates = {"input_rate": PRICE_FIELDS["input"], "cached_input_rate": PRICE_FIELDS["cached_input"],
             "output_rate": PRICE_FIELDS["output"]}
    each = sorted(
        calibration().dollars({"prompt_tokens": row.prompt_tokens,
                               "cached_input_tokens": row.cached_input_tokens,
                               "completion_tokens": row.completion_tokens}, rates) or 0.0
        for row in rows
    )
    value: float = calibration()._quantile(each, 0.95)
    return value


def partial_design() -> tuple[int, float]:
    """The `partial` scenario's seeds and cap.  k depth:d1 tasks (two calls each) run first; the
    first depth:d3 episode (four calls) is dispatched with a reservation of two calls and runs
    whole under a cap of 2k + 6 calls; the next is reserved four calls, which leaves no room, so
    the run stops with one depth:d3 task of k recorded and none cut short."""
    call = call_dollars()
    k = max(2, math.ceil((first_reservation() / call - 6) / 2) + 1)
    return k, (2 * k + 6) * call


def cut_design() -> tuple[int, float]:
    """The `cut` scenario's seeds and cap, from the published card the run reserves from.

    Before its first episode a run reserves the published card's 95th percentile of the arm,
    read from model A's card for a model no card measured; after that, the largest
    episode it has seen.  A depth:d1 episode costs two calls and a depth:d8 one nine, at
    `call_dollars()` each.  So with k depth:d1 tasks run first and the cap at k × 2 calls plus
    four and a half calls: the first depth:d1 episode fits under the cap with its reservation
    (k is large enough), every later one fits with a reservation of two calls, the first depth:d8
    episode is dispatched with a reservation of two calls, and the cap is reached during its
    calls, which cuts it short."""
    first = first_reservation()
    call = call_dollars()
    k = max(1, math.ceil((first - 4.5 * call) / (2 * call)) + 1)
    return k, k * 2 * call + 4.5 * call


class RunFolders:
    """The session's scenarios, made the first time a test asks for one."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._made: dict[str, Made] = {}
        cache = os.environ.get(CACHE_VARIABLE)
        self.cache = Path(cache) if cache else None

    def __getitem__(self, name: str) -> Made:
        if name not in self._made:
            if name.startswith("failed_once"):
                self._made.update(self._cached("failed_once", self._failed_once))
            else:
                self._made.update(self._cached(name, functools.partial(self._run, name)))
        return self._made[name]

    def _cached(self, key: str, make: Callable[[Path], dict[str, Made]]) -> dict[str, Made]:
        if self.cache is None:
            return make(self.root / key)
        kept = self.cache / key
        index = kept / "made.json"
        if not index.exists():
            made = make(self.root / key)
            if kept.exists():
                shutil.rmtree(kept)
            shutil.copytree(self.root / key, kept)
            index.write_text(json.dumps({
                name: {"folder": str(item.folder.relative_to(self.root / key)),
                       "result": dataclasses.asdict(item.result)}
                for name, item in made.items()
            }), encoding="utf-8")
            return made
        target = self.root / key
        if not target.exists():
            shutil.copytree(kept, target)
        out: dict[str, Made] = {}
        for name, entry in json.loads(index.read_text(encoding="utf-8")).items():
            folder = target / entry["folder"]
            out[name] = Made(folder=folder, plan=plan_from_folder(folder),
                             result=runs().RunResult(**entry["result"]))
        return out

    @contextmanager
    def _environment(self, where: Path) -> Iterator[pytest.MonkeyPatch]:
        with pytest.MonkeyPatch.context() as patch:
            stubs = stub_bin(where / "stub-bin")
            patch.setenv("PATH", f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}")
            patch.setenv(KEY_VAR, KEY)
            for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
                         "all_proxy"):
                patch.delenv(name, raising=False)
            patch.setenv("NO_PROXY", "127.0.0.1,localhost")
            yield patch

    def _run_once(self, patch: pytest.MonkeyPatch, plan: Any, runs_dir: Path,
                  caps: Mapping[str, Any], concurrency: int) -> tuple[Path, Any]:
        folder = runs().find_run(plan, runs_dir)
        with network_guard(patch):
            result = runs().run_plan(plan, folder, caps=dict(caps), concurrency=concurrency)
        return Path(folder.path), result

    def _run(self, name: str, where: Path) -> dict[str, Made]:
        scenario = SCENARIOS[name]
        where.mkdir(parents=True, exist_ok=True)
        if scenario.spend_cap == "cut":
            count, cap = cut_design()
        elif scenario.spend_cap == "partial":
            count, cap = partial_design()
        else:
            count, cap = scenario.seeds, float(scenario.spend_cap)
        with self._environment(where) as patch, FixtureModel() as model:
            plan = plan_of(scenario, model.base_url, published_seeds(count))
            folder, result = self._run_once(patch, plan, where / "runs",
                                            {"spend_usd": cap, "tokens": None},
                                            scenario.concurrency)
        return {name: Made(folder=folder, plan=plan, result=result)}

    def _failed_once(self, where: Path) -> dict[str, Made]:
        scenario = SCENARIOS["failed_once"]
        where.mkdir(parents=True, exist_ok=True)
        caps = {"spend_usd": scenario.spend_cap, "tokens": None}
        with self._environment(where) as patch, FixtureModel() as model:
            plan = plan_of(scenario, model.base_url, published_seeds(scenario.seeds))
            folder, first = self._run_once(patch, plan, where / "runs", caps,
                                           scenario.concurrency)
            kept = where / "before-the-resume" / folder.name
            shutil.copytree(folder, kept)
            model.forget()
            _, again = self._run_once(patch, plan, where / "runs", caps, scenario.concurrency)
        return {
            "failed_once": Made(folder=kept, plan=plan, result=first),
            "failed_once_resumed": Made(folder=folder, plan=plan, result=again),
        }


def plan_from_folder(folder: Path) -> Any:
    """The plan a run folder's `plan.json` holds, made again as `config.Plan`."""
    import types

    from poisson_tasks import config
    from poisson_tasks.knobs import ArmSpec

    held = json.loads((folder / "plan.json").read_text(encoding="utf-8"))["plan"]
    model = dict(held["model"])
    if model.get("price") is not None:
        model["price"] = config.PriceConfig(**model["price"])
    return config.Plan(
        preset=held["preset"], arms=tuple(ArmSpec(**arm) for arm in held["arms"]),
        seeds=tuple(held["seeds"]), attempts=held["attempts"],
        model=config.ModelConfig(**model),
        decoding=types.MappingProxyType(dict(held["decoding"])),
        max_model_calls=held["max_model_calls"],
    )


_SHARED: list[RunFolders] = []


@pytest.fixture(scope="session")
def fd4_runs(tmp_path_factory: pytest.TempPathFactory) -> RunFolders:
    """The session's scenarios.  pytest keeps a session fixture imported into several modules once
    per module, so the folders themselves are kept here, once per process."""
    if not _SHARED:
        _SHARED.append(RunFolders(tmp_path_factory.mktemp("fd4-runs")))
    return _SHARED[0]


# ---------------------------------------------------------------------------
# what a run folder holds, read without the code under test
# ---------------------------------------------------------------------------


def recorded(made: Made) -> dict[str, int]:
    """Per arm id, the episodes the folder's trace files record, failed ones included."""
    out: dict[str, int] = {}
    for spec in made.plan.arms:
        out[arm_id(spec)] = len(trace_lines(made.folder / arm_dir(spec)))
    return out


def kept(made: Made) -> dict[str, int]:
    """Per arm id, the episodes that ended well: what a resume keeps."""
    return {arm_id(spec): len(ok_lines(made.folder / arm_dir(spec))) for spec in made.plan.arms}


def designed(made: Made) -> int:
    """The attempts the plan asks of each arm."""
    return len(made.plan.seeds) * int(made.plan.attempts)


def ledger(made: Made) -> list[dict[str, Any]]:
    path = made.folder / "spend.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def tallied(made: Made) -> dict[str, dict[str, int]]:
    """Per arm id, the instrument tally the arm's folder kept, counted from its lines."""
    out: dict[str, dict[str, int]] = {}
    for spec in made.plan.arms:
        path = made.folder / arm_dir(spec) / "instrument-tally.jsonl"
        counts: dict[str, int] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    label = json.loads(line)["label"]
                    counts[label] = counts.get(label, 0) + 1
        out[arm_id(spec)] = counts
    return out


def arm_id(spec: Any) -> str:
    from poisson_tasks.knobs import arm_id as _arm_id

    return str(_arm_id(spec))


# ---------------------------------------------------------------------------
# the published cards, read off their files
# ---------------------------------------------------------------------------


def shipped_folders() -> list[Path]:
    """Every folder of `calibration/` that holds a card."""
    return sorted(path.parent for path in SHIPPED.glob("*/artifact.json"))


@functools.cache
def shipped_artifacts() -> tuple[Any, ...]:
    """Each shipped card rebuilt from its own records under the provenance it recorded."""
    return tuple(rebuild_committed_card(folder)[0] for folder in shipped_folders())


def package_generator_hash() -> str:
    """The generator hash the package gives today, as the published cards' staleness reads it."""
    from poisson_tasks.tasks import generate

    cal = calibration()
    value: str = generate(cal.arm_specs()[0], cal.seed_list()[0]).generator_hash
    return value


def differing(a: Any, b: Any) -> list[str]:
    """The fields of `_COMPARABLE` two provenance blocks differ in, in that tuple's order."""
    return [name for name in calibration()._COMPARABLE
            if getattr(a, name, None) != getattr(b, name, None)]


def cells_by_arm(artifact: Any) -> dict[str, dict[str, Any]]:
    return {cell["arm_id"]: cell for cell in artifact.cells}


def rebuilt_from_card(card: Any) -> tuple[Any, bytes, bytes]:
    """The card's artifact rebuilt from its own files, as `card --check` would: its records, the
    provenance block its written artifact holds, and its tally; with the written artifact's bytes
    and the rebuilt one's."""
    import tempfile

    cal = calibration()
    with tempfile.TemporaryDirectory() as scratch:
        written = cal.write_artifact(card.artifact, Path(scratch) / "artifact.json").read_bytes()
        stored = json.loads(written)
        cells: dict[tuple[str, str], list[Any]] = {}
        for record in card.records:
            cells.setdefault((record.arm_id, record.model), []).append(record)
        tally = {key: dict(card.tally.get(key[0], {})) for key in cells}
        rebuilt = cal.build_artifact(cells, cal.Provenance(**stored["provenance"]), tally=tally)
        again = cal.write_artifact(rebuilt, Path(scratch) / "again.json").read_bytes()
    return rebuilt, written, again


def scored_calls(card: Any) -> int:
    """The model calls of the card's scored records: what the fixture served them."""
    instrument = calibration().INSTRUMENT_LABELS
    return sum(int(row.turns) for row in card.records if row.label not in instrument)


def tree(root: Path) -> dict[str, bytes | None]:
    """Every file under `root` with its bytes, and every folder, as `None`."""
    out: dict[str, bytes | None] = {}
    for path in sorted(root.rglob("*")):
        out[str(path.relative_to(root))] = path.read_bytes() if path.is_file() else None
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one_line(text: str) -> bool:
    return bool(text.strip()) and "\n" not in text.strip()
