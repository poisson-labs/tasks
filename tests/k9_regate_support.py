"""What the re-gate tests share: phase 1's gate as the probe's driver first built it, phase 1's
records with no-calls where a test puts them, a fake model that answers chosen episodes in plain
text, and a phase 1 that failed under the first gate, made by the driver itself.

The tests are `tests/test_k9_regate.py`; its docstring says what they pin.  Nothing here asserts
anything a test relies on, except that the folders it makes failed the way they were made to.
"""

from __future__ import annotations

import io
import json
import shutil
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import tests.k9_fake as k9_fake
from poisson_tasks import calibration as cal
from tests.fd2_fakes import free_port, network_guard
from tests.k9_fake import Behaviour, running
from tests.k9_support import ARMS, BASES, episode, env_file, harness, mixed, small_design

PHASE1 = (1180681854, 601375552, 2652385879)
"""Phase 1's three seeds, in the order drawn, typed here."""
ASKED = (
    "I need the record_id for the booking ledger entry to proceed. Please confirm the record_id."
)
"""What a silent episode answers: the gpt-5-nano reply that stopped the first run, shortened."""

ONE = (("block:k8", 1180681854),)
"""The first run's one no-call: `block:k8` at phase 1's first seed."""
THREE = (("block:k8", 1180681854), ("shape:w1", 601375552), ("spread:p1", 2652385879))
"""Three no-calls on three base arms, one at each seed.  The fake plays a task two arms share as
the first of them (`arguments:a2`'s phase 1 tasks are `history:t0`'s), so these are base arms
whose first turn is their own; `spread:p1`'s is also `spread:p4`'s, a top, which phase 1 checks
for plumbing alone."""

# ---------------------------------------------------------------------------
# the first gate, as built at d5c93aa
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OldVerdict:
    passed: bool
    reasons: tuple[str, ...]


def old_phase1_verdict(
    records: Mapping[str, Sequence[cal.EpisodeRecord]],
    tallies: Mapping[str, Mapping[str, int]],
    *,
    design: Any = None,
) -> Any:
    """Phase 1's gate before 2026-10-13, written out here: the cards' plumbing gate in full on the
    base arms' episodes pooled (any one without a tool call stops it), and plumbing alone on every
    arm.  Returns the driver's own verdict type, so the driver writes what it wrote then."""
    from poisson_tasks import knob_probe as probe

    design = probe.DESIGN if design is None else design
    planned = design.phase1_episodes_per_arm
    bases = [arm for arm in design.arms if arm in BASES]
    base_rows = [row for arm in bases for row in records.get(arm, ())]
    merged: dict[str, int] = {}
    for arm in bases:
        for label, count in tallies.get(arm, {}).items():
            merged[label] = merged.get(label, 0) + int(count)
    gate = cal.plumbing_gate(base_rows, merged)
    reasons = [f"base arms: {reason}" for reason in gate.reasons]
    plumbing: dict[str, tuple[str, ...]] = {}
    for arm in design.arms:
        rows = list(records.get(arm, ()))
        tally = tallies.get(arm, {})
        found: list[str] = []
        if len(rows) < planned:
            found.append(f"{len(rows)} of its {planned} episodes were recorded")
        labelled = sum(1 for row in rows if row.label in cal.INSTRUMENT_LABELS)
        if labelled:
            found.append(f"{labelled} of its episodes carry an instrument label")
        if sum(tally.values()):
            found.append(f"its instrument tally is not empty: {dict(tally)}")
        if found:
            plumbing[arm] = tuple(found)
            reasons += [f"{arm}: {reason}" for reason in found]
    return probe.Phase1Verdict(
        passed=not reasons, reasons=tuple(reasons), bases=gate, plumbing=plumbing
    )


# ---------------------------------------------------------------------------
# phase 1's records, made up
# ---------------------------------------------------------------------------


def phase1_records(
    silent: Iterable[tuple[str, int]] = (),
    *,
    seeds: Sequence[int] = PHASE1,
    model: str = "gpt-5-nano-2025-08-07",
    short: Iterable[str] = (),
    labelled: Iterable[tuple[str, int]] = (),
    skip: Iterable[tuple[str, int]] = (),
) -> dict[str, list[cal.EpisodeRecord]]:
    """Every arm's phase 1 episodes, each reaching its minimum and passing, but those (arm, seed)
    in `silent` (no tool call), `labelled` (an instrument label) and `skip` (not recorded), and
    every episode of an arm in `short` (one call short of its minimum)."""
    quiet, marked, gone, shorts = set(silent), set(labelled), set(skip), set(short)
    out: dict[str, list[cal.EpisodeRecord]] = {}
    for arm in ARMS:
        minimum = cal._minimum_calls(arm)
        assert minimum is not None
        rows = []
        for seed in seeds:
            if (arm, seed) in gone:
                continue
            if (arm, seed) in marked:
                rows.append(episode(arm, seed, 0, model=model, label="api_error", calls=0))
            elif (arm, seed) in quiet:
                rows.append(episode(arm, seed, 0, model=model, calls=0))
            elif arm in shorts:
                rows.append(episode(arm, seed, 0, model=model, calls=minimum - 1))
            else:
                rows.append(episode(arm, seed, 0, model=model, passed=True, calls=minimum))
        out[arm] = rows
    return out


