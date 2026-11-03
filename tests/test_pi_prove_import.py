"""Tasks beside Prove as published: the import path, the optional extra, and the refusal without it.

Prove went public as the distribution `poisson-prove` and the package `poisson_prove`.  Every
Tasks release up to 0.3.0 imported it as `proofload`, so a Tasks installed beside the published
Prove could not use the Prove route.  These tests hold what 0.3.1 says instead:

- **The import.**  `poisson_tasks.adapter` takes `Episode` (and, if it ever needs it, `Rollout`)
  from the top level of `poisson_prove` and nothing else from Prove, and no module of the
  package names the old import.
- **Prove stays optional.**  Nothing the package imports on its own path reaches the adapter or
  Prove: every other module imports with `poisson_prove` unavailable, and importing the adapter
  then is refused with a message that names the extra, `poisson-tasks[prove]`, and says nothing
  of a checkout.
- **The extra is real.**  `pyproject.toml` declares a `prove` extra that depends on
  `poisson-prove`; the `dev` extra and the base dependencies do not, so the suite without Prove
  stays a suite without it; the built wheel carries the extra in its metadata; the old comment
  block that said Prove was unpublished is gone.
- **The old name is not printed.**  The adapter's source holds no `proofload` at all.

The tests need no Prove: the one that runs the package with Prove unavailable blocks it by name,
whether or not it is installed.
"""

from __future__ import annotations

import ast
import email.parser
import re
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

from tests.fd6_support import REPO, built_wheel

__all__ = ["built_wheel"]

SRC = REPO / "src"
ADAPTER = SRC / "poisson_tasks" / "adapter.py"
PYPROJECT = REPO / "pyproject.toml"
OLD_NAME = "proofload"
NEW_NAME = "poisson_prove"
ALLOWED_FROM_PROVE = {"Episode", "Rollout"}


def pyproject() -> dict[str, object]:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def requirement_name(requirement: str) -> str:
    """The distribution a requirement string names, in PEP 503's normal form."""
    found = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    assert found, requirement
    return re.sub(r"[-_.]+", "-", found.group(1)).lower()


def source_modules() -> list[Path]:
    found = sorted(path for path in SRC.rglob("*.py") if "__pycache__" not in path.parts)
    assert found, "no source module found"
    return found


