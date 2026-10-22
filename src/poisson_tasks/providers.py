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
never written to any return value, message, exception, log or file.  Nothing an endpoint answers
is passed on as it came: a message here is made of this module's own words, and the few values
taken from an answer (an error code, a version, a digest) are kept only when they have the shape
of one and hold no four characters in a row of the key's secret part.  A key's public prefix, the
one every key of its kind starts with (`sk-proj-`), is not secret: a value that shares only it
with the key, such as a code holding `proj`, is kept.  `_secret_part` is that rule's one home;
the run engine masks a run's texts by it too.

**The requests** are GETs through the standard library, with the proxy settings of the
environment, read at each call, as verifiers' own client reads them.  A redirect is not followed,
so a key is never carried to a host the config did not name.

`tests/test_fd2_key.py`, `tests/test_fd2_server.py` and `tests/test_fd2_environment.py` say what
each name does.
"""

from __future__ import annotations

import dataclasses
import hashlib
import http.client
import importlib.metadata
import ipaddress
import json
import os
import pathlib
import platform
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from poisson_tasks.config import PRESETS, ConfigError, ModelConfig, ProjectConfig
from poisson_tasks.tokenizer import _ENCODING_PATH, _ENCODING_SHA256

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
    "refuse_plain_http_key",
    "server_facts",
    "EnvironmentReport",
    "environment_report",
    "fetch_tokenizer",
]

# The six outcomes of a key check.
NOT_SET = "not set"
ACCEPTED = "accepted"
REFUSED = "refused"
MODEL_MISSING = "model missing"
UNREACHABLE = "unreachable"
NOT_CHECKABLE = "not checkable"

# The version of Anthropic's native API the model-retrieve check speaks.
_ANTHROPIC_VERSION = "2023-06-01"

# An answer longer than this is not read to its end; a model list is far shorter.
_MAX_BODY = 8 * 1024 * 1024

# The shapes of the values kept from an answer.
_CODE = re.compile(r"[A-Za-z0-9_.\-]{1,80}")
_VERSION = re.compile(r"[A-Za-z0-9_.+\-]{1,80}")
_DIGEST = re.compile(r"(sha256:)?[0-9a-f]{64}")

_PART = 4
"""Four characters of the key's secret part in a row are part of the key."""
_PUBLIC_PREFIX = re.compile(
    r"sk-(?:proj|svcacct|admin|None)-|sk-ant-(?:api|admin)\d\d-|sk-or-v\d+-|sk-"
    r"|gsk_|xai-|fw_|hf_|pplx-|nvapi-|csk-|AIza"
)
"""The public prefixes of the keys providers issue: every key of a kind starts with its prefix."""


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


# ---------------------------------------------------------------------------
# the endpoint, and the one request
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _Endpoint:
    """A model's endpoint, read from its URL.  `host` is the host as written, with its port and
    without any user part; `root` is the scheme and that host; `base` is the root and the URL's
    path, with no slash at its end."""

    host: str
    root: str
    base: str
    query: str
    plain_http: bool
    loopback: bool

    def url(self, path: str, *, at_root: bool = False) -> str:
        made = (self.root if at_root else self.base) + path
        return made + ("?" + self.query if self.query and not at_root else "")


def _endpoint(model: ModelConfig) -> _Endpoint:
    refusal = ConfigError(
        f"[model] base_url is {json.dumps(model.base_url, ensure_ascii=False)}; it must be a URL "
        "starting with https:// or http://",
        key="model.base_url",
    )
    try:
        parts = urllib.parse.urlsplit(model.base_url)
        hostname = parts.hostname
        _ = parts.port
    except ValueError:
        raise refusal from None
    if parts.scheme not in ("http", "https") or not hostname:
        raise refusal
    host = parts.netloc.rpartition("@")[2]
    root = f"{parts.scheme}://{host}"
    return _Endpoint(
        host=host,
        root=root,
        base=root + parts.path.rstrip("/"),
        query=parts.query,
        plain_http=parts.scheme == "http",
        loopback=_is_loopback(hostname),
    )


def _is_loopback(hostname: str) -> bool:
    """Whether the host, as the URL writes it, is this machine: `localhost`, or an address in
    127.0.0.0/8 or `::1`.  A name that only starts like one is not."""
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _refuse_plain_http_key(model: ModelConfig, endpoint: _Endpoint) -> None:
    """A config that names a key and would send it over plain http to another machine is refused
    before any connection, whether or not the variable is set in this shell."""
    if (
        model.api_key_env
        and endpoint.plain_http
        and not endpoint.loopback
        and not model.allow_plain_http_key
    ):
        raise ConfigError(
            f"[model] base_url would send the key in {model.api_key_env} to {endpoint.host} over "
            "plain http, where anyone on the network path can read it; use an https:// URL, or "
            "set allow_plain_http_key = true under [model] to send it anyway",
            key="model.base_url",
        )


