"""What a card says about the two new knobs, and "experimental" read from one source wherever a knob
is named, frozen as tests.

The invariants (the 0.4.0 stale-data spec, BD.16 and BD.17).  `acted_on_bad_data` and
`read_again_after_bad` are read off the record's trace and replay, tell apart an agent that never
looked again from one that looked and still went wrong, and are `None` and left out of JSON on every
other arm and at `b0` and `g0`; a cell counts them from records read back, instrument failures out;
the card prints the two at the end of every table on a card holding either knob, and on no other.
`arms.EXPERIMENTAL_KNOBS` is six knobs and two reasons, and every surface that names a knob reads it,
each entry's own note held and not the joined text.  `custom` offers `baddata` on the built-in tasks
with `controls = true` refused, and both on own tools; the recipes hold neither.

Shapes decided here
-------------------

**1. Each case is a hand-built episode** whose tool messages are the server's (`tests/k3_support.py`)
or the simulator's (`tests/f2_support.py`), read back as a run's record, as 0.3.0's figures are.

**2. An episode that received no bad answer reads `False` on both**: the spec says so of *acted*, and
*read again* is "after the bad answer", which never came.

**3. An instrument failure is held at the cell.**  The spec says a cell leaves it out; what the record
of one holds is the build's.

**4. "A 0.3.x card is byte for byte" is held by digests of a card rendered on `main` at `acc3144`**
(0.3.3) from records and a provenance the test writes: a timeouts card and an own-tools `landed` card.
They are guards, true on `main` by construction, as 0.3.0's held bytes are; the repo holds no card
written by a 0.3.x run, and the published cards keep their own tests (`tests/test_cal_committed_cards.py`,
`tests/test_fd4_published.py`).

**5. Where `card --json` carries the two figures** is put to the maintainer as a yes/no, and nothing is
frozen on it until it is ruled: the spec says that it does and not under what.  Its `experimental` is
held here through the function it prints.  No fixture-model run is here: `tests/fixtures/model_server.py`
reads B's request and answers a `baddata` request in text, so `card` refuses that run as `no_call`.  The
run against a scripted model is the build's gate (the spec's section 10).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import arms, config, export
from poisson_tasks import calibration as cal
from poisson_tasks.cli import _common, _init
from tests.bd_support import (
    ABOVE_ZERO,
    ACTED,
    BUILT_IN_SENTENCE,
    COLUMNS,
    EXPERIMENTAL_REASONS,
    NOT_MEASURED,
    READ_AGAIN,
    another_page,
    bad_read,
    baddata,
    carried,
    figure,
    figures,
    own_task,
    read_pairs,
    stage_calls_on,
    target_and_decoy,
    the_two_reads,
)
from tests.f2_support import experimental, own_record, written
from tests.fd5_support import Answers
from tests.k3_support import answers, episode, made, records_of, trace_of
from tests.o1_support import fixture
from tests.o2_support import fixture_sets, generator
from tests.pv_support import invoke_json
from tests.test_f2_card_and_experimental import (
    built_in_artifact,
    cell_figures,
    data_of,
    header_lines,
    line,
    planned_arms,
    row,
    timeouts_artifact,
)
from tests.test_fx_tightened import knob_menu
from tests.test_o2_card import artifact as own_artifact
from tests.test_o2_cli import QUIET, invoke, work  # noqa: F401 - the fixture is used by name
from tests.test_o2d_b2 import BASE

# Shape 4: measured on `main` at `acc3144`.
TIMEOUTS_CARD_ON_0_3_3 = "ae045fd8ff0977cf27216a32d80b56ededd31db25a128c9a9f40ea504a4bb7b7"
LANDED_CARD_ON_0_3_3 = "d44475e136ff3c663a233751b357ac4c717e37c27420f0ea05b0962d07ccc96c"


def bad_cases(level: int, seed: int) -> dict[str, tuple[list[tuple[str, Any]], bool, bool]]:
    """Each built-in episode at `level`: its calls, whether it acted, whether it read again."""
    bundle = baddata(level, seed)
    target, decoy = target_and_decoy(bundle)
    right_calls = stage_calls_on(bundle, target)
    r = bad_read(bundle)
    first, second = the_two_reads(bundle)
    s = second if r == first else first
    if level < 3:
        wrong = stage_calls_on(bundle, decoy)
        return {
            "trusted": ([r, s, *wrong], True, False),
            "read again then right": ([r, r, s, *right_calls], False, True),
            "read again then wrong": ([r, r, s, *wrong], True, True),
            "never read, wrong": ([*wrong], False, False),
            "never read, right": ([*right_calls], False, False),
            "a badly written second read": ([r, (r[0], "{"), s, *right_calls], False, True),
            "another page of the same read": ([r, another_page(r), s, *right_calls], False, True),
            "the other read between": ([r, s, r, *right_calls], False, True),
            "read after acting": ([r, s, *wrong, r], True, False),
            "acted and then right": ([r, s, *wrong, *right_calls], True, False),
            "stopped without moving": ([r], False, False),
        }
    short = right_calls[:1]
    return {
        "trusted": ([s, r, *short], True, False),
        "read again then right": ([s, r, r, *right_calls], False, True),
        "read again then wrong": ([s, r, r, *short], True, True),
        "never read, wrong": ([*short], False, False),
        "never read, right": ([*right_calls], False, False),
        "a badly written second read": ([s, r, (r[0], "{"), *right_calls], False, True),
        "another page of the same read": ([s, r, another_page(r), *right_calls], False, True),
        "short, read after, then finished": ([s, r, *short, r, right_calls[1]], False, False),
        "only the other read": ([s, *short], False, False),
    }


@pytest.mark.parametrize("level", ABOVE_ZERO)
def test_the_two_figures_on_each_built_in_case(level: int, tmp_path: Path) -> None:
    """Shapes 1 and 2.  Each figure is the case's, an episode that acted never passes strict, and the
    written line carries both."""
    for name, (calls, acted, again) in bad_cases(level, 404).items():
        folder = tmp_path / name.replace(" ", "-").replace(",", "")
        folder.mkdir()
        record = episode(folder, baddata(level, 404), calls)
        assert figures(record) == (acted, again), (level, name, record.label)
        assert written(record)[ACTED] is acted and written(record)[READ_AGAIN] is again, name
        if acted:
            assert record.strict is False, (level, name, record.label)


def own_bad_cases(bundle: Any) -> dict[str, tuple[list[tuple[str, Any]], bool, bool]]:
    from tests.test_bd_own import bad_write

    held = carried(bundle)
    r, w = held.read, held.write
    b = bad_write(bundle)
    return {
        "trusted": ([r, b], True, False),
        "read again then right": ([r, r, w], False, True),
        "read again then wrong": ([r, r, b], True, True),
        "never read, wrong": ([b], False, False),
        "a badly written second read": ([r, (r[0], "{"), w], False, True),
        "read after acting": ([r, b, r], True, False),
        "acted and then right": ([r, b, w], True, False),
        "stopped without writing": ([r], False, False),
    }


@pytest.mark.parametrize("level", ABOVE_ZERO)
def test_the_two_figures_on_each_own_baddata_case(level: int, tmp_path: Path) -> None:
    """On acme at seed 404, read off the store's writes."""
    bundle = own_task("acme-mcp", "baddata", level, 404)
    for name, (calls, acted, again) in own_bad_cases(bundle).items():
        record = own_record(tmp_path / name.replace(" ", "-").replace(",", ""), bundle, calls)
        assert figures(record) == (acted, again), (level, name, record.label)
        if acted:
            assert record.strict is False, (level, name, record.label)


