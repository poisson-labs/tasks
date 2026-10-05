"""Which folder a run goes in, and nothing spent before the run starts, frozen as tests:
`runs.find_run`, and what is sent before `runs.run_plan` is called.

The invariants are FD3.2 and FD3.3 of the front door's plan (spec §8.1 and §8.5), with the
folder names ruled on 2026-10-03:
- the folder is `runs/<preset>-<model>/`, then `-2`, `-3` for `again` or for a changed plan, with
  no hash in its name; the model part is made folder-safe;
- the folder that holds a plan is found by the `plan_hash` in each folder's `plan.json`, never by
  its name; `--run` takes a folder's name (`find_run(..., name=...)`);
- the same plan finds the same folder: unfinished is `resume`, finished is `complete`, and a
  complete run makes no request; a changed plan gets a new folder, with the fields that changed;
- until `run_plan` is called, the model has seen only the key check's free GET.

And the ruling of 2026-09-30 carried into the runner (plan ruling 42, FD0.4 and FD0.5): a real
run with no arm or no seeds refuses before anything is sent or written.

Shapes decided here
-------------------

**1. `RunFolder`** has `path`, `name` (the folder's name, which `--run` takes), `status` (`"new"`,
`"resume"` or `"complete"`), `changed` and `previous`.  `find_run` only reads: it creates no folder
and changes no byte of any it reads.  `run_plan` makes the folder and writes `plan.json`.

**2. `changed` names the plan's fields** that differ from the folder named in `previous`, out of
`arms`, `generator_version`, `seeds`, `attempts`, `model`, `base_url`, `decoding` and
`max_model_calls`: the fields that move `plan_hash` (FD1.9), with an arm's generator version
named on its own.  `previous` is the newest run folder in the runs folder, whatever its name (the
one whose `plan.json` was written last), and `None` (with `changed` empty) when there is none.  So
a changed model, which also changes the folder's name, is still told as "the model changed since
runs/first-look-…" (spec §8.5).  `again` makes a new folder with `changed` empty and `previous`
`None`: nothing changed.

**3. When more than one folder holds the plan** (a run and its `again`), the newest is the one
found, so `--again`, then Ctrl-C, then `run` resumes the second run, not the first.

**4. `find_run(name=...)` refuses** a name that holds another plan, a name nothing holds, and a
name that is not one folder's name, each with a `ValueError` of one line that names the name.

**5. A plan with no arm or no seeds** is a `ValueError` from `run_plan`, before the folder is made.

Not pinned here: what a folder whose every episode ran, some of them failed, reports.  The
wheel's own resume rule owes a failed episode again, so `resume`; that waits on a yes/no
(`evidence/front-door-fd3-a/rulings.md`, yes/no 2) and is pinned in its own file,
`tests/test_fd3_pending_failed_episode.py`.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import network_guard
from tests.fd3_support import (
    KEY_VAR,
    arm_dir,
    config,
    fixture_model,
    harness_env,
    make_plan,
    needs_uv,
    run_here,
    runs,
    snapshot,
    tree_bytes,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["fixture_model", "harness_env"]


def tiny(model: FixtureModel, **kwargs: Any) -> Any:
    """One arm, one task, one attempt: two model calls."""
    return make_plan(model.base_url, **kwargs)


def stopped_early(model: FixtureModel, runs_dir: Path, monkeypatch: pytest.MonkeyPatch,
                  plan: Any) -> Any:
    """A run of `plan` stopped by a cap before it finished, leaving its folder to resume."""
    folder, result = run_here(plan, runs_dir, monkeypatch,
                              caps={"spend_usd": 0.015, "tokens": None}, concurrency=1)
    assert result.verdict == "stopped" and result.episodes_owed > 0, result
    return folder


def resolved(*flags: str) -> Any:
    cfg = config()
    return cfg.resolve_plan(cfg.config_from_init_args(list(flags)))


# ---------------------------------------------------------------------------
# names
# ---------------------------------------------------------------------------


def test_fd3_2_a_new_plan_gets_its_preset_and_model_as_the_folder_name(tmp_path: Path) -> None:
    """Spec §8.5's own example, and `find_run` writes nothing."""
    plan = resolved("--provider", "openai", "--measure", "first-look", "--tasks-per-level", "10")
    runs_dir = tmp_path / "runs"
    folder = runs().find_run(plan, runs_dir)
    assert folder.status == "new"
    assert folder.name == "first-look-gpt-5-nano-2025-08-07"
    assert Path(folder.path) == runs_dir / folder.name
    assert folder.changed == () and folder.previous is None
    assert not runs_dir.exists() or snapshot(runs_dir) == {}


