"""Four clauses of the key check that keep the key safe, which FD2's build added and no frozen test
pinned, frozen as tests.

FD2 Session B's mutation pass named them among the build's unpinned clauses (its table's `b-`
rows), and Taylor ruled on 2026-10-04 that a test-only session pins them:

- **A redirect is not followed.**  urllib would follow a 3xx to the host it names and carry the
  `Authorization` header there, so the key would reach a host the config did not name.  The
  answer is not checkable (ruled 2026-10-04: an answer that says nothing about the key).
- **A key no header can carry is refused before any request.**  A value with a line break in it
  (a key pasted with its newline) makes Python's client raise an error that quotes the header,
  and so the key; a value with a space or a character outside ASCII would be sent as it is.  The
  check says `REFUSED`, naming the variable, and opens no socket; `server_facts` sends nothing.
- **A value taken from an answer is kept only when it has its shape and holds no part of the
  key**: the error code of a refusal, a server's version and a model's digest.  A server that
  echoes the key, or sends text where a code goes, gets nothing of it into what `check_key` and
  `server_facts` return.
- **The proxy settings are read at each call** (Session A's yes/no 5, ruled 2026-10-04: the key
  check follows the user's proxy settings).  A check made with `HTTP_PROXY` set goes through the
  proxy, and the next one, made with it unset, goes direct.

Every check runs against a fake on loopback (`tests/fd2_fakes.py`), inside its network guard.  No
real key is used and no provider is called.
"""

from __future__ import annotations

import importlib
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from tests.fd2_fakes import (
    FAKE_DOMAIN,
    KEY_BODY,
    SENTINEL,
    FakeServer,
    connections,
    leaked,
    network_guard,
)


def providers() -> Any:
    return importlib.import_module("poisson_tasks.providers")


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


KEY_VARIABLES = ("OPENAI_API_KEY", "MY_API_KEY", "VLLM_API_KEY", "OPENAI_BASE_URL")
PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """No proxy, as the frozen FD2 tests run: none set, and `NO_PROXY` is `*`."""
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """No key, no base URL and no proxy from the shell running the suite."""
    for name in KEY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    no_proxy(monkeypatch)


@pytest.fixture
def fake() -> Iterator[Callable[[], FakeServer]]:
    made: list[FakeServer] = []

    def make() -> FakeServer:
        made.append(FakeServer())
        return made[-1]

    yield make
    for server in made:
        server.close()


def model(provider: str, base_url: str, key_env: str = "", name: str = "m1") -> Any:
    return config().ModelConfig(
        provider=provider, name=name, base_url=base_url, api_key_env=key_env
    )


def model_list(*ids: str) -> dict[str, Any]:
    return {"object": "list", "data": [{"id": i, "object": "model"} for i in ids]}


# --------------------------------------------------------------------------
# a redirect is not followed
# --------------------------------------------------------------------------


