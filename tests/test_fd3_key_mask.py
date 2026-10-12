"""The run engine's key mask: the key where a provider can put it, and nothing else, frozen as tests.

FD3.16, amended and ruled 2026-10-12 (`tests/keymask_support.py` states the rule).  The mask it
replaces rewrote every run of four characters of the key anywhere in a trace line: every OpenAI
project key holds `-pro`, the tasks' item codes hold it too, and so about 95% of a probe run's
trace lines were rewritten, a number masked broke the JSON, and a masked reply or argument failed
the replay check.

- **Kept.** A run with a project key whose secret part shares runs of up to eleven characters with
  the run's own text writes every trace line byte for byte as the wheel's own writer writes the
  episode it finished, and the records read from them pass the replay check.
- **Masked where a provider can put it.** A provider that refuses the key and quotes it back,
  whole, masked and in part: every error the traces record, the first error and `run.log` hold no
  four characters of the secret part in a row; the public prefix stays, and so do the provider's
  other words; every line is still JSON the wheel reads; everything but the error texts is the
  wheel's own; and no file, the result and neither stream holds twelve.
- **Masked anywhere it is the key's.** A provider that puts the key in a reply: the key and a run
  of twelve of it are masked in that string, a run of eleven is kept, and the rest of the line is
  the wheel's own.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import (
    KEY_VAR,
    arm_dir,
    harness_env,
    make_plan,
    needs_uv,
    run_here,
)
from tests.keymask_support import (
    ECHO_MODEL,
    KEY_RUN,
    KEYS,
    PREFIXES,
    PROJECT_KEY,
    PROJECT_SECRET,
    REFUSED_MODEL,
    KeyQuoting,
    echo,
    echo_masked,
    error_texts,
    key_runs,
    longest_run,
    masked_runs,
    strings,
    without_error_texts,
)

__all__ = ["harness_env"]

pytestmark = needs_uv

ARMS = ("depth:d1", "similarity:s1", "faults:f1", "spread:p1")
"""A published knob's arm and three the replay check covers."""


@pytest.fixture
def quoting(request: pytest.FixtureRequest) -> Iterator[KeyQuoting]:
    secret = getattr(request, "param", PROJECT_SECRET)
    model = KeyQuoting(secret)
    model.start()
    try:
        yield model
    finally:
        model.close()


