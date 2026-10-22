"""The command's help, its version, its imports and its flags, frozen as tests.

The invariants, with rules L1, L2 and L15 (the help in this process; the fresh interpreter's half
is in `tests/test_fd5_fresh.py`):
- every verb's `--help` exits 0 and prints, on stdout, a description, help on every
  argument and at least one example command, which starts with the prog;
- `--version` is `poisson-tasks <version> (verifiers <v>, Python <v>)`, exit 0;
- `build_parser(prog)` names the command by `prog`, and so does every verb's usage;
- the command's source imports only names a module lists in `__all__`, read from its
  source;
- an abbreviated flag is refused, exit 2, naming what was typed; the flag in full is
  not; and a common flag may come before or after the verb.

Shapes decided here
-------------------

**1. The command's source** is `poisson_tasks/cli.py`, or every module of a `poisson_tasks/cli/`
package, and `poisson_tasks/__main__.py`.  A module of the command may use its own private names;
every name it takes from another `poisson_tasks` module must be in that module's `__all__`.

**2. The version line's first word is the distribution's name** as `pyproject.toml` declares it,
whatever the prog: it names the package, not a command.

**3. A verb's description is the parser's own** (`build_parser(prog)`'s subparser for the verb), so
the test reads it there and finds it, whitespace aside, in the help.  Every argument the verb's
parser declares has help text, and every one of its option strings is in the help.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.util
import importlib.metadata
import platform
import re
from pathlib import Path
from typing import Any

import pytest

from tests.fd5_support import (
    DISTRIBUTION,
    VERBS,
    Ran,
    cli,
    error_lines,
    invoke,
    prog,
    world,
)

__all__ = ["prog", "world"]


def keyless(world: Any) -> None:
    """A settings file whose model needs no key, so `doctor --offline` is ready."""
    from tests.fd5_support import config

    made = config().config_from_init_args(["--api-key-env", ""])
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")


def run(argv: list[str], prog: str, monkeypatch: pytest.MonkeyPatch) -> Ran:
    return invoke(argv, prog=prog, monkeypatch=monkeypatch)


def subparsers(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("the parser has no verbs")


def squashed(text: str) -> str:
    return " ".join(text.split())


def example_lines(text: str, prog: str, verb: str | None) -> list[str]:
    """Lines of the help that are a command starting with `<prog> <verb>`, not the usage."""
    head = prog if verb is None else f"{prog} {verb}"
    found = []
    for line in text.splitlines():
        stripped = line.strip().lstrip("$ ").strip()
        if stripped.startswith("usage:"):
            continue
        if stripped == head or stripped.startswith(head + " "):
            found.append(stripped)
    return found


# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verb", VERBS)
def test_fd5_1_a_verbs_help_has_its_description_every_argument_and_an_example(
    verb: str, prog: str, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = run([verb, "--help"], prog, monkeypatch)
    assert ran.code == 0, ran
    assert ran.err == "", ran
    parser = subparsers(cli().build_parser(prog))[verb]
    assert parser.description and parser.description.strip(), f"{verb} has no description"
    assert squashed(parser.description) in squashed(ran.out), ran
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        assert action.help and action.help is not argparse.SUPPRESS and action.help.strip(), (
            f"{verb}: {action.option_strings or action.dest} has no help")
        for option in action.option_strings:
            assert re.search(rf"(?<![\w-]){re.escape(option)}(?![\w-])", ran.out), (
                f"{verb}'s help does not show {option}")
    assert example_lines(ran.out, prog, verb), f"{verb}'s help gives no example:\n{ran.out}"


def test_fd5_1_the_top_level_help_names_every_verb_and_gives_an_example(
    prog: str, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = run(["--help"], prog, monkeypatch)
    assert ran.code == 0 and ran.err == "", ran
    parser = cli().build_parser(prog)
    assert parser.description and squashed(parser.description) in squashed(ran.out)
    for verb in VERBS:
        assert re.search(rf"(?<![\w-]){verb}(?![\w-])", ran.out), f"{verb} is not listed"
    assert example_lines(ran.out, prog, None), ran.out


@pytest.mark.parametrize("verb", VERBS)
def test_fd5_1_help_comes_before_everything_else_a_verb_checks(
    verb: str, prog: str, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--help` beside arguments a verb would refuse still prints the help and exits 0: help is
    read before anything else is checked, and checks nothing."""
    monkeypatch.setattr("sys.platform", "win32")
    ran = run([verb, "--config", "no-such-file.toml", "--help"], prog, monkeypatch)
    assert ran.code == 0, ran
    assert example_lines(ran.out, prog, verb), ran
    assert list(Path(".").iterdir()) == []


