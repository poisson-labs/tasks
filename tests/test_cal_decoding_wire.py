"""The declared decoding as it reaches the endpoint: the name the token limit travels under.

The first live calibration pass stopped at its gate with every call refused: OpenAI answers
HTTP 400 to `max_tokens` from `gpt-5-nano-2025-08-07` and asks for `max_completion_tokens`.
`tests/test_cal_calibration.py` checks the decoding as declared (CAL5) and the config the run
builds from it (CAL21), and neither looks at the request body, so the name on the wire was
never pinned.

These tests pin it where it is decided: a real episode through the wheel, carrying the
calibration run's own sampling, against a stub OpenAI-compatible endpoint on loopback that
keeps every request body.  The same body goes to model A on OpenAI and to model B on a vLLM
server, whose chat endpoint accepts `max_completion_tokens` and reads it before the
deprecated `max_tokens`, so both models are driven here and must see the same thing.  No key
is loaded and nothing leaves the machine.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import os
import shutil
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks.knobs import ArmSpec

KEY_VAR = "POISSON_TASKS_CAL_WIRE_TEST_KEY"
MODEL_B = "Qwen/Qwen3-8B"


@contextlib.contextmanager
def recording_endpoint() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """An OpenAI-compatible chat endpoint on loopback that ends every episode on its first
    turn and keeps each request body whole."""
    bodies: list[dict[str, Any]] = []

    class Stub(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            bodies.append(body)
            out = {
                "id": "chatcmpl-stub", "object": "chat.completion", "created": 0,
                "model": body.get("model"),
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Done."},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
            data = json.dumps(out).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", bodies
    finally:
        server.shutdown()
        server.server_close()


def one_episode_body(model: str) -> dict[str, Any]:
    """The first request body one calibration episode sends, through the wheel's own path:
    `run_config_for`'s sampling on the `ModelContext`, as `run_arm` builds it."""
    import verifiers.v1 as vf

    spec = ArmSpec(
        knob="depth", level=3, control=None, strictness="strict",
        split=cal.SPLIT, generator_version=cal.GENERATOR_VERSION,
    )
    _, calibration = cal.run_config_for(spec, model=model)
    config = vf.resolve_env_config({
        "taskset": {"id": cal.TASKSET_ID, "arm": dataclasses.asdict(spec), "seeds": [404]}
    })
    env = vf.load_environment(config)
    task = next(iter(env.taskset.load()))
    saved = os.environ.get(KEY_VAR)
    os.environ[KEY_VAR] = "stub-secret"
    try:
        with recording_endpoint() as (base_url, bodies):
            ctx = vf.ModelContext(
                model=model,
                client=vf.EvalClientConfig(base_url=base_url, api_key_var=KEY_VAR),
                sampling=calibration.sampling,
            )

            async def run() -> Any:
                async with env.serving():
                    return await env.run_episode(task, ctx)

            episode = asyncio.run(run())
    finally:
        if saved is None:
            os.environ.pop(KEY_VAR, None)
        else:
            os.environ[KEY_VAR] = saved
    assert episode.ok, episode.errors
    assert bodies, "the episode sent no request"
    return bodies[0]


@pytest.mark.skipif(
    shutil.which("uv") is None, reason="the `null` harness launches its program through uv"
)
@pytest.mark.parametrize("model", [cal.MODEL_A, MODEL_B], ids=["model_a", "model_b"])
def test_the_token_limit_goes_out_as_max_completion_tokens(model: str) -> None:
    """The limit reaches the endpoint as `max_completion_tokens`, with the declared value,
    and `max_tokens` is absent: OpenAI's reasoning models refuse that name outright."""
    body = one_episode_body(model)
    assert body["model"] == model
    assert "max_tokens" not in body, body
    assert body["max_completion_tokens"] == cal.DECODING["max_tokens"], body


@pytest.mark.skipif(
    shutil.which("uv") is None, reason="the `null` harness launches its program through uv"
)
@pytest.mark.parametrize("model", [cal.MODEL_A, MODEL_B], ids=["model_a", "model_b"])
def test_the_rest_of_the_declared_decoding_goes_out_unchanged(model: str) -> None:
    """The other three declared fields travel under their own names and values, so moving
    the limit's name moved nothing else."""
    body = one_episode_body(model)
    for field in ("temperature", "top_p", "reasoning_effort"):
        assert body[field] == cal.DECODING[field], (field, body)
