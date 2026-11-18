"""What the version 2 card's run-path tests share: the design typed from its table, the models and
how each is called, a smaller design for runs at no cost, and the driver run against the fake.

The test files are `tests/test_c2_*.py`; each says in its own docstring which of the run path's
invariants (C2.1 to C2.13) it pins.  Nothing here asserts anything.

Shapes decided here
-------------------
The design says what the run does and leaves its names to the tests.  These are the names the
tests hold the build to; each is used in at least one test file.

**1. The design.**  `calibration.arm_specs("card-v2")` is the 56 arms in the order they run.
`calibration.arm_specs()` stays the published generator-0 design's fourteen.

**2. The driver for a hosted model** is `poisson_tasks.card_run`, as `knob_probe` was the knob
probe's:

* `card_run.Design(arms, phase1_seeds, seeds, attempts)` and `card_run.DESIGN`, the registered
  one; `card_run.ARMS`, `BASES`, `TOPS`, `CONTROLS`, `MIDDLES`, `OWN_ARMS` (arm ids).
* `card_run.MODELS`: model id to a row with `role` (`"card"` or `"bridge"`), `provider` (the
  settings file's preset name), `base_url`, `decoding`, `price` (a `config.PriceConfig`),
  `cap` (dollars), `aliases` (other `model` values the provider documents for the id) and
  `api_surface`.
* `card_run.run_card(folder, *, model, cap, concurrency, env_file, key_var, base_url=None,
  design=DESIGN, row=None) -> int`: phase 1, then every arm, into `folder`.  0: every arm
  complete; 2: phase 1 stopped the run; 4: a stop left episodes owed; 1: refused before
  anything was spent, in one `error:` line on stderr.  Run again on the same folder, it goes on
  with what is owed.  `row` replaces the model's row of `MODELS` (a test's alias table).
* What the folder holds: `record.json` (written before the first model call), `phase1.json`,
  `status.json`, `records/episodes.jsonl` (one line per scored episode of the run proper, arm by
  arm in the design's order) and `artifact.json` once the run has finished or stopped after
  phase 1.
* `card_run.build_artifact(folder) -> dict`, `card_run.check_provenance(block)` and
  `card_run.PROVENANCE_FIELDS` (dotted paths).
* `card_run.file_run(folder, into) -> Path`: the folder's card files written under a
  `calibration/` folder.

**3. The open model** runs through the notebook's driver: `calibration_run --design card-v2`,
the pin `calibration_run.QWEN3_8_27B`, and `calibration_run.CARD_V2_DESIGN` (a `card_run.Design`;
`None` is the registered one), which a test's driver sets as `KNOB_DESIGN` is set.
"""

from __future__ import annotations

import io
import json
import os
import sys
import textwrap
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from tests.c2_fake import CLAUDE_LIKE, OPENAI_LIKE, Play, Provider, cached_registry, running
from tests.k9_fake import Behaviour

REPO = Path(__file__).resolve().parents[1]
FAKE = Path(__file__).with_name("c2_fake.py")
NOTEBOOK = REPO / "notebooks" / "calibration_model_b.ipynb"
DESIGN = "card-v2"

BUILT_IN_HASH = "98cbd21dc912bed4dbde5398748b832aae4711c2096f0092c296eab77b52eac3"
OWN_HASH = "f01bcf327965f6c8c5351cc7c985b9e1bf6cf5caacbeb8fbba2cc06215886032"
"""The frozen generators of 0.5.0, as ruled 2026-11-18: built-in at label "4", own tools at
"own-4".  Typed here, not read from the package."""

ACME_SHA256 = "5038e1bbef2e2e65c00227bf715cae357b8af056005591e35d8edc4b3251c647"
"""`tests/fixtures/o1/acme-openai-chat.json`, 2,613 bytes."""

KEY_VAR = "MODEL_API_KEY"
KEY = "sk-c2-FIXTURE-QXZQXZQXZQXZQXZQXZ"
"""The fixture key the runs here send: no four characters of its secret part in a row occur in
any other text a run writes."""

