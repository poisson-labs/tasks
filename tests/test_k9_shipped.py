"""The knob probe's outcome in the package: the knobs it shipped and each knob's measured status.

The knob probe (spec Knobs §9) ran on gpt-5-nano and Qwen3-8B.  Its outcome as Taylor ruled it on
2026-10-14:

1. **Faults, history and shape ship**, and nothing else: `arms.SHIPPED_KNOBS` is exactly those
   three, in the probe's knob order.  The recipes follow R0's rule unchanged: a recipe is offered
   when it uses only the published cards' knobs or one of its probe knobs has shipped, and the
   arms of a knob that has not shipped are dropped.  So `error-recovery`, `long-sessions`,
   `planning` and `profile` join `first-look` and `card`; `tool-choice` waits on similarity and
   block, `reading-and-filling` on spread and arguments.
2. **Every knob stays.**  The four that did not ship keep their tasks and their arms (the kept
   digests of every knob's tasks pin that), each labelled with its measured status on each model.
3. **No knob is called a non-biter where its base could not show it.**  On a model where the
   knob's base arm's strict pass@1 is not clear of 0 and 1, a status other than "bites" is
   "cannot tell", with the base rate given.  Clear is read as the decision rule's own size,
   delta* = 0.15, from each end: a base from 0.15 to 0.85, where a change of 0.15 could show in
   either direction.  Spread's base on gpt-5-nano is 0.067.
4. **The status table is package data**, `src/poisson_tasks/knob_status.json`, read through one
   public function, `arms.knob_status()`, so the wheel carries it: each knob's status on each
   model (bites, does not bite, top easier, cannot tell) with the base arm's strict pass@1 and each
   contrast's Δ and 95% interval.  `docs/knobs-and-arms.md` states the same statuses.

The numbers are the combined outcome's (`python -m poisson_tasks.knob_probe analyse` over both
models' records), which is not in the repository.  These tests hold the file to its own rule and
to the statuses that outcome gave, not to the outcome's bytes; the vault's filing rebuilds the
file from the outcome byte for byte.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import arms, config
from poisson_tasks.arms import arm_from_id
from tests.helpers import INTERNAL

REPO = Path(__file__).resolve().parent.parent
PROBE_KNOBS = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")
SHIPPED = ("faults", "history", "shape")
OFFERED = ["first-look", "error-recovery", "long-sessions", "planning", "profile", "card"]
WAITING = {"tool-choice": ("similarity", "block"), "reading-and-filling": ("spread", "arguments")}

NANO = "gpt-5-nano-2025-08-07"
QWEN = "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218"
NAMES = {NANO: "gpt-5-nano", QWEN: "Qwen3-8B"}
BASES = {
    "similarity": "similarity:s0",
    "faults": "faults:f0",
    "history": "history:t0",
    "block": "block:k8",
    "arguments": "arguments:a2",
    "shape": "shape:w1",
    "spread": "spread:p1",
}
STATUSES = ("bites", "does not bite", "top easier", "cannot tell")
DELTA = 0.15
# The outcome with ruling 3 read in, (gpt-5-nano, Qwen3-8B).
MEASURED = {
    "similarity": ("does not bite", "cannot tell"),
    "faults": ("cannot tell", "bites"),
    "history": ("bites", "bites"),
    "block": ("cannot tell", "cannot tell"),
    "arguments": ("does not bite", "cannot tell"),
    "shape": ("does not bite", "bites"),
    "spread": ("cannot tell", "cannot tell"),
}


def knob_of(arm: str) -> str:
    return arm_from_id(arm).knob


def clear(base: float) -> bool:
    return DELTA <= base <= 1 - DELTA


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for key, item in value.items() for s in (*strings(key), *strings(item))]
    if isinstance(value, list):
        return [s for item in value for s in strings(item)]
    return []


# ---------------------------------------------------------------------------
# the shipped list and the recipes
# ---------------------------------------------------------------------------


def test_the_probe_shipped_faults_history_and_shape_and_the_recipes_follow() -> None:
    """Rulings 1 and 2.  Bugs caught: the list left empty, a fourth knob shipped, a knob listed
    twice or out of order; the recipe table built from another list than the shipped one; a
    recipe of a knob that did not ship offered, or a shipped knob's arms dropped; `init` refusing
    a recipe the list now offers."""
    assert tuple(arms.SHIPPED_KNOBS) == SHIPPED
    assert [name for name, recipe in arms.RECIPES.items() if recipe.offered] == OFFERED
    for name, waits in WAITING.items():
        recipe = arms.RECIPES[name]
        assert not recipe.offered and tuple(recipe.waiting) == waits, name
        assert tuple(recipe.arms) == () and recipe.episodes == 0, name
        with pytest.raises(config.ConfigError) as refused:
            config.config_from_init_args(["--recipe", name])
        assert refused.value.key == "measure.preset", name
    profile = arms.RECIPES["profile"]
    assert tuple(profile.waiting) == ("similarity", "block", "arguments", "spread")
    assert {knob_of(arm) for arm in profile.arms} == {"depth", *SHIPPED}
    for name in OFFERED:
        assert arms.RECIPES[name].arms, name
        made = config.config_from_init_args(["--recipe", name])
        assert made.measure.preset == name


# ---------------------------------------------------------------------------
# the status file
# ---------------------------------------------------------------------------


def test_the_status_table_is_package_data_read_through_one_public_function() -> None:
    """Ruling 4.  Bugs caught: the table written into the code rather than the package's file;
    the function not public; a caller's edit to what it returned seen by the next caller."""
    assert "knob_status" in arms.__all__
    path = REPO / "src" / "poisson_tasks" / "knob_status.json"
    assert Path(arms.__file__).resolve().parent / "knob_status.json" == path
    assert arms.knob_status() == json.loads(path.read_text(encoding="utf-8"))
    first = arms.knob_status()
    first["knobs"].clear()
    assert list(arms.knob_status()["knobs"]) == list(PROBE_KNOBS)


