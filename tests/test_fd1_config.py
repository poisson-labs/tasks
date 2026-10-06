"""The settings file behind `init`: `tasks.toml`, init's flags, the provider presets and the
resolved plan, frozen as tests.

The invariants are FD1.1 to FD1.7, FD1.9, FD1.10, FD1.12 (for `config`), FD1.15 and FD1.16 of the
front door's plan, and four of the rulings of 2026-10-02 on it:
- init's default spend cap is the larger of $1.00 and twice the run's estimate, rounded up to a
  whole dollar;
- init asks for an endpoint only for the vLLM preset and for another OpenAI-compatible endpoint;
- init asks no price for the Ollama and vLLM presets;
- a misspelled strictness is refused (here, in `tasks.toml`; the export config's side is in
  `tests/test_fd1_export_arm.py`).
The arm ids, `describe_pins` and the version constant are in `tests/test_fd1_arms.py`.

Every test reaches the module through `importlib`, so the file collects on a tree that has no
`poisson_tasks.config` and each test fails there for that one reason.

Shapes decided here
-------------------

**1. The config's attributes are the file's keys.**  `ProjectConfig.model.price.cached_input` is
`[model.price] cached_input`.  The tests read a few attributes this way (the base URL, the price,
the caps) and otherwise go through the file: `dump_config`, then `tomllib`.

**2. `ConfigError.key` is the dotted path of the offending key** (`"measure.levles"`, `"mesure"`
for a table), and `.suggestion` is the dotted path of the nearest known key in the same table.
For a value that is not one of its choices (a provider, a measure, a knob, a strictness),
`.suggestion` is the nearest choice itself (`"leaky"` for `"leakey"`), as the spec's
`"dpeth" is not a knob; did you mean "depth"?` shows.  "Within two edits" is pinned only on cases
where Levenshtein and Damerau-Levenshtein agree.  The message is one line and names the key's last
part; its wording is not pinned.

**3. A refusal is pinned by its `.key`, against an accepted control document** that differs only
in the clause under test.  Where the plan says only "refused" and leaves the place open (the card
preset's `[tasks]` table could be refused while reading or while resolving), the test accepts
either: `resolve_plan(loads_config(text))` raises `ConfigError`.

**4. `config_from_init_args(argv, *, expected_dollars=None)`.**  The keyword carries the run's
estimate in dollars, which `init` computes and this module cannot (the estimate reads the
published cards' records, and that needs the tokenizer this module must not need).  Without it the
default spend cap is $1.00, the rule's floor.  `default_spend_cap(expected_dollars)` is the rule
itself, and is public so that `init`, the plan line and the cap refusal all use one.  It returns
dollars as a float.  That `init` passes its estimate is FD5's to pin.

**5. The presets are a mapping from name to `Preset`, in `PRESET_NAMES` order**, with the fields
`name`, `label`, `endpoint`, `api_key_env`, `default_model`, `key_check_path`, and two more that
carry two rulings as data: `asks_endpoint` and `asks_price`.  `None` means the setting has no
default and must be given (with `--yes`, a flag).  `key_check_path` is the path appended to the
endpoint, with `{model}` for the model's name.  `init`'s dialogue reading these is FD5's to pin.

**6. `Plan` has at least `arms`, `seeds`, `attempts` and `decoding`.**  `arms` is a tuple of
`knobs.ArmSpec` in the order the card's own arms come in (`calibration.arm_specs()`), whatever
order the levels were written in; `seeds` is in the order declared; `decoding` is a mapping.

**7. With a preset other than `custom`, `[measure]` holds only `preset`.**  A knob, levels,
controls or strictness beside `first-look` or `card` is refused rather than ignored, as an
unknown key is.  A level listed twice in `custom` is refused, as a repeated seed is.

Not pinned here, and left to the build: comments in the written file; the wording of every
message; what a missing required key is told; `--price` without `--price-read-on`; which flags the
equivalent command leaves at their defaults (only `--yes` and `--base-url` are pinned in it); a
changed `[decoding]` under the card preset (the card's comparability check reports it, FD4); and
what `[model]` says about plain http, which is FD2's (FD2.6).
"""

from __future__ import annotations

import contextlib
import datetime
import importlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from poisson_tasks.arms import DEFAULT_GENERATOR_VERSION
from poisson_tasks.knobs import ArmSpec, arm_id

REPO = Path(__file__).resolve().parents[1]
PROGS = ("poisson-tasks", "poisson tasks")


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


def arms() -> Any:
    return importlib.import_module("poisson_tasks.arms")


def cal() -> Any:
    return importlib.import_module("poisson_tasks.calibration")


# --------------------------------------------------------------------------
# the spec's file and its keys
# --------------------------------------------------------------------------

# Spec §5.2's file with its comments removed: what `init` writes for the openai preset's defaults.
SPEC_FILE = textwrap.dedent("""\
    version = 1

    [model]
    provider = "openai"
    name = "gpt-5-nano-2025-08-07"
    base_url = "https://api.openai.com/v1"
    api_key_env = "OPENAI_API_KEY"

    [model.price]
    input = 0.05
    cached_input = 0.005
    output = 0.40
    read_on = "2026-09-25"

    [measure]
    preset = "first-look"

    [tasks]
    per_level = 10
    attempts = 1

    [decoding]
    temperature = 1.0
    top_p = 1.0
    reasoning_effort = "low"
    max_tokens = 2048

    [limits]
    spend_usd = 1.00
    max_model_calls = 32
    concurrency = 8

    [output]
    runs = "runs"
    tasks = "tasks"
""")

# Every key §5.2 names, the commented ones included, as dotted paths.
SPEC_KEYS = (
    "version",
    "model.provider", "model.name", "model.base_url", "model.api_key_env",
    "model.allow_plain_http_key",
    "model.price.input", "model.price.cached_input", "model.price.output", "model.price.read_on",
    "measure.preset", "measure.knob", "measure.levels", "measure.controls", "measure.strictness",
    "tasks.per_level", "tasks.seeds", "tasks.attempts", "tasks.generator_version",
    "decoding.temperature", "decoding.top_p", "decoding.reasoning_effort", "decoding.max_tokens",
    "limits.spend_usd", "limits.tokens", "limits.max_model_calls", "limits.concurrency",
    "output.runs", "output.tasks",
)

# Spec §6.2's flags that set a key of the file (`--fetch` and `--check-key` set none).
SPEC_FLAGS = frozenset({
    "--provider", "--model", "--base-url", "--api-key-env", "--allow-plain-http-key",
    "--price", "--price-read-on", "--no-price",
    "--measure", "--knob", "--levels", "--controls", "--no-controls", "--strictness",
    "--tasks-per-level", "--seeds", "--attempts", "--generator-version",
    "--temperature", "--top-p", "--reasoning-effort", "--max-tokens",
    "--spend-cap", "--token-cap", "--max-model-calls", "--concurrency",
    "--runs-dir", "--tasks-dir",
})


