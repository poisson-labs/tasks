"""Test configuration, outside the frozen test files.

`tests/test_tg_m5_scripted.py` drives Proofload's real CLI and `tests/test_tg_m5_bridge.py`
calls the adapter's `to_episode`, and Proofload is an optional extra: `pip install
"poisson-tasks[proofload]"`, and not the plain install.  Without it every test in those two
files is skipped, with the reason below, and the rest of the suite runs.

It is done here and not in the file itself because the test files are frozen: each module
was built against tests written before it, and the suite is not edited to suit an install.
This adds no assertion and changes none; with the extra installed the hook does nothing and
all 548 tests run exactly as they did.

The file collects cleanly either way -- it imports `poisson_tasks.adapter` lazily, through
`importlib`, inside its own helper -- so the skip is applied to collected items rather than
by refusing to collect, and `pytest -q` reports the count and the reason.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

# The test files that need the extra: the scripted path's, which drives Proofload's CLI, and
# the model path's bridge (MP10), which calls `to_episode`. Matched on the name, so a run from
# any directory and any invocation (`pytest`, `pytest tests/`, a single node id) sees the same
# thing.
PROOFLOAD_TEST_FILES = frozenset({"test_tg_m5_scripted.py", "test_tg_m5_bridge.py"})

SKIP_REASON = (
    "Proofload is not installed: these tests drive its real CLI. "
    "It is the optional `proofload` extra -- `pip install -e '.[proofload]'` -- and it is "
    "not publicly available yet, so the extra resolves only against a checkout already "
    "installed in the same environment."
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
