"""Test configuration, outside the frozen test files.

`tests/test_tg_m5_scripted.py` drives Proofload's real CLI and `tests/test_tg_m5_bridge.py`
calls the adapter's `to_episode`, and Proofload is not a dependency of this package and not
installable from any index.  It comes from a checkout installed into the same environment
(`pip install -e ../proofload`).  Without it every test in those two files is skipped, with
the reason below, and the rest of the suite runs.

It is done here and not in the file itself because the test files are frozen: each module
was built against tests written before it, and the suite is not edited to suit an install.
This adds no assertion and changes none; with the extra installed the hook does nothing and
every test runs exactly as it would without it.

The file collects cleanly either way -- it imports `poisson_tasks.adapter` lazily, through
`importlib`, inside its own helper -- so the skip is applied to collected items rather than
by refusing to collect, and `pytest -q` reports the count and the reason.

**The network.** Generation needs none, but every test that runs an episode through the
`null` harness does. Before each episode's harness starts, the `verifiers` wheel makes sure
of the latest `uv`: it runs `pip install --user uv`, and where that cannot install (inside a
virtualenv it never can) it downloads uv's installer from astral.sh with curl. Then
`uv sync --script` installs the harness program's own dependencies from PyPI. That is the
wheel's behaviour, not this package's, and it happens even when `uv` is already installed.
Without the network those tests fail at the harness's setup, with the wheel's error.

**Hypothesis profiles.** Property tests draw new examples on every run by default, so what
one run catches can differ from the next. `HYPOTHESIS_PROFILE=ci` (which the CI workflow
sets) derandomizes them: every run draws the same examples, so a red test is reproducible.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from hypothesis import settings

settings.register_profile("ci", derandomize=True)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))

# The test files that need the extra: the scripted path's, which drives Proofload's CLI, and
# the model path's bridge, which calls `to_episode`. Matched on the name, so a run from
# any directory and any invocation (`pytest`, `pytest tests/`, a single node id) sees the same
# thing.
PROOFLOAD_TEST_FILES = frozenset({"test_tg_m5_scripted.py", "test_tg_m5_bridge.py"})

SKIP_REASON = (
    "Proofload is not installed: these tests drive its real CLI.  It is not a dependency "
    "of this package and it is not publicly available yet, so there is no extra and no "
    "index to install it from: it comes from a checkout installed into the same "
    "environment -- `pip install -e ../proofload`."
)


def proofload_installed() -> bool:
    """Whether the extra is present. `find_spec` and not an import: importing Proofload
    here would cost every run of the suite the import, and this module is read first."""
    try:
        return importlib.util.find_spec("proofload") is not None
    except (ImportError, ValueError):
        return False


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    if proofload_installed():
        return
    skip = pytest.mark.skip(reason=SKIP_REASON)
    for item in items:
        if Path(str(item.fspath)).name in PROOFLOAD_TEST_FILES:
            item.add_marker(skip)


# ---------------------------------------------------------------------------
# fixtures more than one test file uses
#
# Their helpers are in `tests/helpers.py`, imported inside each fixture so that a run that
# uses neither fixture does not pay for the import.
# ---------------------------------------------------------------------------


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Any]:
    """A factory for `Rig`s: the notebook's filesystem and processes on a laptop, each in a
    folder of its own with the pinned template's tokenizer config.  Teardown stops every
    process each rig started."""
    from tests.helpers import FIXTURE, Rig

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    (tmp_path / "tokenizer_config.json").write_text(
        json.dumps({"chat_template": data["chat_template"]}), encoding="utf-8"
    )
    made: list[Rig] = []

    def factory(mode: str = "reference", delay: float = 0.0) -> Rig:
        sub = tmp_path / f"rig{len(made)}"
        sub.mkdir()
        shutil.copy(tmp_path / "tokenizer_config.json", sub / "tokenizer_config.json")
        made.append(Rig(sub, mode=mode, delay=delay))
        return made[-1]

    yield factory
    for each in made:
        each.close()


@pytest.fixture
def code_cell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The clone cell's world: a stand-in origin with one commit on `main`, a fake
    `google.colab.userdata` holding a token, a Drive folder, and git kept inside tmp."""
    from tests.helpers import GIT

    origin = tmp_path / "origin"
    subprocess.run([*GIT, "init", "--quiet", "-b", "main", str(origin)], check=True)
    (origin / "README").write_text("stand-in\n")
    subprocess.run([*GIT, "-C", str(origin), "add", "README"], check=True)
    subprocess.run([*GIT, "-C", str(origin), "commit", "--quiet", "-m", "stand-in"], check=True)
    head = subprocess.run(["git", "-C", str(origin), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    colab = types.ModuleType("google.colab")
    colab.userdata = types.SimpleNamespace(get=lambda name: "tok-123")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.colab", colab)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    drive = tmp_path / "drive"
    drive.mkdir()
    return {"origin": origin, "head": head, "drive": drive, "tasks": tmp_path / "tasks",
            "tmp": tmp_path}
