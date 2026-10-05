"""The key check, frozen as tests: `providers.key_is_set` and `providers.check_key`.

The invariants are FD2.1 to FD2.6 of the front door's plan (spec §7.1's free checks and §7.3),
and two rulings: a key is named by its environment variable only, never stored or printed; and an
"another OpenAI-compatible endpoint" setup names its own key variable, so OpenAI's key is never
sent to a third party's host.  FD2.1 is held here over every public function of the module: the
key check on each of its status paths, the plain-http refusal, `server_facts` and
`environment_report`.

Every check runs against a fake provider on loopback (`tests/fd2_fakes.py`), inside a guard that
records every socket event and stops any that would leave the machine.  No real key is used and
no provider is called.  Every test reaches the module through `importlib`, so the file collects on
a tree with no `poisson_tasks.providers` and each test fails there for that one reason.

The proxy variables are cleared and `NO_PROXY` is `*` in every test, so a build that honours the
proxy settings, as the OpenAI client does, sends its request where the test can see it.  Whether
the key check follows a user's proxy is not pinned.

Shapes decided here
-------------------

**1. The statuses are module constants**, `providers.ACCEPTED` and the other five, compared by
equality.  Their values are not pinned.

**2. `KeyCheck.host` is the endpoint's host as its URL writes it, with the port when the URL gives
one** (`urllib.parse.urlsplit(base_url).netloc` for a URL with no user part): `127.0.0.1:11434`,
as the spec's `cannot reach 127.0.0.1:11434` names it.  It is pinned on every status that made a
request or tried to.

**3. `KeyCheck.code` is the provider's own code**, read from the error body: `error.code` in
OpenAI's shape (`{"error": {"code": "expired_secret_key", ...}}`), and `error.type` in
Anthropic's, whose errors carry no `code` (`{"type": "error", "error": {"type":
"authentication_error", ...}}`).  `None` when the body is not JSON or names none.  It is pinned
on refusals, as the plan asks; on other statuses it is not.

**4. `KeyCheck.detail` is one line.**  Its wording is not pinned; the facts it must carry are:
the key's variable, when the key is not set or refused; the provider's code, when a refusal has
one; the model's name, when it is missing; and for Ollama, `ollama pull <model>` as the next step
(spec §7.1).

**5. The plain-http refusal is a `config.ConfigError` raised by `check_key`, with `.key`
`"model.base_url"`**, the setting whose scheme is wrong, and a one-line message that names
`allow_plain_http_key`, the setting that allows it.  "Loopback" is read from the URL's host as
written: `localhost`, or an address in 127.0.0.0/8 or `::1`.  A name that only starts like one
(`localhost.tasks-fake.test`, `127.0.0.1.tasks-fake.test`) is not loopback, and nor is a URL
whose user part looks like one (`http://127.0.0.1@tasks-fake.test`).  `server_facts`, which also
sends a configured key, refuses the same way.

**6. On the list path**, used by the Ollama, vLLM and openai-compatible presets, the model is
there when an entry of `data` has its name as `id`.

Not pinned here, and left to the build: the statuses' values; what any other answer maps to (a
500, a 429 or a 400 is pinned only as not accepted); how many times the one path is asked; a
refused key's HTTP status in the detail; the plain-http refusal when the key's variable is named
but not set; whether the check follows a proxy; and the `timeout` argument's default.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import logging
import time
import traceback
import warnings
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import (
    FAKE_DOMAIN,
    OTHER_BODY,
    OTHER_SENTINEL,
    SENTINEL,
    FakeServer,
    connections,
    free_port,
    leaked,
    network_guard,
    recording_writes,
)


def providers() -> Any:
    return importlib.import_module("poisson_tasks.providers")


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


KEY_VARIABLES = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "VLLM_API_KEY", "MY_API_KEY",
                 "OTHER_API_KEY", "OPENAI_BASE_URL")
PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
                   "all_proxy")


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """No key, no base URL and no proxy from the shell running the suite."""
    for name in KEY_VARIABLES + PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")


@pytest.fixture
def fake() -> Iterator[Callable[[], FakeServer]]:
    made: list[FakeServer] = []

    def make() -> FakeServer:
        made.append(FakeServer())
        return made[-1]

    yield make
    for server in made:
        server.close()


# --------------------------------------------------------------------------
# the presets, as the fake serves them
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Case:
    provider: str
    base: str  # the endpoint's path; the preset's own, or one a user would give
    key_env: str
    name: str
    path: str  # the one path the check may ask

    @property
    def lists(self) -> bool:
        return self.path.endswith("/models")


PRESETS = {
    "openai": Case("openai", "/v1", "OPENAI_API_KEY", "gpt-5-nano-2025-08-07",
                   "/v1/models/gpt-5-nano-2025-08-07"),
    # the preset's endpoint ends in a slash: `https://api.anthropic.com/v1/`
    "anthropic": Case("anthropic", "/v1/", "ANTHROPIC_API_KEY", "claude-haiku-4-5",
                      "/v1/models/claude-haiku-4-5"),
    "ollama": Case("ollama", "/v1", "", "qwen3:8b", "/v1/models"),
    "vllm": Case("vllm", "/v1", "VLLM_API_KEY", "Qwen/Qwen3-8B", "/v1/models"),
    "openai-compatible": Case("openai-compatible", "/openai/v1", "MY_API_KEY", "llama-3.3-70b",
                              "/openai/v1/models"),
}
WITH_KEY = [name for name, case in PRESETS.items() if case.key_env]


def model_list(*ids: str) -> dict[str, Any]:
    return {"object": "list", "data": [{"id": i, "object": "model", "owned_by": "you"}
                                       for i in ids]}


def found(case: Case) -> dict[str, Any]:
    """The body of a 200 that says the model is there."""
    if case.lists:
        return model_list("some-other-model", case.name)
    if case.provider == "anthropic":
        return {"type": "model", "id": case.name, "display_name": "Claude Haiku 4.5",
                "created_at": "2025-10-15T00:00:00Z"}
    return {"id": case.name, "object": "model", "created": 1754425777, "owned_by": "system"}


def openai_error(code: str | None, status_words: str = "invalid_request_error") -> dict[str, Any]:
    """OpenAI's error shape.  The message quotes the key masked, as OpenAI's own does."""
    return {"error": {
        "message": f"Incorrect API key provided: {SENTINEL[:12]}{'*' * 30}{SENTINEL[-4:]}. You can "
                   "find your API key at https://platform.openai.com/account/api-keys.",
        "type": status_words, "param": None, "code": code}}


def anthropic_error(kind: str) -> dict[str, Any]:
    return {"type": "error", "error": {"type": kind, "message": "invalid x-api-key"},
            "request_id": "req_011CSHoEeqs5C35K2UUqR7Fy"}


def model_for(case: Case, base_url: str, *, key_env: str | None = None,
              allow_plain_http_key: bool = False, name: str | None = None) -> Any:
    return config().ModelConfig(
        provider=case.provider, name=case.name if name is None else name, base_url=base_url,
        api_key_env=case.key_env if key_env is None else key_env,
        allow_plain_http_key=allow_plain_http_key)


def check(case: Case, server: FakeServer, monkeypatch: pytest.MonkeyPatch, *,
          key: str | None = SENTINEL, **model: Any) -> tuple[Any, list[tuple[str, Any]]]:
    """Run the check of `case` against `server`, with `key` in the case's variable, inside the
    guard; give the result and the socket events."""
    if case.key_env and key is not None:
        monkeypatch.setenv(case.key_env, key)
    made = model_for(case, server.url + case.base, **model)
    with network_guard(monkeypatch) as events:
        result = providers().check_key(made, timeout=5)
    return result, events


def one_line(text: str) -> bool:
    return bool(text.strip()) and "\n" not in text.strip()


# --------------------------------------------------------------------------
# FD2.3 free by construction: one GET, to the preset's path
# --------------------------------------------------------------------------


@pytest.mark.parametrize("preset", list(PRESETS))
def test_fd2_3_the_check_asks_only_the_presets_path_with_a_get(
    preset: str, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The endpoint's own path is kept (`/openai/v1/models`), and a trailing slash on it adds no
    second one (`/v1/models/...`, not `/v1//models/...`)."""
    case = PRESETS[preset]
    server = fake().route(case.path, 200, found(case))
    result, _ = check(case, server, monkeypatch)
    assert server.requests
    assert {(r.method, r.path) for r in server.requests} == {("GET", case.path)}
    assert all(int(r.headers.get("content-length", "0")) == 0 for r in server.requests)
    assert result.status == providers().ACCEPTED