@pytest.mark.parametrize("model, words", [
    ("Qwen/Qwen3-8B", ["Qwen", "Qwen3", "8B"]),
    ("qwen3:8b", ["qwen3", "8b"]),
    ("acme/team:model@v2", ["acme", "team", "model", "v2"]),
])
def test_fd3_2_the_model_part_is_folder_safe_and_readable(
    tmp_path: Path, model: str, words: list[str]
) -> None:
    """One folder name, whatever the model's name holds, with no character a path or a shell
    reads specially, the model's words in order (in any case), and no run of hex digits a user
    would paste."""
    plan = make_plan("http://127.0.0.1:9/v1", model=model, preset="first-look")
    folder = runs().find_run(plan, tmp_path)
    name = folder.name
    assert Path(folder.path) == tmp_path / name and Path(name).name == name
    assert re.fullmatch(r"[A-Za-z0-9._-]+", name), name
    assert name.startswith("first-look-") and not name.startswith(".")
    position = 0
    for word in words:
        found = name.lower().find(word.lower(), position)
        assert found >= 0, (name, word)
        position = found + len(word)
    assert re.search(r"[0-9a-f]{8,}", name) is None, name


# ---------------------------------------------------------------------------
# the same plan, its folder's state
# ---------------------------------------------------------------------------


