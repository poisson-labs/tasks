"""What the knob probe's test files share: made-up records, a smaller design for the runs at no
cost, the fake model's behaviours, and the notebook's rig with the fake in vLLM's place.

The test files are `tests/test_k9_*.py`; each says in its own docstring what it pins.  Nothing here
asserts anything.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from tests.k9_fake import Behaviour

REPO = Path(__file__).resolve().parents[1]
FAKE = Path(__file__).with_name("k9_fake.py")
MODEL = "gpt-5-nano-2025-08-07"
OTHER = "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218"
KEY = "sk-k9-FIXTURE-QXZQXZQXZQXZQXZQXZ"
"""The fixture key the runs here send: no four characters of it in a row occur in any other
text a run writes."""

ARMS = (
    "similarity:s0",
    "faults:f0",
    "history:t0",
    "block:k8",
    "arguments:a2",
    "shape:w1",
    "spread:p1",
    "similarity:s3",
    "faults:f4",
    "history:t2400",
    "block:k64",
    "arguments:a8",
    "shape:w4",
    "spread:p4",
    "faults:f0+len(f4)",
    "block:k8+len(k64)",
    "arguments:a2+len(a8)",
    "shape:w1+len(w4)",
)
"""The eighteen arms of the spec's table, in the order it says they run, typed here and not
read from the module under test."""
BASES, TOPS, CONTROLS = ARMS[:7], ARMS[7:14], ARMS[14:]

# ---------------------------------------------------------------------------
# made-up records
# ---------------------------------------------------------------------------


def seeds60() -> tuple[int, ...]:
    from tests.k2_support import PROBE_SEEDS

    return PROBE_SEEDS[3:]


def episode(
    arm: str,
    seed: int,
    attempt: int,
    *,
    model: str = MODEL,
    passed: bool = False,
    label: str | None = None,
    calls: int = 2,
    gave_up: bool | None = None,
    leaky: bool | None = None,
) -> cal.EpisodeRecord:
    if label is None:
        label = "passed" if passed else "wrong_state"
    return cal.EpisodeRecord(
        task_id=f"{arm}/{seed}",
        arm_id=arm,
        model=model,
        seed=seed,
        attempt=attempt,
        strict=label == "passed",
        leaky=(label == "passed") if leaky is None else leaky,
        label=label,
        turns=calls + 1,
        sampled_calls=calls,
        prompt_tokens=1000,
        cached_input_tokens=200,
        completion_tokens=300,
        reasoning_tokens=100,
        episode_seconds=4.0 + attempt,
        model_seconds=3.0,
        harness_seconds=1.0,
        gave_up_after_fault=gave_up,
    )


def cell(
    arm: str,
    passes: int | Iterable[int],
    *,
    model: str = MODEL,
    seeds: Sequence[int] | None = None,
    attempts: int = 2,
    no_call: Iterable[int] = (),
    instrument: Iterable[tuple[int, int]] = (),
    half: Iterable[int] = (),
    gave_up: Iterable[int] = (),
) -> list[cal.EpisodeRecord]:
    """An arm's records: at the seed positions in `passes` (or the first `passes` of them) every
    attempt passes, at those in `half` the first attempt passes and the second fails, at those in
    `no_call` every attempt fails without calling a tool, and each (position, attempt) in
    `instrument` carries an instrument label.  Everything else fails with a wrong state."""
    seeds = list(seeds60() if seeds is None else seeds)
    passing = set(range(passes)) if isinstance(passes, int) else set(passes)
    halves, silent, labelled = set(half), set(no_call), set(instrument)
    quitters = set(gave_up)
    out: list[cal.EpisodeRecord] = []
    for index, seed in enumerate(seeds):
        for attempt in range(attempts):
            judged = (index in quitters) if arm.startswith("faults:f4") else None
            if (index, attempt) in labelled:
                out.append(
                    episode(
                        arm, seed, attempt, model=model, label="api_error", calls=0, gave_up=judged
                    )
                )
            elif index in passing or (index in halves and attempt == 0):
                out.append(episode(arm, seed, attempt, model=model, passed=True, gave_up=judged))
            elif index in silent:
                out.append(episode(arm, seed, attempt, model=model, calls=0, gave_up=judged))
            else:
                out.append(episode(arm, seed, attempt, model=model, calls=1, gave_up=judged))
    return out


def model_run(
    cells: Mapping[str, list[cal.EpisodeRecord]],
    *,
    tallies: Mapping[str, Mapping[str, int]] | None = None,
    reruns: Sequence[Mapping[str, Any]] = (),
    facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One model's run, as `knob_probe.analyse` takes it."""
    return {
        "records": [row for rows in cells.values() for row in rows],
        "tallies": {arm: dict(t) for arm, t in (tallies or {}).items()},
        "reruns": list(reruns),
        "facts": dict(facts or {"concurrency": 8}),
    }


def every_arm(
    passes: Mapping[str, int],
    *,
    model: str = MODEL,
    default: int = 54,
    options: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, list[cal.EpisodeRecord]]:
    """All eighteen arms, each passing on its first `passes[arm]` seeds (`default` otherwise), so
    an arm that passes more passes on a superset of the seeds another passes on.  `options[arm]`
    is passed on to that arm's `cell` (`no_call`, `instrument`, `half`, `gave_up`)."""
    out = {arm: cell(arm, passes.get(arm, default), model=model) for arm in ARMS}
    for arm, kwargs in (options or {}).items():
        out[arm] = cell(arm, passes.get(arm, default), model=model, **dict(kwargs))
    return out


