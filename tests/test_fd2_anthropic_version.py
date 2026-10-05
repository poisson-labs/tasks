"""Anthropic's key check names the API version it speaks: waiting on a yes/no.

Spec §7.1 gives the Anthropic preset's free check as `GET /v1/models/{model}` on the native API,
with `x-api-key`, and says nothing more about its headers.  Anthropic's API documents every
request with an `anthropic-version` header as well (its own model-retrieve example sends
`anthropic-version: 2023-06-01`), and its client libraries send it on every call.  A check
without it risks a 400 from the real API for every Anthropic key, which only the live check
(plan §4.3) would find.

This file pins that the check sends `anthropic-version: 2023-06-01` on each request.  It is
committed on its own: a "no" to the yes/no drops that commit and nothing else.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import Any

import pytest

from tests.fd2_fakes import SENTINEL, FakeServer, network_guard


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeServer]:
    for name in ("ANTHROPIC_API_KEY", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy",
                 "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")
    monkeypatch.setenv("no_proxy", "*")
    made = FakeServer().route("/v1/models/claude-haiku-4-5", 200, {
        "type": "model", "id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5",
        "created_at": "2025-10-15T00:00:00Z"})
    yield made
    made.close()


def test_fd2_2_the_anthropic_check_sends_the_api_version(
    server: FakeServer, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config: Any = importlib.import_module("poisson_tasks.config")
    providers: Any = importlib.import_module("poisson_tasks.providers")
    monkeypatch.setenv("ANTHROPIC_API_KEY", SENTINEL)
    made = config.ModelConfig(provider="anthropic", name="claude-haiku-4-5",
                              base_url=server.url + "/v1/", api_key_env="ANTHROPIC_API_KEY")
    with network_guard(monkeypatch):
        result = providers.check_key(made, timeout=5)
    assert result.status == providers.ACCEPTED
    assert server.requests
    assert {r.headers.get("anthropic-version") for r in server.requests} == {"2023-06-01"}
