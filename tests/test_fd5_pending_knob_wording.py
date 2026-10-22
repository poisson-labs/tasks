"""Pending a decision: init's refusal of a knob the library has and `tasks.toml` does not offer.

A decision with the history knob (decided yes, 2026-10-07) left
`init --recipe custom --knob history` saying
`--knob: "history" is not a knob; it is one of depth or distractor` until the step that opens the
new knobs in `init`; reading your own tools flagged it for rewording with the command.  History is a
knob: the library makes its tasks.  What is true is that the settings file does not offer it yet.
The refusal itself is pinned in `tests/test_fd5_init.py`; this pins the words.

**Proposed, and recommended:** `--knob: "history" is a knob not offered here yet; the knobs
offered are depth and distractor` (in the file, `tasks.toml line N: [measure] knob: …`), for
every knob the library has that `tasks.toml` does not offer; a word that is no knob keeps today's
words, with its nearest knob.

**If it is declined**, this file's commit is dropped, and the words wait for the step that opens
the knobs, as the decision of 2026-10-07 has it.
"""

from __future__ import annotations

import pytest

from tests.fd5_support import World, config, error_lines, invoke, prog, world

__all__ = ["prog", "world"]

NOT_OFFERED = ["similarity", "faults", "history", "block", "arguments", "shape", "spread"]


@pytest.mark.parametrize("knob", NOT_OFFERED)
def test_fd5_8_a_knob_not_offered_is_said_to_be_a_knob_not_offered_here_yet(
    knob: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init", "--yes", "--no-check-key", "--recipe", "custom", "--knob", knob],
                 prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 2, ran
    assert error_lines(ran) == [
        f'error: --knob: "{knob}" is a knob not offered here yet; the knobs offered are depth '
        "and distractor"], ran


def test_fd5_8_a_word_that_is_no_knob_keeps_its_nearest_knob(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(config().ConfigError) as refused:
        config().config_from_init_args(["--recipe", "custom", "--knob", "dpeth"])
    assert refused.value.suggestion == "depth"
    ran = invoke(["init", "--yes", "--no-check-key", "--recipe", "custom", "--knob", "dpeth"],
                 prog=prog, monkeypatch=monkeypatch)
    assert error_lines(ran) == [f"error: {refused.value}"]
    assert "not offered here" not in error_lines(ran)[0]