# ---------------------------------------------------------------------------
# the design, typed from its table
# ---------------------------------------------------------------------------

TABLE: dict[str, tuple[str, ...]] = {
    "depth": ("d1", "d2", "d3", "d5", "d8", "d1+h8", "d2+h5"),
    "similarity": ("s0", "s1", "s2", "s3"),
    "faults": ("f0", "f1", "f2", "f4", "f0+len(f4)"),
    "history": ("t0", "t300", "t600", "t1200", "t2400"),
    "block": ("k8", "k16", "k32", "k64", "k8+len(k64)"),
    "arguments": ("a2", "a4", "a6", "a8", "a2+len(a8)"),
    "shape": ("w1", "w2", "w4", "w1+len(w4)"),
    "spread": ("p1", "p2", "p4"),
    "timeouts": ("o0", "o1", "o2", "o4", "o0+len(o4)"),
    "ratelimits": ("r0", "r1", "r2", "r4", "r0+len(r4)"),
    "baddata": ("b0", "b1", "b2", "b3"),
}
"""The design's table of built-in arms, row by row: 52."""
OWN_TABLE: dict[str, tuple[str, ...]] = {"landed": ("l0", "l1"), "lagged": ("g0", "g1")}

BASES = (
    "depth:d1",
    "similarity:s0",
    "faults:f0",
    "history:t0",
    "block:k8",
    "arguments:a2",
    "shape:w1",
    "spread:p1",
    "timeouts:o0",
    "ratelimits:r0",
    "baddata:b0",
)
TOPS = (
    "depth:d8",
    "similarity:s3",
    "faults:f4",
    "history:t2400",
    "block:k64",
    "arguments:a8",
    "shape:w4",
    "spread:p4",
    "timeouts:o4",
    "ratelimits:r4",
    "baddata:b3",
)
CONTROLS = (
    "depth:d1+h8",
    "depth:d2+h5",
    "faults:f0+len(f4)",
    "block:k8+len(k64)",
    "arguments:a2+len(a8)",
    "shape:w1+len(w4)",
    "timeouts:o0+len(o4)",
    "ratelimits:r0+len(r4)",
)
MIDDLES = (
    "depth:d2",
    "depth:d3",
    "depth:d5",
    "similarity:s1",
    "similarity:s2",
    "faults:f1",
    "faults:f2",
    "history:t300",
    "history:t600",
    "history:t1200",
    "block:k16",
    "block:k32",
    "arguments:a4",
    "arguments:a6",
    "shape:w2",
    "spread:p2",
    "timeouts:o1",
    "timeouts:o2",
    "ratelimits:r1",
    "ratelimits:r2",
    "baddata:b1",
    "baddata:b2",
)
OWN_ARMS = ("landed:l0", "landed:l1", "lagged:g0", "lagged:g1")
BUILT_IN_ARMS = BASES + TOPS + CONTROLS + MIDDLES
ARMS = BUILT_IN_ARMS + OWN_ARMS
"""The 56 arms in the order they run: each dial's first level, then each dial's top, then the
controls, then the middle levels, then the four on acme's tool file; inside each group the
table's own order.  Typed here from the design, not read from the module under test."""
DECISION_ARMS = BASES + TOPS + CONTROLS
"""The arms a dial's decision contrast or control contrast reads, on the built-in tasks."""

PHASE1_SEEDS = (1180681854, 601375552, 2652385879)
"""The first three seeds of `poisson-tasks/knob-probe/seeds/v1`."""
TASKS, ATTEMPTS = 60, 5
EPISODES = len(ARMS) * TASKS * ATTEMPTS
PHASE1_EPISODES = len(ARMS) * len(PHASE1_SEEDS)

# ---------------------------------------------------------------------------
# the models, and how each is called
# ---------------------------------------------------------------------------

