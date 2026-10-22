"""`tasks.toml`'s `[own]` table, its flags and the plan it resolves to, frozen as tests.

By design (and decided): own-tools settings live in their own `[own]` table, never in `[tasks]`,
whose content the frozen `test_fd1_*` tests pin; every own-tools setting has an `init` flag so the
equivalent command reproduces the file.  The table: `file` (OpenAI tools, an MCP
`tools/list`, or OpenAPI), `format` (`auto`, `openai`, `mcp` or `openapi`), `name` (shown on the
card), `read` and `write` (the effects Tasks could not read from the file), `[own.intents]` and
`[[own.flow]]`.  The flags: `--own-file PATH`, `--own-format`, `--own-name NAME`, `--own-read
TOOL` and `--own-write TOOL` (repeatable), `--own-intent TOOL=TEXT` (repeatable), `--own-flow
FROM.FIELD:TO.PARAM` (repeatable), and `--mcp-command CMD`, which is `init`'s own
(`tests/test_o2_cli.py`).

Shapes decided here
-------------------

**1. `ProjectConfig.own`** is `None` without `[own]`, else `config.OwnConfig(file, format, name,
read, write, intents, flows)`: `format` defaults to `"auto"` and `name` to `None` (the plan then
names the set by the file's stem); `read` and `write` are tuples of tool names; `intents` a tuple
of `(tool, text)` pairs in the file's order; `flows` a tuple of `(from, field, to, param)`.

**2. One validation**, as the settings file's: a refusal is a `ConfigError` whose `.key` is the
dotted path (`own.format`, `own.flow`), the same from the file and from the flags, pinned against an
accepted control.  What needs the tool file (a tool name in `read`, `write`, `[own.intents]` or a
flow, the recipe or the custom knob and levels on this set) is checked when the plan is resolved, as
the settings file's shape 3 allows; reading a settings file stays pure.

**3. The plan.**  `resolve_plan(config, root=None)` reads the tool file from `root` (else the
working folder).  Its arms are own-tools arms (`generator_version` `own-1`): a recipe's are
`own.recipes.recipes_for(set)[recipe].arms`, and a recipe not offered on this set, or `card`, is
refused under `measure.preset`.  `Plan.own` carries `file` (absolute), `format`, `name`, `read`,
`write`, `intents`, `flows` (as `from`/`field`/`to`/`param` mappings), `file_digest`,
`source_format` and `tools` (the usable count).  `plan_hash` moves with what the tasks are made
from (the file's bytes and every `[own]` setting) and not with where the project sits.

**4. The run's eval config** for an own-tools plan names `own.export.OWN_TASKSET_ID` and carries
the plan's `own` whole.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

from tests.o1_support import fixture
from tests.o2_support import acme, acme_flows, config, export, recipes, runs

PROG = "poisson-tasks"
FLOW_A = "search_orders.orders[].order_id:get_order.order_id"
FLOW_B = "get_order.order_id:refund_order.order_id"
BASE = ["--provider", "openai", "--no-price", "--token-cap", "100000"]

OWN_TEXT = textwrap.dedent("""\
    [own]
    file = "tools.json"
    format = "mcp"
    name = "acme-support"
    read = ["get_order"]
    write = ["refund_order"]

    [own.intents]
    refund_order = "refund a customer's order"
    get_order = "look up an order"

    [[own.flow]]
    from = "search_orders"
    field = "orders[].order_id"
    to = "get_order"
    param = "order_id"

    [[own.flow]]
    from = "get_order"
    field = "order_id"
    to = "refund_order"
    param = "order_id"
""")


def base_text() -> str:
    return str(config().dump_config(config().config_from_init_args(BASE)))


def with_own(text: str = OWN_TEXT, recipe: str = "first-look") -> str:
    """The defaults' file with `[measure] preset` set to `recipe` and the `[own]` text after it."""
    base = base_text().replace('preset = "first-look"', f'preset = "{recipe}"', 1)
    return base + "\n" + text


