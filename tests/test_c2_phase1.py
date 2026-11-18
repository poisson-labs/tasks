"""C2.8: phase 1, before each paid run, and the four things that stop it.

The design: three seeds (the knob probe's phase 1 derivation, its first three), one attempt, all
56 arms, 168 episodes.  It stops the run when
1. any episode carries an instrument label;
2. the share of calls stopped by the length cap is above 0.02 over all of phase 1;
3. more than 0.10 of the base arms' episodes made no tool call; or
4. any answer's `model` field differs from the id asked for in a way the provider's page does not
   document as an alias.
A stopped phase 1 reports what it spent; a passing phase 1 goes on in the same folder.

The clean run of every arm (`c2_support.clean_run`) shows the 168 episodes.  The stops are run on
a smaller design (`GATE_ARMS`: four base arms, so twelve base episodes; a top, a middle level and
two own-tools arms), where one failing task decides each case.

Shapes decided here
-------------------
* `phase1.json` holds `passed`, `episodes`, `spent` (dollars), `stops` (which of the four
  stopped it, from `STOPS`, in that order; empty when it passed), `length_stop_share`,
  `no_call_share` and `answer_models`.
* A run phase 1 stopped exits 2 and has run no episode of the card; run again on the same
  folder it exits 2 again without a model call.
* A documented alias is a row's `aliases`; the registered rows document none for gpt-6-luna.

Readings made here: the base arms are the built-in dials' first levels (`BASES`); and "calls" in
the length rule are model calls, cut ones included.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

import pytest

from tests.c2_fake import Play, Provider, cached_registry
from tests.c2_support import (
    ARMS,
    BASES,
    GATE_ARMS,
    LUNA,
    PHASE1_EPISODES,
    PHASE1_SEEDS,
    card_run,
    clean_run,
    complete_arms,
    design_seeds,
    drive,
    lines,
    needs_uv,
    read,
    registry_cache,
    small_design,
)
from tests.k9_fake import Behaviour

pytestmark = needs_uv

STOPS = ("instrument", "length_stops", "no_call", "answer_model")
SEED = PHASE1_SEEDS[0]


def gate_design() -> Any:
    return small_design(arms=GATE_ARMS)


def calls_in_phase_1(cache: Path, cut: dict[str, frozenset[int]]) -> tuple[int, int]:
    """The model calls phase 1 of the gate design makes against the fake, and how many are cut:
    a task makes its reference calls and one reply, and a cut task makes its one cut call."""
    design = gate_design()
    registry = cached_registry(design.arms, design_seeds(design), cache)
    total = stopped = 0
    for entries in registry.values():
        for entry in entries:
            if entry.seed not in PHASE1_SEEDS:
                continue
            if entry.arm in cut and (not cut[entry.arm] or entry.seed in cut[entry.arm]):
                total, stopped = total + 1, stopped + 1
            else:
                total += len(entry.calls) + 1
    return total, stopped


def gate(tmp_path: Path, tmp_path_factory: pytest.TempPathFactory, play: Play, **kwargs: Any
         ) -> dict[str, Any]:
    return drive(tmp_path, registry_cache(tmp_path_factory), play=play, design=gate_design(),
                 **kwargs)


def stopped(found: dict[str, Any], reason: str) -> dict[str, Any]:
    """The checks every stopped phase 1 passes; returns `phase1.json`."""
    assert found["code"] == 2, found["out"] + found["err"]
    phase1 = read(found["folder"] / "phase1.json")
    assert phase1["passed"] is False and phase1["stops"] == [reason]
    assert phase1["episodes"] == 3 * len(GATE_ARMS)
    assert phase1["spent"] > 0
    assert f"${phase1['spent']:.4f}" in found["out"]
    assert not (found["folder"] / "records" / "episodes.jsonl").exists()
    assert {seed for _arm, seed in filter(None, found["matched"])} <= set(PHASE1_SEEDS)
    return dict(phase1)


# ---------------------------------------------------------------------------
# the 168 episodes, and a pass going on in the same folder
# ---------------------------------------------------------------------------


def test_phase_1_is_three_seeds_once_on_every_arm_168_episodes(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = clean_run(LUNA, tmp_path_factory)
    assert found["code"] == 0, found["out"] + found["err"]
    phase1 = read(found["folder"] / "phase1.json")
    assert phase1["passed"] is True and phase1["stops"] == []
    assert phase1["episodes"] == PHASE1_EPISODES == 168
    played = [pair for pair in found["matched"] if pair is not None and pair[1] in PHASE1_SEEDS]
    # Retrofitted 2026-11-18, ruled yes by Taylor in the build session: `arguments:a2`'s task is
    # `history:t0`'s (the same request, tools and calls), so the fake, which tells a task by
    # those, plays its requests as `history:t0`'s.  The 168 episodes above are every arm's.
    assert {arm for arm, _seed in played} == set(ARMS) - {"arguments:a2"}
    assert {seed for _arm, seed in played} == set(PHASE1_SEEDS)
    record = read(found["folder"] / "record.json")
    assert record["phase1_seeds"] == list(PHASE1_SEEDS) and record["phase1_attempts"] == 1


def test_phase_1_is_gated_before_any_episode_of_the_card_is_asked_for(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = clean_run(LUNA, tmp_path_factory)
    seeds = [pair[1] for pair in found["matched"] if pair is not None]
    last_of_phase_1 = max(i for i, seed in enumerate(seeds) if seed in PHASE1_SEEDS)
    first_of_the_card = min(i for i, seed in enumerate(seeds) if seed not in PHASE1_SEEDS)
    assert last_of_phase_1 < first_of_the_card


def test_a_passing_phase_1_goes_on_in_the_same_folder_and_is_not_run_twice(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = clean_run(LUNA, tmp_path_factory)
    folder = found["folder"]
    assert (folder / "phase1.json").exists() and (folder / "records" / "episodes.jsonl").exists()
    assert complete_arms(folder, found["design"]) == list(ARMS)
    assert not {row["seed"] for row in lines(folder)} & set(PHASE1_SEEDS)
    status = read(folder / "status.json")
    assert status["verdict"] == "done" and status["stop"] is None
    assert f"${status['spent']:.4f}" in found["out"]


def test_what_phase_1_measured_is_written_down(tmp_path_factory: pytest.TempPathFactory) -> None:
    phase1 = read(clean_run(LUNA, tmp_path_factory)["folder"] / "phase1.json")
    assert phase1["length_stop_share"] == 0.0 and phase1["no_call_share"] == 0.0
    assert phase1["answer_models"] == [LUNA]
    assert phase1["spent"] > 0


# ---------------------------------------------------------------------------
# the four stops
# ---------------------------------------------------------------------------


def test_stop_1_one_episode_with_an_instrument_label(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Every completion of one task of a top arm is answered 500."""
    play = Play(behaviour=Behaviour.from_mapping({"error": {"depth:d8": [SEED]}}))
    found = gate(tmp_path, tmp_path_factory, play)
    stopped(found, "instrument")