def test_fd5_1_init_says_measure_is_an_alias_of_recipe(
    prog: str, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recipes: `--recipe` is the flag for init's sixth question and `--measure` its alias for one
    release, which `init --help` says."""
    ran = run(["init", "--help"], prog, monkeypatch)
    assert ran.code == 0, ran
    lines = ran.out.splitlines()
    at = [index for index, line in enumerate(lines)
          if re.match(r"^\s*-", line) and re.search(r"(?<![\w-])--measure(?![\w-])", line)]
    assert at, ran.out
    entry = [lines[at[0]]]
    for line in lines[at[0] + 1:]:
        if re.match(r"^\s*-", line) or not line.startswith(" "):
            break
        entry.append(line)
    assert "--recipe" in " ".join(entry), entry


# ---------------------------------------------------------------------------
# the version
# ---------------------------------------------------------------------------


def test_fd5_2_the_version_names_the_package_verifiers_and_python(
    prog: str, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = run(["--version"], prog, monkeypatch)
    assert ran.code == 0, ran
    assert ran.err == ""
    expected = (f"{DISTRIBUTION} {importlib.metadata.version(DISTRIBUTION)} (verifiers "
                f"{importlib.metadata.version('verifiers')}, Python "
                f"{platform.python_version()})\n")
    assert ran.out == expected


# ---------------------------------------------------------------------------
# the parser
# ---------------------------------------------------------------------------


def test_fd5_6_the_parser_and_every_verbs_usage_carry_the_prog(prog: str) -> None:
    parser = cli().build_parser(prog)
    assert parser.prog == prog
    assert parser.format_usage().split(":", 1)[1].strip().startswith(prog + " ")
    for verb, sub in subparsers(parser).items():
        assert sub.prog == f"{prog} {verb}", (verb, sub.prog)


# ---------------------------------------------------------------------------
# public names only
# ---------------------------------------------------------------------------


def command_sources() -> list[Path]:
    package = Path(importlib.import_module("poisson_tasks").__file__ or "").resolve().parent
    found = []
    if (package / "cli.py").is_file():
        found.append(package / "cli.py")
    if (package / "cli").is_dir():
        found += sorted((package / "cli").rglob("*.py"))
    if (package / "__main__.py").is_file():
        found.append(package / "__main__.py")
    return found


def borrowed_names(source: str, own: tuple[str, ...],
                   here: str = "poisson_tasks.cli") -> list[tuple[str, str, int]]:
    """Every (module, name, line) the source takes from a `poisson_tasks` module other than its
    own: a `from` import's names, and each attribute read off a name bound to such a module in
    the scope that reads it (a function's own assignment or argument hides a module's binding)."""
    tree = ast.parse(source)
    taken: list[tuple[str, str, int]] = []

    def library(module: str) -> bool:
        return module.startswith("poisson_tasks") and not module.startswith(own)

    def own_nodes(scope: ast.AST) -> list[ast.AST]:
        """The scope's nodes, without those of the functions and classes nested in it."""
        found: list[ast.AST] = []
        stack = list(ast.iter_child_nodes(scope))
        while stack:
            node = stack.pop()
            found.append(node)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                                 ast.ClassDef)):
                continue
            stack.extend(ast.iter_child_nodes(node))
        return found

    def visit(scope: ast.AST, outer: dict[str, str]) -> None:
        nodes = own_nodes(scope)
        bound = dict(outer)
        hidden: set[str] = set()
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            arguments = scope.args
            for arg in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
                        *([arguments.vararg] if arguments.vararg else []),
                        *([arguments.kwarg] if arguments.kwarg else [])):
                hidden.add(arg.arg)
        for node in nodes:
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                hidden.add(node.id)
        for name in hidden:
            bound.pop(name, None)
        for node in nodes:
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    base = here.rsplit(".", node.level)[0] if here.count(".") >= node.level \
                        else ""
                    module = ".".join(part for part in (base, node.module or "") if part)
                elif node.module:
                    module = node.module
                else:
                    continue
                for alias in node.names:
                    as_module = f"{module}.{alias.name}"
                    if module == "poisson_tasks" or _is_module(as_module):
                        if library(as_module):
                            bound[alias.asname or alias.name] = as_module
                    elif library(module):
                        taken.append((module, alias.name, node.lineno))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("poisson_tasks"):
                        bound[alias.asname or alias.name.split(".")[0]] = (
                            alias.name if alias.asname else alias.name.split(".")[0])
            elif isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                if name == "import_module" and node.args and isinstance(
                        node.args[0], ast.Constant) and library(str(node.args[0].value)):
                    taken.append((str(node.args[0].value), "*import_module", node.lineno))
        for node in nodes:
            if isinstance(node, ast.Attribute):
                chain: list[str] = []
                inner: ast.AST = node
                while isinstance(inner, ast.Attribute):
                    chain.insert(0, inner.attr)
                    inner = inner.value
                if isinstance(inner, ast.Name) and inner.id in bound:
                    held = bound[inner.id]
                    for attr in chain:
                        if _is_module(f"{held}.{attr}"):
                            held = f"{held}.{attr}"
                            continue
                        if library(held):
                            taken.append((held, attr, node.lineno))
                        break
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in ("getattr", "hasattr") and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name) and node.args[0].id in bound
                    and isinstance(node.args[1], ast.Constant)):
                taken.append((bound[node.args[0].id], str(node.args[1].value), node.lineno))
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                                 ast.ClassDef)):
                visit(node, bound)

    visit(tree, {})
    return taken