@pytest.fixture
def finished(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Every episode the run finished, as verifiers handed it over (`record_run` is the first
    thing the run does with one)."""
    from verifiers.v1.episode import Episode

    seen: list[Any] = []
    original = Episode.record_run

    def record_run(self: Any, run: Any) -> None:
        original(self, run)
        seen.append(self)

    monkeypatch.setattr(Episode, "record_run", record_run)
    return seen


def wheel_lines(episodes: list[Any], where: Path) -> dict[str, bytes]:
    """Each episode as the wheel's own writer writes it, by its id."""
    from verifiers.v1.cli.output import write_episode

    where.mkdir(parents=True, exist_ok=True)
    out: dict[str, bytes] = {}
    for episode in episodes:
        path = where / "traces.jsonl"
        path.unlink(missing_ok=True)
        write_episode(where, episode)
        out[str(episode.id)] = path.read_bytes()
    return out


def written_lines(folder: Path) -> dict[str, bytes]:
    """Each trace line of every arm of a run folder, with its newline, by its episode's id."""
    out: dict[str, bytes] = {}
    for path in sorted(folder.glob("*/traces.jsonl")):
        for line in path.read_bytes().splitlines(keepends=True):
            out[str(json.loads(line)["id"])] = line
    return out


def every_text(folder: Path) -> list[tuple[str, str]]:
    return [
        (str(path), path.read_bytes().decode("utf-8", "replace"))
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    ]


# ---------------------------------------------------------------------------
# kept: what the run produced
# ---------------------------------------------------------------------------


def test_a_project_keys_run_writes_every_trace_line_as_the_wheel_writes_it(
    tmp_path: Path,
    harness_env: Path,
    quoting: KeyQuoting,
    finished: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from poisson_tasks import calibration

    monkeypatch.setenv(KEY_VAR, PROJECT_KEY)
    plan = make_plan(quoting.base_url, arms=ARMS, seeds=(404, 55))
    folder, result = run_here(plan, tmp_path, monkeypatch, concurrency=4)
    assert result.verdict == "done", result
    path = Path(folder.path)
    written = written_lines(path)
    assert len(written) == len(ARMS) * 2

    text = b"".join(written.values()).decode("utf-8")
    assert "-pro" in text, "no trace line holds the project prefix's -pro"
    assert all(
        longest_run(line.decode("utf-8"), PROJECT_SECRET) >= 6 for line in written.values()
    ), "a line meets none of the key's runs"
    assert longest_run(text, PROJECT_SECRET) == KEY_RUN - 1

    assert written == wheel_lines(finished, tmp_path / "wheel")
    for spec in plan.arms:
        records = calibration.records_from_run(path / arm_dir(spec), model="fixture-reference")
        labels = [row.label for row in records]
        assert len(labels) == 2 and not {"replay_mismatch", "api_error"} & set(labels), labels


# ---------------------------------------------------------------------------
# masked where a provider can put it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "quoting", [secret for _, secret in KEYS.values()], indirect=True, ids=list(KEYS)
)
def test_the_key_a_provider_quotes_back_is_masked_in_its_errors_the_log_and_the_first_error(
    tmp_path: Path,
    harness_env: Path,
    quoting: KeyQuoting,
    finished: list[Any],
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    from verifiers.v1.cli.output import read_episodes
    from verifiers.v1.trace import Trace

    name = next(name for name, (_, secret) in KEYS.items() if secret == quoting.secret)
    key, secret = KEYS[name]
    monkeypatch.setenv(KEY_VAR, key)
    plan = make_plan(quoting.base_url, model=REFUSED_MODEL, seeds=(404, 55))
    folder, result = run_here(plan, tmp_path, monkeypatch, concurrency=1)
    assert result.verdict == "stopped" and result.first_error, result
    assert any(seen.headers.get("authorization") == f"Bearer {key}" for seen in quoting.posts()), (
        "the key never reached the endpoint"
    )
    path = Path(folder.path)
    log = (path / "run.log").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in written_lines(path).values()]
    errors = [text for row in rows for text in error_texts(row)]
    assert rows and errors, "no error was recorded: the test did not reach its case"

    for text in [log, str(result.first_error), *errors]:
        assert masked_runs(text, secret) == [], text
    for where, text in every_text(path) + [("result", repr(result))]:
        assert key_runs(text, secret) == [], where
    out, err = capfd.readouterr()
    assert key_runs(out, secret) == [] and key_runs(err, secret) == []

    prefix = PREFIXES.get(name)
    messages = [text for row in rows for text in error_texts(row, ("message",))]
    if prefix is not None:
        for text in [log, str(result.first_error), *messages]:
            assert f"{prefix}****" in text and "project's keys" in text, text
    if name == "project":
        assert f"it starts {secret[:3]} )" in str(result.first_error)

    assert len(read_episodes(path / arm_dir(plan.arms[0]), Trace)) == len(rows)
    wheel = wheel_lines(finished, tmp_path / "wheel")
    for row in rows:
        assert without_error_texts(row) == without_error_texts(json.loads(wheel[row["id"]]))


# ---------------------------------------------------------------------------
# masked anywhere it is the key's
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "quoting", [KEYS["project"][1], KEYS["escaped"][1]], indirect=True, ids=["project", "escaped"]
)
def test_a_key_quoted_in_a_reply_is_masked_in_that_string_alone_and_the_line_stays_json(
    tmp_path: Path,
    harness_env: Path,
    quoting: KeyQuoting,
    finished: list[Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from verifiers.v1.cli.output import read_episodes
    from verifiers.v1.trace import Trace

    key, secret = next(pair for pair in KEYS.values() if pair[1] == quoting.secret)
    monkeypatch.setenv(KEY_VAR, key)
    plan = make_plan(quoting.base_url, model=ECHO_MODEL, seeds=(404, 55))
    folder, result = run_here(plan, tmp_path, monkeypatch, concurrency=1)
    assert result.verdict == "done", result
    path = Path(folder.path)
    written = written_lines(path)
    for where, text in every_text(path):
        assert key_runs(text, secret) == [], where

    said, wanted = echo(key, secret), echo_masked(key, secret)
    wheel = wheel_lines(finished, tmp_path / "wheel")
    assert set(written) == set(wheel)
    for episode_id, line in written.items():
        row, made = json.loads(line), json.loads(wheel[episode_id])
        assert said in list(strings(made)), "the reply did not quote the key"
        assert wanted in list(strings(row))
        assert row == json.loads(
            json.dumps(made).replace(json.dumps(said)[1:-1], json.dumps(wanted)[1:-1])
        )
    assert len(read_episodes(path / arm_dir(plan.arms[0]), Trace)) == len(written)
