"""Pending a decision: the refusal of a key variable written as a shell would write it, reworded.

The pinning work (decided yes, 2026-10-05) and reading your own tools flagged it:
`api_key_env = "$OPENAI_API_KEY"` is refused, rightly, with the words "the variable's name must
contain API_KEY", and the name does contain `API_KEY`: the fault is that it is not a variable's
name.  The words live in `config.py`, which the command's build touches for its messages; the
`test_fd1_*` frozen test pins the refusal by its key and its one line, not by its words, so it is
unchanged.

**Proposed, and recommended:**
- a value that is a variable's name once a leading `$` (or `${…}`) or a trailing `=…` is taken
  off: `<setting> is "$OPENAI_API_KEY", which is not a variable's name; write the name alone, as
  OPENAI_API_KEY`, with `.suggestion` that name;
- any other value that is not a variable's name: `<setting> is "1_API_KEY", which is not a
  variable's name: a name is letters, digits and _, and does not start with a digit`;
- a variable's name without `API_KEY` keeps today's words.

**A no** drops this file's commit, and the message stays as it is.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fd5_support import World, config, error_lines, invoke, prog, world

__all__ = ["prog", "world"]

CASES = {
    "$OPENAI_API_KEY": "OPENAI_API_KEY",
    "${OPENAI_API_KEY}": "OPENAI_API_KEY",
    "OPENAI_API_KEY=placeholder": "OPENAI_API_KEY",
    "1_API_KEY": None,
    "OPENAI API_KEY": None,
}


def said(value: str, name: str | None) -> str:
    if name is not None:
        return (f"is \"{value}\", which is not a variable's name; write the name alone, as "
                f"{name}")
    return (f"is \"{value}\", which is not a variable's name: a name is letters, digits and _, "
            "and does not start with a digit")


@pytest.mark.parametrize("value", list(CASES))
def test_fd5_4_a_key_variable_written_as_a_shell_writes_it_is_told_to_write_the_name(
    value: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = CASES[value]
    ran = invoke(["init", "--yes", "--no-check-key", "--api-key-env", value], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 2, ran
    assert error_lines(ran) == [f"error: --api-key-env {said(value, name)}"], ran
    text = config().dump_config(config().config_from_init_args([]))
    text = text.replace('api_key_env = "OPENAI_API_KEY"', f'api_key_env = "{value}"')
    line = next(i for i, row in enumerate(text.splitlines(), start=1)
                if row.startswith("api_key_env"))
    with pytest.raises(config().ConfigError) as refused:
        config().loads_config(text)
    assert str(refused.value) == f"tasks.toml line {line}: [model] api_key_env {said(value, name)}"
    assert refused.value.suggestion == name
    Path("tasks.toml").write_text(text, encoding="utf-8")
    run = invoke(["run", "--dry-run", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert run.code == 1, run
    assert error_lines(run) == [f"error: {refused.value}"]


def test_fd5_4_a_name_without_api_key_keeps_its_words(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init", "--yes", "--no-check-key", "--api-key-env", "OPENAI_KEY"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 2, ran
    assert "API_KEY" in error_lines(ran)[0] and "not a variable's name" not in error_lines(ran)[0]
