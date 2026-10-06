"""The published tasks keep their content when the generator changes, frozen as tests.

When the generator gains its new knobs, every task id moves, because an id is a hash over the
task and the generator's own bytes.  What must not move is the task: every one of the 840
(arm, seed) tasks the two published cards measured regenerates with the same prompt, tools,
goal, reference solution and every other field, apart from its id, its generator hash and its
pin record.  That is what keeps the published cards' measurements true of the tasks Tasks
generates, and what lets a rerun of the depth arms be read as a replication.

What the tests compare against
------------------------------

`tests/fixtures/k1/published-tasks.json.gz` holds the 840 tasks as the generator made them
before the change: built by running the tree at commit `c3c630e` (an archive of `src/poisson_tasks`
at that commit, nothing else on the path), every bundle written whole as canonical JSON.  It also
holds that tree's pin ledger, and its verdicts on every negative control and on sixteen seeded
random call sequences per task, which `tests/test_k1_verify.py` and `tests/test_k1_ledger.py`
read.

The fixture does not have to be taken on trust.  A task id is a hash over every other field of
its bundle, and the two published cards record the id of every task they ran.  So the first test
recomputes each stored task's id from its stored fields and finds it among the ids the published
records carry: a stored task that differed in any field from the one the cards measured would
carry another id.  The ids are recomputed here, with the construction written out below, and not
with the generator's own code, which is what is being changed.

Shapes decided here
-------------------

**1. The new tasks are generated at the default generator version.**  `arms.arm_from_id` with no
version names the arm a user gets; that is the arm whose content must not move.

**2. The pin record may move only where the change moves it.**  The rows the ledger had before
(N1 to N9 and N11) measure the same values, N12 carries the same engine hash beside the new
generator hash, and only N10 and N13 are unmeasured, each with a reason that is not the old
one.  The new rows are measured on every task.

**3. The fixture's digest is pinned.**  That test is true the moment the fixture is committed, so
it pins nothing about the build; it is here so that an edited fixture fails loudly rather than
quietly changing what "unchanged" means.
"""

from __future__ import annotations

import dataclasses
import gzip
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import generate

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "k1" / "published-tasks.json.gz"
FIXTURE_SHA256 = "84ded2aabfb5542a0614f0220ae2634a326493ae8b3e56680734f1ba534a8d6e"
CARDS = ("gpt-5-nano-2025-08-07", "qwen3-8b-b968826d")

# The task id's construction before the change: a domain line, then every bundle field but the
# id, as JSON with sorted keys and no spaces.
OLD_TASK_ID_DOMAIN = b"task-generator/task_id/1\n"

# The fields that may move, and the ledger rows that existed before the change.
MOVING = ("task_id", "generator_hash", "pins")
OLD_MEASURED = ("N1", "N2", "N3", "N4", "N5", "N6", "N7", "N8", "N9", "N11")
NEW_ROWS = tuple(f"N{i}" for i in range(19, 36))


@lru_cache(maxsize=1)
def fixture() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    return doc


def canon(value: Any) -> Any:
    """Every bundle field as JSON-able data, the way the fixture stores it."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: canon(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): canon(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [canon(v) for v in value]
    return value


def as_stored(value: Any) -> Any:
    """`canon`, then through JSON, so tuples and lists compare as the fixture holds them."""
    return json.loads(json.dumps(canon(value)))


def old_task_id(stored: dict[str, Any]) -> str:
    body = {name: value for name, value in stored.items() if name != "task_id"}
    text = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(OLD_TASK_ID_DOMAIN + text).hexdigest()


@lru_cache(maxsize=1)
def regenerated() -> dict[tuple[str, int], Any]:
    """Every stored task, generated now at the default generator version."""
    return {
        (entry["arm_id"], entry["seed"]): generate(arm_from_id(entry["arm_id"]), entry["seed"])
        for entry in fixture()["tasks"]
    }


def test_the_fixture_is_the_one_built_from_the_pinned_tree() -> None:
    """Green by construction: it hashes a committed file and pins nothing about the build."""
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_SHA256


def test_the_stored_tasks_are_the_840_the_published_cards_measured() -> None:
    stored = fixture()["tasks"]
    assert len(stored) == 840
    assert len({(entry["arm_id"], entry["seed"]) for entry in stored}) == 840
    ids = set()
    for entry in stored:
        assert old_task_id(entry["bundle"]) == entry["bundle"]["task_id"], entry["arm_id"]
        ids.add(entry["bundle"]["task_id"])
    for card in CARDS:
        lines = (REPO / "calibration" / card / "episodes.jsonl").read_text().splitlines()
        assert {json.loads(line)["task_id"] for line in lines} == ids, card


def test_every_published_task_regenerates_with_the_same_content() -> None:
    """Every field but the id, the generator hash and the pin record, byte for byte."""
    differences = []
    for entry in fixture()["tasks"]:
        new = as_stored(regenerated()[(entry["arm_id"], entry["seed"])])
        old = entry["bundle"]
        assert set(new) == set(old)
        moved = [name for name in old if name not in MOVING and new[name] != old[name]]
        if moved:
            differences.append((entry["arm_id"], entry["seed"], moved))
    assert not differences, differences[:10]


def test_the_ids_and_the_generator_hash_move_and_the_engine_hash_does_not() -> None:
    hashes = set()
    for entry in fixture()["tasks"]:
        new = regenerated()[(entry["arm_id"], entry["seed"])]
        old = entry["bundle"]
        assert new.task_id != old["task_id"]
        assert new.generator_hash != old["generator_hash"]
        assert new.engine_hash == old["engine_hash"]
        hashes.add(new.generator_hash)
    assert len(hashes) == 1


@pytest.mark.parametrize("row", OLD_MEASURED)
def test_the_rows_measured_before_measure_the_same_values(row: str) -> None:
    for entry in fixture()["tasks"]:
        new = as_stored(regenerated()[(entry["arm_id"], entry["seed"])].pins)
        assert new["values"][row] == entry["bundle"]["pins"]["values"][row], entry["arm_id"]


def test_the_pin_record_moves_only_in_the_hashes_row_the_reasons_and_the_new_rows() -> None:
    for entry in fixture()["tasks"]:
        new = regenerated()[(entry["arm_id"], entry["seed"])]
        old = entry["bundle"]["pins"]
        assert new.pins.arm_id == old["arm_id"]
        assert new.pins.values["N12"] == (new.engine_hash, new.generator_hash)
        assert old["values"]["N12"][0] == new.engine_hash
        assert set(new.pins.values) == set(old["values"]) | set(NEW_ROWS)
        assert set(new.pins.unmeasured) == set(old["unmeasured"]) == {"N10", "N13"}
        for row in ("N10", "N13"):
            assert new.pins.unmeasured[row] != old["unmeasured"][row], row