def custom(measure: str, tasks: str = "per_level = 10\nattempts = 1") -> str:
    """The spec's file with its `[measure]` and `[tasks]` tables replaced."""
    text = SPEC_FILE.replace('[measure]\npreset = "first-look"\n', f"[measure]\n{measure}\n")
    return text.replace("[tasks]\nper_level = 10\nattempts = 1\n", f"[tasks]\n{tasks}\n")


def edit(old: str, new: str, text: str = SPEC_FILE) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def flatten(data: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for key, value in data.items():
            out.update(flatten(value, f"{prefix}{key}."))
        return out
    return {prefix[:-1]: data}


def active_keys(text: str) -> list[str]:
    """The keys a TOML file sets, in the order it writes them, as dotted paths."""
    table, keys = "", []
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].strip()
        header = re.fullmatch(r"\[([A-Za-z0-9_.-]+)\]", stripped)
        if header:
            table = header.group(1) + "."
            continue
        assignment = re.match(r"([A-Za-z0-9_-]+)\s*=", stripped)
        if assignment:
            keys.append(table + assignment.group(1))
    return keys


def refused(text: str) -> Any:
    """The `ConfigError` reading `text` raises."""
    with pytest.raises(config().ConfigError) as error:
        config().loads_config(text)
    return error.value


def assert_one_line_naming(error: Any, key: str) -> None:
    message = str(error)
    assert "\n" not in message, message
    assert key.rsplit(".", 1)[-1] in message, (key, message)


@contextlib.contextmanager
def openai_base_url(value: str | None) -> Iterator[None]:
    saved = os.environ.get("OPENAI_BASE_URL")
    if value is None:
        os.environ.pop("OPENAI_BASE_URL", None)
    else:
        os.environ["OPENAI_BASE_URL"] = value
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("OPENAI_BASE_URL", None)
        else:
            os.environ["OPENAI_BASE_URL"] = saved


@pytest.fixture(autouse=True)
def _no_openai_base_url() -> Iterator[None]:
    """Every test starts with `OPENAI_BASE_URL` unset, whatever the shell running the suite has."""
    with openai_base_url(None):
        yield


def fresh(code: str, *, env: dict[str, str] | None = None) -> str:
    """Run `code` in a fresh interpreter with this one's environment, and give its stdout."""
    done = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=300,
        env={**os.environ, **(env or {})},
    )
    assert done.returncode == 0, done.stderr[-3000:]
    return done.stdout


# --------------------------------------------------------------------------
# FD1.1 and FD1.10: every config init can write, through the file and through the command
# --------------------------------------------------------------------------

PROVIDERS = ("openai", "anthropic", "ollama", "vllm", "openai-compatible")
CANDIDATES = {"depth": (1, 2, 3, 5, 8), "distractor": (0, 2, 4, 8, 14)}
PAIRS = {"depth": ((1, 8), (2, 5)), "distractor": ((0, 8), (2, 14))}
MODEL_NAMES = st.one_of(
    st.sampled_from(["gpt-5-nano-2025-08-07", "qwen3:8b", "Qwen/Qwen3-8B", "claude-haiku-4-5"]),
    st.from_regex(r"[A-Za-z][A-Za-z0-9._:/-]{0,24}", fullmatch=True),
)
URLS = st.sampled_from([
    "https://api.openai.com/v1", "http://127.0.0.1:9000/v1",
    "https://gateway.example.test/openai/v1", "http://localhost:8000/v1/",
])
KEY_VARS = st.sampled_from(["", "OPENAI_API_KEY", "MY_API_KEY", "together_api_key", "VLLM_API_KEY"])
PRICES = st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)
DATES = st.dates(min_value=datetime.date(2024, 1, 1), max_value=datetime.date(2030, 12, 31))
FOLDERS = st.from_regex(r"[a-z][a-z0-9_-]{0,12}(/[a-z][a-z0-9_-]{0,8})?", fullmatch=True)


@st.composite
def init_argv(draw: Any) -> list[str]:
    """An argv for init's settings that every preset and choice can produce: the flag space."""
    argv: list[str] = []
    if draw(st.booleans()):
        argv.append("--yes")
    provider = draw(st.sampled_from(PROVIDERS))
    argv += ["--provider", provider]
    if provider in ("anthropic", "vllm", "openai-compatible") or draw(st.booleans()):
        argv += ["--model", draw(MODEL_NAMES)]
    if provider == "openai-compatible" or draw(st.booleans()):
        argv += ["--base-url", draw(URLS)]
    if provider == "openai-compatible" or draw(st.booleans()):
        argv += ["--api-key-env", draw(KEY_VARS)]
    if draw(st.booleans()):
        argv.append("--allow-plain-http-key")
    price = draw(st.sampled_from(["default", "none", "given"]))
    if price == "none":
        argv.append("--no-price")
    elif price == "given":
        figures = [draw(PRICES) for _ in range(3)]
        argv += ["--price", ",".join(repr(f) for f in figures),
                 "--price-read-on", draw(DATES).isoformat()]

    measure = draw(st.sampled_from([None, "first-look", "card", "custom"]))
    if measure is not None:
        argv += ["--measure", measure]
    if measure == "custom":
        knob = draw(st.sampled_from(["depth", "distractor"]))
        if knob == "distractor" or draw(st.booleans()):
            argv += ["--knob", knob]
        chosen: tuple[int, ...] = CANDIDATES[knob]
        if draw(st.booleans()):
            chosen = tuple(draw(st.lists(st.sampled_from(CANDIDATES[knob]), min_size=1,
                                         unique=True)))
            argv += ["--levels", ",".join(str(level) for level in chosen)]
        if any(low in chosen and high in chosen for low, high in PAIRS[knob]) and draw(st.booleans()):
            argv.append("--controls")
        elif draw(st.booleans()):
            argv.append("--no-controls")
        if draw(st.booleans()):
            argv += ["--strictness", draw(st.sampled_from(["strict", "leaky"]))]
    if measure != "card":
        tasks = draw(st.sampled_from([None, "per_level", "seeds"]))
        if tasks == "per_level":
            argv += ["--tasks-per-level", str(draw(st.integers(1, 60)))]
        elif tasks == "seeds":
            seeds = draw(st.lists(st.integers(0, 2**32 - 1), min_size=1, max_size=6, unique=True))
            argv += ["--seeds", ",".join(str(seed) for seed in seeds)]
        if draw(st.booleans()):
            argv += ["--attempts", str(draw(st.integers(1, 10)))]
        if draw(st.booleans()):
            argv += ["--generator-version", draw(st.sampled_from(["0", "tg-m3-v1", "1"]))]
        if draw(st.booleans()):
            argv += ["--temperature", repr(draw(st.floats(0.05, 2.0)))]
        if draw(st.booleans()):
            argv += ["--top-p", draw(st.one_of(st.just("not sent"),
                                                st.floats(0.01, 1.0).map(repr)))]
        if draw(st.booleans()):
            argv += ["--reasoning-effort",
                     draw(st.sampled_from(["minimal", "low", "medium", "high", "not sent"]))]
        if draw(st.booleans()):
            argv += ["--max-tokens", draw(st.one_of(st.just("not sent"),
                                                     st.integers(1, 65536).map(str)))]
    if price == "given" and draw(st.booleans()):
        argv += ["--spend-cap", repr(draw(st.floats(0.01, 1000)))]
    if draw(st.booleans()):
        argv += ["--token-cap", str(draw(st.integers(1, 10**9)))]
    if draw(st.booleans()):
        argv += ["--max-model-calls", str(draw(st.integers(1, 128)))]
    if draw(st.booleans()):
        argv += ["--concurrency", str(draw(st.integers(1, 256)))]
    if draw(st.booleans()):
        argv += ["--runs-dir", draw(FOLDERS)]
    if draw(st.booleans()):
        argv += ["--tasks-dir", draw(FOLDERS)]
    return argv


