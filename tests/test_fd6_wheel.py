"""What the built wheel carries and claims, and what the package does from it, frozen as tests.

The invariants are FD6.1 and FD6.2 of the front door's plan (spec §9.7 and §12.6), and the four
carried items that need the cards inside the package (FD3 Session A's yes/no 5, FD4 Session B's
items 1 and 3, FD5 Session B's item 1, FD4 Session A's finding 22):
- **FD6.1** the wheel carries the `poisson-tasks` console script, `poisson_tasks/py.typed`,
  `knob_status.json` and `poisson_tasks/cards/<both card folders>/`, byte for byte what the
  checkout keeps in `calibration/`; it carries no `*.tiktoken`, no `examples/`, no `tests/`;
- **FD6.2** it claims Python 3.11 to 3.13 (`>=3.11,<3.14`, matching verifiers 0.3.1) on macOS and
  Linux, and no other version or system;
- **finding 22** the module `poisson_tasks/cards.py` and the data folder `poisson_tasks/cards/`
  share a name.  The module wins an import while the folder holds no `__init__.py`, and the wheel
  holds no Python file in it, so the two cannot collide;
- **the cards in the package** from the wheel alone, with no checkout beside it: the published
  cards are listed, `card --published` rebuilds both, a plan's estimate reads them (by whatever
  the card folders are called), and a run's card carries its small-sample and comparability
  lines.

**The wheel is built from this working tree**, by `hatchling`, once per session
(`tests/fd6_support.py`), and every assertion reads the zip's own file list or its metadata, or
runs the package unpacked from it with the checkout off the path.  The cards the wheel carries
are compared with the checkout's `calibration/` folder, so they hold when the cards are replaced.
"""

from __future__ import annotations

import configparser
import email.parser
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from tests.fd3_support import needs_uv
from tests.fd4_support import fd4_runs
from tests.fd6_support import (
    CARDS_SOURCE,
    REPO,
    built_wheel,
    child_env,
    python_from,
    run_from,
    unpacked,
    wheel_names,
    with_tokenizer,
)

__all__ = ["fd4_runs", "built_wheel", "unpacked", "with_tokenizer", "wheel_names"]

DIST_INFO = "poisson_tasks-"


def card_files() -> dict[str, bytes]:
    """The checkout's published cards, by the path the wheel carries each at."""
    found = {
        f"poisson_tasks/cards/{folder.name}/{path.name}": path.read_bytes()
        for folder in sorted(CARDS_SOURCE.iterdir()) if folder.is_dir()
        for path in sorted(folder.iterdir()) if path.is_file()
    }
    assert found, "the checkout keeps no published card"
    return found


def metadata(built_wheel: Path) -> email.message.Message:
    with zipfile.ZipFile(built_wheel) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        return email.parser.Parser().parsestr(archive.read(name).decode("utf-8"))


# ---------------------------------------------------------------------------
# FD6.1 the wheel
# ---------------------------------------------------------------------------


def test_fd6_1_the_wheel_carries_the_command_the_marker_the_status_table_and_the_vocabulary(
    built_wheel: Path, wheel_names: list[str]
) -> None:
    for name in ("poisson_tasks/py.typed", "poisson_tasks/knob_status.json",
                 "poisson_tasks/data/vocabulary-v2.json", "poisson_tasks/__main__.py",
                 "poisson_tasks_own/__init__.py", "poisson_tasks_own/py.typed"):
        assert name in wheel_names, name
    with zipfile.ZipFile(built_wheel) as archive:
        entry = next(n for n in wheel_names if n.endswith(".dist-info/entry_points.txt"))
        parsed = configparser.ConfigParser()
        parsed.optionxform = str  # type: ignore[assignment,method-assign]
        parsed.read_string(archive.read(entry).decode("utf-8"))
        markers = [archive.read(f"{top}/py.typed") for top in ("poisson_tasks", "poisson_tasks_own")]
    assert dict(parsed["console_scripts"]) == {"poisson-tasks": "poisson_tasks.cli:main"}
    assert markers == [b"", b""]


