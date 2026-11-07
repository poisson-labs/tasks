"""#35, what a run's card says: only what the run recorded, and why where it recorded nothing.

Four leftovers of the wording, on the card of a run of a plan and not on the published cards:

- **concurrency**: the card said *Concurrency of this run: not recorded* beside every time figure
  and in its provenance list.  The figure is in the run's own `run.log` (one line for each part of
  the run, `run of N episodes, K kept, at concurrency C`), and the card does not read it, so the
  card now says where the figure is;
- **budget**: the provenance list said *budget: not recorded*.  A run of a plan has no budget;
  it stops at the spend or token cap it was given, and no file of the run folder records the
  cap.  The card says so;
- **the resumed run**: every card carried the paragraph *A resumed run is the same run in this
  sense and no other*, the run that was never interrupted among them.  A run's card carries it
  when the run was resumed, and the published cards, which are not a run of a plan, keep it;
- **intent**: an own-tools card says that without an intent for every tool choosing a tool was
  partly a word match, and used the word with no meaning.  The line now says what an intent is.

And the estimate `init` shows before it asks for the cap, which on your own tools was *at the
published card's usage*, the built-in tasks' card's: it now says so, and that it is scaled to
your tools' size.  (The estimate row of the plan `run` prints says the same thing in another
place, `docs/own-tools.md` shows it in a block the docs check compares, and it is not changed
here.)

**The published cards keep their bytes.**  A run of a plan is told from the published cards by
what only a plan's provenance holds, the arms (`Provenance.arms`); the published artifacts hold
none, so their rendering is the one it was, which `test_fd4_pending_published_page` holds to its
SHA-256, and the controls below hold to the sentences this change leaves alone.  A run card's
document is still the published renderer's document with the claims inserted (`test_fd4_10`): the
same artifact is rendered both ways, so the two stay in step.
"""

from __future__ import annotations

import pytest

from tests.fd3_support import calibration, needs_uv
from tests.fd4_support import RunFolders, fd4_runs, shipped_artifacts
from tests.test_fd4_card import card
from tests.test_o2_card import artifact as own_artifact
from tests.test_o2_card import tools_block

__all__ = ["fd4_runs"]

RESUMED = "A resumed run is the same run in this sense and no other."


def _lines(document: str, start: str) -> list[str]:
    return [line for line in document.splitlines() if line.startswith(start)]


@needs_uv
@pytest.mark.parametrize("scenario", ["first_look", "failed_once", "failed_once_resumed"])
def test_fx35_1_a_run_card_says_where_its_concurrency_is_not_that_it_was_not_recorded(
    fd4_runs: RunFolders, scenario: str
) -> None:
    """Red before the change: every one of these lines says *not recorded*."""
    document = card(fd4_runs[scenario]).document
    assert "oncurrency of this run: not recorded" not in document
    assert "- concurrency: not recorded" not in document
    body = _lines(document, "Concurrency of this run:")
    assert len(body) >= 3, body
    for line in body:
        assert "run.log" in line and "each part of the run" in line, line
    (item,) = _lines(document, "- concurrency:")
    assert "run.log" in item, item


@needs_uv
@pytest.mark.parametrize("scenario", ["first_look", "failed_once_resumed"])
def test_fx35_2_a_run_card_says_why_it_has_no_budget(fd4_runs: RunFolders, scenario: str) -> None:
    """Red before the change: the line is *budget: not recorded* and nothing more.  The words
    *not recorded* stay in it, since `test_fd4_2_a_runs_card_records_no_budget_it_did_not_have`
    holds that a run's card prints its missing budget as not recorded; what follows them is the
    reason."""
    document = card(fd4_runs[scenario]).document
    (item,) = _lines(document, "- budget:")
    assert item.startswith("- budget: not recorded, because "), item
    assert "cap" in item and "run folder" in item, item
    assert "None" not in item, item


@needs_uv
@pytest.mark.parametrize("scenario", ["first_look", "failed_once"])
def test_fx35_3_a_run_that_was_never_resumed_has_no_resumed_paragraph(
    fd4_runs: RunFolders, scenario: str
) -> None:
    """Red before the change: every card has it.  `failed_once` is the run before its resume:
    one episode failed, and nothing has run it again."""
    document = card(fd4_runs[scenario]).document
    assert RESUMED not in document


