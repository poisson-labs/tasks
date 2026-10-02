"""A bare `pytest` collects the same tests as `python -m pytest`.

Some tests import others as `tests.<module>`, which needs the repository root on the import path.
`python -m pytest` puts the working directory there and a bare `pytest` does not, so a bare run
used to fail to collect those files. Both are run here from the repository root with
`PYTHONPATH` and `PYTEST_ADDOPTS` cleared, so neither can borrow the root from the environment.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def collected(command: list[str]) -> tuple[int, list[str]]:
    """The exit code of a collect-only run, and the test ids it lists."""
    env = {name: value for name, value in os.environ.items()
           if name not in ("PYTHONPATH", "PYTEST_ADDOPTS")}
    done = subprocess.run(
        [*command, "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=600,
    )
    return done.returncode, sorted(line for line in done.stdout.splitlines() if "::" in line)


def test_a_bare_pytest_collects_what_python_m_pytest_collects() -> None:
    bare = Path(sys.executable).parent / "pytest"
    assert bare.is_file(), f"no pytest script beside {sys.executable}"
    reference = collected([sys.executable, "-m", "pytest"])
    assert reference[0] == 0 and reference[1], reference[0]
    code, ids = collected([str(bare)])
    missing = sorted(set(reference[1]) - set(ids))
    assert (code, ids) == reference, (code, len(missing), missing[:5])
