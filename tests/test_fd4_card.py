"""A run's card, frozen as tests: `calibration.card_from_run` and `calibration.card_verdict`.

The invariants are FD4.2, FD4.3, FD4.8, FD4.9, FD4.10 and FD4.12 of the front door's plan (spec
§9.1 to §9.5), with the rulings that reach the card:
- **a run whose every episode ran and one failed is resumable, not complete** (FD3 Session A's
  yes/no 2, ruled 2026-10-05), and its tally keeps the failure; so its card says what is owed and
  never reads as a finished result;
- **an episode the cap cut short is not a failure** (FD3 Session A's yes/no 4, ruled 2026-10-05):
  it is owed again, and the card counts no instrument failure for it;
- **the cost and time columns already on the published cards stay as they are**: a run's card
  carries the published renderer's every line, the claims block inserted and nothing changed.

Every folder is made by the run engine against the fixture model (`tests/fd4_support.py`).

Shapes decided here, where the spec leaves them open
----------------------------------------------------

**1. `card_from_run(folder, *, serving=None)` returns a `RunCard`**: `records` (every arm's
`records_from_run`, in the plan's arm order), `tally` (per arm id, the instrument tally the arm's
folder kept, `{}` for an arm with none), and, unless the verdict refuses, `artifact`, `document`
and `claims`; a refused card has `None` for those three, because nothing but the records may be
written for it (spec §4.4).  `card_from_run` writes nothing and opens no socket: writing `card/`
is the command's (FD5).

**2. The plan is read from the folder's `plan.json`**, the model's prices with it; the card is
measured under `Provenance.for_plan` of that plan.  A priced plan's rates are its price and the
rates' date its `read_on`.  A model of the `ollama` or `vllm` provider is `self_served` at the
plan's endpoint, with what `serving` (a `providers.server_facts` mapping) says the server
reported, and nothing reported when `serving` is not given: the folder holds no server facts, and
the card must not open a socket to read them (CAL19).  Any other model is `hosted` at the
endpoint's host and port.  When and whether the command reads the server's facts is FD5's.

**3. `CardVerdict`** has `word` (`"ok"` or `"refused"`), `model`, `partial`, `owed`, `incomplete`,
`not_run` and `refused`.  `owed` is every attempt the design asks for that the card holds no
scored record of: for a folder the run engine left, exactly what a resume would run.  `partial`
is `owed > 0`.  A cell is marked incomplete when it holds fewer scored attempts than its design,
for any reason: a task not reached, or an attempt that failed and was not run again.  An arm with
no recorded episode has no cell, so no figure, and is listed in `not_run`; the document names it
and prints no row for it.  `refused` is `(arm id, gate)` with gate `"instrument"` or
`"no_call"`.

**4. `card_verdict(artifact)` judges an artifact by its own cells and provenance**, so a card read
back later says what its first line said: it gives the verdict `card_from_run` gave for the same
artifact, and it refuses an artifact whose cell is over its own gate (an artifact written by
something else, for `card --check`, by the shares the cells already carry).  `card --check`
recomputes "an existing card folder, or a calibration bundle `.zip`" (spec §4.4), and neither
holds the run's `plan.json`; so what a card needs to say what it says (the arms the plan asked
for, whether the run was resumed) is carried in its artifact, which recomputes from its records
and its own stored provenance and tally, and its incomplete flags count scored attempts.

**5. The server facts a card records are its run's server's**: given facts whose endpoint is not
the plan's are refused in one line.

**6. Not a run folder, or a run that recorded nothing**, is a `ValueError` of one line naming the
folder (spec §4.4's exit 1).  A run whose episodes all failed is not empty: it is refused.

**7. The card's dollars are its scored attempts'** (the published cards' rule); the ledger holds
what the run paid beyond them.  The plan's FD4.12 says the two are equal, which holds only when
every paid episode was scored: reported as a defect in the plan.

`test_fd4_9_a_field_declared_not_sent_is_on_the_card_as_not_sent` is green by construction after
its first assertion (the existing renderer prints a declared field as it is); its first assertion,
the card's decoding is the plan's as declared, is what it holds.

Not covered here, and named for FD5's Session A: the verdict lines' words and layout (spec §9.3),
the files `card` writes and their names (a card folder needs its tally beside its records for
`--check` to recompute it), what it writes for a refused card, `--print`, `--check`'s exit 4, and
the exit codes.
"""

from __future__ import annotations