LUNA = "gpt-6-luna"
HAIKU = "claude-haiku-5-5"
NANO = "gpt-5-nano-2025-08-07"
QWEN_REPO = "Qwen/Qwen3.8-27B-FP8"
QWEN_REVISION = "c3a462cc3d38cf351f3b26cbd763469eeb74ef81"
"""The FP8 checkpoint's revision as Hugging Face reported it on 2026-11-15."""
QWEN = f"{QWEN_REPO}@{QWEN_REVISION}"

NOT_SENT = "not sent"
MAX_TOKENS = 8192
DECODING: dict[str, dict[str, Any]] = {
    LUNA: {"temperature": 1.0, "top_p": 1.0, "reasoning_effort": "low", "max_tokens": MAX_TOKENS},
    HAIKU: {
        "temperature": 1.0,
        "top_p": NOT_SENT,
        "reasoning_effort": NOT_SENT,
        "max_tokens": MAX_TOKENS,
    },
    QWEN: {"temperature": 1.0, "top_p": 1.0, "reasoning_effort": "low", "max_tokens": MAX_TOKENS},
}
"""The decoding each card's model is called with, typed from the design's table."""

PRICES: dict[str, tuple[float, float, float, str]] = {
    LUNA: (0.10, 0.01, 0.50, "2026-11-15"),
    HAIKU: (0.10, 0.01, 0.50, "2026-11-15"),
}
"""Dollars per million tokens of input, cached input and output, and the date they were read."""
CAPS = {NANO: 15.0, LUNA: 50.0, HAIKU: 65.0}
"""Taylor's caps, 2026-11-15, in dollars."""
ENDPOINTS = {
    LUNA: "https://api.openai.com/v1",
    NANO: "https://api.openai.com/v1",
    HAIKU: "https://api.anthropic.com/v1/",
}
PROVIDERS = {LUNA: OPENAI_LIKE, NANO: OPENAI_LIKE, HAIKU: CLAUDE_LIKE}
"""How the fake answers as each hosted model's provider."""

# ---------------------------------------------------------------------------
# the record's fields
# ---------------------------------------------------------------------------

RECORD_FIELDS = (
    "arm_id",
    "seed",
    "attempt",
    "strict",
    "leaky",
    "label",
    "turns",
    "sampled_calls",
    "prompt_tokens",
    "cached_input_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "length_stops",
    "answer_models",
    "episode_seconds",
)
"""What every line of a version 2 run's `episodes.jsonl` carries, by the line's key.
`turns` is the model calls and `sampled_calls` the tool calls, as on every card;
`reasoning_tokens` is `null` where the provider reports none; `length_stops` is how many of the
episode's model calls ended at the completion cap; `answer_models` is the distinct `model`
values the episode's answers carried, in the order first seen; `episode_seconds` is the
episode's seconds."""
DIAL_FIELDS = {
    "gave_up_after_fault": ("faults", "timeouts", "ratelimits"),
    "acted_on_bad_data": ("baddata", "lagged"),
    "read_again_after_bad": ("baddata", "lagged"),
    "retried_after_landed": ("landed",),
    "duplicate_write": ("landed", "lagged"),
    "first_entry_code": ("spread",),
}
"""Each dial column's key, and the dials whose arms carry it."""
FIRST_ENTRY_CODES = ("right", "joined_marker", "filler", "other", "none_sent")


def knob_of(arm: str) -> str:
    return arm.split(":", 1)[0]


# ---------------------------------------------------------------------------
# a smaller design, and the driver run against the fake
# ---------------------------------------------------------------------------


def card_run() -> Any:
    import importlib

    return importlib.import_module("poisson_tasks.card_run")


def card_seeds() -> tuple[int, ...]:
    from poisson_tasks import calibration as cal

    return tuple(cal.seed_list())


def full_size() -> bool:
    """Whether the full-size group runs at the registered size: `POISSON_TASKS_C2_FULL_SIZE=1`.
    Without it the same tests run the same three cases on the smaller design."""
    return os.environ.get("POISSON_TASKS_C2_FULL_SIZE") == "1"


