"""Phase 1 runs under Colab's environment, and a phase 1 that fails says what failed.

On Colab, after serve and preflight passed, phase 1 ran 6 episodes in 22 s and every one
carried `api_error`: none reached the model (vLLM logged no request after preflight's).  The
error, read from `traces.jsonl` by hand, was the harness's own setup failing:

    HarnessError: harness setup: RuntimeError: failed to prepare uv script: error: the
    argument '--script <SCRIPT>' cannot be used with '--system'

The `null` harness prepares its program with `uv sync --script` and `uv python find --script`,
and Colab's runtime sets `UV_SYSTEM_PYTHON`, which uv reads as `--system`.  uv 0.11.14 refuses
the pair (reproduced on a laptop with the variable set, and gone without it).  So the driver
drops that variable from its own environment before anything runs.  It decides only which
Python runs the harness's helper script, and nothing about the model, the server or the
decoding.

The phase 1 report printed the gate's reasons ("6 of 6 episodes carry an instrument label")
and not the error.  It now prints the first episode's error as well.

The rig is the `rig` fixture in `tests/conftest.py`, the one `tests/test_cal_qwen_prep.py` uses:
a fake vLLM and a fake `nvidia-smi` on PATH, and the driver run as a subprocess.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.helpers import needs_uv, run_module

COLAB_ERROR = (
    "harness setup: RuntimeError: failed to prepare uv script: error: the argument "
    "'--script <SCRIPT>' cannot be used with '--system'"
)


# ---------------------------------------------------------------------------
# reading an episode's error out of traces.jsonl
# ---------------------------------------------------------------------------


def _traces(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    run_dir = tmp_path / "depth-d3"
    run_dir.mkdir()
    (run_dir / "traces.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return run_dir


def test_the_first_episode_error_is_read_from_the_traces(tmp_path: Path) -> None:
    run_dir = _traces(tmp_path, [
        {"id": "a", "errors": []},
        {"id": "b", "errors": [{"type": "HarnessError", "message": COLAB_ERROR}]},
        {"id": "c", "errors": [{"type": "OtherError", "message": "a later one"}]},
    ])
    found = run_module().first_episode_error(run_dir)
    assert found is not None
    assert "HarnessError" in found and COLAB_ERROR in found
    assert "a later one" not in found


def test_traces_without_errors_have_no_first_error(tmp_path: Path) -> None:
    run_dir = _traces(tmp_path, [{"id": "a", "errors": []}, {"id": "b"}])
    assert run_module().first_episode_error(run_dir) is None
    assert run_module().first_episode_error(tmp_path / "missing") is None


# ---------------------------------------------------------------------------
# phase 1, end to end, on the rig
# ---------------------------------------------------------------------------


@needs_uv
def test_phase1_passes_with_colabs_uv_system_python_set(rig: Any) -> None:
    r = rig()
    r.env["UV_SYSTEM_PYTHON"] = "true"
    r.serve()
    r.run("preflight")
    done = r.run("phase1", check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert json.loads((r.durable / "phase1.json").read_text())["passed"] is True
    r.stop_server()


@needs_uv
def test_a_failed_phase1_prints_the_episodes_own_error(rig: Any) -> None:
    """`UV_PYTHON` naming an interpreter that does not exist: every episode's harness setup
    fails, as on Colab, and the printout carries the failure's own words, not only the gate's
    count.  (A `uv` planted on PATH would not do: the harness puts `$HOME/.local/bin` first and
    installs its own there.)"""
    r = rig()
    r.env["UV_PYTHON"] = "/nonexistent/planted-python"
    r.serve()
    r.run("preflight")
    done = r.run("phase1", check=False)
    assert done.returncode == 2, done.stdout + done.stderr
    assert "planted-python" in done.stdout, done.stdout
    report = json.loads((r.durable / "phase1.json").read_text())
    assert "planted-python" in (report["first_error"] or "")
    r.stop_server()