def refuse_plain_http_key(model: ModelConfig) -> None:
    """The refusal `check_key` and `server_facts` make before any connection, alone: a config
    that names a key and would send it over plain http to another machine is refused with
    `config.ConfigError` on `model.base_url`, unless `model.allow_plain_http_key`.  Opens no
    socket and reads no key; a config that passes returns `None`."""
    _refuse_plain_http_key(model, _endpoint(model))


def _sendable(key: str) -> bool:
    """Whether a key's value can go in a header as it is: visible ASCII and nothing else.  A value
    with a line break or a control character in it is one no client can send."""
    return all(0x21 <= ord(character) <= 0x7E for character in key)


def _secret_part(key: str) -> str:
    """The key without the public prefix it starts with, if it starts with one.  A secret part
    shorter than four characters is no secret part, and the whole key stands for it."""
    match = _PUBLIC_PREFIX.match(key)
    secret = key[match.end() :] if match else key
    return secret if len(secret) >= _PART else key


def _holds_part_of(text: str, key: str) -> bool:
    """Whether `text` holds any four characters of the key's secret part in a row."""
    secret = _secret_part(key)
    return any(secret[i : i + _PART] in text for i in range(len(secret) - _PART + 1))


def _kept(value: Any, shape: re.Pattern[str], key: str) -> str | None:
    """A value from an answer, kept only when it has its shape and holds no part of the key."""
    if not isinstance(value, str) or not shape.fullmatch(value) or _holds_part_of(value, key):
        return None
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def _user_agent() -> str:
    try:
        return "poisson-tasks/" + importlib.metadata.version("poisson-tasks")
    except importlib.metadata.PackageNotFoundError:
        return "poisson-tasks"


def _headers(model: ModelConfig, key: str, *, native_anthropic: bool = False) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": _user_agent()}
    if native_anthropic:
        headers["anthropic-version"] = _ANTHROPIC_VERSION
        if key:
            headers["x-api-key"] = key
    elif key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


@dataclasses.dataclass(frozen=True)
class _Answer:
    """One GET's outcome: a status and the body as JSON (`None` when it is not JSON), or
    `failure`, this module's own words for why there was no answer."""

    status: int | None
    body: Any = None
    failure: str | None = None


def _get(url: str, headers: dict[str, str], timeout: float) -> _Answer:
    """One GET.  The opener is built here, at each call, so it reads the proxy settings the
    environment has now.  No exception's text is passed on: a failure is described by its kind."""
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            response = opener.open(request, timeout=timeout)
        except urllib.error.HTTPError as answered:
            response = answered
        with response:
            status = int(response.status)
            raw = response.read(_MAX_BODY)
    except (OSError, http.client.HTTPException, ValueError) as error:
        return _Answer(status=None, failure=_failure(error, timeout))
    try:
        body = json.loads(raw.decode("utf-8"))
    except ValueError:
        body = None
    return _Answer(status=status, body=body)


def _failure(error: BaseException, timeout: float) -> str:
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, TimeoutError):
        return f"no answer within {timeout:g} seconds"
    if isinstance(reason, socket.gaierror):
        return "the name did not resolve"
    if isinstance(reason, ConnectionRefusedError):
        return "the connection was refused"
    if isinstance(reason, ssl.SSLError):
        return "the secure connection could not be made"
    return "the connection failed"


# ---------------------------------------------------------------------------
# the key
# ---------------------------------------------------------------------------


def key_is_set(name: str) -> bool:
    """Whether the environment variable `name` holds a value that is not empty.  No network."""
    return bool(name) and bool(os.environ.get(name))


def _ollama_name(name: str) -> str:
    """An Ollama model's name with its tag: a name given without one means its `latest` tag."""
    return name if ":" in name.rsplit("/", 1)[-1] else name + ":latest"


def _names(model: ModelConfig) -> set[str]:
    """The names a server's list may give the model under."""
    if model.provider == "ollama":
        return {model.name, _ollama_name(model.name)}
    return {model.name}


def _listed(body: Any) -> list[str] | None:
    """The ids of an OpenAI-shaped model list, or `None` when the body is not one."""
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        return None
    return [entry["id"] for entry in data if isinstance(entry, dict) and "id" in entry]


def _code(model: ModelConfig, body: Any, key: str) -> str | None:
    """The provider's own code for a refusal: `error.code`, or `error.type` on Anthropic's native
    API, whose errors carry no code."""
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return None
    return _kept(error.get("type" if model.provider == "anthropic" else "code"), _CODE, key)


def _set_it(name: str) -> str:
    return f"set it in this shell (export {name}=…) and run again"


