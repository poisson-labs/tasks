"""What the build's mutation pass found no frozen test reads: pinned here (FD5 Session B).

- **item 19** (ruled 2026-10-13): a card whose depth arms include the ladder's top level carries
  the published cards' own note on depth, taken from the card's document, never typed;
- **init's flags given twice**: the last one given counts, as the library's reader has it, so the
  command hands the flags to the library in the order typed;
- **Ctrl-C outside a verb's own handling** (rule L6): an interrupt while `generate` makes its
  tasks is a stop, `stopped` on stdout and exit 130, with nothing written;
- **`transcripts.read_transcript`**: a list whose items are both messages (a `role`) and turns
  (`content`, `calls`, `finish_reason`) is refused as ambiguous, not read as one of them; the
  OpenAI form's calls are ordered by the `seq` their answers open with, a call the harness
  refused keeping its place, and a reply after the last call ends the attempt.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import needs_uv
from tests.fd4_support import fd4_runs
from tests.fd5_support import World, calibration, cards, config, invoke, prog, world

__all__ = ["prog", "world", "fd4_runs"]


@needs_uv
def test_item_19_a_card_with_the_top_depth_level_carries_the_published_cards_depth_note(
    fd4_runs: Any, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = world.work / "runs" / "first-look"
    shutil.copytree(fd4_runs["first_look"].folder, folder)
    card = calibration().card_from_run(folder)
    assert card.document is not None
    # a first look has three of the five depth levels, so its own document renders no ordering
    # and no note; the note is the published card's, from its document
    assert "no stage lies above the goal" not in card.document
    published = calibration().render_document(cards().recompute(cards().published()[0]).artifact)
    note = next(line for line in published.splitlines()
                if "no stage lies above the goal" in line).strip().lstrip("- ").strip()
    ran = invoke(["card", str(folder)], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    lines = [line for line in ran.lines if line.strip().startswith("about depth")]
    assert len(lines) == 1, ran
    assert note in lines[0], (note, lines[0])


def test_inits_flag_given_twice_keeps_the_last_one_typed(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    for flags, preset in ((["--recipe", "card", "--recipe", "first-look"], "first-look"),
                          (["--recipe", "first-look", "--measure", "card"], "card")):
        ran = invoke(["init", "--yes", "--no-fetch", "--no-check-key", "--force", *flags],
                     prog=prog, monkeypatch=monkeypatch)
        assert ran.code == 0, ran
        assert config().load_config(world.work / "tasks.toml").measure.preset == preset, flags


def test_ctrl_c_while_generate_makes_its_tasks_is_a_stop_with_exit_130(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.fd5_support import patch_everywhere

    def interrupted(*args: Any, **kwargs: Any) -> Any:
        raise KeyboardInterrupt

    import importlib

    importlib.import_module("poisson_tasks.cli")
    importlib.import_module("poisson_tasks.tasks")
    patch_everywhere(monkeypatch, "poisson_tasks.tasks", "generate", interrupted)
    ran = invoke(["generate", "--arm", "depth:d1", "--tasks-per-level", "1"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 130, ran
    assert ran.word == "stopped", ran
    assert not list(world.work.iterdir())


def transcripts() -> Any:
    import importlib

    return importlib.import_module("poisson_tasks.transcripts")


def test_a_transcript_that_is_both_a_message_and_a_turn_is_refused_as_ambiguous() -> None:
    both = [{"role": "assistant", "content": "", "calls": [], "finish_reason": "stop"}]
    with pytest.raises(ValueError) as refused:
        transcripts().read_transcript(json.dumps(both))
    assert "OpenAI chat messages" in str(refused.value) and "own turns" in str(refused.value)
    assert "\n" not in str(refused.value)


def test_the_openai_forms_calls_are_ordered_by_their_answers_seq_and_a_reply_ends_it() -> None:
    def call(call_id: str, name: str) -> dict[str, Any]:
        return {"id": call_id, "type": "function",
                "function": {"name": name, "arguments": json.dumps({"record_id": call_id})}}

    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": None, "tool_calls": [call("a", "second"),
                                                                call("b", "first")]},
        {"role": "tool", "tool_call_id": "a", "content": "2 the second answer"},
        {"role": "tool", "tool_call_id": "b", "content": "1 the first answer"},
        {"role": "assistant", "content": None, "tool_calls": [call("c", "refused")]},
        {"role": "tool", "tool_call_id": "c", "content": "error: not a tool"},
        {"role": "assistant", "content": "Done."},
    ]
    read = transcripts().read_transcript(json.dumps(messages))
    assert read.form == "openai"
    assert [turn.calls[0][0] for turn in read.turns[:-1]] == ["first", "second", "refused"]
    assert read.turns[0].calls[0][1] == {"record_id": "b"}
    assert read.ended_with_reply and read.turns[-1].content == "Done."
    assert read.turn_limit_hit is None
    cut = transcripts().read_transcript(json.dumps(messages[:-1]))
    assert not cut.ended_with_reply and len(cut.turns) == 3


def test_a_transcript_file_in_two_forms_is_refused_by_the_command(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    both = [{"role": "assistant", "content": "", "calls": [], "finish_reason": "stop"}]
    Path("both.json").write_text(json.dumps(both), encoding="utf-8")
    ran = invoke(["verify", "--arm", "depth:d1", "--task", "1", "--transcript", "both.json"],
                 prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    assert ran.out == "" and len([line for line in ran.err_lines if line.startswith("error: ")]) == 1