def outcome_of(result: Mapping[str, Any], knob: str) -> dict[str, Any]:
    for row in result["outcomes"]:
        if row["knob"] == knob:
            return dict(row)
    raise KeyError(knob)


# ---------------------------------------------------------------------------
# a smaller design, and the fake's behaviours
# ---------------------------------------------------------------------------


def small_design() -> Any:
    """Every arm, phase 1 as registered (three seeds, one attempt), and two of the probe's seeds at
    two attempts: 54 and 72 episodes."""
    from poisson_tasks import knob_probe as probe

    return probe.Design(
        arms=probe.ARMS, phase1_seeds=probe.PHASE1_SEEDS, probe_seeds=probe.PROBE_SEEDS[:2]
    )


def mixed() -> Behaviour:
    """Similarity, faults and block size bite; spread's top is easier; shape's narrow width is the
    harder; history and argument difficulty do not bite.  The base arms fail only at the probe's
    seeds, never at phase 1's, so phase 1 passes whatever way its base gate is read."""
    from poisson_tasks import knob_probe as probe

    probe_only = list(probe.PROBE_SEEDS)
    return Behaviour.from_mapping(
        {
            "fail": {"similarity:s3": 1.0, "block:k64": 1.0},
            "fail_at": {
                "spread:p1": probe_only,
                "shape:w1": probe_only,
                "shape:w1+len(w4)": probe_only,
            },
            "give_up": {"faults:f4": 1.0},
        }
    )


PHASE1_FAILS = Behaviour.from_mapping({"no_call": list(BASES)})
"""Every base arm answers without calling a tool."""


@contextmanager
def harness(where: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """This process's environment for a run against the fake: a `pip` that does nothing first on
    `PATH` (the harness's bootstrap must find uv and install nothing), no proxy, and the fixture
    key's variable restored afterwards."""
    stub = where / "stub-bin"
    stub.mkdir(parents=True, exist_ok=True)
    pip = stub / "pip"
    pip.write_text("#!/bin/sh\nexit 0\n")
    pip.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ.get('PATH', '')}")
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    # set then removed, so the variable the run sets is undone whether or not it was there
    monkeypatch.setenv("MODEL_API_KEY", "unset")
    monkeypatch.delenv("MODEL_API_KEY")
    yield


def env_file(where: Path, key: str = KEY) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    path = where / ".env"
    path.write_text(f"OTHER=1\nMODEL_API_KEY={key}\n")
    return path


def ledger(folder: Path) -> list[dict[str, Any]]:
    path = folder / "spend.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# the notebook's rig, with the fake in vLLM's place
# ---------------------------------------------------------------------------

KNOB_DRIVER = textwrap.dedent("""
    import sys
    from poisson_tasks import calibration_run as run
    from poisson_tasks import knob_probe as probe

    # The knob probe's design on fewer tasks: every arm, phase 1 as registered, two probe seeds.
    run.KNOB_DESIGN = probe.Design(arms=probe.ARMS, phase1_seeds=probe.PHASE1_SEEDS,
                                   probe_seeds=probe.PROBE_SEEDS[:2])
    sys.exit(run.main(sys.argv[1:]))
""")


def knob_rig(tmp: Path, behaviour: Behaviour, cache: Path) -> Any:
    """The notebook's filesystem and processes on a laptop (`helpers.Rig`), running the knob
    probe's design against the fake model as its vLLM."""
    from tests.helpers import FIXTURE, Rig

    class KnobRig(Rig):
        def argv(self, command: str, *extra: str) -> list[str]:
            made = super().argv(command, *extra)
            if command in ("install-vllm", "verify", "finalize"):
                return made
            return [*made[:2], command, "--design", "knob-probe", *made[3:]]

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "tokenizer_config.json").write_text(json.dumps({"chat_template": data["chat_template"]}))
    rig = KnobRig(tmp)
    (rig.bin / "vllm").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    (rig.bin / "pip").write_text("#!/bin/sh\nexit 0\n")
    (rig.bin / "pip").chmod(0o755)
    rig.driver.write_text(KNOB_DRIVER)
    from poisson_tasks import knob_probe as probe

    rig.env.update(
        {
            "K9_FAKE_ARMS": json.dumps(list(probe.ARMS)),
            "K9_FAKE_SEEDS": json.dumps([*probe.PHASE1_SEEDS, *probe.PROBE_SEEDS[:2]]),
            "K9_FAKE_BEHAVIOUR": json.dumps(behaviour.as_mapping()),
            "K9_FAKE_CACHE": str(cache),
            "PYTHONPATH": f"{REPO / 'src'}{os.pathsep}{REPO}",
        }
    )
    return rig


def have_uv() -> bool:
    return shutil.which("uv") is not None


needs_uv = pytest.mark.skipif(not have_uv(), reason="the `null` harness launches through uv")


def module_run(argv: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *argv],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
        **kwargs,
    )