@needs_uv
def test_fd3_2_a_finished_run_is_complete_and_makes_no_request(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = tiny(fixture_model)
    first, result = run_here(plan, tmp_path, monkeypatch)
    assert result.verdict == "done", result
    plan_json = json.loads((Path(first.path) / "plan.json").read_text(encoding="utf-8"))
    assert plan_json["plan_hash"] == config().plan_hash(plan)

    again = runs().find_run(plan, tmp_path)
    assert (again.status, Path(again.path)) == ("complete", Path(first.path))
    requests = len(fixture_model.requests)
    before = tree_bytes(tmp_path)
    with network_guard(monkeypatch):
        repeat = runs().run_plan(plan, again, caps={"spend_usd": 100.0, "tokens": None},
                                 concurrency=4)
    assert len(fixture_model.requests) == requests, "a complete run sent a request"
    assert (repeat.verdict, repeat.episodes_run, repeat.episodes_owed) == ("done", 0, 0)
    kept = ("run.log", "plan.json")
    assert {k: v for k, v in tree_bytes(tmp_path).items() if not k.endswith(kept)} == {
        k: v for k, v in before.items() if not k.endswith(kept)}


@needs_uv
def test_fd3_2_an_unfinished_run_is_resumed_and_find_run_changes_nothing_in_it(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`find_run` only reads.  The folder is left with a torn last line in its trace file, which
    the wheel's own resume would rewrite: a `find_run` that asked it would change the file."""
    plan = tiny(fixture_model, seeds=(404, 55), attempts=2)
    folder = stopped_early(fixture_model, tmp_path, monkeypatch, plan)
    arm = Path(folder.path) / arm_dir(plan.arms[0])
    arm.mkdir(parents=True, exist_ok=True)
    with (arm / "traces.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"task": {"hash": "')
    before = tree_bytes(tmp_path)
    found = runs().find_run(plan, tmp_path)
    assert (found.status, Path(found.path), found.name) == ("resume", Path(folder.path),
                                                           folder.name)
    assert tree_bytes(tmp_path) == before


# ---------------------------------------------------------------------------
# a changed plan, again, and a folder found by its plan
# ---------------------------------------------------------------------------


CHANGES: dict[str, dict[str, Any]] = {
    "seeds": {"seeds": (404, 2121)},
    "attempts": {"attempts": 3},
    "base_url": {"base_url": "http://127.0.0.1:9/v1"},
    "decoding": {"decoding": {"temperature": 0.7, "top_p": 1.0, "reasoning_effort": "low",
                              "max_tokens": 2048}},
    "max_model_calls": {"max_model_calls": 12},
    "generator_version": {"generator_version": "tg-m3-v1"},
    "arms": {"arms": ("depth:d1", "depth:d3")},
    "model": {"model": "fixture-overshoot"},
}


@needs_uv
def test_fd3_2_a_changed_plan_gets_the_next_folder_and_names_what_changed(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each field that moves the plan's identity, changed alone, then two at once: the next free
    `-2` (a changed model starts a name of its own), the previous folder named, the field named;
    and `find_run` writes nothing."""
    base = dict(arms=("depth:d1",), seeds=(404, 55), attempts=2)
    plan = tiny(fixture_model, **base)
    folder = stopped_early(fixture_model, tmp_path, monkeypatch, plan)
    before = snapshot(tmp_path)
    for field, change in CHANGES.items():
        other = make_plan(change.get("base_url", fixture_model.base_url),
                          **{**base, **{k: v for k, v in change.items() if k != "base_url"}})
        assert config().plan_hash(other) != config().plan_hash(plan)
        found = runs().find_run(other, tmp_path)
        assert found.status == "new", field
        if field == "model":
            assert found.name == runs().find_run(other, tmp_path / "elsewhere").name, found.name
        else:
            assert found.name == folder.name + "-2", (field, found.name)
        assert found.previous == folder.name, field
        assert found.changed == (field,), (field, found.changed)
    both = tiny(fixture_model, arms=("depth:d1",), seeds=(404,), attempts=1)
    found = runs().find_run(both, tmp_path)
    assert set(found.changed) == {"seeds", "attempts"}, found.changed
    assert snapshot(tmp_path) == before


@needs_uv
def test_fd3_2_a_changed_plan_takes_the_next_free_suffix(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tiny(fixture_model, seeds=(404, 55), attempts=2)
    second = tiny(fixture_model, seeds=(404, 55), attempts=3)
    third = tiny(fixture_model, seeds=(404, 55), attempts=4)
    one = stopped_early(fixture_model, tmp_path, monkeypatch, first)
    two = stopped_early(fixture_model, tmp_path, monkeypatch, second)
    assert two.name == one.name + "-2"
    found = runs().find_run(third, tmp_path)
    assert found.name == one.name + "-3"
    assert found.previous == one.name + "-2" and found.changed == ("attempts",)
    assert runs().find_run(first, tmp_path).name == one.name
    assert runs().find_run(second, tmp_path).name == two.name


@needs_uv
def test_fd3_2_again_takes_the_next_suffix_and_the_newest_run_is_the_one_found(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = tiny(fixture_model, seeds=(404, 55), attempts=2)
    first, done = run_here(plan, tmp_path, monkeypatch)
    assert done.verdict == "done"
    second = runs().find_run(plan, tmp_path, again=True)
    assert (second.status, second.name) == ("new", first.name + "-2")
    assert snapshot(tmp_path / second.name) == {}, "find_run made the folder"
    _, cut = run_here(plan, tmp_path, monkeypatch, again=True,
                      caps={"spend_usd": 0.015, "tokens": None}, concurrency=1)
    assert cut.verdict == "stopped"
    found = runs().find_run(plan, tmp_path)
    assert (found.name, found.status) == (first.name + "-2", "resume")
    third = runs().find_run(plan, tmp_path, again=True)
    assert third.name == first.name + "-3"


@needs_uv
def test_fd3_2_a_folder_is_found_by_the_plan_in_it_and_not_by_its_name(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A folder the user renamed is still found.  And a custom plan of depth at 1, 3 and 8 is
    the first look's plan (ruled 2026-10-03: the plan's identity leaves out the preset): it finds the first look's
    folder, whatever the preset was called."""
    plan = tiny(fixture_model, preset="first-look", seeds=(404, 55), attempts=2)
    folder = stopped_early(fixture_model, tmp_path, monkeypatch, plan)
    renamed = tmp_path / "my-first-try"
    os.rename(folder.path, renamed)
    found = runs().find_run(plan, tmp_path)
    assert (Path(found.path), found.name, found.status) == (renamed, "my-first-try", "resume")
    shutil.rmtree(renamed)

    look = resolved("--provider", "openai-compatible", "--base-url", fixture_model.base_url,
                    "--model", "fixture-reference", "--api-key-env", KEY_VAR, "--no-price",
                    "--token-cap", "3000", "--measure", "first-look", "--tasks-per-level", "1")
    custom = resolved("--provider", "openai-compatible", "--base-url", fixture_model.base_url,
                      "--model", "fixture-reference", "--api-key-env", KEY_VAR, "--no-price",
                      "--token-cap", "3000", "--measure", "custom", "--knob", "depth",
                      "--levels", "1,3,8", "--no-controls", "--strictness", "strict",
                      "--tasks-per-level", "1")
    assert look.preset != custom.preset
    assert config().plan_hash(look) == config().plan_hash(custom)
    looked, result = run_here(look, tmp_path, monkeypatch,
                              caps={"spend_usd": None, "tokens": 3000}, concurrency=1)
    assert result.verdict == "stopped"
    found = runs().find_run(custom, tmp_path)
    assert (Path(found.path), found.status) == (Path(looked.path), "resume")


@needs_uv
def test_fd3_2_run_takes_a_folders_name(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = tiny(fixture_model, seeds=(404, 55), attempts=2)
    first, done = run_here(plan, tmp_path, monkeypatch)
    _, cut = run_here(plan, tmp_path, monkeypatch, again=True,
                      caps={"spend_usd": 0.015, "tokens": None}, concurrency=1)
    assert (done.verdict, cut.verdict) == ("done", "stopped")
    named = runs().find_run(plan, tmp_path, name=first.name)
    assert (Path(named.path), named.status) == (Path(first.path), "complete")
    named = runs().find_run(plan, tmp_path, name=first.name + "-2")
    assert named.status == "resume"


@needs_uv
@pytest.mark.parametrize("name", ["holds-another-plan", "nothing-by-that-name",
                                  "a-folder-outside", "a-path-inside"])
def test_fd3_2_run_refuses_a_name_that_does_not_hold_the_plan(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch, name: str,
) -> None:
    """`--run` takes one folder's name in the runs folder.  A path that leads elsewhere is
    refused even where it leads to a folder holding this very plan: one outside the runs folder
    (`../outside/<name>`), or inside it but below a folder (`<name>/<arm folder>`)."""
    runs_dir = tmp_path / "runs"
    plan = tiny(fixture_model, seeds=(404, 55), attempts=2)
    other = tiny(fixture_model, seeds=(404, 55), attempts=3)
    mine = stopped_early(fixture_model, runs_dir, monkeypatch, plan)
    theirs = stopped_early(fixture_model, runs_dir, monkeypatch, other)
    outside = stopped_early(fixture_model, tmp_path / "outside", monkeypatch, plan)
    nested = Path(mine.path) / "nested"
    nested.mkdir()
    (nested / "plan.json").write_bytes((Path(mine.path) / "plan.json").read_bytes())
    runs().find_run(plan, runs_dir, name=mine.name)
    before = snapshot(tmp_path)
    wrong = {
        "holds-another-plan": theirs.name,
        "a-folder-outside": f"../outside/{outside.name}",
        "a-path-inside": f"{mine.name}/nested",
    }.get(name, name)
    with pytest.raises(ValueError) as refused:
        runs().find_run(plan, runs_dir, name=wrong)
    assert snapshot(tmp_path) == before
    message = str(refused.value)
    assert "\n" not in message and wrong in message, message


# ---------------------------------------------------------------------------
# nothing before the run starts
# ---------------------------------------------------------------------------


@needs_uv
def test_fd3_3_until_run_plan_the_model_sees_only_the_key_checks_get(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec §8.1 steps 2 to 7, as `run` makes them: read the config and resolve the plan, find
    the folder, check the key, make the estimate, and write the eval configs `export` would.
    Before the run starts the fixture has had GETs and no POST, nothing is in the runs folder,
    and no socket has opened to anything but the fixture.  Then `run_plan` sends the calls."""
    providers = importlib.import_module("poisson_tasks.providers")
    text = "\n".join(config().dump_config(config().config_from_init_args([
        "--provider", "openai-compatible", "--base-url", fixture_model.base_url,
        "--model", "fixture-reference", "--api-key-env", KEY_VAR,
        "--price", "10,5,20", "--price-read-on", "2026-10-05",
        "--measure", "first-look", "--tasks-per-level", "1", "--spend-cap", "1.00",
    ])).splitlines())
    runs_dir = tmp_path / "runs"
    with network_guard(monkeypatch) as events:
        project = config().loads_config(text)
        plan = config().resolve_plan(project)
        folder = runs().find_run(plan, runs_dir)
        check = providers.check_key(project.model)
        estimate = runs().estimate(plan)
        for spec in plan.arms:
            runs().verifiers_config(plan, spec)
    assert check.status == providers.ACCEPTED, check
    assert estimate.episodes == 3
    assert fixture_model.methods() == {"GET"}, fixture_model.methods()
    assert fixture_model.posts() == []
    assert not runs_dir.exists() or snapshot(runs_dir) == {}
    ports = {address[1] for kind, address in events if kind == "connect"}
    assert ports == {fixture_model.port}, ports

    with network_guard(monkeypatch):
        result = runs().run_plan(plan, folder, caps={"spend_usd": 1.0, "tokens": None},
                                 concurrency=3)
    assert result.verdict == "done" and fixture_model.posts()


# ---------------------------------------------------------------------------
# a plan with nothing to run
# ---------------------------------------------------------------------------


@needs_uv
@pytest.mark.parametrize("empty", ["arms", "seeds"])
def test_fd3_a_run_with_no_arm_or_no_seeds_refuses_before_anything_is_sent(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch, empty: str,
) -> None:
    plan = tiny(fixture_model)
    bare = dataclasses.replace(plan, **{empty: ()})
    folder = runs().find_run(bare, tmp_path)
    with network_guard(monkeypatch), pytest.raises(ValueError) as refused:
        runs().run_plan(bare, folder, caps={"spend_usd": 1.0, "tokens": None}, concurrency=1)
    assert "\n" not in str(refused.value) and str(refused.value)
    assert fixture_model.requests == []
    assert snapshot(tmp_path) == {} and not Path(folder.path).exists()
    _, control = run_here(plan, tmp_path, monkeypatch)
    assert control.verdict == "done"
