"""Pending a decision: how `doctor` knows the tool file changed since the last run.

**Why it is open.**  The design: "`doctor` re-reads the file and reports the same summary; a file
whose digest changed since the last run says so, because its tasks changed".  Which run is "the last
run" is not said: a run's folder is found by its plan's hash, and the plan's hash moves with the
file's digest, so the plan of a changed file has no folder.

**Recommended.**  The last run is the run folder under `[output] runs` most recently written whose
`plan.json` names the same tool file (its `own.name` and the file's name); when its `file_digest` is
not the file's now, `doctor` says so on one line naming both digests' first twelve characters and
that the tasks changed.  With no such folder it says nothing of it.  If it is declined, the build
compares against a digest `tasks.toml` itself keeps, which a user would then see in the file.
"""

from __future__ import annotations

import dataclasses
import importlib
import io
import json
import sys
from pathlib import Path

import pytest

from poisson_tasks import own
from tests.o1_support import fixture
from tests.o2_support import config, runs


def doctor(monkeypatch: pytest.MonkeyPatch) -> str:
    out, err = io.StringIO(), io.StringIO()
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        importlib.import_module("poisson_tasks.cli").main(["doctor", "--offline"], prog="poisson-tasks")
    finally:
        sys.stdout, sys.stderr = saved
    return out.getvalue() + err.getvalue()


def test_doctor_says_the_tool_files_digest_changed_since_the_last_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    data = fixture("acme-mcp-tools-list.json")
    (tmp_path / "tools.json").write_bytes(data)
    flags = ["--provider", "openai", "--no-price", "--token-cap", "1000", "--recipe", "first-look",
             "--tasks-per-level", "1", "--own-file", "tools.json",
             "--own-flow", "get_order.order_id:refund_order.order_id"]
    made = config().config_from_init_args(flags)
    (tmp_path / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")
    plan = config().resolve_plan(made, root=tmp_path)
    folder = runs().find_run(plan, tmp_path / "runs")
    Path(folder.path).mkdir(parents=True)
    held = {"plan": {"preset": plan.preset, "arms": [dataclasses.asdict(a) for a in plan.arms],
                     "seeds": list(plan.seeds), "attempts": plan.attempts,
                     "model": dataclasses.asdict(plan.model), "decoding": dict(plan.decoding),
                     "max_model_calls": plan.max_model_calls, "own": dict(plan.own)},
            "plan_hash": config().plan_hash(plan)}
    (Path(folder.path) / "plan.json").write_text(json.dumps(held), encoding="utf-8")
    old = own.read_tools(data).toolset.file_digest
    assert old[:12] not in [line for line in doctor(monkeypatch).splitlines() if "changed" in line]
    (tmp_path / "tools.json").write_bytes(data + b"\n")
    new = own.read_tools(data + b"\n").toolset.file_digest
    lines = [line for line in doctor(monkeypatch).splitlines() if old[:12] in line and new[:12] in line]
    assert len(lines) == 1
    assert json.loads((Path(folder.path) / "plan.json").read_text())["plan"]["own"]["file_digest"] == old
