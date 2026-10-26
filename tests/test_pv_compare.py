"""Two runs read side by side on what produced them, and the published cards left as they are,
frozen as tests.

The invariants:
- the two published cards keep their bytes and carry no record: `card --published` rebuilds them
  byte for byte and its `--json` gains nothing, and `card --compare published` on a run says what
  it said before;
- `card RUN --compare OTHER` sets two runs side by side (exit 0, `ok`, `compare.md` ending with
  `calibration.render_side_by_side` of the two cards) when they measured the same tasks the same
  way, a version-only difference being one `note:`;
- a changed generator is named with both hashes and no figure is set beside another;
- a side that recorded nothing is said so: with other tasks the answer is `different` and says what
  is not known; with the same task ids it is `ok` with a note.

`--json` carries `verdict`, `sentence`, `note`, `changed` (the record's keys whose values differ, in
the docs' order, `[]` when a side recorded nothing), `a` and `b` (each `folder` and `produced_by`)
and `wrote`.  The run folders are copies of the `tests/fd4_support.py` scenarios under names of
their own, so each side's name is its folder's.  On your own tools the same rules are held in
`tests/test_pv_records.py`, beside its one own-tools run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import needs_uv
from tests.fd4_support import RunFolders, fd4_runs
from tests.fd5_support import World, world
from tests.pv_support import (
    BUILT_IN_GENERATOR,
    GENERATOR_0_PREFIX,
    GENERATOR_KEYS,
    RECORD,
    SECTION_1,
    SHIPPED,
    TOOL_KEYS,
    bare,
    changed,
    copy_run,
    invoke_json,
    record_lines,
    rewrite_first_line,
    sha256,
)

__all__ = ["fd4_runs", "world"]

# The two published cards' `artifact.json`, as shipped.
PUBLISHED = {
    "40446353be3f9b4f349df674245e29029188ebee3b66936c1b5b9d4e31a7d6de",
    "a595d8b1bb4246162e94ec47cd81e026723f69337880fa30ab346e6800343361",
}
EARLIER_BUILD = ("the published cards were measured on an earlier build of the generator, so "
                 "this release does not set them side by side")


def calibration() -> Any:
    from poisson_tasks import calibration as module

    return module


def compare(a: Path, b: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    ran, document = invoke_json(["card", str(a), "--compare", str(b)], monkeypatch)
    assert ran.code == 0, ran
    assert set(document) >= {"verdict", "sentence", "note", "changed", "a", "b", "wrote"}, ran
    assert not (b / "card").exists(), "nothing of the other run's is written"
    return document


def side(document: dict[str, Any], key: str, folder: Path) -> dict[str, Any] | None:
    """One side's entry: its folder, and its record with `resumed_with` set aside."""
    entry = document[key]
    assert set(entry) == {"folder", "produced_by"}, entry
    assert Path(entry["folder"]).name == folder.name, entry
    if entry["produced_by"] is None:
        return None
    return {k: v for k, v in entry["produced_by"].items() if k != "resumed_with"}


def what_produced_each(text: str, keys: list[str]) -> None:
    """One table row per key of the record, marked `differs` exactly where the values differ."""
    lines = text.splitlines()
    start = lines.index("## What produced each")
    table: list[str] = []
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        if line.startswith("|"):
            table.append(line)
    for key in SECTION_1:
        found = [line for line in table if re.search(rf"(?<![a-z_]){key}(?![a-z_])", line)]
        assert len(found) == 1, (key, table)
        assert ("differs" in found[0]) == (key in keys), (key, found[0])


def side_by_side(a: Path, b: Path) -> str:
    cal = calibration()
    return str(cal.render_side_by_side({a.name: cal.card_from_run(a).artifact,
                                        b.name: cal.card_from_run(b).artifact}))