ESTIMATES = st.one_of(st.none(), st.floats(min_value=0, max_value=100))
FLAG_SPACE = settings(max_examples=300, deadline=None, derandomize=True,
                      suppress_health_check=[HealthCheck.too_slow])
BASE_URLS = (None, "https://proxy.example.test/v1")


@FLAG_SPACE
@given(argv=init_argv(), expected=ESTIMATES)
def test_fd1_1_every_config_init_can_write_reads_back_equal(argv: list[str], expected: Any) -> None:
    for base_url in BASE_URLS:
        with openai_base_url(base_url):
            made = config().config_from_init_args(argv, expected_dollars=expected)
            assert config().loads_config(config().dump_config(made)) == made


@FLAG_SPACE
@given(argv=init_argv(), expected=ESTIMATES)
def test_fd1_10_the_equivalent_command_writes_the_same_file(argv: list[str], expected: Any) -> None:
    """Under both progs, and with `OPENAI_BASE_URL` set and unset both where the config was made
    and where the command is run: the command always carries `--base-url`, so where it runs
    cannot move the endpoint."""
    for made_under in BASE_URLS:
        with openai_base_url(made_under):
            made = config().config_from_init_args(argv, expected_dollars=expected)
        written = config().dump_config(made)
        for prog in PROGS:
            command = config().equivalent_init_command(made, prog=prog)
            words = shlex.split(prog)
            assert isinstance(command, list) and all(isinstance(word, str) for word in command)
            assert command[:len(words) + 1] == [*words, "init"], command
            assert "--yes" in command and "--base-url" in command, command
            for run_under in BASE_URLS:
                with openai_base_url(run_under):
                    again = config().config_from_init_args(command[len(words) + 1:])
                assert config().dump_config(again) == written, (prog, run_under, command)


def test_fd1_1_every_key_of_the_file_is_reachable_from_a_flag() -> None:
    """Each key of §5.2 (but `version`, which is the schema's) moved by its own flag, against the
    defaults."""
    price = ["--price", "0.1,0.01,0.8", "--price-read-on", "2026-10-01"]
    custom_levels = ["--measure", "custom", "--levels", "2,5"]
    reach = {
        "model.provider": (["--provider", "ollama"], "ollama"),
        "model.name": (["--model", "gpt-4o-mini"], "gpt-4o-mini"),
        "model.base_url": (["--base-url", "https://proxy.example.test/v1"],
                           "https://proxy.example.test/v1"),
        "model.api_key_env": (["--api-key-env", "WORK_API_KEY"], "WORK_API_KEY"),
        "model.allow_plain_http_key": (["--allow-plain-http-key"], True),
        "model.price.input": (price, 0.1),
        "model.price.cached_input": (price, 0.01),
        "model.price.output": (price, 0.8),
        "model.price.read_on": (price, "2026-10-01"),
        "measure.preset": (["--measure", "card"], "card"),
        "measure.knob": (["--measure", "custom", "--knob", "distractor"], "distractor"),
        "measure.levels": (custom_levels, [2, 5]),
        "measure.controls": ([*custom_levels, "--controls"], True),
        "measure.strictness": (["--measure", "custom", "--strictness", "leaky"], "leaky"),
        "tasks.per_level": (["--tasks-per-level", "25"], 25),
        "tasks.seeds": (["--seeds", "404,55,2121"], [404, 55, 2121]),
        "tasks.attempts": (["--attempts", "3"], 3),
        "tasks.generator_version": (["--generator-version", "tg-m3-v1"], "tg-m3-v1"),
        "decoding.temperature": (["--temperature", "0.7"], 0.7),
        "decoding.top_p": (["--top-p", "not sent"], "not sent"),
        "decoding.reasoning_effort": (["--reasoning-effort", "medium"], "medium"),
        "decoding.max_tokens": (["--max-tokens", "4096"], 4096),
        "limits.spend_usd": (["--spend-cap", "3.5"], 3.5),
        "limits.tokens": (["--token-cap", "500000"], 500000),
        "limits.max_model_calls": (["--max-model-calls", "16"], 16),
        "limits.concurrency": (["--concurrency", "2"], 2),
        "output.runs": (["--runs-dir", "measurements"], "measurements"),
        "output.tasks": (["--tasks-dir", "generated"], "generated"),
    }
    assert set(reach) == set(SPEC_KEYS) - {"version"}
    default = flatten(tomllib.loads(config().dump_config(config().config_from_init_args([]))))
    for key, (argv, value) in reach.items():
        written = flatten(tomllib.loads(config().dump_config(config().config_from_init_args(argv))))
        assert written.get(key) == value, (key, argv, written.get(key))
        assert default.get(key) != value, (key, "the default already says it, so this proves nothing")


def test_fd1_1_the_flag_table_covers_every_key_with_the_spec_flags() -> None:
    """`INIT_FLAGS` is §6.2 as data: each entry names a flag of §6.2 and a key of §5.2 (or the
    table it sets whole, as `--price` does), and between them they reach every key."""
    flags = config().INIT_FLAGS
    names = {flag.flag for flag in flags}
    assert names <= SPEC_FLAGS, sorted(names - SPEC_FLAGS)
    assert {"--provider", "--model", "--base-url", "--api-key-env", "--price", "--measure",
            "--levels", "--seeds", "--spend-cap", "--token-cap", "--top-p",
            "--generator-version", "--runs-dir"} <= names
    keys = {flag.key for flag in flags}
    for key in keys:
        assert any(spec == key or spec.startswith(key + ".") for spec in SPEC_KEYS), key
    for spec in set(SPEC_KEYS) - {"version"}:
        assert any(spec == key or spec.startswith(key + ".") for key in keys), spec


