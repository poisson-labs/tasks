"""What a reader of the calibration card, the Colab driver or the taskset sees carries no
reference they cannot look up.

The card printed tags such as `(R10)`, `(R13)`, `(X4)`, `(CAL24)` and `(R9)`: identifiers of
design decisions and test groups that live nowhere a user can open.  Refusals did the same
("a label 2.3 defines", "A21's distinct-instance rule", "(CAL12)", "(N18)"), and the Colab
driver's help and messages said "the files the vault keeps", "(R11)", "comparable (R10)" and
"the next run is a ruling".  Every such string now says what it means in words.

The check reads every string a user can meet: each committed card as rendered, every string
literal in these modules that is not a docstring (help text, refusals, rendered text), and
every cell of the model B notebook.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from poisson_tasks import calibration as cal

REPO = Path(__file__).resolve().parent.parent

# Identifiers of internal decisions and test groups, spec section numbers, and the names of
# private places and people.  Whole words only, so a model name or a version number does not
# trip it.
INTERNAL = re.compile(
    r"\b(?:R(?:[1-9]|1[0-7])|CAL\d+|MP\d+|[XNGAE]\d+)\b"
    r"|\b2\.\d defines\b|§|\bTG-(?:ADR|M)\d*|\b[Vv]ault\b|\bTaylor\b|\bruling\b|\bhandoff\b"
)

MODULES = ["calibration.py", "calibration_run.py", "export.py", "taskset.py", "__init__.py"]


def _reader_strings(path: Path) -> list[tuple[int, str]]:
    """Every string literal that is not a bare statement (so not a docstring), with its line:
    the literal parts of f-strings included."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bare = {id(node.value) for node in ast.walk(tree)
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in bare:
            found.append((node.lineno, node.value))
    return found


@pytest.mark.parametrize("module", MODULES)
def test_no_string_a_user_can_meet_names_an_internal_reference(module: str) -> None:
    path = REPO / "src" / "poisson_tasks" / module
    hits = [(line, text[:100]) for line, text in _reader_strings(path) if INTERNAL.search(text)]
    assert not hits, hits


def test_the_notebook_says_nothing_a_reader_cannot_look_up() -> None:
    notebook = json.loads((REPO / "notebooks" / "calibration_model_b.ipynb").read_text())
    hits = [line for cell in notebook["cells"] for line in cell["source"]
            if INTERNAL.search(line)]
    assert not hits, hits


@pytest.mark.parametrize("folder", ["gpt-5-nano-2025-08-07", "qwen3-8b-b968826d"])
def test_each_committed_card_renders_in_plain_words(folder: str) -> None:
    root = REPO / "calibration" / folder
    stored = json.loads((root / "artifact.json").read_text())
    cells: dict[tuple[str, str], list[cal.EpisodeRecord]] = {}
    for record in cal.read_records(root / "episodes.jsonl"):
        cells.setdefault((record.arm_id, record.model), []).append(record)
    tallies_path = root / "tallies.json"
    tallies = json.loads(tallies_path.read_text()) if tallies_path.exists() else {}
    artifact = cal.build_artifact(cells, cal.Provenance(**stored["provenance"]),
                                  tally={key: tallies.get(key[0], {}) for key in cells})
    document = cal.render_document(artifact)
    hits = [line for line in document.splitlines() if INTERNAL.search(line)]
    assert not hits, hits


def test_the_pattern_catches_what_the_card_used_to_print() -> None:
    """The control: every tag and phrase removed would have been caught."""
    for old in ("no other (R13).", "with a reply (X4).", "at all (CAL24),", "arms (R9).",
                "a label 2.3 defines", "A21's distinct-instance rule", "the files the vault keeps",
                "the next run is a ruling (Qwen3-14B)", "(N18)"):
        assert INTERNAL.search(old), old
    for fine in ("Qwen/Qwen3-8B@b968826d", "vLLM 0.29.0", "pass@5", "gpt-5-nano-2025-08-07",
                 "depth:d2+h5", "distractor:r0+len(r8)@k16", "delta* = 0.15"):
        assert not INTERNAL.search(fine), fine


def test_a_refusal_still_names_what_it_refused() -> None:
    """Plain words, not less information: the closed-vocabulary refusal still lists the
    vocabulary and names the bad label."""
    with pytest.raises(ValueError) as caught:
        cal.EpisodeRecord(task_id="t", arm_id="depth:d1", model="m", seed=1, attempt=0,
                          strict=False, leaky=False, label="bogus", turns=1, sampled_calls=0,
                          prompt_tokens=0, cached_input_tokens=0, completion_tokens=0,
                          reasoning_tokens=0)
    message = str(caught.value)
    assert "'bogus'" in message
    assert all(label in message for label in cal.OUTCOME_LABELS)
