"""What a user's own server says about itself, frozen as tests: `providers.server_facts`.

The invariant is FD2.8 of the front door's plan (spec §9.5): from a fake server, `server_facts`
reads Ollama's version (`/api/version`) and the model's digest (`/api/tags`), or vLLM's version
(`/version`) and served model (`/v1/models`); it marks each field as reported by the server; and
it sends a key only when one is configured.  The card's `self_served` serving kind (FD4) records
what it returns.  Its refusal of a key over plain http is FD2.6's, in `tests/test_fd2_key.py`.

Every request goes to a fake on loopback, inside the network guard of `tests/fd2_fakes.py`.
Every test reaches the module through `importlib`, so the file collects on a tree with no
`poisson_tasks.providers`.

Shapes decided here
-------------------

**1. The facts are one JSON-ready mapping**, so that FD4 can write them into the card's provenance
as they are: `stack` (`"ollama"` or `"vllm"`, the preset's name), `endpoint` (the configured base
URL), `stack_version`, and `model_digest` for Ollama or `served_model` for vLLM, the names
`calibration`'s `local` kind already uses for the stack.  `reported_by_server` lists the fields
whose values came from the server.

**2. A field the server does not report is `None`, and is not in `reported_by_server`**: a
version path that answers 404 (an older server), a model Ollama has not pulled, a model vLLM is
not serving.  The other field is still read.

**3. `/api/version` and `/version` are asked at the endpoint's root** (`http://host:port`), where
both servers answer them; the model list is the endpoint's own `/models`.  The tests use the
presets' `/v1` endpoints, so only that much is pinned.

Not pinned here, and left to the build: what `server_facts` does for the openai, anthropic and
openai-compatible presets; what it does when the server cannot be reached; and an Ollama model
named without its tag (`qwen3` for `qwen3:latest`), which `tests/test_fd2_ollama_latest.py` holds
while it waits on a ruling.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from tests.fd2_fakes import (
    OTHER_BODY,
    OTHER_SENTINEL,
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


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """No key and no proxy from the shell running the suite."""
    for name in ("OPENAI_API_KEY", "VLLM_API_KEY", "OPENAI_BASE_URL", "HTTP_PROXY",
                 "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
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


DIGEST = "500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41"
OTHER_DIGEST = "e5bd1bd2bcc3f5fb6b0d2bfbc3b1d0e7a5e0f6c1d1a2b3c4d5e6f708192a3b4c"


def tags(*models: tuple[str, str]) -> dict[str, Any]:
    """Ollama's `/api/tags`, with each model's name and digest."""
    return {"models": [
        {"name": name, "model": name, "modified_at": "2026-09-28T10:12:44.123456-07:00",
         "size": 5225388164, "digest": digest,
         "details": {"format": "gguf", "family": "qwen3", "parameter_size": "8.2B",
                     "quantization_level": "Q4_K_M"}}
        for name, digest in models]}


def model_list(*ids: str) -> dict[str, Any]:
    return {"object": "list", "data": [{"id": i, "object": "model", "owned_by": "vllm",
                                        "root": i, "max_model_len": 16384} for i in ids]}


def ollama(server: FakeServer, *, version: tuple[int, Any] = (200, {"version": "0.12.6"}),
           pulled: tuple[tuple[str, str], ...] = (("qwen3:4b", OTHER_DIGEST),
                                                  ("qwen3:8b", DIGEST))) -> FakeServer:
    server.route("/api/version", *version)
    server.route("/api/tags", 200, tags(*pulled))
    server.route("/v1/models", 200, model_list(*(name for name, _ in pulled)))
    return server


def vllm(server: FakeServer, *, version: tuple[int, Any] = (200, {"version": "0.29.0+cu129"}),
         served: tuple[str, ...] = ("Qwen/Qwen3-8B",)) -> FakeServer:
    server.route("/version", *version)
    server.route("/v1/models", 200, model_list(*served))
    return server


def model(provider: str, server: FakeServer, *, key_env: str = "") -> Any:
    name = "qwen3:8b" if provider == "ollama" else "Qwen/Qwen3-8B"
    return config().ModelConfig(provider=provider, name=name, base_url=server.url + "/v1",
                                api_key_env=key_env)


def facts_of(made: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, list[tuple[str, Any]]]:
    with network_guard(monkeypatch) as events:
        facts = providers().server_facts(made, timeout=5)
    return facts, events


def test_fd2_8_ollama_reports_its_version_and_the_models_digest(
    fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ollama(fake())
    made = model("ollama", server)
    facts, events = facts_of(made, monkeypatch)
    assert json.loads(json.dumps(facts)) == facts
    assert {k: v for k, v in facts.items() if k != "reported_by_server"} == {
        "stack": "ollama", "endpoint": made.base_url, "stack_version": "0.12.6",
        "model_digest": DIGEST}
    assert sorted(facts["reported_by_server"]) == ["model_digest", "stack_version"]
    assert {r.method for r in server.requests} == {"GET"}
    assert {"/api/version", "/api/tags"} <= {r.path for r in server.requests}
    assert connections(events) == {server.port}


def test_fd2_8_vllm_reports_its_version_and_the_served_model(
    fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = vllm(fake(), served=("Qwen/Qwen3-4B", "Qwen/Qwen3-8B"))
    made = model("vllm", server)
    facts, events = facts_of(made, monkeypatch)
    assert json.loads(json.dumps(facts)) == facts
    assert {k: v for k, v in facts.items() if k != "reported_by_server"} == {
        "stack": "vllm", "endpoint": made.base_url, "stack_version": "0.29.0+cu129",
        "served_model": "Qwen/Qwen3-8B"}
    assert sorted(facts["reported_by_server"]) == ["served_model", "stack_version"]
    assert {r.method for r in server.requests} == {"GET"}
    assert {"/version", "/v1/models"} <= {r.path for r in server.requests}
    assert connections(events) == {server.port}


# (id, preset, the key variable configured, what the shell sets, the header expected)
KEYS: list[tuple[str, str, str, dict[str, str], str | None]] = [
    ("vllm-with-a-key", "vllm", "VLLM_API_KEY", {"VLLM_API_KEY": SENTINEL}, f"Bearer {SENTINEL}"),
    ("vllm-no-key-variable", "vllm", "", {"OPENAI_API_KEY": OTHER_SENTINEL}, None),
    ("vllm-variable-not-set", "vllm", "VLLM_API_KEY", {"OPENAI_API_KEY": OTHER_SENTINEL}, None),
    ("ollama-no-key-variable", "ollama", "", {"OPENAI_API_KEY": OTHER_SENTINEL}, None),
]


@pytest.mark.parametrize(("preset", "key_env", "shell", "header"), [k[1:] for k in KEYS],
                         ids=[k[0] for k in KEYS])
def test_fd2_8_a_key_is_sent_only_when_one_is_configured(
    preset: str, key_env: str, shell: dict[str, str], header: str | None,
    fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On every request when one is, and never OpenAI's from the shell."""
    server = (ollama if preset == "ollama" else vllm)(fake())
    for name, value in shell.items():
        monkeypatch.setenv(name, value)
    facts, _ = facts_of(model(preset, server, key_env=key_env), monkeypatch)
    assert facts["stack_version"] is not None
    assert server.requests
    assert {r.headers.get("authorization") for r in server.requests} == {header}
    assert all("x-api-key" not in r.headers for r in server.requests)
    assert leaked(server.seen(), OTHER_BODY) == []