def test_the_two_figures_on_each_lagged_case(tmp_path: Path) -> None:
    """On petstore at seed 404.  Acted is an accepted write of the target repeated after the lagging
    read; a duplicate without the lagging read is `duplicate_write` and not *acted*."""
    bundle = own_task("petstore", "lagged", 1, 404)
    w, r = bundle.reference_calls[:2]
    cases = {
        "trusted": ([w, r, w], True, False),
        "read again then right": ([w, r, r], False, True),
        "read again and wrote": ([w, r, r, w], True, True),
        "never read": ([w, w], False, False),
        "read before the write only": ([r, w], False, False),
        "a badly written second read": ([w, r, (r[0], "{")], False, True),
        "read after the second write": ([w, r, w, r], True, False),
    }
    for name, (calls, acted, again) in cases.items():
        record = own_record(tmp_path / name.replace(" ", "-"), bundle, calls)
        assert figures(record) == (acted, again), (name, record.label)
        if acted:
            assert record.strict is False, (name, record.label)


def test_both_figures_are_none_and_left_out_at_level_0_and_on_every_other_arm(tmp_path: Path) -> None:
    """At `b0` and `g0`, on a built-in `depth` and `faults` arm and an own-tools `faults` arm.  The
    control is the same reader at `b2`, where each is carried."""
    fields = {ACTED, READ_AGAIN}
    held = [("b0", baddata(0, 404)), ("depth", made("depth:d3", 404)), ("faults", made("faults:f1", 404))]
    for name, bundle in held:
        (tmp_path / name).mkdir()
        record = episode(tmp_path / name, bundle, list(bundle.reference_calls))
        assert figures(record) == (None, None), name
        assert not fields & set(written(record)), name
    own = [("own-b0", own_task("acme-mcp", "baddata", 0, 404)),
           ("own-g0", own_task("petstore", "lagged", 0, 404)),
           ("own-faults", generator().generate(fixture_sets()["acme-mcp"], faults_arm(), 404))]
    for name, bundle in own:
        record = own_record(tmp_path / name, bundle, list(bundle.reference_calls))
        assert figures(record) == (None, None), name
        assert not fields & set(written(record)), name
    (tmp_path / "b2").mkdir()
    carried_record = episode(tmp_path / "b2", baddata(2, 404), list(baddata(2, 404).reference_calls))
    assert fields <= set(written(carried_record))


