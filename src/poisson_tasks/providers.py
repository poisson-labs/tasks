"""The key, the server and the environment: what `init`, `doctor` and `run` check before anything
is spent.

Three things, each free:
- **the key.**  `key_is_set` says whether the variable a config names holds a value, with no
  network.  `check_key` asks the configured endpoint, with one free GET to the preset's
  model-list or model-retrieve path, whether it takes the key and serves the model, and returns a
  `KeyCheck` with one of six statuses.
- **the server.**  `server_facts` reads what a user's Ollama or vLLM server says about itself,
  for the card's `self_served` serving kind.
- **the environment.**  `environment_report` says which Python and which copy of this package are
  running, whether the tokenizer file is in place, whether uv is where the harness looks for it,
  and whether the platform is supported.  It opens no socket.  `fetch_tokenizer` puts the
  tokenizer file in place.

**The key never shows.**  A key is named by its environment variable only.  Its value is read
from the environment when a request is made, sent only to the configured endpoint's host, and
never written to any return value, message, exception, log or file.

`tests/test_fd2_key.py`, `tests/test_fd2_server.py` and `tests/test_fd2_environment.py` say what
each name does.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any

from poisson_tasks.config import ModelConfig, ProjectConfig

__all__ = [
    "KeyCheck",
    "NOT_SET",
    "ACCEPTED",
    "REFUSED",
    "MODEL_MISSING",
    "UNREACHABLE",
    "NOT_CHECKABLE",
    "key_is_set",
    "check_key",
    "server_facts",
    "EnvironmentReport",
    "environment_report",
    "fetch_tokenizer",
]

# The six outcomes of a key check (spec §7.3).
NOT_SET = "not set"
ACCEPTED = "accepted"
REFUSED = "refused"
MODEL_MISSING = "model missing"
UNREACHABLE = "unreachable"
NOT_CHECKABLE = "not checkable"


@dataclasses.dataclass(frozen=True)
class KeyCheck:
    """What a key check found.

    `status` is one of the six statuses.  `host` is the endpoint's host as the URL writes it, with
    its port when the URL gives one (`api.openai.com`, `127.0.0.1:11434`).  `code` is the
    provider's own error code from the body of a refusal, when it gives one
    (`expired_secret_key`), else `None`.  `detail` is one line: what was found, and what to do.
    """

    status: str
    host: str | None
    code: str | None
    detail: str


def key_is_set(name: str) -> bool:
    """Whether the environment variable `name` holds a value that is not empty.  No network."""
    raise NotImplementedError


def check_key(model: ModelConfig, *, timeout: float = 10) -> KeyCheck:
    """Check the key and the model against `model`'s endpoint, with one free GET.

    `NOT_SET`, with no socket opened, when the model's key variable is named and absent or empty.
    A key that would go over plain `http://` to a host that is not loopback is refused before any
    connection, with `config.ConfigError`, unless `model.allow_plain_http_key`.
    """
    raise NotImplementedError


def server_facts(model: ModelConfig, *, timeout: float = 10) -> dict[str, Any]:
    """What an Ollama or vLLM server reports about itself, for the `self_served` serving kind.

    A mapping with `stack` (the preset's name), `endpoint` (the configured base URL),
    `stack_version`, and `model_digest` (Ollama) or `served_model` (vLLM), and
    `reported_by_server`, the names of the fields whose values the server reported.  A field the
    server did not report is `None`, and is not in that list.  A key is sent only when one is
    configured, and over plain http to a host that is not loopback it is refused as
    `check_key` refuses it.
    """
    raise NotImplementedError


@dataclasses.dataclass(frozen=True)
class EnvironmentReport:
    """Where this environment stands, for `doctor`.

    - `python`: `sys.executable`; `python_version`: its version, `3.11.7`.
    - `package`: the folder this package was imported from; `package_outside_environment`: true
      when that folder is not inside `sys.prefix` (an editable install, or another project's
      environment on the path).
    - `tokenizer`: `"present"`, `"missing"` or `"wrong digest"`; `tokenizer_path`: where the file
      is looked for.
    - `uv`: whether `HOME/.local/bin/uv` exists.
    - `platform`: `sys.platform`; `platform_supported`: macOS or Linux.
    - `key_env`: the config's key variable (`""` when it names none), and `key_set`: whether
      that variable holds a value, `None` when the config names no key variable.  Both are
      `None` without a config.  The key's value is never in the report.
    """

    python: str
    python_version: str
    package: str
    package_outside_environment: bool
    tokenizer: str
    tokenizer_path: str
    uv: bool
    platform: str
    platform_supported: bool
    key_env: str | None
    key_set: bool | None


def environment_report(config: ProjectConfig | None = None) -> EnvironmentReport:
    """The report.  It opens no socket, and imports nothing that needs the tokenizer file."""
    raise NotImplementedError


def fetch_tokenizer() -> pathlib.Path:
    """Put the tokenizer file in place, through `fetch_encoding.fetch`, and return its path."""
    raise NotImplementedError
