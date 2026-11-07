"""#34, the uv half: a run does not fetch uv's installer when a uv that can run the harness is
already there.

**The cause.**  Before the first episode of every process, verifiers 0.3.1's bootstrap
(`verifiers.v1.runtimes.base._ENSURE_UV`) ensures the *latest* uv: `pip install -q -U --user uv`,
and when pip cannot, a download of astral's installer through `curl | sh`.  `run` sets
`PIP_REQUIRE_VIRTUALENV=1` on purpose (decided 2026-10-02, `tests/test_fd3_machine.py`), so pip
always refuses and the installer always runs: one fetch from astral.sh for every run, with a uv
already installed, which the installer then replaces with the newest one.

**The change.**  For the length of a run, the bootstrap is the same text with a guard in front of
it: when the first `uv` on the harness's `PATH` (`~/.local/bin` first, as the bootstrap puts it)
can do the two things the harness asks of it, `uv sync --script` and `uv python find --script`,
the bootstrap does nothing; otherwise it is what it was.  The guard asks uv, not a version
number: it looks for `--script` in the `--help` of the two commands.  Measured on 2026-11-07 with
the release wheels, offline, on a script with no dependencies: `uv sync --script` is in 0.6.0 and
`uv python find --script` in 0.6.10 (0.6.9 and earlier refuse it with `unexpected argument`), so
the floor is **0.6.10**, which the plan's `harness` line, the README and the docs say.

What each test holds:

- the guard, run with `sh` against a fake `uv`, `pip` and `curl` in a home of its own: a uv that
  can do both commands, on the `PATH` or in `~/.local/bin`, fetches nothing and runs no pip; a uv
  that cannot do the second (0.6.0 to 0.6.9), one that can do neither, and no uv at all, each
  take the bootstrap as it was (pip, then one fetch of the installer); the first uv on the
  `PATH` is the one asked, because it is the one the next command uses; the bootstrap is whole
  inside the guard;
- the wiring: during a run `base._ENSURE_UV` is the guarded text and afterwards it is put back,
  also when the run raises; a text that is not the one this package was written against is left
  alone, and the installed verifiers' text still is that one (a guard on the pin);
- two runs of one episode in a process of their own (the fixture model, a fake `curl`, a `pip`
  that refuses as the real one does under the setting): with a uv that can do the commands there
  is no fetch and no pip; with one that cannot, the bootstrap runs as before;
- the words: the plan's `harness` line, and the README, say a uv of 0.6.10 or later on the
  `PATH` is used.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import (
    child_env,
    child_result,
    make_plan,
    marked_processes,
    needs_uv,
    new_mark,
    plan_spec,
    reaped,
    start_child,
    stub_bin,
    wait_until,
)
from tests.fd3_support import runs as runs_module
from tests.fixtures.model_server import FixtureModel

REPO = Path(__file__).resolve().parents[1]
HEAD = 'export PATH="$HOME/.local/bin:$PATH" UV_INSTALL_DIR="$HOME/.local/bin"; '
INSTALLER = "https://astral.sh/uv/install.sh"
FLOOR = "0.6.10"

FAKE_CURL = """#!/bin/sh
echo "curl $*" >> "$FX_LOG"
echo 'echo "the installer ran" >> "$FX_LOG"'
"""
REFUSING_PIP = """#!/bin/sh
echo "pip $*" >> "$FX_LOG"
exit 1
"""
"""What `pip` does under `PIP_REQUIRE_VIRTUALENV=1`: it refuses."""


def fake_uv(*, sync: bool, find: bool) -> str:
    """A `uv` that says, in the `--help` of the two commands the harness runs, whether it takes
    `--script`: `uv sync` did from 0.6.0 and `uv python find` did from 0.6.10."""
    has = '  --script <SCRIPT>  the script'
    lacks = '  --python <PYTHON>  the interpreter'
    return (
        "#!/bin/sh\n"
        'case "$1 $2 $3" in\n'
        f'  "sync --help"*) echo "{has if sync else lacks}" ;;\n'
        f'  "python find --help"*) echo "{has if find else lacks}" ;;\n'
        '  "--version"*) echo "uv 0.0.0" ;;\n'
        "esac\n"
        "exit 0\n"
    )


def write_script(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
    return path


def bootstrap_text() -> str:
    """The text a run hands the harness's shell: verifiers' bootstrap, guarded."""
    from verifiers.v1.runtimes import base

    return str(runs_module().guard_uv_bootstrap(base._ENSURE_UV))


def run_bootstrap(
    tmp_path: Path, *, on_path: str | None = None, in_home: str | None = None,
    after: str | None = None,
) -> tuple[int, list[str]]:
    """Run the guarded bootstrap with `sh` in a home of its own.  The folders on `PATH`, in
    order: the fakes (`curl`, `pip`, and `on_path` as `uv`), then `after` as `uv` in a folder
    behind it, then the system's.  Returns the exit code and the lines the fakes wrote."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    fakes = tmp_path / "fakes"
    write_script(fakes / "curl", FAKE_CURL)
    write_script(fakes / "pip", REFUSING_PIP)
    if on_path is not None:
        write_script(fakes / "uv", on_path)
    if in_home is not None:
        write_script(home / ".local" / "bin" / "uv", in_home)
    behind = tmp_path / "behind"
    behind.mkdir()
    if after is not None:
        write_script(behind / "uv", after)
    log = tmp_path / "log.txt"
    log.write_text("", encoding="utf-8")
    env = {"HOME": str(home), "PATH": f"{fakes}{os.pathsep}{behind}{os.pathsep}/usr/bin:/bin",
           "FX_LOG": str(log)}
    done = subprocess.run(["sh", "-c", bootstrap_text()], env=env, capture_output=True,
                          text=True, check=False)
    return done.returncode, log.read_text(encoding="utf-8").splitlines()