def test_fd6_1_the_wheel_carries_both_published_cards_byte_for_byte_and_nothing_else_there(
    built_wheel: Path, wheel_names: list[str]
) -> None:
    wanted = card_files()
    carried = sorted(n for n in wheel_names if n.startswith("poisson_tasks/cards/"))
    assert carried == sorted(wanted), carried
    with zipfile.ZipFile(built_wheel) as archive:
        wrong = [name for name, data in wanted.items() if archive.read(name) != data]
    assert wrong == [], wrong
    folders = {name.split("/")[2] for name in carried}
    assert len(folders) == len([p for p in CARDS_SOURCE.iterdir() if p.is_dir()]) >= 2


def test_fd6_1_the_wheel_carries_no_tokenizer_file_no_examples_no_tests(
    wheel_names: list[str]
) -> None:
    from tests.fd6_support import tokenizer_file

    # the control: the checkout does hold the file the exclusion is for
    assert tokenizer_file().is_file()
    assert [n for n in wheel_names if n.endswith(".tiktoken")] == []
    tops = {name.split("/")[0] for name in wheel_names}
    assert {t for t in tops if not t.startswith(DIST_INFO)} == {"poisson_tasks", "poisson_tasks_own"}
    for left_out in ("examples", "tests", "calibration", "notebooks", "docs"):
        assert left_out not in tops
    assert [n for n in wheel_names if "__pycache__" in n or n.endswith((".pyc", ".DS_Store"))] == []


# ---------------------------------------------------------------------------
# FD6.2 the range
# ---------------------------------------------------------------------------


def test_fd6_2_the_wheel_claims_python_3_11_to_3_13_on_macos_and_linux_only(
    built_wheel: Path
) -> None:
    head = metadata(built_wheel)
    assert set(head["Requires-Python"].split(",")) == {">=3.11", "<3.14"}
    classifiers = set(head.get_all("Classifier") or [])
    versions = {c.rsplit(" :: ", 1)[1] for c in classifiers if c.startswith("Programming Language :: Python :: 3.")}
    assert versions == {"3.11", "3.12", "3.13"}
    assert {"Operating System :: MacOS", "Operating System :: POSIX :: Linux",
            "Typing :: Typed"} <= classifiers
    assert [c for c in classifiers if c.startswith("Operating System ::")
            and c not in ("Operating System :: MacOS", "Operating System :: POSIX :: Linux")] == []


def test_fd6_2_the_range_matches_what_verifiers_declares() -> None:
    """The upper bound is verifiers 0.3.1's own, which is why it is there."""
    import importlib.metadata

    declared = importlib.metadata.metadata("verifiers")["Requires-Python"]
    assert declared is not None and "<3.14" in declared.replace(" ", ""), declared


# ---------------------------------------------------------------------------
# finding 22: the module and the data folder of one name
# ---------------------------------------------------------------------------


def test_finding_22_the_data_folder_holds_no_python_so_the_module_wins_the_import(
    wheel_names: list[str], unpacked: Path, tmp_path: Path
) -> None:
    inside = [n for n in wheel_names if n.startswith("poisson_tasks/cards/")]
    assert inside and [n for n in inside if n.endswith(".py") or n.endswith("__init__.py")] == []
    assert "poisson_tasks/cards.py" in wheel_names
    done = python_from(unpacked, (
        "import json, pathlib, poisson_tasks.cards as cards\n"
        "print(json.dumps({'file': cards.__file__, 'has': hasattr(cards, 'published')}))"
    ), work=tmp_path)
    assert done.returncode == 0, done.stderr[-2000:]
    seen = json.loads(done.stdout)
    assert seen["has"] is True and Path(seen["file"]) == unpacked / "poisson_tasks" / "cards.py"