def test_fd1_1_the_written_file_is_the_same_bytes_in_every_process() -> None:
    code = textwrap.dedent("""\
        from poisson_tasks.config import config_from_init_args, dump_config
        for argv in ([], ["--measure", "custom", "--knob", "distractor", "--controls",
                          "--strictness", "leaky", "--seeds", "9,404,55", "--top-p", "not sent"],
                     ["--provider", "vllm", "--model", "Qwen/Qwen3-8B", "--token-cap", "1000"]):
            print(dump_config(config_from_init_args(argv)), end="\\x00")
    """)
    first = fresh(code, env={"PYTHONHASHSEED": "0"})
    second = fresh(code, env={"PYTHONHASHSEED": "4242"})
    assert first == second and first.count("\x00") == 3


# --------------------------------------------------------------------------
# FD1.2: the written file
# --------------------------------------------------------------------------


def test_fd1_2_init_defaults_write_the_spec_file() -> None:
    """Keys, order, values and their TOML types; comments are not pinned."""
    for argv in ([], ["--yes"]):
        written = config().dump_config(config().config_from_init_args(argv))
        assert active_keys(written) == active_keys(SPEC_FILE), active_keys(written)
        ours, spec = flatten(tomllib.loads(written)), flatten(tomllib.loads(SPEC_FILE))
        assert {key: (type(value), value) for key, value in ours.items()} == {
            key: (type(value), value) for key, value in spec.items()}


def test_fd1_2_the_spec_file_reads_as_init_defaults() -> None:
    assert config().loads_config(SPEC_FILE) == config().config_from_init_args([])


# --------------------------------------------------------------------------
# FD1.3: unknown keys and tables
# --------------------------------------------------------------------------

LEVELS_DOC = 'preset = "custom"\nknob = "depth"\nlevels = [1, 3]'

UNKNOWN = [
    # (the file with the misspelling, its control, the key, the suggestion)
    pytest.param(edit("version = 1", "verison = 1"), None, "verison", "version", id="top-level"),
    pytest.param(edit("[measure]", "[mesure]"), SPEC_FILE, "mesure", "measure", id="table"),
    pytest.param(edit("[model.price]", "[model.prise]"), SPEC_FILE, "model.prise", "model.price",
                 id="sub-table"),
    pytest.param(custom(LEVELS_DOC.replace("levels", "levles")), custom(LEVELS_DOC),
                 "measure.levles", "measure.levels", id="spec-example"),
    pytest.param(edit("per_level = 10", "per_lvl = 10"), SPEC_FILE, "tasks.per_lvl",
                 "tasks.per_level", id="two-edits"),
    pytest.param(edit("cached_input = 0.005", "cachedinput = 0.005"), SPEC_FILE,
                 "model.price.cachedinput", "model.price.cached_input", id="one-edit"),
    pytest.param(edit("concurrency = 8", "concurrency = 8\ntokns = 5000"),
                 edit("concurrency = 8", "concurrency = 8\ntokens = 5000"),
                 "limits.tokns", "limits.tokens", id="a-key-left-out"),
    pytest.param(edit("attempts = 1", "attempts = 1\nattemptsabc = 2"), SPEC_FILE,
                 "tasks.attemptsabc", None, id="three-edits"),
    pytest.param(edit("[output]", "[telemetry]\nendpoint = \"x\"\n\n[output]"), SPEC_FILE,
                 "telemetry", None, id="far-table"),
    pytest.param(edit("max_tokens = 2048", "max_tokens = 2048\nseed = 3"), SPEC_FILE,
                 "decoding.seed", None, id="far-key"),
]


@pytest.mark.parametrize(("text", "control", "key", "suggestion"), UNKNOWN)
def test_fd1_3_an_unknown_key_names_its_path_and_the_nearest_key(
    text: str, control: str | None, key: str, suggestion: str | None
) -> None:
    error = refused(text)
    assert (error.key, error.suggestion) == (key, suggestion), (error.key, error.suggestion)
    assert_one_line_naming(error, key)
    if suggestion is not None:
        assert suggestion.rsplit(".", 1)[-1] in str(error), str(error)
    config().loads_config(control if control is not None else SPEC_FILE)


# --------------------------------------------------------------------------
# FD1.4: bad values
# --------------------------------------------------------------------------

BAD_VALUES = [
    # (the file with the bad value, its control, the key, the suggestion)
    pytest.param(edit("attempts = 1", 'attempts = "1"'), SPEC_FILE, "tasks.attempts", None,
                 id="text-for-a-number"),
    pytest.param(edit("attempts = 1", "attempts = true"), SPEC_FILE, "tasks.attempts", None,
                 id="a-boolean-for-a-number"),
    pytest.param(edit("per_level = 10", "per_level = 10.0"), SPEC_FILE, "tasks.per_level", None,
                 id="a-fraction-for-a-count"),
    pytest.param(edit("temperature = 1.0", 'temperature = "hot"'), SPEC_FILE,
                 "decoding.temperature", None, id="text-for-temperature"),
    pytest.param(edit("concurrency = 8", "concurrency = [8]"), SPEC_FILE, "limits.concurrency",
                 None, id="a-list-for-a-number"),
    pytest.param(edit("version = 1\n", 'version = 1\noutput = "runs"\n',
                      edit('\n[output]\nruns = "runs"\ntasks = "tasks"\n', "")),
                 SPEC_FILE, "output", None, id="a-value-for-a-table"),
    pytest.param(edit("top_p = 1.0", "top_p = 1.5"), edit("top_p = 1.0", "top_p = 0.95"),
                 "decoding.top_p", None, id="top-p-above-one"),
    pytest.param(edit("max_tokens = 2048", "max_tokens = 0"),
                 edit("max_tokens = 2048", "max_tokens = 1"), "decoding.max_tokens", None,
                 id="no-tokens"),
    pytest.param(edit("temperature = 1.0", "temperature = 0.0"),
                 edit("temperature = 1.0", "temperature = 0.01"), "decoding.temperature", None,
                 id="deterministic"),
    pytest.param(edit("spend_usd = 1.00", "spend_usd = 0.0"),
                 edit("spend_usd = 1.00", "spend_usd = 0.01"), "limits.spend_usd", None,
                 id="a-zero-cap"),
    pytest.param(edit("input = 0.05", "input = -0.05"), edit("input = 0.05", "input = 0.0"),
                 "model.price.input", None, id="a-negative-price"),
    pytest.param(edit('read_on = "2026-09-25"', 'read_on = "2026-13-01"'), SPEC_FILE,
                 "model.price.read_on", None, id="not-a-date"),
    pytest.param(edit('base_url = "https://api.openai.com/v1"', 'base_url = "api.openai.com/v1"'),
                 SPEC_FILE, "model.base_url", None, id="no-scheme"),
    pytest.param(edit('provider = "openai"', 'provider = "openia"'), SPEC_FILE,
                 "model.provider", "openai", id="provider-typo"),
    pytest.param(edit('provider = "openai"', 'provider = "bedrock"'), SPEC_FILE,
                 "model.provider", None, id="provider-not-offered"),
    pytest.param(edit('preset = "first-look"', 'preset = "frist-look"'), SPEC_FILE,
                 "measure.preset", "first-look", id="measure-typo"),
    pytest.param(custom('preset = "custom"\nknob = "dpeth"'), custom('preset = "custom"\nknob = "depth"'),
                 "measure.knob", "depth", id="knob-typo"),
    pytest.param(custom('preset = "custom"\nstrictness = "leakey"'),
                 custom('preset = "custom"\nstrictness = "leaky"'),
                 "measure.strictness", "leaky", id="strictness-typo"),
    pytest.param(custom('preset = "custom"\nstrictness = "loose"'),
                 custom('preset = "custom"\nstrictness = "strict"'),
                 "measure.strictness", None, id="strictness-not-offered"),
]