def fetches(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("curl") and INSTALLER in line]


NEW = fake_uv(sync=True, find=True)
SYNC_ONLY = fake_uv(sync=True, find=False)
OLD = fake_uv(sync=False, find=False)


# ---------------------------------------------------------------------------
# the guard
# ---------------------------------------------------------------------------


def test_fx34_20_a_uv_that_can_run_the_harness_is_used_and_nothing_is_fetched(
    tmp_path: Path,
) -> None:
    """Red before the change: there is no guard (`runs.guard_uv_bootstrap`), and the bootstrap
    asks pip, which refuses, and then fetches the installer."""
    code, lines = run_bootstrap(tmp_path, on_path=NEW)
    assert code == 0 and lines == [], lines


def test_fx34_21_a_uv_in_home_local_bin_is_found_where_the_bootstrap_puts_it(
    tmp_path: Path,
) -> None:
    code, lines = run_bootstrap(tmp_path, in_home=NEW)
    assert code == 0 and lines == [], lines


@pytest.mark.parametrize(("name", "uv"), [("0.6.0 to 0.6.9, which cannot find a script's python",
                                           SYNC_ONLY),
                                          ("0.5 and earlier, which take no --script", OLD)])
def test_fx34_22_a_uv_that_cannot_run_the_harness_takes_the_bootstrap_as_it_was(
    name: str, uv: str, tmp_path: Path
) -> None:
    """The floor: with a uv below it, pip is asked first (and refuses) and the installer is
    fetched once, as before.  The case of 0.6.0 to 0.6.9 is the one a check on `uv sync` alone
    would let through, to fail later at `uv python find --script`."""
    code, lines = run_bootstrap(tmp_path, on_path=uv)
    assert code == 0, name
    assert [line.split()[0] for line in lines if line.startswith("pip")] == ["pip"], lines
    assert len(fetches(lines)) == 1 and "the installer ran" in lines, lines


def test_fx34_23_with_no_uv_at_all_the_bootstrap_is_as_it_was(tmp_path: Path) -> None:
    """The no-uv case stays what it was: pip is asked and refuses, and the installer is fetched
    once.  (Red before the change only because the guard is not there to call.)"""
    code, lines = run_bootstrap(tmp_path)
    assert code == 0, lines
    assert len(fetches(lines)) == 1 and "the installer ran" in lines, lines


def test_fx34_24_the_first_uv_on_the_path_is_the_one_asked(tmp_path: Path) -> None:
    """`~/.local/bin` comes first, so an old uv there is the one the next command would run, and
    a new one behind it does not save the run: the bootstrap is taken."""
    code, lines = run_bootstrap(tmp_path, in_home=OLD, after=NEW)
    assert code == 0 and len(fetches(lines)) == 1, lines
    code, lines = run_bootstrap(tmp_path / "other", in_home=NEW, after=OLD)
    assert code == 0 and lines == [], lines


