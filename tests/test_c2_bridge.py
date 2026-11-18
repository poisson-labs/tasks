"""C2.12: the last gpt-5-nano run, a bridge record, through the same path.

The design: the full version 2 design on `gpt-5-nano-2025-08-07`, before it retires on
2026-12-11, through the same path as the cards' runs; filed as a bridge record under
`calibration/bridge/gpt-5-nano-2025-08-07/`, not as a published card, counting toward no dial's
status; `card --compare published` does not offer it.  Taylor's cap is $15.

The run here is on a smaller design (`BRIDGE_ARMS`), against the OpenAI-like fake.

Shapes decided here
-------------------
* The bridge is a row of `card_run.MODELS` with `role == "bridge"`; `run_card` runs it as it
  runs a card's model, and the folder's record and its artifact's block say `role: "bridge"`.
* `card_run.file_run(folder, into)` writes a finished run's `artifact.json`, `episodes.jsonl`
  and `tallies.json` (the three files a committed card has) under `into`, a `calibration/`
  folder, and returns the folder it wrote: `into/bridge/<model id>/` for a bridge.
* `cards.published(into)` does not list what is under `bridge/`.

How many completion tokens a call of the bridge may take is not pinned here: it is
`tests/test_c2_pending_bridge_decoding.py`'s question.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.c2_support import (
    ARMS,
    CAPS,
    DESIGN,
    ENDPOINTS,
    LUNA,
    NANO,
    RECORD_FIELDS,
    bodies,
    card_run,
    clean_run,
    complete_arms,
    drive,
    lines,
    needs_uv,
    read,
    registry_cache,
    sampling,
    small_design,
)

BRIDGE_ARMS = ("depth:d1", "timeouts:o0", "depth:d8", "depth:d2", "landed:l0")
FILES = ("artifact.json", "episodes.jsonl", "tallies.json")


def test_the_bridge_is_gpt_5_nano_on_the_openai_preset_under_its_own_cap() -> None:
    row = card_run().MODELS[NANO]
    assert NANO == "gpt-5-nano-2025-08-07"
    assert (row.role, row.provider, row.base_url) == ("bridge", "openai", ENDPOINTS[NANO])
    assert row.cap == CAPS[NANO] == 15.0
    assert row.api_surface == "OpenAI chat completions"
    assert (row.price.input, row.price.cached_input, row.price.output) == (0.05, 0.005, 0.40)
    decoding = dict(row.decoding)
    assert (decoding["temperature"], decoding["top_p"], decoding["reasoning_effort"]) == (
        1.0, 1.0, "low")


def test_the_bridge_is_the_only_row_that_is_not_a_card() -> None:
    roles = {name: row.role for name, row in card_run().MODELS.items()}
    assert [name for name, role in roles.items() if role == "bridge"] == [NANO]
    assert set(roles.values()) == {"card", "bridge"}


@pytest.fixture(scope="module")
def bridge(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return drive(
        tmp_path_factory.mktemp("c2-bridge"),
        registry_cache(tmp_path_factory),
        model=NANO,
        design=small_design(arms=BRIDGE_ARMS),
    )


@needs_uv
def test_it_runs_through_the_same_path_phase_1_first(bridge: dict[str, Any]) -> None:
    assert bridge["code"] == 0, bridge["out"] + bridge["err"]
    folder, design = bridge["folder"], bridge["design"]
    assert read(folder / "phase1.json")["passed"] is True
    assert complete_arms(folder, design) == list(design.arms)
    for row in lines(folder):
        assert not [name for name in RECORD_FIELDS if name not in row], row["arm_id"]
        assert row["model"] == NANO and row["answer_models"] == [NANO]


@needs_uv
def test_its_requests_are_the_openai_rows_but_for_the_token_limit(bridge: dict[str, Any]) -> None:
    for body in bodies(bridge):
        sent = sampling(body)
        limit = sent.pop("max_completion_tokens")
        assert sent == {"model": NANO, "temperature": 1.0, "top_p": 1.0,
                        "reasoning_effort": "low"}, sent
        assert limit in (2048, 8192)


@needs_uv
def test_the_folder_says_it_is_a_bridge_record_of_the_same_design(bridge: dict[str, Any]) -> None:
    record = read(bridge["folder"] / "record.json")
    assert (record["role"], record["design"], record["model"]) == ("bridge", DESIGN, NANO)
    assert record["arms"] == list(bridge["design"].arms)
    assert card_run().DESIGN.arms == ARMS, "there is one registered design, the cards' own"
    block = read(bridge["folder"] / "artifact.json")["provenance"]
    card_run().check_provenance(block)
    assert (block["role"], block["design"], block["card_version"]) == ("bridge", DESIGN, 2)
    assert block["models"][0]["id"] == NANO


@needs_uv
def test_filed_it_lands_under_calibration_bridge(bridge: dict[str, Any], tmp_path: Path) -> None:
    into = tmp_path / "calibration"
    where = Path(card_run().file_run(bridge["folder"], into))
    assert where == into / "bridge" / NANO
    assert sorted(path.name for path in where.iterdir()) == sorted(FILES)
    assert (where / "episodes.jsonl").read_bytes() == (
        bridge["folder"] / "records" / "episodes.jsonl").read_bytes()
    assert read(where / "artifact.json") == read(bridge["folder"] / "artifact.json")


@needs_uv
def test_a_bridge_record_is_not_a_published_card(bridge: dict[str, Any], tmp_path: Path) -> None:
    from poisson_tasks import cards

    into = tmp_path / "calibration"
    card_run().file_run(bridge["folder"], into)
    assert cards.published(into) == ()


@needs_uv
def test_a_cards_run_is_never_filed_under_bridge(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    into = tmp_path / "calibration"
    where = Path(card_run().file_run(clean_run(LUNA, tmp_path_factory)["folder"], into))
    assert where.parent == into and where.name not in ("bridge", "generator-0")
    assert sorted(path.name for path in where.iterdir()) == sorted(FILES)
    assert not (into / "bridge").exists()


@needs_uv
def test_a_run_that_is_not_finished_is_not_filed(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A folder phase 1 stopped holds no card to file."""
    from tests.c2_fake import Play
    from tests.k9_fake import Behaviour

    stopped = drive(
        tmp_path / "work",
        registry_cache(tmp_path_factory),
        model=NANO,
        design=small_design(arms=BRIDGE_ARMS),
        play=Play(behaviour=Behaviour.from_mapping({"no_call": ["depth:d1", "timeouts:o0"]})),
    )
    assert stopped["code"] == 2, stopped["out"] + stopped["err"]
    with pytest.raises(ValueError):
        card_run().file_run(stopped["folder"], tmp_path / "calibration")
    assert not (tmp_path / "calibration").exists()
