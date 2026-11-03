"""Which Prove the `prove` extra allows, and that the route runs at the lowest it allows.

The floor is measured, not guessed.  On 2026-11-03 the end-to-end check (`scripts/release/
prove_e2e.py`, the wheel built from this tree installed with its extra and one `poisson-prove`
pinned beside it) ran against every published version: 0.1.0, 0.1.1 and 0.1.2 each passed all
twenty checks, and 0.0.1, the yanked name-hold, which has no command and no `Episode`, failed ten.
So the floor is 0.1.0, the first release that has what Tasks uses.

- **PI6.1** the extra's specifier lets 0.1.0 in and keeps the name-hold 0.0.1 out;
- **PI6.2** the route runs, end to end, at the lowest version the extra allows -- read from
  `pyproject.toml`, so a floor that is moved is a floor that is measured again.

The upper bound is a separate decision, held by its own tests.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version

from tests.fd6_support import REPO, built_wheel, tokenizer_file

__all__ = ["built_wheel"]

MEASURED_FLOOR = Version("0.1.0")
NAME_HOLD = Version("0.0.1")


def prove_requirement() -> Requirement:
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    (line,) = project["optional-dependencies"]["prove"]
    return Requirement(line)


def test_pi6_1_the_extra_allows_the_measured_floor_and_not_the_name_hold() -> None:
    requirement = prove_requirement()
    assert requirement.name == "poisson-prove"
    assert requirement.specifier.contains(MEASURED_FLOOR, prereleases=False)
    assert not requirement.specifier.contains(NAME_HOLD, prereleases=True)
    assert requirement.specifier.contains(Version("0.1.2"), prereleases=False)


def lowest_allowed(requirement: Requirement) -> Version:
    """The lowest version a specifier set names as a lower bound (`>=` or `==`)."""
    floors = [Version(s.version) for s in requirement.specifier if s.operator in (">=", "==", "~=")]
    assert floors, f"{requirement} names no lower bound"
    return max(floors)


def test_pi6_2_the_route_runs_end_to_end_at_the_lowest_prove_the_extra_allows(
    built_wheel: Path, tmp_path: Path
) -> None:
    floor = lowest_allowed(prove_requirement())
    assert floor == MEASURED_FLOOR, "the floor moved: measure it again, then change this"
    example = REPO / "examples" / "prove_sweep" / "run.py"
    done = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "release" / "prove_e2e.py"), "--wheel", str(built_wheel),
         "--work", str(tmp_path / "work"), "--example", str(example), "--tokenizer", str(tokenizer_file()),
         "--prove-version", str(floor)],
        env=dict(os.environ), capture_output=True, text=True, timeout=3000, check=False,
    )
    assert done.returncode == 0, (done.stdout + done.stderr)[-4000:]
    assert done.stdout.strip().splitlines()[-1].endswith(f"poisson-prove {floor}")
