"""`verify`, frozen as tests.

The invariant is `verify`'s (decided 2026-10-03 on naming tasks):
- **one attempt, three forms, one verdict**: an agent's attempt given as OpenAI chat messages, as
  one row of a verifiers `traces.jsonl`, or as Tasks' own turns gives one verdict, the task's own
  verifier's; a file that could be read as two forms is refused, and so is one in none;
- **`--self-check` holds on every arm at a seed**: the reference solution passes and each wrong
  answer the task ships with earns its outcome, exit 0, verdict `ok`;
- **exit 4 follows a verdict that is not `passed`**, and the verdict word is the outcome label;
- **a task is named by its arm and its place in the plan**, `verify --arm depth:d3 --task 7`, and
  by `--seed` only for a seed the user chose; every line that names a task says both;
- the verdict's sentence is the library's (`outcomes.describe`), never typed in the
  command, and `--hit-turn-limit` says the attempt was cut off when its form cannot say.

The attempts are real: the fixture model plays a task's reference policy, and plays it one stage
too far, through the run engine, once per module; each attempt's trace row is what the wheel
wrote, and the other two forms are made from that row's own messages.

Shapes decided here
-------------------

**1. The plan a `--task N` counts in** is the settings file's when there is one (its seeds, so a
file's `seeds = [404, 55, 2121]` makes `--task 2` seed 55), and otherwise the published cards'
sixty seeds.  `--tasks FILE` (a file `generate` wrote) counts in the file.

**2. A refused transcript is exit 1** (the design: "a transcript in none of the three forms: exit 1,
naming the form expected"), one `error:` line.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import network_guard
from tests.fd3_support import KEY, KEY_VAR, make_plan, needs_uv, runs, stub_bin
from tests.fd5_support import (
    World,
    arms,
    calibration,
    config,
    error_lines,
    invoke,
    outcomes,
    prog,
    tasks,
    world,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["prog", "world"]

ARM = "depth:d3"


@pytest.fixture(scope="module")
def attempts(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, dict[str, Any]]]:
    """Two real attempts at the first published task of depth:d3: the reference policy and one
    stage too far.  Each is its trace row, as the wheel wrote it."""
    where = tmp_path_factory.mktemp("fd5-verify-attempts")
    out: dict[str, dict[str, Any]] = {}
    with pytest.MonkeyPatch.context() as patch:
        stubs = stub_bin(where / "stub-bin")
        import os

        patch.setenv("PATH", f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}")
        patch.setenv(KEY_VAR, KEY)
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
                     "all_proxy"):
            patch.delenv(name, raising=False)
        patch.setenv("NO_PROXY", "127.0.0.1,localhost")
        for model in ("fixture-reference", "fixture-overshoot"):
            with FixtureModel() as fixture:
                plan = make_plan(fixture.base_url, model=model, arms=(ARM,),
                                 seeds=calibration().seed_list()[:1])
                folder = runs().find_run(plan, where / model)
                with network_guard(patch):
                    result = runs().run_plan(plan, folder, caps={"spend_usd": 100.0,
                                                                "tokens": None},
                                             concurrency=1)
                assert result.verdict == "done", result
            lines = (Path(folder.path) / "depth-d3" / "traces.jsonl").read_text(
                encoding="utf-8").splitlines()
            assert len(lines) == 1
            out[model] = json.loads(lines[0])
    yield out


def openai_messages(row: dict[str, Any]) -> list[dict[str, Any]]:
    """The attempt's messages, as OpenAI's chat API writes them."""
    out: list[dict[str, Any]] = []
    for node in row["traces"][0]["nodes"]:
        message = node["message"]
        role = message["role"]
        if role == "assistant":
            entry: dict[str, Any] = {"role": "assistant", "content": message.get("content")}
            if message.get("tool_calls"):
                entry["tool_calls"] = [
                    {"id": call["id"], "type": "function",
                     "function": {"name": call["name"], "arguments": call["arguments"]}}
                    for call in message["tool_calls"]
                ]
            out.append(entry)
        elif role == "tool":
            out.append({"role": "tool", "tool_call_id": message["tool_call_id"],
                        "content": message["content"]})
        else:
            out.append({"role": role, "content": message["content"]})
    return out


def own_turns(row: dict[str, Any]) -> list[dict[str, Any]]:
    """The attempt as Tasks' own turns: `tasks.Turn`'s fields."""
    out = []
    for message in openai_messages(row):
        if message["role"] != "assistant":
            continue
        calls = [[call["function"]["name"], json.loads(call["function"]["arguments"])]
                 for call in message.get("tool_calls", [])]
        out.append({"content": message.get("content") or "", "calls": calls,
                    "finish_reason": "tool_calls" if calls else "stop"})
    return out


def expected_verdict(rows: list[dict[str, Any]], *, limit: bool = False) -> Any:
    """The task's own verdict on Tasks' own turns, by the library."""
    bundle = tasks().generate(arms().arm_from_id(ARM), calibration().seed_list()[0])
    turns = tuple(tasks().Turn(content=row["content"],
                               calls=tuple((name, args) for name, args in row["calls"]),
                               finish_reason=row["finish_reason"]) for row in rows)
    ended = bool(turns) and not turns[-1].calls
    return tasks().verify(bundle, turns, ended, limit,
                          tasks().FormatSpec(name="direct", markers=()))


def forms(row: dict[str, Any]) -> dict[str, str]:
    return {
        "openai": json.dumps(openai_messages(row)),
        "traces-row": json.dumps(row) + "\n",
        "own-turns": json.dumps(own_turns(row)),
    }


@needs_uv
@pytest.mark.parametrize("model,label", [("fixture-reference", "passed"),
                                         ("fixture-overshoot", "overshoot")],
                         ids=["passed", "overshoot"])
def test_fd5_15_three_forms_of_one_attempt_give_one_verdict(
    model: str, label: str, attempts: dict[str, dict[str, Any]], prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = attempts[model]
    expected = expected_verdict(own_turns(row))
    assert expected.label == label
    firsts = {}
    for form, text in forms(row).items():
        path = world.work / f"{form}.json"
        path.write_text(text, encoding="utf-8")
        ran = invoke(["verify", "--arm", ARM, "--task", "1", "--transcript", path.name],
                     prog=prog, monkeypatch=monkeypatch)
        assert ran.code == (0 if label == "passed" else 4), (form, ran)
        assert ran.word == label, (form, ran)
        assert outcomes().describe(expected) in ran.first, (form, ran)
        firsts[form] = ran.first
    assert len(set(firsts.values())) == 1, firsts


@pytest.mark.parametrize("text", ["[]", '{"messages": 1}', "not json", '[{"role": "x"}]'],
                         ids=["either-form", "no-form", "not-json", "an-unknown-role"])
def test_fd5_15_a_transcript_in_no_form_or_in_two_is_refused(
    text: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    (world.work / "attempt.json").write_text(text, encoding="utf-8")
    ran = invoke(["verify", "--arm", ARM, "--task", "1", "--transcript", "attempt.json"],
                 prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    assert len(error_lines(ran)) == 1 and ran.out == "", ran


def test_fd5_15_the_turn_limit_flag_says_what_the_form_cannot(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tasks' own turns of an attempt cut off one call short, with no reply: the verdict differs
    with `--hit-turn-limit`, and each is the library's."""
    bundle = tasks().generate(arms().arm_from_id(ARM), calibration().seed_list()[0])
    rows = [{"content": "", "calls": [[name, args]], "finish_reason": "tool_calls"}
            for name, args in bundle.reference_calls[:-1]]
    (world.work / "cut.json").write_text(json.dumps(rows), encoding="utf-8")
    words = []
    for flag in ([], ["--hit-turn-limit"]):
        ran = invoke(["verify", "--arm", ARM, "--task", "1", "--transcript", "cut.json", *flag],
                     prog=prog, monkeypatch=monkeypatch)
        expected = expected_verdict(rows, limit=bool(flag))
        assert ran.code == 4, ran
        assert ran.word == expected.label, ran
        words.append(ran.word)
    assert words[0] != words[1]


