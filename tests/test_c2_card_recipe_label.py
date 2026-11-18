"""The `card` recipe's refusal of a generator label says what is true.

Carried from the generator 4 build (ruled 2026-11-18, to be settled with the run path): a
settings file with `[measure] preset = "card"` and a `[tasks] generator_version` other than this
release's is refused in one line.  The line said "the published cards were measured at "4"",
naming the release's own label, and the published cards were measured at "0"; it had been untrue
since 0.3.0.

The sentence pinned here says only what holds: the recipe makes its tasks at this release's
label.  It makes no claim about where any published card was measured, so it stays true when the
version 2 cards are filed.  The whole line, for a file that sets `"0"`, after the
file's name and line number:

    [tasks] generator_version is "0"; the card recipe makes its tasks at "4", this release's
    generator, and tasks at another version carry other ids

`tests/test_g4_labels.py` holds that the line is one line and shows both labels; this file holds
the words.
"""

from __future__ import annotations

import re

import pytest

from poisson_tasks import config

SENTENCE = (
    '{name} is "{given}"; the card recipe makes its tasks at "4", this release\'s generator, '
    "and tasks at another version carry other ids"
)


def card_file(label: str) -> str:
    made = config.config_from_init_args(["--recipe", "card"])
    text = config.dump_config(made)
    assert "[tasks]\n" in text
    return text.replace("[tasks]\n", f'[tasks]\ngenerator_version = "{label}"\n', 1)


@pytest.mark.parametrize("label", ["0", "3", "mine"])
def test_a_card_file_at_another_label_is_refused_in_the_true_sentence(label: str) -> None:
    with pytest.raises(config.ConfigError) as refused:
        config.loads_config(card_file(label))
    assert refused.value.key == "tasks.generator_version"
    said = str(refused.value)
    assert re.fullmatch(r"tasks\.toml line \d+: .*", said), said
    assert said.split(": ", 1)[1] == SENTENCE.format(
        name="[tasks] generator_version", given=label)


def test_the_flag_is_refused_in_the_same_sentence_under_its_own_name() -> None:
    with pytest.raises(config.ConfigError) as refused:
        config.config_from_init_args(["--recipe", "card", "--generator-version", "0"])
    assert str(refused.value) == SENTENCE.format(name="--generator-version", given="0")


def test_the_refusal_no_longer_says_where_the_published_cards_were_measured() -> None:
    with pytest.raises(config.ConfigError) as refused:
        config.loads_config(card_file("0"))
    assert "were measured at" not in str(refused.value)


def test_a_card_file_at_this_releases_label_is_read() -> None:
    """A guard, which holds today."""
    assert config.loads_config(card_file("4")).tasks.generator_version == "4"