def small_design(tasks: int = 2, attempts: int = 2, arms: Sequence[str] = ARMS) -> Any:
    """Every arm (or `arms`, in the design's order), phase 1 as registered (three seeds, one
    attempt), and the first `tasks` of the card's seeds at `attempts` attempts: with every arm,
    168 and, by default, 224 episodes."""
    return card_run().Design(
        arms=tuple(arm for arm in ARMS if arm in set(arms)),
        phase1_seeds=PHASE1_SEEDS,
        seeds=card_seeds()[:tasks],
        attempts=attempts,
    )


HAIKU_ARMS = ("depth:d1", "history:t2400", "spread:p1", "baddata:b3", "landed:l1", "lagged:g1")
"""The arms the Claude-like run here plays: what its tests read needs no more."""
GATE_ARMS = (
    "depth:d1",
    "similarity:s0",
    "faults:f0",
    "history:t0",
    "depth:d8",
    "shape:w2",
    "landed:l0",
    "lagged:g1",
)
"""A design for phase 1's stops: four of the built-in base arms (twelve base episodes in phase
1), a top, a middle level and two own-tools arms."""
STOP_ARMS = (
    "depth:d1",
    "spread:p1",
    "depth:d8",
    "spread:p4",
    "depth:d1+h8",
    "depth:d3",
    "spread:p2",
    "baddata:b1",
    "landed:l0",
    "landed:l1",
)
"""A design for the cap: two bases, two tops and a control (the decision arms), then three
middle levels and two own-tools arms."""


def design_seeds(design: Any) -> list[int]:
    return [*design.phase1_seeds, *design.seeds]


@contextmanager
def harness(where: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """This process's environment for a run against the fake: a `pip` that does nothing first on
    `PATH`, no proxy, and the fixture key's variable restored afterwards."""
    stub = where / "stub-bin"
    stub.mkdir(parents=True, exist_ok=True)
    pip = stub / "pip"
    pip.write_text("#!/bin/sh\nexit 0\n")
    pip.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub}{os.pathsep}{os.environ.get('PATH', '')}")
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
                 "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv(KEY_VAR, "unset")
    monkeypatch.delenv(KEY_VAR)
    yield


def env_file(where: Path, key: str = KEY) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    path = where / ".env"
    path.write_text(f"OTHER=1\n{KEY_VAR}={key}\n")
    return path


def drive(
    where: Path,
    cache: Path,
    *,
    model: str = LUNA,
    play: Play | None = None,
    cap: float = 5.0,
    concurrency: int = 8,
    folder: str = "run",
    design: Any = None,
    before: Callable[[pytest.MonkeyPatch], None] | None = None,
    port: int = 0,
    row: Any = None,
) -> dict[str, Any]:
    """`card_run.run_card` into `where/folder` against the fake, in this process: its exit code,
    its printed lines, the fake's requests, and what the folder held at the first model call.
    A folder's record holds its endpoint, so two runs into one folder pass the same `port`.
    Without `play` the fake answers as the model's own provider does and fails nothing."""
    from tests.fd2_fakes import network_guard

    chosen = small_design() if design is None else design
    if play is None:
        play = Play(provider=PROVIDERS.get(model, OPENAI_LIKE))
    out, err = io.StringIO(), io.StringIO()
    seen: dict[str, Any] = {}
    with pytest.MonkeyPatch.context() as mp, harness(where, mp), network_guard(mp):
        if before is not None:
            before(mp)
        with running(chosen.arms, design_seeds(chosen), play, cache=cache, port=port) as fake:
            record = where / folder / "record.json"
            fake.on_first_chat = lambda: seen.update(
                record=json.loads(record.read_text()) if record.exists() else None
            )
            extra = {} if row is None else {"row": row}
            with redirect_stdout(out), redirect_stderr(err):
                code = card_run().run_card(
                    where / folder,
                    model=model,
                    cap=cap,
                    concurrency=concurrency,
                    env_file=env_file(where),
                    key_var=KEY_VAR,
                    base_url=fake.base_url,
                    design=chosen,
                    **extra,
                )
            found = {
                "chats": fake.chats(),
                "gets": list(fake.gets),
                "posts": list(fake.posts),
                "matched": list(fake.matched),
            }
    return {
        "code": code,
        "out": out.getvalue(),
        "err": err.getvalue(),
        "seen": seen,
        "folder": where / folder,
        "design": chosen,
        "model": model,
        **found,
    }


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def lines(folder: Path) -> list[dict[str, Any]]:
    """The run's records, one mapping a line, as written."""
    path = folder / "records" / "episodes.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def by_arm(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    out: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        out.setdefault(str(row["arm_id"]), []).append(row)
    return out


