"""`card`, frozen as tests.

The invariant is FD5.18 of the front door's plan (spec §4.4, §9; ruled 2026-10-03 on naming cards
by their model), with what cards for any plan (FD4) carried to it:
- **FD5.18** the verdict comes first and the three files are written, each the library's: the
  records, the artifact and the document `calibration.card_from_run` gives for the folder;
  `--check` exits 4 after a one-byte change to `artifact.json`, and 0 on the files as written;
  `--published` recomputes the published cards, and `--published NAME` names one by its model,
  the names `card --help` lists;
- **a refused card** (a cell over a gate) is exit 1, verdict `refused` naming the level, and
  nothing written but the records (spec §4.4);
- **a partial card carries its "What ran" section**, and the command shows it (FD4 Session B's
  yes/no 7, ruled): the facts of that section are in what `card` prints;
- **comparing a run with the published cards is refused for every run until the new cards
  exist** (FD4 Session A's finding, carried): exit 1, one line, the side-by-side renderer's own;
  nothing is written;
- **a run against the user's own server saves what the server reports about itself when the run
  starts, and the card reads that saved copy** (FD4 Session A's yes/no 5, ruled yes): the card's
  artifact is `card_from_run(folder, serving=<the saved facts>)`'s, and `card` opens no socket;
- **the default folder** is the settings file's newest run, named in what `card` prints;
- **not a run folder, or a run that recorded nothing**, is exit 1 with the library's line.

The run folders are FD4's scenarios, made by the run engine against the fixture model once per
session (`tests/fd4_support.py`), and copied into each test's own folder before `card` reads them.

Shapes decided here
-------------------

**1. `card` writes `card/` inside the run folder**: `episodes.jsonl` (`write_records`),
`artifact.json` (`write_artifact`), `card.md` (the document) and `tallies.json`
(`cards.TALLIES_FILE`, the tally per arm id), so `card --check <run>/card` recomputes the card
the way `cards.recompute` recomputes a published one.

**2. `card --compare published` keys the run's card by its folder's name and each published card
by its short name**, in `cards.published()`'s order, and refuses with the text
`calibration.render_side_by_side` raises for that mapping.

**3. "The config's newest run"** (spec §4.4) is the newest folder holding the settings file's
plan, as `run` finds it; the test's two folders both hold it.

**4. `--page --out FILE`** writes `calibration.render_combined_document` of the published cards,
in `cards.published()`'s order.

**5. The saved facts are `serving.json` in the run folder** (FD4 Session A's yes/no 5 names it),
written before the first model call and holding `providers.server_facts`'s mapping.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import harness_env, needs_uv
from tests.fd4_support import fd4_runs
from tests.fd5_support import (
    World,
    calibration,
    cards,
    config,
    error_lines,
    fixture_flags,
    invoke,
    prog,
    providers,
    tree,
    world,
    write_config,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["prog", "world", "fd4_runs", "harness_env"]


def copied(fd4_runs: Any, scenario: str, world: World, name: str | None = None) -> Path:
    made = fd4_runs[scenario]
    target = world.work / "runs" / (name or Path(made.folder).name)
    shutil.copytree(made.folder, target)
    return target


def library_card(folder: Path, serving: Any = None) -> Any:
    return calibration().card_from_run(folder, serving=serving)


def written_by_library(card: Any, scratch: Path) -> dict[str, bytes]:
    scratch.mkdir(parents=True, exist_ok=True)
    return {
        "episodes.jsonl": calibration().write_records(card.records,
                                                      scratch / "episodes.jsonl").read_bytes(),
        "artifact.json": calibration().write_artifact(card.artifact,
                                                      scratch / "artifact.json").read_bytes(),
        "card.md": (card.document or "").encode("utf-8"),
    }


def plain(text: str) -> str:
    return " ".join(text.replace("`", "").split())


@needs_uv
def test_fd5_18_the_verdict_comes_first_and_the_three_files_are_the_librarys(
    fd4_runs: Any, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = copied(fd4_runs, "first_look", world)
    expected = library_card(folder)
    ran = invoke(["card", str(folder)], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert ran.word == "ok", ran
    written = folder / "card"
    for name, data in written_by_library(expected, world.tmp / "library").items():
        assert (written / name).read_bytes() == data, name
    assert expected.claims is not None
    assert plain(expected.claims.meaning) in plain(ran.out), ran
    for line in expected.claims.not_claimed:
        assert plain(line) in plain(ran.out), line


@needs_uv
@pytest.mark.parametrize("scenario", ["first_look", "failed_once_resumed"])
def test_fd5_18_check_recomputes_a_card_and_exits_4_after_one_byte_changes(
    scenario: str, fd4_runs: Any, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clean run, and one whose card needs its tally to rebuild: an episode failed and the
    resume ran it again, so its records alone under-count what failed (`cards.TALLIES_FILE`)."""
    folder = copied(fd4_runs, scenario, world)
    assert invoke(["card", str(folder)], prog=prog, monkeypatch=monkeypatch).code == 0
    card = folder / "card"
    same = invoke(["card", "--check", str(card)], prog=prog, monkeypatch=monkeypatch)
    assert same.code == 0, same
    assert same.word == "ok", same
    artifact = card / "artifact.json"
    original = artifact.read_bytes()
    at = next(i for i, byte in enumerate(original) if chr(byte).isdigit() and i > 100)
    changed = bytearray(original)
    changed[at] = ord("7") if chr(original[at]) != "7" else ord("3")
    artifact.write_bytes(bytes(changed))
    differs = invoke(["card", "--check", str(card)], prog=prog, monkeypatch=monkeypatch)
    assert differs.code == 4, differs
    artifact.write_bytes(original)
    assert invoke(["card", "--check", str(card)], prog=prog,
                  monkeypatch=monkeypatch).code == 0