import copy
import dataclasses
import re
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import FakeServer, connections, network_guard
from tests.fd3_support import arm_dir, call_dollars, calibration, needs_uv
from tests.fd4_support import (
    NOT_SENT,
    Made,
    RunFolders,
    cells_by_arm,
    designed,
    fd4_runs,
    kept,
    ledger,
    one_line,
    rebuilt_from_card,
    recorded,
    scored_calls,
    tallied,
    tree,
)

__all__ = ["fd4_runs"]

pytestmark = needs_uv


def card(made: Made, **kwargs: Any) -> Any:
    return calibration().card_from_run(made.folder, **kwargs)


def arm_ids(made: Made) -> list[str]:
    from poisson_tasks.knobs import arm_id

    return [arm_id(spec) for spec in made.plan.arms]


def figure_rows(document: str, arm: str) -> list[str]:
    """The table rows of a document for `arm` that print a figure (a rate or a share)."""
    rows = re.findall(r"^\| `" + re.escape(arm) + r"` \|.*$", document, flags=re.M)
    return [row for row in rows if re.search(r"\b\d+\.\d{3}\b", row)]


# ---------------------------------------------------------------------------
# the verdict (FD4.3) and the two rulings
# ---------------------------------------------------------------------------


def test_fd4_3_a_finished_run_is_an_ok_card_with_nothing_owed(fd4_runs: RunFolders) -> None:
    """The control for every partial and refused card below.  Measured under the plan's own
    design, no cell of a finished first look is incomplete, though it has far fewer tasks than
    the published sixty."""
    made = fd4_runs["first_look"]
    assert made.result.verdict == "done" and made.result.episodes_owed == 0
    built = card(made)
    verdict = built.verdict
    assert (verdict.word, verdict.partial, verdict.owed) == ("ok", False, 0)
    assert (verdict.incomplete, verdict.not_run, verdict.refused) == ((), (), ())
    assert verdict.model == made.plan.model.name
    cells = cells_by_arm(built.artifact)
    assert sorted(cells) == sorted(arm_ids(made))
    for cell in cells.values():
        assert cell["incomplete"] is False
        assert cell["episodes_scored"] == designed(made)
    assert calibration().card_verdict(built.artifact) == verdict


def test_fd4_3_a_run_with_a_failed_episode_is_a_partial_card_that_says_what_is_owed(
    fd4_runs: RunFolders,
) -> None:
    """The ruling: every episode ran and one failed, so the folder is resumed, not complete.  The
    card is not refused (one failure in 52 attempts is under the instrument threshold), and it
    must not read as finished: it is partial, owes the one attempt, marks the cell incomplete,
    and counts the failure."""
    made = fd4_runs["failed_once"]
    (arm,) = arm_ids(made)
    assert made.result.verdict == "done"
    assert recorded(made) == {arm: designed(made)}
    assert kept(made) == {arm: designed(made) - 1}
    assert tallied(made) == {arm: {"api_error": 1}}
    from tests.fd3_support import runs

    assert runs().find_run(made.plan, made.folder.parent).status == "resume"

    built = card(made)
    verdict = built.verdict
    assert verdict.word == "ok"
    assert (verdict.partial, verdict.owed) == (True, 1) == (True, made.result.episodes_owed)
    assert (verdict.incomplete, verdict.not_run) == ((arm,), ())
    cell = cells_by_arm(built.artifact)[arm]
    assert cell["incomplete"] is True
    assert cell["instrument_count"] == 1
    assert cell["episodes_scored"] == designed(made) - 1
    assert dict(built.tally) == tallied(made)
    assert calibration().card_verdict(built.artifact) == verdict


def test_fd4_3_the_resumed_run_is_finished_and_its_tally_keeps_the_failure(
    fd4_runs: RunFolders,
) -> None:
    """After the resume has run the failed attempt again, the wheel's resume has dropped the
    failed line from the trace file; the tally, which a resume never touches, is what still
    counts it (CAL16), so the card does."""
    made = fd4_runs["failed_once_resumed"]
    (arm,) = arm_ids(made)
    assert kept(made) == {arm: designed(made)}
    assert recorded(made) == {arm: designed(made)}
    assert tallied(made) == {arm: {"api_error": 1}}

    built = card(made)
    assert (built.verdict.word, built.verdict.partial, built.verdict.owed) == ("ok", False, 0)
    cell = cells_by_arm(built.artifact)[arm]
    assert cell["incomplete"] is False
    assert cell["instrument_count"] == 1
    assert cell["instrument_rate"] == pytest.approx(1 / (designed(made) + 1))


