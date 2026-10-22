"""The settings file's clauses that its build added and no frozen test pinned, frozen as tests.

The mutation pass on the settings file's build named eleven clauses of `config.py` and the export
arm validator that the build has and the frozen tests do not ask for (its table's `b-` rows), and
it was decided on 2026-10-03 that a change of tests alone pins them, with the five questions they
rest on decided as built.  The `config.py` ones are here; the export validator's are in
`tests/test_fd1_export_build_clauses.py`.

Each refusal is pinned by its `.key` against an accepted control that differs only in the clause
under test, and by a message of one line that names the setting.  Nothing else in a message is
pinned.

- A generator version reaches the first look's arms, as it reaches a custom plan's.
- A seed is a whole number from 0 to 2**32 - 1, the generator's seed space; one outside it is
  refused when the file is read.
- `per_level` and `seeds` together are refused (under `tasks.seeds`): a plan takes its tasks from
  one of them.
- The published model's price is prefilled on the OpenAI preset only (decided): not on
  Anthropic's, nor on another endpoint serving a model of that name.
- The plan's identity leaves out the measure preset's name, the provider and the key variable
  (decided): the same tasks against the same model at the same endpoint are the same run.
- A key variable is a variable's name (`[A-Za-z_][A-Za-z0-9_]*`) as well as holding `API_KEY`:
  `$OPENAI_API_KEY` or `OPENAI_API_KEY=...` is refused, not looked up as a variable no shell can
  set, and not written into the file with a key after it.
- `top_p` is above 0, as `temperature` is: 0 is refused.
- `read_on` written as a TOML date reads as the same date written as text.
- A priced file with a token cap and no dollar cap has no equivalent `init` command
  (decided): `equivalent_init_command` refuses it under `limits.spend_usd`.
"""

from __future__ import annotations

import importlib
import textwrap
from collections.abc import Iterator
from typing import Any

import pytest


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


def arms() -> Any:
    return importlib.import_module("poisson_tasks.arms")


