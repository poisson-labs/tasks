"""The recipes in `tasks.toml` and init's `--recipe`, frozen as tests.

The invariants:  `[measure] preset` keeps its name and takes every recipe name and `custom`, with
the frozen `test_fd1_*` tests green; `--recipe` is the flag for init's question 6, and `--measure`
stays as its alias for one release.  The invariant-to-test table for all of the recipes is in
`tests/test_r0_recipes.py`.

Shapes decided here
-------------------

**1. A recipe is taken when it is offered.**  `preset` takes each recipe `RECIPES` offers, and
`custom`.  A recipe not offered is refused under `measure.preset`, in one line naming the recipe
and each of its knobs that has not shipped, from the file and from either flag alike; a name that
is no recipe gets the reader's usual refusal, with the nearest name offered.

**2. The file says what it offers.**  The comment beside `preset` lists the recipes offered and
then `custom`, in `RECIPES`' order, so the file never names a recipe whose knobs have not shipped.

**3. A recipe sets init's tasks per level and attempts** ("questions 7 and 8 are
skipped and their values shown"); `--tasks-per-level`, `--seeds` and `--attempts` still override.
`custom` keeps init's defaults, ten tasks and one attempt.

**4. A recipe resolves to its own arms**, in its order, strict, at the file's generator version;
`card` is still `calibration.arm_specs()`.

**5. `--measure` is `--recipe` under another name.**  The two give the same config; given both,
the last one given counts, as a flag given twice does.  `INIT_FLAGS` lists `--recipe` for
`measure.preset`, so a refusal names `--recipe`, and `equivalent_init_command` writes `--recipe`:
a command that outlives the alias's one release still works.

**What "after a knob ships" means here.**  The tests that need a recipe offered that is not
offered today run in a fresh interpreter that sets `arms.SHIPPED_KNOBS` and
`arms.RECIPES = arms.recipe_table(...)` before `poisson_tasks.config` is imported: the state the
package is in once the probe's outcome edits `SHIPPED_KNOBS`.
"""

from __future__ import annotations

import json
import textwrap
import tomllib
from typing import Any

import pytest

from poisson_tasks.arms import DEFAULT_GENERATOR_VERSION
from poisson_tasks.knobs import arm_id
from tests.r0_support import (
    NAMES,
    PROBE_KNOBS,
    arms,
    cal,
    config,
    fresh,
    full_design,
    tasks_and_attempts,
)

# The settings file with its comments removed, as `tests/test_fd1_config.py` holds it.
FILE = textwrap.dedent("""\
    version = 1

    [model]
    provider = "openai"
    name = "gpt-5-nano-2025-08-07"
    base_url = "https://api.openai.com/v1"
    api_key_env = "OPENAI_API_KEY"

    [model.price]
    input = 0.05
    cached_input = 0.005
    output = 0.40
    read_on = "2026-09-25"

    [measure]
    preset = "first-look"

    [tasks]
    per_level = 10
    attempts = 1

    [decoding]
    temperature = 1.0
    top_p = 1.0
    reasoning_effort = "low"
    max_tokens = 2048

    [limits]
    spend_usd = 1.00
    max_model_calls = 32
    concurrency = 8

    [output]
    runs = "runs"
    tasks = "tasks"
""")
MEASURE = '[measure]\npreset = "first-look"\n'
TASKS = "[tasks]\nper_level = 10\nattempts = 1\n"


def with_measure(measure: str, tasks: str = "per_level = 10\nattempts = 1") -> str:
    assert FILE.count(MEASURE) == 1 and FILE.count(TASKS) == 1
    return FILE.replace(MEASURE, f"[measure]\n{measure}\n").replace(TASKS, f"[tasks]\n{tasks}\n")


def recipe_file(name: str, *, version: str | None = None) -> str:
    """The file for one recipe: `card`'s with no `[tasks]` keys, the others' at their sizes."""
    if name == "card":
        return with_measure(f'preset = "{name}"', "")
    tasks, attempts = tasks_and_attempts(name)
    lines = f"per_level = {tasks}\nattempts = {attempts}"
    if version is not None:
        lines += f'\ngenerator_version = "{version}"'
    return with_measure(f'preset = "{name}"', lines)


def offered_names() -> list[str]:
    return [name for name, recipe in arms().RECIPES.items() if recipe.offered]


