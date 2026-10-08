"""The fixture model: a local OpenAI-compatible server that plays a task's reference policy.

It stands in for a provider wherever a run would cost money: in the tests of `poisson_tasks.runs`
and, later, in the clean-install check, which runs the README's paid commands against it.  It is
the standard library only, and it never connects anywhere.

**What it serves.**  `GET <prefix>/models`, `GET <prefix>/models/{id}` and
`POST <prefix>/chat/completions`, under any prefix (`/v1` in practice): the key check's free
requests and the run's model calls.

**How it plays.**  It reads the task from the conversation it is sent, never from the generator:
the record id, its ledger, the stage ladder, the goal stage and the entry code, from the user's
request.  It calls the first stage's tool with the entry code, each later stage's tool with the
chain token the last tool reply returned, and replies in plain words once the goal stage is
reached.  So a task of depth d takes d + 1 model calls, its structural minimum.

**What every answer costs.**  Each successful completion reports the same usage: `PROMPT_TOKENS`
prompt tokens, `CACHED_TOKENS` of them read from the cache, and `COMPLETION_TOKENS` completion
tokens.  An error answer reports none.  So a test knows to the token what each call costs.

**The model's name selects a mode**, for the refusal paths and the stops:

| name | what it does |
|---|---|
| `fixture-reference`, and any name not below | the reference policy |
| `fixture-overshoot` | the reference policy, then one stage past the goal, then a reply |
| `fixture-silent` | a reply with no tool call, at once |
| `fixture-slow` | the reference policy, each completion held back `slow_seconds`; a call whose client has gone by then is neither answered nor counted |
| `fixture-401` | 401 on everything, quoting the key it was sent back, whole and masked |
| `fixture-429` | 429 `rate_limit_exceeded` on every completion |
| `fixture-429-after-<n>` | the reference policy for the first `n` completions, then 429 as above |
| `fixture-429-quota` | 429 `insufficient_quota`, naming the plan and billing |
| `fixture-402` | 402, the account out of credit |

A key check (`GET .../models/{id}`) answers 200 for every name but `fixture-401`.

**What it records.**  Every request: its method, its path, its headers and its body.  Each
completion it served with a 200 is a call; a call whose conversation holds no turn the fixture
made is the start of an episode.  (A control arm's task can open with a seeded history of other
tools' calls; the fixture's own tool calls carry ids starting `CALL_ID_PREFIX`, and only those
count as the policy's progress.)  `served()` is the usage of every call served.

**As a process** (the clean-install check): `python tests/fixtures/model_server.py --port-file F`
binds a free loopback port, writes it to `F`, appends every request to `--log` as JSON Lines, and
serves until it is stopped.
"""

from __future__ import annotations

import argparse
import json
import re
import select
import socket
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PROMPT_TOKENS = 1000
"""Prompt tokens each completion reports, cached ones included, as OpenAI reports them."""
CACHED_TOKENS = 400
"""Of `PROMPT_TOKENS`, the ones read from the cache."""
COMPLETION_TOKENS = 100
"""Completion tokens each completion reports."""

DEFAULT_SLOW_SECONDS = 2.0

RATE_LIMIT_MESSAGE = (
    "Rate limit reached for {model} in organization org-fixture on requests per min (RPM): "
    "Limit 3, Used 3, Requested 1. Please try again in 20s."
)
QUOTA_MESSAGE = (
    "You exceeded your current quota, please check your plan and billing details."
)
CREDIT_MESSAGE = "Your account has no credit left. Add credit to continue."

_RECORD = re.compile(r'record "([^"]+)"')
_LEDGER = re.compile(r"of the (\w+) ledger")
_LADDER = re.compile(r"Stage ladder: ([a-z ]+?)\.")
_GOAL = re.compile(r"through (\w+), and no further")
_ENTRY = re.compile(r'entry code "([^"]+)"')
_AFTER = re.compile(r"^fixture-429-after-(\d+)$")

CALL_ID_PREFIX = "fixture-call-"