# The settings file with its comments removed: what `init` writes for the openai preset's defaults.
BASE = textwrap.dedent("""\
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


def edit(old: str, new: str, text: str = BASE) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def refused(text: str, key: str) -> Any:
    """The `ConfigError` reading `text` raises: under `key`, in one line naming the setting."""
    with pytest.raises(config().ConfigError) as error:
        config().loads_config(text)
    assert_names(error.value, key)
    return error.value


def assert_names(error: Any, key: str) -> None:
    message = str(error)
    assert error.key == key, (error.key, message)
    assert "\n" not in message, message
    assert key.rsplit(".", 1)[-1] in message, (key, message)


def plan_of(text: str) -> Any:
    return config().resolve_plan(config().loads_config(text))


@pytest.fixture(autouse=True)
def _no_openai_base_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The OpenAI preset's endpoint is its own, whatever the shell running the suite says."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    yield


# --------------------------------------------------------------------------
# the plan
# --------------------------------------------------------------------------


def test_a_generator_version_reaches_the_first_looks_arms() -> None:
    plan = plan_of(edit("attempts = 1", 'attempts = 1\ngenerator_version = "tg-m3-v1"'))
    assert list(plan.arms) == [
        arms().arm_from_id(f"depth:d{level}", generator_version="tg-m3-v1") for level in (1, 3, 8)
    ]


# The plan's identity is what runs; these name what runs the same and only reads differently.
SAME_RUN = {
    "custom-at-the-first-looks-levels": edit(
        'preset = "first-look"', 'preset = "custom"\nknob = "depth"\nlevels = [1, 3, 8]'
    ),
    "another-provider-at-the-same-endpoint": edit(
        'provider = "openai"', 'provider = "openai-compatible"'
    ),
    "another-key-variable": edit('api_key_env = "OPENAI_API_KEY"', 'api_key_env = "MY_API_KEY"'),
}


@pytest.mark.parametrize("what", sorted(SAME_RUN))
def test_the_plan_hash_leaves_out_the_preset_the_provider_and_the_key_variable(what: str) -> None:
    base, other = plan_of(BASE), plan_of(SAME_RUN[what])
    assert other.arms == base.arms and other.seeds == base.seeds
    assert config().plan_hash(other) == config().plan_hash(base)


# --------------------------------------------------------------------------
# [tasks]
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outside", "edge"), [(-1, 0), (2**32, 2**32 - 1)], ids=["below-0", "past-32-bits"]
)
def test_a_seed_outside_the_generators_seed_space_is_refused(outside: int, edge: int) -> None:
    refused(edit("per_level = 10", f"seeds = [404, {outside}]"), "tasks.seeds")
    accepted = config().loads_config(edit("per_level = 10", f"seeds = [404, {edge}]"))
    assert accepted.tasks.seeds == (404, edge)


def test_per_level_and_seeds_together_are_refused() -> None:
    refused(edit("per_level = 10", "per_level = 10\nseeds = [404, 55]"), "tasks.seeds")
    assert config().loads_config(BASE).tasks.per_level == 10
    assert config().loads_config(edit("per_level = 10", "seeds = [404, 55]")).tasks.seeds == (
        404,
        55,
    )


# --------------------------------------------------------------------------
# [model]
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["--provider", "anthropic", "--model", "gpt-5-nano-2025-08-07"],
        [
            "--provider",
            "openai-compatible",
            "--model",
            "gpt-5-nano-2025-08-07",
            "--base-url",
            "https://gateway.example.test/v1",
            "--api-key-env",
            "GATEWAY_API_KEY",
        ],
    ],
    ids=["anthropic", "another-endpoint"],
)
def test_the_published_models_price_is_prefilled_on_the_openai_preset_only(
    argv: list[str],
) -> None:
    elsewhere = config().config_from_init_args(argv)
    assert elsewhere.model.price is None
    assert elsewhere.limits.spend_usd is None and elsewhere.limits.tokens is not None
    openai = config().config_from_init_args(["--model", "gpt-5-nano-2025-08-07"])
    assert openai.model.price is not None and openai.limits.spend_usd is not None


@pytest.mark.parametrize(
    "name",
    [
        "$OPENAI_API_KEY",
        "OPENAI_API_KEY=placeholder",
        "OPENAI API_KEY",
        "1_API_KEY",
    ],
    ids=["shell-form", "an-assignment", "a-space", "a-leading-digit"],
)
def test_a_key_variable_that_is_not_a_variables_name_is_refused(name: str) -> None:
    refused(edit('api_key_env = "OPENAI_API_KEY"', f'api_key_env = "{name}"'), "model.api_key_env")
    for control in ("OPENAI_API_KEY", "_my_api_key_2"):
        accepted = config().loads_config(
            edit('api_key_env = "OPENAI_API_KEY"', f'api_key_env = "{control}"')
        )
        assert accepted.model.api_key_env == control


def test_read_on_written_as_a_toml_date_is_that_date() -> None:
    as_date = config().loads_config(edit('read_on = "2026-09-25"', "read_on = 2026-09-25"))
    assert as_date == config().loads_config(BASE)


# --------------------------------------------------------------------------
# [decoding]
# --------------------------------------------------------------------------


@pytest.mark.parametrize("zero", ["0", "0.0"])
def test_top_p_zero_is_refused(zero: str) -> None:
    refused(edit("top_p = 1.0", f"top_p = {zero}"), "decoding.top_p")
    assert config().loads_config(edit("top_p = 1.0", "top_p = 0.01")).decoding.top_p == 0.01


# --------------------------------------------------------------------------
# the equivalent command
# --------------------------------------------------------------------------


def test_a_priced_file_with_no_dollar_cap_has_no_equivalent_command() -> None:
    tokens_only = config().loads_config(edit("spend_usd = 1.00", "tokens = 500000"))
    assert tokens_only.model.price is not None and tokens_only.limits.spend_usd is None
    with pytest.raises(config().ConfigError) as error:
        config().equivalent_init_command(tokens_only, prog="poisson-tasks")
    assert_names(error.value, "limits.spend_usd")
    both = config().loads_config(edit("spend_usd = 1.00", "spend_usd = 1.00\ntokens = 500000"))
    assert "--spend-cap" in config().equivalent_init_command(both, prog="poisson-tasks")