def project(tmp_path: Path, name: str = "acme-mcp-tools-list.json") -> Path:
    (tmp_path / "tools.json").write_bytes(fixture(name))
    return tmp_path


def refusal_key(text: str, root: Path) -> str | None:
    cfg = config()
    try:
        cfg.resolve_plan(cfg.loads_config(text), root=root)
    except cfg.ConfigError as error:
        return str(error.key)
    return None


# --------------------------------------------------------------------------
# the table
# --------------------------------------------------------------------------


def test_the_own_table_reads_into_own_config_and_writes_back_the_same() -> None:
    cfg = config()
    made = cfg.loads_config(with_own())
    assert made.own == cfg.OwnConfig(
        file="tools.json", format="mcp", name="acme-support", read=("get_order",),
        write=("refund_order",),
        intents=(("refund_order", "refund a customer's order"), ("get_order", "look up an order")),
        flows=(("search_orders", "orders[].order_id", "get_order", "order_id"),
               ("get_order", "order_id", "refund_order", "order_id")))
    written = cfg.dump_config(made)
    assert cfg.loads_config(written) == made
    assert tomllib.loads(written)["own"] == tomllib.loads(OWN_TEXT)["own"]


def test_a_file_without_own_has_none_and_own_never_changes_the_tasks_table() -> None:
    """A guard for that decision: `[own]` is a table of its own and `[tasks]` is as the
    `test_fd1_*` tests pin it."""
    cfg = config()
    plain = cfg.loads_config(base_text())
    assert plain.own is None
    assert "own" not in tomllib.loads(cfg.dump_config(plain))
    mine = tomllib.loads(cfg.dump_config(cfg.loads_config(with_own())))
    theirs = tomllib.loads(cfg.dump_config(plain))
    assert mine["tasks"] == theirs["tasks"] and "own" not in mine["tasks"]
    assert {k: v for k, v in mine.items() if k != "own"} == theirs


def test_the_defaults_are_auto_and_no_name() -> None:
    made = config().loads_config(with_own('[own]\nfile = "tools.json"\n'))
    assert dataclasses.astuple(made.own) == ("tools.json", "auto", None, (), (), (), ())


# --------------------------------------------------------------------------
# the flags
# --------------------------------------------------------------------------

OWN_FLAGS = [
    ["--own-file", "tools.json"],
    ["--own-file", "tools.json", "--own-format", "openapi", "--own-name", "pets"],
    ["--own-file", "x/tools.mcp.json", "--own-read", "get_order", "--own-read", "list_channels",
     "--own-write", "refund_order"],
    ["--own-file", "tools.json", "--own-intent", "refund_order=refund a customer's order",
     "--own-intent", "get_order=look up an order: by its id"],
    ["--own-file", "tools.json", "--own-flow", FLOW_A, "--own-flow", FLOW_B],
]


def test_every_own_key_is_reachable_from_its_flag() -> None:
    cfg = config()
    made = cfg.config_from_init_args([*BASE, "--own-file", "t.json", "--own-format", "mcp",
                                      "--own-name", "acme", "--own-read", "a", "--own-read", "b",
                                      "--own-write", "c", "--own-intent", "a=one thing",
                                      "--own-intent", "c=x=y", "--own-flow", FLOW_A,
                                      "--own-flow", FLOW_B])
    assert made.own == cfg.OwnConfig(
        file="t.json", format="mcp", name="acme", read=("a", "b"), write=("c",),
        intents=(("a", "one thing"), ("c", "x=y")),
        flows=(("search_orders", "orders[].order_id", "get_order", "order_id"),
               ("get_order", "order_id", "refund_order", "order_id")))
    assert cfg.config_from_init_args(BASE).own is None