@pytest.mark.parametrize(("text", "control", "key", "suggestion"), BAD_VALUES)
def test_fd1_4_a_bad_value_names_its_key(
    text: str, control: str, key: str, suggestion: str | None
) -> None:
    error = refused(text)
    assert error.key == key, error.key
    assert error.suggestion == suggestion, error.suggestion
    assert_one_line_naming(error, key)
    config().loads_config(control)


@pytest.mark.parametrize("broken", ['name = "gpt-5-nano-2025-08-07', "attempts = "])
def test_fd1_4_a_file_that_is_not_toml_gives_the_line_tomllib_reports(broken: str) -> None:
    whole = {'name = "gpt-5-nano-2025-08-07': 'name = "gpt-5-nano-2025-08-07"',
             "attempts = ": "attempts = 1"}[broken]
    text = edit(whole, broken)
    line = text.splitlines().index(broken) + 1
    error = refused(text)
    assert error.line == line, (error.line, line)
    assert "\n" not in str(error)


# --------------------------------------------------------------------------
# FD1.5: the refusals, each with its control
# --------------------------------------------------------------------------

NO_PRICE = edit(
    '[model.price]\ninput = 0.05\ncached_input = 0.005\noutput = 0.40\nread_on = "2026-09-25"\n\n',
    "",
)

REFUSALS = [
    pytest.param(edit("per_level = 10", "per_level = 0"), edit("per_level = 10", "per_level = 1"),
                 "tasks.per_level", id="per-level-0"),
    pytest.param(edit("per_level = 10", "per_level = 61"), edit("per_level = 10", "per_level = 60"),
                 "tasks.per_level", id="per-level-61"),
    pytest.param(edit("per_level = 10", "seeds = []"), edit("per_level = 10", "seeds = [404]"),
                 "tasks.seeds", id="no-seeds"),
    pytest.param(edit("per_level = 10", "seeds = [404, 55, 404]"),
                 edit("per_level = 10", "seeds = [404, 55]"), "tasks.seeds", id="repeated-seed"),
    pytest.param(edit("attempts = 1", "attempts = 0"), SPEC_FILE, "tasks.attempts",
                 id="no-attempts"),
    pytest.param(edit("max_model_calls = 32", "max_model_calls = 0"),
                 edit("max_model_calls = 32", "max_model_calls = 1"), "limits.max_model_calls",
                 id="no-model-calls"),
    pytest.param(edit("concurrency = 8", "concurrency = 0"),
                 edit("concurrency = 8", "concurrency = 1"), "limits.concurrency",
                 id="no-concurrency"),
    pytest.param(custom('preset = "custom"\nknob = "depth"\nlevels = [1, 4]'),
                 custom('preset = "custom"\nknob = "depth"\nlevels = [1, 5]'),
                 "measure.levels", id="depth-4"),
    pytest.param(custom('preset = "custom"\nknob = "distractor"\nlevels = [1]'),
                 custom('preset = "custom"\nknob = "distractor"\nlevels = [0]'),
                 "measure.levels", id="distractor-1"),
    pytest.param(custom('preset = "custom"\nknob = "depth"\nlevels = []'),
                 custom('preset = "custom"\nknob = "depth"\nlevels = [3]'),
                 "measure.levels", id="no-levels"),
    pytest.param(custom('preset = "custom"\nknob = "depth"\nlevels = [3, 1, 3]'),
                 custom('preset = "custom"\nknob = "depth"\nlevels = [3, 1]'),
                 "measure.levels", id="a-level-twice"),
    pytest.param(custom('preset = "custom"\nlevels = [1, 3]\ncontrols = true'),
                 custom('preset = "custom"\nlevels = [1, 8]\ncontrols = true'),
                 "measure.controls", id="controls-with-one-end-of-a-pair"),
    pytest.param(custom('preset = "custom"\nlevels = [2, 8]\ncontrols = true'),
                 custom('preset = "custom"\nlevels = [2, 5, 8]\ncontrols = true'),
                 "measure.controls", id="controls-with-crossed-ends"),
    pytest.param(edit("temperature = 1.0", 'temperature = "not sent"'),
                 edit("top_p = 1.0", 'top_p = "not sent"'), "decoding.temperature",
                 id="temperature-not-sent"),
    pytest.param(edit('api_key_env = "OPENAI_API_KEY"', 'api_key_env = "OPENAI_KEY"'),
                 edit('api_key_env = "OPENAI_API_KEY"', 'api_key_env = "work_api_key"'),
                 "model.api_key_env", id="a-key-variable-the-harness-would-see"),
    pytest.param(edit("version = 1", "version = 2"), SPEC_FILE, "version", id="a-newer-file"),
    pytest.param(custom('preset = "first-look"\nstrictness = "leaky"'), SPEC_FILE,
                 "measure.strictness", id="strictness-outside-custom"),
    pytest.param(custom('preset = "card"\nlevels = [1, 3]', tasks="attempts = 5"),
                 custom('preset = "card"', tasks="attempts = 5"), "measure.levels",
                 id="levels-outside-custom"),
]


@pytest.mark.parametrize(("text", "control", "key"), REFUSALS)
def test_fd1_5_a_refusal_names_its_key_and_its_control_is_accepted(
    text: str, control: str, key: str
) -> None:
    error = refused(text)
    assert error.key == key, error.key
    assert_one_line_naming(error, key)
    config().loads_config(control)


def test_fd1_5_a_plan_with_no_finite_limit_is_refused() -> None:
    """Neither cap; and, with no price, a dollar cap, which cannot be measured.  The controls: a
    token cap on each."""
    no_caps = edit("spend_usd = 1.00\n", "")
    dollars_without_a_price = NO_PRICE
    for text, control in ((no_caps, edit("spend_usd = 1.00", "tokens = 2000000")),
                          (dollars_without_a_price,
                           edit("spend_usd = 1.00", "tokens = 2000000", NO_PRICE))):
        error = refused(text)
        assert error.key is not None and error.key.startswith("limits"), error.key
        assert "\n" not in str(error)
        config().loads_config(control)


def test_fd1_5_an_empty_key_variable_means_no_key_and_is_accepted() -> None:
    accepted = config().loads_config(
        edit('api_key_env = "OPENAI_API_KEY"', 'api_key_env = ""'))
    assert accepted.model.api_key_env == ""


