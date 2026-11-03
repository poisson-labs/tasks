"""The licence the package claims: an SPDX expression, not the licence text.

PyPI printed the whole MIT text in its License field, because `license = { file = "LICENSE" }`
puts the file's text into the `License:` header.  PEP 639's form is an SPDX expression, which a
page shows as `MIT`, and the files go in `License-File` headers.  These tests hold, on the
metadata of a wheel and an sdist built from this tree:

- `License-Expression: MIT`, and no `License:` header carrying the text;
- no `License ::` classifier, which PEP 639 retires beside an expression;
- `License-File` names the two files the package has always shipped, `LICENSE` and `NOTICE`
  (the second holds the notices of third-party material), and the wheel carries both under
  `dist-info/licenses/`;
- `pyproject.toml` says the same, and asks for a hatchling that reads the expression.
"""

from __future__ import annotations

import email.parser
import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

from tests.fd6_support import REPO, built_wheel

__all__ = ["built_wheel"]

LICENSE_FILES = ["LICENSE", "NOTICE"]
TEXT_MARK = "Permission is hereby granted"


def pyproject() -> dict[str, object]:
    return tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))


def parse(text: str) -> email.message.Message:
    return email.parser.Parser().parsestr(text)


@pytest.fixture(scope="session")
def built_sdist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    into = tmp_path_factory.mktemp("pi-sdist")
    done = subprocess.run(
        [sys.executable, "-c",
         "import sys; from hatchling.build import build_sdist; print(build_sdist(sys.argv[1]))",
         str(into)],
        cwd=REPO, capture_output=True, text=True, timeout=600, check=False,
    )
    assert done.returncode == 0, done.stderr[-3000:]
    sdist = into / done.stdout.strip().splitlines()[-1]
    assert sdist.is_file(), done.stdout
    return sdist


def wheel_head(wheel: Path) -> email.message.Message:
    with zipfile.ZipFile(wheel) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        return parse(archive.read(name).decode("utf-8"))


def sdist_head(sdist: Path) -> email.message.Message:
    with tarfile.open(sdist) as archive:
        name = next(n for n in archive.getnames() if n.count("/") == 1 and n.endswith("/PKG-INFO"))
        member = archive.extractfile(name)
        assert member is not None
        return parse(member.read().decode("utf-8"))


def test_pi4_1_pyproject_says_the_licence_is_the_spdx_expression_mit_and_lists_its_files() -> None:
    project = pyproject()["project"]
    assert isinstance(project, dict)
    assert project["license"] == "MIT"
    assert project["license-files"] == LICENSE_FILES
    for name in LICENSE_FILES:
        assert (REPO / name).is_file(), name
    assert [c for c in project["classifiers"] if c.startswith("License ::")] == []


def test_pi4_2_the_build_backend_asked_for_reads_a_licence_expression() -> None:
    """PEP 639 support arrived in hatchling 1.27.0, the floor `dev` already names."""
    requires = pyproject()["build-system"]["requires"]  # type: ignore[index]
    floors = [r for r in requires if r.lower().startswith("hatchling")]
    assert len(floors) == 1, requires
    found = re.search(r">=\s*(\d+)\.(\d+)", floors[0])
    assert found and (int(found.group(1)), int(found.group(2))) >= (1, 27), floors[0]


def test_pi4_3_the_wheel_shows_license_expression_mit_and_no_licence_text_in_a_header(
    built_wheel: Path,
) -> None:
    head = wheel_head(built_wheel)
    assert head.get_all("License-Expression") == ["MIT"]
    assert head.get("License") is None
    assert [c for c in head.get_all("Classifier") or [] if c.startswith("License ::")] == []
    assert head.get_all("License-File") == LICENSE_FILES
    major, minor = head["Metadata-Version"].split(".")[:2]
    assert (int(major), int(minor)) >= (2, 4), head["Metadata-Version"]
    raw = "\n".join(f"{key}: {value}" for key, value in head.items())
    assert TEXT_MARK not in raw


def test_pi4_4_the_wheel_carries_the_licence_files_under_dist_info_licenses(
    built_wheel: Path,
) -> None:
    with zipfile.ZipFile(built_wheel) as archive:
        names = archive.namelist()
        for name in LICENSE_FILES:
            inside = [n for n in names if re.fullmatch(rf"[^/]+\.dist-info/licenses/{name}", n)]
            assert len(inside) == 1, (name, inside)
            assert archive.read(inside[0]) == (REPO / name).read_bytes()


def test_pi4_5_the_sdist_says_the_same(built_sdist: Path) -> None:
    head = sdist_head(built_sdist)
    assert head.get_all("License-Expression") == ["MIT"]
    assert head.get("License") is None
    assert head.get_all("License-File") == LICENSE_FILES
    assert TEXT_MARK not in "\n".join(f"{key}: {value}" for key, value in head.items())