def preset_comment(text: str) -> list[str]:
    """The choices the written file's comment beside `preset` lists."""
    (line,) = [line for line in text.splitlines() if line.startswith("preset = ")]
    return [word.strip() for word in line.split("#", 1)[1].split("|")]


def refusal(error: Any) -> dict[str, Any]:
    return {"key": error.key, "message": str(error), "suggestion": error.suggestion}


def after_shipping(shipped: tuple[str, ...], body: str) -> Any:
    """Run `body` with `shipped` as the shipped knobs, `config` imported after; give its JSON."""
    head = textwrap.dedent(f"""\
        import json
        import poisson_tasks.arms as arms
        arms.SHIPPED_KNOBS = {shipped!r}
        arms.RECIPES = arms.recipe_table(arms.SHIPPED_KNOBS)
        from poisson_tasks import config
        from poisson_tasks.knobs import arm_id

        def refusal(argv=None, text=None):
            try:
                if text is not None:
                    config.loads_config(text)
                else:
                    config.config_from_init_args(argv)
            except config.ConfigError as error:
                return {{"key": error.key, "message": str(error), "suggestion": error.suggestion}}
            return None
    """)
    out = fresh(head + textwrap.dedent(body))
    return json.loads(out.strip().splitlines()[-1])


# --------------------------------------------------------------------------
# the preset key
# --------------------------------------------------------------------------


def test_every_recipe_offered_is_a_preset_and_reads_back() -> None:
    """Shapes 1 and 4: here, and with every knob shipped.  Bugs caught: the preset's values left
    at first-look, card and custom, so a shipped recipe is refused; a new recipe resolved down
    the custom path (depth's arms); its arms resolved leaky, or at the default generator version
    rather than the file's."""
    for name in offered_names():
        made = config().loads_config(recipe_file(name))
        assert made.measure == config().MeasureConfig(preset=name), name
        assert config().loads_config(config().dump_config(made)) == made, name
        plan = config().resolve_plan(made)
        assert tuple(arm_id(spec) for spec in plan.arms) == tuple(arms().RECIPES[name].arms), name
        if name == "card":
            assert plan.arms == tuple(cal().arm_specs())
        else:
            assert {spec.strictness for spec in plan.arms} == {"strict"}, name

    files = {name: recipe_file(name, version=None if name == "card" else "0") for name in NAMES}
    got = after_shipping(
        PROBE_KNOBS,
        f"""\
        out = {{}}
        for name, text in {files!r}.items():
            made = config.loads_config(text)
            again = config.loads_config(config.dump_config(made))
            plan = config.resolve_plan(made)
            out[name] = {{
                "preset": made.measure.preset,
                "custom_keys": [made.measure.knob, made.measure.levels],
                "reads_back": again == made,
                "arms": [arm_id(spec) for spec in plan.arms],
                "strictness": sorted({{spec.strictness for spec in plan.arms}}),
                "versions": sorted({{spec.generator_version for spec in plan.arms}}),
                "seeds": len(plan.seeds),
                "attempts": plan.attempts,
            }}
        print(json.dumps(out))
    """,
    )
    for name in NAMES:
        tasks, attempts = tasks_and_attempts(name)
        version = DEFAULT_GENERATOR_VERSION if name == "card" else "0"
        assert got[name] == {
            "preset": name,
            "custom_keys": [None, None],
            "reads_back": True,
            "arms": list(full_design(name)),
            "strictness": ["strict"],
            "versions": [version],
            "seeds": tasks,
            "attempts": attempts,
        }, name


