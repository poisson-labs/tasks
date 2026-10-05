"""The generator hash covers every module that shapes a task, and the engine does not move,
frozen as tests.

A task's id hashes its generator hash, so the generator hash must move whenever a task could:
when the generator version label changes, or the bytes of `tasks.py`, of `surface.py` (the
display names and the fault plan) or of `knobs.py` (the knobs' levels and literals).  It must
move for nothing else -- not the process, `PYTHONHASHSEED`, or the folder the package is
installed in -- or one task would carry two ids.

Shapes decided here
-------------------

**1. The construction**, written out below and recomputed here: SHA-256 over the domain line
`task-generator/generator_hash/2`, then the version label, `tasks.py`, `surface.py` and
`knobs.py`, in that order, separated by the byte 0x1f, as the version and the source were before.

**2. "Moves for those and nothing else" is shown on copies of the package**, each in a fresh
interpreter: one byte appended to each of the three modules moves the hash, the same bytes in
another folder or under another hash seed do not, and an edit to a module outside the three
(`export.py`) does not.

**3. The engine is untouched.**  `engine.py`'s bytes are pinned, which is true the moment this
file is committed and pins nothing about the build by itself; the vocabulary table and the
tokenizer data are pinned by the engine's own tests, and every published task's `engine_hash` is
held equal by `tests/test_k1_content.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import generate

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "src" / "poisson_tasks"
DOMAIN = b"task-generator/generator_hash/2\n"
MODULES = ("tasks.py", "surface.py", "knobs.py")
ENGINE_SHA256 = "5ae0ae984b960cf52fe9691141ff05f63a2df33bdcbcc767330c0f0177aaa725"


def expected(version: str, package: Path = PACKAGE) -> str:
    parts = [version.encode("utf-8")] + [(package / name).read_bytes() for name in MODULES]
    return hashlib.sha256(DOMAIN + b"\x1f".join(parts)).hexdigest()


@pytest.mark.parametrize("version", ["1", "0", "tg-m3-v1"])
def test_the_generator_hash_is_the_version_and_the_three_modules_bytes(version: str) -> None:
    bundle = generate(arm_from_id("depth:d3", generator_version=version), 404)
    assert bundle.generator_hash == expected(version)
    assert bundle.pins.values["N12"][1] == expected(version)


def hash_in(package_root: Path, seed: str = "0") -> str:
    """The generator hash a fresh interpreter computes from the package under `package_root`."""
    code = (
        "import json\n"
        "from poisson_tasks.arms import arm_from_id\n"
        "from poisson_tasks.tasks import generate\n"
        "print(json.dumps(generate(arm_from_id('depth:d3'), 404).generator_hash))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(package_root), "PYTHONHASHSEED": seed}
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env=env, cwd=package_root, timeout=300)
    assert done.returncode == 0, done.stderr[-2000:]
    return str(json.loads(done.stdout))


@pytest.fixture(scope="module")
def copies(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """The hash from copies of the package: as it is, elsewhere and under another hash seed, and
    with one byte appended to each of four modules."""
    out = {}
    for label, edited, seed in (("as-is", None, "0"), ("elsewhere", None, "1"),
                                ("tasks.py", "tasks.py", "0"), ("surface.py", "surface.py", "0"),
                                ("knobs.py", "knobs.py", "0"), ("export.py", "export.py", "0")):
        root = tmp_path_factory.mktemp(label.replace(".", "-"))
        shutil.copytree(PACKAGE, root / "poisson_tasks",
                        ignore=shutil.ignore_patterns("__pycache__"))
        if edited is not None:
            with (root / "poisson_tasks" / edited).open("a", encoding="utf-8") as handle:
                handle.write("\n")
        out[label] = hash_in(root, seed)
    return out


def test_the_hash_does_not_move_with_the_folder_the_process_or_the_hash_seed(
    copies: dict[str, str]
) -> None:
    here = generate(arm_from_id("depth:d3"), 404).generator_hash
    assert copies["as-is"] == copies["elsewhere"] == here


@pytest.mark.parametrize("module", MODULES)
def test_the_hash_moves_with_each_module_that_shapes_a_task(copies: dict[str, str],
                                                             module: str) -> None:
    assert copies[module] != copies["as-is"]


def test_the_hash_does_not_move_with_a_module_that_shapes_no_task(
    copies: dict[str, str]
) -> None:
    assert copies["export.py"] == copies["as-is"]


def test_the_engines_source_is_the_one_every_published_task_was_judged_by() -> None:
    """Green by construction: it hashes a committed file and pins nothing about the build."""
    assert hashlib.sha256((PACKAGE / "engine.py").read_bytes()).hexdigest() == ENGINE_SHA256
