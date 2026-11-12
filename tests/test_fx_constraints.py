"""The versions the suite is tested with are a constraints file that CI installs from, and the
package's metadata is unchanged (#40, ruled 2026-11-11: a tested constraints file, not upper
bounds).

Only `verifiers` and `tiktoken` were pinned, so a fresh install resolved newer releases of
everything else than the release was tested with (eleven packages had moved three days after 0.4.1,
none by a major version, which is why upper bounds would have caught none of it).  So:
- `constraints.txt` pins every package a checkout's `pip install -e ".[dev]"` installs, at the
  version the whole suite last passed on, each version inside what the package itself asks for;
- the package's own dependencies keep their floors and their two pins, and gain no ceiling, so
  an install into an environment you already have resolves as before, and every published Prove
  still installs beside it;
- CI's jobs without Prove install from the file, and the jobs with Prove do not, so they still
  meet a new release of any dependency (Prove's among them) first;
- neither Tasks itself nor Prove is in the file.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO = Path(__file__).resolve().parents[1]
CONSTRAINTS = REPO / "constraints.txt"
WORKFLOWS = REPO / ".github" / "workflows"
PROJECT = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def pinned() -> dict[str, Requirement]:
    found: dict[str, Requirement] = {}
    for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        requirement = Requirement(line)
        found[canonicalize_name(requirement.name)] = requirement
    return found


def version_of(requirement: Requirement) -> str:
    (spec,) = list(requirement.specifier)
    return spec.version


def test_every_line_pins_one_exact_version() -> None:
    lines = [line for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    assert len(lines) > 50, len(lines)
    for line in lines:
        requirement = Requirement(line)
        specs = list(requirement.specifier)
        assert len(specs) == 1 and specs[0].operator == "==", line
        assert not requirement.extras, line
    names = [canonicalize_name(Requirement(line).name) for line in lines]
    assert len(names) == len(set(names)), "a package is pinned twice"


def test_every_dependency_and_dev_tool_is_pinned_inside_what_the_package_asks_for() -> None:
    pins = pinned()
    asked = [*PROJECT["dependencies"], *PROJECT["optional-dependencies"]["dev"]]
    for text in asked:
        requirement = Requirement(text)
        name = canonicalize_name(requirement.name)
        assert name in pins, f"{name} is not in constraints.txt"
        assert requirement.specifier.contains(version_of(pins[name]), prereleases=True), (
            text, str(pins[name]))


def test_neither_tasks_nor_prove_is_constrained() -> None:
    pins = pinned()
    assert "poisson-tasks" not in pins
    assert "poisson-prove" not in pins and "proofload" not in pins


def test_the_package_metadata_keeps_its_floors_and_two_pins_and_gains_no_ceiling() -> None:
    ceilings = []
    exact = []
    for text in [*PROJECT["dependencies"], *PROJECT["optional-dependencies"]["prove"]]:
        requirement = Requirement(text)
        for spec in requirement.specifier:
            if spec.operator in ("<", "<=", "~=", "!="):
                ceilings.append(text)
            if spec.operator == "==":
                exact.append(canonicalize_name(requirement.name))
    assert ceilings == [], ceilings
    assert sorted(exact) == ["tiktoken", "verifiers"], exact
    assert PROJECT["optional-dependencies"]["prove"] == ["poisson-prove>=0.1.0"]


def load(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def installs(job: dict[str, Any]) -> list[str]:
    return [line.strip() for step in job["steps"] for line in str(step.get("run", "")).splitlines()
            if re.search(r"pip install (?!build==)", line)]


@pytest.mark.parametrize("name", ["ci.yml", "suite.yml"])
def test_the_jobs_without_prove_install_the_tested_versions_and_the_jobs_with_prove_do_not(
    name: str,
) -> None:
    jobs = load(name)["jobs"]
    without = {key: job for key, job in jobs.items() if key.endswith("without-prove")}
    with_prove = {key: job for key, job in jobs.items() if key.endswith("with-prove")}
    assert without and with_prove
    for key, job in without.items():
        lines = installs(job)
        assert lines, key
        assert all("-c constraints.txt" in line for line in lines), (key, lines)
    for key, job in with_prove.items():
        lines = installs(job)
        assert lines, key
        assert not any("constraints" in line for line in lines), (key, lines)