def test_finding_22_a_module_beside_a_folder_of_its_name_wins_until_the_folder_holds_an_init(
    tmp_path: Path
) -> None:
    """The control for the rule above: with a data folder beside the module, the import is the
    module's; put an `__init__.py` in the folder and the folder's package takes the name.  So
    the wheel's rule (no Python in `cards/`) is what keeps the two apart, on every Python the
    package claims."""
    package = tmp_path / "pkg"
    (package / "cards").mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "cards.py").write_text("WHO = 'the module'\n")
    (package / "cards" / "data.json").write_text("{}")

    def who() -> str:
        done = subprocess.run(
            [sys.executable, "-P", "-c", "import pkg.cards as c; print(getattr(c, 'WHO', c.__file__))"],
            cwd=tmp_path, env=child_env(tmp_path, root=tmp_path), capture_output=True, text=True,
            check=False)
        assert done.returncode == 0, done.stderr
        return done.stdout.strip()

    assert who() == "the module"
    (package / "cards" / "__init__.py").write_text("")
    assert who().endswith("cards/__init__.py")


# ---------------------------------------------------------------------------
# the cards in the package, from the wheel alone
# ---------------------------------------------------------------------------


def test_the_published_cards_are_listed_from_the_wheel_with_no_checkout_and_no_tokenizer(
    unpacked: Path, tmp_path: Path
) -> None:
    code = (
        "import json, pathlib\n"
        "from poisson_tasks import cards\n"
        "print(json.dumps([[c.name, str(c.folder)] for c in cards.published()]))"
    )
    done = python_from(unpacked, code, work=tmp_path)
    assert done.returncode == 0, done.stderr[-2000:]
    listed = json.loads(done.stdout)
    assert sorted(name for name, _ in listed) == ["gpt-5-nano", "qwen3-8b"]
    assert all(Path(folder).is_relative_to(unpacked / "poisson_tasks" / "cards") for _, folder in listed)


def test_fd5_item_1_card_published_works_from_a_clean_wheel(with_tokenizer: Path, tmp_path: Path) -> None:
    ours = run_from(None, ["card", "--published", "--plain"], work=tmp_path / "ours")
    theirs = run_from(with_tokenizer, ["card", "--published", "--plain"], work=tmp_path / "wheel")
    assert theirs.returncode == 0, theirs.stderr[-2000:]
    assert theirs.stderr == "" and theirs.stdout == ours.stdout
    assert theirs.stdout.startswith("ok  every published card rebuilds from its records byte for byte")
    assert "gpt-5-nano" in theirs.stdout and "qwen3-8b" in theirs.stdout
    one = run_from(with_tokenizer, ["card", "--published", "qwen3-8b", "--plain"], work=tmp_path / "one")
    assert one.returncode == 0 and "qwen3-8b" in one.stdout and "gpt-5-nano" not in one.stdout


DRY_RUN = ["run", "--dry-run", "--offline", "--plain"]
INIT = ["init", "--yes", "--no-check-key", "--no-fetch", "--plain"]


def test_the_estimate_reads_the_cards_in_the_package(with_tokenizer: Path, tmp_path: Path) -> None:
    """A plan's estimate from the wheel is the checkout's, and the wheel has no `calibration/`
    folder to read it from."""
    assert not (with_tokenizer / "calibration").exists()
    out = {}
    for label, root in (("ours", None), ("wheel", with_tokenizer)):
        work = tmp_path / label
        made = run_from(root, INIT, work=work)
        assert made.returncode == 0, made.stderr[-2000:]
        planned = run_from(root, DRY_RUN, work=work)
        assert planned.returncode == 0 and planned.stderr == "", planned.stderr[-2000:]
        out[label] = planned.stdout
    assert out["wheel"] == out["ours"]
    assert "estimate  from the published gpt-5-nano card for this model" in out["wheel"]


