"""C2.2: the four own-tools arms run on acme's OpenAI tool file, shipped as package data.

The design: `landed:l0`, `landed:l1`, `lagged:g0` and `lagged:g1` run on
`poisson_tasks/data/fixtures/acme-openai-chat.json`, byte-equal to
`tests/fixtures/o1/acme-openai-chat.json`, with `read = ["get_order", "search_orders",
"list_channels"]` declared (the OpenAI shape states no effects), on the card's sixty seeds; the
file ships in the wheel, so the four arms can be run again from an install, and its sha256 is in
the run's record.

Readings made here: the set is named after the file (`acme-openai-chat`), as a settings file
that names no `[own] name` does; no write is declared, no intent and no flow.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

import poisson_tasks
from tests.c2_fake import ACME_FILE, ACME_NAME, ACME_READS, bundle_for
from tests.c2_support import (
    ACME_SHA256,
    LUNA,
    OWN_ARMS,
    by_arm,
    card_run,
    card_seeds,
    clean_run,
    lines,
    needs_uv,
    read,
)
from tests.fd6_support import built_wheel, wheel_names

__all__ = ["built_wheel", "wheel_names"]

SHIPPED = "poisson_tasks/data/fixtures/acme-openai-chat.json"


def shipped() -> Path:
    return Path(poisson_tasks.__file__).resolve().parent / "data" / "fixtures" / ACME_FILE.name


def test_the_tests_fixture_is_the_file_the_design_names() -> None:
    """A guard: the digest typed in the support file is the test fixture's."""
    assert hashlib.sha256(ACME_FILE.read_bytes()).hexdigest() == ACME_SHA256
    assert len(ACME_FILE.read_bytes()) == 2613


def test_the_package_carries_the_file_byte_for_byte() -> None:
    assert shipped().is_file(), shipped()
    assert shipped().read_bytes() == ACME_FILE.read_bytes()


def test_the_wheel_carries_the_file_byte_for_byte(built_wheel: Path, wheel_names: list[str]) -> None:
    import zipfile

    assert SHIPPED in wheel_names
    with zipfile.ZipFile(built_wheel) as archive:
        assert archive.read(SHIPPED) == ACME_FILE.read_bytes()


def test_the_driver_reads_that_file_with_the_three_reads_declared() -> None:
    run = card_run()
    assert Path(run.OWN_FIXTURE).resolve() == shipped()
    assert tuple(run.OWN_READS) == ACME_READS == ("get_order", "search_orders", "list_channels")
    assert run.OWN_SET_NAME == ACME_NAME == "acme-openai-chat"


def test_the_file_reaches_both_dials_at_both_levels_on_every_card_seed() -> None:
    """A guard on the fixture, which holds today: with the reads declared the own-tools generator
    makes all four arms at each of the sixty seeds, each task naming the file's digest."""
    for arm in OWN_ARMS:
        for seed in card_seeds():
            bundle = bundle_for(arm, seed)
            assert (bundle.arm_id, bundle.seed, bundle.file_digest) == (arm, seed, ACME_SHA256)
            assert bundle.set_name == ACME_NAME and bundle.source_format == "openai"


@pytest.fixture(scope="module")
def done(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return clean_run(LUNA, tmp_path_factory)


@needs_uv
def test_the_four_arms_run_on_the_card_seeds_in_the_same_folder(done: dict[str, Any]) -> None:
    assert done["code"] == 0, done["out"] + done["err"]
    design = done["design"]
    rows = by_arm(lines(done["folder"]))
    for arm in OWN_ARMS:
        assert sorted({row["seed"] for row in rows[arm]}) == sorted(design.seeds), arm
        assert len(rows[arm]) == len(design.seeds) * design.attempts, arm
    assert set(design.seeds) <= set(card_seeds())
    played = {found[0] for found in done["matched"] if found is not None}
    assert set(OWN_ARMS) <= played


@needs_uv
def test_each_own_tools_task_is_the_one_the_fixture_makes_at_that_seed(
    done: dict[str, Any],
) -> None:
    """The run's tasks are the generator's on this file with the reads declared: every record
    of an own-tools arm carries the id of the task made here."""
    rows = by_arm(lines(done["folder"]))
    for arm in OWN_ARMS:
        expected = {seed: bundle_for(arm, seed).task_id for seed in done["design"].seeds}
        assert {row["seed"]: row["task_id"] for row in rows[arm]} == expected, arm


@needs_uv
def test_the_record_names_the_file_by_its_digest_and_its_declared_reads(
    done: dict[str, Any],
) -> None:
    record = read(done["folder"] / "record.json")
    own = record["own_tools"]
    assert own["fixture_sha256"] == ACME_SHA256
    assert own["read"] == list(ACME_READS)
    assert own["name"] == ACME_NAME and own["tool_format"] == "openai"
    assert record["own_arms"] == list(OWN_ARMS)