def test_fd1_5_the_flags_are_refused_where_the_file_is() -> None:
    """One validation: a refused value given as a flag names the same key."""
    cases = [
        (["--tasks-per-level", "0"], "tasks.per_level"),
        (["--seeds", "404,55,404"], "tasks.seeds"),
        (["--attempts", "0"], "tasks.attempts"),
        (["--concurrency", "0"], "limits.concurrency"),
        (["--measure", "custom", "--levels", "1,4"], "measure.levels"),
        (["--measure", "custom", "--levels", "1,3", "--controls"], "measure.controls"),
        (["--measure", "custom", "--strictness", "leakey"], "measure.strictness"),
        (["--temperature", "not sent"], "decoding.temperature"),
        (["--api-key-env", "OPENAI_KEY"], "model.api_key_env"),
        (["--no-price", "--spend-cap", "2"], "limits.spend_usd"),
        (["--provider", "openai-compatible", "--model", "m", "--api-key-env", ""],
         "model.base_url"),
    ]
    for argv, key in cases:
        with pytest.raises(config().ConfigError) as error:
            config().config_from_init_args(argv)
        assert error.value.key == key, (argv, error.value.key)


# --------------------------------------------------------------------------
# FD1.6 and FD1.7: what each preset resolves to
# --------------------------------------------------------------------------

CARD = custom('preset = "card"', tasks="")


def plan_of(text: str) -> Any:
    return config().resolve_plan(config().loads_config(text))


def test_fd1_6_the_card_preset_is_the_published_design() -> None:
    for text in (CARD, custom('preset = "card"', tasks="per_level = 60\nattempts = 5"),
                 config().dump_config(config().config_from_init_args(["--measure", "card"]))):
        plan = plan_of(text)
        assert tuple(plan.arms) == cal().arm_specs()
        assert tuple(plan.seeds) == cal().seed_list()
        assert plan.attempts == cal().N
        assert dict(plan.decoding) == cal().DECODING


@pytest.mark.parametrize("tasks", [
    "per_level = 10", "attempts = 1", "per_level = 60\nattempts = 1", "seeds = [404]",
    'generator_version = "tg-m3-v1"',
])
def test_fd1_6_a_card_preset_tasks_table_that_says_anything_else_is_refused(tasks: str) -> None:
    with pytest.raises(config().ConfigError):
        plan_of(custom('preset = "card"', tasks=tasks))
    plan_of(custom('preset = "card"', tasks='per_level = 60\nattempts = 5\n'
                   f'generator_version = "{DEFAULT_GENERATOR_VERSION}"'))


def plain(level: int, *, knob: str = "depth", strictness: str = "strict",
          generator_version: str = DEFAULT_GENERATOR_VERSION) -> ArmSpec:
    return ArmSpec(knob=knob, level=level, control=None, strictness=strictness, split="eval",
                   generator_version=generator_version)


def test_fd1_7_the_first_look_is_depth_1_3_8_on_the_first_seeds_of_the_cards() -> None:
    seeds = cal().seed_list()
    for per_level in (1, 10, 60):
        plan = plan_of(edit("per_level = 10", f"per_level = {per_level}"))
        assert tuple(plan.arms) == (plain(1), plain(3), plain(8))
        assert tuple(plan.seeds) == seeds[:per_level]
        assert plan.attempts == 1
    assert plan_of(edit("attempts = 1", "attempts = 3")).attempts == 3


def card_arms_chosen(knob: str, chosen: set[int], controls: bool) -> list[ArmSpec]:
    """The card's own arms of `knob`, in the card's order, whose levels are all chosen: a plain
    arm at a chosen level, and a control arm whose two levels are both chosen."""
    out = []
    for spec in cal().arm_specs():
        if spec.knob != knob or spec.level not in chosen:
            continue
        if spec.control is not None and not (controls and spec.control in chosen):
            continue
        out.append(spec)
    return out


@pytest.mark.parametrize(("knob", "levels", "controls"), [
    ("depth", [8, 1, 3], False),
    ("depth", [1, 2, 5, 8], True),
    ("depth", [1, 5, 8], True),
    ("depth", [1, 2, 8], True),
    ("distractor", [0, 2, 8], True),
    ("distractor", [14, 2, 0, 8], True),
    ("distractor", [4], False),
])
@pytest.mark.parametrize("strictness", ["strict", "leaky"])
def test_fd1_7_custom_resolves_the_levels_the_control_pairs_and_the_strictness(
    knob: str, levels: list[int], controls: bool, strictness: str
) -> None:
    measure = (f'preset = "custom"\nknob = "{knob}"\nlevels = {levels}\n'
               f"controls = {'true' if controls else 'false'}\nstrictness = \"{strictness}\"")
    plan = plan_of(custom(measure))
    expected = [arms().arm_from_id(arm_id(spec), strictness=strictness)
                for spec in card_arms_chosen(knob, set(levels), controls)]
    assert list(plan.arms) == expected
    assert all(spec.strictness == strictness for spec in plan.arms)
    assert any(spec.control is not None for spec in plan.arms) == controls


def test_fd1_7_custom_defaults_to_every_level_of_depth_with_no_controls_strict() -> None:
    plan = plan_of(custom('preset = "custom"'))
    assert list(plan.arms) == [plain(level) for level in (1, 2, 3, 5, 8)]


def test_fd1_7_declared_seeds_and_a_generator_version_reach_every_arm() -> None:
    plan = plan_of(custom('preset = "custom"\nlevels = [3, 1]',
                          tasks='seeds = [2121, 404, 55]\nattempts = 2\ngenerator_version = "tg-m3-v1"'))
    assert tuple(plan.seeds) == (2121, 404, 55)
    assert plan.attempts == 2
    assert list(plan.arms) == [plain(1, generator_version="tg-m3-v1"),
                               plain(3, generator_version="tg-m3-v1")]


# --------------------------------------------------------------------------
# FD1.9: the plan's identity
# --------------------------------------------------------------------------

HASH_BASE = custom('preset = "custom"\nlevels = [1, 3]', tasks="per_level = 10\nattempts = 1")

CHANGES_THE_RUN = {
    "the arms": edit("levels = [1, 3]", "levels = [1, 3, 8]", HASH_BASE),
    "the strictness": edit("levels = [1, 3]", 'levels = [1, 3]\nstrictness = "leaky"', HASH_BASE),
    "the seeds": edit("per_level = 10", "per_level = 11", HASH_BASE),
    "the attempts": edit("attempts = 1", "attempts = 2", HASH_BASE),
    "the model": edit('name = "gpt-5-nano-2025-08-07"', 'name = "gpt-5-mini-2025-08-07"', HASH_BASE),
    "the endpoint": edit('base_url = "https://api.openai.com/v1"',
                         'base_url = "https://proxy.example.test/v1"', HASH_BASE),
    "the temperature": edit("temperature = 1.0", "temperature = 0.9", HASH_BASE),
    "top_p not sent": edit("top_p = 1.0", 'top_p = "not sent"', HASH_BASE),
    "the reasoning effort": edit('reasoning_effort = "low"', 'reasoning_effort = "medium"', HASH_BASE),
    "the token limit": edit("max_tokens = 2048", "max_tokens = 1024", HASH_BASE),
    "the turn cap": edit("max_model_calls = 32", "max_model_calls = 16", HASH_BASE),
    "the generator version": edit("attempts = 1", 'attempts = 1\ngenerator_version = "tg-m3-v1"',
                                  HASH_BASE),
}