def test_a_recipe_not_offered_is_refused_in_one_line_naming_it_and_its_knobs() -> None:
    """Shape 1, here and in two other states: nothing shipped, and similarity alone.  Bugs
    caught: every recipe name taken whether offered or not; the refusal given as "not a recipe",
    naming no knob it waits on; the flags taking what the file refuses."""

    def check(name: str, waiting: list[str], refusals: list[Any]) -> None:
        for found in refusals:
            assert found is not None, name
            assert found["key"] == "measure.preset", (name, found)
            assert "\n" not in found["message"], found
            assert name in found["message"], found
            for knob in waiting:
                assert knob in found["message"], (knob, found)

    not_offered = {
        name: list(recipe.waiting) for name, recipe in arms().RECIPES.items() if not recipe.offered
    }
    for name, waiting in not_offered.items():
        refusals = []
        for argv in (["--recipe", name], ["--measure", name]):
            with pytest.raises(config().ConfigError) as error:
                config().config_from_init_args(argv)
            refusals.append(refusal(error.value))
        with pytest.raises(config().ConfigError) as error:
            config().loads_config(recipe_file(name))
        refusals.append(refusal(error.value))
        check(name, waiting, refusals)

    for shipped in ((), ("similarity",)):
        table = arms().recipe_table(shipped)
        waiting = {
            name: list(recipe.waiting) for name, recipe in table.items() if not recipe.offered
        }
        assert waiting, shipped
        files = {name: recipe_file(name) for name in waiting}
        got = after_shipping(
            shipped,
            f"""\
            out = {{}}
            for name, text in {files!r}.items():
                out[name] = [refusal(argv=["--recipe", name]), refusal(argv=["--measure", name]),
                             refusal(text=text)]
            print(json.dumps(out))
        """,
        )
        assert set(got) == set(waiting), shipped
        for name, refusals in got.items():
            check(name, waiting[name], refusals)


def test_the_written_file_lists_only_the_recipes_offered() -> None:
    """Shape 2.  Bugs caught: the comment listing all eight recipes, so the file offers a recipe
    whose knobs have not shipped; the comment left at first-look, card and custom once a recipe
    ships."""
    text = config().dump_config(config().config_from_init_args([]))
    assert preset_comment(text) == [*offered_names(), "custom"]
    got = after_shipping(
        ("faults",),
        """\
        print(json.dumps(config.dump_config(config.config_from_init_args([]))))
    """,
    )
    assert preset_comment(got) == ["first-look", "error-recovery", "profile", "card", "custom"]


def test_a_recipe_sets_inits_tasks_and_attempts_and_the_flags_override() -> None:
    """Shape 3.  Bugs caught: every recipe but card at ten tasks and one attempt (`profile` is
    twenty and two); a recipe's sizes beating the flags given beside it."""
    for name in offered_names():
        tasks = config().config_from_init_args(["--recipe", name]).tasks
        per_level, attempts = tasks_and_attempts(name)
        assert (tasks.per_level, tasks.seeds, tasks.attempts) == (per_level, None, attempts), name

    got = after_shipping(
        PROBE_KNOBS,
        f"""\
        def sizes(argv):
            tasks = config.config_from_init_args(argv).tasks
            return [tasks.per_level, list(tasks.seeds or []), tasks.attempts]
        out = {{name: sizes(["--recipe", name]) for name in {list(NAMES)!r}}}
        out["profile, overridden"] = sizes(
            ["--recipe", "profile", "--tasks-per-level", "7", "--attempts", "3"])
        out["profile, seeds"] = sizes(["--recipe", "profile", "--seeds", "9,404"])
        out["custom"] = sizes(["--recipe", "custom"])
        print(json.dumps(out))
    """,
    )
    for name in NAMES:
        tasks, attempts = tasks_and_attempts(name)
        assert got[name] == [tasks, [], attempts], name
    assert got["profile"] == [20, [], 2]
    assert got["profile, overridden"] == [7, [], 3]
    assert got["profile, seeds"] == [None, [9, 404], 2]
    assert got["custom"] == [10, [], 1]


def test_custom_is_unchanged() -> None:
    """`preset = "custom"` reads, writes and resolves as it did before recipes.  Bugs caught:
    `custom` dropped from the preset's values when the recipes join them; `--recipe custom` not
    taken; custom's levels defaulted from a recipe (`first-look`'s 1, 3, 8) rather than the
    knob's every level."""
    argv = [
        "--recipe",
        "custom",
        "--knob",
        "distractor",
        "--levels",
        "0,8",
        "--controls",
        "--strictness",
        "leaky",
    ]
    made = config().config_from_init_args(argv)
    assert made.measure == config().MeasureConfig(
        preset="custom", knob="distractor", levels=(0, 8), controls=True, strictness="leaky"
    )
    assert (made.tasks.per_level, made.tasks.attempts) == (10, 1)
    written = config().dump_config(made)
    assert tomllib.loads(written)["measure"] == {
        "preset": "custom",
        "knob": "distractor",
        "levels": [0, 8],
        "controls": True,
        "strictness": "leaky",
    }
    assert config().loads_config(written) == made
    plan = config().resolve_plan(made)
    assert [arm_id(spec) for spec in plan.arms] == [
        "distractor:r0@k16",
        "distractor:r8@k16",
        "distractor:r0+len(r8)@k16",
    ]
    assert {spec.strictness for spec in plan.arms} == {"leaky"}

    plain = config().config_from_init_args(["--recipe", "custom"]).measure
    assert plain == config().MeasureConfig(
        preset="custom", knob="depth", levels=(1, 2, 3, 5, 8), controls=False, strictness="strict"
    )
    from_file = config().loads_config(with_measure('preset = "custom"')).measure
    assert from_file == plain