@needs_uv
def test_fx35_4_a_run_that_was_resumed_keeps_the_paragraph(fd4_runs: RunFolders) -> None:
    """A control: green before the change, and the change keeps it green."""
    document = card(fd4_runs["failed_once_resumed"]).document
    assert RESUMED in document


def test_fx35_5_the_published_cards_keep_every_sentence_this_change_leaves_alone() -> None:
    """A control: green before the change.  The published page is the published renderer's
    document, held by SHA-256 elsewhere; this says in words what must stay in it."""
    cal = calibration()
    found = list(shipped_artifacts())
    assert len(found) == 2
    for published in found:
        document = cal.render_document(published)
        assert RESUMED in document
        assert document.count("Concurrency of this run: not recorded.") >= 3
        assert "- concurrency: not recorded" in document
        (budget,) = _lines(document, "- budget:")
        assert "tokens" in budget and "not recorded" not in budget, budget


def test_fx35_6_a_published_artifact_is_not_a_run_of_a_plan() -> None:
    """What the change depends on to leave the published cards alone: no published artifact
    holds the arms a plan's provenance does.  A control, green before the change."""
    for published in shipped_artifacts():
        assert published.provenance.arms is None


def test_fx35_7_the_own_tools_line_on_a_runs_card_says_what_an_intent_is() -> None:
    """Red before the change: the line uses the word and says nothing of it.  The artifact is the
    one `tests/test_o2_card.py` builds, with the arms a plan's provenance holds."""
    import dataclasses

    cal = calibration()
    names = ["get_order", "search_orders", "refund_order", "notify_customer", "list_channels"]
    plain = own_artifact(tools=tools_block(intents=names[:4]))
    run = dataclasses.replace(
        plain, provenance=dataclasses.replace(plain.provenance, arms=["depth:d1", "depth:d2"]))
    (line,) = [line for line in cal.card_claims(run).not_claimed if "word match" in line]
    assert "an intent is" in line and "[own.intents]" in line, line
    assert "in place of its description" in line, line
    assert "\n" not in line
    assert line in cal.render_document(run, claims=True)


def test_fx35_7b_an_artifact_with_no_plan_in_it_says_the_line_as_it_always_did() -> None:
    """A control: green before the change, and what keeps `test_bd_card_and_experimental`'s digest
    of a 0.3.x own-tools card where it is."""
    cal = calibration()
    names = ["get_order", "search_orders", "refund_order", "notify_customer", "list_channels"]
    artifact = own_artifact(tools=tools_block(intents=names[:4]))
    assert artifact.provenance.arms is None
    (line,) = [line for line in cal.card_claims(artifact).not_claimed if "word match" in line]
    assert line == (
        "Without an intent for every tool, choosing a tool was partly a word match with its "
        "description."
    )


def test_fx35_8_the_cap_question_on_your_tools_says_the_estimate_is_the_built_in_cards_scaled() -> None:
    """Red before the change: `_cap_hint` does not exist; the words were *at the published
    card's usage* for a plan on your tools as on the built-in tasks."""
    from types import SimpleNamespace

    from poisson_tasks.cli._init import _cap_hint

    estimate = SimpleNamespace(episodes=40)
    built_in = _cap_hint(estimate, 0.0153, own=False)
    own = _cap_hint(estimate, 0.0153, own=True)
    assert built_in == (
        "This plan: 40 episodes, about $0.02 at the published card's usage. The cap is what holds."
    )
    assert "built-in tasks" in own and "scaled" in own and "your tools" in own, own
    assert "at the published card's usage" not in own, own
    assert own.startswith("This plan: 40 episodes, about $0.02")
    assert own.endswith("The cap is what holds.")


@needs_uv
def test_fx35_9_the_run_log_has_the_line_the_card_points_at(fd4_runs: RunFolders) -> None:
    """A guard for what the card now says of its concurrency: that `run.log` holds, for each part
    of the run, how many episodes ran at once.  Green by construction once the runs exist; it
    holds the card's sentence to the log.  `failed_once_resumed` is two parts of one run, so two
    lines, each with the scenario's concurrency (4)."""
    import re

    from tests.fd4_support import SCENARIOS

    made = fd4_runs["failed_once_resumed"]
    log = (made.folder / "run.log").read_text(encoding="utf-8")
    found = re.findall(r"run of \d+ episodes, \d+ kept, at concurrency (\d+)", log)
    assert found == [str(SCENARIOS["failed_once"].concurrency)] * 2, log