def test_fx34_25_the_whole_of_verifiers_bootstrap_is_inside_the_guard() -> None:
    """Nothing of verifiers' text is dropped or reworded: the guard is added in front of what
    follows its two exports, and what follows them is kept whole."""
    from verifiers.v1.runtimes import base

    guarded = bootstrap_text()
    original = str(base._ENSURE_UV)
    assert original.startswith(HEAD)
    assert guarded.startswith(HEAD)
    assert original[len(HEAD):] in guarded
    assert guarded.count("--script") == 2 and "uv sync --help" in guarded
    assert "uv python find --help" in guarded


@needs_uv
def test_fx34_26_the_uv_on_this_machine_passes_the_guard_when_it_is_at_the_floor_or_later(
    tmp_path: Path,
) -> None:
    """The floor in words, 0.6.10, against a real uv: if this machine's is at or above it, the
    guard lets it through (nothing is fetched).  A guard on the number in the docs and the
    plan's line: a uv of the floor's version that the guard refuses would fail here."""
    found = shutil.which("uv")
    assert found is not None
    said = subprocess.run([found, "--version"], capture_output=True, text=True, check=False)
    seen = re.match(r"uv (\d+)\.(\d+)\.(\d+)", said.stdout)
    assert seen is not None, said.stdout
    version = tuple(int(part) for part in seen.groups())
    if version < tuple(int(part) for part in FLOOR.split(".")):
        pytest.skip(f"this machine's uv is {said.stdout.strip()}, below the floor")
    real = tmp_path / "real"
    write_script(real / "uv", f'#!/bin/sh\nexec "{found}" "$@"\n')
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    fakes = tmp_path / "fakes"
    write_script(fakes / "curl", FAKE_CURL)
    write_script(fakes / "pip", REFUSING_PIP)
    log = tmp_path / "log.txt"
    log.write_text("", encoding="utf-8")
    env = {"HOME": str(home), "PATH": f"{real}{os.pathsep}{fakes}{os.pathsep}/usr/bin:/bin",
           "FX_LOG": str(log)}
    done = subprocess.run(["sh", "-c", bootstrap_text()], env=env, capture_output=True,
                          text=True, check=False)
    assert done.returncode == 0 and log.read_text(encoding="utf-8") == "", done


# ---------------------------------------------------------------------------
# the wiring around verifiers' bootstrap
# ---------------------------------------------------------------------------


def test_fx34_27_during_a_run_the_bootstrap_is_guarded_and_afterwards_it_is_put_back() -> None:
    """Red before the change: `_harness_environment` leaves the bootstrap alone."""
    from verifiers.v1.runtimes import base

    original = base._ENSURE_UV
    with runs_module()._harness_environment():
        inside = base._ENSURE_UV
        assert inside == runs_module().guard_uv_bootstrap(original) != original
    assert base._ENSURE_UV == original


def test_fx34_28_the_bootstrap_is_put_back_when_the_run_raises() -> None:
    from verifiers.v1.runtimes import base

    original = base._ENSURE_UV
    with pytest.raises(RuntimeError, match="the run broke"):
        with runs_module()._harness_environment():
            assert base._ENSURE_UV != original
            raise RuntimeError("the run broke")
    assert base._ENSURE_UV == original