def _is_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def not_public(source: str, own: tuple[str, ...], here: str = "poisson_tasks.cli") -> list[str]:
    bad = []
    for module, name, line in borrowed_names(source, own, here):
        if name == "*import_module":
            bad.append(f"line {line}: {module} imported by name at run time")
            continue
        listed = getattr(importlib.import_module(module), "__all__", None)
        if listed is None or name not in listed:
            bad.append(f"line {line}: {module}.{name} is not in its __all__")
    return bad


def test_fd5_7_the_command_takes_only_names_a_module_lists_in_all() -> None:
    sources = command_sources()
    assert sources, "no command source: poisson_tasks/cli.py or poisson_tasks/cli/"
    assert any(path.name == "__main__.py" for path in sources), "no poisson_tasks/__main__.py"
    own = ("poisson_tasks.cli",)
    problems = []
    package = Path(importlib.import_module("poisson_tasks").__file__ or "").resolve().parent
    for path in sources:
        parts = path.relative_to(package).with_suffix("").parts
        here = ".".join(("poisson_tasks", *parts))
        if path.name == "__init__.py" or parts == ("__main__",):
            here = ".".join(("poisson_tasks", *parts[:-1], "x"))
        problems += [f"{path.name} {problem}"
                     for problem in not_public(path.read_text(encoding="utf-8"), own, here)]
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------
# abbreviations, and flags before or after the verb
# ---------------------------------------------------------------------------

ABBREVIATED = [
    (["--vers", "doctor", "--offline"], ["--version", "doctor", "--offline"]),
    (["doctor", "--off"], ["doctor", "--offline"]),
    (["doctor", "--show-com"], ["doctor", "--show-command"]),
    (["init", "--yes", "--no-check-key", "--rec", "first-look"],
     ["init", "--yes", "--no-check-key", "--recipe", "first-look"]),
    (["generate", "--arm", "depth:d1", "--tasks-per", "1", "--print"],
     ["generate", "--arm", "depth:d1", "--tasks-per-level", "1", "--print"]),
    (["card", "--pub"], ["card", "--published"]),
    (["verify", "--arm", "depth:d1", "--task", "1", "--self"],
     ["verify", "--arm", "depth:d1", "--task", "1", "--self-check"]),
    (["run", "--dry", "--offline"], ["run", "--dry-run", "--offline"]),
    (["export", "--ou", "x"], ["export", "--out", "x"]),
]


@pytest.mark.parametrize("abbreviated,full", ABBREVIATED,
                         ids=[" ".join(case[0][:2]).replace("doctor", "") .strip()
                              for case in ABBREVIATED])
def test_fd5_13_an_abbreviated_flag_is_refused_and_the_full_flag_is_not(
    abbreviated: list[str], full: list[str], prog: str, world: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refused = run(abbreviated, prog, monkeypatch)
    assert refused.code == 2, refused
    typed = next(word for word in abbreviated if word not in full)
    lines = error_lines(refused)
    assert lines and typed in lines[0], refused
    for path in Path(".").iterdir():
        if path.name == "tasks.toml":
            path.unlink()
    if full[0] in ("--version", "doctor"):
        keyless(world)
    accepted = run(full, prog, monkeypatch)
    assert accepted.code != 2, accepted


@pytest.mark.parametrize("flag", ["--json", "--debug"])
def test_fd5_13_a_common_flag_may_come_before_or_after_the_verb(
    flag: str, prog: str, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    keyless(world)
    after = run(["doctor", "--offline", flag], prog, monkeypatch)
    before = run([flag, "doctor", "--offline"], prog, monkeypatch)
    assert after.code == before.code == 0, (after, before)
    assert after.out == before.out


def test_fd5_13_config_may_come_before_or_after_the_verb(
    prog: str, world: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    after = run(["doctor", "--offline", "--config", "elsewhere.toml"], prog, monkeypatch)
    before = run(["--config", "elsewhere.toml", "doctor", "--offline"], prog, monkeypatch)
    assert after.code == before.code == 1, (after, before)
    assert error_lines(after) == error_lines(before)
    assert "elsewhere.toml" in error_lines(after)[0]