@pytest.mark.parametrize("flags", OWN_FLAGS, ids=["file", "format-name", "effects", "intents", "flows"])
def test_the_equivalent_command_writes_the_same_own_table(flags: list[str]) -> None:
    cfg = config()
    made = cfg.config_from_init_args([*BASE, *flags])
    written = cfg.dump_config(made)
    command = cfg.equivalent_init_command(made, prog=PROG)
    assert command[:3] == [PROG, "init", "--yes"] and "--own-file" in command
    assert cfg.dump_config(cfg.config_from_init_args(command[2:])) == written
    assert cfg.loads_config(written) == made


@pytest.mark.parametrize(
    "flags, key",
    [
        (["--own-format", "yaml"], "own.format"),
        (["--own-name", ""], "own.name"),
        (["--own-intent", "no equals sign"], "own.intents"),
        (["--own-flow", "search_orders.orders:get_order"], "own.flow"),
        (["--own-flow", "a:b.c"], "own.flow"),
    ],
    ids=["format", "empty-name", "intent", "flow-no-param", "flow-no-field"],
)
def test_a_flag_is_refused_under_the_key_it_sets(flags: list[str], key: str) -> None:
    cfg = config()
    assert cfg.config_from_init_args([*BASE, "--own-file", "tools.json"]).own is not None
    with pytest.raises(cfg.ConfigError) as refused:
        cfg.config_from_init_args([*BASE, "--own-file", "tools.json", *flags])
    assert refused.value.key == key


def test_an_own_flag_without_own_file_is_refused_under_own_file() -> None:
    cfg = config()
    with pytest.raises(cfg.ConfigError) as refused:
        cfg.config_from_init_args([*BASE, "--own-read", "get_order"])
    assert refused.value.key == "own.file"


# --------------------------------------------------------------------------
# the file's refusals, each beside its control
# --------------------------------------------------------------------------

READ_TIME = [
    ("[own]\nformat = \"mcp\"\n", "own.file"),
    ("[own]\nfile = \"tools.json\"\nformat = \"swagger\"\n", "own.format"),
    ("[own]\nfile = \"tools.json\"\nname = \"\"\n", "own.name"),
    ("[own]\nfile = \"tools.json\"\nread = \"get_order\"\n", "own.read"),
    ("[own]\nfile = \"tools.json\"\nread = [\"get_order\"]\nwrite = [\"get_order\"]\n", "own.write"),
    ("[own]\nfile = \"tools.json\"\n\n[own.intents]\nget_order = 3\n", "own.intents"),
    ("[own]\nfile = \"tools.json\"\n\n[[own.flow]]\nfrom = \"get_order\"\nfield = \"order_id\"\nto = \"refund_order\"\n", "own.flow"),
    ("[own]\nfile = \"tools.json\"\nfiles = \"tools.json\"\n", "own.files"),
]


@pytest.mark.parametrize("text, key", READ_TIME, ids=[key for _t, key in READ_TIME])
def test_a_refused_own_setting_names_its_key_when_the_file_is_read(text: str, key: str, tmp_path: Path) -> None:
    cfg = config()
    with pytest.raises(cfg.ConfigError) as refused:
        cfg.loads_config(with_own(text))
    assert refused.value.key == key
    assert refusal_key(with_own(), project(tmp_path)) is None


RESOLVE_TIME = [
    ("[own]\nfile = \"missing.json\"\n", "own.file"),
    ("[own]\nfile = \"tools.json\"\nread = [\"no_such_tool\"]\n", "own.read"),
    ("[own]\nfile = \"tools.json\"\nwrite = [\"no_such_tool\"]\n", "own.write"),
    ("[own]\nfile = \"tools.json\"\n\n[own.intents]\nno_such_tool = \"do it\"\n", "own.intents"),
    ("[own]\nfile = \"tools.json\"\n\n[[own.flow]]\nfrom = \"get_order\"\nfield = \"no_field\"\nto = \"refund_order\"\nparam = \"order_id\"\n", "own.flow"),
    ("[own]\nfile = \"tools.json\"\nformat = \"openapi\"\n", "own.format"),
]