def test_stop_2_more_than_two_in_a_hundred_calls_cut_by_the_length_cap(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Every phase 1 task of one middle-level arm has its one call cut: three cut calls."""
    cut = {"shape:w2": frozenset()}
    total, cut_calls = calls_in_phase_1(registry_cache(tmp_path_factory), cut)
    assert cut_calls == 3 and cut_calls / total > 0.02, (cut_calls, total)
    found = gate(tmp_path, tmp_path_factory, Play(length=cut))
    phase1 = stopped(found, "length_stops")
    assert phase1["length_stop_share"] == pytest.approx(cut_calls / total)


def test_stop_3_more_than_a_tenth_of_the_base_episodes_made_no_tool_call(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """One base arm answers without calling a tool at each of its three tasks: 3 of the 12 base
    episodes."""
    assert len([arm for arm in GATE_ARMS if arm in BASES]) == 4
    play = Play(behaviour=Behaviour.from_mapping({"no_call": ["similarity:s0"]}))
    found = gate(tmp_path, tmp_path_factory, play)
    phase1 = stopped(found, "no_call")
    assert phase1["no_call_share"] == pytest.approx(3 / 12)


def test_no_tool_call_on_an_arm_that_is_no_base_does_not_stop_it(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A top arm that never calls a tool is the dial's effect, scored as failures."""
    play = Play(behaviour=Behaviour.from_mapping({"no_call": ["depth:d8"]}))
    found = gate(tmp_path, tmp_path_factory, play)
    assert found["code"] == 0, found["out"] + found["err"]
    phase1 = read(found["folder"] / "phase1.json")
    assert phase1["passed"] is True and phase1["no_call_share"] == 0.0


def test_stop_4_an_answer_that_names_another_model(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    play = Play(provider=Provider(answers_as="gpt-6-luna-2026-11-01"))
    found = gate(tmp_path, tmp_path_factory, play)
    phase1 = stopped(found, "answer_model")
    assert phase1["answer_models"] == ["gpt-6-luna-2026-11-01"]


def test_an_alias_the_providers_page_documents_does_not_stop_it(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """With the other name in the model's row as an alias the same answers pass, and every
    record says which name answered."""
    assert tuple(card_run().MODELS[LUNA].aliases) == ()
    row = dataclasses.replace(card_run().MODELS[LUNA], aliases=("gpt-6-luna-2026-11-01",))
    play = Play(provider=Provider(answers_as="gpt-6-luna-2026-11-01"))
    found = gate(tmp_path, tmp_path_factory, play, row=row)
    assert found["code"] == 0, found["out"] + found["err"]
    assert read(found["folder"] / "phase1.json")["answer_models"] == ["gpt-6-luna-2026-11-01"]
    assert {tuple(row["answer_models"]) for row in lines(found["folder"])} == {
        ("gpt-6-luna-2026-11-01",)}
    assert {row["model"] for row in lines(found["folder"])} == {LUNA}


# ---------------------------------------------------------------------------
# under each threshold, and after a stop
# ---------------------------------------------------------------------------


def test_one_cut_call_and_one_silent_base_episode_are_under_both_thresholds(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """One base task's one call is cut: 1 call in more than fifty, and 1 of the 12 base episodes
    without a tool call.  Phase 1 passes and the run goes on to its end in the same folder."""
    cut = {"history:t0": frozenset({SEED})}
    total, cut_calls = calls_in_phase_1(registry_cache(tmp_path_factory), cut)
    assert cut_calls == 1 and cut_calls / total <= 0.02, (cut_calls, total)
    found = gate(tmp_path, tmp_path_factory, Play(length=cut))
    assert found["code"] == 0, found["out"] + found["err"]
    phase1 = read(found["folder"] / "phase1.json")
    assert phase1["passed"] is True and phase1["stops"] == []
    assert phase1["length_stop_share"] == pytest.approx(1 / total)
    assert phase1["no_call_share"] == pytest.approx(1 / 12)
    assert complete_arms(found["folder"], found["design"]) == list(found["design"].arms)


def test_a_cut_call_is_counted_on_its_episodes_record(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A task of the card's own seeds whose call is cut: its records count one length stop each,
    and every other record none."""
    design = gate_design()
    play = Play(length={"shape:w2": frozenset({design.seeds[0]})})
    found = gate(tmp_path, tmp_path_factory, play)
    assert found["code"] == 0, found["out"] + found["err"]
    for row in lines(found["folder"]):
        cut = row["arm_id"] == "shape:w2" and row["seed"] == design.seeds[0]
        assert row["length_stops"] == (1 if cut else 0), (row["arm_id"], row["seed"])
        if cut:
            assert (row["turns"], row["sampled_calls"], row["strict"]) == (1, 0, False)


def test_a_stopped_phase_1_is_not_run_again_in_its_folder(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    from tests.fd2_fakes import free_port

    port = free_port()
    play = Play(behaviour=Behaviour.from_mapping({"no_call": ["similarity:s0"]}))
    first = gate(tmp_path, tmp_path_factory, play, port=port)
    kept = (first["folder"] / "phase1.json").read_bytes()
    again = gate(tmp_path, tmp_path_factory, Play(), port=port)
    assert (first["code"], again["code"]) == (2, 2)
    assert again["chats"] == 0
    assert (first["folder"] / "phase1.json").read_bytes() == kept
    assert re.search(r"phase 1", again["out"], flags=re.I)


def test_the_stops_are_named_from_a_closed_list_in_a_fixed_order(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Two causes at once are both named, in the order the design lists them."""
    play = Play(
        behaviour=Behaviour.from_mapping({"no_call": ["similarity:s0"]}),
        provider=Provider(answers_as="another-model"),
    )
    found = gate(tmp_path, tmp_path_factory, play)
    assert found["code"] == 2, found["out"] + found["err"]
    stops = read(found["folder"] / "phase1.json")["stops"]
    assert stops == ["no_call", "answer_model"]
    assert set(stops) <= set(STOPS)