# --------------------------------------------------------------------------
# --recipe, and --measure its alias
# --------------------------------------------------------------------------

# The flags given beside each value; the card's design fixes its tasks, so it takes only its own.
EXTRAS: dict[str, list[list[str]]] = {
    "card": [[], ["--tasks-per-level", "60", "--attempts", "5"]],
    "custom": [
        [],
        ["--knob", "distractor", "--levels", "2,14", "--controls"],
        ["--levels", "1,8", "--controls", "--strictness", "leaky", "--attempts", "2"],
    ],
}


def test_recipe_and_measure_give_the_same_config() -> None:
    """Shape 5.  Bugs caught: `--measure` dropped; `--measure` taking only the three old values;
    the alias refusing a bad value under another key."""
    for name in [*offered_names(), "custom"]:
        for extra in EXTRAS.get(name, [[], ["--tasks-per-level", "5"]]):
            by_recipe = config().config_from_init_args(["--recipe", name, *extra])
            by_measure = config().config_from_init_args(["--measure", name, *extra])
            assert by_recipe == by_measure, (name, extra)
            assert by_recipe.measure.preset == name
            assert config().dump_config(by_recipe) == config().dump_config(by_measure)
    found = []
    for flag in ("--recipe", "--measure"):
        with pytest.raises(config().ConfigError) as error:
            config().config_from_init_args([flag, "frist-look"])
        found.append((error.value.key, error.value.suggestion))
    assert found == [("measure.preset", "first-look")] * 2

    got = after_shipping(
        PROBE_KNOBS,
        f"""\
        out = {{}}
        for name in {list(NAMES)!r}:
            a = config.config_from_init_args(["--recipe", name])
            b = config.config_from_init_args(["--measure", name])
            out[name] = [a == b, a.measure.preset, config.dump_config(a) == config.dump_config(b)]
        print(json.dumps(out))
    """,
    )
    assert got == {name: [True, name, True] for name in NAMES}


def test_recipe_is_the_flag_init_names_and_writes() -> None:
    """Shape 5.  Bugs caught: `--recipe` missing from `INIT_FLAGS`, or listed after
    `--measure`, so a refusal names the alias; `equivalent_init_command` still writing
    `--measure`, which stops working when the alias goes."""
    flags = config().INIT_FLAGS
    setting = [flag for flag in flags if flag.key == "measure.preset"]
    assert config().InitFlag("--recipe", "measure.preset", "choice", "first-look") in setting
    assert "--measure" in {flag.flag for flag in setting}
    for flag in ("--recipe", "--measure"):
        with pytest.raises(config().ConfigError) as error:
            config().config_from_init_args([flag, "frist-look"])
        assert "--recipe" in str(error.value), str(error.value)

    for argv in ([], ["--recipe", "card"], ["--measure", "custom", "--knob", "distractor"]):
        made = config().config_from_init_args(argv)
        command = config().equivalent_init_command(made, prog="poisson-tasks")
        assert "--measure" not in command, command
        at = command.index("--recipe")
        assert command[at + 1] == made.measure.preset, command
        assert config().config_from_init_args(command[2:]) == made


def test_the_last_of_recipe_and_measure_wins() -> None:
    """Shape 5: an alias is the same flag, and a flag given twice keeps its last value.  Bugs
    caught: `--recipe` always read before `--measure`, or always after."""
    assert (
        config().config_from_init_args(["--recipe", "card", "--measure", "custom"]).measure.preset
        == "custom"
    )
    assert (
        config().config_from_init_args(["--measure", "card", "--recipe", "custom"]).measure.preset
        == "custom"
    )
    assert (
        config().config_from_init_args(["--measure", "custom", "--recipe", "card"]).measure.preset
        == "card"
    )
