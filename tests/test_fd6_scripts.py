"""The examples and the Colab driver's help, frozen as tests: FD0's yes/no 2, the examples at
generator version `"0"` (FD6.6) and the driver's help (FD6.8, P9).

- **FD0's yes/no 2 (ruled yes).**  `--help` and a bad argument need no encoding file, on the three
  examples and on `python -m poisson_tasks.calibration_run verify`.  The check runs each from a copy
  of the package that has no `*.tiktoken` (`tests/fd5_support.package_copy`): the help is the
  help the full package gives, byte for byte, and a bad argument is the same one `error:` line and
  exit code.  The control is the same copy running a command that does need the file, which fails
  naming it.
- **FD6.6.**  The examples use generator version `"0"`, as ruled (the published cards were measured
  at `"0"`), and none keeps `"tg-m3-v1"`; the task `one_task.py` prints is the task the library
  makes at `"0"`.
- **FD6.8 (P9).**  `calibration_run --help` describes the driver without "Model B"; every option of
  every step has help text; each option is shown only on the steps that read it.  The notebook
  hands one set of folder options to nearly every step and its cells are frozen, so a step still
  accepts an option it does not read, and does not list it.

**What each step reads** is the table `READS` below, from the driver's source: `serve` starts the
server (its folder for the process id and log, the port, the vLLM executable, the tokenizer
config, the timeout); `stop-server` stops the process the folder names; `preflight`, `phase1`,
`probe` and `phase3` read both folders and the port, and the last three restore and mirror
(`--mirror-interval`); `status` reads the durable folder; `bundle` zips the durable folder
(`--design` picks what goes in); `rerun-void` is the knob probe's step and reads no port;
`finalize` and `verify` read their own arguments.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fd5_support import package_copy
from tests.fd6_support import child_env

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = REPO / "examples"
NOTEBOOK = REPO / "notebooks" / "calibration_model_b.ipynb"
DRIVER = [sys.executable, "-m", "poisson_tasks.calibration_run"]


@pytest.fixture(scope="module")
def bare(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of the package with no tokenizer file, to put first on the path."""
    return package_copy(tmp_path_factory.mktemp("fd6-bare"))


def run(command: list[str], *args: str, root: Path | None, cwd: Path,
        home: Path) -> subprocess.CompletedProcess[str]:
    home.mkdir(parents=True, exist_ok=True)
    return subprocess.run([*command, *args], cwd=cwd, env=child_env(home, root=root),
                          capture_output=True, text=True, timeout=300, check=False)


def not_a_zip(folder: Path) -> str:
    path = folder / "card.zip"
    path.write_text("not an archive\n", encoding="utf-8")
    return str(path)


def no_manifest(folder: Path) -> str:
    path = folder / "unzipped"
    path.mkdir()
    (path / "card.md").write_bytes(b"a card\n")
    return str(path)


EXAMPLE = {
    "one_task": [sys.executable, str(EXAMPLES / "one_task.py")],
    "a_contrast": [sys.executable, str(EXAMPLES / "a_contrast.py")],
    "calibration_card": [sys.executable, str(EXAMPLES / "calibration_card.py")],
    "verify": [*DRIVER, "verify"],
}

# case id: (which command, its arguments or a function of a scratch folder, the exit code)
CASES = {
    "one_task-help": ("one_task", ["--help"], 0),
    "one_task-seed-not-a-number": ("one_task", ["seven"], 2),
    "one_task-seed-out-of-range": ("one_task", ["4294967296"], 2),
    "a_contrast-help": ("a_contrast", ["--help"], 0),
    "a_contrast-takes-no-argument": ("a_contrast", ["--bogus"], 2),
    "calibration_card-help": ("calibration_card", ["--help"], 0),
    "calibration_card-not-a-card-folder": ("calibration_card", ["calibration/nope"], 1),
    "calibration_card-page-and-a-folder": ("calibration_card", ["--page", "calibration/nope"], 2),
    "verify-help": ("verify", ["--help"], 0),
    "verify-no-such-bundle": ("verify", ["nope.zip"], 1),
    "verify-not-a-zip": ("verify", [not_a_zip], 1),
    "verify-no-manifest": ("verify", [no_manifest], 1),
}


def arguments(spec: list[object], scratch: Path) -> list[str]:
    return [item if isinstance(item, str) else item(scratch) for item in spec]  # type: ignore[operator]


@pytest.mark.parametrize("case", CASES)
def test_fd0_item_2_help_and_a_bad_argument_need_no_encoding_file(
    case: str, bare: Path, tmp_path: Path
) -> None:
    which, spec, code = CASES[case]
    args = arguments(spec, tmp_path)
    cwd = tmp_path if which == "verify" else REPO
    without = run(EXAMPLE[which], *args, root=bare, cwd=cwd, home=tmp_path / "home-without")
    full = run(EXAMPLE[which], *args, root=None, cwd=cwd, home=tmp_path / "home-full")
    assert without.returncode == code, without.stderr[-2000:]
    assert "encoding file" not in without.stderr and "Traceback" not in without.stderr
    assert (without.stdout, without.stderr, without.returncode) == (
        full.stdout, full.stderr, full.returncode)
    if code == 0:
        assert without.stdout.strip() and without.stderr == ""
    else:
        lines = [line for line in without.stderr.splitlines() if line.strip()]
        assert without.stdout == "" and len(lines) == 1, without.stderr
        assert lines[0].startswith("error: ") or ": error: " in lines[0], lines[0]


@pytest.mark.parametrize("which", ["one_task", "a_contrast"])
def test_the_copy_without_the_file_really_does_without_it(which: str, bare: Path, tmp_path: Path) -> None:
    """The control: the same copy, running a command that needs the file, fails and names it."""
    done = run(EXAMPLE[which], root=bare, cwd=REPO, home=tmp_path / "home")
    assert done.returncode != 0 and "encoding file" in done.stderr, done.stderr[-1500:]


