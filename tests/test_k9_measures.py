"""The knob probe: what is reported beside the primary measure.

The probe's design: the primary measure is strict pass@1 per arm; leaky, the no-call share, gave up
after a fault, cost and time are reported beside it; `faults:f0` against `history:t0` (the same task
but one system sentence) is reported as a check and decides nothing.  Concurrency is recorded.  Each
figure is the cards' own arithmetic (`calibration`), so it is checked against that.
"""

from __future__ import annotations

from typing import Any

from poisson_tasks import calibration as cal
from tests.k9_support import MODEL, OTHER, episode, every_arm, model_run, outcome_of, seeds60

RATES = {"input_rate": 0.05, "cached_input_rate": 0.005, "output_rate": 0.40}


def with_overshoot(arm: str) -> list[cal.EpisodeRecord]:
    """Passing on the first 30 seeds; on the next 20 the record is carried past the goal (leaky
    but not strict); failing on the rest."""
    rows = []
    for index, seed in enumerate(seeds60()):
        for attempt in range(2):
            if index < 30:
                rows.append(episode(arm, seed, attempt, passed=True))
            elif index < 50:
                rows.append(episode(arm, seed, attempt, label="overshoot", leaky=True, calls=3))
            else:
                rows.append(episode(arm, seed, attempt, calls=1))
    return rows


def measures(cells: dict[str, Any], arm: str, **facts: Any) -> dict[str, Any]:
    from poisson_tasks import knob_probe as probe

    result = probe.analyse({MODEL: model_run(cells, facts=facts or None)}, expected=(MODEL,))
    return dict(result["arms"][MODEL][arm]["measures"])


def test_strict_and_leaky_each_with_the_cards_interval() -> None:
    cells = every_arm({})
    cells["history:t2400"] = with_overshoot("history:t2400")
    found = measures(cells, "history:t2400")
    rows = cells["history:t2400"]
    assert found["strict"] == cal.pass_at_1(rows) == 0.5
    assert found["leaky"] == cal._leaky_at_1(rows) > found["strict"]
    assert found["strict_interval"] == list(
        cal.cluster_bootstrap(rows, cal.pass_at_1, resamples=2000, seed=20260922)
    )
    assert found["leaky_interval"] == list(
        cal.cluster_bootstrap(rows, cal._leaky_at_1, resamples=2000, seed=20260922)
    )


def test_the_no_call_share_is_over_scored_episodes() -> None:
    cells = every_arm(
        {}, options={"block:k64": {"no_call": range(54, 60), "instrument": [(0, 0), (0, 1)]}}
    )
    found = measures(cells, "block:k64")
    assert found["scored"] == 118
    assert found["no_call_share"] == 12 / 118


def test_gave_up_after_a_fault_is_reported_on_the_arm_that_plans_faults() -> None:
    cells = every_arm({"faults:f4": 30}, options={"faults:f4": {"gave_up": range(30, 45)}})
    found = measures(cells, "faults:f4")
    assert found["gave_up_after_fault"] == 30 and found["gave_up_after_fault_share"] == 0.25
    assert "gave_up_after_fault" not in measures(cells, "faults:f0")


def test_cost_is_every_episodes_tokens_at_the_models_rates_and_none_without_rates() -> None:
    cells = every_arm({}, options={"spread:p4": {"instrument": [(3, 1)]}})
    rows = cells["spread:p4"]
    found = measures(cells, "spread:p4", rates=RATES, concurrency=8)
    spent = {
        "prompt_tokens": 1000 * len(rows),
        "cached_input_tokens": 200 * len(rows),
        "completion_tokens": 300 * len(rows),
    }
    assert found["dollars"] == cal.dollars(spent, RATES)
    assert found["tokens"] == 1500 * len(rows)
    assert measures(cells, "spread:p4", concurrency=8)["dollars"] is None


def test_calls_tokens_and_time_are_the_cards_figures() -> None:
    cells = every_arm({"arguments:a8": 30})
    found = measures(cells, "arguments:a8")
    figures = cal._cost_and_time(cells["arguments:a8"], cal.pass_at_1(cells["arguments:a8"]))
    for name in (
        "model_calls_mean",
        "tool_calls_mean",
        "tokens_mean",
        "tokens_p90",
        "episode_seconds_median",
        "episode_seconds_p90",
        "model_seconds_median",
        "harness_seconds_median",
    ):
        assert found[name] == figures[name], name
    assert found["episode_seconds_median"] == 4.5


def test_faults_f0_against_history_t0_is_reported_as_a_check_that_decides_nothing() -> None:
    from poisson_tasks import knob_probe as probe

    cells = every_arm({"faults:f0": 54, "history:t0": 30, "faults:f4": 30, "history:t2400": 30})
    result = probe.analyse({MODEL: model_run(cells)}, expected=(MODEL,))
    check = result["check"][MODEL]
    assert (check["a"], check["b"]) == ("faults:f0", "history:t0")
    assert abs(check["delta"] - 0.4) < 1e-12 and check["meets"]
    assert "decides nothing" in check["note"]
    assert outcome_of(result, "faults")["per_model"][MODEL]["status"] == "bites"
    assert outcome_of(result, "history")["per_model"][MODEL]["status"] == "does not bite"
    for row in result["outcomes"]:
        assert all("faults:f0 against history:t0" not in reason for reason in row["reasons"])


def test_the_runs_concurrency_is_carried_into_the_outcome_and_its_page() -> None:
    from poisson_tasks import knob_probe as probe

    result = probe.analyse(
        {
            MODEL: model_run(every_arm({}), facts={"concurrency": 96}),
            OTHER: model_run(every_arm({}, model=OTHER), facts={"concurrency": 128}),
        },
        expected=(MODEL, OTHER),
    )
    assert result["facts"][MODEL]["concurrency"] == 96
    assert result["facts"][OTHER]["concurrency"] == 128
    page = probe.render_outcome(result)
    assert "Concurrency: 96 episodes at once" in page
    assert "Concurrency: 128 episodes at once" in page


def test_the_page_shows_each_knobs_outcome_each_contrast_each_arm_and_the_check() -> None:
    from poisson_tasks import knob_probe as probe

    cells = every_arm({"similarity:s3": 30})
    cells["history:t2400"] = with_overshoot("history:t2400")
    result = probe.analyse(
        {MODEL: model_run(cells, facts={"concurrency": 8, "rates": RATES})}, expected=(MODEL, OTHER)
    )
    page = probe.render_outcome(result)
    assert result["frozen_generator_hash"] in page
    assert "| similarity | waiting |" in page
    assert (
        "| similarity | gpt-5-nano-2025-08-07 | bites | similarity:s0 − similarity:s3 | 0.400 |"
        in page
    )
    assert f"| similarity | {OTHER} | not run |" in page
    t2400 = next(line for line in page.splitlines() if line.startswith("| history:t2400 |"))
    assert "| 0.500 | 0.833 |" in t2400
    assert "Check (decides nothing): faults:f0 − history:t0" in page
    assert (
        len(
            [
                line
                for line in page.splitlines()
                if line.startswith("| ")
                and line.split("|")[1].strip() in {a for a in result["arms"][MODEL]}
            ]
        )
        == 18
    )
