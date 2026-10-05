"""An Ollama model named without its tag is the `latest` one: waiting on a yes/no.

Ollama names a model `name:tag`, and a name given without a tag means `name:latest`: `ollama pull
qwen3` pulls `qwen3:latest`, and a chat request for `qwen3` is answered by it.  Ollama's model
list and `/api/tags` always write the tag.  So a `tasks.toml` that says `name = "qwen3"` runs, and
a check that looks for `qwen3` in the list as written would call the model missing, and `run`
would refuse it (spec §8.1 step 4); `server_facts` would find no digest for it.

This file pins the reading, for the Ollama preset only, in both functions, with a control: a name
without a tag does not match another tag of the same model.  It is committed on its own: a "no"
to the yes/no drops that commit and nothing else.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import Any

import pytest

from tests.fd2_fakes import FakeServer, network_guard

DIGEST = "35a1c4bd5f8d0c6d1e6e2f6cc7e0bd6a4f6e1b7f0f2d5e8c9a1b3c5d7e9f1a2b"


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeServer]:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
                 "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")
    made = FakeServer()
    yield made
    made.close()


def serve(server: FakeServer, *tagged: str) -> None:
    server.route("/v1/models", 200, {"object": "list", "data": [
        {"id": name, "object": "model", "owned_by": "library"} for name in tagged]})
    server.route("/api/tags", 200, {"models": [
        {"name": name, "model": name, "size": 5225388164,
         "digest": DIGEST if name.endswith(":latest") else "0" * 64} for name in tagged]})
    server.route("/api/version", 200, {"version": "0.12.6"})


def model(server: FakeServer) -> Any:
    config: Any = importlib.import_module("poisson_tasks.config")
    return config.ModelConfig(provider="ollama", name="qwen3", base_url=server.url + "/v1",
                              api_key_env="")


@pytest.mark.parametrize(("tagged", "expected"), [
    (("qwen3:4b", "qwen3:latest"), "ACCEPTED"),
    (("qwen3:4b", "qwen3:8b"), "MODEL_MISSING"),
], ids=["latest-pulled", "only-other-tags"])
def test_fd2_4_an_untagged_ollama_name_is_checked_as_its_latest_tag(
    tagged: tuple[str, ...], expected: str, server: FakeServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers: Any = importlib.import_module("poisson_tasks.providers")
    serve(server, *tagged)
    with network_guard(monkeypatch):
        result = providers.check_key(model(server), timeout=5)
    assert result.status == getattr(providers, expected)


@pytest.mark.parametrize(("tagged", "digest"), [
    (("qwen3:4b", "qwen3:latest"), DIGEST),
    (("qwen3:4b", "qwen3:8b"), None),
], ids=["latest-pulled", "only-other-tags"])
def test_fd2_8_an_untagged_ollama_name_reports_its_latest_tags_digest(
    tagged: tuple[str, ...], digest: str | None, server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers: Any = importlib.import_module("poisson_tasks.providers")
    serve(server, *tagged)
    with network_guard(monkeypatch):
        facts = providers.server_facts(model(server), timeout=5)
    assert facts["model_digest"] == digest