# ---------------------------------------------------------------------------
# FD6.6 the examples at generator version "0"
# ---------------------------------------------------------------------------


EXAMPLE_FILES = [EXAMPLES / "one_task.py", EXAMPLES / "a_contrast.py",
                 EXAMPLES / "proofload_sweep" / "run.py"]


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_fd6_6_an_example_names_generator_version_0_and_not_the_old_label(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert "tg-m3-v1" not in text
    assert re.search(r'"0"', text), "the example does not name its generator version"


def test_fd6_6_the_task_the_example_prints_is_the_task_the_library_makes_at_0() -> None:
    from poisson_tasks.knobs import ArmSpec
    from poisson_tasks.tasks import generate

    bundle = generate(ArmSpec("depth", 3, None, "strict", "eval", "0"), 7)
    done = subprocess.run([sys.executable, str(EXAMPLES / "one_task.py"), "7"], cwd=REPO,
                          capture_output=True, text=True, timeout=300, check=False)
    assert done.returncode == 0, done.stderr[-1500:]
    line = next(line for line in done.stdout.splitlines() if line.startswith("task_id"))
    assert line.split()[1] == bundle.task_id


# ---------------------------------------------------------------------------
# FD6.8 the driver's help
# ---------------------------------------------------------------------------


READS = {
    "install-vllm": {"--venv", "--dry-run"},
    "serve": {"--local", "--port", "--vllm", "--tokenizer-config", "--timeout"},
    "stop-server": {"--local"},
    "preflight": {"--local", "--durable", "--port", "--design"},
    "phase1": {"--local", "--durable", "--port", "--mirror-interval", "--design"},
    "probe": {"--local", "--durable", "--port", "--mirror-interval", "--design"},
    "phase3": {"--local", "--durable", "--port", "--mirror-interval", "--design",
               "--wall-clock-hours"},
    "status": {"--durable"},
    "rerun-void": {"--local", "--durable", "--mirror-interval", "--design", "--arm", "--cause"},
    "bundle": {"--durable", "--design"},
    "finalize": {"--durable", "--out", "--port"},
    "verify": {"--into"},
}


def driver_parser() -> argparse.ArgumentParser:
    import importlib

    return importlib.import_module("poisson_tasks.calibration_run").build_parser()


def steps(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    (action,) = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    return dict(action.choices)


def test_fd6_8_the_top_help_describes_the_driver_and_never_says_model_b() -> None:
    parser = driver_parser()
    assert parser.description and "model b" not in parser.description.lower()
    assert len(parser.description.split()) >= 12
    for name, step in steps(parser).items():
        assert "model b" not in step.format_help().lower(), name
    done = subprocess.run([*DRIVER, "--help"], capture_output=True, text=True, timeout=120,
                          check=False)
    assert done.returncode == 0 and "model b" not in done.stdout.lower()


def test_fd6_8_every_step_is_one_the_table_names() -> None:
    assert set(steps(driver_parser())) == set(READS)


@pytest.mark.parametrize("step", READS)
def test_fd6_8_a_step_lists_the_options_it_reads_and_each_has_help_text(step: str) -> None:
    parser = steps(driver_parser())[step]
    shown = [a for a in parser._actions if a.help != argparse.SUPPRESS
             and not isinstance(a, argparse._HelpAction)]
    options = {s for a in shown for s in a.option_strings}
    assert options == READS[step], (step, options ^ READS[step])
    assert [a.dest for a in shown if not (a.help or "").strip()] == []
    text = parser.format_help()
    for option in READS[step]:
        assert option in text


@pytest.mark.parametrize("step", [s for s in READS if s not in ("install-vllm", "verify", "finalize")])
def test_fd6_8_a_step_still_accepts_the_options_the_notebook_hands_every_step(step: str) -> None:
    """The notebook's cells are frozen: its `step()` adds `--local --durable --mirror-interval
    --design` to every step but `install-vllm` and `verify`.  A step that does not read one takes
    it and says nothing of it."""
    extra = {"phase3": ["--wall-clock-hours", "1"], "rerun-void": ["--arm", "a", "--cause", "c"]}
    parser = driver_parser()
    args = parser.parse_args([step, "--local", "l", "--durable", "d", "--mirror-interval", "5",
                              "--design", "card", *extra.get(step, [])])
    assert str(args.local) == "l" and str(args.durable) == "d" and args.design == "card"


def test_fd6_8_the_notebook_hands_those_options_to_those_steps() -> None:
    """The control for the test above: the notebook's own text."""
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    text = "\n".join("".join(cell["source"]) for cell in notebook["cells"])
    assert 'COMMON = ["--local", LOCAL_DIR, "--durable", DRIVE_DIR,' in text
    assert '"--mirror-interval", str(MIRROR_INTERVAL), "--design", DESIGN]' in text
    assert 'NO_FOLDERS = {"install-vllm", "verify"}' in text


def test_fd6_8_a_step_that_reads_one_folder_needs_only_that_one(tmp_path: Path) -> None:
    """`status` reads the durable folder and `stop-server` the local one; neither asks for the
    other (the unread option is no longer required)."""
    status = subprocess.run([*DRIVER, "status", "--durable", str(tmp_path)], capture_output=True,
                            text=True, timeout=300, check=False)
    assert status.returncode == 0, status.stderr[-1500:]
    stop = subprocess.run([*DRIVER, "stop-server", "--local", str(tmp_path)], capture_output=True,
                          text=True, timeout=300, check=False)
    assert stop.returncode == 0 and "no server was started from here" in stop.stdout