def test_fd5_18_check_takes_a_published_cards_folder(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    for card in cards().published():
        ran = invoke(["card", "--check", str(card.folder)], prog=prog, monkeypatch=monkeypatch)
        assert ran.code == 0, ran


def test_fd5_18_published_recomputes_every_published_card_and_names_one_by_its_model(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    names = [card.name for card in cards().published()]
    assert len(names) >= 2
    every = invoke(["card", "--published"], prog=prog, monkeypatch=monkeypatch)
    assert every.code == 0 and every.word == "ok", every
    for name in names:
        assert name in every.out
    for name in names:
        one = invoke(["card", "--published", name], prog=prog, monkeypatch=monkeypatch)
        assert one.code == 0 and one.word == "ok", one
        assert name in one.out
        assert not [other for other in names if other != name and other in one.out], one
    assert tree(world.work) == {}


def test_fd5_18_a_published_card_that_is_not_one_is_refused_naming_the_cards(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["card", "--published", "gpt-5"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 2, ran
    lines = error_lines(ran)
    assert len(lines) == 1, ran
    for card in cards().published():
        assert card.name in lines[0], ran


def test_fd5_18_card_help_lists_the_published_cards_names(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["card", "--help"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    for card in cards().published():
        assert card.name in ran.out, card.name
        assert card.folder.name not in ran.out or card.folder.name == card.name


@needs_uv
def test_fd5_18_a_refused_card_says_refused_and_writes_only_its_records(
    fd4_runs: Any, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = copied(fd4_runs, "silent", world)
    expected = library_card(folder)
    assert expected.verdict.word == "refused"
    ran = invoke(["card", str(folder)], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    assert ran.word == "refused", ran
    for arm, _gate in expected.verdict.refused:
        assert arm in ran.first, ran
    assert sorted(p.name for p in (folder / "card").iterdir()) == ["episodes.jsonl"]
    assert (folder / "card" / "episodes.jsonl").read_bytes() == calibration().write_records(
        expected.records, world.tmp / "episodes.jsonl").read_bytes()


def what_ran(document: str) -> list[str]:
    """The lines of the document's "What ran" section, without its heading."""
    lines = document.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## ") and "ran" in line)
    out = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if line.strip():
            out.append(line.lstrip("- ").strip())
    return out


@needs_uv
@pytest.mark.parametrize("scenario", ["partial", "cut"])
def test_fd5_18_a_partial_card_shows_what_ran(
    scenario: str, fd4_runs: Any, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = copied(fd4_runs, scenario, world)
    expected = library_card(folder)
    assert expected.verdict.partial and expected.document is not None
    ran = invoke(["card", str(folder)], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert ran.word == "ok", ran
    for line in what_ran(expected.document):
        assert plain(line) in plain(ran.out), line
    for arm in (*expected.verdict.not_run, *expected.verdict.incomplete):
        assert arm in ran.first, (arm, ran.first)
    again = copied(fd4_runs, scenario, world, name="printed")
    printed = invoke(["card", str(again), "--print"], prog=prog, monkeypatch=monkeypatch)
    assert printed.code == 0, printed
    assert expected.document in printed.out


@needs_uv
@pytest.mark.parametrize("scenario", ["first_look", "qwen"])
def test_fd5_18_comparing_with_the_published_cards_is_refused_for_every_run_today(
    scenario: str, fd4_runs: Any, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = copied(fd4_runs, scenario, world)
    card = library_card(folder)
    mapping = {folder.name: card.artifact}
    for published in cards().published():
        mapping[published.name] = cards().recompute(published).artifact
    with pytest.raises(ValueError):
        calibration().render_side_by_side(mapping)
    ran = invoke(["card", str(folder), "--compare", "published"], prog=prog,
                 monkeypatch=monkeypatch)
    # Retrofitted by ruling G12, on FD9 Session A's yes/no 4 (2026-10-20): the library still sets
    # no built-in card beside the published ones; the command says so as its verdict, `different`,
    # exit 0, and writes `compare.md`.
    assert ran.code == 0 and ran.word == "different", ran
    assert error_lines(ran) == []
    assert (folder / "card" / "compare.md").is_file()


@needs_uv
def test_fd5_18_not_a_run_folder_or_an_empty_run_is_the_librarys_line(
    fd4_runs: Any, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = copied(fd4_runs, "empty", world)
    stray = world.work / "stray"
    stray.mkdir()
    for folder in (empty, stray):
        with pytest.raises(ValueError) as refused:
            library_card(folder)
        ran = invoke(["card", str(folder)], prog=prog, monkeypatch=monkeypatch)
        assert ran.code == 1, ran
        assert error_lines(ran) == [f"error: {refused.value}"], ran
        assert not (folder / "card").exists()


@needs_uv
def test_fd5_18_without_a_folder_card_reads_the_settings_files_newest_run(
    fd4_runs: Any, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two folders of the settings file's own plan, the second run with `--again`: the card is
    the newer's, and the output names it."""
    import os

    older = copied(fd4_runs, "strict", world, name="older-run")
    newer = copied(fd4_runs, "strict", world, name="newer-run")
    held = json.loads((older / "plan.json").read_text(encoding="utf-8"))
    made = write_config(world.work / "tasks.toml", fixture_flags(
        held["plan"]["model"]["base_url"], provider="openai-compatible", tasks_per_level=2))
    assert config().plan_hash(config().resolve_plan(made)) == held["plan_hash"]
    stamp = os.stat(older / "plan.json").st_mtime_ns
    os.utime(older / "plan.json", ns=(stamp - 10**10, stamp - 10**10))
    os.utime(newer / "plan.json", ns=(stamp + 10**10, stamp + 10**10))
    ran = invoke(["card"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert "newer-run" in ran.out and (newer / "card" / "artifact.json").is_file()
    assert not (older / "card").exists()


def test_fd5_18_page_writes_the_published_cards_page(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = [cards().recompute(card).artifact for card in cards().published()]
    ran = invoke(["card", "--page", "--out", "page.md"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert (world.work / "page.md").read_text(encoding="utf-8") == \
        calibration().render_combined_document(artifacts)


# ---------------------------------------------------------------------------
# a model the user serves: the facts saved when the run starts
# ---------------------------------------------------------------------------


@needs_uv
def test_fd5_18_a_self_served_run_saves_its_servers_facts_and_the_card_reads_the_saved_copy(
    harness_env: Path, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FixtureModel() as fixture:
        flags = fixture_flags(fixture.base_url, provider="vllm", priced=False,
                              token_cap=10_000_000, tasks_per_level=2)
        made = write_config(world.work / "tasks.toml", flags)
        facts = providers().server_facts(made.model)
        assert facts["reported_by_server"], facts
        ran = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
        assert ran.code == 0, ran
    folders = [p for p in (world.work / "runs").iterdir() if p.is_dir()]
    assert len(folders) == 1
    folder = folders[0]
    saved = json.loads((folder / "serving.json").read_text(encoding="utf-8"))
    assert saved == facts
    gone = providers().server_facts(made.model)
    assert gone != facts, "the server's answer must change once it is gone"
    ran = invoke(["card"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert ran.connections == [], ran.events
    expected = library_card(folder, serving=saved)
    assert (folder / "card" / "artifact.json").read_bytes() == calibration().write_artifact(
        expected.artifact, world.tmp / "artifact.json").read_bytes()