def test_fd4_3_an_episode_the_cap_cut_short_is_owed_and_is_not_a_failure(
    fd4_runs: RunFolders,
) -> None:
    """The ruling: the cap cut the first depth:d8 episode short.  Its calls are in the ledger;
    it is in no trace file and no tally.  On the card it is owed, depth:d8 is not run, and no cell
    counts an instrument failure, so nothing is refused on the cap's account."""
    made = fd4_runs["cut"]
    first, second = arm_ids(made)
    assert made.result.stop_reason == "spend_cap"
    assert recorded(made) == {first: designed(made), second: 0}
    assert any(line["arm"] == second for line in ledger(made))
    assert tallied(made) == {first: {}, second: {}}

    built = card(made)
    verdict = built.verdict
    assert verdict.word == "ok"
    assert (verdict.partial, verdict.owed) == (True, designed(made))
    assert verdict.owed == made.result.episodes_owed
    assert (verdict.not_run, verdict.incomplete) == ((second,), ())
    cells = cells_by_arm(built.artifact)
    assert sorted(cells) == [first]
    assert all(cell["instrument_count"] == 0 for cell in cells.values())
    assert figure_rows(built.document, second) == []
    assert second in built.document
    assert calibration().card_verdict(built.artifact) == verdict


def test_fd4_3_a_level_the_run_left_part_way_is_an_incomplete_cell(fd4_runs: RunFolders) -> None:
    """Spec §9.3's own example: the cap stopped the run after one depth:d3 task of several.  The
    cell is there and marked incomplete, with the tasks it holds; the attempts it never reached are
    owed, exactly what a resume would run; nothing is listed as not run."""
    made = fd4_runs["partial"]
    first, second = arm_ids(made)
    assert made.result.stop_reason == "spend_cap"
    assert recorded(made) == kept(made) == {first: designed(made), second: 1}
    assert len(ledger(made)) == designed(made) + 1

    built = card(made)
    verdict = built.verdict
    assert verdict.word == "ok"
    assert (verdict.partial, verdict.incomplete, verdict.not_run) == (True, (second,), ())
    assert verdict.owed == designed(made) - 1 == made.result.episodes_owed
    cell = cells_by_arm(built.artifact)[second]
    assert (cell["incomplete"], cell["S_observed"], cell["S_declared"]) == (
        True, 1, len(made.plan.seeds))
    assert cells_by_arm(built.artifact)[first]["incomplete"] is False
    assert calibration().card_verdict(built.artifact) == verdict


@pytest.mark.parametrize("scenario, gate", [("silent", "no_call"), ("all_failed", "instrument")])
def test_fd4_3_a_cell_over_its_gate_refuses_the_card(
    fd4_runs: RunFolders, scenario: str, gate: str
) -> None:
    """A cell over the no-call gate or the instrument gate is not published: the verdict refuses,
    naming the arm and the gate, and the card has records and nothing else.  The control is the
    finished first look above."""
    made = fd4_runs[scenario]
    (arm,) = arm_ids(made)
    records = calibration().records_from_run(made.folder / arm_dir(made.plan.arms[0]),
                                             model=made.plan.model.name)
    if gate == "no_call":
        assert records and all(row.sampled_calls == 0 for row in records)
    else:
        assert records and all(row.label in calibration().INSTRUMENT_LABELS for row in records)

    built = card(made)
    assert built.verdict.word == "refused"
    assert built.verdict.refused == ((arm, gate),)
    assert (built.artifact, built.document, built.claims) == (None, None, None)
    assert list(built.records) == records


def test_fd4_3_card_verdict_judges_an_artifact_by_its_own_gates(fd4_runs: RunFolders) -> None:
    """An artifact read back (for `card --check`) is judged by its own cells and the thresholds
    its own provenance declares; the published cards are complete and ok."""
    built = card(fd4_runs["first_look"])
    prov = built.artifact.provenance
    for key, over, gate in (("no_call_share", prov.no_call_threshold, "no_call"),
                            ("instrument_rate", prov.instrument_threshold, "instrument")):
        cells = copy.deepcopy(built.artifact.cells)
        cells[1][key] = over + 0.01
        tampered = dataclasses.replace(built.artifact, cells=cells)
        verdict = calibration().card_verdict(tampered)
        assert verdict.word == "refused", key
        assert verdict.refused == ((cells[1]["arm_id"], gate),)
        cells[1][key] = over
        assert calibration().card_verdict(dataclasses.replace(built.artifact, cells=cells)).word \
            == "ok"
    from tests.fd4_support import shipped_artifacts

    for artifact in shipped_artifacts():
        verdict = calibration().card_verdict(artifact)
        assert (verdict.word, verdict.partial, verdict.owed) == ("ok", False, 0)


