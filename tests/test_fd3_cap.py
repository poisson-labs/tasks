"""The run's cap and its ledger, frozen as tests: what `runs.run_plan` may spend, and what it
writes down.  These protect the user's money.

The invariants, with the decision of 2026-10-02 that the cap is a guaranteed bound:
- for fixed per-call usage, concurrency c in {1, 4, 8} and caps around the run's cost,
  the final spend is at most the cap plus the cost of the calls in flight when it was reached;
- the same for the token cap, with no price;
- one ledger line per finished episode; their sum is `RunResult.spend`, and equals the
  card's cost at the same rates.

**Which bound, and why: c calls, not c episodes.**  Measured when the run engine was
built: every model call an episode makes passes through verifiers'
interception server, which runs inside the run's own process and makes the upstream request
there (`EvalClient.get_response`; 8 of 8 and 22 of 22 calls counted in-process against the
fixture's own count).  So the run can check the cap before each call, and the bound is the cost
of at most c calls: one call in flight per episode, c episodes at once.  The plan's d8 arm makes
nine calls an episode, so a build that checks only between episodes overshoots by up to eight
calls an episode in flight, which the bound refuses.

**The caps are set where any run that keeps the cap's rule can move.**  Before its first episode a
run reserves the estimate's 95th percentile, from model A's card at the plan's prices: at these
prices about $0.117 and 10,600 tokens for a depth:d1 episode, about five times what the fixture
charges.  So a cap below that may stop a run before its first call (the $0.05 rows, which then
check only the bound and the stop), and every cap that asks for progress is above it.  After the
first episode the reservation is the largest episode seen, so a run with one episode
in flight stops within one episode of the cap (the "stopped well short" check, at concurrency 1).

**What is spent is counted by the fixture, not by the code under test.**  Every call the fixture
answers costs `call_dollars()` (one cent at these prices) and `CALL_TOKENS` tokens, whatever the
run thinks it spent.

Also pinned here:
- arms run in the plan's order, one after another: an uncapped run makes every call of its first
  arm before any of its second, and a cap that stops a run has started an arm only once every
  arm before it was whole;
- an episode the cap cut short is not an instrument failure: the card of a capped run must not
  read the cap's own stop as the instrument failing (CAL16's tally stays empty, every recorded
  episode is a whole one);
- raising the cap resumes the same run, and the cap is on the run's total, not on each `run`;
- `events` is called once for each episode that finishes, with the running count and spend.

Shapes decided here
-------------------

**1. `caps`** is a mapping with the `[limits]` table's names: `spend_usd` (dollars, or `None`)
and `tokens` (or `None`).

**2. `RunResult`** has `verdict` (`"done"` or `"stopped"`), `stop_reason` (`None` when done;
here `"spend_cap"` or `"token_cap"`), `episodes_kept` (kept from earlier runs of the folder when
this one started), `episodes_run` (episodes this call ran to their end and recorded),
`episodes_owed` (what a resume would still run), `spend` and `tokens` (the run folder's totals,
from its ledger, across every `run_plan` on it; `spend` is `None` without a price),
`first_error` and `log_tail`.  For a run in which no episode failed, kept + run + owed is the
plan's episode count.

**3. A ledger line** is a JSON object with `arm` (its id), `seed`, `attempt`, `tokens` (prompt,
cached input and completion tokens together) and `dollars` (`null` without a price).  An episode
the cap cut short has a line too: it cost what its calls cost.  For an uninterrupted run, the
attempts of each (arm, seed) are 0 to n - 1.

**4. `SpendLedger(folder, *, price)`** reads `spend.jsonl` in a run folder (`lines()`,
`total_dollars`, `total_tokens`) and appends to it (`append(arm=, seed=, attempt=, usage=)`,
`usage` in the card's names: `prompt_tokens`, `cached_input_tokens`, `completion_tokens`).  A torn
last line, left by a process that died while writing it, is dropped when the ledger is opened, so
the next line starts a line of its own.

**5. `events`** is called with a mapping holding at least `arm` (the finished episode's arm id),
`episodes_done` (episodes kept and finished so far, counting the ones kept before), `episodes_total`
and `spend` (the ledger's total so far).

Not pinned: how the run reserves for calls in flight (the design describes one way; the bound is
the invariant), what it does with a call it refuses, and the time a run takes.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import (
    CALL_TOKENS,
    PRICE_FIELDS,
    arm_dir,
    call_dollars,
    calibration,
    config,
    fixture_model,
    harness_env,
    ledger_lines,
    make_plan,
    needs_uv,
    ok_lines,
    planned_tasks,
    rates,
    records,
    run_here,
    runs,
    scored_tasks,
    total_episodes,
    trace_lines,
)
from tests.fixtures.model_server import FixtureModel, usage_per_call

__all__ = ["fixture_model", "harness_env"]

pytestmark = needs_uv

EPS = 1e-9


PER_ARM = 9
TOTAL_CALLS = PER_ARM * 2 + PER_ARM * 9


def two_arms(model: FixtureModel, **kwargs: Any) -> Any:
    """depth:d1 (two calls an episode) then depth:d8 (nine), three tasks, three attempts: nine
    episodes an arm, so eight can be in flight at once; 99 calls, 99 cents."""
    return make_plan(model.base_url, arms=("depth:d1", "depth:d8"), seeds=(404, 55, 2121),
                     attempts=3, **kwargs)


def goal_times(model: FixtureModel, goal: str) -> list[float]:
    """When each call reached the fixture, for the tasks whose goal stage is `goal` (depth:d1's
    is the first stage, review; depth:d8's the eighth, label)."""
    return [seen.at for seen in model.posts()
            if f"through {goal}, and no further" in json.dumps(seen.body)]


def arm_figures(plan: Any, folder: Path) -> dict[str, int]:
    """Episodes recorded per arm id."""
    return Counter(row.arm_id for row in records(plan, folder))


def assert_kept_work_is_clean(plan: Any, folder: Path) -> None:
    """Every recorded episode is a whole one, and nothing is in the instrument tally."""
    for spec in plan.arms:
        arm = folder / arm_dir(spec)
        assert ok_lines(arm) == trace_lines(arm), f"{arm.name}: a recorded episode failed"
        if arm.exists():
            assert calibration().read_tally(arm) == {}, calibration().read_tally(arm)


# ---------------------------------------------------------------------------
# the spend cap
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cap, concurrency", [
    (0.05, 1), (0.05, 8), (0.30, 4), (0.30, 8), (0.60, 1), (0.60, 8), (0.90, 4),
])
def test_fd3_4_final_spend_is_at_most_the_cap_plus_the_calls_in_flight(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch, cap: float, concurrency: int,
) -> None:
    plan = two_arms(fixture_model)
    call = call_dollars()
    folder, result = run_here(plan, tmp_path, monkeypatch,
                              caps={"spend_usd": cap, "tokens": None}, concurrency=concurrency)
    spent = fixture_model.calls() * call
    assert spent <= cap + concurrency * call + EPS, (spent, cap, concurrency)
    assert (result.verdict, result.stop_reason) == ("stopped", "spend_cap"), result
    assert result.spend is not None and math.isclose(result.spend, spent, abs_tol=EPS)
    assert math.isclose(sum(line["dollars"] for line in ledger_lines(Path(folder.path))), spent,
                        abs_tol=EPS)
    assert result.tokens == fixture_model.calls() * CALL_TOKENS
    total = total_episodes(plan)
    assert result.episodes_owed > 0
    assert result.episodes_kept + result.episodes_run + result.episodes_owed == total, result
    if concurrency == 1 and cap > 0.5:
        largest_episode = 9 * call
        assert spent >= cap - largest_episode - call - EPS, ("stopped well short", spent, cap)

    arms = arm_figures(plan, Path(folder.path))
    second_started = arms["depth:d8"] > 0 or any(
        line["arm"] == "depth:d8" for line in ledger_lines(Path(folder.path)))
    if second_started:
        assert arms["depth:d1"] == PER_ARM, "the second arm started before the first was whole"
    assert arms["depth:d8"] < PER_ARM
    assert_kept_work_is_clean(plan, Path(folder.path))


