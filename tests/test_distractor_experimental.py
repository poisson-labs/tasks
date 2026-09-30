"""The distractor dial is labelled experimental where a user picks an arm.

Both calibrated models show that, as built, the distractor dial does not make tasks harder:
gpt-5-nano stays between 0.90 and 0.96 strict pass@1 from r0 to r14, and Qwen3-8B is at 0.98
or more at every level. So it ships documented as not a difficulty setting for current models.
A user chooses an arm on the `eval` command line (`--env.taskset.arm`), so the label goes
where that option is described: the command's own `--help`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _option_help(text: str, option: str) -> str:
    """The help text of one option, joined across the lines the table wraps it over."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if option in line)
    block = [lines[start]]
    for line in lines[start + 1:]:
        cell = line.strip("│ ").strip()
        if cell.startswith("--") or not cell or line.lstrip().startswith("╰"):
            break
        block.append(line)
    return " ".join(line.strip("│ ").strip() for line in block)


def test_eval_help_labels_the_distractor_dial_experimental(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, "-c",
         "import sys; from verifiers.v1.cli.eval.main import main; main(sys.argv[1:])",
         "poisson-tasks", "--help"],
        cwd=tmp_path, capture_output=True, text=True, timeout=300,
        env={"COLUMNS": "200", "PATH": "/usr/bin:/bin"},
    )
    assert done.returncode == 0, done.stderr[-2000:]
    arm = _option_help(done.stdout, "--env.taskset.arm").lower()
    assert "distractor" in arm and "experimental" in arm, arm
    assert "depth" in arm, arm