def faults_arm() -> Any:
    from poisson_tasks.arms import arm_from_id

    return arm_from_id("faults:f0", generator_version=generator().GENERATOR_VERSION)


def test_a_cell_counts_the_two_from_records_read_back_instrument_failures_out(tmp_path: Path) -> None:
    """Ten scored `baddata:b2` episodes, three that acted and four that read again, and an instrument
    failure that says both and counts in neither; `gave_up_after_fault` and neither figure at all on a
    depth cell; `b0`'s cell, whose records carry none, has neither figure."""
    cell = (
        [row(i, "baddata:b2", **{ACTED: True, READ_AGAIN: False}) for i in range(2)]
        + [row(2, "baddata:b2", **{ACTED: True, READ_AGAIN: True})]
        + [row(i, "baddata:b2", "passed", **{ACTED: False, READ_AGAIN: True}) for i in range(3, 6)]
        + [row(i, "baddata:b2", "passed", **{ACTED: False, READ_AGAIN: False}) for i in range(6, 10)]
        + [row(10, "baddata:b2", "api_error", **{ACTED: True, READ_AGAIN: True})]
    )
    got = cell_figures(cell, tmp_path)
    assert (got[f"{ACTED}_count"], got[f"{ACTED}_share"]) == (3, 0.3)
    assert (got[f"{READ_AGAIN}_count"], got[f"{READ_AGAIN}_share"]) == (4, 0.4)
    for arm_id in ("depth:d3", "baddata:b0"):
        plain = cell_figures([row(i, arm_id) for i in range(10)], tmp_path)
        assert not [key for key in plain if key.startswith((ACTED, READ_AGAIN))], plain


