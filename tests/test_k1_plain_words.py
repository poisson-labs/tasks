"""The generator's own source in plain words, frozen as tests.

`tasks.py`'s comments and docstrings cited specification section numbers ("2.2's block", "the
spec's 2.3"), decision-record ids (TG-ADR-35 to TG-ADR-44), module codenames (TG-M1 to TG-M3),
numbered decisions of a test file and one requirement id no test carries, and one message a user
could see ended "(G4)".  A reader of the repository cannot look any of those up.  They were left
because every byte of `tasks.py` is in the generator hash, so rewording them moved every task id;
they change with the generator change that adds the new knobs, when the ids move anyway.  The
same holds from now on for `surface.py`, which the generator hash covers too.

The prose rule is the one the engine's, the knobs' and the adapter's prose were cleaned to:
invariant ids that name a test group stay (E, G, N, X, SF and A1 to A9 and A12), and so does a
gap-log id, since `gap-log.md` is in the repository; everything else must say what it means.
String values a user can see are held to the stricter rule `tests/test_plain_words_knobs_adapter.py`
holds the knobs' and the adapter's to: no invariant id at all.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tests.helpers import INTERNAL

REPO = Path(__file__).resolve().parent.parent
MODULES = ("tasks.py", "surface.py")

# Prose: specification section numbers, decision records and module codenames, landscape and
# upstream-note ids, requirement ids no test group carries, numbered decisions, and the names of
# private places and people.
PROSE = re.compile(
    r"\b2\.\d\b|\bTG-(?:ADR|M)|\bVN-\d|\bKC\d|\bA(?:1[013-9]|[2-9]\d|\d{3,})\b"
    r"|\bdecision \d|\bstanding rule|§|\b[Vv]ault\b|\bTaylor\b|\bruling\b|\bhandoff\b"
)
# Values a user can see: the knobs' and the adapter's rule.
VALUES = re.compile(INTERNAL.pattern + r"|\bKC\d+\b|\bVN-\d+\b|\(\d\.\d\b")


def values(path: Path) -> list[tuple[int, str]]:
    """Every string literal that is not a bare statement (so not a docstring), with its line."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bare = {id(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in bare]


@pytest.mark.parametrize("module", MODULES)
def test_no_line_of_the_generators_source_cites_an_internal_reference(module: str) -> None:
    lines = (REPO / "src" / "poisson_tasks" / module).read_text(encoding="utf-8").splitlines()
    hits = [(number, line.strip()[:100]) for number, line in enumerate(lines, 1)
            if PROSE.search(line)]
    assert not hits, hits


@pytest.mark.parametrize("module", MODULES)
def test_no_value_the_generator_can_show_names_an_invariant(module: str) -> None:
    hits = [(line, text[:100]) for line, text in values(REPO / "src" / "poisson_tasks" / module)
            if VALUES.search(text)]
    assert not hits, hits


def test_the_patterns_catch_what_tasks_py_used_to_carry() -> None:
    """The control: lines and a message the module carried before, each caught; and references
    the rule keeps, each let through."""
    for old in ('"""TG-M3, task and verifier generation: `(arm, seed)` to a task bundle, with the',
                "format check in the spec's 2.3, as amended on 2026-09-11 by TG-ADR-35 and",
                "# 2.2's knob names.  TG-M2's `ArmSpec.__post_init__` is what refuses anything",
                "exercised through each model's stack at stage 0b (A16), so this generates",
                "from the label order (decision 4).  On a table too small to leave a read",
                "`ArmSpec.reference_turns` rather than copied as a number (SF9, standing rule 8)."):
        assert PROSE.search(old), old
    assert VALUES.search("verifies as 'wrong_state', not 'passed' (G4)")
    for kept in ("no clock, no RNG, no model, no network (G1, G2).",
                 "rows, with no audit field (PG-16) -- so", "E8's replay check", "A4's failure",
                 "N9 is an aggregate", "token 0.75 of the band"):
        assert not PROSE.search(kept), kept