def test_fd3_4_a_cap_above_the_runs_cost_does_not_stop_it(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = two_arms(fixture_model)
    folder, result = run_here(plan, tmp_path, monkeypatch,
                              caps={"spend_usd": 1.00, "tokens": None}, concurrency=8)
    assert (result.verdict, result.stop_reason, result.episodes_owed) == ("done", None, 0)
    assert fixture_model.calls() == TOTAL_CALLS
    first, second = goal_times(fixture_model, "review"), goal_times(fixture_model, "label")
    assert len(first) == PER_ARM * 2 and len(second) == PER_ARM * 9
    assert max(first) < min(second), "the arms ran together, not one after the other"
    assert result.spend is not None
    assert math.isclose(result.spend, TOTAL_CALLS * call_dollars(), abs_tol=EPS)


def test_fd3_4_raising_the_cap_resumes_the_same_run_and_the_cap_is_on_its_total(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`run --spend-cap 2.00` resumes the run the cap stopped.  Run again at the same
    cap, it spends nothing past the bound: the cap holds the run's total, not each `run`'s."""
    plan = two_arms(fixture_model)
    call = call_dollars()
    cap = 0.30
    first, stopped = run_here(plan, tmp_path, monkeypatch,
                              caps={"spend_usd": cap, "tokens": None}, concurrency=4)
    assert stopped.stop_reason == "spend_cap"

    second, again = run_here(plan, tmp_path, monkeypatch,
                             caps={"spend_usd": cap, "tokens": None}, concurrency=4)
    assert Path(second.path) == Path(first.path) and second.status == "resume"
    assert again.stop_reason == "spend_cap", again
    assert fixture_model.calls() * call <= cap + 4 * call + EPS, "the cap was applied per run"

    third, done = run_here(plan, tmp_path, monkeypatch,
                           caps={"spend_usd": 2.00, "tokens": None}, concurrency=4)
    assert Path(third.path) == Path(first.path)
    assert (done.verdict, done.episodes_owed) == ("done", 0), done
    spent = fixture_model.calls() * call
    assert done.spend is not None and math.isclose(done.spend, spent, abs_tol=EPS)
    assert math.isclose(sum(line["dollars"] for line in ledger_lines(Path(first.path))), spent,
                        abs_tol=EPS)
    assert scored_tasks(plan, Path(first.path)) == planned_tasks(plan)
    assert_kept_work_is_clean(plan, Path(first.path))


# ---------------------------------------------------------------------------
# the token cap
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cap, concurrency", [(15_000, 1), (15_000, 8), (70_000, 1), (70_000, 8)])
def test_fd3_5_final_tokens_are_at_most_the_cap_plus_the_calls_in_flight(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch, cap: int, concurrency: int,
) -> None:
    plan = two_arms(fixture_model, priced=False)
    folder, result = run_here(plan, tmp_path, monkeypatch,
                              caps={"spend_usd": None, "tokens": cap}, concurrency=concurrency)
    used = fixture_model.calls() * CALL_TOKENS
    assert used <= cap + concurrency * CALL_TOKENS, (used, cap, concurrency)
    assert (result.verdict, result.stop_reason) == ("stopped", "token_cap"), result
    assert result.tokens == used
    assert result.spend is None
    lines = ledger_lines(Path(folder.path))
    assert lines and all(line["dollars"] is None for line in lines)
    assert sum(line["tokens"] for line in lines) == used
    if concurrency == 1 and cap > 50_000:
        assert used >= cap - 10 * CALL_TOKENS, ("stopped well short", used, cap)
    assert_kept_work_is_clean(plan, Path(folder.path))


@pytest.mark.parametrize("caps, binding", [
    ({"spend_usd": 2.00, "tokens": 15_000}, "token_cap"),
    ({"spend_usd": 0.20, "tokens": 1_000_000}, "spend_cap"),
])
def test_fd3_5_with_both_caps_the_first_reached_stops_the_run(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch, caps: dict[str, Any], binding: str,
) -> None:
    plan = two_arms(fixture_model)
    _, result = run_here(plan, tmp_path, monkeypatch, caps=caps, concurrency=4)
    assert result.stop_reason == binding, result
    calls = fixture_model.calls()
    assert calls * call_dollars() <= caps["spend_usd"] + 4 * call_dollars() + EPS
    assert calls * CALL_TOKENS <= caps["tokens"] + 4 * CALL_TOKENS


# ---------------------------------------------------------------------------
# the ledger
# ---------------------------------------------------------------------------


def test_fd3_6_one_line_per_episode_summing_to_the_spend_and_the_cards_cost(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = make_plan(fixture_model.base_url, arms=("depth:d1", "depth:d3"), seeds=(404, 55),
                     attempts=2)
    seen: list[dict[str, Any]] = []
    folder, result = run_here(plan, tmp_path, monkeypatch, concurrency=4,
                              events=lambda event: seen.append(dict(event)))
    assert result.verdict == "done"
    path = Path(folder.path)
    lines = ledger_lines(path)
    rows = records(plan, path)
    assert len(lines) == len(rows) == total_episodes(plan) == result.episodes_run
    for line in lines:
        assert {"arm", "seed", "attempt", "tokens", "dollars"} <= set(line), line
    attempts: dict[tuple[str, int], list[int]] = {}
    for line in lines:
        attempts.setdefault((line["arm"], line["seed"]), []).append(line["attempt"])
    assert {key: sorted(value) for key, value in attempts.items()} == {
        (arm, seed): [0, 1] for arm in ("depth:d1", "depth:d3") for seed in (404, 55)}

    def figures(row: Any) -> dict[str, int]:
        return {"prompt_tokens": row.prompt_tokens, "cached_input_tokens": row.cached_input_tokens,
                "completion_tokens": row.completion_tokens}

    from_ledger = Counter((line["arm"], line["seed"], line["tokens"], round(line["dollars"], 12))
                          for line in lines)
    from_records = Counter(
        (row.arm_id, row.seed, sum(figures(row).values()),
         round(calibration().dollars(figures(row), rates()), 12)) for row in rows)
    assert from_ledger == from_records
    ledger_sum = sum(line["dollars"] for line in lines)
    card_cost = sum(calibration().dollars(figures(row), rates()) for row in rows)
    assert result.spend is not None
    assert math.isclose(ledger_sum, result.spend, abs_tol=EPS)
    assert math.isclose(ledger_sum, card_cost, abs_tol=EPS)
    assert math.isclose(ledger_sum, fixture_model.calls() * call_dollars(), abs_tol=EPS)
    assert result.tokens == sum(line["tokens"] for line in lines)

    assert len(seen) == len(lines)
    assert [event["episodes_done"] for event in seen] == list(range(1, len(lines) + 1))
    assert {event["episodes_total"] for event in seen} == {total_episodes(plan)}
    assert Counter(event["arm"] for event in seen) == Counter(line["arm"] for line in lines)
    spends = [event["spend"] for event in seen]
    assert spends == sorted(spends) and math.isclose(spends[-1], result.spend, abs_tol=EPS)


def test_fd3_6_without_a_price_every_line_has_no_dollars(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = make_plan(fixture_model.base_url, seeds=(404, 55), priced=False)
    folder, result = run_here(plan, tmp_path, monkeypatch,
                              caps={"spend_usd": None, "tokens": 1_000_000})
    lines = ledger_lines(Path(folder.path))
    assert len(lines) == 2 and all(line["dollars"] is None for line in lines)
    assert result.spend is None
    assert result.tokens == fixture_model.calls() * CALL_TOKENS == sum(
        line["tokens"] for line in lines)


def test_fd3_6_the_ledger_drops_a_torn_last_line_and_appends_on_a_line_of_its_own(
    tmp_path: Path,
) -> None:
    """A process killed while writing its last line leaves half of it.  Opened again, the
    ledger reads the whole lines, and its next line is a line of its own, not glued to the
    half."""
    price = config().PriceConfig(**PRICE_FIELDS)
    path = tmp_path / "spend.jsonl"
    whole = [
        {"arm": "depth:d1", "seed": 404, "attempt": 0, "tokens": 2200, "dollars": 0.02},
        {"arm": "depth:d1", "seed": 404, "attempt": 1, "tokens": 2200, "dollars": 0.02},
    ]
    path.write_text("".join(json.dumps(line) + "\n" for line in whole) + '{"arm": "depth:d1", "se',
                    encoding="utf-8")
    ledger = runs().SpendLedger(tmp_path, price=price)
    assert ledger.lines() == whole
    assert math.isclose(ledger.total_dollars, 0.04, abs_tol=EPS)
    assert ledger.total_tokens == 4400
    usage = {name: value * 2 for name, value in usage_per_call().items()}
    ledger.append(arm="depth:d1", seed=55, attempt=0, usage=usage)
    lines = [json.loads(text) for text in path.read_text(encoding="utf-8").splitlines()]
    assert lines[:2] == whole and len(lines) == 3
    assert (lines[2]["arm"], lines[2]["seed"], lines[2]["attempt"]) == ("depth:d1", 55, 0)
    assert lines[2]["tokens"] == sum(usage.values())
    assert math.isclose(lines[2]["dollars"], calibration().dollars(usage, rates()), abs_tol=EPS)
    assert runs().SpendLedger(tmp_path, price=price).lines() == lines
    assert runs().SpendLedger(tmp_path, price=None).total_dollars is None
