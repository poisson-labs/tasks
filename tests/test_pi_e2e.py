"""The documented Prove route, run end to end from two published packages.

Before 0.3.1 nothing ran Tasks beside the Prove that is on PyPI: the suite's Prove tests used a
checkout, so the import name and three details of the command line could be wrong for a stranger
and green here.  `scripts/release/prove_e2e.py` is the check that cannot be: it takes the wheel
built from this tree, makes a fresh environment, installs the wheel with its `prove` extra so that
`poisson-prove` resolves from PyPI, and runs the route `docs/prove.md` documents -- the example
`examples/prove_sweep/run.py`, three real `poisson-prove sweep` runs on the built-in tasks driven by
the scripted reference policy, and a `diff` -- and then the real `poisson-prove` command on the
same files, reading the stored episodes back.  Then it uninstalls Prove and checks that Tasks
still imports and the adapter is refused with the extra's name.

- **PI5.1** runs it, here, on this tree's wheel.  It needs the network (PyPI), like every test
  that runs an episode through the `null` harness.  Beside the script run, the child is given a
  decoy Prove: a `poisson_prove` package that raises on import, found through `PYTHONPATH`, and a
  `poisson-prove` that exits 99, first on `PATH`.  A script that let either through would fail, so
  a pass is a pass with no local Prove checkout anywhere on the path.
- **PI5.2** is the script's refusal of a wheel that is not there, which needs no network.
- **PI5.3** holds that the script is part of the release: `release_checks.sh` runs it, the fast
  lane's job with Prove runs it, and no workflow checks out the private Prove repository any more.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.fd6_support import REPO, built_wheel, tokenizer_file

__all__ = ["built_wheel"]

SCRIPT = REPO / "scripts" / "release" / "prove_e2e.py"
EXAMPLE = REPO / "examples" / "prove_sweep" / "run.py"
RELEASE_CHECKS = REPO / "scripts" / "release" / "release_checks.sh"
WORKFLOWS = REPO / ".github" / "workflows"


def version() -> str:
    return str(tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])


def decoy_env(root: Path) -> dict[str, str]:
    """The caller's environment with a Prove that must never be reached: a package that raises
    on import on `PYTHONPATH`, and a command that exits 99 first on `PATH`."""
    package = root / "decoy-checkout" / "poisson_prove"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("raise ImportError('a local Prove checkout was imported')\n")
    bin_dir = root / "decoy-bin"
    bin_dir.mkdir()
    command = bin_dir / "poisson-prove"
    command.write_text("#!/bin/sh\necho 'a local poisson-prove was run' >&2\nexit 99\n")
    command.chmod(0o755)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "decoy-checkout")
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    return env


def run_script(wheel: Path, work: Path, env: dict[str, str], *more: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--wheel", str(wheel), "--work", str(work),
         "--example", str(EXAMPLE), "--tokenizer", str(tokenizer_file()), *more],
        env=env, capture_output=True, text=True, timeout=3000, check=False,
    )


def test_pi5_1_the_route_runs_end_to_end_from_pypi_beside_this_trees_wheel(
    built_wheel: Path, tmp_path: Path
) -> None:
    done = run_script(built_wheel, tmp_path / "work", decoy_env(tmp_path))
    assert done.returncode == 0, (done.stdout + done.stderr)[-4000:]
    last = done.stdout.strip().splitlines()[-1]
    found = re.fullmatch(r"PROVE E2E OK: poisson-tasks (\S+) \+ poisson-prove (\S+)", last)
    assert found, last
    assert found.group(1) == version()
    for what in ("poisson_tasks comes from the wheel's environment",
                 "poisson_prove comes from the index, not a checkout",
                 "the example exits 0",
                 "every episode of every arm passed",
                 "the real command lists the runs",
                 "without poisson-prove the package imports and the adapter is refused"):
        assert f"ok   {what}" in done.stdout, what
    assert "FAIL" not in done.stdout


def test_pi5_2_the_script_refuses_a_wheel_that_is_not_there(tmp_path: Path) -> None:
    done = run_script(tmp_path / "nope.whl", tmp_path / "work", dict(os.environ))
    assert done.returncode == 2
    assert "nope.whl" in done.stdout + done.stderr
    assert not (tmp_path / "work").exists()


def load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def steps_of(job: dict[str, Any]) -> list[dict[str, Any]]:
    return list(job["steps"])


def test_pi5_3_the_release_checks_the_fast_lane_and_no_private_checkout() -> None:
    assert "prove_e2e.py" in RELEASE_CHECKS.read_text(encoding="utf-8")
    ci = load(WORKFLOWS / "ci.yml")
    runs = [s.get("run", "") for s in steps_of(ci["jobs"]["with-prove"])]
    assert any("prove_e2e.py" in r for r in runs), "the fast lane's job with Prove does not run the check"
    for name in ("ci.yml", "suite.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert "poisson-labs/prove" not in text, name
        assert "PROVE_READ_TOKEN" not in text, name
        assert "../prove" not in text, name


@pytest.mark.parametrize("name", ["ci.yml", "suite.yml"])
def test_pi5_4_the_jobs_with_prove_install_it_from_the_extra_and_the_jobs_without_check_for_the_new_name(
    name: str
) -> None:
    workflow = load(WORKFLOWS / name)
    with_prove = [job for key, job in workflow["jobs"].items() if key.endswith("with-prove")]
    without = [job for key, job in workflow["jobs"].items() if key.endswith("without-prove")]
    assert len(with_prove) == len(without) >= 1
    for job in with_prove:
        runs = "\n".join(s.get("run", "") for s in steps_of(job))
        assert re.search(r'pip install -e "\.\[dev,prove\]"', runs), name
        assert "import poisson_prove" in runs, name
        assert "proofload" not in runs.lower(), name
    for job in without:
        runs = "\n".join(s.get("run", "") for s in steps_of(job))
        assert "find_spec('poisson_prove')" in runs, name
        assert "proofload" not in runs.lower(), name
