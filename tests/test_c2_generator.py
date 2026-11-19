"""C2.13: the run refuses any generator but the one frozen for 0.5.0.

Ruled 2026-11-18: the generator is frozen from the merge of generator "4" until the last paid
run.  The run refuses any generator but "4" at built-in hash
`98cbd21dc912bed4dbde5398748b832aae4711c2096f0092c296eab77b52eac3` and own-tools hash
`f01bcf327965f6c8c5351cc7c985b9e1bf6cf5caacbeb8fbba2cc06215886032`.

Shapes decided here
-------------------
* The hosted driver holds what it expects in `card_run.FROZEN_GENERATOR_HASH`,
  `FROZEN_OWN_GENERATOR_HASH`, `GENERATOR_VERSION` and `OWN_GENERATOR_VERSION`, and compares
  them with what the installed package makes before it reads a key or writes a folder.  A
  refusal is one `error:` line that shows both values, and exit 1; a label is shown in double
  quotes, as every refusal of a label shows one.  `card_run.check_generators()` is the check,
  and raises `card_run.GeneratorMoved`.
* The notebook's driver holds the own-tools hash in
  `calibration_run.EXPECTED_OWN_GENERATOR_HASH`, beside `EXPECTED_GENERATOR_HASH`, and its
  `preflight` stops on either before it asks the server anything.

The tests set the *expected* value to another one, as the knob probe's tests do: the package's
own generators cannot be changed from a test without editing the frozen files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks import calibration_run as run
from tests.c2_fake import bundle_for
from tests.c2_support import (
    BUILT_IN_HASH,
    DESIGN,
    LUNA,
    OWN_HASH,
    card_run,
    clean_run,
    drive,
    needs_uv,
    registry_cache,
    small_design,
)

OTHER = "0" * 64
ARMS = ("depth:d1", "landed:l0")


def test_the_two_hashes_are_the_ones_ruled_and_every_copy_equals_them() -> None:
    from tests.test_frozen_generator import FROZEN_GENERATOR_HASH
    from tests.test_o2b_kept import OWN_GENERATOR_HASH

    assert BUILT_IN_HASH == "98cbd21dc912bed4dbde5398748b832aae4711c2096f0092c296eab77b52eac3"
    assert OWN_HASH == "f01bcf327965f6c8c5351cc7c985b9e1bf6cf5caacbeb8fbba2cc06215886032"
    assert FROZEN_GENERATOR_HASH == run.EXPECTED_GENERATOR_HASH == BUILT_IN_HASH
    assert OWN_GENERATOR_HASH == OWN_HASH
    assert card_run().FROZEN_GENERATOR_HASH == BUILT_IN_HASH
    assert card_run().FROZEN_OWN_GENERATOR_HASH == OWN_HASH
    assert run.EXPECTED_OWN_GENERATOR_HASH == OWN_HASH
    assert (card_run().GENERATOR_VERSION, card_run().OWN_GENERATOR_VERSION) == ("4", "own-4")


def test_the_installed_generators_are_the_frozen_ones() -> None:
    """A guard, which holds today: the freeze is of these two."""
    from poisson_tasks import arms
    from poisson_tasks.own import generator

    assert arms.DEFAULT_GENERATOR_VERSION == "4" and generator.GENERATOR_VERSION == "own-4"
    assert bundle_for("depth:d1", cal.seed_list()[0]).generator_hash == BUILT_IN_HASH
    assert bundle_for("spread:p4", cal.seed_list()[0]).generator_hash == BUILT_IN_HASH
    assert generator.generator_hash() == OWN_HASH
    assert bundle_for("landed:l1", cal.seed_list()[0]).generator_hash == OWN_HASH


def refused(found: dict[str, Any], shows: tuple[str, str]) -> None:
    assert found["code"] == 1, found["out"] + found["err"]
    assert found["err"].startswith("error: ") and found["err"].count("\n") == 1, found["err"]
    assert shows[0] in found["err"] and shows[1] in found["err"], found["err"]
    assert found["chats"] == 0 and found["gets"] == []
    assert not found["folder"].exists()


@pytest.mark.parametrize(
    ("name", "shows"),
    [
        ("FROZEN_GENERATOR_HASH", (BUILT_IN_HASH, OTHER)),
        ("FROZEN_OWN_GENERATOR_HASH", (OWN_HASH, OTHER)),
    ],
)
def test_it_refuses_a_generator_whose_hash_is_not_the_frozen_one(
    name: str, shows: tuple[str, str], tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    found = drive(
        tmp_path,
        registry_cache(tmp_path_factory),
        design=small_design(arms=ARMS),
        before=lambda mp: mp.setattr(card_run(), name, OTHER),
    )
    refused(found, shows)


@pytest.mark.parametrize(
    ("name", "label", "expected"),
    [("GENERATOR_VERSION", "4", "5"), ("OWN_GENERATOR_VERSION", "own-4", "own-5")],
)
def test_it_refuses_a_generator_at_another_label(
    name: str,
    label: str,
    expected: str,
    tmp_path: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = drive(
        tmp_path,
        registry_cache(tmp_path_factory),
        design=small_design(arms=ARMS),
        before=lambda mp: mp.setattr(card_run(), name, expected),
    )
    refused(found, (f'"{label}"', f'"{expected}"'))


def test_a_design_with_no_own_tools_arm_is_still_held_to_both() -> None:
    """The check is of the install, not of the arms a call happens to run."""
    refusal = card_run().check_generators
    refusal()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(card_run(), "FROZEN_OWN_GENERATOR_HASH", OTHER)
        with pytest.raises(card_run().GeneratorMoved) as moved:
            refusal()
    assert OWN_HASH in str(moved.value) and OTHER in str(moved.value)


@needs_uv
def test_the_record_holds_both_hashes_before_the_first_model_call(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found = clean_run(LUNA, tmp_path_factory)
    record = found["seen"]["record"]
    assert record is not None, "no record when the first model call was made"
    assert record["frozen_generator_hash"] == BUILT_IN_HASH
    assert record["own_generator_hash"] == OWN_HASH
    assert (record["generator_version"], record["own_generator_version"]) == ("4", "own-4")
    assert record["design"] == DESIGN
    rows = {row for row in (found["folder"] / "records" / "episodes.jsonl").read_text().splitlines()}
    assert rows, "the run recorded nothing"


@pytest.mark.parametrize(
    ("name", "shows"),
    [
        ("EXPECTED_GENERATOR_HASH", (BUILT_IN_HASH, OTHER)),
        ("EXPECTED_OWN_GENERATOR_HASH", (OWN_HASH, OTHER)),
    ],
)
def test_the_notebooks_preflight_stops_on_either_before_it_asks_the_server(
    name: str,
    shows: tuple[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    asked: list[str] = []
    ctx = run.Context(local=tmp_path / "local", durable=tmp_path / "durable", port=9,
                      mirror_interval=30.0, pin=run.QWEN3_8_27B, design=DESIGN)
    monkeypatch.setattr(run, "gpu_facts",
                        lambda: {"name": "NVIDIA A100-SXM4-80GB", "driver": "580.82.07"})
    monkeypatch.setattr(run, "check_server", lambda *a, **k: asked.append("server"))
    monkeypatch.setattr(run, "_http", lambda *a, **k: asked.append("http"))
    monkeypatch.setattr(run, name, OTHER)
    assert run.cmd_preflight(ctx) == 1
    said = capsys.readouterr().out.strip()
    assert asked == []
    assert said.startswith("STOP: ") and "\n" not in said, said
    assert shows[0] in said and shows[1] in said, said
    assert not (tmp_path / "durable").exists()
