"""The settings file, the run and the command on a user's own tools: the choices O2 Session B2
made beyond the frozen tests, pinned.

Own-tools spec §8 as ruled (2026-10-13, yes/nos 18 to 28; 2026-10-13 23:26, every knob), built
2026-10-14.  What the frozen tests of `tests/test_o2_config.py`, `tests/test_o2_cli.py`,
`tests/test_o2_run.py` and the pending files of yes/nos 20 to 28 do not name, this file does:

- `config`'s copy of the own knobs is the own generator's list; `custom` beside `[own]` takes
  every level the set reaches when `levels` is unset, in the knob's order; `card` beside `[own]`
  is refused when the file is read; a generator version beside `[own]` that is not the own
  generator's is refused; the file writer and the equivalent command round-trip an own custom
  file; `plan_toolset` refuses a changed file and `plan_flows` gives the generator's flows.
- `runs`: a built-in plan's eval config and `plan.json` carry no `own`; an own plan's estimate
  counts every episode's reference turns as its calls; the reservation before the first episode
  of an own arm is the card's 95th percentile over every record.
- `doctor` on a settings file with `[own]`: every line carries a status word, the knobs the set
  reaches are listed with the shipped ones first and each knob's status is exactly
  `arms.knob_status()`'s, depth's line says the published cards measured it, a missing tool
  file is not ready, and the last run of the same file is named with or without a changed digest.
- `init`: choosing the knob yourself on own tools offers every knob the set reaches, the shipped
  ones first, and writes the `--yes` file; `--mcp-command` without `--yes` asks for consent and a
  no writes nothing; a tool file that cannot be read is refused with nothing written; a recipe or
  a knob the set does not reach is the library's refusal, exit 2, with nothing written.
- `generate`, `export`, `run --dry-run` and `verify` on an own settings file: the files hold own
  wire rows, the eval configs name the own taskset, the plan names your tools, and `verify`
  refuses an own tasks file in one line.
"""

from __future__ import annotations

import io
import json
import shlex
import sys
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import arms as arms_module
from poisson_tasks import calibration, config, own, runs
from poisson_tasks.own import generator, recipes
from poisson_tasks.own import card as own_card
from tests.o1_support import FAKE_MCP_SERVER, fixture
from tests.test_o2_cli import Answers, invoke, work

FIXTURES = (work,)
"""The world of `tests/test_o2_cli.py`, used here by name."""
PROG = "poisson-tasks"
MADE_UP_KEY = "sk-made-up-for-this-test-only"
QUIET = ["--yes", "--no-fetch", "--no-check-key"]
BASE = ["--provider", "openai", "--no-price", "--token-cap", "100000"]
FLOWS = ["--own-flow", "search_orders.orders[].order_id:get_order.order_id",
         "--own-flow", "get_order.order_id:refund_order.order_id"]


