"""A stand-in for a vLLM OpenAI-compatible server, for the model B preparation tests.

It answers what the calibration driver asks a real server: `GET /health`, `GET /version`,
`GET /v1/models` and `POST /v1/chat/completions`.  The chat endpoint is stateless, so
concurrent episodes cannot confuse it: it finds the task by the conversation's first user
message, counts the assistant turns past any seeded history, and plays the task's reference
calls, then a plain-text reply.  Nothing leaves the loopback interface and no key is read.

It runs two ways: in-process on a thread (`serve_in_thread`), or as a script that takes the
`vllm serve` command line (`python fake_vllm.py serve <model> --port P --served-model-name N
...`), which is how the driver's `serve` step is exercised without a GPU.

Behaviour is set by environment variables, so a subprocess inherits it:

* `FAKE_MODE`: `reference` (default: the reference calls, so episodes pass), `no_call` (a
  plain reply on the first turn), `wrong` (one call with a wrong entry code, then a reply),
  `think` (a reply that opens with a `<think>` block).
* `FAKE_DELAY`: seconds to sleep before each chat answer (default 0).
* `FAKE_SEEDS`: comma-separated seeds whose tasks the server can play, at every arm.
* `FAKE_VERSION`: what `/version` reports (default `0.29.0+cu129`).
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DEFAULT_VERSION = "0.29.0+cu129"


def _first_user(messages: list[dict[str, Any]]) -> str | None:
    for message in messages:
        if message.get("role") == "user":
            content = message.get("content")
            return content if isinstance(content, str) else json.dumps(content)
    return None


Calls = list[tuple[str, dict[str, Any]]]
Registry = dict[str, list[tuple[list[str], Calls]]]


def _call_names(messages: list[dict[str, Any]]) -> list[str]:
    names = []
    for message in messages:
        if message.get("role") == "assistant":
            for call in message.get("tool_calls") or []:
                names.append(call.get("function", call).get("name"))
    return names


def build_registry(seeds: list[int]) -> Registry:
    """First user message -> every task that opens with it, as (the seeded history's call
    names, the reference calls).  A control arm opens with its plain arm's message and a
    seeded history, so the history is what tells them apart."""
    from poisson_tasks import calibration as cal
    from poisson_tasks.tasks import generate

    registry: Registry = {}
    for spec in cal.arm_specs():
        for seed in seeds:
            bundle = generate(spec, seed)
            prompt = bundle.prompt
            if isinstance(prompt, str):
                first, history = prompt, []
            else:
                messages = [dict(m) for m in prompt]
                first = _first_user(messages) or ""
                history = _call_names(messages)
            calls = [(name, dict(arguments)) for name, arguments in bundle.reference_calls]
            registry.setdefault(first, []).append((history, calls))
    return registry


def _match(registry: Registry, messages: list[dict[str, Any]]) -> tuple[int, Calls] | None:
    """The task whose seeded history is the longest prefix of the conversation's calls."""
    made = _call_names(messages)
    best: tuple[int, Calls] | None = None
    for history, calls in registry.get(_first_user(messages) or "", []):
        if made[: len(history)] == history and (best is None or len(history) > best[0]):
            best = (len(history), calls)
    return best


def _reply(body: dict[str, Any], registry: Registry, mode: str) -> dict[str, Any]:
    messages = body.get("messages") or []
    known = _match(registry, messages)
    assistants = sum(1 for m in messages if m.get("role") == "assistant")
    message: dict[str, Any] = {"role": "assistant", "content": "Done."}
    finish = "stop"
    if mode == "think":
        message = {"role": "assistant", "content": "<think>\nplanning\n</think>\n\nDone."}
    elif known is not None and mode in ("reference", "wrong"):
        history, calls = known
        step = assistants - history
        if mode == "wrong":
            calls = [(calls[0][0], {**calls[0][1], "entry_code": "not-the-code"})]
        if 0 <= step < len(calls):
            name, arguments = calls[step]
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": f"call_{step}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }],
            }
            finish = "tool_calls"
    prompt_tokens = max(1, len(json.dumps(messages)) // 4 + len(json.dumps(body.get("tools") or [])) // 4)
    return {
        "id": "chatcmpl-fake", "object": "chat.completion", "created": 0,
        "model": body.get("model"),
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 7,
                  "total_tokens": prompt_tokens + 7},
    }


def make_server(
    served: str, port: int = 0, host: str = "127.0.0.1"
) -> tuple[ThreadingHTTPServer, list[dict[str, Any]]]:
    seeds = [int(s) for s in os.environ.get("FAKE_SEEDS", "").split(",") if s.strip()]
    registry = build_registry(seeds) if seeds else {}
    mode = os.environ.get("FAKE_MODE", "reference")
    delay = float(os.environ.get("FAKE_DELAY", "0") or 0)
    version = os.environ.get("FAKE_VERSION", DEFAULT_VERSION)
    log: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def _send(self, status: int, payload: Any) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(200, {})
            elif self.path == "/version":
                self._send(200, {"version": version})
            elif self.path == "/v1/models":
                self._send(200, {"object": "list", "data": [{"id": served, "object": "model"}]})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            log.append(body)
            if self.path != "/v1/chat/completions":
                self._send(404, {"error": "not found"})
                return
            if body.get("model") != served:
                self._send(404, {"error": {"message": f"The model `{body.get('model')}` does "
                                           "not exist.", "code": 404}})
                return
            if delay:
                time.sleep(delay)
            self._send(200, _reply(body, registry, mode))

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server, log


@contextmanager
def serve_in_thread(served: str) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """The fake on a daemon thread; yields its `/v1` base URL and the request log."""
    server, log = make_server(served)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", log
    finally:
        server.shutdown()
        server.server_close()


def main(argv: list[str]) -> int:
    """`fake_vllm.py serve <model> [--flag value ...]`: the parts of `vllm serve` it needs."""
    if not argv or argv[0] != "serve":
        print("usage: fake_vllm.py serve <model> ...", file=sys.stderr)
        return 2
    args = argv[1:]
    port, host, served = 8000, "127.0.0.1", args[0] if args else "model"
    for i, token in enumerate(args):
        if token == "--port":
            port = int(args[i + 1])
        elif token == "--host":
            host = args[i + 1]
        elif token == "--served-model-name":
            served = args[i + 1]
    print("fake vllm argv: " + json.dumps(argv), flush=True)
    server, _ = make_server(served, port=port, host=host)
    print(f"fake vllm serving {served} on {host}:{port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