def test_every_probe_knob_has_its_measured_status_on_each_model_and_shipped_is_the_list() -> None:
    """Rulings 2 and 4, and the statuses the outcome gave with ruling 3 read in.  Bugs caught: a
    knob that did not ship left out of the table; a model left out; a status outside the four
    words; a knob marked shipped that is not in `SHIPPED_KNOBS`, or the other way; a status word
    edited by hand; spread's base on gpt-5-nano not the 0.067 the run measured."""
    table = arms.knob_status()
    assert list(table["models"]) == [NANO, QWEN]
    assert table["models"] == NAMES
    assert list(table["knobs"]) == list(PROBE_KNOBS)
    shipped = [knob for knob, row in table["knobs"].items() if row["shipped"]]
    assert shipped == list(arms.SHIPPED_KNOBS)
    for knob, row in table["knobs"].items():
        assert row["outcome"] == ("ships" if row["shipped"] else "does not ship"), knob
        assert list(row["models"]) == [NANO, QWEN], knob
        for model, cell in row["models"].items():
            assert cell["status"] in STATUSES, (knob, model)
            assert cell["base"]["arm"] == BASES[knob], (knob, model)
            assert 0 <= cell["base"]["strict"] <= 1, (knob, model)
        assert tuple(cell["status"] for cell in row["models"].values()) == MEASURED[knob], knob
    spread = table["knobs"]["spread"]["models"][NANO]
    assert spread["status"] == "cannot tell"
    assert spread["base"]["strict"] == pytest.approx(8 / 120, abs=5e-5)


def test_no_knob_is_called_a_non_biter_where_its_base_is_not_clear_of_0_and_1() -> None:
    """Ruling 3, and each status follows from its own numbers by spec §9.4 and §9.5.  Bugs
    caught: a knob called a non-biter (or easier at the top) on a model whose base was at the
    floor or the ceiling; "cannot tell" where the base was clear; a bite turned into "cannot
    tell"; a status that its contrasts do not give; a contrast marked as meeting the rule whose
    interval or size does not."""
    table = arms.knob_status()
    assert table["probe"]["floor"] == DELTA
    assert table["probe"]["ceiling"] == pytest.approx(1 - DELTA)
    for knob, row in table["knobs"].items():
        for model, cell in row["models"].items():
            where = (knob, model)
            contrasts = cell["contrasts"]
            assert [c["a"] for c in contrasts][:1] == [BASES[knob]], where
            for c in contrasts:
                low, high = c["interval"]
                assert low <= c["delta"] <= high, where
                assert not (c["meets"] and c["the_other_way"]), where
                if c["meets"]:
                    assert low > 0 and c["delta"] >= DELTA - 1e-9, where
                if c["the_other_way"]:
                    assert high < 0 and c["delta"] <= -DELTA + 1e-9, where
            first = contrasts[0]
            if knob == "shape":
                assert len(contrasts) == 2, where
                control = contrasts[1]
                bites = (first["meets"] or first["the_other_way"]) and not (
                    control["meets"] or control["the_other_way"]
                )
                easier = False
            else:
                assert len(contrasts) == (2 if knob in ("faults", "block", "arguments") else 1)
                bites = all(c["meets"] for c in contrasts)
                easier = not bites and first["the_other_way"]
            measured = "bites" if bites else "top easier" if easier else "does not bite"
            base = cell["base"]["strict"]
            expected = measured if bites or clear(base) else "cannot tell"
            assert cell["status"] == expected, (where, base, measured)


def test_each_knobs_line_says_its_statuses_in_plain_words() -> None:
    """The words a reader sees.  Bugs caught: a line that calls a knob a non-biter on a model
    where its status is "cannot tell", or names no base rate there; a line that names a private
    place, person or internal id."""
    table = arms.knob_status()
    for knob, row in table["knobs"].items():
        says = row["says"]
        assert says.startswith(row["outcome"] + ": "), knob
        for model, cell in row["models"].items():
            name = NAMES[model]
            phrase = {
                "bites": f"bites on {name}",
                "does not bite": f"does not bite on {name}",
                "top easier": f"the top is easier on {name}",
                "cannot tell": f"cannot tell on {name} (its base passed "
                f"{cell['base']['strict']:.3f})",
            }[cell["status"]]
            assert phrase in says, (knob, model, says)
    hits = [text for text in strings(table) if INTERNAL.search(text)]
    assert not hits, hits


def test_the_knobs_page_states_each_knobs_status_on_each_model() -> None:
    """Ruling 2's label where a reader looks for a knob.  Bugs caught: the page's table left out
    of step with the file; a knob that did not ship missing from it; a "cannot tell" cell with no
    base rate."""
    page = (REPO / "docs" / "knobs-and-arms.md").read_text(encoding="utf-8")
    table = arms.knob_status()
    for knob, row in table["knobs"].items():
        found = re.findall(rf"^\| `{knob}` \|(.*)\|$", page, flags=re.MULTILINE)
        rows = [cells for cells in found if cells.split("|")[0].strip() in ("yes", "no")]
        assert len(rows) == 1, (knob, found)
        cells = [cell.strip() for cell in rows[0].split("|")]
        assert cells[0] == ("yes" if row["shipped"] else "no"), (knob, cells)
        for cell_text, cell in zip(cells[1:3], row["models"].values(), strict=True):
            assert cell_text.startswith(cell["status"]), (knob, cell_text)
            if cell["status"] == "cannot tell":
                assert f"{cell['base']['strict']:.3f}" in cell_text, (knob, cell_text)
