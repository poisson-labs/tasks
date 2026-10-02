"""`--help` and a bad argument, on the three examples, the encoding fetch and the bundle check.

Each script's `--help` exits 0 and prints, on stdout, the script's own description (the first
line of its docstring) and the arguments it takes. It runs nothing: no line a plain run prints
appears in it.

A bad argument gets one line on stderr, `error: ...`, that names what was wrong, and nothing on
stdout. The exit code is 2 when the command line itself is wrong, and 1 when the thing it names
is refused. Each bad argument has a control: the same command with a good argument in its place
exits 0, so the refusal is about that argument and nothing else.

The examples are run from the repository root, as their docstrings and the docs show them.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
EXAMPLES = REPO / "examples"
FETCH = "poisson_tasks.fetch_encoding"

COMMANDS = {
    "one_task.py": [sys.executable, str(EXAMPLES / "one_task.py")],
    "a_contrast.py": [sys.executable, str(EXAMPLES / "a_contrast.py")],
    "calibration_card.py": [sys.executable, str(EXAMPLES / "calibration_card.py")],
    "fetch_encoding": [sys.executable, "-m", FETCH],
}
VERIFY = [sys.executable, "-m", "poisson_tasks.calibration_run", "verify"]

# The arguments each script takes, as its docstring's usage lines and the docs name them.
ARGUMENTS = {
    "one_task.py": ("SEED",),
    "a_contrast.py": (),
    "calibration_card.py": ("DIR", "--page"),
    "fetch_encoding": ("--force",),
}


def run(command: list[str], *args: str, cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*command, *args], cwd=cwd, capture_output=True, text=True, timeout=300)


def docstring(name: str) -> str:
    """The script's docstring, read from its source without running it."""
    if name.endswith(".py"):
        path = EXAMPLES / name
    else:
        spec = importlib.util.find_spec(FETCH)
        assert spec is not None and spec.origin is not None
        path = Path(spec.origin)
    return ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""


def squash(text: str) -> str:
    return " ".join(text.split())


@pytest.fixture(scope="module")
def plain() -> dict[str, str]:
    """What each script prints with no argument. The encoding fetch finds its file in place
    and fetches nothing."""
    printed = {}
    for name, command in COMMANDS.items():
        done = run(command)
        assert done.returncode == 0, (name, done.stderr[-2000:])
        printed[name] = done.stdout
    return printed


@pytest.mark.parametrize("name", COMMANDS)
def test_help_gives_the_description_and_the_arguments_and_runs_nothing(
    name: str, plain: dict[str, str]
) -> None:
    done = run(COMMANDS[name], "--help")
    assert (done.returncode, done.stderr) == (0, ""), done.stderr[-2000:]
    doc = docstring(name)
    assert doc and squash(doc.splitlines()[0]) in squash(done.stdout), done.stdout
    # The arguments are looked for outside the docstring, whose usage lines name them too.
    rest = squash(done.stdout).replace(squash(doc), " ")
    missing = [argument for argument in ARGUMENTS[name] if argument not in rest]
    assert missing == [], done.stdout
    ran = {line.strip() for line in plain[name].splitlines() if line.strip()}
    shared = ran & {line.strip() for line in done.stdout.splitlines()}
    assert not shared, sorted(shared)[:5]


def bundle(root: Path) -> Path:
    """A bundle `verify` accepts: one file, and a manifest that holds its digest."""
    folder = root / "bundle"
    folder.mkdir()
    card = b"a card\n"
    (folder / "card.md").write_bytes(card)
    digest = hashlib.sha256(card).hexdigest()
    (folder / "MANIFEST.sha256").write_text(f"{digest}  card.md\n", encoding="utf-8")
    return folder


def not_a_zip(root: Path) -> Path:
    path = root / "card.zip"
    path.write_text("not an archive\n", encoding="utf-8")
    return path


def no_manifest(root: Path) -> Path:
    folder = root / "unzipped"
    folder.mkdir()
    (folder / "card.md").write_bytes(b"a card\n")
    return folder


# id: (script, the bad argument, the exit code, the good argument in its place)
BAD = {
    "seed-not-a-number": ("one_task.py", "seven", 2, "404"),
    "seed-out-of-range": ("one_task.py", "4294967296", 2, "4294967295"),
    "contrast-takes-no-argument": ("a_contrast.py", "--bogus", 2, None),
    "not-a-card-folder": ("calibration_card.py", "calibration/nope", 1, "calibration/qwen3-8b-b968826d"),
    "no-such-bundle": ("verify", "nope.zip", 1, bundle),
    "bundle-not-a-zip": ("verify", not_a_zip, 1, bundle),
    "bundle-without-a-manifest": ("verify", no_manifest, 1, bundle),
}


@pytest.mark.parametrize("case", BAD)
def test_a_bad_argument_gets_one_line_naming_it_and_no_traceback(case: str, tmp_path: Path) -> None:
    name, bad, code, good = BAD[case]
    command, cwd = (VERIFY, tmp_path) if name == "verify" else (COMMANDS[name], REPO)
    bad_arg = bad if isinstance(bad, str) else str(bad(tmp_path))
    done = run(command, bad_arg, cwd=cwd)
    lines = [line for line in done.stderr.splitlines() if line.strip()]
    assert done.returncode == code, done.stderr[-2000:]
    assert done.stdout == "" and len(lines) == 1, done.stderr[-2000:]
    assert lines[0].startswith("error: ") and bad_arg in lines[0], lines[0]

    good_args = [] if good is None else [good if isinstance(good, str) else str(good(tmp_path))]
    control = run(command, *good_args, cwd=cwd)
    assert control.returncode == 0, control.stderr[-2000:]