def same_tasks(a: Path, b: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """`ok`, the side-by-side sentence, and `compare.md` ending with the two cards side by side."""
    document = compare(a, b, monkeypatch)
    assert document["verdict"] == "ok", document
    assert document["sentence"] == (
        f"{a.name} and {b.name} measured the same tasks the same way: compare.md sets them side by "
        "side")
    text = (a / "card" / "compare.md").read_text(encoding="utf-8")
    assert text.endswith(side_by_side(a, b))
    return document


def both_recorded(a: Path, b: Path, document: dict[str, Any]) -> list[str]:
    (line_a,), (line_b,) = record_lines(a), record_lines(b)
    keys = changed(bare(line_a), bare(line_b))
    assert document["changed"] == keys
    assert side(document, "a", a) == bare(line_a)
    assert side(document, "b", b) == bare(line_b)
    what_produced_each((a / "card" / "compare.md").read_text(encoding="utf-8"), keys)
    return keys


# ---------------------------------------------------------------------------
# the published cards
# ---------------------------------------------------------------------------


@needs_uv
def test_pv_12_the_published_cards_are_untouched(
    fd4_runs: RunFolders, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    stored = sorted(SHIPPED.glob("*/artifact.json"))
    assert {sha256(path.read_bytes()) for path in stored} == PUBLISHED and len(stored) == 2
    for path in stored:
        assert "produced_by" not in json.loads(path.read_text(encoding="utf-8"))["provenance"]

    ran, document = invoke_json(["card", "--published"], monkeypatch)
    assert ran.code == 0 and document["verdict"] == "ok", ran
    assert set(document) == {"schema", "verdict", "sentence", "cards"}
    for entry in document["cards"].values():
        assert set(entry) == {"identical", "current", "records"} and entry["identical"] is True

    folder = copy_run(fd4_runs["strict"].folder, world.tmp / "strict-run")
    ran, document = invoke_json(["card", str(folder), "--compare", "published"], monkeypatch)
    assert ran.code == 0, ran
    assert (document["verdict"], document["sentence"]) == ("different", EARLIER_BUILD)
    assert (folder / "card" / "compare.md").read_text(encoding="utf-8") == EARLIER_BUILD + "\n"


# ---------------------------------------------------------------------------
# the same tasks
# ---------------------------------------------------------------------------


@needs_uv
def test_pv_13_one_plan_run_twice_is_set_side_by_side(
    fd4_runs: RunFolders, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = copy_run(fd4_runs["strict"].folder, world.tmp / "strict-run")
    b = copy_run(fd4_runs["strict_again"].folder, world.tmp / "strict-again-run")
    document = same_tasks(a, b, monkeypatch)
    keys = both_recorded(a, b, document)
    assert not set(keys) & {*GENERATOR_KEYS, *TOOL_KEYS}, keys
    assert document["note"] is None


@needs_uv
def test_pv_13_another_model_on_the_same_tasks_is_set_side_by_side(
    fd4_runs: RunFolders, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = copy_run(fd4_runs["strict"].folder, world.tmp / "strict-run")
    b = copy_run(fd4_runs["qwen"].folder, world.tmp / "qwen-run")
    document = same_tasks(a, b, monkeypatch)
    keys = both_recorded(a, b, document)
    assert "plan_hash" in keys and not set(keys) & {*GENERATOR_KEYS, *TOOL_KEYS}, keys
    assert document["note"] is None


@needs_uv
def test_pv_13_a_version_alone_is_one_note(
    fd4_runs: RunFolders, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = copy_run(fd4_runs["strict"].folder, world.tmp / "strict-run")
    b = copy_run(fd4_runs["strict_again"].folder, world.tmp / "strict-again-later")
    later = "99.0.0"  # a version no install has, so b is always made with another one
    rewrite_first_line(b, poisson_tasks_version=later)
    (line_a,), (line_b,) = record_lines(a), record_lines(b)
    document = same_tasks(a, b, monkeypatch)
    keys = both_recorded(a, b, document)
    assert "poisson_tasks_version" in keys and not set(keys) & {*GENERATOR_KEYS, *TOOL_KEYS}
    assert str(document["note"]).removeprefix("note: ") == (
        f"{a.name} was made with poisson-tasks {line_a['poisson_tasks_version']} and verifiers "
        f"{line_a['verifiers_version']}, {b.name} with poisson-tasks {later} and verifiers "
        f"{line_b['verifiers_version']}; the generator and the tasks are the same")


# ---------------------------------------------------------------------------
# another generator
# ---------------------------------------------------------------------------


@needs_uv
def test_pv_14_another_generator_is_named_and_no_figure_is_set_beside_another(
    fd4_runs: RunFolders, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from poisson_tasks.tasks import generate

    made = fd4_runs["generator_0"]
    zero = generate(made.plan.arms[0], made.plan.seeds[0]).generator_hash
    assert zero.startswith(GENERATOR_0_PREFIX)
    a = copy_run(fd4_runs["strict"].folder, world.tmp / "strict-run")
    b = copy_run(made.folder, world.tmp / "generator-0-run")
    assert record_lines(b)[0]["builtin_generator_hash"] == zero
    document = compare(a, b, monkeypatch)
    assert document["verdict"] == "different", document
    assert document["sentence"] == (
        f"{a.name} and {b.name} were made by different generators ({BUILT_IN_GENERATOR[:12]} and "
        f"{zero[:12]}), so their tasks differ and a shift between them is not the model's alone")
    keys = both_recorded(a, b, document)
    assert {"generator_version", "builtin_generator_hash"} <= set(keys)
    text = (a / "card" / "compare.md").read_text(encoding="utf-8")
    assert document["sentence"] in text
    assert "# Cards side by side" not in text and "| level | card | model |" not in text
    for folder in (a, b):
        assert calibration().card_from_run(folder).document in text, folder.name


# ---------------------------------------------------------------------------
# a side that recorded nothing
# ---------------------------------------------------------------------------


@needs_uv
def test_pv_15_a_side_that_recorded_nothing_and_measured_other_tasks_is_said_so(
    fd4_runs: RunFolders, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = copy_run(fd4_runs["strict"].folder, world.tmp / "strict-run")
    b = copy_run(fd4_runs["generator_0"].folder, world.tmp / "generator-0-before")
    (b / RECORD).unlink()
    document = compare(a, b, monkeypatch)
    assert document["verdict"] == "different", document
    assert document["sentence"] == (
        f"{a.name} and {b.name} did not measure the same tasks, and {b.name} recorded nothing of "
        "what produced it (made before poisson-tasks 0.2.0), so whether its tools or generator "
        "changed is not known")
    assert document["changed"] == []
    assert side(document, "b", b) is None and side(document, "a", a) is not None


@needs_uv
def test_pv_15_a_side_that_recorded_nothing_with_the_same_task_ids_is_one_note(
    fd4_runs: RunFolders, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = copy_run(fd4_runs["strict"].folder, world.tmp / "strict-run")
    b = copy_run(fd4_runs["strict_again"].folder, world.tmp / "strict-again-before")
    (b / RECORD).unlink()
    document = same_tasks(a, b, monkeypatch)
    assert document["changed"] == []
    assert side(document, "b", b) is None and side(document, "a", a) is not None
    assert str(document["note"]).removeprefix("note: ") == (
        f"{b.name} was made before poisson-tasks 0.2.0 and recorded nothing of what produced it; "
        f"its task ids match {a.name}'s, so the tasks are the same")