# (id, preset, the server, the field it does not report)
UNREPORTED: list[tuple[str, str, Callable[[FakeServer], FakeServer], str]] = [
    ("ollama-no-version", "ollama",
     lambda s: ollama(s, version=(404, "404 page not found")), "stack_version"),
    ("ollama-model-not-pulled", "ollama",
     lambda s: ollama(s, pulled=(("qwen3:4b", OTHER_DIGEST),)), "model_digest"),
    ("vllm-no-version", "vllm",
     lambda s: vllm(s, version=(404, {"detail": "Not Found"})), "stack_version"),
    ("vllm-model-not-served", "vllm", lambda s: vllm(s, served=("Qwen/Qwen3-4B",)),
     "served_model"),
]


@pytest.mark.parametrize(("preset", "serve", "missing"), [u[1:] for u in UNREPORTED],
                         ids=[u[0] for u in UNREPORTED])
def test_fd2_8_a_field_the_server_does_not_report_is_none_and_not_marked(
    preset: str, serve: Callable[[FakeServer], FakeServer], missing: str,
    fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = serve(fake())
    facts, _ = facts_of(model(preset, server), monkeypatch)
    other = ({"stack_version", "model_digest"} if preset == "ollama"
             else {"stack_version", "served_model"}) - {missing}
    assert facts[missing] is None
    assert all(facts[name] is not None for name in other)
    assert sorted(facts["reported_by_server"]) == sorted(other)