def check_key(model: ModelConfig, *, timeout: float = 10) -> KeyCheck:
    """Check the key and the model against `model`'s endpoint, with one free GET.

    `NOT_SET`, with no socket opened, when the model's key variable is named and absent or empty.
    A key that would go over plain `http://` to a host that is not loopback is refused before any
    connection, with `config.ConfigError`, unless `model.allow_plain_http_key`.

    The GET goes to the preset's path, once: the model itself on the openai and anthropic presets
    (`/models/{model}`), and the model list on the others (`/models`).  200 is `ACCEPTED` when
    the model is there and `MODEL_MISSING` when a list does not hold it; 401 and 403 are
    `REFUSED`; a 404 on the model is `MODEL_MISSING`; no answer is `UNREACHABLE`.  Anything else
    (a 404 or 405 on the list, a 500, a 429, a list that is not one) is `NOT_CHECKABLE`: the
    endpoint answered, and the answer says nothing about the key.  `timeout` is how long each
    wait for the endpoint may last, in seconds.
    """
    if model.provider not in PRESETS:
        raise ConfigError(
            f"[model] provider is {json.dumps(model.provider, ensure_ascii=False)}; it must be "
            "one of " + ", ".join(PRESETS),
            key="model.provider",
        )
    endpoint = _endpoint(model)
    _refuse_plain_http_key(model, endpoint)
    variable = model.api_key_env
    host = endpoint.host
    if variable and not key_is_set(variable):
        return KeyCheck(NOT_SET, host, None, f"{variable} is not set; {_set_it(variable)}")
    key = os.environ.get(variable, "") if variable else ""
    if not _sendable(key):
        return KeyCheck(
            REFUSED,
            host,
            None,
            f"{variable} holds a value no request can carry (a space, a line break or another "
            f"character a key never has); {_set_it(variable)}",
        )

    retrieves = "{model}" in PRESETS[model.provider].key_check_path
    path = PRESETS[model.provider].key_check_path.replace(
        "{model}", urllib.parse.quote(model.name, safe=":@")
    )
    answer = _get(
        endpoint.url(path),
        _headers(model, key, native_anthropic=model.provider == "anthropic"),
        timeout,
    )

    if answer.status is None:
        return KeyCheck(
            UNREACHABLE,
            host,
            None,
            f"cannot reach {host}: {answer.failure}; check base_url under [model], and that the "
            "server is running",
        )
    if answer.status in (401, 403):
        code = _code(model, answer.body, key)
        said = f"{code}, HTTP {answer.status}" if code else f"HTTP {answer.status}"
        if not variable:
            return KeyCheck(
                REFUSED,
                host,
                code,
                f"{host} refused the request ({said}) and the config names no key; name the "
                "variable that holds the key as api_key_env under [model]",
            )
        return KeyCheck(
            REFUSED,
            host,
            code,
            f"{host} refused the key in {variable} ({said}); check the key, then "
            f"{_set_it(variable)}",
        )
    missing = KeyCheck(
        MODEL_MISSING,
        host,
        None,
        f"{host} has no model named {model.name}; "
        + (
            f"pull it with `ollama pull {model.name}` and run again"
            if model.provider == "ollama"
            else "check name under [model]"
        ),
    )
    if retrieves and answer.status == 404:
        return missing
    if answer.status == 200:
        listed = None if retrieves else _listed(answer.body)
        if retrieves or (listed is not None and _names(model) & set(listed)):
            return KeyCheck(
                ACCEPTED,
                host,
                None,
                f"{variable} is set, and {host} accepts it (a free request)"
                if variable
                else f"{host} answers and serves {model.name}; the config names no key",
            )
        if listed is not None:
            return missing
        return KeyCheck(
            NOT_CHECKABLE,
            host,
            None,
            f"{host} answered {path} with something that is not a model list, so the key and "
            "the model cannot be checked for free; a run's first request will show",
        )
    if not retrieves and answer.status in (404, 405):
        return KeyCheck(
            NOT_CHECKABLE,
            host,
            None,
            f"{host} has no model list at {path} (HTTP {answer.status}), so the key and the "
            "model cannot be checked for free; a run's first request will show",
        )
    return KeyCheck(
        NOT_CHECKABLE,
        host,
        None,
        f"{host} answered the free check with HTTP {answer.status}, which says nothing about "
        "the key; try again, or a run's first request will show",
    )


# ---------------------------------------------------------------------------
# the server
# ---------------------------------------------------------------------------