def imported_roots(tree: ast.AST) -> list[tuple[str, tuple[str, ...], int]]:
    """Every import in a tree as (module, imported names, relative level)."""
    found: list[tuple[str, tuple[str, ...], int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(alias.name, (), 0) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", tuple(a.name for a in node.names), node.level))
    return found


# ---------------------------------------------------------------------------
# PI1: the adapter's import
# ---------------------------------------------------------------------------


def test_pi1_1_the_adapter_takes_episode_from_the_top_of_poisson_prove_and_nothing_else() -> None:
    tree = ast.parse(ADAPTER.read_text(encoding="utf-8"))
    from_prove = [(m, n) for m, n, level in imported_roots(tree)
                  if level == 0 and m.split(".")[0] == NEW_NAME]
    assert from_prove, "the adapter imports nothing from poisson_prove"
    for module, names in from_prove:
        assert module == NEW_NAME, f"{module}: only the top of the package may be imported"
        assert names and set(names) <= ALLOWED_FROM_PROVE, names
    assert any("Episode" in names for _module, names in from_prove)


def test_pi1_2_the_adapter_holds_the_old_name_nowhere() -> None:
    """Not as an import, and not as a word: the old name is not printed, and a refusal that
    sent a reader to `../proofload` would be the old advice."""
    source = ADAPTER.read_text(encoding="utf-8")
    assert OLD_NAME not in source.lower()
    assert [m for m, _n, level in imported_roots(ast.parse(source))
            if level == 0 and m.split(".")[0] == OLD_NAME] == []


def test_pi1_3_the_control_the_check_sees_a_wrong_import() -> None:
    """The control for the two checks above: a deep import, a bare `import poisson_prove` and
    the old name are each seen by the walk they rely on."""
    for wrong in ("from poisson_prove.store import x", "import poisson_prove", "from proofload import Episode"):
        roots = imported_roots(ast.parse(wrong))
        assert [m for m, _n, _l in roots if m.split(".")[0] in (NEW_NAME, OLD_NAME)], wrong
    assert imported_roots(ast.parse("from poisson_prove import Episode")) == [(NEW_NAME, ("Episode",), 0)]


# ---------------------------------------------------------------------------
# PI2: Prove stays optional
# ---------------------------------------------------------------------------


def test_pi2_1_no_module_but_the_adapter_imports_prove_or_the_adapter() -> None:
    for path in source_modules():
        if path == ADAPTER:
            continue
        source = path.read_text(encoding="utf-8")
        for module, names, level in imported_roots(ast.parse(source)):
            root = module.split(".")[0]
            assert root not in (NEW_NAME, OLD_NAME), f"{path.name} imports {module}"
            assert not (level == 0 and module == "poisson_tasks.adapter"), path.name
            assert not (level > 0 and (module == "adapter" or "adapter" in names)), path.name
        assert NEW_NAME not in source, f"{path.name} names {NEW_NAME}, so a string import could hide there"


def test_pi2_2_every_module_but_the_adapter_imports_with_prove_unavailable_and_the_adapter_is_refused(
    tmp_path: Path,
) -> None:
    """`sys.modules['poisson_prove'] = None` makes the import fail whether or not Prove is
    installed, so this holds in both lanes.  Every other module of the package imports; the
    adapter's refusal is a `ModuleNotFoundError` naming the extra."""
    program = (
        "import importlib, pkgutil, sys\n"
        "sys.modules['poisson_prove'] = None\n"
        "import poisson_tasks, poisson_tasks_own\n"
        "done = []\n"
        "for package in (poisson_tasks, poisson_tasks_own):\n"
        "    for info in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):\n"
        "        if info.name.endswith(('.adapter', '.__main__')):\n"
        "            continue\n"
        "        importlib.import_module(info.name)\n"
        "        done.append(info.name)\n"
        "print(len(done), 'modules imported')\n"
        "try:\n"
        "    import poisson_tasks.adapter\n"
        "except ModuleNotFoundError as exc:\n"
        "    print('REFUSED:' + str(exc))\n"
        "else:\n"
        "    print('NOT REFUSED')\n"
    )
    done = subprocess.run([sys.executable, "-c", program], cwd=tmp_path, capture_output=True,
                          text=True, timeout=300, check=False)
    assert done.returncode == 0, done.stderr[-3000:]
    lines = done.stdout.strip().splitlines()
    imported = int(lines[0].split()[0])
    assert imported >= 20, lines[0]
    refusal = next(line for line in lines if line.startswith(("REFUSED:", "NOT REFUSED")))
    assert refusal.startswith("REFUSED:"), refusal
    message = refusal.removeprefix("REFUSED:")
    assert 'pip install "poisson-tasks[prove]"' in message, message
    assert "poisson-prove" in message, message
    for old in (OLD_NAME, "checkout", "pip install -e", "not publicly", "not public"):
        assert old not in message.lower(), (old, message)


# ---------------------------------------------------------------------------
# PI3: the extra
# ---------------------------------------------------------------------------


def test_pi3_1_pyproject_declares_a_prove_extra_that_depends_on_poisson_prove() -> None:
    data = pyproject()
    project = data["project"]
    assert isinstance(project, dict)
    extras = project["optional-dependencies"]
    assert set(extras) == {"prove", "dev"}, sorted(extras)
    assert [requirement_name(r) for r in extras["prove"]] == ["poisson-prove"], extras["prove"]


def test_pi3_2_nothing_else_pulls_prove_in_so_the_suite_without_it_stays_that() -> None:
    project = pyproject()["project"]
    assert isinstance(project, dict)
    for where in (project["dependencies"], project["optional-dependencies"]["dev"]):
        names = {requirement_name(r) for r in where}
        assert names.isdisjoint({"poisson-prove", OLD_NAME}), names


def test_pi3_3_pyproject_holds_no_word_of_the_old_name_or_of_prove_being_unpublished() -> None:
    text = PYPROJECT.read_text(encoding="utf-8").lower()
    assert OLD_NAME not in text
    assert "unpublished" not in text and "not public" not in text
    overrides = pyproject()["tool"]["mypy"]["overrides"]  # type: ignore[index]
    held = [o for o in overrides if NEW_NAME in (o["module"] if isinstance(o["module"], list) else [o["module"]])]
    assert held and held[0]["ignore_missing_imports"] is True, (
        "mypy over a plain install has nothing to read for the adapter's import")


def test_pi3_4_the_wheel_carries_the_extra_and_asks_for_poisson_prove_only_with_it(
    built_wheel: Path,
) -> None:
    with zipfile.ZipFile(built_wheel) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        head = email.parser.Parser().parsestr(archive.read(name).decode("utf-8"))
    assert "prove" in (head.get_all("Provides-Extra") or [])
    wanted = [r for r in head.get_all("Requires-Dist") or [] if requirement_name(r) == "poisson-prove"]
    assert wanted, "the wheel does not ask for poisson-prove at all"
    assert all(re.search(r"""extra == ['"]prove['"]""", r) for r in wanted), wanted