def spread_silent(count: int, seeds: Sequence[int] = PHASE1) -> tuple[tuple[str, int], ...]:
    """`count` base episodes without a tool call, spread over the base arms and the seeds."""
    slots = [(arm, seed) for seed in seeds for arm in BASES]
    return tuple(slots[:count])


# ---------------------------------------------------------------------------
# the fake model, answering chosen episodes in plain text
# ---------------------------------------------------------------------------


@contextmanager
def silent_at(mp: pytest.MonkeyPatch, silent: Iterable[tuple[str, int]]) -> Iterator[None]:
    """The fake answers the first turn of each (arm, seed) in `silent` in plain text, with no tool
    call, as gpt-5-nano did; every other request as `k9_fake.reply_for` does."""
    quiet = set(silent)
    original = k9_fake.reply_for

    def reply(body: Mapping[str, Any], registry: Any, behaviour: Behaviour) -> dict[str, Any]:
        found = k9_fake._match(
            registry, list(body.get("messages") or []), body.get("tools") or []
        )
        if found is not None:
            entry, calls, _ = found
            if not calls and (entry.arm, entry.seed) in quiet:
                answer = original(body, {}, behaviour)
                answer["choices"][0]["message"] = {"role": "assistant", "content": ASKED}
                return answer
        return original(body, registry, behaviour)

    mp.setattr(k9_fake, "reply_for", reply)
    yield


# ---------------------------------------------------------------------------
# a folder whose phase 1 failed under the first gate, made by the driver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Failed:
    """A run folder the driver wrote with the first gate, kept as it was: copy it to use it.
    `port` is the fake's, which the folder's record names."""

    folder: Path
    port: int
    spent: float


def drive(
    where: Path,
    folder: Path,
    *,
    port: int,
    cache: Path,
    cap: float = 5.0,
    silent: Iterable[tuple[str, int]] = (),
    old_gate: bool = False,
    behaviour: Behaviour | None = None,
    concurrency: int = 8,
) -> dict[str, Any]:
    """`run_probe` on the smaller design into `folder` against the fake on `port`: its exit code,
    its lines, its refusals and the requests the fake saw."""
    from poisson_tasks import knob_probe as probe

    design = small_design()
    out, err = io.StringIO(), io.StringIO()
    with pytest.MonkeyPatch.context() as mp, harness(where, mp), network_guard(mp):
        if old_gate:
            mp.setattr(probe, "phase1_verdict", old_phase1_verdict)
        with silent_at(mp, silent), running(
            design.arms,
            [*design.phase1_seeds, *design.probe_seeds],
            behaviour or mixed(),
            cache=cache,
            port=port,
        ) as fake:
            with redirect_stdout(out), redirect_stderr(err):
                code = probe.run_probe(
                    folder,
                    cap=cap,
                    concurrency=concurrency,
                    env_file=env_file(where),
                    base_url=fake.base_url,
                    design=design,
                )
            chats, gets = len(fake.posts), list(fake.gets)
    return {"code": code, "out": out.getvalue(), "err": err.getvalue(), "chats": chats,
            "gets": gets}


def failed_phase1(where: Path, silent: Sequence[tuple[str, int]], cache: Path) -> Failed:
    """Phase 1 run by the driver with the first gate, the fake silent at `silent`: it fails on
    the no-call clause alone, as the first gpt-5-nano run did."""
    port = free_port()
    folder = where / "run"
    found = drive(where, folder, port=port, cache=cache, silent=silent, old_gate=True)
    phase1 = json.loads((folder / "phase1.json").read_text())
    assert found["code"] == 2, found["out"] + found["err"]
    assert phase1["reasons"] == [f"base arms: {len(silent)} of 21 episodes made no tool call"], (
        phase1["reasons"]
    )
    assert sum(1 for row in phase1["per_episode"] if row["tool_calls"] == 0) == len(silent)
    return Failed(folder=folder, port=port, spent=float(phase1["spent"]))


def copy_of(failed: Failed, where: Path) -> Path:
    """A copy of the failed folder at `where/run`, where a test may change it."""
    target = where / "run"
    shutil.copytree(failed.folder, target)
    return target


def tree(folder: Path) -> dict[str, bytes]:
    """Every file under `folder`, by its path within it, as bytes."""
    return {
        str(path.relative_to(folder)): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def regate(
    folder: Path, reason: str, *, design: Any = None
) -> tuple[int, str, str]:
    """`knob_probe.regate_phase1` in this process: its exit code, stdout and stderr."""
    from poisson_tasks import knob_probe as probe

    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = probe.regate_phase1(
            folder, reason, design=small_design() if design is None else design
        )
    return code, out.getvalue(), err.getvalue()


def ledger_total(folder: Path) -> float:
    path = folder / "spend.jsonl"
    if not path.exists():
        return 0.0
    return sum(
        float(json.loads(line)["dollars"])
        for line in path.read_text().splitlines()
        if line.strip()
    )
