"""`run`, end to end against the fixture model, frozen as tests.

The invariants are FD5.19 and FD5.20 of the front door's plan (spec §4.3, §8; FD3 Session A's
yes/nos 2 and 3, ruled yes 2026-10-05), and the rest of the mistakes round FD5.4 names:
- **FD5.19** every row of spec §8.7's table gives its verdict and its exit code: every episode
  ran, `done`, 0; the cap, `stopped`, 3, with a `next:` command that raises the cap and resumes;
  the provider out of credit, `stopped`, 3; a failure streak, `stopped`, 3, naming the first
  error's status and the provider's own code; nothing happening, `stopped`, 3, quoting `run.log`;
  Ctrl-C, `stopped`, 130, then the resume.  A complete run reports itself and sends nothing;
- **a run in which every episode ran but one failed ends `done`, exit 0, and is resumed, not
  complete**: run again, it runs the one failed episode, and then reports itself complete (FD3
  Session A's yes/no 2; what its done line says is `tests/test_fd5_pending_owed_done_line.py`);
- **the key check** (spec §7.3, §8.1 step 4): refused, the model missing and the endpoint
  unreachable are each exit 1, nothing sent to the model, the `error:` line the library's own;
  a check that comes back "not checkable" still shows the plan, saying so, and still asks, and
  with `--yes` the run is made (FD3 Session A's yes/no 3);
- **uv's installer is disclosed in every plan the command shows** (FD3 Session A's yes/no 3): a
  plan line names uv, astral.sh and PyPI, for each recipe, a custom plan and a resumed run;
- **nothing is sent, written or opened before the user confirms** (spec P-4, §8.1): on a pipe
  without `--yes`, or answered no, the plan is printed, no model call is made, no run folder is
  made and no harness is started;
- **FD5.20** with the platform reported as Windows, `run` refuses in one line, exit 1, before it
  opens the settings file;
- **a changed plan gets a new folder**, and the plan line says which folder it follows and what
  changed (spec §8.5);
- `--run` naming a folder that is not there is refused with the library's text.

Every run is against the fixture model on loopback (`tests/fixtures/model_server.py`), the
harness's bootstrap given a `pip` that installs nothing (`fd3_support.harness_env`), inside the
network guard.  Expectations come from the plan, the fixture's own count, the folder and the
library.

Shapes decided here
-------------------

**1. A dry run checks no key it is told not to**: `run --dry-run --offline` prints the plan
whether or not the key is set; a run that would send something refuses a key that is not set.

**2. The `next:` command after the cap carries `--spend-cap` (or `--token-cap`) with a higher
cap**, and run as printed it resumes the same folder.
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import KEY_BODY, SENTINEL, free_port
from tests.fd3_support import (
    KEY,
    KEY_VAR,
    MARK,
    harness_env,
    ledger_lines,
    marked_processes,
    needs_uv,
    planned_tasks,
    scored_tasks,
    stub_bin,
    wait_until,
)
from tests.fd4_support import partial_design
from tests.fd5_support import (
    CHILD,
    Answers,
    NotCheckable,
    World,
    assert_clean,
    base_env,
    error_lines,
    fixture_flags,
    fresh,
    invoke,
    leaked,
    next_commands,
    plan_of,
    prog,
    providers,
    recording_opens,
    runs,
    strict_json,
    strip_prog,
    verdict_lines,
    world,
    write_config,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["prog", "world", "harness_env"]


@pytest.fixture
def fixture() -> Any:
    model = FixtureModel(slow_seconds=1.0)
    model.start()
    try:
        yield model
    finally:
        model.close()


def shutil_rmtree(path: Path) -> None:
    import shutil

    shutil.rmtree(path)


def last_verdict(out: str) -> tuple[str, str]:
    found = verdict_lines(out, "run")
    assert found, out
    return found[-1]


def run_folders(world: World) -> list[Path]:
    root = world.work / "runs"
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []


def harness_line(out: str) -> list[str]:
    return [line for line in out.splitlines()
            if "uv" in line.split() or "uv's" in line
            if "astral.sh" in line and "PyPI" in line]


# ---------------------------------------------------------------------------
# every episode ran
# ---------------------------------------------------------------------------


@needs_uv
def test_fd5_19_every_episode_ran_is_done_exit_0_and_the_next_step_is_the_card(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_config(world.work / "tasks.toml", fixture_flags(fixture.base_url, tasks_per_level=2))
    plan = plan_of(world.work / "tasks.toml")
    ran = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert ran.word == "plan", ran
    assert last_verdict(ran.out)[0] == "done", ran
    folders = run_folders(world)
    assert len(folders) == 1 and folders[0].name in ran.out
    assert providers().ACCEPTED in ran.out
    assert harness_line(ran.out), ran
    assert fixture.calls() == 2 * 2
    assert scored_tasks(plan, folders[0]) == planned_tasks(plan)
    assert next_commands(ran.out)[-1] == f"{prog} card"
    # the leak rule (ruled 2026-10-12): twelve characters of the key's secret part nowhere in
    # the output or the folder, four nowhere in `run.log`
    assert_clean(ran, "run", folders[0])


@needs_uv
def test_fd5_19_a_complete_run_reports_itself_and_sends_nothing(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_config(world.work / "tasks.toml", fixture_flags(fixture.base_url))
    assert invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch).code == 0
    seen = len(fixture.requests)
    again = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
    assert again.code == 0, again
    assert again.word == "done", again
    assert len(fixture.requests) == seen
    assert again.connections == []
    assert next_commands(again.out)[-1] == f"{prog} card"


@needs_uv
def test_fd5_9_a_runs_json_is_one_document_with_the_runs_verdict(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_config(world.work / "tasks.toml", fixture_flags(fixture.base_url))
    ran = invoke(["run", "--yes", "--json"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    document = strict_json(ran.out)
    assert list(document)[:3] == ["schema", "verdict", "sentence"]
    assert document["verdict"] == "done"


# ---------------------------------------------------------------------------
# the stops
# ---------------------------------------------------------------------------


@needs_uv
def test_fd5_19_the_cap_stops_with_exit_3_and_its_next_command_resumes_to_done(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    count, cap = partial_design()
    write_config(world.work / "tasks.toml",
                 fixture_flags(fixture.base_url, levels="1,3", tasks_per_level=count,
                               concurrency=1, spend_cap=cap))
    plan = plan_of(world.work / "tasks.toml")
    stopped = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
    assert stopped.code == 3, stopped
    assert last_verdict(stopped.out)[0] == "stopped", stopped
    folder = run_folders(world)[0]
    assert scored_tasks(plan, folder) != planned_tasks(plan)
    commands = [shlex.split(command) for command in next_commands(stopped.out)]
    assert commands, stopped
    command = strip_prog(commands[-1], prog)
    assert command[0] == "run" and "--spend-cap" in command, command
    assert float(command[command.index("--spend-cap") + 1]) > cap
    resumed = invoke([*command, "--yes"], prog=prog, monkeypatch=monkeypatch)
    assert resumed.code == 0, resumed
    assert last_verdict(resumed.out)[0] == "done"
    assert run_folders(world) == [folder]
    assert scored_tasks(plan, folder) == planned_tasks(plan)


@needs_uv
def test_fd5_19_the_provider_out_of_credit_stops_with_exit_3_and_is_not_a_streak(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same plan against a provider out of credit and against one refusing every call for
    its rate: both stop, exit 3, and the two lines differ, so neither stop is reported as the
    other.  With `--json`, the document's verdict is the stop's."""
    sentences = {}
    for model in ("fixture-402", "fixture-429"):
        (world.work / model).mkdir()
        monkeypatch.chdir(world.work / model)
        write_config(world.work / model / "tasks.toml",
                     fixture_flags(fixture.base_url, model=model, tasks_per_level=6,
                                   concurrency=1))
        ran = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
        assert ran.code == 3, ran
        word, sentences[model] = last_verdict(ran.out)
        assert word == "stopped", ran
    assert sentences["fixture-402"] != sentences["fixture-429"], sentences
    monkeypatch.chdir(world.work / "fixture-402")
    shutil_rmtree(world.work / "fixture-402" / "runs")
    data = invoke(["run", "--yes", "--json"], prog=prog, monkeypatch=monkeypatch)
    assert data.code == 3, data
    assert strict_json(data.out)["verdict"] == "stopped"