def test_an_instrument_failure_is_held_out_of_a_cell_from_a_hand_built_trace(tmp_path: Path) -> None:
    """Shape 3: a trace that did not finish, on the `b2` trusted episode, is an instrument label; beside
    ten that trusted, the cell's count and share are the ten's."""
    bundle = baddata(2, 404)
    _target, decoy = target_and_decoy(bundle)
    calls = [*the_two_reads(bundle), *stage_calls_on(bundle, decoy)]
    trace = trace_of(bundle, calls, answers(bundle, calls))
    (failed,) = records_of(tmp_path, trace.model_copy(update={"ok": False}))
    assert failed.label in cal.INSTRUMENT_LABELS
    trusted = [row(i, "baddata:b2", **{ACTED: True, READ_AGAIN: False}) for i in range(10)]
    extra = cal.EpisodeRecord.from_json(cal.EpisodeRecord.to_json(failed))
    moved = row(10, "baddata:b2", failed.label, **{
        ACTED: figure(extra, ACTED), READ_AGAIN: figure(extra, READ_AGAIN)})
    got = cell_figures([*trusted, moved], tmp_path)
    assert (got[f"{ACTED}_count"], got[f"{ACTED}_share"]) == (10, 1.0)
    assert (got[f"{READ_AGAIN}_count"], got[f"{READ_AGAIN}_share"]) == (0, 0.0)


# --------------------------------------------------------------------------
# the card
# --------------------------------------------------------------------------


def baddata_artifact() -> cal.Artifact:
    return built_in_artifact({
        "baddata:b0": lambda i: row(i, "baddata:b0", "passed"),
        "baddata:b3": lambda i: row(i, "baddata:b3", **{ACTED: i < 3, READ_AGAIN: i >= 3}),
    })


def test_the_two_columns_end_every_table_of_a_card_holding_either_knob_and_no_other() -> None:
    """On a built-in `baddata` card and own-tools `baddata` and `lagged` cards, where *duplicate
    writes* is before them; on a depth card and a timeouts card, none."""
    both = "".join(f" {title} |" for title in COLUMNS)
    built_in = header_lines(cal.render_document(baddata_artifact(), claims=True))
    assert built_in and all(text.endswith(both) for text in built_in), built_in
    for rates in ({"baddata:b0": 0.8, "baddata:b3": 0.5}, {"lagged:g0": 0.8, "lagged:g1": 0.5}):
        own = header_lines(cal.render_document(own_artifact(rates), claims=True))
        assert own and all(text.endswith(both) and "duplicate writes" in text for text in own), own
    depth = built_in_artifact({
        "depth:d1": lambda i: row(i, "depth:d1", "passed"),
        "depth:d3": lambda i: row(i, "depth:d3"),
    })
    for artifact in (depth, timeouts_artifact()):
        for text in header_lines(cal.render_document(artifact, claims=True)):
            assert not any(title in text for title in COLUMNS), text


def card_digest(artifact: cal.Artifact) -> str:
    return hashlib.sha256(cal.render_document(artifact, claims=True).encode("utf-8")).hexdigest()


def test_a_0_3_x_card_keeps_its_bytes() -> None:
    """Shape 4: a guard."""
    assert card_digest(timeouts_artifact()) == TIMEOUTS_CARD_ON_0_3_3
    landed = own_artifact({"landed:l0": 0.8, "landed:l1": 0.5}, generator_hash="g" * 64)
    assert card_digest(landed) == LANDED_CARD_ON_0_3_3


def test_the_card_and_card_json_say_each_new_knob_is_experimental_with_its_reason() -> None:
    """The claims' line, and `experimental_knobs`, what `card --json` prints as `experimental`."""
    said = cal.card_claims(baddata_artifact()).not_claimed
    assert line("baddata", NOT_MEASURED) in said
    assert line("lagged", NOT_MEASURED) not in said
    lagged = own_artifact({"lagged:g0": 0.8, "lagged:g1": 0.5})
    assert line("lagged", NOT_MEASURED) in cal.card_claims(lagged).not_claimed
    assert cal.experimental_knobs(baddata_artifact()) == {"baddata": NOT_MEASURED}
    assert cal.experimental_knobs(lagged) == {"lagged": NOT_MEASURED}