def acme_with_flows(root: Path) -> tuple[Any, tuple[Any, ...]]:
    (root / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    toolset = own.read_tools(fixture("acme-mcp-tools-list.json"), name="tools").toolset
    flows = (generator.Flow("search_orders", "orders[].order_id", "get_order", "order_id"),
             generator.Flow("get_order", "order_id", "refund_order", "order_id"))
    return toolset, flows


def own_text(measure: str, extra: str = "") -> str:
    base = config.dump_config(config.config_from_init_args(BASE))
    start, end = base.index("[measure]"), base.index("[tasks]")
    flows = "".join(f'\n[[own.flow]]\nfrom = "{a}"\nfield = "{f}"\nto = "{b}"\nparam = "{p}"\n'
                    for a, f, b, p in (("search_orders", "orders[].order_id", "get_order", "order_id"),
                                       ("get_order", "order_id", "refund_order", "order_id")))
    return (base[:start] + "[measure]\n" + measure + "\n" + base[end:]
            + '\n[own]\nfile = "tools.json"\n' + extra + flows)


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------


def test_the_own_knobs_config_copies_are_the_generators() -> None:
    assert config._OWN_KNOBS == generator.KNOBS
    assert config._OWN_GENERATOR_VERSION == generator.GENERATOR_VERSION


def test_custom_without_levels_takes_every_level_the_set_reaches_in_order(tmp_path: Path) -> None:
    toolset, flows = acme_with_flows(tmp_path)
    for knob in recipes.offered_knobs(toolset, flows=flows):
        made = config.loads_config(own_text(f'preset = "custom"\nknob = "{knob}"'))
        assert made.measure.levels is None and made.measure.controls is False
        plan = config.resolve_plan(made, root=tmp_path)
        assert [spec.level for spec in plan.arms] == list(
            generator.knob_levels(toolset, knob, flows=flows))
        assert all(spec.knob == knob and spec.control is None for spec in plan.arms)
    plain = config.loads_config(own_text('preset = "custom"'))
    assert plain.measure.knob == "depth"


def test_card_beside_own_is_refused_when_the_file_is_read() -> None:
    with pytest.raises(config.ConfigError) as refused:
        config.loads_config(own_text('preset = "card"'))
    assert refused.value.key == "measure.preset"


def test_a_generator_version_that_is_not_the_own_generators_is_refused(tmp_path: Path) -> None:
    acme_with_flows(tmp_path)
    text = own_text('preset = "first-look"').replace(
        '# generator_version = "1"', 'generator_version = "1"', 1)
    made = config.loads_config(text)
    assert made.tasks.generator_version == "1"
    with pytest.raises(config.ConfigError) as refused:
        config.resolve_plan(made, root=tmp_path)
    assert refused.value.key == "tasks.generator_version"
    fine = own_text('preset = "first-look"').replace(
        '# generator_version = "1"', 'generator_version = "own-1"', 1)
    assert config.resolve_plan(config.loads_config(fine), root=tmp_path).arms


@pytest.mark.parametrize("measure", [
    'preset = "custom"\nknob = "faults"',
    'preset = "custom"\nknob = "faults"\nlevels = [0, 2]\nstrictness = "leaky"',
    'preset = "error-recovery"',
], ids=["custom-no-levels", "custom-levels", "recipe"])
def test_an_own_file_round_trips_through_the_writer_and_the_equivalent_command(
    measure: str,
) -> None:
    made = config.loads_config(own_text(measure, 'name = "acme"\nread = ["get_order"]\n'))
    written = config.dump_config(made)
    assert config.loads_config(written) == made
    command = config.equivalent_init_command(made, prog=PROG)
    assert "--controls" not in command and "--no-controls" not in command
    assert ("--levels" in command) == (made.measure.levels is not None)
    again = config.config_from_init_args(command[2:])
    assert config.dump_config(again) == written


def test_plan_toolset_refuses_a_changed_file_and_plan_flows_are_the_generators(
    tmp_path: Path,
) -> None:
    toolset, flows = acme_with_flows(tmp_path)
    plan = config.resolve_plan(config.loads_config(own_text('preset = "first-look"')),
                               root=tmp_path)
    assert config.plan_toolset(plan) == toolset
    assert config.plan_flows(plan) == flows
    (tmp_path / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json") + b"\n")
    with pytest.raises(ValueError, match="has changed since the plan was made"):
        config.plan_toolset(plan)
    built_in = config.resolve_plan(config.config_from_init_args(BASE))
    assert config.plan_flows(built_in) == ()
    with pytest.raises(ValueError):
        config.plan_toolset(built_in)


def test_an_own_flag_refused_names_the_flag(tmp_path: Path) -> None:
    for flags, key in ((["--own-file", "t.json", "--own-read", "a", "--own-read", "a"], "own.read"),
                       (["--own-file", "t.json", "--own-read", "a", "--own-write", "a"], "own.write")):
        with pytest.raises(config.ConfigError) as refused:
            config.config_from_init_args([*BASE, *flags])
        assert refused.value.key == key and "--own-" in str(refused.value)


# --------------------------------------------------------------------------
# runs
# --------------------------------------------------------------------------


def test_a_built_in_plan_carries_no_own_in_its_eval_config_or_plan_json() -> None:
    plan = config.resolve_plan(config.config_from_init_args(BASE))
    for spec in plan.arms:
        taskset = runs.verifiers_config(plan, spec)["env"]["taskset"]
        assert "own" not in taskset and taskset["id"] != "poisson-tasks-own"
    assert "own" not in runs._plan_document(plan)["plan"]


def test_an_own_plans_estimate_counts_reference_turns_and_reserves_the_cards_percentile(
    tmp_path: Path,
) -> None:
    acme_with_flows(tmp_path)
    flags = ["--provider", "openai", "--recipe", "first-look", "--tasks-per-level", "2",
             "--attempts", "2", "--own-file", "tools.json", *FLOWS]
    plan = config.resolve_plan(config.config_from_init_args(flags), root=tmp_path)
    found = runs.estimate(plan)
    turns = sum(len(bundle.reference_calls) + 1
                for spec in plan.arms for bundle in runs.own_bundles(plan, spec, plan.seeds))
    assert found.calls_min == found.calls_expected == turns * plan.attempts
    assert found.episodes == len(plan.arms) * 2 * 2
    assert found.tokens_expected > 0 and found.dollars_expected is not None
    assert found.source == "gpt-5-nano" and found.same_model
    assert plan.own is not None
    assert runs._plan_document(plan)["plan"]["own"] == dict(plan.own)
    dollars, tokens = runs._reservation(plan, plan.arms[0])
    assert dollars > 0 and tokens > 0
    for spec in plan.arms:
        assert (dollars, tokens) == runs._reservation(plan, spec)


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------


def doctor_rows(ran: Any) -> dict[str, tuple[str, str]]:
    """Each detail line of `doctor` as `label: (status, text)`."""
    rows: dict[str, tuple[str, str]] = {}
    for line in ran.out.splitlines()[1:]:
        if not line.startswith("  ") or not line.strip():
            continue
        parts = line.split()
        status = parts[1] if parts[1] != "not" else " ".join(parts[1:3])
        rows[parts[0]] = (status, line)
    return rows


@pytest.mark.parametrize("shipped", [(), ("faults", "history", "shape"), ("spread",)],
                         ids=["none", "as-shipped", "spread"])
def test_doctor_lists_every_knob_the_set_reaches_shipped_first_with_its_status(
    shipped: tuple[str, ...], work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arms_module, "SHIPPED_KNOBS", shipped)
    monkeypatch.setenv("OPENAI_API_KEY", MADE_UP_KEY)
    toolset, flows = acme_with_flows(work)
    assert invoke(["init", *QUIET, "--own-file", "tools.json", *FLOWS, "--recipe", "custom",
                   "--knob", "faults"], monkeypatch).code == 0
    ran = invoke(["doctor", "--offline"], monkeypatch)
    assert ran.code == 0, ran
    rows = doctor_rows(ran)
    reached = recipes.offered_knobs(toolset, flows=flows)
    # Retrofitted by ruling G14 (FD9 Session A): a knob's probe line is information, `note`.
    assert all(status == ("note" if label in reached else "ok")
               for label, (status, _) in rows.items()), rows
    lead = recipes.shipped_knobs(toolset, flows=flows)
    ordered = [*lead, *(knob for knob in reached if knob not in lead)]
    assert [label for label in rows if label in generator.KNOBS] == ordered
    statuses = own_card.probe_statuses(ordered)
    for knob in ordered:
        _, line = rows[knob]
        if knob in statuses:
            for model, status in statuses[knob].items():
                assert f"{status} on {model}" in line, (knob, line)
        else:
            assert "published cards" in line
    assert "flows" not in rows


def test_doctor_says_when_no_flow_is_declared_and_names_the_last_run(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", MADE_UP_KEY)
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    flags = ["--own-file", "tools.json", "--recipe", "custom", "--knob", "faults"]
    assert invoke(["init", *QUIET, *flags], monkeypatch).code == 0
    first = invoke(["doctor", "--offline"], monkeypatch)
    assert first.code == 0, first
    rows = doctor_rows(first)
    assert "depth" not in rows and "shape" not in rows
    assert generator.UNAVAILABLE_WITHOUT_FLOWS in rows["flows"][1]
    assert "run" not in rows
    made = config.load_config(work / "tasks.toml")
    plan = config.resolve_plan(made, root=work)
    folder = runs.find_run(plan, work / "runs")
    Path(folder.path).mkdir(parents=True)
    (Path(folder.path) / "plan.json").write_text(json.dumps(runs._plan_document(plan)),
                                                  encoding="utf-8")
    again = doctor_rows(invoke(["doctor", "--offline"], monkeypatch))
    assert "on this tool file" in again["run"][1] and folder.name in again["run"][1]


def test_doctor_is_not_ready_when_the_tool_file_is_missing_or_refused(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", MADE_UP_KEY)
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    assert invoke(["init", *QUIET, "--own-file", "tools.json", "--recipe", "custom",
                   "--knob", "faults"], monkeypatch).code == 0
    (work / "tools.json").unlink()
    ran = invoke(["doctor", "--offline"], monkeypatch)
    assert ran.code == 4 and ran.out.startswith("not ready  "), ran
    assert doctor_rows(ran)["tools"][0] == "not ok"
    (work / "tools.json").write_bytes(b'{"tools": []}')
    ran = invoke(["doctor", "--offline"], monkeypatch)
    assert ran.code == 4 and doctor_rows(ran)["tools"][0] == "not ok", ran


# --------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------


def offered_recipes() -> list[str]:
    return [name for name, recipe in arms_module.RECIPES.items() if recipe.offered]


@pytest.mark.parametrize("shipped", [(), ("faults", "history", "shape")], ids=["none", "shipped"])
def test_choosing_the_knob_yourself_on_own_tools_offers_every_knob_shipped_first(
    shipped: tuple[str, ...], work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arms_module, "SHIPPED_KNOBS", shipped)
    toolset, flows = acme_with_flows(work)
    table = recipes.recipes_for(toolset, flows=flows)
    custom_entry = str(sum(1 for recipe in table.values() if recipe.offered) + 1)
    reached = recipes.offered_knobs(toolset, flows=flows)
    lead = recipes.shipped_knobs(toolset, flows=flows)
    ordered = [*lead, *(knob for knob in reached if knob not in lead)]
    chosen = ordered[-1]
    err = io.StringIO()
    stdin = Answers(["2", "", "", "", "", "tools.json",  # G7 (FD9 Session A)
                     custom_entry, str(len(ordered)), "", ""])
    saved = sys.stderr
    ran = invoke(["init", "--no-check-key", *FLOWS], monkeypatch, stdin)
    sys.stderr = saved
    assert ran.code == 0, ran
    said = ran.err
    for knob in ordered:
        assert f") {knob}" in said, (knob, said)
    assert said.index(f") {ordered[0]}") < said.index(f") {ordered[-1]}")
    written = (work / "tasks.toml").read_text(encoding="utf-8")
    made = config.load_config(work / "tasks.toml")
    assert (made.measure.preset, made.measure.knob) == ("custom", chosen)
    assert made.measure.levels == generator.knob_levels(toolset, chosen, flows=flows)
    (work / "tasks.toml").unlink()
    yes = invoke(["init", *QUIET, "--own-file", "tools.json", *FLOWS, "--recipe", "custom",
                  "--knob", chosen, "--levels",
                  ",".join(str(x) for x in made.measure.levels), "--strictness", "strict"],
                 monkeypatch)
    assert yes.code == 0, yes
    assert (work / "tasks.toml").read_text(encoding="utf-8") == written
    del err


def test_mcp_command_without_yes_asks_for_consent_and_no_writes_nothing(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command = shlex.join([sys.executable, str(FAKE_MCP_SERVER), str(work / "log"),
                          str(work / "marker")])
    # G7 (FD9 Session A): own tools is the first question's second answer, before the provider
    declined = invoke(["init", "--no-check-key", "--mcp-command", command, "--recipe",
                       "error-recovery"], monkeypatch, Answers(["2", "", "", "", "", "n"]))
    assert declined.code == 1, declined
    assert sorted(path.name for path in work.iterdir()) == []
    assert "not started" in declined.err
    consented = invoke(["init", "--no-check-key", "--mcp-command", command, "--recipe",
                        "error-recovery"], monkeypatch, Answers(["2", "", "", "", "", "y"]))
    assert consented.code == 0, consented
    assert (work / "tools.mcp.json").is_file() and not (work / "marker").exists()
    made = config.load_config(work / "tasks.toml")
    assert made.own is not None and made.own.file == config.OWN_LIST_FILE
    assert command not in (work / "tasks.toml").read_text(encoding="utf-8")


def test_a_tool_file_that_cannot_be_read_is_refused_with_nothing_written(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = invoke(["init", *QUIET, "--own-file", "missing.json"], monkeypatch)
    assert missing.code == 1, missing
    assert [line for line in missing.err.splitlines() if line.startswith("error:")]
    assert sorted(path.name for path in work.iterdir()) == []
    (work / "tools.json").write_bytes(b'{"tools": [{"name": "a"}]}')
    refused = invoke(["init", *QUIET, "--own-file", "tools.json"], monkeypatch)
    assert refused.code == 1, refused
    assert sorted(path.name for path in work.iterdir()) == ["tools.json"]


def test_a_recipe_or_a_knob_the_set_does_not_reach_is_the_librarys_refusal(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    for flags in (["--recipe", "first-look"], ["--recipe", "custom", "--knob", "depth"],
                  ["--recipe", "custom", "--knob", "distractor"],
                  ["--recipe", "custom", "--knob", "faults", "--levels", "0,3"]):
        ran = invoke(["init", *QUIET, "--own-file", "tools.json", *flags], monkeypatch)
        assert ran.code == 2, (flags, ran)
        assert len([line for line in ran.err.splitlines() if line.startswith("error:")]) == 1
        assert sorted(path.name for path in work.iterdir()) == ["tools.json"]


def test_init_names_your_tools_in_its_result(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    ran = invoke(["init", *QUIET, "--own-file", "tools.json", "--own-name", "acme", *FLOWS,
                  "--json"], monkeypatch)
    assert ran.code == 0, ran
    document = json.loads(ran.out)
    assert document["tools"]["name"] == "acme" and document["tools"]["tools"] == 5
    assert document["tools"]["source_format"] == "mcp" and document["tools"]["flows"] == 2
    assert "your tools (acme)" in document["sentence"]


# --------------------------------------------------------------------------
# generate, export, run --dry-run, verify
# --------------------------------------------------------------------------


def _settled(work: Path, monkeypatch: pytest.MonkeyPatch, *flags: str) -> None:
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    ran = invoke(["init", *QUIET, "--own-file", "tools.json", *FLOWS, "--tasks-per-level", "2",
                  *flags], monkeypatch)
    assert ran.code == 0, ran


def test_generate_writes_own_wire_rows_and_shows_a_task(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from poisson_tasks.own.export import OwnTaskData, bundle_from_data

    _settled(work, monkeypatch, "--recipe", "custom", "--knob", "faults", "--levels", "2")
    ran = invoke(["generate"], monkeypatch)
    assert ran.code == 0, ran
    assert "none on your tools" in ran.out
    rows = (work / "tasks" / "faults-f2.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(rows) == 2
    plan = config.resolve_plan(config.load_config(work / "tasks.toml"), root=work)
    expected = runs.own_bundles(plan, plan.arms[0], plan.seeds)
    for row, bundle in zip(rows, expected, strict=True):
        data = OwnTaskData.model_validate_json(row)
        assert bundle_from_data(data) == bundle
    printed = invoke(["generate", "--print"], monkeypatch)
    assert printed.code == 0 and printed.out.splitlines() == rows, printed
    shown = invoke(["generate", "--show", "--task", "2"], monkeypatch)
    assert shown.code == 0, shown
    assert expected[1].task_id in shown.out and "the reference solution" in shown.out
    from poisson_tasks.own import verdict as own_verdict
    from poisson_tasks.tasks import FormatSpec, Turn

    fmt = FormatSpec(name="direct", markers=())
    for name, calls in expected[1].negative_controls.items():
        limit = name == "turn_limit"
        turns = tuple(Turn(content="", calls=(call,), finish_reason="tool_calls") for call in calls)
        if not limit:
            turns += (Turn(content="Done.", calls=(), finish_reason="stop"),)
        label = own_verdict.verify(expected[1], turns, not limit, limit, fmt).label
        lines = [line.split() for line in shown.out.splitlines() if line.strip().startswith(name + " ")]
        assert lines and lines[0][1] == label, (name, label, shown.out)


def test_export_names_the_own_taskset_and_run_dry_run_names_your_tools(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settled(work, monkeypatch)
    exported = invoke(["export", "--to", "verifiers"], monkeypatch)
    assert exported.code == 0, exported
    plan = config.resolve_plan(config.load_config(work / "tasks.toml"), root=work)
    assert plan.own is not None
    for spec in plan.arms:
        name = f"eval-{calibration._run_dir_name(spec)}.json"
        held = json.loads((work / "export" / name).read_text(encoding="utf-8"))
        assert held["env"]["taskset"]["id"] == "poisson-tasks-own"
        assert held["env"]["taskset"]["own"] == dict(plan.own)
    dry = invoke(["run", "--dry-run", "--offline"], monkeypatch)
    assert dry.code == 0 and dry.out.startswith("plan  "), dry
    assert "your tools" in dry.out and "never called" in dry.out


def test_verify_refuses_an_own_tasks_file_in_one_line(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settled(work, monkeypatch, "--recipe", "custom", "--knob", "faults", "--levels", "2")
    assert invoke(["generate"], monkeypatch).code == 0
    ran = invoke(["verify", "--tasks", "tasks/faults-f2.jsonl", "--task", "1", "--self-check"],
                 monkeypatch)
    assert ran.code == 1, ran
    assert len([line for line in ran.err.splitlines() if line.startswith("error:")]) == 1
    assert "your own tools" in ran.err


def test_the_cli_reads_the_tool_file_beside_the_settings_file_not_the_working_folder(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", MADE_UP_KEY)
    project = work / "project"
    project.mkdir()
    (project / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    # a plan large enough that its estimate moves the default cap above the $1.00 floor
    size = ["--tasks-per-level", "60", "--attempts", "100"]
    ran = invoke(["init", *QUIET, "--config", "project/tasks.toml", "--own-file", "tools.json",
                  *FLOWS, *size], monkeypatch)
    assert ran.code == 0, ran
    assert not (work / "tools.json").exists()
    # the default cap is made from the estimate, which reads the tool file beside the settings file
    from tests.test_o2_cli import library_file

    toolset, flows = acme_with_flows(project)
    default = recipes.default_recipe(toolset, flows=flows)
    assert default is not None
    expected = library_file(["--own-file", "tools.json", *FLOWS, *size, "--recipe", default], project)
    assert config.loads_config(expected).limits.spend_usd != config.default_spend_cap(None)
    assert (project / "tasks.toml").read_text(encoding="utf-8") == expected
    checked = invoke(["doctor", "--offline", "--config", "project/tasks.toml"], monkeypatch)
    assert checked.code == 0, checked
    assert doctor_rows(checked)["tools"][0] == "ok"
    made = invoke(["generate", "--config", "project/tasks.toml"], monkeypatch)
    assert made.code == 0, made
    assert sorted(path.name for path in (project / "tasks").iterdir())


# --------------------------------------------------------------------------
# what the first mutation pass found unpinned
# --------------------------------------------------------------------------


def test_the_plans_tool_count_is_the_usable_tools_not_the_refused(tmp_path: Path) -> None:
    listing = json.loads(fixture("acme-mcp-tools-list.json"))
    listing["tools"].append({"name": "pick", "description": "Picks.",
                             "inputSchema": {"type": "object",
                                             "properties": {"v": {"anyOf": [{"type": "string"}]}}}})
    (tmp_path / "tools.json").write_bytes(json.dumps(listing).encode())
    plan = config.resolve_plan(config.loads_config(own_text('preset = "first-look"')), root=tmp_path)
    assert plan.own is not None and plan.own["tools"] == 5
    reading = own.read_tools((tmp_path / "tools.json").read_bytes(), name="tools")
    assert len(reading.refused) == 1 and len(reading.toolset.tools) == 5


def test_the_runs_tasks_carry_the_intents_and_the_folder_keys_match_them(tmp_path: Path) -> None:
    toolset, flows = acme_with_flows(tmp_path)
    text = own_text('preset = "first-look"',
                    '\n[own.intents]\nrefund_order = "refund a customer\'s order"\n')
    plan = config.resolve_plan(config.loads_config(text), root=tmp_path)
    from poisson_tasks.own.export import task_from_bundle

    for spec in plan.arms:
        bundles = runs.own_bundles(plan, spec, plan.seeds)
        expected = [generator.generate(toolset, spec, seed, flows=flows,
                                       intents={"refund_order": "refund a customer's order"})
                    for seed in plan.seeds]
        assert bundles == expected
        assert any("refund a customer's order" in bundle.request.lower() for bundle in bundles)
        assert runs._task_hashes(spec, plan.seeds, plan) == [
            str(task_from_bundle(bundle).hash) for bundle in expected]


def test_doctors_last_run_is_of_the_same_set_not_only_the_same_file_name(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", MADE_UP_KEY)
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    flags = ["--own-file", "tools.json", "--own-name", "mine", "--recipe", "custom", "--knob", "faults"]
    assert invoke(["init", *QUIET, *flags], monkeypatch).code == 0
    other = config.config_from_init_args(["--own-file", "tools.json", "--own-name", "theirs",
                                          "--recipe", "custom", "--knob", "faults"])
    plan = config.resolve_plan(other, root=work)
    folder = runs.find_run(plan, work / "runs")
    Path(folder.path).mkdir(parents=True)
    (Path(folder.path) / "plan.json").write_text(json.dumps(runs._plan_document(plan)),
                                                  encoding="utf-8")
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json") + b"\n")
    rows = doctor_rows(invoke(["doctor", "--offline"], monkeypatch))
    assert "run" not in rows, rows


def test_the_dialogue_says_the_summary_line_before_the_recipe_question(
    work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    first = own.summary(own.read_tools(fixture("acme-mcp-tools-list.json"), name="tools")).splitlines()[0]
    stdin = Answers(["2", "", "", "", "", "tools.json"])  # G7 (FD9 Session A)
    ran = invoke(["init", "--no-check-key", *FLOWS], monkeypatch, stdin)
    assert ran.code == 0, ran
    assert first in ran.err and ran.err.index(first) < ran.err.index("What do you want to measure on")