LEAVES_THE_RUN = {
    "the spend cap": edit("spend_usd = 1.00", "spend_usd = 2.00", HASH_BASE),
    "a token cap added": edit("spend_usd = 1.00", "spend_usd = 1.00\ntokens = 500000", HASH_BASE),
    "the concurrency": edit("concurrency = 8", "concurrency = 2", HASH_BASE),
    "the prices": edit("output = 0.40", "output = 0.45", HASH_BASE),
    "the date they were read": edit('read_on = "2026-09-25"', 'read_on = "2026-10-02"', HASH_BASE),
    "no price at all": edit("spend_usd = 1.00", "tokens = 2000000",
                            custom('preset = "custom"\nlevels = [1, 3]',
                                   tasks="per_level = 10\nattempts = 1").replace(
                                '[model.price]\ninput = 0.05\ncached_input = 0.005\noutput = 0.40\n'
                                'read_on = "2026-09-25"\n\n', "")),
    "the runs folder": edit('runs = "runs"', 'runs = "elsewhere"', HASH_BASE),
    "the tasks folder": edit('tasks = "tasks"', 'tasks = "generated"', HASH_BASE),
}


def hash_of(text: str) -> str:
    digest = config().plan_hash(plan_of(text))
    assert isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{12,}", digest), digest
    return str(digest)


@pytest.mark.parametrize("what", sorted(CHANGES_THE_RUN))
def test_fd1_9_the_plan_hash_moves_with_what_runs(what: str) -> None:
    assert hash_of(CHANGES_THE_RUN[what]) != hash_of(HASH_BASE)


@pytest.mark.parametrize("what", sorted(LEAVES_THE_RUN))
def test_fd1_9_the_plan_hash_stays_with_what_does_not_run(what: str) -> None:
    assert hash_of(LEAVES_THE_RUN[what]) == hash_of(HASH_BASE)


def test_fd1_9_declared_seeds_run_in_their_order_so_the_order_is_part_of_the_plan() -> None:
    forward = edit("per_level = 10", "seeds = [404, 55]", HASH_BASE)
    backward = edit("per_level = 10", "seeds = [55, 404]", HASH_BASE)
    assert hash_of(forward) != hash_of(backward)


def test_fd1_9_the_plan_hash_is_the_same_in_every_process() -> None:
    code = textwrap.dedent(f"""\
        from poisson_tasks.config import loads_config, plan_hash, resolve_plan
        for text in ({HASH_BASE!r}, {CARD!r}):
            print(plan_hash(resolve_plan(loads_config(text))))
    """)
    first = fresh(code, env={"PYTHONHASHSEED": "0"})
    second = fresh(code, env={"PYTHONHASHSEED": "4242"})
    assert first == second and len(set(first.split())) == 2
    assert first.split()[0] == hash_of(HASH_BASE)


# --------------------------------------------------------------------------
# FD1.12: pure, and the tokenizer first
# --------------------------------------------------------------------------

GENERATOR_MODULES = ("verifiers", "poisson_tasks.tasks", "poisson_tasks.calibration",
                     "poisson_tasks.export")


def test_fd1_12_importing_config_and_arms_loads_neither_verifiers_nor_the_generator() -> None:
    out = fresh(
        "import sys, poisson_tasks.config, poisson_tasks.arms\n"
        f"print(sorted(m for m in {GENERATOR_MODULES!r} if m in sys.modules))\n"
    )
    assert out.strip() == "[]", out


AUDIT = textwrap.dedent("""\
    import os, sys
    events = []
    WRITE = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

    def hook(event, args):
        if event == "open":
            mode, flags = args[1], args[2]
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                    isinstance(flags, int) and flags & WRITE):
                events.append(("open for writing", str(args[0])))
        elif event.startswith("socket.") and event != "socket.__new__":
            events.append((event, repr(args)[:120]))
        elif event in ("os.mkdir", "os.rename", "os.remove", "os.unlink", "shutil.rmtree"):
            events.append((event, repr(args)[:120]))

    sys.addaudithook(hook)
""")


def test_fd1_12_reading_resolving_and_dumping_open_no_socket_and_write_no_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "tasks.toml"
    path.write_text(SPEC_FILE, encoding="utf-8")
    code = AUDIT + textwrap.dedent(f"""\
        from poisson_tasks import config
        made = config.load_config({str(path)!r})
        text = config.dump_config(made)
        again = config.loads_config(text)
        flagged = config.config_from_init_args(["--measure", "custom", "--controls"])
        command = config.equivalent_init_command(flagged, prog="poisson-tasks")
        for one in (made, flagged, config.loads_config({CARD!r})):
            config.plan_hash(config.resolve_plan(one))
        print(events)
    """)
    out = fresh(code, env={"PYTHONDONTWRITEBYTECODE": "1"})
    assert out.strip() == "[]", out


def package_without_tokenizer(tmp_path: Path) -> Path:
    """A copy of the package under test with the tokenizer file left out, importable first."""
    source = Path(importlib.import_module("poisson_tasks").__file__).resolve().parent
    root = tmp_path / "site"
    shutil.copytree(source, root / "poisson_tasks",
                    ignore=shutil.ignore_patterns("*.tiktoken", "__pycache__"))
    assert not list((root / "poisson_tasks").rglob("*.tiktoken"))
    return root


def test_fd1_12_without_the_tokenizer_reading_works_and_resolving_refuses_first(
    tmp_path: Path,
) -> None:
    root = package_without_tokenizer(tmp_path)
    code = textwrap.dedent(f"""\
        import sys
        import poisson_tasks
        assert poisson_tasks.__file__.startswith({str(root)!r}), poisson_tasks.__file__
        from poisson_tasks import config
        made = config.loads_config({SPEC_FILE!r})
        config.dump_config(config.config_from_init_args([]))
        try:
            config.resolve_plan(made)
        except config.TokenizerMissing:
            print("refused")
        print(sorted(m for m in {GENERATOR_MODULES!r} if m in sys.modules))
    """)
    out = fresh(code, env={"PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"})
    assert out.split("\n")[:2] == ["refused", "[]"], out


def test_fd1_12_the_tokenizer_check_is_the_control() -> None:
    """With the tokenizer present the same plan resolves: the refusal above is the file's."""
    assert plan_of(SPEC_FILE).arms


# --------------------------------------------------------------------------
# the design's literals, held equal to their source
# --------------------------------------------------------------------------