@pytest.mark.parametrize("text, key", RESOLVE_TIME, ids=[f"{key}-{i}" for i, (_t, key) in enumerate(RESOLVE_TIME)])
def test_a_setting_that_needs_the_tool_file_is_refused_when_the_plan_is_resolved(
    text: str, key: str, tmp_path: Path
) -> None:
    root = project(tmp_path)
    flows = "".join(f"\n[[own.flow]]\nfrom = \"{a}\"\nfield = \"{f}\"\nto = \"{b}\"\nparam = \"{p}\"\n"
                    for a, f, b, p in (("search_orders", "orders[].order_id", "get_order", "order_id"),
                                       ("get_order", "order_id", "refund_order", "order_id")))
    if "[[own.flow]]" not in text:
        text += flows
    assert refusal_key(with_own(text), root) == key
    assert refusal_key(with_own('[own]\nfile = "tools.json"\n' + flows), root) is None


def test_a_recipe_not_offered_on_this_set_is_refused_under_measure_preset(tmp_path: Path) -> None:
    root = project(tmp_path)
    flows = "".join(f'\n[[own.flow]]\nfrom = "{a}"\nfield = "{f}"\nto = "{b}"\nparam = "{p}"\n'
                    for a, f, b, p in (("search_orders", "orders[].order_id", "get_order", "order_id"),
                                       ("get_order", "order_id", "refund_order", "order_id")))
    accepted = 0
    for declared, text in (((), '[own]\nfile = "tools.json"\n'), (acme_flows(), '[own]\nfile = "tools.json"\n' + flows)):
        table = recipes().recipes_for(acme(), flows=declared)
        for name, recipe in table.items():
            found = refusal_key(with_own(text, recipe=name), root)
            if recipe.offered:
                assert found is None, name
                accepted += 1
            else:
                assert found == "measure.preset", name
    assert accepted


# --------------------------------------------------------------------------
# the plan
# --------------------------------------------------------------------------


def test_the_plan_of_a_recipe_is_its_arms_on_this_set_and_carries_the_settings(tmp_path: Path) -> None:
    cfg = config()
    root = project(tmp_path)
    made = cfg.loads_config(with_own())
    plan = cfg.resolve_plan(made, root=root)
    from poisson_tasks import own
    from tests.o2_support import generator

    toolset = own.apply_effects(own.read_tools(fixture("acme-mcp-tools-list.json"), name="acme-support").toolset,
                                read=["get_order"], write=["refund_order"])
    expected_arms = recipes().recipes_for(toolset, flows=acme_flows())["first-look"].arms
    from poisson_tasks.knobs import arm_id

    assert [arm_id(spec) for spec in plan.arms] == list(expected_arms)
    assert {spec.generator_version for spec in plan.arms} == {generator().GENERATOR_VERSION}
    from poisson_tasks.calibration import seed_list

    assert plan.seeds == seed_list()[: made.tasks.per_level]
    assert dict(plan.own) == {
        "file": str((root / "tools.json").resolve()), "format": "mcp", "name": "acme-support",
        "read": ["get_order"], "write": ["refund_order"],
        "intents": {"refund_order": "refund a customer's order", "get_order": "look up an order"},
        "flows": [{"from": "search_orders", "field": "orders[].order_id", "to": "get_order", "param": "order_id"},
                  {"from": "get_order", "field": "order_id", "to": "refund_order", "param": "order_id"}],
        "file_digest": toolset.file_digest, "source_format": "mcp", "tools": 5,
    }


def test_the_set_is_named_by_the_files_stem_when_no_name_is_given(tmp_path: Path) -> None:
    cfg = config()
    root = project(tmp_path)
    text = with_own('[own]\nfile = "tools.json"\n' + "".join(
        f'\n[[own.flow]]\nfrom = "{a}"\nfield = "{f}"\nto = "{b}"\nparam = "{p}"\n'
        for a, f, b, p in (("get_order", "order_id", "refund_order", "order_id"),)))
    assert cfg.resolve_plan(cfg.loads_config(text), root=root).own["name"] == "tools"


