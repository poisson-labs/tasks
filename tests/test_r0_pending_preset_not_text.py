"""A preset that is not text is refused in one line, frozen as a test.

The preset key, from the decision on the build's untested clauses (decided 2026-10-08: one part
pinned).  `[measure] preset` takes a recipe's name or `custom`, both text.  The
build looks a preset up among the recipes only when it is text; a value that is not, such as a list
or a table, would otherwise reach that lookup and raise `TypeError` (a list is unhashable) instead of
the reader's one-line refusal under `measure.preset`.

The bug this catches: the build's text check dropped, so `preset = [1]` raises `TypeError`
(a row of its mutation pass).  It passes on `main` before the recipes, where no recipe lookup
exists: the test pins behaviour the recipes must keep, not behaviour they add.
"""

from __future__ import annotations

import importlib
import textwrap
from typing import Any

import pytest

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


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


def test_a_preset_that_is_not_text_is_refused_in_one_line() -> None:
    """A list, a table, a number and a boolean, each refused under `measure.preset` in one line
    that names the key; the file with a recipe's name is the control."""
    assert config().loads_config(FILE).measure.preset == "first-look"
    for value in ("[1]", '["first-look"]', '{ name = "first-look" }', "1", "true"):
        text = FILE.replace('preset = "first-look"', f"preset = {value}")
        assert text.count(f"preset = {value}") == 1
        with pytest.raises(config().ConfigError) as error:
            config().loads_config(text)
        message = str(error.value)
        assert error.value.key == "measure.preset", (value, error.value.key)
        assert "\n" not in message and "preset" in message, (value, message)
