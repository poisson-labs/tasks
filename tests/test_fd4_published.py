"""The published cards, frozen as tests: `poisson_tasks.cards`.

The invariant is FD4.7 of the front door's plan (spec §4.4 and §9.7): `published()` lists the
published cards, each named by its model's short name and never by its folder (ruled 2026-10-03),
and `recompute` rebuilds each from its records and says whether it is identical and current.

**A defect in the plan, reported.**  The plan's FD4.7 says `recompute` gives "identical and
current" for both cards.  Both were measured at generator version `"0"`, and since the knobs'
shared base moved the generator (K1.11, frozen in `tests/test_k1_calibration.py`), both say they
are stale.  The spec (§4.4) asks `card --published` to "say whether it is current for this
install"; it wins.  The test reads whether a card is current from the hashes: its recorded
generator hash against the one the package gives.  Today that is false for both; for the new
cards it will be true.

Shapes decided here, where the spec leaves them open
----------------------------------------------------

**1. `published()` returns a tuple of `PublishedCard`** (`name`, `folder`), one per shipped card,
read from the package's own `cards/` folder when it has one and otherwise from the checkout's
`calibration/` (as the estimate reads them, FD3 Session A's yes/no 5).  The folder holds the
card's `episodes.jsonl` and `artifact.json`, and `tallies.json` when the run kept one.

**2. `recompute(card)` returns a `Recomputed`**: `identical` (the artifact rebuilt from the
folder's records, under the provenance its `artifact.json` recorded and with its tally, written
as `write_artifact` writes it, is `artifact.json` byte for byte), `current`, `records` (how many
records it was rebuilt from) and `artifact` (the rebuilt artifact, which `card --compare
published` reads).  A card whose files no longer rebuild is not identical; it is not an error.

**Assertions the new cards will change** (listed in the session's filing): the two names.
Everything else reads the shipped files.
"""

from __future__ import annotations

import dataclasses
import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest


from tests.fd4_support import package_generator_hash, shipped_folders

NAMES = {"gpt-5-nano", "qwen3-8b"}
"""The two published cards' names, ruled 2026-10-03.  The new cards change this."""


def cards() -> Any:
    import importlib

    return importlib.import_module("poisson_tasks.cards")


def by_artifact(folder: Path) -> bytes:
    return (folder / "artifact.json").read_bytes()


def test_fd4_7_published_lists_every_shipped_card_by_its_short_name() -> None:
    listed = cards().published()
    shipped = {by_artifact(folder): folder for folder in shipped_folders()}
    assert {card.name for card in listed} == NAMES
    assert len(listed) == len(shipped) == len({card.name for card in listed})
    assert {by_artifact(Path(card.folder)) for card in listed} == set(shipped)
    for card in listed:
        assert card.name != Path(card.folder).name
        assert not re.search(r"[0-9a-f]{7,}", card.name), card.name


def test_fd4_7_recompute_rebuilds_each_card_and_says_whether_it_is_current() -> None:
    package = package_generator_hash()
    for card in cards().published():
        folder = Path(card.folder)
        stored = json.loads(by_artifact(folder))
        answer = cards().recompute(card)
        assert answer.identical is True, card.name
        assert answer.records == len(
            (folder / "episodes.jsonl").read_text(encoding="utf-8").splitlines())
        assert answer.current == (stored["provenance"]["generator_hash"] == package)
        assert json.loads(json.dumps(answer.artifact.as_dict())) == stored


@pytest.mark.parametrize("change", ["figure", "tally", "record"])
def test_fd4_7_recompute_finds_a_card_that_does_not_rebuild(change: str, tmp_path: Path) -> None:
    """A copy of a published card with one figure of its artifact changed, with a failure added
    to its tally, or with a record taken out, is not identical; an untouched copy is (the
    control)."""
    (card, *_) = cards().published()
    folder = Path(card.folder)
    copy = tmp_path / "copy" / folder.name
    shutil.copytree(folder, copy)
    untouched = cards().recompute(dataclasses.replace(card, folder=copy))
    assert untouched.identical is True
    if change == "figure":
        stored = json.loads(by_artifact(copy))
        stored["cells"][0]["pass_at_1"] = round(stored["cells"][0]["pass_at_1"] + 0.001, 6)
        (copy / "artifact.json").write_text(json.dumps(stored, indent=2, sort_keys=True) + "\n",
                                            encoding="utf-8")
    elif change == "tally":
        arm = json.loads(by_artifact(copy))["cells"][0]["arm_id"]
        tallies_path = copy / "tallies.json"
        tallies = json.loads(tallies_path.read_text()) if tallies_path.exists() else {}
        tallies[arm] = {"api_error": 1}
        tallies_path.write_text(json.dumps(tallies, indent=2), encoding="utf-8")
    else:
        lines = (copy / "episodes.jsonl").read_text(encoding="utf-8").splitlines(keepends=True)
        (copy / "episodes.jsonl").write_text("".join(lines[1:]), encoding="utf-8")
    answer = cards().recompute(dataclasses.replace(card, folder=copy))
    assert answer.identical is False
    if change == "record":
        assert answer.records == untouched.records - 1
