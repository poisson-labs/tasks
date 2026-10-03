"""A refused value in `tasks.toml` carries the line it is written on.

**This file waits on a yes/no.**  The plan's FD1.4 gives a `ConfigError` its `.line` "wherever
`tomllib` reports one", and `tomllib` reports a line only for a file that is not TOML (pinned in
`tests/test_fd1_config.py`).  The spec's own example of a refused value carries one:
`tasks.toml line 14: level 4 is not a depth level; the levels are 1, 2, 3, 5 and 8`.  To give it,
the reader finds the line of the key it refuses in the text itself.  This file asks for that, for
an unknown key or table as well as a bad value.  It is its own commit, so that a "no" drops it
whole.

The line is the 1-based line on which the offending key is written, or, for a table, its header.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from tests.test_fd1_config import SPEC_FILE, custom, edit


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


CASES = [
    pytest.param(custom('preset = "custom"\nknob = "depth"\nlevels = [1, 4]'), "levels = [1, 4]",
                 id="spec-example"),
    pytest.param(edit("per_level = 10", "per_level = 61"), "per_level = 61", id="out-of-range"),
    pytest.param(edit('provider = "openai"', 'provider = "openia"'), 'provider = "openia"',
                 id="a-choice"),
    pytest.param(edit("attempts = 1", 'attempts = "1"'), 'attempts = "1"', id="a-type"),
    pytest.param(edit("concurrency = 8", "concurrency = 8\ntokns = 5000"), "tokns = 5000",
                 id="an-unknown-key"),
    pytest.param(edit("[measure]", "[mesure]"), "[mesure]", id="an-unknown-table"),
    pytest.param(edit('api_key_env = "OPENAI_API_KEY"', 'api_key_env = "OPENAI_KEY"'),
                 'api_key_env = "OPENAI_KEY"', id="a-key-variable"),
]


@pytest.mark.parametrize(("text", "written"), CASES)
def test_a_refused_key_carries_the_line_it_is_written_on(text: str, written: str) -> None:
    line = text.splitlines().index(written) + 1
    with pytest.raises(config().ConfigError) as error:
        config().loads_config(text)
    assert error.value.line == line, (error.value.line, line)
    assert str(line) in str(error.value)
    assert text != SPEC_FILE