@pytest.mark.parametrize("arm", [
    "depth:d1", "depth:d2", "depth:d3", "depth:d5", "depth:d8", "depth:d1+h8", "depth:d2+h5",
    "distractor:r0@k16", "distractor:r2@k16", "distractor:r4@k16", "distractor:r8@k16",
    "distractor:r14@k16", "distractor:r0+len(r8)@k16", "distractor:r2+len(r14)@k16",
])
def test_fd5_15_self_check_holds_on_every_arm_at_a_seed(
    arm: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["verify", "--arm", arm, "--task", "3", "--self-check"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert ran.word == "ok", ran


def names(line: str, arm: str, place: int | None, seed: int) -> bool:
    if arm not in line or not re.search(rf"(?<!\d){seed}(?!\d)", line):
        return False
    return place is None or bool(re.search(rf"\btask {place}\b", line))


def test_fd5_15_a_task_is_named_by_its_arm_its_place_and_its_seed(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = calibration().seed_list()[6]
    ran = invoke(["verify", "--arm", ARM, "--task", "7", "--self-check"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert names(ran.first, ARM, 7, seed), ran.first
    lines = [line for line in ran.lines if re.search(r"\btask \d+\b", line)]
    assert all(names(line, ARM, 7, seed) for line in lines), lines


def test_fd5_15_a_chosen_seed_is_named_by_its_seed(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["verify", "--arm", "depth:d2", "--seed", "4242", "--self-check"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert names(ran.first, "depth:d2", None, 4242), ran.first


def test_fd5_15_a_settings_files_seeds_are_the_plan_a_place_counts_in(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = config().config_from_init_args(["--seeds", "404,55,2121"])
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")
    ran = invoke(["verify", "--arm", "depth:d1", "--task", "2", "--self-check"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert names(ran.first, "depth:d1", 2, 55), ran.first


def test_fd5_15_a_task_file_from_generate_is_counted_in_that_file(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = invoke(["generate", "--arm", "depth:d2", "--seeds", "404,55,2121"], prog=prog,
                  monkeypatch=monkeypatch)
    assert made.code == 0, made
    path = Path("tasks") / "depth-d2.jsonl"
    ran = invoke(["verify", "--tasks", str(path), "--task", "3", "--self-check"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert names(ran.first, "depth:d2", 3, 2121), ran.first


def test_fd5_15_a_self_check_that_does_not_hold_is_exit_4_naming_the_wrong_answer(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The task's verifier made to give one of its wrong answers another label: the self-check
    no longer holds, the verdict is not `ok`, exit 4, and the line for that wrong answer says
    the label it got."""
    import dataclasses

    from tests.fd5_support import patch_everywhere

    real = tasks().verify

    def verify(bundle: Any, turns: Any, *args: Any, **kwargs: Any) -> Any:
        verdict = real(bundle, turns, *args, **kwargs)
        if verdict.label == "overshoot":
            return dataclasses.replace(verdict, label="wrong_state", strict_label="wrong_state")
        return verdict

    patch_everywhere(monkeypatch, "poisson_tasks.tasks", "verify", verify)
    ran = invoke(["verify", "--arm", ARM, "--task", "1", "--self-check"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 4, ran
    assert ran.word is not None and ran.word != "ok", ran
    assert any("overshoot" in line and "wrong_state" in line for line in ran.lines[1:]), ran


@needs_uv
def test_fd5_9_verifys_json_keeps_its_exit_4(
    attempts: dict[str, dict[str, Any]], prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.fd5_support import json_keys, strict_json

    (world.work / "attempt.json").write_text(forms(attempts["fixture-overshoot"])["own-turns"],
                                             encoding="utf-8")
    ran = invoke(["verify", "--arm", ARM, "--task", "1", "--transcript", "attempt.json",
                  "--json"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 4, ran
    document = strict_json(ran.out)
    assert json_keys(ran.out)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "overshoot"