def complete_arms(folder: Path, design: Any) -> list[str]:
    """The arms with every planned episode recorded, in the design's order."""
    per_arm = len(design.seeds) * design.attempts
    found = by_arm(lines(folder)) if (folder / "records" / "episodes.jsonl").exists() else {}
    return [arm for arm in design.arms if len(found.get(arm, [])) == per_arm]


def bodies(found: Mapping[str, Any], arm: str | None = None) -> list[dict[str, Any]]:
    """The chat requests a `drive` sent, or those played as `arm`."""
    return [
        body
        for body, matched in zip(found["posts"], found["matched"], strict=True)
        if arm is None or (matched is not None and matched[0] == arm)
    ]


def sampling(body: Mapping[str, Any]) -> dict[str, Any]:
    """A request body without its conversation: what decides how the model samples."""
    return {k: v for k, v in body.items() if k not in ("messages", "tools", "tool_choice")}


def dotted(block: Mapping[str, Any], path: str) -> Any:
    """`block` read at a dotted path; a `KeyError` naming the path when a part is missing."""
    node: Any = block
    for part in path.split("."):
        if not isinstance(node, Mapping) or part not in node:
            raise KeyError(path)
        node = node[part]
    return node


def without(block: Mapping[str, Any], path: str) -> dict[str, Any]:
    """A deep copy of `block` with the key at the dotted `path` removed."""
    copy: dict[str, Any] = json.loads(json.dumps(block))
    node: Any = copy
    parts = path.split(".")
    for part in parts[:-1]:
        node = node[part]
    del node[parts[-1]]
    return copy


_RUNS: dict[str, dict[str, Any]] = {}