# --------------------------------------------------------------------------
# experimental, one source
# --------------------------------------------------------------------------


def test_experimental_knobs_is_the_six_with_their_two_reasons() -> None:
    assert experimental() == EXPERIMENTAL_REASONS


def init_entry() -> bool:
    entry = {name: (label, note) for name, label, note in _init.KNOBS}
    label, note = entry["baddata"]
    return bool(note == experimental()["baddata"] and "baddata (experimental)" in label
                and "lagged" not in entry)


def plan_words() -> bool:
    return bool(
        _common._knob_words("baddata", (0, 3), False) == "baddata (experimental) at 0 and 3"
        and _common._knob_words("lagged", (0, 1), False) == "lagged (experimental) at 0 and 1"
    )


def config_words() -> bool:
    text = config.dump_config(config.config_from_init_args([*BASE, "--recipe", "custom"]))
    (knob,) = [text_line for text_line in text.splitlines() if text_line.startswith("knob = ")]
    return knob.split("#", 1)[1].strip() == (
        "depth | distractor | timeouts | ratelimits | baddata (experimental)")


def export_sentences() -> bool:
    said = str(export.ExportTasksetConfig.model_fields["arm"].description)
    sentences = {knob: said[said.index(f"knob '{knob}'"):].split(" knob '")[0]
                 for knob in ("baddata", "lagged") if f"knob '{knob}'" in said}
    return bool(
        set(sentences) == {"baddata", "lagged"}
        and all("EXPERIMENTAL: " + experimental()[knob] in text for knob, text in sentences.items())
        and "own tools" in sentences["lagged"]
        and "own tools" not in sentences["baddata"]
    )


def probe_lines() -> bool:
    from poisson_tasks.own import card

    return card.probe_lines(("baddata", "lagged")) == [
        f"- {knob}: experimental, {experimental()[knob]} (the built-in probe did not run it)."
        for knob in ("baddata", "lagged")
    ]


SURFACES: dict[str, Callable[[], bool]] = {
    "init": init_entry,
    "plan": plan_words,
    "config": config_words,
    "export": export_sentences,
    "probe": probe_lines,
}


@pytest.mark.parametrize("surface", list(SURFACES))
def test_each_surface_says_experimental_and_the_mappings_reason_entry_by_entry(surface: str) -> None:
    assert SURFACES[surface]()