def usage_per_call() -> dict[str, int]:
    """One call's usage as `verifiers` records it: the cached tokens split out of the prompt."""
    return {
        "prompt_tokens": PROMPT_TOKENS - CACHED_TOKENS,
        "cached_input_tokens": CACHED_TOKENS,
        "completion_tokens": COMPLETION_TOKENS,
    }


@dataclass
class Seen:
    """One request, as the server received it."""

    method: str
    path: str
    headers: dict[str, str]
    body: Any
    at: float = 0.0
    """When it arrived, by `time.time()`."""


@dataclass
class _Task:
    record: str
    ledger: str
    stages: list[str]
    entry: str


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text", "")) for part in content if isinstance(part, Mapping)
        )
    return ""


def _task_from(messages: list[Any]) -> _Task | None:
    """The task the conversation's user request states, or `None` when it states none."""
    for message in messages:
        if not isinstance(message, Mapping) or message.get("role") != "user":
            continue
        text = _text(message.get("content"))
        found = [pattern.search(text) for pattern in (_RECORD, _LEDGER, _LADDER, _GOAL, _ENTRY)]
        if not all(found):
            continue
        record, ledger, ladder, goal, entry = (match.group(1) for match in found if match)
        rungs = [rung.strip() for rung in ladder.split(" then ")]
        if goal not in rungs:
            return None
        return _Task(record, ledger, rungs[: rungs.index(goal) + 1], entry)
    return None


def _own_calls(messages: list[Any]) -> list[str]:
    """The ids of the tool calls the fixture made in this conversation, in order."""
    return [
        str(call.get("id"))
        for message in messages
        if isinstance(message, Mapping) and message.get("role") == "assistant"
        for call in message.get("tool_calls") or []
        if isinstance(call, Mapping) and str(call.get("id", "")).startswith(CALL_ID_PREFIX)
    ]


def _tool_calls_so_far(messages: list[Any]) -> int:
    return len(_own_calls(messages))


def _last_token(messages: list[Any]) -> str | None:
    """The chain token the reply to the fixture's last tool call returned: its last word, when
    its status is ok."""
    own = _own_calls(messages)
    if not own:
        return None
    for message in reversed(messages):
        if (isinstance(message, Mapping) and message.get("role") == "tool"
                and message.get("tool_call_id") == own[-1]):
            words = _text(message.get("content")).split()
            if len(words) >= 3 and words[1] == "ok":
                return words[-1]
            return None
    return None


def _next_move(task: _Task, messages: list[Any], *, overshoot: bool) -> tuple[str, dict[str, str]] | None:
    """The reference policy's next tool call, or `None` for its reply."""
    done = _tool_calls_so_far(messages)
    if done == 0:
        return f"submit_{task.stages[0]}_{task.ledger}", {
            "record_id": task.record, "entry_code": task.entry,
        }
    token = _last_token(messages)
    if token is None:
        return None
    stages = list(task.stages)
    if overshoot:
        stages = stages + ["__past__"]
    if done >= len(stages):
        return None
    stage: str | None = stages[done]
    if stage == "__past__":
        stage = _stage_after(messages, task)
        if stage is None:
            return None
    return f"submit_{stage}_{task.ledger}", {"record_id": task.record, "chain_token": token}


def _stage_after(messages: list[Any], task: _Task) -> str | None:
    """The rung after the goal on the full ladder, read again from the user's request."""
    for message in messages:
        if isinstance(message, Mapping) and message.get("role") == "user":
            match = _LADDER.search(_text(message.get("content")))
            if match:
                rungs = [rung.strip() for rung in match.group(1).split(" then ")]
                position = rungs.index(task.stages[-1]) + 1
                return rungs[position] if position < len(rungs) else None
    return None


def _masked(key: str) -> str:
    return key[:8] + "*" * max(len(key) - 12, 0) + key[-4:] if len(key) > 12 else "****"


