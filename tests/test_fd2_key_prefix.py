"""The free key check's rule of four, without the key's public prefix, frozen as tests.

Ruled 2026-10-12 (the key mask session's yes/no 2): the key check keeps a provider's short value
(a refusal's error code, a vLLM server's version) only when it holds no four characters in a row
of the key's secret part, the part after its public prefix (`tests/keymask_support.py` states the
rule; the run engine masks by the same one).  Before, the prefix counted too, so with a project
key a code holding `proj` or a version holding `-pro` was dropped from the check's sentence.

- **Kept**: a value that shares only the public prefix with the key.
- **Still dropped**: a value holding four characters of the secret part, right after the prefix,
  at its end (the last four a provider shows of a masked key), or anywhere in a key with no public
  prefix at its start; and a key too short to have a secret part counts whole.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from tests.fd2_fakes import FakeServer, network_guard
from tests.keymask_support import LOCAL_KEY, PROJECT_KEY, SHORT_KEY


def providers() -> Any:
    return importlib.import_module("poisson_tasks.providers")


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """No key and no proxy from the shell running the suite, as the frozen FD2 tests run."""
    for name in ("OPENAI_API_KEY", "MY_API_KEY", "VLLM_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
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


def model(provider: str, base_url: str, key_env: str) -> Any:
    return config().ModelConfig(
        provider=provider, name="m1", base_url=base_url, api_key_env=key_env
    )


def refused_with(
    code: str, key: str, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch
) -> Any:
    """The key check's result when the endpoint refuses `key` with `code`."""
    monkeypatch.setenv("MY_API_KEY", key)
    server = fake().route("/v1/models", 401, {"error": {"message": "refused", "code": code}})
    with network_guard(monkeypatch):
        return providers().check_key(
            model("openai-compatible", server.url + "/v1", "MY_API_KEY"), timeout=5
        )


def version_with(
    version: str, key: str, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch
) -> Any:
    """The vLLM server's version as the check reads it when the server is sent `key`."""
    monkeypatch.setenv("VLLM_API_KEY", key)
    server = (
        fake()
        .route("/version", 200, {"version": version})
        .route("/v1/models", 200, {"object": "list", "data": [{"id": "m1", "object": "model"}]})
    )
    with network_guard(monkeypatch):
        facts = providers().server_facts(
            model("vllm", server.url + "/v1", "VLLM_API_KEY"), timeout=5
        )
    return facts["stack_version"]


@pytest.mark.parametrize("code", ["invalid_project", "no-project-key"])
def test_a_refusals_code_that_shares_only_the_public_prefix_is_kept(
    code: str, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = refused_with(code, PROJECT_KEY, fake, monkeypatch)
    assert result.status == providers().REFUSED
    assert result.code == code


def test_a_servers_version_that_shares_only_the_public_prefix_is_kept(
    fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert version_with("0.11.0-pro", PROJECT_KEY, fake, monkeypatch) == "0.11.0-pro"


@pytest.mark.parametrize(
    ("key", "code"),
    [
        (PROJECT_KEY, "invalid_record_id"),
        (PROJECT_KEY, "sk-proj-Qm7R"),
        (LOCAL_KEY, "token-Zq8"),
        (SHORT_KEY, "sk-Zq9"),
        (PROJECT_KEY, "key-" + PROJECT_KEY[-4:]),
    ],
    ids=[
        "after-the-prefix",
        "the-prefix-and-four-more",
        "no-public-prefix",
        "too-short-to-split",
        "its-last-four",
    ],
)
def test_four_characters_of_the_secret_part_still_drop_the_code(
    key: str, code: str, fake: Callable[[], FakeServer], monkeypatch: pytest.MonkeyPatch
) -> None:
    result = refused_with(code, key, fake, monkeypatch)
    assert result.status == providers().REFUSED and result.code is None
    assert code not in repr(result)