def test_the_estimate_finds_a_card_by_its_model_whatever_its_folder_is_called(
    with_tokenizer: Path, tmp_path: Path
) -> None:
    """`runs.py` keeps no table of folder names: it asks `cards.published()`.  Here the card
    folders are renamed, as a replaced design's would be."""
    renamed = tmp_path / "renamed"
    shutil.copytree(with_tokenizer, renamed)
    cards = renamed / "poisson_tasks" / "cards"
    assert cards.is_dir(), "the wheel carries no cards"
    for folder, new in zip(sorted(cards.iterdir()), ("first-card-folder", "second-card-folder")):
        folder.rename(cards / new)
    work = tmp_path / "work"
    assert run_from(renamed, INIT, work=work).returncode == 0
    planned = run_from(renamed, DRY_RUN, work=work)
    assert planned.returncode == 0, planned.stderr[-2000:]
    assert "estimate  from the published gpt-5-nano card for this model" in planned.stdout
    code = (
        "import sys\n"
        "from poisson_tasks import config, runs\n"
        "plan = config.resolve_plan(config.load_config('tasks.toml'))\n"
        "print(runs.estimate(plan, reference='qwen3-8b').source)\n"
        "try:\n"
        "    runs.estimate(plan, reference='first-card-folder')\n"
        "except ValueError as refused:\n"
        "    print(refused)\n"
    )
    done = python_from(renamed, code, work=work)
    assert done.returncode == 0, done.stderr[-2000:]
    source, refusal = done.stdout.strip().splitlines()
    assert source == "qwen3-8b"
    assert "first-card-folder" in refusal and "gpt-5-nano" in refusal and "qwen3-8b" in refusal
    assert "\n" not in refusal


def test_the_estimate_falls_back_to_the_first_card_when_no_card_measured_the_first_models_model(
    with_tokenizer: Path, tmp_path: Path
) -> None:
    """A plan whose model no card measured is estimated from the card of the model the settings
    default to (`gpt-5-nano`); with that card gone from the install, from the first card there is."""
    kept = tmp_path / "only-the-second"
    shutil.copytree(with_tokenizer, kept)
    cards = kept / "poisson_tasks" / "cards"
    for folder in cards.iterdir():
        if folder.name.startswith("gpt-5-nano"):
            shutil.rmtree(folder)
    assert sorted(p.name for p in cards.iterdir()) == ["qwen3-8b-b968826d"]
    work = tmp_path / "work"
    assert run_from(kept, INIT, work=work).returncode == 0
    planned = run_from(kept, DRY_RUN, work=work)
    assert planned.returncode == 0, planned.stderr[-2000:]
    assert "published qwen3-8b card" in planned.stdout and "gpt-5-nano card" not in planned.stdout


@needs_uv
def test_a_runs_card_from_a_clean_wheel_carries_its_small_sample_and_comparability_lines(
    fd4_runs, with_tokenizer: Path, tmp_path: Path
) -> None:
    folder = fd4_runs["first_look"].folder
    code = (
        "import json, sys\n"
        "from poisson_tasks import calibration\n"
        "claims = calibration.card_claims(calibration.card_from_run(sys.argv[1]).artifact)\n"
        "print(json.dumps({'flags': sorted(claims.flags), 'lines': list(claims.not_claimed)}))"
    )
    ours = python_from(None, code, str(folder), work=tmp_path / "ours")
    theirs = python_from(with_tokenizer, code, str(folder), work=tmp_path / "wheel")
    assert theirs.returncode == 0, theirs.stderr[-2000:]
    held = json.loads(theirs.stdout)
    assert held == json.loads(ours.stdout)
    assert {"small_sample", "not_comparable"} <= set(held["flags"])
    assert len(held["lines"]) == len(set(held["lines"])) >= 3


def test_the_repo_layout_is_unchanged_the_cards_stay_in_calibration() -> None:
    """The packaging maps `calibration/` into the wheel; it adds no `cards/` folder to the
    source tree, so the checkout falls back to `calibration/` as it did (spec §9.7)."""
    assert not (REPO / "src" / "poisson_tasks" / "cards").exists()
    assert (CARDS_SOURCE / "gpt-5-nano-2025-08-07" / "artifact.json").is_file()
