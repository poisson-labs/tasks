"""The refusals and pin-ledger text that `knobs.py` and `adapter.py` show a user say what they
mean in words.

They cited references a reader of this repository cannot look up:
- refusals: "an arm id 2.2 defines", "(N18)", "(N18: one for every model)", "(G12)", "(N15)",
  "N17 makes it the largest", "(A12)", "(A3)";
- the ledger's texts: "(2.3, TG-ADR-38)", "(TG-ADR-37)", "(A14)", "E2, over" and "by E10".

The check reads every string literal in the two modules that is not a docstring, with the
calibration module's pattern widened by three kinds of reference these modules carried.  Three things are allowed, each for a reason:
- a ledger row id on its own (`"N3"`): the rows N1 to N13 are the ledger's public names, and
  `docs/knobs-and-arms.md` lists every one;
- "N18" in N10's held text: the frozen test `test_n18_1` requires it there, as the ledger's
  pointer to the serving pin, and the text says in words what that pin covers;
- N10's and N13's `unmeasured` reasons: they are written into every task bundle, which the
  task id hashes, so rewording them moves every task id and stales both calibration cards.
  They change with the next deliberate generator change, not before.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks.knobs import pin_ledger
from poisson_tasks.tasks import generate

from tests.test_cal_plain_words import INTERNAL

REPO = Path(__file__).resolve().parent.parent
ROW_ID = re.compile(r"N(?:[1-9]|1[0-3])")
# The calibration modules' pattern, and three more kinds of reference these two modules
# carried: a landscape check's id (KC3), an upstream note's id (VN-7) and a bare
# specification section, "(2.3".
PATTERN = re.compile(INTERNAL.pattern + r"|\bKC\d+\b|\bVN-\d+\b|\(\d\.\d\b")


def _strings(path: Path) -> list[tuple[int, str]]:
    """Every string literal that is not a bare statement (so not a docstring), with its line;
    the literal parts of f-strings included."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bare = {id(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
    return [(node.lineno, node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in bare]


def _bundle_reasons() -> set[str]:
    """The `unmeasured` reasons a generated bundle carries, read off a real one."""
    bundle = generate(cal.arm_specs()[0], cal.seed_list()[0])
    return set(bundle.pins.unmeasured.values())


def _n10_held() -> str:
    return next(row.held for row in pin_ledger("depth") if row.row_id == "N10")


def test_the_rows_allowed_by_name_are_the_ones_the_docs_list() -> None:
    """The row-id allowance is only as good as the docs: every row the ledger has is named in
    `docs/knobs-and-arms.md`."""
    docs = (REPO / "docs" / "knobs-and-arms.md").read_text(encoding="utf-8")
    rows = {row.row_id for knob in ("depth", "distractor") for row in pin_ledger(knob)}
    assert rows and all(ROW_ID.fullmatch(row) for row in rows), rows
    assert all(re.search(rf"\b{row}\b", docs) for row in rows)


@pytest.mark.parametrize("module", ["knobs.py", "adapter.py"])
def test_no_refusal_or_ledger_text_names_an_internal_reference(module: str) -> None:
    reasons, n10_held = _bundle_reasons(), _n10_held()
    hits = []
    for line, text in _strings(REPO / "src" / "poisson_tasks" / module):
        if ROW_ID.fullmatch(text) or text in reasons:
            continue
        checked = text.replace("N18", "") if text == n10_held else text
        if PATTERN.search(checked):
            hits.append((line, text[:100]))
    assert not hits, hits


def test_the_pattern_catches_what_the_two_modules_used_to_print() -> None:
    """The control: every reference removed would have been caught, and the two bundle
    reasons, which stay, are caught too (so their allowance is doing work)."""
    for old in ("is not an arm id 2.2 defines", "and not a commit (N18)",
                "(N18: one for every model)", "eval only (G12)", "pre-registration error (N15)",
                "but N17 makes it the largest", "one loop in another (A12)", "breaks pairing (A3)",
                "(2.3, TG-ADR-38)", "against this table (TG-ADR-37)", "The serving pin (A14)",
                "E2, over the bundle's", "inside `engine_hash` by E10"):
        assert PATTERN.search(old), old
    reasons = _bundle_reasons()
    assert len(reasons) == 2 and all(PATTERN.search(reason) for reason in reasons), reasons