def server_facts(model: ModelConfig, *, timeout: float = 10) -> dict[str, Any]:
    """What an Ollama or vLLM server reports about itself, for the `self_served` serving kind.

    A mapping with `stack` (the preset's name), `endpoint` (the configured base URL),
    `stack_version`, and `model_digest` (Ollama) or `served_model` (vLLM), and
    `reported_by_server`, the names of the fields whose values the server reported.  A field the
    server did not report is `None`, and is not in that list.  A key is sent only when one is
    configured, and over plain http to a host that is not loopback it is refused as
    `check_key` refuses it.

    Ollama's version is read from `/api/version` and the model's digest from `/api/tags`, both at
    the endpoint's root; vLLM's version from `/version` at the root, and the served model from
    the endpoint's own `/models`.  A server that cannot be reached reports nothing, so each field
    is `None`.  The other presets have no server of the user's to read, and are a `ValueError`.
    """
    if model.provider not in ("ollama", "vllm"):
        raise ValueError(
            f"server_facts reads an Ollama or a vLLM server, and this model's provider is "
            f"{model.provider}"
        )
    endpoint = _endpoint(model)
    _refuse_plain_http_key(model, endpoint)
    key = os.environ.get(model.api_key_env, "") if model.api_key_env else ""
    headers = _headers(model, key)
    sendable = _sendable(key)

    def ask(path: str, *, at_root: bool) -> Any:
        if not sendable:
            return None
        answer = _get(endpoint.url(path, at_root=at_root), headers, timeout)
        return answer.body if answer.status == 200 else None

    def version(path: str) -> str | None:
        body = ask(path, at_root=True)
        return _kept(body.get("version") if isinstance(body, dict) else None, _VERSION, key)

    facts: dict[str, Any] = {"stack": model.provider, "endpoint": model.base_url}
    if model.provider == "ollama":
        facts["stack_version"] = version("/api/version")
        facts["model_digest"] = _ollama_digest(model, ask("/api/tags", at_root=True), key)
    else:
        facts["stack_version"] = version("/version")
        listed = _listed(ask("/models", at_root=False))
        facts["served_model"] = model.name if listed is not None and model.name in listed else None
    facts["reported_by_server"] = [
        name for name in ("stack_version", "model_digest", "served_model") if facts.get(name)
    ]
    return facts


def _ollama_digest(model: ModelConfig, body: Any, key: str) -> str | None:
    """The digest `/api/tags` gives for the model, by its name with its tag."""
    models = body.get("models") if isinstance(body, dict) else None
    if not isinstance(models, list):
        return None
    names = _names(model)
    for entry in models:
        if isinstance(entry, dict) and (entry.get("name") in names or entry.get("model") in names):
            return _kept(entry.get("digest"), _DIGEST, key)
    return None


# ---------------------------------------------------------------------------
# the environment
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class EnvironmentReport:
    """Where this environment stands, for `doctor`.

    - `python`: `sys.executable`; `python_version`: its version, `3.11.7`.
    - `package`: the folder this package was imported from; `package_outside_environment`: true
      when that folder is not inside `sys.prefix` (an editable install, or another project's
      environment on the path).
    - `tokenizer`: `"present"`, `"missing"` or `"wrong digest"`; `tokenizer_path`: where the file
      is looked for.  A file that is there and cannot be read is `"wrong digest"`: it is not the
      file the tokenizer needs.
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


def _tokenizer_status() -> str:
    if not _ENCODING_PATH.is_file():
        return "missing"
    try:
        digest = hashlib.sha256(_ENCODING_PATH.read_bytes()).hexdigest()
    except OSError:
        return "wrong digest"
    return "present" if digest == _ENCODING_SHA256 else "wrong digest"


def _uv_in_home() -> bool:
    """Whether uv is where the harness's bootstrap installs it and looks for it first."""
    try:
        home = pathlib.Path.home()
    except RuntimeError:
        return False
    return (home / ".local" / "bin" / "uv").is_file()


def environment_report(config: ProjectConfig | None = None) -> EnvironmentReport:
    """The report.  It opens no socket, and imports nothing that needs the tokenizer file."""
    package = pathlib.Path(__file__).resolve().parent
    key_env = None if config is None else config.model.api_key_env
    return EnvironmentReport(
        python=sys.executable,
        python_version=platform.python_version(),
        package=str(package),
        package_outside_environment=not package.is_relative_to(pathlib.Path(sys.prefix).resolve()),
        tokenizer=_tokenizer_status(),
        tokenizer_path=str(_ENCODING_PATH),
        uv=_uv_in_home(),
        platform=sys.platform,
        platform_supported=sys.platform == "darwin" or sys.platform.startswith("linux"),
        key_env=key_env,
        key_set=key_is_set(key_env) if key_env else None,
    )


def fetch_tokenizer() -> pathlib.Path:
    """Put the tokenizer file in place, through `fetch_encoding.fetch`, and return its path."""
    from poisson_tasks import fetch_encoding

    return fetch_encoding.fetch()