@dataclass
class FixtureModel:
    """The fixture model on 127.0.0.1, on a free port.  `start()` returns its base URL."""

    slow_seconds: float = DEFAULT_SLOW_SECONDS
    log_path: Path | None = None
    requests: list[Seen] = field(default_factory=list)
    _calls: list[str] = field(default_factory=list)
    _starts: list[str] = field(default_factory=list)
    _completions: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._closing = threading.Event()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # -- what a test reads -------------------------------------------------------------

    @property
    def port(self) -> int:
        assert self._server is not None, "the fixture model is not started"
        return int(self._server.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def calls(self, model: str | None = None) -> int:
        """Completions served with a 200, for one model's name or for all."""
        with self._lock:
            return sum(1 for name in self._calls if model is None or name == model)

    def episodes_started(self, model: str | None = None) -> int:
        """Completions served whose conversation held no assistant turn yet."""
        with self._lock:
            return sum(1 for name in self._starts if model is None or name == model)

    def served(self) -> dict[str, int]:
        """The usage of every call served, summed as `verifiers` records it."""
        n = self.calls()
        return {name: value * n for name, value in usage_per_call().items()}

    def forget(self) -> None:
        """Start every mode's count of completions again, as a fixture just started would; the
        record of requests is kept."""
        with self._lock:
            self._completions.clear()

    def posts(self) -> list[Seen]:
        with self._lock:
            return [seen for seen in self.requests if seen.method == "POST"]

    def methods(self) -> set[str]:
        with self._lock:
            return {seen.method for seen in self.requests}

    # -- running -----------------------------------------------------------------------

    def start(self) -> str:
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                pass

            def _read(self) -> Any:
                length = int(self.headers.get("content-length") or 0)
                if not length:
                    return None
                raw = self.rfile.read(length)
                try:
                    return json.loads(raw)
                except ValueError:
                    return raw.decode("utf-8", "replace")

            def _send(self, status: int, body: Any) -> None:
                data = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _record(self, body: Any) -> None:
                seen = Seen(
                    method=self.command, path=self.path,
                    headers={k.lower(): v for k, v in self.headers.items()}, body=body,
                    at=time.time(),
                )
                with fixture._lock:
                    fixture.requests.append(seen)
                    if fixture.log_path is not None:
                        with fixture.log_path.open("a", encoding="utf-8") as handle:
                            handle.write(json.dumps(seen.__dict__) + "\n")

            def do_GET(self) -> None:
                self._record(None)
                path = self.path.split("?")[0].rstrip("/")
                key = _bearer(self.headers)
                if path.endswith("/models"):
                    self._send(200, {"object": "list", "data": [
                        {"id": name, "object": "model", "owned_by": "fixture"}
                        for name in ("fixture-reference", "fixture-slow", "fixture-overshoot",
                                     "fixture-silent")
                    ]})
                    return
                marker = "/models/"
                if marker in path:
                    name = path.split(marker, 1)[1]
                    if name == "fixture-401":
                        self._send(401, _refused(key))
                        return
                    self._send(200, {"id": name, "object": "model", "owned_by": "fixture"})
                    return
                self._send(404, {"error": {"message": "not found", "type": "invalid_request_error",
                                           "code": None}})

            def do_POST(self) -> None:
                body = self._read()
                self._record(body)
                if not self.path.split("?")[0].rstrip("/").endswith("/chat/completions") or (
                        not isinstance(body, Mapping)):
                    self._send(404, {"error": {"message": "not found",
                                               "type": "invalid_request_error", "code": None}})
                    return
                if body.get("model") == "fixture-slow" and not fixture._hold(self.connection):
                    return
                status, answer = fixture._answer(body, _bearer(self.headers))
                self._send(status, answer)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(
            target=self._server.serve_forever, args=(0.05,), daemon=True
        )
        self._thread.start()
        return self.base_url

    def close(self) -> None:
        self._closing.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(10)

    def __enter__(self) -> FixtureModel:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- the answers -------------------------------------------------------------------

    def _hold(self, connection: socket.socket) -> bool:
        """fixture-slow's wait.  False, and the call is neither answered nor counted, when the
        fixture is closing or the client has gone (it closed the connection) before the wait
        ended: a call nobody receives was never served."""
        deadline = time.monotonic() + self.slow_seconds
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return True
            if self._closing.is_set():
                return False
            readable, _, _ = select.select([connection], [], [], min(left, 0.05))
            if readable:
                try:
                    if connection.recv(1, socket.MSG_PEEK) == b"":
                        return False
                except OSError:
                    return False

    def _answer(self, body: Mapping[str, Any], key: str) -> tuple[int, dict[str, Any]]:
        model = str(body.get("model", ""))
        messages = list(body.get("messages") or [])
        if model == "fixture-401":
            return 401, _refused(key)
        if model == "fixture-402":
            return 402, {"error": {"message": CREDIT_MESSAGE, "type": "insufficient_balance",
                                   "code": "insufficient_balance"}}
        if model == "fixture-429-quota":
            return 429, {"error": {"message": QUOTA_MESSAGE, "type": "insufficient_quota",
                                   "code": "insufficient_quota"}}
        after = _AFTER.match(model)
        with self._lock:
            served = self._completions.get(model, 0)
        if model == "fixture-429" or (after is not None and served >= int(after.group(1))):
            return 429, {"error": {"message": RATE_LIMIT_MESSAGE.format(model=model),
                                   "type": "requests", "code": "rate_limit_exceeded"}}
        task = _task_from(messages)
        move = None
        if model != "fixture-silent" and task is not None:
            move = _next_move(task, messages, overshoot=model == "fixture-overshoot")
        with self._lock:
            self._completions[model] = served + 1
            self._calls.append(model)
            if not _own_calls(messages):
                self._starts.append(model)
            number = len(self._calls)
        if move is None:
            message: dict[str, Any] = {"role": "assistant", "content": "Done."}
            finish = "stop"
        else:
            name, arguments = move
            message = {"role": "assistant", "content": None, "tool_calls": [{
                "id": f"{CALL_ID_PREFIX}{number}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }]}
            finish = "tool_calls"
        return 200, {
            "id": f"chatcmpl-fixture-{number}", "object": "chat.completion", "created": 0,
            "model": model,
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {
                "prompt_tokens": PROMPT_TOKENS, "completion_tokens": COMPLETION_TOKENS,
                "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS,
                "prompt_tokens_details": {"cached_tokens": CACHED_TOKENS},
            },
        }


def _bearer(headers: Any) -> str:
    value = str(headers.get("Authorization") or headers.get("authorization") or "")
    return value[len("Bearer "):] if value.startswith("Bearer ") else value


def _refused(key: str) -> dict[str, Any]:
    """OpenAI's answer to a refused key, which quotes the key back masked; this one also quotes
    it whole, so a build that passes a provider's words on is caught."""
    return {"error": {
        "message": f"Incorrect API key provided: {_masked(key)} (sent as {key}). You can find "
                   "your API key at https://platform.openai.com/account/api-keys.",
        "type": "invalid_request_error", "param": None, "code": "invalid_api_key",
    }}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="model_server.py",
        description="The fixture model: an OpenAI-compatible server on loopback that plays each "
                    "task's reference policy, for tests and the clean-install check.",
    )
    parser.add_argument("--port-file", type=Path, required=True,
                        help="write the bound port here once serving")
    parser.add_argument("--log", type=Path, default=None,
                        help="append every request here as JSON Lines (default: none)")
    parser.add_argument("--slow-seconds", type=float, default=DEFAULT_SLOW_SECONDS,
                        help=f"how long fixture-slow holds each answer "
                             f"(default: {DEFAULT_SLOW_SECONDS})")
    args = parser.parse_args(argv)
    fixture = FixtureModel(slow_seconds=args.slow_seconds, log_path=args.log)
    fixture.start()
    args.port_file.write_text(str(fixture.port), encoding="utf-8")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        fixture.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
