"""Pending a decision: `init` on own tools when no recipe applies.

**Why it is open.**  The design offers the recipes that apply to the set and nothing else.  With
nothing shipped (today) a set with no flows has no recipe at all (`first-look` is depth's and needs
flows).

**Recommended.**  `init` refuses in one line naming what is missing (a flow for depth; the probe for
the rest), writes nothing and exits 1.  If it is declined, the build offers the knob menu (`custom`)
there instead.
"""

from __future__ import annotations

import importlib
import io
import sys
from pathlib import Path

import pytest

from poisson_tasks import arms
from tests.o1_support import fixture
from tests.o2_support import acme, recipes


def test_init_on_own_tools_with_no_recipe_refuses_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arms, "SHIPPED_KNOBS", ())
    assert recipes().default_recipe(acme()) is None
    monkeypatch.chdir(tmp_path)
    (tmp_path / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", err)
    code = importlib.import_module("poisson_tasks.cli").main(
        ["init", "--yes", "--no-fetch", "--no-check-key", "--own-file", "tools.json"], prog="poisson-tasks")
    assert code == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tools.json"]
    assert len([line for line in err.getvalue().splitlines() if line.startswith("error:")]) == 1