def test_the_guided_menu_on_own_tools_gives_each_knob_its_reason_as_its_note(
    work: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """On petstore, which reaches both.  The entry's own note, compared whole."""
    from poisson_tasks.own import recipes

    (work / "tools.json").write_bytes(fixture("petstore-openapi-3.0.json"))
    table = recipes.recipes_for(fixture_sets()["petstore"])
    custom = str(sum(1 for recipe in table.values() if recipe.offered) + 1)
    ran = invoke(["init", "--no-check-key"], monkeypatch,
                 Answers(["2", "", "", "", "", "tools.json", custom]))
    assert ran.code == 0, ran
    menu = knob_menu(ran.out + ran.err)
    for name in ("baddata", "lagged"):
        assert menu.get(f"{name} (experimental)") == [f"experimental: {experimental()[name]}"], (name, menu)


def test_doctor_names_each_new_knob_experimental_in_its_rows_and_json(
    work: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """On petstore: a note row per knob, and `--json`'s `tools.experimental` each to its reason."""
    (work / "tools.json").write_bytes(fixture("petstore-openapi-3.0.json"))
    assert invoke(["init", *QUIET, "--own-file", "tools.json"], monkeypatch).code == 0
    ran = invoke(["doctor", "--offline"], monkeypatch)
    lines = ran.said.splitlines()
    for knob in ("baddata", "lagged"):
        (found,) = [text for text in lines if text.split()[:1] == [knob]]
        assert f"experimental: {NOT_MEASURED}" in found and "note" in found.split(), found
    _ran, document = invoke_json(["doctor", "--offline"], monkeypatch)
    held = data_of(document)["tools"]["experimental"]
    assert held["baddata"] == NOT_MEASURED and held["lagged"] == NOT_MEASURED, held


def test_generate_show_shows_the_bad_answer_in_the_references_steps(
    work: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """Section 8: `--show` at `b2` prints the read's two answers, the bad then the true, as it prints
    a fault line, and the sentence with the system prompt."""
    seed = cal.seed_list()[0]
    ran = invoke(["generate", "--arm", "baddata:b2", "--show", "--seed", str(seed)], monkeypatch)
    assert ran.code == 0, ran
    bundle = baddata(2, seed)
    bad, true = [line for call, line in read_pairs(bundle) if call == bad_read(bundle)]
    assert ran.said.index(bad) < ran.said.index(true), ran.said
    assert BUILT_IN_SENTENCE in ran.said


def test_custom_offers_baddata_on_the_built_in_tasks_and_refuses_its_control(tmp_path: Path) -> None:
    """Every level by default, and any of them; `controls = true` refused beside `timeouts`' accepted
    control, naming the reason."""
    knob = 'preset = "custom"\nknob = "baddata"'
    assert planned_arms(knob, tmp_path) == [f"baddata:b{level}" for level in (0, 1, 2, 3)]
    assert planned_arms(knob + "\nlevels = [0, 3]", tmp_path) == ["baddata:b0", "baddata:b3"]
    assert "timeouts:o0+len(o4)" in planned_arms(
        'preset = "custom"\nknob = "timeouts"\nlevels = [0, 4]\ncontrols = true', tmp_path)
    with pytest.raises(config.ConfigError) as refused:
        planned_arms(knob + "\nlevels = [0, 3]\ncontrols = true", tmp_path)
    said = str(refused.value).replace(str(tmp_path), "")
    assert refused.value.key == "measure.controls"
    assert "\n" not in said and "read" in said and "no control arm" in said, said


@pytest.mark.parametrize(("knob", "levels"), [("baddata", (0, 2, 3)), ("lagged", (0, 1))])
def test_custom_on_own_tools_offers_both_at_the_levels_the_set_reaches(
    knob: str, levels: tuple[int, ...], tmp_path: Path
) -> None:
    """On petstore, whose `baddata` has no level 1; a level it does not reach is refused."""
    (tmp_path / "tools.json").write_bytes(fixture("petstore-openapi-3.0.json"))
    base = config.dump_config(config.config_from_init_args(BASE))
    start, end = base.index("[measure]"), base.index("[tasks]")
    text = (base[:start] + f'[measure]\npreset = "custom"\nknob = "{knob}"\n{{}}\n' + base[end:]
            + '\n[own]\nfile = "tools.json"\n')
    plan = config.resolve_plan(config.loads_config(text.format("")), root=tmp_path)
    letter = {"baddata": "b", "lagged": "g"}[knob]
    from poisson_tasks.knobs import arm_id

    assert [arm_id(spec) for spec in plan.arms] == [f"{knob}:{letter}{level}" for level in levels]
    with pytest.raises(config.ConfigError) as refused:
        config.resolve_plan(config.loads_config(text.format("levels = [9]")), root=tmp_path)
    assert refused.value.key == "measure.levels"


def test_the_recipes_hold_neither_knob_though_custom_reaches_both() -> None:
    """No recipe gains them (Q11).  The control is the arm itself, which the generator makes."""
    assert baddata(1, 404).arm_id == "baddata:b1"
    for recipe in arms.RECIPES.values():
        assert "baddata" not in recipe.knobs and "lagged" not in recipe.knobs, recipe.name
        assert not [arm for arm in recipe.arms if arm.startswith(("baddata:", "lagged:"))], recipe.name