class Redirector:
    """A server on loopback that answers every request with `status` and a `Location` on another
    host, and records the headers of each request it is sent."""

    def __init__(self, status: int, to: str) -> None:
        self.seen: list[dict[str, str]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                outer.seen.append({k.lower(): v for k, v in self.headers.items()})
                self.send_response(status)
                self.send_header("Location", to + self.path)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True)
        self.thread.start()
        self.port = int(self.server.server_address[1])
        self.url = f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(10)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirect_is_not_followed_so_the_key_reaches_no_other_host(
    status: int,
    fake: Callable[[], FakeServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elsewhere = fake().route("/v1/models", 200, model_list("m1"))
    redirector = Redirector(status, f"http://elsewhere.{FAKE_DOMAIN}:{elsewhere.port}")
    try:
        monkeypatch.setenv("MY_API_KEY", SENTINEL)
        with network_guard(monkeypatch) as events:
            result = providers().check_key(
                model("openai-compatible", redirector.url + "/v1", "MY_API_KEY"), timeout=5
            )
    finally:
        redirector.close()
    assert [seen.get("authorization") for seen in redirector.seen] == [f"Bearer {SENTINEL}"]
    assert elsewhere.requests == []
    assert connections(events) == {redirector.port}
    assert result.status == providers().NOT_CHECKABLE
    assert leaked(repr(result)) == []


# --------------------------------------------------------------------------
# a key no header can carry is refused before any request
# --------------------------------------------------------------------------

UNSENDABLE = {
    "a-trailing-newline": SENTINEL + "\n",
    "a-header-after-it": SENTINEL + "\r\nX-Injected: 1",
    "a-space": SENTINEL[:16] + " " + SENTINEL[16:],
    "a-letter-outside-ascii": SENTINEL + "é",
}


@pytest.mark.parametrize("value", list(UNSENDABLE.values()), ids=list(UNSENDABLE))
def test_a_key_no_header_can_carry_is_refused_before_any_request(
    value: str,
    fake: Callable[[], FakeServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = fake().route("/v1/models", 200, model_list("m1"))
    monkeypatch.setenv("MY_API_KEY", value)
    with network_guard(monkeypatch) as events:
        result = providers().check_key(
            model("openai-compatible", server.url + "/v1", "MY_API_KEY"), timeout=5
        )
    assert events == [] and server.requests == []
    assert result.status == providers().REFUSED
    assert "\n" not in result.detail and "MY_API_KEY" in result.detail, result.detail
    assert leaked(repr(result)) == []
    monkeypatch.setenv("MY_API_KEY", SENTINEL)
    with network_guard(monkeypatch):
        control = providers().check_key(
            model("openai-compatible", server.url + "/v1", "MY_API_KEY"), timeout=5
        )
    assert control.status == providers().ACCEPTED


@pytest.mark.parametrize("value", list(UNSENDABLE.values()), ids=list(UNSENDABLE))
def test_server_facts_sends_no_key_a_header_cannot_carry(
    value: str,
    fake: Callable[[], FakeServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = (
        fake()
        .route("/version", 200, {"version": "0.11.0"})
        .route("/v1/models", 200, model_list("m1"))
    )
    monkeypatch.setenv("VLLM_API_KEY", value)
    with network_guard(monkeypatch) as events:
        facts = providers().server_facts(
            model("vllm", server.url + "/v1", "VLLM_API_KEY"), timeout=5
        )
    assert events == [] and server.requests == []
    assert facts["reported_by_server"] == []
    assert leaked(repr(facts)) == []


# --------------------------------------------------------------------------
# a value from an answer is kept only with its shape and no part of the key
# --------------------------------------------------------------------------

NOT_KEPT = {"part-of-the-key": KEY_BODY[:20], "not-shaped-like-one": "expired key\nretry later"}


@pytest.mark.parametrize("code", list(NOT_KEPT.values()), ids=list(NOT_KEPT))
def test_a_refusals_code_is_kept_only_with_its_shape_and_no_part_of_the_key(
    code: str,
    fake: Callable[[], FakeServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MY_API_KEY", SENTINEL)

    def refused_with(said: str) -> Any:
        server = fake().route("/v1/models", 401, {"error": {"code": said}})
        with network_guard(monkeypatch):
            return providers().check_key(
                model("openai-compatible", server.url + "/v1", "MY_API_KEY"), timeout=5
            )

    result = refused_with(code)
    assert result.status == providers().REFUSED and result.code is None
    assert "\n" not in result.detail and leaked(repr(result)) == []
    assert refused_with("expired_secret_key").code == "expired_secret_key"


@pytest.mark.parametrize(
    "version", [SENTINEL, "0.11.0\nbuilt from main"], ids=["the-key", "not-shaped-like-one"]
)
def test_a_servers_version_is_kept_only_with_its_shape_and_no_part_of_the_key(
    version: str,
    fake: Callable[[], FakeServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VLLM_API_KEY", SENTINEL)

    def facts_with(said: str) -> Any:
        server = (
            fake()
            .route("/version", 200, {"version": said})
            .route("/v1/models", 200, model_list("m1"))
        )
        with network_guard(monkeypatch):
            return providers().server_facts(
                model("vllm", server.url + "/v1", "VLLM_API_KEY"), timeout=5
            )

    facts = facts_with(version)
    assert facts["stack_version"] is None
    assert facts["reported_by_server"] == ["served_model"]
    assert leaked(repr(facts)) == []
    assert facts_with("0.11.0")["stack_version"] == "0.11.0"


DIGEST = "a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72"


@pytest.mark.parametrize("digest", ["latest", DIGEST + "\n" + DIGEST], ids=["a-tag", "two-lines"])
def test_a_models_digest_is_kept_only_with_its_shape(
    digest: str,
    fake: Callable[[], FakeServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def facts_with(said: str) -> Any:
        server = (
            fake()
            .route("/api/version", 200, {"version": "0.12.6"})
            .route(
                "/api/tags",
                200,
                {"models": [{"name": "qwen3:8b", "model": "qwen3:8b", "digest": said}]},
            )
        )
        with network_guard(monkeypatch):
            return providers().server_facts(
                model("ollama", server.url + "/v1", name="qwen3:8b"), timeout=5
            )

    facts = facts_with(digest)
    assert facts["model_digest"] is None
    assert facts["reported_by_server"] == ["stack_version"]
    assert facts_with(DIGEST)["model_digest"] == DIGEST


# --------------------------------------------------------------------------
# the proxy settings are read at each call
# --------------------------------------------------------------------------


def test_the_proxy_settings_are_read_at_each_call(
    fake: Callable[[], FakeServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy, target = fake(), fake()
    target.route("/v1/models", 200, model_list("m1"))
    through = f"http://{FAKE_DOMAIN}:{target.port}/v1/models"
    proxy.route(through, 200, model_list("m1"))
    made = model("openai-compatible", f"http://{FAKE_DOMAIN}:{target.port}/v1")

    monkeypatch.delenv("NO_PROXY")
    monkeypatch.delenv("no_proxy")
    monkeypatch.setenv("HTTP_PROXY", proxy.url)
    monkeypatch.setenv("http_proxy", proxy.url)
    with network_guard(monkeypatch) as events:
        first = providers().check_key(made, timeout=5)
    assert first.status == providers().ACCEPTED
    assert [request.path for request in proxy.requests] == [through]
    assert target.requests == [] and connections(events) == {proxy.port}

    no_proxy(monkeypatch)
    with network_guard(monkeypatch) as events:
        second = providers().check_key(made, timeout=5)
    assert second.status == providers().ACCEPTED
    assert [request.path for request in target.requests] == ["/v1/models"]
    assert len(proxy.requests) == 1 and connections(events) == {target.port}