def test_fd1_6_init_defaults_carry_the_published_decoding_and_the_cards_price() -> None:
    """`config` may not import `calibration`, so it carries its own copy of the declared decoding
    and of model A's name and rates; this holds each equal to the published card's."""
    made = config().config_from_init_args([])
    assert dict(plan_of(config().dump_config(made)).decoding) == cal().DECODING
    assert made.model.name == cal().MODEL_A
    artifact = json.loads(
        (REPO / "calibration" / cal().MODEL_A / "artifact.json").read_text(encoding="utf-8"))
    (card,) = artifact["provenance"]["models"]
    assert card["id"] == made.model.name
    assert made.model.price is not None
    assert (made.model.price.input, made.model.price.cached_input, made.model.price.output,
            made.model.price.read_on) == (card["input_rate"], card["cached_input_rate"],
                                          card["output_rate"],
                                          artifact["provenance"]["rate_read_date"])


# --------------------------------------------------------------------------
# FD1.15, FD1.16 and rulings 3 and 4: the presets
# --------------------------------------------------------------------------

SPEC_PRESETS = {
    # name: (endpoint, key variable, default model, key-check path)
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-5-nano-2025-08-07",
               "/models/{model}"),
    "anthropic": ("https://api.anthropic.com/v1/", "ANTHROPIC_API_KEY", None, "/models/{model}"),
    "ollama": ("http://127.0.0.1:11434/v1", "", "qwen3:8b", "/models"),
    "vllm": ("http://127.0.0.1:8000/v1", "", None, "/models"),
    "openai-compatible": (None, None, None, "/models"),
}


def test_fd1_15_the_presets_are_the_spec_table() -> None:
    """Anthropic has no default model until its live check (ruled), vLLM's is whatever the server
    lists, and the openai-compatible endpoint is asked for every time."""
    assert config().PRESET_NAMES == PROVIDERS
    assert tuple(config().PRESETS) == PROVIDERS
    labels = set()
    for name, (endpoint, key_env, model, path) in SPEC_PRESETS.items():
        preset = config().PRESETS[name]
        assert preset.name == name
        assert (preset.endpoint, preset.api_key_env, preset.default_model,
                preset.key_check_path) == (endpoint, key_env, model, path), name
        assert isinstance(preset.label, str) and preset.label
        labels.add(preset.label)
    assert len(labels) == len(PROVIDERS)
    assert config().SCHEMA_VERSION == 1


def test_ruling_3_init_asks_for_an_endpoint_only_for_vllm_and_another_endpoint() -> None:
    asks = {name for name in PROVIDERS if config().PRESETS[name].asks_endpoint}
    assert asks == {"vllm", "openai-compatible"}


def test_ruling_4_init_asks_no_price_for_ollama_or_vllm() -> None:
    asks = {name for name in PROVIDERS if config().PRESETS[name].asks_price}
    assert asks == {"openai", "anthropic", "openai-compatible"}


@pytest.mark.parametrize(("argv", "model"), [
    (["--provider", "ollama"], "qwen3:8b"),
    (["--provider", "vllm", "--model", "Qwen/Qwen3-8B"], "Qwen/Qwen3-8B"),
    (["--provider", "ollama", "--model", "gpt-5-nano-2025-08-07"], "gpt-5-nano-2025-08-07"),
])
def test_ruling_4_a_local_model_gets_no_price_and_a_token_cap(argv: list[str], model: str) -> None:
    """With no price the cap is in tokens, 2,000,000 by default.  The third case names the one
    model whose price is prefilled, on a preset that asks for none: no price either."""
    made = config().config_from_init_args(argv)
    assert made.model.name == model
    assert made.model.price is None
    assert (made.limits.spend_usd, made.limits.tokens) == (None, 2_000_000)


def test_the_price_is_prefilled_only_for_the_published_model() -> None:
    made = config().config_from_init_args([])
    assert made.model.price is not None
    assert (made.model.price.input, made.model.price.cached_input, made.model.price.output,
            made.model.price.read_on) == (0.05, 0.005, 0.40, "2026-09-25")
    other = config().config_from_init_args(["--model", "gpt-4o-mini"])
    assert other.model.price is None and other.limits.tokens == 2_000_000
    assert config().config_from_init_args(["--no-price"]).model.price is None


@pytest.mark.parametrize(("argv", "key"), [
    (["--provider", "anthropic"], "model.name"),
    (["--provider", "vllm"], "model.name"),
    (["--provider", "openai-compatible", "--model", "m", "--api-key-env", "X_API_KEY"],
     "model.base_url"),
    (["--provider", "openai-compatible", "--model", "m", "--base-url", "https://h.test/v1"],
     "model.api_key_env"),
])
def test_fd1_15_a_setting_with_no_default_must_be_given(argv: list[str], key: str) -> None:
    with pytest.raises(config().ConfigError) as error:
        config().config_from_init_args(argv)
    assert error.value.key == key
    given = {"model.name": ["--model", "m"], "model.base_url": ["--base-url", "https://h.test/v1"],
             "model.api_key_env": ["--api-key-env", "X_API_KEY"]}[key]
    config().config_from_init_args([*argv, *given])


def test_fd1_16_openai_base_url_is_the_openai_presets_default_endpoint() -> None:
    proxy = "https://proxy.example.test/v1"
    with openai_base_url(proxy):
        assert config().config_from_init_args([]).model.base_url == proxy
        assert config().config_from_init_args(
            ["--base-url", "https://other.example.test/v1"]).model.base_url == (
            "https://other.example.test/v1")
        assert config().config_from_init_args(["--provider", "ollama"]).model.base_url == (
            "http://127.0.0.1:11434/v1")
        assert config().PRESETS["openai"].endpoint == "https://api.openai.com/v1"
    with openai_base_url(""):
        assert config().config_from_init_args([]).model.base_url == "https://api.openai.com/v1"
    assert config().config_from_init_args([]).model.base_url == "https://api.openai.com/v1"


# --------------------------------------------------------------------------
# ruling 2: the default spend cap
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("expected", "cap"), [
    (None, 1.0),
    (0.0, 1.0),
    (0.0206, 1.0),
    (0.5, 1.0),
    (0.51, 2.0),
    (2.1, 5.0),
    (2.5, 5.0),
    (2.51, 6.0),
])
def test_ruling_2_the_default_cap_is_twice_the_estimate_rounded_up_and_at_least_a_dollar(
    expected: float | None, cap: float
) -> None:
    assert config().default_spend_cap(expected) == cap


def test_ruling_2_init_writes_that_cap_unless_one_is_given() -> None:
    assert config().config_from_init_args(
        ["--measure", "card"], expected_dollars=2.5).limits.spend_usd == 5.0
    assert config().config_from_init_args([], expected_dollars=0.0206).limits.spend_usd == 1.0
    assert config().config_from_init_args(
        ["--measure", "card", "--spend-cap", "3"], expected_dollars=2.5).limits.spend_usd == 3.0
    unpriced = config().config_from_init_args(["--no-price"], expected_dollars=2.5)
    assert (unpriced.limits.spend_usd, unpriced.limits.tokens) == (None, 2_000_000)