# --------------------------------------------------------------------------
# FD2.2 one host, in the preset's header
# --------------------------------------------------------------------------


@pytest.mark.parametrize("preset", WITH_KEY)
def test_fd2_2_the_key_goes_in_the_presets_header(
    preset: str, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Bearer token, and `x-api-key` with no `Authorization` for Anthropic's native API."""
    case = PRESETS[preset]
    server = fake().route(case.path, 200, found(case))
    check(case, server, monkeypatch)
    for request in server.requests:
        if case.provider == "anthropic":
            assert request.headers.get("x-api-key") == SENTINEL
            assert "authorization" not in request.headers
        else:
            assert request.headers.get("authorization") == f"Bearer {SENTINEL}"
            assert "x-api-key" not in request.headers


def test_fd2_2_the_check_connects_to_the_configured_host_and_no_other(
    fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`OPENAI_BASE_URL` points at a second server; the check goes only where the model says."""
    case = PRESETS["openai"]
    endpoint, elsewhere = fake(), fake()
    endpoint.route(case.path, 200, found(case))
    elsewhere.route(case.path, 200, found(case))
    monkeypatch.setenv("OPENAI_BASE_URL", elsewhere.url + "/v1")
    result, events = check(case, endpoint, monkeypatch)
    assert result.status == providers().ACCEPTED
    assert connections(events) == {endpoint.port}
    assert elsewhere.requests == []


def test_fd2_2_a_named_variable_is_the_only_key_sent(
    fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ruling of 2026-10-03: another endpoint's key is the variable it names, and OpenAI's
    key, set in the same shell, is never sent there."""
    case = PRESETS["openai-compatible"]
    server = fake().route(case.path, 200, found(case))
    monkeypatch.setenv("OPENAI_API_KEY", OTHER_SENTINEL)
    check(case, server, monkeypatch)
    assert {r.headers.get("authorization") for r in server.requests} == {f"Bearer {SENTINEL}"}
    assert leaked(server.seen(), OTHER_BODY) == []


@pytest.mark.parametrize("preset", ["ollama", "vllm", "openai-compatible"])
def test_fd2_2_no_key_variable_sends_no_key(
    preset: str, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`api_key_env = ""` means no key: no key header at all, and not OpenAI's from the shell."""
    case = PRESETS[preset]
    server = fake().route(case.path, 200, found(case))
    monkeypatch.setenv("OPENAI_API_KEY", OTHER_SENTINEL)
    result, _ = check(case, server, monkeypatch, key_env="")
    assert server.requests
    for request in server.requests:
        assert "authorization" not in request.headers
        assert "x-api-key" not in request.headers
    assert leaked(server.seen(), OTHER_BODY) == []
    assert result.status == providers().ACCEPTED


# --------------------------------------------------------------------------
# FD2.4 each answer maps to its status
# --------------------------------------------------------------------------

# (id, preset, status, body, the status's name, the code)
ANSWERS: list[tuple[str, str, int, Any, str, str | None]] = [
    ("openai-ok", "openai", 200, None, "ACCEPTED", None),
    ("openai-expired", "openai", 401, openai_error("expired_secret_key"), "REFUSED",
     "expired_secret_key"),
    ("openai-invalid", "openai", 401, openai_error("invalid_api_key"), "REFUSED",
     "invalid_api_key"),
    ("openai-forbidden", "openai", 403,
     openai_error("unsupported_country_region_territory", "request_forbidden"), "REFUSED",
     "unsupported_country_region_territory"),
    ("openai-no-code", "openai", 401, openai_error(None), "REFUSED", None),
    ("openai-not-json", "openai", 401, "401 Unauthorized", "REFUSED", None),
    ("openai-no-model", "openai", 404, openai_error("model_not_found"), "MODEL_MISSING", None),
    ("anthropic-ok", "anthropic", 200, None, "ACCEPTED", None),
    ("anthropic-refused", "anthropic", 401, anthropic_error("authentication_error"), "REFUSED",
     "authentication_error"),
    ("anthropic-forbidden", "anthropic", 403, anthropic_error("permission_error"), "REFUSED",
     "permission_error"),
    ("anthropic-no-model", "anthropic", 404, anthropic_error("not_found_error"),
     "MODEL_MISSING", None),
    ("ollama-listed", "ollama", 200, None, "ACCEPTED", None),
    ("ollama-not-listed", "ollama", 200, model_list("llama3.2:3b", "qwen3:4b"), "MODEL_MISSING",
     None),
    ("ollama-no-list", "ollama", 404, "404 page not found", "NOT_CHECKABLE", None),
    ("vllm-listed", "vllm", 200, None, "ACCEPTED", None),
    ("vllm-not-listed", "vllm", 200, model_list("Qwen/Qwen3-4B"), "MODEL_MISSING", None),
    ("vllm-refused", "vllm", 401, {"error": "Unauthorized"}, "REFUSED", None),
    ("vllm-no-list", "vllm", 405, {"detail": "Method Not Allowed"}, "NOT_CHECKABLE", None),
    ("compatible-listed", "openai-compatible", 200, None, "ACCEPTED", None),
    ("compatible-not-listed", "openai-compatible", 200, model_list("llama-3.1-8b"),
     "MODEL_MISSING", None),
    ("compatible-refused", "openai-compatible", 401, openai_error("invalid_api_key"), "REFUSED",
     "invalid_api_key"),
    ("compatible-no-list", "openai-compatible", 404, {"error": "not found"}, "NOT_CHECKABLE",
     None),
    ("compatible-not-allowed", "openai-compatible", 405, "Method Not Allowed", "NOT_CHECKABLE",
     None),
]


@pytest.mark.parametrize(("preset", "status", "body", "expected", "code"),
                         [a[1:] for a in ANSWERS], ids=[a[0] for a in ANSWERS])
def test_fd2_4_each_answer_maps_to_its_status(
    preset: str, status: int, body: Any, expected: str, code: str | None,
    fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = PRESETS[preset]
    server = fake().route(case.path, status, found(case) if body is None else body)
    result, _ = check(case, server, monkeypatch)
    assert {r.path for r in server.requests} == {case.path}
    assert result.status == getattr(providers(), expected)
    assert result.host == server.netloc
    assert one_line(result.detail)
    if expected == "REFUSED":
        assert result.code == code
        assert case.key_env in result.detail
        if code is not None:
            assert code in result.detail
    if expected == "MODEL_MISSING":
        assert case.name in result.detail
        if preset == "ollama":
            assert f"ollama pull {case.name}" in result.detail


def test_fd2_4_a_refused_connection_is_unreachable_naming_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = PRESETS["ollama"]
    port = free_port()
    made = model_for(case, f"http://127.0.0.1:{port}/v1")
    with network_guard(monkeypatch) as events:
        result = providers().check_key(made, timeout=5)
    assert ("connect", ("127.0.0.1", port)) in events
    assert result.status == providers().UNREACHABLE
    assert result.host == f"127.0.0.1:{port}"
    assert result.host in result.detail
    assert one_line(result.detail)


def test_fd2_4_a_server_that_never_answers_is_unreachable_within_the_timeout(
    fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = PRESETS["openai"]
    server = fake().hang(case.path)
    monkeypatch.setenv(case.key_env, SENTINEL)
    made = model_for(case, server.url + case.base)
    start = time.monotonic()
    with network_guard(monkeypatch):
        result = providers().check_key(made, timeout=0.5)
    assert time.monotonic() - start < 5
    assert server.requests
    assert result.status == providers().UNREACHABLE
    assert result.host == server.netloc


def test_fd2_4_a_name_that_does_not_resolve_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Over https with a key set: not refused as plain http, and no connection is made."""
    case = PRESETS["openai-compatible"]
    monkeypatch.setenv(case.key_env, SENTINEL)
    made = model_for(case, "https://gateway.nowhere.invalid/openai/v1")
    with network_guard(monkeypatch) as events:
        result = providers().check_key(made, timeout=5)
    assert ("getaddrinfo", "gateway.nowhere.invalid") in events
    assert connections(events) == set()
    assert result.status == providers().UNREACHABLE
    assert result.host == "gateway.nowhere.invalid"


OTHER_ANSWERS = [
    ("openai", 500, {"error": {"message": "The server had an error", "code": None}}),
    ("openai", 429, openai_error("rate_limit_exceeded")),
    ("openai", 400, openai_error("invalid_request")),
    ("anthropic", 529, anthropic_error("overloaded_error")),
    ("vllm", 200, "this is not a model list"),
    ("vllm", 200, {"object": "list"}),
    ("openai-compatible", 502, "Bad Gateway"),
]


@pytest.mark.parametrize(("preset", "status", "body"), OTHER_ANSWERS,
                         ids=[f"{p}-{s}-{i}" for i, (p, s, _) in enumerate(OTHER_ANSWERS)])
def test_fd2_4_any_other_answer_is_never_accepted(
    preset: str, status: int, body: Any, fake: Callable[[], FakeServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What these map to is the build's; that none of them reads as a working key is not."""
    case = PRESETS[preset]
    server = fake().route(case.path, status, body)
    result, _ = check(case, server, monkeypatch)
    p = providers()
    assert result.status in {p.REFUSED, p.MODEL_MISSING, p.UNREACHABLE, p.NOT_CHECKABLE}
    assert result.host == server.netloc
    assert one_line(result.detail)


# --------------------------------------------------------------------------
# FD2.5 not set
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, ""], ids=["absent", "empty"])
@pytest.mark.parametrize("preset", WITH_KEY)
def test_fd2_5_a_key_absent_or_empty_is_not_set_and_opens_no_socket(
    preset: str, value: str | None, fake: Callable[[], FakeServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = PRESETS[preset]
    server = fake().route(case.path, 200, found(case))
    if value is not None:
        monkeypatch.setenv(case.key_env, value)
    made = model_for(case, server.url + case.base)
    with network_guard(monkeypatch) as events:
        result = providers().check_key(made, timeout=5)
    assert events == []
    assert server.requests == []
    assert result.status == providers().NOT_SET
    assert case.key_env in result.detail
    assert one_line(result.detail)


def test_fd2_5_key_is_set_only_for_a_value(monkeypatch: pytest.MonkeyPatch) -> None:
    is_set = providers().key_is_set
    assert is_set("MY_API_KEY") is False
    monkeypatch.setenv("MY_API_KEY", "")
    assert is_set("MY_API_KEY") is False
    monkeypatch.setenv("MY_API_KEY", SENTINEL)
    assert is_set("MY_API_KEY") is True
    assert is_set("") is False


# --------------------------------------------------------------------------
# FD2.6 plain http
# --------------------------------------------------------------------------

NOT_LOOPBACK = {
    "a-name": "http://{fake}:{port}",
    "starts-like-localhost": "http://localhost.{fake}:{port}",
    "starts-like-127": "http://127.0.0.1.{fake}:{port}",
    "a-user-part-like-127": "http://127.0.0.1@{fake}:{port}",
}


def at(template: str, server: FakeServer, base: str) -> str:
    return template.format(fake=FAKE_DOMAIN, port=server.port) + base


@pytest.mark.parametrize("where", list(NOT_LOOPBACK))
def test_fd2_6_a_key_over_plain_http_to_another_host_is_refused_before_any_connection(
    where: str, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = PRESETS["openai-compatible"]
    server = fake().route(case.path, 200, found(case))
    monkeypatch.setenv(case.key_env, SENTINEL)
    made = model_for(case, at(NOT_LOOPBACK[where], server, case.base))
    with network_guard(monkeypatch) as events, pytest.raises(config().ConfigError) as refused:
        providers().check_key(made, timeout=5)
    assert events == []
    assert server.requests == []
    assert refused.value.key == "model.base_url"
    assert one_line(str(refused.value))
    assert "allow_plain_http_key" in str(refused.value)


# A user part in an endpoint's URL is not something a client sends on as written, so it has no
# control here; that it is refused is enough.
ALLOWED = [where for where in NOT_LOOPBACK if where != "a-user-part-like-127"]


@pytest.mark.parametrize("where", ALLOWED)
def test_fd2_6_allow_plain_http_key_lets_it_through(
    where: str, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: the same endpoint, allowed, is asked, with the key."""
    case = PRESETS["openai-compatible"]
    server = fake().route(case.path, 200, found(case))
    monkeypatch.setenv(case.key_env, SENTINEL)
    made = model_for(case, at(NOT_LOOPBACK[where], server, case.base), allow_plain_http_key=True)
    with network_guard(monkeypatch):
        result = providers().check_key(made, timeout=5)
    assert result.status == providers().ACCEPTED
    assert any(r.headers.get("authorization") == f"Bearer {SENTINEL}" for r in server.requests)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_fd2_6_plain_http_to_loopback_is_allowed(
    host: str, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = PRESETS["vllm"]
    server = fake().route(case.path, 200, found(case))
    monkeypatch.setenv(case.key_env, SENTINEL)
    made = model_for(case, f"http://{host}:{server.port}{case.base}")
    with network_guard(monkeypatch):
        result = providers().check_key(made, timeout=5)
    assert result.status == providers().ACCEPTED
    assert any(r.headers.get("authorization") == f"Bearer {SENTINEL}" for r in server.requests)


def test_fd2_6_plain_http_to_another_host_with_no_key_is_allowed(
    fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no key variable there is no key to protect: a vLLM server on the network."""
    case = PRESETS["openai-compatible"]
    server = fake().route(case.path, 200, found(case))
    monkeypatch.setenv("OPENAI_API_KEY", OTHER_SENTINEL)
    made = model_for(case, at(NOT_LOOPBACK["a-name"], server, case.base), key_env="")
    with network_guard(monkeypatch):
        result = providers().check_key(made, timeout=5)
    assert result.status == providers().ACCEPTED
    assert leaked(server.seen(), OTHER_BODY) == []


def vllm_server(server: FakeServer) -> FakeServer:
    return (server.route("/version", 200, {"version": "0.29.0+cu129"})
            .route("/v1/models", 200, model_list("Qwen/Qwen3-8B")))


@pytest.mark.parametrize("allowed", [False, True], ids=["refused", "allowed"])
def test_fd2_6_server_facts_refuses_a_key_over_plain_http_the_same_way(
    allowed: bool, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = PRESETS["vllm"]
    server = vllm_server(fake())
    monkeypatch.setenv(case.key_env, SENTINEL)
    made = model_for(case, at(NOT_LOOPBACK["a-name"], server, case.base),
                     allow_plain_http_key=allowed)
    with network_guard(monkeypatch) as events:
        if allowed:
            facts = providers().server_facts(made, timeout=5)
            assert facts["stack_version"] == "0.29.0+cu129"
            return
        with pytest.raises(config().ConfigError) as refused:
            providers().server_facts(made, timeout=5)
    assert events == []
    assert server.requests == []
    assert refused.value.key == "model.base_url"


# --------------------------------------------------------------------------
# FD2.1 the key never shows
# --------------------------------------------------------------------------


def everything_said(outcome: Any) -> str:
    """A result or an exception, as every form a caller could print or store it in."""
    if isinstance(outcome, BaseException):
        return "".join(traceback.format_exception(outcome)) + repr(outcome.args) + repr(
            vars(outcome))
    parts = [repr(outcome), str(outcome)]
    if dataclasses.is_dataclass(outcome) and not isinstance(outcome, type):
        parts.append(json.dumps(dataclasses.asdict(outcome), default=str))
    elif isinstance(outcome, dict):
        parts.append(json.dumps(outcome, default=str))
    return "\n".join(parts)


Setup = Callable[[FakeServer, pytest.MonkeyPatch], Callable[[], Any]]


def _key_check(preset: str, status: int | None, body: Any = None, *, key_env: str | None = None,
               base: str | None = None, hang: bool = False) -> Setup:
    def setup(server: FakeServer, monkeypatch: pytest.MonkeyPatch) -> Callable[[], Any]:
        case = PRESETS[preset]
        if hang:
            server.hang(case.path)
        elif status is not None:
            server.route(case.path, status, found(case) if body is None else body)
        monkeypatch.setenv(case.key_env, SENTINEL)
        url = (base or server.url + case.base).format(port=free_port(), fake=FAKE_DOMAIN,
                                                      server=server.port)
        made = model_for(case, url, key_env=key_env)
        return lambda: providers().check_key(made, timeout=0.5 if hang else 5)
    return setup


def _facts(server: FakeServer, monkeypatch: pytest.MonkeyPatch) -> Callable[[], Any]:
    case = PRESETS["vllm"]
    server.route("/version", 200, {"version": "0.29.0+cu129", "api_key": SENTINEL})
    server.route("/v1/models", 200, model_list("Qwen/Qwen3-8B"))
    monkeypatch.setenv(case.key_env, SENTINEL)
    made = model_for(case, server.url + case.base)
    return lambda: providers().server_facts(made, timeout=5)


def _report(server: FakeServer, monkeypatch: pytest.MonkeyPatch) -> Callable[[], Any]:
    monkeypatch.setenv("MY_API_KEY", SENTINEL)
    made = config().config_from_init_args([
        "--provider", "openai-compatible", "--model", "llama-3.3-70b",
        "--base-url", server.url + "/openai/v1", "--api-key-env", "MY_API_KEY", "--no-price"])
    return lambda: providers().environment_report(made)


def _key_is_set(server: FakeServer, monkeypatch: pytest.MonkeyPatch) -> Callable[[], Any]:
    monkeypatch.setenv("MY_API_KEY", SENTINEL)
    return lambda: providers().key_is_set("MY_API_KEY")


ECHO = {"error": {"message": f"Incorrect API key provided: {SENTINEL}", "code": "invalid_api_key",
                  "key": SENTINEL[-4:]}}
SAYING: dict[str, Setup] = {
    # the key is in OPENAI_API_KEY, and the config names another variable, which is not set
    "not-set": _key_check("openai-compatible", 200, key_env="OTHER_API_KEY"),
    "accepted": _key_check("openai", 200),
    "refused-quoting-the-key": _key_check("openai", 401, ECHO),
    "refused-masked": _key_check("openai", 401, openai_error("expired_secret_key")),
    "forbidden": _key_check("anthropic", 403, anthropic_error("permission_error")),
    "model-missing": _key_check("openai", 404, ECHO),
    "model-not-listed": _key_check("vllm", 200, model_list("Qwen/Qwen3-4B", SENTINEL)),
    "not-checkable": _key_check("openai-compatible", 404, ECHO),
    "server-error": _key_check("openai", 500, ECHO),
    "connection-refused": _key_check("openai", None, base="http://127.0.0.1:{port}/v1"),
    "timeout": _key_check("openai", None, hang=True),
    "no-such-name": _key_check("openai", None, base="https://api.nowhere.invalid/v1"),
    "plain-http-refused": _key_check("openai-compatible", 200,
                                     base="http://{fake}:{server}/openai/v1"),
    "server-facts": _facts,
    "environment-report": _report,
    "key-is-set": _key_is_set,
}


@pytest.mark.parametrize("path", list(SAYING))
def test_fd2_1_the_key_never_shows(
    path: str, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture, tmp_path: Path,
) -> None:
    """With a sentinel key, every function on every status path holds no four characters of it
    in a row: not in its return value or exception, nor on stdout, stderr, any log record or
    warning, nor in any file it writes.  The provider's own error message quotes the key, whole
    or masked, on several paths."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    if path == "not-set":
        monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
    server = fake()
    call = SAYING[path](server, monkeypatch)
    caplog.set_level(logging.DEBUG)
    outcome: Any
    with warnings.catch_warnings(record=True) as warned, recording_writes() as written, \
            network_guard(monkeypatch):
        warnings.simplefilter("always")
        try:
            outcome = call()
        except Exception as error:  # the plain-http refusal, and anything a build raises
            outcome = error
    out, err = capfd.readouterr()
    said = [everything_said(outcome), out, err]
    said += [f"{r.getMessage()} {r.args!r} {r.exc_text or ''}" for r in caplog.records]
    said += [str(w.message) for w in warned]
    for name in written:
        if Path(name).is_file():
            said.append(Path(name).read_bytes().decode("utf-8", "replace"))
    for each in tmp_path.rglob("*"):
        if each.is_file():
            said.append(each.read_bytes().decode("utf-8", "replace"))
    assert leaked("\n".join(said)) == [], path
    assert REACHED[path](outcome), (path, outcome)
    if SENT[path]:
        # the key was in play: the endpoint was sent it
        assert SENTINEL in server.seen()


def _status(name: str) -> Callable[[Any], bool]:
    return lambda outcome: getattr(outcome, "status", None) == getattr(providers(), name)


# What each path must have reached, so that none passes by failing early.
REACHED: dict[str, Callable[[Any], bool]] = {
    "not-set": _status("NOT_SET"),
    "accepted": _status("ACCEPTED"),
    "refused-quoting-the-key": _status("REFUSED"),
    "refused-masked": _status("REFUSED"),
    "forbidden": _status("REFUSED"),
    "model-missing": _status("MODEL_MISSING"),
    "model-not-listed": _status("MODEL_MISSING"),
    "not-checkable": _status("NOT_CHECKABLE"),
    "server-error": lambda outcome: getattr(outcome, "status", None) in {
        providers().REFUSED, providers().MODEL_MISSING, providers().UNREACHABLE,
        providers().NOT_CHECKABLE},
    "connection-refused": _status("UNREACHABLE"),
    "timeout": _status("UNREACHABLE"),
    "no-such-name": _status("UNREACHABLE"),
    "plain-http-refused": lambda outcome: isinstance(outcome, config().ConfigError),
    "server-facts": lambda outcome: isinstance(outcome, dict)
    and outcome.get("stack_version") == "0.29.0+cu129",
    "environment-report": lambda outcome: getattr(outcome, "key_set", None) is True,
    "key-is-set": lambda outcome: outcome is True,
}
SENT = {path: path in {"accepted", "refused-quoting-the-key", "refused-masked", "forbidden",
                       "model-missing", "model-not-listed", "not-checkable", "server-error",
                       "timeout", "server-facts"} for path in SAYING}