@needs_uv
def test_fd5_19_a_failure_streak_stops_with_exit_3_naming_the_first_error(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_config(world.work / "tasks.toml",
                 fixture_flags(fixture.base_url, model="fixture-429", tasks_per_level=6,
                               concurrency=1))
    ran = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 3, ran
    word, sentence = last_verdict(ran.out)
    assert word == "stopped", ran
    assert "429" in sentence and "rate_limit_exceeded" in sentence, sentence


@needs_uv
def test_fd5_19_nothing_happening_stops_with_exit_3_quoting_run_log(
    fixture: FixtureModel, prog: str, world: World, tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """A bootstrap that never ends, in a process of its own (the bootstrap runs once per
    process): the watchdog's limit is shortened for the test, and the run stops, quoting run of
    lines of its log, says nothing raw on stderr, and leaves nothing running."""
    mark = "fd5-watchdog-" + os.urandom(6).hex()
    started = tmp_path_factory.mktemp("hanging-pip-ran") / "pid"
    stubs = stub_bin(tmp_path_factory.mktemp("hanging-pip"),
                     pip=f"#!/bin/sh\necho $$ > {started}\nsleep 300\n")
    write_config(world.work / "tasks.toml", fixture_flags(fixture.base_url))
    try:
        ran = fresh(["run", "--yes"], prog=prog, world=world,
                    job={"watchdog_seconds": 8},
                    env={"PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}", KEY_VAR: KEY,
                         MARK: mark})
        assert started.exists(), "the stuck bootstrap never started"
        assert ran.code == 3, ran
        assert last_verdict(ran.out)[0] == "stopped", ran
        log = [line.strip() for line in (run_folders(world)[0] / "run.log").read_text(
            encoding="utf-8").splitlines() if line.strip()]
        quoted = [index for index, line in enumerate(log) if line in ran.out]
        assert len(quoted) >= 2, (ran.out, log[-8:])
        assert any(b == a + 1 for a, b in zip(quoted, quoted[1:])), "no run of the log is quoted"
        # the leak rule (ruled 2026-10-12): the lines quoted from `run.log` can carry the key, so
        # they hold no four characters of its secret part; the rest of the output no twelve
        assert_clean(ran, "run", quoted=[log[index] for index in quoted])
        assert fixture.calls() == 0
        assert wait_until(lambda: not marked_processes(mark), 20), marked_processes(mark)
    finally:
        for pid in marked_processes(mark):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


@needs_uv
def test_fd5_4_a_run_in_a_process_of_its_own_says_nothing_raw_on_stderr(
    fixture: FixtureModel, prog: str, world: World, tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The whole of a run's stderr, read from the process's own descriptor: the harness's
    bootstrap, verifiers' log records and anything else written there are held to the look,
    and no file the run wrote holds the key.  The plan is leaky, an arm no published card
    measured that way, so the library warns, and the warning is a `note:` line (rule L4)."""
    stubs = stub_bin(tmp_path_factory.mktemp("quiet-pip"))
    write_config(world.work / "tasks.toml",
                 fixture_flags(fixture.base_url, tasks_per_level=2,
                               extra=["--strictness", "leaky"]))
    ran = fresh(["run", "--yes"], prog=prog, world=world,
                env={"PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}", KEY_VAR: KEY})
    assert ran.code == 0, ran
    assert last_verdict(ran.out)[0] == "done", ran
    assert ran.record["ended"] == "returned", ran.record
    # the leak rule (ruled 2026-10-12): every file of every run folder, traces included, holds no
    # twelve characters of the key's secret part, and `run.log` no four
    assert_clean(ran, "run", world.work / "runs")
    assert [line for line in ran.err_lines if line.startswith("note: ")], ran


@needs_uv
def test_fd5_19_one_episode_failed_is_done_exit_0_and_resumed_not_complete(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three tasks of depth 1, two calls each, one at a time; the fixture refuses the sixth
    completion, the last episode's last call, so exactly one episode fails."""
    write_config(world.work / "tasks.toml",
                 fixture_flags(fixture.base_url, model="fixture-429-after-5", tasks_per_level=3,
                               concurrency=1))
    plan = plan_of(world.work / "tasks.toml")
    first = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
    assert first.code == 0, first
    assert last_verdict(first.out)[0] == "done", first
    folder = run_folders(world)[0]
    assert len(scored_tasks(plan, folder)) == 3
    assert runs().find_run(plan, world.work / "runs").status == "resume"
    fixture.forget()
    started = fixture.episodes_started()
    second = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
    assert second.code == 0, second
    assert last_verdict(second.out)[0] == "done"
    assert fixture.episodes_started() - started == 1
    seen = len(fixture.requests)
    third = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
    assert third.code == 0 and third.word == "done", third
    assert len(fixture.requests) == seen
    assert run_folders(world) == [folder]


# ---------------------------------------------------------------------------
# the key check
# ---------------------------------------------------------------------------


@needs_uv
@pytest.mark.parametrize("case", ["refused", "model-missing", "unreachable"])
def test_fd5_19_a_key_check_that_fails_refuses_with_the_librarys_line_and_sends_nothing(
    case: str, harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = fixture.base_url if case != "unreachable" else f"http://127.0.0.1:{free_port()}/v1"
    model = {"refused": "fixture-401", "model-missing": "not-served"}.get(case,
                                                                         "fixture-reference")
    monkeypatch.setenv(KEY_VAR, SENTINEL)
    provider = "openai-compatible" if case == "model-missing" else "openai"
    made = write_config(world.work / "tasks.toml",
                        fixture_flags(base, model=model, provider=provider))
    ran = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
    found = providers().check_key(made.model)
    assert found.status == {"refused": providers().REFUSED,
                            "model-missing": providers().MODEL_MISSING,
                            "unreachable": providers().UNREACHABLE}[case]
    assert ran.code == 1, ran
    lines = error_lines(ran)
    assert len(lines) == 1 and lines[0].startswith(f"error: {found.detail}"), ran
    assert fixture.posts() == []
    assert run_folders(world) == []
    assert leaked(ran.out + ran.err, KEY_BODY) == []


@needs_uv
def test_fd5_19_a_key_check_that_cannot_tell_still_shows_the_plan_and_asks(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    front = NotCheckable(fixture.port)
    try:
        made = write_config(world.work / "tasks.toml", fixture_flags(front.base_url))
        assert providers().check_key(made.model).status == providers().NOT_CHECKABLE
        stdin = Answers(["n"])
        asked = invoke(["run"], prog=prog, monkeypatch=monkeypatch, stdin=stdin)
        assert asked.code == 1, asked
        assert asked.word == "plan", asked
        assert providers().NOT_CHECKABLE in asked.out, asked
        assert harness_line(asked.out), asked
        assert stdin.reads == 1
        assert last_verdict(asked.out)[0] == "stopped"
        assert fixture.posts() == [] and run_folders(world) == []
        made_run = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
        assert made_run.code == 0, made_run
        assert last_verdict(made_run.out)[0] == "done"
        assert fixture.calls() == 2
    finally:
        front.close()


# ---------------------------------------------------------------------------
# the plan: uv's installer, and nothing before the user says yes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flags", [[], ["--recipe", "card"],
                                   ["--recipe", "custom", "--knob", "distractor", "--levels",
                                    "0,8", "--controls", "--tasks-per-level", "2"]],
                         ids=["first-look", "card", "custom"])
def test_fd5_19_every_plan_discloses_uvs_installer(
    flags: list[str], prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(world.work / "tasks.toml", flags)
    ran = invoke(["run", "--dry-run", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert ran.word == "plan", ran
    assert harness_line(ran.out), ran
    assert run_folders(world) == [] and ran.connections == []


@needs_uv
def test_fd5_19_a_resumed_runs_plan_discloses_uvs_installer(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    count, cap = partial_design()
    write_config(world.work / "tasks.toml",
                 fixture_flags(fixture.base_url, levels="1,3", tasks_per_level=count,
                               concurrency=1, spend_cap=cap))
    assert invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch).code == 3
    ran = invoke(["run", "--dry-run", "--spend-cap", str(cap * 4)], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert ran.word == "plan" and harness_line(ran.out), ran


@needs_uv
@pytest.mark.parametrize("how", ["a-pipe", "answered-no"])
def test_fd5_19_nothing_is_sent_written_or_started_before_the_user_says_yes(
    how: str, harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark = "fd5-ask-" + os.urandom(6).hex()
    monkeypatch.setenv(MARK, mark)
    write_config(world.work / "tasks.toml", fixture_flags(fixture.base_url, tasks_per_level=2))
    stdin = None if how == "a-pipe" else Answers(["n"])
    before = [tree_of(world.work), tree_of(world.home), tree_of(world.tmp)]
    ran = invoke(["run"], prog=prog, monkeypatch=monkeypatch, stdin=stdin)
    assert ran.code == 1, ran
    assert ran.word == "plan", ran
    assert harness_line(ran.out), ran
    if how == "a-pipe":
        assert len(error_lines(ran)) == 1 and "--yes" in error_lines(ran)[0], ran
    else:
        assert last_verdict(ran.out)[0] == "stopped"
    assert fixture.posts() == []
    assert [tree_of(world.work), tree_of(world.home), tree_of(world.tmp)] == before
    assert set(marked_processes(mark)) & set(marked_processes(mark)) == set(), (
        "a process was started; the marker is in this process, so `ps` itself carries it and "
        "only a pid seen twice is one left running")
    yes = invoke(["run"], prog=prog, monkeypatch=monkeypatch, stdin=Answers(["y"]))
    assert yes.code == 0, yes
    assert fixture.calls() == 4


def tree_of(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*"))


# ---------------------------------------------------------------------------
# FD5.20 Windows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("file", ["absent", "not-toml", "valid"])
def test_fd5_20_on_windows_run_refuses_in_one_line_before_reading_the_settings_file(
    file: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    import platform

    path = world.work / "tasks.toml"
    if file == "not-toml":
        path.write_text("this is [[not toml\n", encoding="utf-8")
    elif file == "valid":
        write_config(path, [])
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    with recording_opens() as opened:
        ran = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    assert ran.out == ""
    assert len(ran.err_lines) == 1 and ran.err_lines[0].startswith("error: "), ran
    assert "macOS" in ran.err_lines[0] and "Linux" in ran.err_lines[0], "the platforms it needs"
    assert str(path) not in opened and str(path.resolve()) not in opened


# ---------------------------------------------------------------------------
# the run folder
# ---------------------------------------------------------------------------


@needs_uv
def test_fd5_19_a_changed_plan_gets_a_new_folder_and_its_plan_says_what_changed(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_config(world.work / "tasks.toml", fixture_flags(fixture.base_url))
    assert invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch).code == 0
    first = run_folders(world)
    write_config(world.work / "tasks.toml",
                 fixture_flags(fixture.base_url, model="fixture-overshoot"))
    changed = runs().find_run(plan_of(world.work / "tasks.toml"), world.work / "runs")
    assert changed.status == "new" and changed.previous == first[0].name and changed.changed
    ran = invoke(["run", "--dry-run", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert changed.name in ran.out and first[0].name in ran.out, ran
    for field in changed.changed:
        assert field in ran.out, field
    assert run_folders(world) == first


@needs_uv
def test_fd5_19_run_naming_a_folder_that_is_not_there_is_the_librarys_refusal(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_config(world.work / "tasks.toml", fixture_flags(fixture.base_url))
    plan = plan_of(world.work / "tasks.toml")
    with pytest.raises(ValueError) as refused:
        runs().find_run(plan, Path("runs"), name="nope")
    ran = invoke(["run", "--yes", "--run", "nope"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    assert error_lines(ran) == [f"error: {refused.value}"], ran
    assert fixture.posts() == []


# ---------------------------------------------------------------------------
# Ctrl-C, then the resume
# ---------------------------------------------------------------------------


@needs_uv
def test_fd5_19_ctrl_c_stops_with_130_and_the_next_run_resumes_to_done(
    harness_env: Path, prog: str, world: World, monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark = "fd5-ctrl-c-" + os.urandom(6).hex()
    with FixtureModel(slow_seconds=1.5) as fixture:
        write_config(world.work / "tasks.toml",
                     fixture_flags(fixture.base_url, model="fixture-slow", tasks_per_level=6,
                                   concurrency=1))
        plan = plan_of(world.work / "tasks.toml")
        job = world.tmp / "job.json"
        record = world.tmp / "record.json"
        job.write_text(json.dumps({"argv": ["run", "--yes"], "prog": prog,
                                   "record": str(record)}), encoding="utf-8")
        env = base_env(world, {"PATH": os.environ["PATH"], KEY_VAR: KEY, MARK: mark})
        out = (world.tmp / "stdout.txt").open("wb")
        err = (world.tmp / "stderr.txt").open("wb")
        process = subprocess.Popen([sys.executable, "-P", str(CHILD), str(job)],
                                   cwd=world.work, env=env, stdout=out, stderr=err,
                                   start_new_session=True)
        out.close()
        err.close()
        def folder_of() -> Path | None:
            return next(iter(sorted((world.work / "runs").glob("*/"))), None)

        def one_ended() -> bool:
            folder = folder_of()
            return folder is not None and len(ledger_lines(folder)) >= 1

        try:
            assert wait_until(one_ended, 120), "no episode ended"
            os.killpg(process.pid, signal.SIGINT)
            code = process.wait(60)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(10)
        stdout = (world.tmp / "stdout.txt").read_text(encoding="utf-8")
        stderr = (world.tmp / "stderr.txt").read_text(encoding="utf-8")
        assert code == 130, (stdout, stderr)
        assert json.loads(record.read_text(encoding="utf-8"))["ended"] == "returned", stderr
        assert "Traceback" not in stderr, stderr
        assert last_verdict(stdout)[0] == "stopped", stdout
        assert f"{prog} run" in next_commands(stdout), stdout
        assert wait_until(lambda: not marked_processes(mark), 20), marked_processes(mark)
        folder = folder_of()
        assert folder is not None
        assert 1 <= len(scored_tasks(plan, folder)) < 6
        resumed = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
        assert resumed.code == 0, resumed
        assert last_verdict(resumed.out)[0] == "done"
        assert scored_tasks(plan, folder) == planned_tasks(plan)
    for pid in marked_processes(mark):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def test_fd5_19_the_dry_run_writes_nothing(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A model with no published card of its own, so the estimate's source, model A's card, is
    named apart from the model."""
    write_config(world.work / "tasks.toml", ["--model", "another-model"])
    plan = plan_of(world.work / "tasks.toml")
    ran = invoke(["run", "--dry-run", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    folder = runs().find_run(plan, world.work / "runs")
    assert folder.name in ran.out
    estimate = runs().estimate(plan)
    assert f"{estimate.episodes:,}" in ran.first, ran.first
    assert estimate.source in ran.out, ran
    assert plan.model.name in ran.first
    assert sorted(p.name for p in world.work.iterdir()) == ["tasks.toml"]


@needs_uv
def test_fd5_19_again_starts_a_second_folder_and_run_names_one(
    harness_env: Path, fixture: FixtureModel, prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spec §4.3 and §8.5: `--again` runs the same plan in a new folder, `-2`; `--run NAME`
    reports the folder named, here complete, sending nothing."""
    write_config(world.work / "tasks.toml", fixture_flags(fixture.base_url))
    assert invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch).code == 0
    first = run_folders(world)
    again = invoke(["run", "--yes", "--again"], prog=prog, monkeypatch=monkeypatch)
    assert again.code == 0, again
    folders = run_folders(world)
    assert len(folders) == 2 and folders[1].name == f"{first[0].name}-2", folders
    assert folders[1].name in again.out
    assert fixture.calls() == 4
    seen = len(fixture.requests)
    named = invoke(["run", "--yes", "--run", first[0].name], prog=prog, monkeypatch=monkeypatch)
    assert named.code == 0 and named.word == "done", named
    assert len(fixture.requests) == seen