def test_fx34_29_a_bootstrap_this_package_was_not_written_against_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a verifiers other than 0.3.1 words its bootstrap otherwise, the run does what
    verifiers does rather than guess where a guard goes (and test 30 fails, to say so)."""
    from verifiers.v1.runtimes import base

    monkeypatch.setattr(base, "_ENSURE_UV", "echo a bootstrap of some other shape")
    with runs_module()._harness_environment():
        assert base._ENSURE_UV == "echo a bootstrap of some other shape"
    assert base._ENSURE_UV == "echo a bootstrap of some other shape"


def test_fx34_30_the_installed_verifiers_has_the_bootstrap_the_guard_was_written_against() -> None:
    """A guard, green by construction: the pin is `verifiers==0.3.1`, whose bootstrap begins with
    the two exports and asks pip, then astral's installer.  If the pin moves to a verifiers that
    words it differently, this fails, and the guard is read again (test 29 shows what a run does
    meanwhile)."""
    from verifiers.v1.runtimes import base

    text = str(base._ENSURE_UV)
    assert text.startswith(HEAD)
    assert "pip install -q -U --user uv" in text and INSTALLER in text
    assert "uv sync --script" in Path(base.__file__).read_text(encoding="utf-8")
    assert "uv python find --script" in Path(base.__file__).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# two runs of one episode, in a process of their own
# ---------------------------------------------------------------------------


def one_episode(base: Path, model: FixtureModel, *, old: bool) -> dict[str, Any]:
    """One episode in a process of its own, with a fake `curl` and a refusing `pip` first on its
    `PATH`, and the old-uv `uv` ahead of them when `old`.  The lines the fakes wrote, and the
    child's result."""
    home, cwd = base / "home", base / "cwd"
    for folder in (home, cwd):
        folder.mkdir(parents=True)
    stubs = stub_bin(base / "bin", pip=REFUSING_PIP, old_uv=old)
    write_script(stubs / "curl", FAKE_CURL)
    log = base / "fakes.txt"
    log.write_text("", encoding="utf-8")
    mark = new_mark()
    env = child_env(home=home, stubs=stubs, mark=mark,
                    extra={"FX_LOG": str(log), "PYTHONDONTWRITEBYTECODE": "1"})
    job = {"plan": plan_spec(make_plan(model.base_url, seeds=(404,))),
           "runs_dir": str(cwd / "runs"), "caps": {"spend_usd": 1.0, "tokens": None},
           "concurrency": 1}
    process, result_path = start_child(job, env=env, cwd=cwd, work=base / "child")
    with reaped(process, mark):
        process.wait(300)
        wait_until(lambda: not marked_processes(mark), 10.0, 0.2)
    return {"result": child_result(result_path), "lines": log.read_text(
        encoding="utf-8").splitlines(), "stderr": (base / "child" / "stderr.txt").read_text(
        encoding="utf-8", errors="replace")[-2000:]}


@pytest.fixture(scope="module")
def episodes(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, dict[str, Any]]]:
    model = FixtureModel()
    model.start()
    try:
        yield {
            "uv": one_episode(tmp_path_factory.mktemp("uv-there"), model, old=False),
            "old": one_episode(tmp_path_factory.mktemp("uv-old"), model, old=True),
        }
    finally:
        model.close()


@needs_uv
def test_fx34_31_a_run_with_a_uv_there_fetches_nothing_and_asks_pip_nothing(
    episodes: dict[str, dict[str, Any]]
) -> None:
    """The reproduction, as a test: one episode, a uv on the `PATH`, a fake `curl` that records
    what it is asked for.  Red before the change: the installer is fetched, once for the run."""
    made = episodes["uv"]
    assert made["result"]["verdict"] == "done", made["stderr"]
    assert made["lines"] == [], made["lines"]


@needs_uv
def test_fx34_32_a_run_with_a_uv_too_old_for_the_harness_takes_the_bootstrap_as_before(
    episodes: dict[str, dict[str, Any]]
) -> None:
    made = episodes["old"]
    assert made["result"]["verdict"] == "done", made["stderr"]
    assert len(fetches(made["lines"])) == 1, made["lines"]
    assert any(line.startswith("pip install") for line in made["lines"]), made["lines"]


# ---------------------------------------------------------------------------
# the words
# ---------------------------------------------------------------------------


def test_fx34_33_the_harness_line_says_a_uv_of_the_floor_or_later_is_used() -> None:
    """Red before the change: the line says the first episode runs uv's installer, always."""
    from poisson_tasks.cli._common import HARNESS_LINE

    assert HARNESS_LINE == (
        "the first episode sets up uv with astral.sh's installer unless uv 0.6.10 or later is "
        "already on your PATH, and fetches four packages and their dependencies from PyPI"
    )


def test_fx34_34_the_readme_says_what_the_run_does_to_uv() -> None:
    """Red before the change: the README says the installer runs *on every run*, replacing the
    uv already there when a newer one exists."""
    text = " ".join((REPO / "README.md").read_text(encoding="utf-8").split())
    assert "replacing the uv already there" not in text
    assert "uv 0.6.10 or later" in text and "already on your `PATH`" in text
    assert "the installer is not fetched" in text