def test_the_plan_hash_moves_with_what_the_tasks_are_made_from_and_not_with_where_they_sit(tmp_path: Path) -> None:
    cfg = config()
    first = tmp_path / "a"
    first.mkdir()
    project(first)
    second = tmp_path / "b"
    second.mkdir()
    shutil.copy(first / "tools.json", second / "tools.json")
    made = cfg.loads_config(with_own())
    here = cfg.plan_hash(cfg.resolve_plan(made, root=first))
    assert cfg.plan_hash(cfg.resolve_plan(made, root=second)) == here
    (second / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json") + b"\n")
    assert cfg.plan_hash(cfg.resolve_plan(made, root=second)) != here
    moved = {
        "name": OWN_TEXT.replace('name = "acme-support"', 'name = "acme"'),
        "read": OWN_TEXT.replace('read = ["get_order"]', 'read = ["get_order", "list_channels"]'),
        "write": OWN_TEXT.replace('write = ["refund_order"]', 'write = ["refund_order", "notify_customer"]'),
        "intent": OWN_TEXT.replace('"look up an order"', '"look an order up"'),
        "flow": OWN_TEXT.split("[[own.flow]]")[0] + "[[own.flow]]" + OWN_TEXT.split("[[own.flow]]")[2],
    }
    for what, text in moved.items():
        other = cfg.plan_hash(cfg.resolve_plan(cfg.loads_config(with_own(text)), root=first))
        assert other != here, what


def test_the_eval_config_of_an_own_tools_arm_names_the_own_taskset_and_carries_the_settings(tmp_path: Path) -> None:
    cfg = config()
    plan = cfg.resolve_plan(cfg.loads_config(with_own()), root=project(tmp_path))
    for spec in plan.arms:
        made = runs().verifiers_config(plan, spec)
        taskset = made["env"]["taskset"]
        assert taskset["id"] == export().OWN_TASKSET_ID
        assert taskset["own"] == dict(plan.own)
        assert taskset["arm"] == dataclasses.asdict(spec) and taskset["seeds"] == list(plan.seeds)


def test_reading_a_settings_file_with_own_imports_no_verifiers_and_none_of_the_generator() -> None:
    code = textwrap.dedent(f"""
        import sys
        from poisson_tasks import config
        made = config.loads_config({with_own()!r})
        config.dump_config(made)
        bad = sorted(m for m in ("verifiers", "poisson_tasks.tasks", "poisson_tasks.own.generator",
                                 "poisson_tasks.calibration", "poisson_tasks.export") if m in sys.modules)
        print(bad)
    """)
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "[]"


PLAN_FIELDS = ("preset", "arms", "seeds", "attempts", "model", "decoding", "max_model_calls")


@pytest.mark.parametrize("argv", [[], ["--recipe", "card"],
                                  ["--provider", "vllm", "--model", "Qwen/Qwen3-8B", "--token-cap", "1000"]],
                         ids=["first-look", "card", "vllm"])
def test_a_built_in_plan_keeps_its_fields_and_its_hash(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """A run folder is found by its plan's hash, so a plan with no `[own]` hashes as it did before
    own tools:  the identity `config.plan_hash` documents, with no `own` in it, and `own` is
    `None`."""
    import hashlib
    import json

    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    cfg = config()
    plan = cfg.resolve_plan(cfg.config_from_init_args(argv))
    assert plan.own is None
    assert [f.name for f in dataclasses.fields(plan)][: len(PLAN_FIELDS)] == list(PLAN_FIELDS)
    identity = {
        "plan": 1, "arms": [dataclasses.asdict(spec) for spec in plan.arms], "seeds": list(plan.seeds),
        "attempts": plan.attempts, "model": plan.model.name, "base_url": plan.model.base_url,
        "decoding": dict(plan.decoding), "max_model_calls": plan.max_model_calls,
    }
    text = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert cfg.plan_hash(plan) == hashlib.sha256(text.encode("ascii")).hexdigest()
