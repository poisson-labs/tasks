"""What a card says it means and what it does not claim, frozen as tests: `calibration.card_claims`.

The invariant: `card_claims(a).flags` holds exactly the conditions that apply, and the tests check
the flags, not the words.  With the decision the card's build was given, a card for a plan no
published card covers says so plainly.

Shapes decided here, where the design leaves them open
------------------------------------------------------

**1. The flags are seven names**, one per condition a not-claimed line depends on:
- `small_sample`: fewer tasks per level than the published cards have (the design: "fewer than the
  published sixty"; read off the shipped cards, so it follows them);
- `not_comparable`: the card cannot be read beside the published cards, because it was not
  measured the same way as one of them (`comparable` names a field); the line "says whether it
  was", so a card without the flag is one that can;
- `self_served`: its model is served by the user (`serving` kind `self_served`), so how it was
  served is not pinned;
- `distractor`: it holds a cell of the distractor knob, which is experimental;
- `stale`: its generator hash is not the one the package gives today (the published cards'
  staleness, `tests/test_k1_calibration.py`);
- `resumed`: some of its attempts were made by a later run of the folder than others, so a
  resumed attempt is a fresh one;
- `not_covered`: no published card holds a cell of any of its arms (the decision above).
The lines a card always carries (one model's result on these tasks; it ranks nothing) have no
flag.

**2. The meaning paragraph names the model, where it was served (the endpoint's host and port for
a hosted model, the endpoint for one the user serves), and how many tasks and attempts per level,
as numerals** (read with the model, the endpoint and the arm ids taken out, so a "3" in
`depth:d3` does not count).

**3. Every line a user reads is plain**: one line, no internal identifier
(`tests.helpers.INTERNAL`), and no two lines alike.

Whether a card was resumed is known by construction here: only `failed_once_resumed` had a second
run that recorded episodes.  A first Ctrl-C between two arms leaves a folder no file can tell
from one run, and no line of that card would differ: no attempt was made twice.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

import pytest

from tests.fd3_support import calibration, needs_uv
from tests.fd4_support import (
    RunFolders,
    differing,
    fd4_runs,
    one_line,
    package_generator_hash,
    shipped_artifacts,
    shipped_folders,
)
from tests.helpers import INTERNAL

__all__ = ["fd4_runs"]

RUN_CARDS = ["first_look", "failed_once", "failed_once_resumed", "cut", "partial", "distractor",
             "self_served", "generator_0", "uncovered"]
FLAGS = frozenset({"small_sample", "not_comparable", "self_served", "distractor", "stale",
                   "resumed", "not_covered"})


def claims_card(made: Any) -> Any:
    return calibration().card_from_run(made.folder).artifact


def knob(arm: str) -> str:
    return arm.split(":", 1)[0]


def expected_flags(artifact: Any, *, resumed: bool) -> set[str]:
    prov = artifact.provenance
    shipped = shipped_artifacts()
    arms = {cell["arm_id"] for cell in artifact.cells}
    published_arms = {cell["arm_id"] for other in shipped for cell in other.cells}
    out = set()
    if prov.S < min(other.provenance.S for other in shipped):
        out.add("small_sample")
    if any(differing(prov, other.provenance) for other in shipped):
        out.add("not_comparable")
    if any(dict(entry).get("kind") == "self_served" for entry in prov.serving.values()):
        out.add("self_served")
    if any(knob(arm) == "distractor" for arm in arms):
        out.add("distractor")
    if prov.generator_hash != package_generator_hash():
        out.add("stale")
    if resumed:
        out.add("resumed")
    if not arms & published_arms:
        out.add("not_covered")
    return out


@needs_uv
@pytest.mark.parametrize("scenario", RUN_CARDS)
def test_fd4_4_a_runs_claims_flag_exactly_the_conditions_that_apply(
    fd4_runs: RunFolders, scenario: str
) -> None:
    """Each condition is computed here from the card's own provenance and cells and the shipped
    cards' files."""
    artifact = calibration().card_from_run(fd4_runs[scenario].folder).artifact
    claims = calibration().card_claims(artifact)
    expected = expected_flags(artifact, resumed=scenario == "failed_once_resumed")
    assert set(claims.flags) == expected
    assert set(claims.flags) <= FLAGS


@pytest.mark.parametrize("index", range(len(shipped_folders())),
                         ids=[folder.name for folder in shipped_folders()])
def test_fd4_4_a_published_cards_claims_flag_exactly_the_conditions_that_apply(
    index: int,
) -> None:
    """The published cards: comparable with each other, measured over the published tasks, each
    with distractor cells; locally served is not served by the user; stale or not by the hashes."""
    artifact = shipped_artifacts()[index]
    claims = calibration().card_claims(artifact)
    assert set(claims.flags) == expected_flags(artifact, resumed=False)


@needs_uv
def test_fd4_4_every_condition_is_flagged_and_changes_what_the_card_says(
    fd4_runs: RunFolders,
) -> None:
    """The scenarios between them raise every flag, so no flag above is checked only absent; and
    two cards whose flags differ do not say the same things they do not claim, so a line follows
    its condition.  No line's words are read."""
    claims = {scenario: calibration().card_claims(
        calibration().card_from_run(fd4_runs[scenario].folder).artifact) for scenario in RUN_CARDS}
    assert set().union(*(set(c.flags) for c in claims.values())) == FLAGS
    for first in RUN_CARDS:
        for second in RUN_CARDS:
            if set(claims[first].flags) != set(claims[second].flags):
                assert set(claims[first].not_claimed) != set(claims[second].not_claimed), (
                    first, second)


@needs_uv
@pytest.mark.parametrize("scenario", ["first_look", "self_served"])
def test_fd4_4_the_meaning_names_the_model_where_it_ran_and_the_design(
    fd4_runs: RunFolders, scenario: str
) -> None:
    made = fd4_runs[scenario]
    claims = calibration().card_from_run(made.folder).claims
    meaning = claims.meaning
    assert claims_card(made).cells
    assert "\n\n" not in meaning.strip()
    assert made.plan.model.name in meaning
    if made.plan.model.provider in ("ollama", "vllm"):
        assert made.plan.model.base_url in meaning
    else:
        assert urllib.parse.urlsplit(made.plan.model.base_url).netloc in meaning
    rest = meaning
    for known in (made.plan.model.name, made.plan.model.base_url,
                  urllib.parse.urlsplit(made.plan.model.base_url).netloc,
                  *(cell["arm_id"] for cell in claims_card(made).cells)):
        rest = rest.replace(known, " ")
    for number in (len(made.plan.seeds), made.plan.attempts):
        assert re.search(rf"(?<![\w.]){number}(?![\w.])", rest), number


@needs_uv
def test_fd4_4_every_claim_is_one_plain_line(fd4_runs: RunFolders) -> None:
    artifacts = [calibration().card_from_run(fd4_runs[name].folder).artifact
                 for name in RUN_CARDS]
    for artifact in [*artifacts, *shipped_artifacts()]:
        claims = calibration().card_claims(artifact)
        assert not INTERNAL.search(claims.meaning), claims.meaning
        assert len(set(claims.not_claimed)) == len(claims.not_claimed)
        for line in claims.not_claimed:
            assert one_line(line), line
            assert not INTERNAL.search(line), line