def test_fd4_3_what_is_not_a_run_of_anything_has_no_card(
    fd4_runs: RunFolders, tmp_path: Path
) -> None:
    """Not a run folder, and a run that recorded no episode, are each refused in one line naming
    the folder; the finished first look is the control."""
    empty = fd4_runs["empty"]
    assert empty.result.episodes_run == 0
    assert all(count == 0 for count in recorded(empty).values())
    nothing = tmp_path / "not-a-run-folder"
    nothing.mkdir()
    for folder in (nothing, empty.folder):
        with pytest.raises(ValueError) as refused:
            calibration().card_from_run(folder)
        assert one_line(str(refused.value)) and folder.name in str(refused.value)
    assert card(fd4_runs["first_look"]).verdict.word == "ok"


def test_fd4_card_from_run_only_reads_the_folder(
    fd4_runs: RunFolders, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Building a card changes no byte of the run folder and adds nothing to it, not even an empty
    folder, and opens no socket (CAL19).  The folder with a failed line is the one a resume would
    rewrite; the cut folder holds an arm folder with no trace file; the self-served one is what a
    card would reach a server for."""
    for name in ("failed_once", "cut", "self_served"):
        made = fd4_runs[name]
        before = tree(made.folder)
        with network_guard(monkeypatch) as events:
            card(made)
        assert tree(made.folder) == before, name
        assert connections(events) == set(), name


# ---------------------------------------------------------------------------
# the card is measured under the plan (FD4.2, FD4.8, FD4.9, FD4.12)
# ---------------------------------------------------------------------------


def test_fd4_2_a_runs_card_is_measured_under_its_own_plan(fd4_runs: RunFolders) -> None:
    made = fd4_runs["first_look"]
    plan = made.plan
    prov = card(made).artifact.provenance
    assert list(prov.seed_list) == list(plan.seeds)
    assert (prov.S, prov.n) == (len(plan.seeds), plan.attempts)
    assert list(prov.k_values) == [k for k in (1, 2, 5) if k <= plan.attempts]
    assert prov.max_model_calls == plan.max_model_calls
    assert dict(prov.decoding) == dict(plan.decoding)
    (entry,) = prov.models
    assert entry["id"] == plan.model.name
    assert entry["endpoint_host"] == urllib.parse.urlsplit(plan.model.base_url).netloc
    assert (entry["input_rate"], entry["cached_input_rate"], entry["output_rate"]) == (
        plan.model.price.input, plan.model.price.cached_input, plan.model.price.output)
    assert prov.rate_read_date == plan.model.price.read_on
    serving = prov.serving[plan.model.name]
    assert serving["kind"] == "hosted"
    assert serving["endpoint_host"] == urllib.parse.urlsplit(plan.model.base_url).netloc


def test_fd4_12_the_card_holds_every_arms_records_and_the_runs_dollars(
    fd4_runs: RunFolders,
) -> None:
    """Several arm folders give each arm's `records_from_run`, concatenated in the plan's order;
    the card's dollars are the ledger's, which are the fixture's own count of calls, for a run
    whose every episode was scored."""
    made = fd4_runs["first_look"]
    built = card(made)
    expected = []
    for spec in made.plan.arms:
        expected += calibration().records_from_run(made.folder / arm_dir(spec),
                                                   model=made.plan.model.name)
    assert list(built.records) == expected
    lines = ledger(made)
    cells = cells_by_arm(built.artifact)
    for arm, cell in cells.items():
        assert cell["dollars"] == pytest.approx(
            sum(line["dollars"] for line in lines if line["arm"] == arm))
    calls = sum(cell["model_calls"] for cell in cells.values())
    assert sum(cell["dollars"] for cell in cells.values()) == pytest.approx(
        sum(line["dollars"] for line in lines)) == pytest.approx(calls * call_dollars())


@pytest.mark.parametrize("scenario, more", [("partial", False), ("failed_once", True),
                                            ("cut", True)])
def test_fd4_12_the_cards_dollars_are_its_scored_attempts_and_the_ledger_holds_the_rest(
    fd4_runs: RunFolders, scenario: str, more: bool
) -> None:
    """The plan's FD4.12 says the card's dollars equal the run's ledger; that holds only when every
    episode the run paid for was scored.  The card's dollars are its scored attempts' calls (the
    published cards' rule, CAL15, and the ruling that the cost columns stay as they are); an
    episode the cap cut short or one that failed was paid for and is in the ledger, not on the
    card (reported as a defect in the plan)."""
    made = fd4_runs[scenario]
    built = card(made)
    on_card = sum(cell["dollars"] for cell in built.artifact.cells)
    assert on_card == pytest.approx(scored_calls(built) * call_dollars())
    spent = sum(line["dollars"] for line in ledger(made))
    if more:
        assert spent > on_card + call_dollars() / 2
    else:
        assert spent == pytest.approx(on_card)


def test_fd4_9_a_field_declared_not_sent_is_on_the_card_as_not_sent(
    fd4_runs: RunFolders,
) -> None:
    made = fd4_runs["self_served"]
    declared = dict(made.plan.decoding)
    assert [name for name, value in declared.items() if value == NOT_SENT] == [
        "top_p", "max_tokens"]
    built = card(made)
    assert dict(built.artifact.provenance.decoding) == declared
    (line,) = [text for text in built.document.splitlines() if text.startswith("- decoding:")]
    assert line.count(NOT_SENT) == 2
    assert "None" not in line


def test_fd4_8_a_model_the_user_serves_is_self_served_on_its_card(
    fd4_runs: RunFolders, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no server facts the card records the endpoint and nothing reported; with the facts
    the server at the plan's endpoint reported, it records each of them, and the document prints
    them.  Facts reported by a server at another endpoint are refused: the card would describe a
    server its run did not use.  (The facts are read from a fake vLLM server and given the plan's
    endpoint for the control; the run's own server, the fixture model, has gone.)"""
    made = fd4_runs["self_served"]
    model = made.plan.model.name
    plain = card(made).artifact.provenance.serving[model]
    assert plain["kind"] == "self_served"
    assert plain["endpoint"] == made.plan.model.base_url
    assert list(plain.get("reported_by_server") or []) == []

    from poisson_tasks import providers

    fake = FakeServer()
    try:
        fake.route("/version", 200, {"version": "0.29.0"})
        fake.route("/v1/models", 200, {"object": "list", "data": [{"id": model}]})
        with network_guard(monkeypatch):
            facts = providers.server_facts(
                dataclasses.replace(made.plan.model, base_url=fake.url + "/v1"), timeout=5)
    finally:
        fake.close()
    assert facts["stack_version"] == "0.29.0" and facts["served_model"] == model

    with pytest.raises(ValueError) as refused:
        card(made, serving=facts)
    assert one_line(str(refused.value))
    facts = {**facts, "endpoint": made.plan.model.base_url}
    built = card(made, serving=facts)
    serving = built.artifact.provenance.serving[model]
    assert serving["kind"] == "self_served"
    for name, value in facts.items():
        assert serving[name] == value, name
    for value in (facts["endpoint"], facts["stack_version"]):
        assert value in built.document


# ---------------------------------------------------------------------------
# the document (FD4.10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ["first_look", "failed_once", "failed_once_resumed", "cut",
                                      "partial", "self_served", "distractor", "leaky"])
def test_fd4_10_the_document_carries_the_claims_and_regenerates_byte_for_byte(
    fd4_runs: RunFolders, scenario: str
) -> None:
    """The card recomputes from its own files: its records, the provenance its written artifact
    holds and its tally give the same artifact, byte for byte, the same verdict and the same
    claims; the document is that artifact rendered with its claims.  The claims block is an insertion: every line of
    the published renderer's document is there, in order, so the cost and time columns are the
    published cards' own."""
    built = card(fd4_runs[scenario])
    rebuilt, written, again = rebuilt_from_card(built)
    assert again == written
    assert calibration().card_verdict(rebuilt) == built.verdict
    assert calibration().card_claims(rebuilt) == built.claims
    assert built.document == calibration().render_document(rebuilt, claims=True)
    assert built.claims == calibration().card_claims(built.artifact)
    assert built.claims.meaning in built.document
    for line in built.claims.not_claimed:
        assert line in built.document
    published_lines = calibration().render_document(built.artifact).splitlines()
    remaining = iter(built.document.splitlines())
    for line in published_lines:
        assert any(line == candidate for candidate in remaining), line
