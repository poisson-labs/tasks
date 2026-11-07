"""#35, the estimate row of the plan `run` prints, on your own tools.

The row said *from the published gpt-5-nano card for this model* for a plan on the user's own
tools as it does on the built-in tasks.  On the built-in tasks that is the whole story: the
estimate is the card's own per-arm means.  On your own tools it is not: the published card
measured the built-in tasks, and the estimate takes that card's mean usage per model call, times
the reference turns of each of your tasks, with the prompt and cached input scaled by the size of
your tool block over the built-in block's (`runs._own_estimate`, decided 2026-10-13).  So the row
now says where the figure comes from, and that it is scaled, in the words `init` uses for its
cap question (`tests/test_fx_card_wording.py`, test 8).

What each test holds:

- the row on your own tools says the card's per-call usage on the built-in tasks, scaled to your
  tools' size, for a model the card measured and for one it did not (the second keeps the
  warning that the model's usage will differ and the cap is what holds);
- the row on the built-in tasks is the words it always was (a control: green before the change,
  and `tests/test_fd6_wheel.py` holds the same line);
- the plan's `--json` still names the card (`source`) and whether it is the model's
  (`same_model`): the words changed, the facts did not.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from poisson_tasks import runs
from tests.test_o2_cli import invoke, work
from tests.test_o2d_b2 import _settled

__all__ = ["work"]

OWN = "from the published gpt-5-nano card for this model: its per-call usage on the built-in tasks, scaled to your tools' size"


def _row(out: str) -> str:
    (line,) = [line for line in out.splitlines() if line.strip().startswith("estimate")]
    return " ".join(line.split())


def test_fx35_10_the_estimate_row_on_your_own_tools_says_it_is_scaled_from_the_built_in_card(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the change: the row is the built-in one, *from the published gpt-5-nano card
    for this model*, and says nothing of the tools or the scaling."""
    _settled(work, monkeypatch)
    dry = invoke(["run", "--dry-run", "--offline"], monkeypatch)
    assert dry.code == 0 and "your tools" in dry.out, dry
    assert _row(dry.out) == "estimate " + OWN, _row(dry.out)


def test_fx35_11_the_estimate_row_on_the_built_in_tasks_is_the_words_it_always_was(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A control: green before the change, and the change keeps it green."""
    made = invoke(["init", "--yes", "--no-fetch", "--no-check-key"], monkeypatch)
    assert made.code == 0, made
    dry = invoke(["run", "--dry-run", "--offline"], monkeypatch)
    assert dry.code == 0 and "your tools" not in dry.out, dry
    assert _row(dry.out) == "estimate from the published gpt-5-nano card for this model"


@pytest.mark.parametrize(("own", "same", "expected"), [
    (False, True, "from the published gpt-5-nano card for this model"),
    (False, False, "from the published gpt-5-nano card; your model's usage will differ, and the "
                   "cap is what holds"),
    (True, True, OWN),
    (True, False, "from the published gpt-5-nano card: its per-call usage on the built-in tasks, "
                  "scaled to your tools' size; your model's usage will differ, and the cap is "
                  "what holds"),
], ids=["built-in, the model's card", "built-in, another model's", "own tools, the model's",
        "own tools, another model's"])
def test_fx35_12_the_estimate_words_for_each_case(own: bool, same: bool, expected: str) -> None:
    """Red before the change: `_estimate_words` does not exist (the two built-in cases are the
    words the row had, held from outside by tests 10 and 11 and by `test_fd6_wheel`)."""
    from poisson_tasks.cli._run import _estimate_words

    found = runs.Estimate(episodes=4, calls_min=4, calls_expected=4.0, calls_at_cap=128,
                          tokens_expected=100.0, dollars_expected=0.01, source="gpt-5-nano",
                          same_model=same)
    assert _estimate_words(found, own=own) == expected


def test_fx35_13_the_plans_json_names_the_card_as_it_did(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A control: green before the change.  The estimate's facts are the same; the row's words
    are the only thing that moves."""
    _settled(work, monkeypatch)
    dry = invoke(["run", "--dry-run", "--offline", "--json"], monkeypatch)
    assert dry.code == 0, dry
    estimate = json.loads(dry.out)["estimate"]
    assert estimate["source"] == "gpt-5-nano" and estimate["same_model"] is True, estimate