def clean_run(model: str, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """One finished run of the smaller design on `model` against its provider's fake, made once
    a process and read by every test file that needs a finished folder.  gpt-6-luna's is every
    arm, with `spread:p4`'s tasks failing at the card's seeds, so the folder holds both
    outcomes; claude-haiku-5-5's is `HAIKU_ARMS`."""
    if model not in _RUNS:
        where = tmp_path_factory.mktemp("c2-clean")
        play = Play(
            behaviour=Behaviour.from_mapping({"fail_at": {"spread:p4": list(card_seeds()[:2])}}),
            provider=PROVIDERS[model],
        )
        design = small_design() if model == LUNA else small_design(arms=HAIKU_ARMS)
        _RUNS[model] = drive(
            where, registry_cache(tmp_path_factory), model=model, play=play, design=design
        )
    return _RUNS[model]


_CACHE: list[Path] = []


def registry_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Where the fake keeps its task list between the runs of one process."""
    if not _CACHE:
        _CACHE.append(tmp_path_factory.mktemp("c2-cache") / "registry")
    return _CACHE[0]


def have_uv() -> bool:
    import shutil

    return shutil.which("uv") is not None


needs_uv = pytest.mark.skipif(not have_uv(), reason="the `null` harness launches through uv")

# ---------------------------------------------------------------------------
# the notebook's rig, with the fake in vLLM's place
# ---------------------------------------------------------------------------

CARD_V2_DRIVER = textwrap.dedent("""
    import json
    import os
    import sys
    from poisson_tasks import calibration_run as run
    from poisson_tasks import card_run

    # The version 2 design on fewer tasks: every arm, phase 1 as registered, the seeds and the
    # attempts the test names.
    run.CARD_V2_DESIGN = card_run.Design(
        arms=tuple(json.loads(os.environ["C2_RIG_ARMS"])), phase1_seeds=card_run.PHASE1_SEEDS,
        seeds=tuple(json.loads(os.environ["C2_RIG_SEEDS"])),
        attempts=int(os.environ["C2_RIG_ATTEMPTS"]))
    # The rig's chat template stands in for the pinned revision's, and a test may shorten the
    # context: everything else of the pin is the driver's own.
    import dataclasses
    import hashlib
    template = json.load(open(os.environ["C2_RIG_TOKENIZER_CONFIG"]))["chat_template"]
    digest = hashlib.sha256(template.encode("utf-8")).hexdigest()
    changes = {"stock_template_sha256": digest, "template_sha256": digest}
    if os.environ.get("C2_RIG_MAX_MODEL_LEN"):
        changes["max_model_len"] = int(os.environ["C2_RIG_MAX_MODEL_LEN"])
    run.QWEN3_8_27B = dataclasses.replace(run.QWEN3_8_27B, **changes)
    sys.exit(run.main(sys.argv[1:]))
""")


GPUS = {
    "A100": "NVIDIA A100-SXM4-80GB, 580.82.07",
    "H100": "NVIDIA H100 80GB HBM3, 580.82.07",
    "L4": "NVIDIA L4, 580.82.07",
}
"""A GPU as the driver's `nvidia-smi` query prints it: name, driver version."""


def card_v2_rig(
    tmp: Path,
    play: Play,
    cache: Path,
    design: Any,
    *,
    gpu: str = "A100",
    max_model_len: int | None = None,
) -> Any:
    """The notebook's filesystem and processes on a laptop (`helpers.Rig`), running the version 2
    design against the fake model as its vLLM, on the GPU `nvidia-smi` is made to report."""
    from poisson_tasks import calibration_run as run
    from tests.helpers import Rig
    from tests.k9_support import _imported_root

    class CardV2Rig(Rig):
        def argv(self, command: str, *extra: str) -> list[str]:
            made = super().argv(command, *extra)
            if command in ("install-vllm", "verify", "finalize"):
                return made
            return [*made[:2], command, "--design", DESIGN, *made[3:]]

    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "tokenizer_config.json").write_text(json.dumps({"chat_template": "{{ messages }}"}))
    rig = CardV2Rig(tmp)
    (rig.bin / "vllm").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    (rig.bin / "nvidia-smi").write_text(f"#!/bin/sh\necho '{GPUS[gpu]}'\n")
    (rig.bin / "pip").write_text("#!/bin/sh\nexit 0\n")
    (rig.bin / "pip").chmod(0o755)
    rig.driver.write_text(CARD_V2_DRIVER)
    seeds = design_seeds(design)
    cached_registry(list(design.arms), seeds, cache)
    rig.requests = tmp / "requests.jsonl"
    rig.env.update(
        {
            "C2_FAKE_LOG": str(rig.requests),
            "C2_FAKE_ARMS": json.dumps(list(design.arms)),
            "C2_FAKE_SEEDS": json.dumps(seeds),
            "C2_FAKE_CACHE": str(cache),
            "C2_RIG_ARMS": json.dumps(list(design.arms)),
            "C2_RIG_TOKENIZER_CONFIG": str(tmp / "tokenizer_config.json"),
            "C2_RIG_SEEDS": json.dumps(list(design.seeds)),
            "C2_RIG_ATTEMPTS": str(design.attempts),
            "FAKE_VERSION": str(run.QWEN3_8_27B.vllm_version),
            "PYTHONPATH": f"{_imported_root()}{os.pathsep}{REPO}",
            **play.as_env(),
        }
    )
    if max_model_len is not None:
        rig.env["C2_RIG_MAX_MODEL_LEN"] = str(max_model_len)
    return rig


__all__ = [name for name in dir() if not name.startswith("_")] + ["Provider"]
