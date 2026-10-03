"""The notebook's code cell makes its Drive folder when it is not there.

Starting model B's run afresh means moving the previous run's Drive folder aside, and the
code cell then wrote `source.json` into a folder that no longer existed:
`FileNotFoundError: .../calibration-model-b/source.json`.  The cell now creates the folder.

The world is the `code_cell` fixture in `tests/conftest.py`, the one
`tests/test_cal_qwen_install_fix.py` uses.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any

from tests.helpers import needs_git, run_code_cell


@needs_git
def test_the_code_cell_makes_a_missing_drive_folder(code_cell: dict[str, Any]) -> None:
    subprocess.run(["git", "clone", "--quiet", str(code_cell["origin"]), str(code_cell["tasks"])],
                   check=True)
    drive = code_cell["drive"] / "poisson-tasks" / "calibration-model-b"
    shutil.rmtree(code_cell["drive"])
    code_cell["drive"] = drive
    run_code_cell(code_cell)
    assert json.loads((drive / "source.json").read_text())["commit"] == code_cell["head"]
