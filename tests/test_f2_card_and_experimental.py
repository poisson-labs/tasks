"""What a card says about the three new knobs, and "experimental" read from one source wherever a
knob is named, frozen as tests.

The invariants (the 0.3.0 faults spec, F2.14 and F2.15; Q5 ruled yes).  `gave_up_after_fault` reads
the kind's word on faults, timeouts and ratelimits arms and is `None` on landed; the record's
`retried_after_landed` is read from the trace on a landed arm and is `None` elsewhere; a cell
counts both figures and `duplicate_write` from records read back, instrument failures out, and
gates on none.  The card prints a column per figure where it applies and says, for each
experimental knob on it, that it is experimental and why; `card --json` carries the same as
`experimental`.  `arms.EXPERIMENTAL_KNOBS` is the one place the four experimental knobs and their
two reasons are listed, and every surface that names a knob reads it.  The recipes do not change,
and `custom` on the built-in tasks offers timeouts and ratelimits.

Shapes decided here
-------------------

**1. The columns are named in the card's words**: *gave up after a fault* on a table of faults,
timeouts or ratelimits arms, *retried after a landed timeout* on a landed table, *duplicate writes*
on every table of an own-tools card.  A depth or distractor table has none of the three, so the
published cards keep their bytes (held by their own tests, `tests/test_k1_*`).

**2. The line is the spec's**: `The <knob> knob is experimental: <reason>.`, the distractor line
of today being that sentence for distractor, word for word.

**3. One case per surface**, each reading the reason the mapping gives rather than a copy: `init`'s
knob entries, the plan's words, the settings file's comment, the export's arm help, the own-tools
card's probe lines, and `doctor`'s rows and `--json`.

**4. The recipes are held by a digest of `repr(sorted(arms.RECIPES.items()))` measured on `main`
at `9474ce4`**, and `knob_status.json` by the digest of its bytes there: a guard, true on `main`
by construction.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import arms, config, export
from poisson_tasks import calibration as cal
from poisson_tasks.cli import _common, _init
from poisson_tasks.knobs import arm_id
from tests.f2_support import (
    DID_NOT_BITE,
    DUPLICATE,
    EXPERIMENTAL_REASONS,
    KINDS,
    NOT_MEASURED,
    RETRIED,
    Kind,
    experimental,
    field,
    own_made,
    own_record,
    written,
)
from tests.fd3_support import needs_uv
from tests.fd4_support import (
    RunFolders,
    Scenario,
    fd4_runs,  # noqa: F401 - the fixture is used by name
    plan_of,
    published_seeds,
)
from tests.fixtures.model_server import FixtureModel
from tests.k3_support import GAVE_UP, episode, made, record_with, right
from tests.o2_support import fixture_sets
from tests.pv_support import copy_run, invoke_json
from tests.test_k3_records import provenance
from tests.test_o2_card import artifact as own_artifact
from tests.test_o2_cli import QUIET, invoke, work  # noqa: F401 - the fixture is used by name
from tests.test_o2d_b2 import BASE, FLOWS

MODEL = "gpt-5-nano-2025-08-07"
RECIPES_ON_MAIN = "1d901aefb293a300f7cdcaa092f437c1273159d79293e3aef83a706d6cbef178"
KNOB_STATUS_ON_MAIN = "6a9cc69cf9ebb34d9a7627d540648a20b97b0e0a9048b29c3ae99715dbdae9c5"
PROBED_GENERATOR = "b460964dc153fab4535af3b39abd41d50198f3dcc644ae3e43ddee85544b57f9"
COLUMNS = ("gave up after a fault", "retried after a landed timeout", "duplicate writes")


def line(knob: str, reason: str) -> str:
    """Shape 2."""
    return f"The {knob} knob is experimental: {reason}."


def data_of(document: dict[str, Any]) -> dict[str, Any]:
    held: dict[str, Any] = document.get("data", document)
    return held


# --------------------------------------------------------------------------
# the records
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(KINDS.values()), ids=list(KINDS))
def test_gave_up_after_fault_reads_the_kinds_word(kind: Kind, tmp_path: Path) -> None:
    """At level 1: the first right call alone gave up after a fault; the call again and the second
    did not; neither carries `retried_after_landed`."""
    bundle = made(kind.arm(1), 404)
    first, second = right(bundle)
    gave = episode(tmp_path, bundle, [first])
    kept_on = episode(tmp_path, bundle, [first, first, second])
    assert (vars(gave)[GAVE_UP], vars(kept_on)[GAVE_UP]) == (True, False)
    assert kept_on.label == "passed"
    for record in (gave, kept_on):
        assert field(record, RETRIED) is None and RETRIED not in written(record)


def test_on_own_tools_landed_records_retries_and_no_giving_up(tmp_path: Path) -> None:
    """On acme at seed 404.  `landed:l1`: the reference gave up on nothing (`None`) and did not
    retry; the call again, or a retry whose arguments are not JSON, retried.  `timeouts:o1`: the
    first call alone gave up after a fault, read off the kind's code, and `retried_after_landed`
    is `None`."""
    acme = fixture_sets()["acme-mcp"]
    landed = own_made(acme, "landed", 1, 404)
    (call,) = landed.reference_calls
    once = own_record(tmp_path / "once", landed, [call])
    again = own_record(tmp_path / "again", landed, [call, call])
    badly = own_record(tmp_path / "badly", landed, [call, (call[0], "{")])
    assert [field(r, RETRIED) for r in (once, again, badly)] == [False, True, True]
    assert [field(r, GAVE_UP) for r in (once, again, badly)] == [None, None, None]
    assert written(once)[RETRIED] is False and GAVE_UP not in written(once)
    timeouts = own_made(acme, "timeouts", 1, 404)
    gave = own_record(tmp_path / "gave", timeouts, list(timeouts.reference_calls[:1]))
    assert (field(gave, GAVE_UP), field(gave, RETRIED)) == (True, None)


def row(index: int, arm: str, label: str = "wrong_state", **figures: Any) -> Any:
    passed = label == "passed"
    return record_with(
        task_id=f"{arm}-{index // 5}", arm_id=arm, model=MODEL, seed=1000 + index // 5,
        attempt=index % 5, strict=passed, leaky=passed, label=label, turns=4, sampled_calls=3,
        prompt_tokens=3000, cached_input_tokens=0, completion_tokens=60, reasoning_tokens=0,
        **figures,
    )


def cell_figures(cell: list[Any], tmp_path: Path) -> dict[str, Any]:
    """The cell's figures, from its records written and read back as a card's are."""
    path = cal.write_records(cell, tmp_path / f"episodes-{len(list(tmp_path.iterdir()))}.jsonl")
    kept = cal.read_records(path)
    built = cal.build_artifact({(kept[0].arm_id, MODEL): kept}, provenance())
    cells: list[dict[str, Any]] = built.cells
    return cells[0]


def test_a_cell_counts_retries_and_duplicate_writes_and_gates_on_neither(tmp_path: Path) -> None:
    """Ten scored `landed:l1` episodes, four that retried (three of them duplicate writes) and an
    instrument failure that retried and counts in nothing; a depth cell, whose records carry
    neither, has neither figure."""
    cell = (
        [row(i, "landed:l1", **{RETRIED: True, DUPLICATE: True}) for i in range(3)]
        + [row(3, "landed:l1", **{RETRIED: True, DUPLICATE: False})]
        + [row(i, "landed:l1", "passed", **{RETRIED: False, DUPLICATE: False})
           for i in range(4, 10)]
        + [row(10, "landed:l1", "api_error", **{RETRIED: True, DUPLICATE: True})]
    )
    got = cell_figures(cell, tmp_path)
    assert (got["retried_after_landed_count"], got["retried_after_landed_share"]) == (4, 0.4)
    assert (got["duplicate_write_count"], got["duplicate_write_share"]) == (3, 0.3)
    depth = cell_figures([row(i, "depth:d3") for i in range(10)], tmp_path)
    assert not [key for key in depth if key.startswith(("retried", "duplicate"))], depth


# --------------------------------------------------------------------------
# the card
# --------------------------------------------------------------------------


def built_in_artifact(arms_and_rows: dict[str, Callable[[int], Any]]) -> cal.Artifact:
    cells = {(arm, MODEL): [make(i) for i in range(10)] for arm, make in arms_and_rows.items()}
    return cal.build_artifact(cells, provenance())


def timeouts_artifact() -> cal.Artifact:
    return built_in_artifact({
        "timeouts:o0": lambda i: row(i, "timeouts:o0", "passed"),
        "timeouts:o4": lambda i: row(i, "timeouts:o4", **{GAVE_UP: i < 3}),
    })


def header_lines(document: str) -> list[str]:
    return [text for text in document.splitlines() if text.startswith("| arm |")]


def test_each_table_prints_the_columns_that_apply() -> None:
    """Shape 1: a timeouts card's table prints *gave up after a fault*; an own-tools card of
    `landed` prints *retried after a landed timeout* and *duplicate writes*; a depth card prints
    none of the three."""
    timeouts = header_lines(cal.render_document(timeouts_artifact(), claims=True))
    assert timeouts and all(COLUMNS[0] in text for text in timeouts), timeouts
    assert not any(COLUMNS[1] in text or COLUMNS[2] in text for text in timeouts)
    landed = header_lines(cal.render_document(
        own_artifact({"landed:l0": 0.8, "landed:l1": 0.5}), claims=True))
    assert landed and all(COLUMNS[1] in t and COLUMNS[2] in t for t in landed), landed
    depth = built_in_artifact({
        "depth:d1": lambda i: row(i, "depth:d1", "passed"),
        "depth:d3": lambda i: row(i, "depth:d3"),
    })
    for text in header_lines(cal.render_document(depth, claims=True)):
        assert not any(column in text for column in COLUMNS), text


def test_the_card_says_each_experimental_knob_with_its_reason() -> None:
    """Shape 2, on a timeouts card, an own-tools landed card, a distractor card and a depth card."""
    said = cal.card_claims(timeouts_artifact()).not_claimed
    assert line("timeouts", NOT_MEASURED) in said
    own = cal.card_claims(own_artifact({"landed:l0": 0.8, "landed:l1": 0.5})).not_claimed
    assert line("landed", NOT_MEASURED) in own
    distractor = built_in_artifact({
        "distractor:r0@k16": lambda i: row(i, "distractor:r0@k16", "passed"),
        "distractor:r8@k16": lambda i: row(i, "distractor:r8@k16"),
    })
    assert line("distractor", DID_NOT_BITE) in cal.card_claims(distractor).not_claimed
    depth = built_in_artifact({"depth:d1": lambda i: row(i, "depth:d1", "passed")})
    assert not [text for text in cal.card_claims(depth).not_claimed if "experimental" in text]


@pytest.fixture(scope="module")
def timeouts_run(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """`timeouts` at 0 and 4, two published seeds, against the fixture model, as the run-folder
    scenarios of `tests/fd4_support.py` are run."""
    where = tmp_path_factory.mktemp("f2-timeouts")
    folders = RunFolders(where)
    with folders._environment(where) as patch, FixtureModel() as model:
        plan = plan_of(Scenario(arms=("timeouts:o0", "timeouts:o4"), seeds=2), model.base_url,
                       published_seeds(2))
        folder, _result = folders._run_once(patch, plan, where / "runs",
                                            {"spend_usd": 100.0, "tokens": None}, 4)
    yield folder


@needs_uv
def test_card_json_carries_experimental_and_the_card_its_line(
    timeouts_run: Path, fd4_runs: RunFolders, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
    tmp_path: Path,
) -> None:
    """`card --json`'s `experimental` maps each experimental knob on the card to its reason, `{}`
    on a card with none; the card's own page carries the line.

    Retrofitted 2026-10-29 by the build session: the two shared run folders are copied before
    `card` writes into them (`tests/pv_support.py`'s rule), since a card left in the session's
    shared folder made a later test's copy of it refuse to write its own."""
    for folder, expected in (
        (timeouts_run, {"timeouts": NOT_MEASURED}),
        (copy_run(fd4_runs["distractor"].folder, tmp_path / "distractor"), {"distractor": DID_NOT_BITE}),
        (copy_run(fd4_runs["strict"].folder, tmp_path / "strict"), {}),
    ):
        ran, document = invoke_json(["card", str(folder)], monkeypatch)
        assert ran.code == 0, ran
        assert data_of(document)["experimental"] == expected, folder
    text = (timeouts_run / "card" / "card.md").read_text(encoding="utf-8")
    assert line("timeouts", NOT_MEASURED) in text


# --------------------------------------------------------------------------
# experimental, one source
# --------------------------------------------------------------------------


def test_experimental_knobs_is_the_four_with_their_two_reasons() -> None:
    assert experimental() == EXPERIMENTAL_REASONS


def surface_init() -> str:
    return "\n".join(f"{name} | {label} | {note}" for name, label, note in _init.KNOBS)


def surface_plan() -> str:
    return _common._knob_words("timeouts", (0, 4), False)


def surface_config() -> str:
    text = config.dump_config(config.config_from_init_args([*BASE, "--recipe", "custom"]))
    (knob,) = [text_line for text_line in text.splitlines() if text_line.startswith("knob = ")]
    return knob


def surface_export() -> str:
    description = export.ExportTasksetConfig.model_fields["arm"].description
    return str(description)


def surface_probe() -> str:
    from poisson_tasks.own import card

    return "\n".join(card.probe_lines(("timeouts", "ratelimits", "landed")))


SURFACES: dict[str, tuple[Callable[[], str], Callable[[str, dict[str, str]], bool]]] = {
    "init": (surface_init, lambda said, why: all(
        f"{knob} | {knob} (experimental)" in said and f" | {why[knob]}" in said
        for knob in ("timeouts", "ratelimits"))),
    "plan": (surface_plan, lambda said, why: said == "timeouts (experimental) at 0 and 4"),
    "config": (surface_config, lambda said, why: said.split("#", 1)[1].strip()
               == "depth | distractor | timeouts | ratelimits (experimental)"),
    "export": (surface_export, lambda said, why: all(
        f"knob '{knob}'" in said
        and "EXPERIMENTAL: " + why[knob] in said[said.index(f"knob '{knob}'"):].split(" knob '")[0]
        for knob in ("timeouts", "ratelimits", "landed"))),
    "probe": (surface_probe, lambda said, why: all(
        f"{knob}: experimental, {why[knob]} (the built-in probe did not run it)" in said
        for knob in ("timeouts", "ratelimits", "landed"))),
}


@pytest.mark.parametrize("surface", list(SURFACES))
def test_each_surface_names_the_new_knobs_experimental_with_their_reason(surface: str) -> None:
    """Shape 3."""
    said, holds = SURFACES[surface]
    text = said()
    assert holds(text, experimental()), text


def test_doctor_names_each_new_knob_experimental_in_its_rows_and_json(
    work: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """On acme with its flows, which reaches every new knob: a row per knob reading `experimental:
    <reason>`, and `--json`'s `tools.experimental` the knobs the set reaches, each to its reason;
    depth keeps its words."""
    from tests.o1_support import fixture

    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    assert invoke(["init", *QUIET, "--own-file", "tools.json", *FLOWS], monkeypatch).code == 0
    ran = invoke(["doctor", "--offline"], monkeypatch)
    lines = ran.said.splitlines()
    for knob in ("timeouts", "ratelimits", "landed", "depth"):
        found = [text for text in lines if text.split()[:1] == [knob]]
        assert len(found) == 1, (knob, ran.said)
        words = "measured on the published cards" if knob == "depth" else (
            f"experimental: {NOT_MEASURED}")
        assert words in found[0], found[0]
    _ran, document = invoke_json(["doctor", "--offline"], monkeypatch)
    assert data_of(document)["tools"]["experimental"] == {
        knob: NOT_MEASURED for knob in ("timeouts", "ratelimits", "landed")}


def test_the_recipes_and_the_probes_record_are_those_of_main() -> None:
    """Shape 4: a guard.  The knob probe's record is not where "experimental" lives (F2.8): its
    bytes are its committed self and it still names the generator the probe ran on."""
    held = hashlib.sha256(repr(sorted(arms.RECIPES.items())).encode()).hexdigest()
    assert held == RECIPES_ON_MAIN
    path = Path(arms.__file__).resolve().parent / "knob_status.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == KNOB_STATUS_ON_MAIN
    assert arms.knob_status()["probe"]["generator"] == PROBED_GENERATOR


def settings(measure: str) -> str:
    base = config.dump_config(config.config_from_init_args(BASE))
    start, end = base.index("[measure]"), base.index("[tasks]")
    return base[:start] + "[measure]\n" + measure + "\n" + base[end:]


def planned_arms(measure: str, root: Path) -> list[str]:
    plan = config.resolve_plan(config.loads_config(settings(measure)), root=root)
    return [arm_id(spec) for spec in plan.arms]


@pytest.mark.parametrize("kind", list(KINDS.values()), ids=list(KINDS))
def test_custom_on_the_built_in_tasks_offers_the_new_knobs(kind: Kind, tmp_path: Path) -> None:
    """Q5: every level by default; 0 and 4 with their control; a control without both levels
    refused, as depth's is; `landed` refused on the built-in tasks."""
    knob = f'preset = "custom"\nknob = "{kind.knob}"'
    assert planned_arms(knob, tmp_path) == [kind.arm(level) for level in (0, 1, 2, 4)]
    assert planned_arms(knob + "\nlevels = [0, 4]\ncontrols = true", tmp_path) == [
        kind.arm(0), kind.arm(4), kind.control]
    with pytest.raises(config.ConfigError) as refused:
        planned_arms(knob + "\nlevels = [0, 2]\ncontrols = true", tmp_path)
    assert refused.value.key == "measure.controls"
    with pytest.raises(config.ConfigError) as landed:
        planned_arms('preset = "custom"\nknob = "landed"', tmp_path)
    assert landed.value.key == "measure.knob"

