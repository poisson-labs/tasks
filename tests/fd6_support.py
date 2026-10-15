"""Shared ground for FD6's tests: the wheel built from this checkout, unpacked, and a child
interpreter that imports the package from it and not from the checkout.

**The wheel is built, never described.**  `hatchling` builds it from the working tree, once per
test session, into a folder of the session's own.  What the tests read is the zip's own file list
and the metadata inside it.  `unpacked` is that wheel extracted as `site-packages` would hold it:
no checkout beside it, no `calibration/` folder, and no tokenizer file (the wheel never ships
one).  `with_tokenizer` is a second extraction with this checkout's tokenizer file put where
`python -m poisson_tasks.fetch_encoding` would leave it, for the commands that need the file.

**A child runs from the wheel.**  `python -P`, the unpacked folder first on `PYTHONPATH`, the
network refused by proxies at a dead loopback port and uv offline, a temporary `HOME` and
working folder.  The dependencies are the test environment's own; what is under test is the
package's files.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CARDS_SOURCE = REPO / "calibration"
"""Where the checkout keeps the published cards; the wheel carries them as `poisson_tasks/cards/`."""

DEAD_PROXY = "http://127.0.0.1:1"


def build_wheel(into: Path) -> Path:
    """The wheel `hatchling` builds from this working tree, in `into`."""
    into.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(
        [sys.executable, "-c",
         "import sys; from hatchling.build import build_wheel; print(build_wheel(sys.argv[1]))",
         str(into)],
        cwd=REPO, capture_output=True, text=True, timeout=600, check=False,
    )
    assert done.returncode == 0, done.stderr[-3000:]
    wheel = into / done.stdout.strip().splitlines()[-1]
    assert wheel.is_file(), done.stdout
    return wheel


def extract(wheel: Path, into: Path) -> Path:
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(into)
    return into


def tokenizer_file() -> Path:
    """This checkout's tokenizer file, which the suite needs in place."""
    path = Path(importlib.import_module("poisson_tasks.fetch_encoding").ENCODING_PATH)
    assert path.is_file(), "the suite needs the tokenizer file in this checkout"
    return path


@pytest.fixture(scope="session")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return build_wheel(tmp_path_factory.mktemp("fd6-wheel"))


@pytest.fixture(scope="session")
def wheel_names(built_wheel: Path) -> list[str]:
    with zipfile.ZipFile(built_wheel) as archive:
        return archive.namelist()


@pytest.fixture(scope="session")
def unpacked(built_wheel: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The wheel as installed, with no tokenizer file."""
    return extract(built_wheel, tmp_path_factory.mktemp("fd6-unpacked"))


@pytest.fixture(scope="session")
def with_tokenizer(built_wheel: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The wheel as installed, with the tokenizer file fetched into it."""
    root = extract(built_wheel, tmp_path_factory.mktemp("fd6-unpacked-tokenizer"))
    data = root / "poisson_tasks" / "data"
    data.mkdir(exist_ok=True)
    shutil.copy2(tokenizer_file(), data / tokenizer_file().name)
    return root


def child_env(home: Path, extra: Mapping[str, str] | None = None, *, root: Path | None = None
              ) -> dict[str, str]:
    """A child's environment: this one's, less the shell's provider variables and the checkout's
    path, with proxies at a dead port, uv offline and a home and temporary folder of its own."""
    env = {name: value for name, value in os.environ.items()
           if name != "PYTHONPATH" and not any(word in name.upper()
                                               for word in ("API_KEY", "TOKEN", "SECRET"))
           and name not in ("OPENAI_BASE_URL", "CI", "NO_COLOR", "FORCE_COLOR")}
    env.update({
        "HOME": str(home), "TMPDIR": str(home), "NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "100",
        "HTTP_PROXY": DEAD_PROXY, "HTTPS_PROXY": DEAD_PROXY, "ALL_PROXY": DEAD_PROXY,
        "http_proxy": DEAD_PROXY, "https_proxy": DEAD_PROXY, "all_proxy": DEAD_PROXY,
        "NO_PROXY": "127.0.0.1,localhost", "UV_OFFLINE": "1", "UV_NO_MODIFY_PATH": "1",
        "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
    })
    if root is not None:
        env["PYTHONPATH"] = str(root)
    env.update(extra or {})
    return env


def run_from(root: Path | None, argv: Sequence[str], *, work: Path, extra: Mapping[str, str] | None = None,
             stdin: bytes = b"", timeout: float = 600) -> subprocess.CompletedProcess[str]:
    """`python -P -m poisson_tasks ARGV` with `root` first on the path, in `work`, with a home
    of its own beside it."""
    home = work / "home"
    home.mkdir(parents=True, exist_ok=True)
    folder = work / "here"
    folder.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, "-P", "-m", "poisson_tasks", *argv], cwd=folder,
        env=child_env(home, extra, root=root), input=stdin.decode("utf-8"),
        capture_output=True, text=True, timeout=timeout, check=False,
    )


def python_from(root: Path | None, code: str, *args: str, work: Path,
                extra: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """`python -P -c CODE ARGS` with `root` first on the path, in `work`."""
    home = work / "home"
    home.mkdir(parents=True, exist_ok=True)
    folder = work / "here"
    folder.mkdir(exist_ok=True)
    return subprocess.run(
        [sys.executable, "-P", "-c", code, *args], cwd=folder,
        env=child_env(home, extra, root=root), capture_output=True, text=True, timeout=600,
        check=False,
    )
