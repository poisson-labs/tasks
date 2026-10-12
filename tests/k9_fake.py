"""A stand-in model for the knob probe: plays any probe arm's task, and fails the ones a behaviour
table says to, so a run costs nothing and its outcome is known before it starts.

It answers what the probe's two drivers ask of a model server: `GET /v1/models` and
`GET /v1/models/{id}` (the free key check), `GET /health` and `GET /version` (what the notebook's
driver asks a vLLM server), and `POST /v1/chat/completions`.  Nothing leaves the loopback interface.

**How it finds the task.**  The registry holds every task of the arms and seeds it is given, made by
the generator: its system message, its user message, its seeded exchanges, its tool names, its
reference calls and the replies they get.  A request is matched on the first four, then on the calls
made and the replies seen so far.  Two arms can open alike: `faults:f0` and `faults:f4` differ only in
the failures the tool server plans, `spread:p1` and `spread:p4` only in the parts of the code the
reads answer.  The first reply tells them apart, as it would for a real model.  Arms whose tasks are
identical in every way (B's own task under two knobs' names) are played as the first of them.

**How it plays.**  The task's reference calls in order, one per turn, then a plain reply.  A task the
behaviour fails stops one call short of the goal and replies, so the record never reaches it; a task
whose arm gives up after a fault replies at its first `unavailable`; an arm marked no-call replies at
once.  Which tasks fail is fixed by a hash of the arm and the seed, so a run repeats exactly and both
attempts at a task agree.

**What it costs.**  Each completion reports prompt tokens of a quarter of the request's characters
and `COMPLETION_TOKENS` completion tokens, none cached.

**The behaviour** is a mapping: `fail` (arm to the share of its tasks that fail), `fail_at` (arm to
the seeds whose tasks fail), `give_up` (arm to
the share of its tasks that give up at the first fault), `no_call` (arms that never call a tool),
`error` (arm to the seeds whose completions are all 500s, an instrument failure; no seeds, every
seed) and `refuse_key` (the key
check answers 401).  `on_first_chat`, when set, is called once, before the first completion is
answered.  As a process (`python tests/k9_fake.py serve <model>
--port P --served-model-name N`, the notebook driver's `vllm` stand-in) it reads the behaviour, the
arms and the seeds from `K9_FAKE_BEHAVIOUR`, `K9_FAKE_ARMS` and `K9_FAKE_SEEDS` (JSON), and keeps its
registry in the file `K9_FAKE_CACHE` names, when it names one.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

COMPLETION_TOKENS = 60
VERSION = "0.29.0+cu129"
CALL_PREFIX = "k9-call-"

Call = tuple[str, str]
"""A tool call as the fake compares it: the tool's name and its arguments as canonical JSON."""


def _canonical_arguments(arguments: Any) -> str:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return str(arguments)
    return json.dumps(arguments, sort_keys=True)


def _canonical_message(message: Mapping[str, Any]) -> tuple[Any, ...]:
    calls = tuple(
        (
            str(call.get("function", call).get("name")),
            _canonical_arguments(call.get("function", call).get("arguments")),
        )
        for call in message.get("tool_calls") or []
    )
    content = message.get("content")
    return (message.get("role"), content if isinstance(content, str) else None, calls)


@dataclass(frozen=True)
class Entry:
    arm: str
    seed: int
    prompt: tuple[tuple[Any, ...], ...]
    tools: tuple[str, ...]
    calls: tuple[Call, ...]
    replies: tuple[str, ...]


Registry = dict[tuple[str, str], list[Entry]]


def _first_user(messages: Sequence[Mapping[str, Any]]) -> str:
    for message in messages:
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            return str(message["content"])
    return ""


def build_registry(arms: Sequence[str], seeds: Sequence[int]) -> Registry:
    """Every task of `arms` at `seeds`, keyed by its system and user messages, in arm order."""
    from poisson_tasks.arms import arm_from_id
    from poisson_tasks.tasks import generate

    registry: Registry = {}
    for arm in arms:
        spec = arm_from_id(arm, strictness="strict", split="eval", generator_version="1")
        for seed in seeds:
            bundle = generate(spec, seed)
            if isinstance(bundle.prompt, str):
                messages: list[dict[str, Any]] = [{"role": "user", "content": bundle.prompt}]
            else:
                messages = [dict(message) for message in bundle.prompt]
            entry = Entry(
                arm=arm,
                seed=seed,
                prompt=tuple(_canonical_message(message) for message in messages),
                tools=tuple(sorted(str(tool["name"]) for tool in bundle.tools)),
                calls=tuple(
                    (name, _canonical_arguments(arguments))
                    for name, arguments in bundle.reference_calls
                ),
                replies=tuple(bundle.reference_observations),
            )
            registry.setdefault((bundle.system_prompt, _first_user(messages)), []).append(entry)
    return registry


def cached_registry(arms: Sequence[str], seeds: Sequence[int], cache: Path | None) -> Registry:
    """`build_registry`, kept in `cache` between runs: the history arms take a second or two a
    task to make.  The file is keyed by the arms, the seeds and the generator's own source."""
    if cache is None:
        return build_registry(arms, seeds)
    import poisson_tasks.tasks as tasks_module

    source = Path(tasks_module.__file__).read_bytes()
    key = hashlib.sha256(json.dumps([list(arms), list(seeds)]).encode() + source).hexdigest()
    path = Path(cache).with_name(f"{Path(cache).name}-{key[:16]}.pickle")
    if path.exists():
        loaded: Registry = pickle.loads(path.read_bytes())
        return loaded
    registry = build_registry(arms, seeds)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(registry))
    return registry


def _share(arm: str, seed: int, what: str) -> float:
    digest = hashlib.sha256(f"k9-fake/{what}/{arm}/{seed}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


@dataclass
class Behaviour:
    fail: dict[str, float] = field(default_factory=dict)
    fail_at: dict[str, frozenset[int]] = field(default_factory=dict)
    give_up: dict[str, float] = field(default_factory=dict)
    no_call: frozenset[str] = frozenset()
    error: dict[str, frozenset[int]] = field(default_factory=dict)
    refuse_key: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> Behaviour:
        return cls(
            fail={str(k): float(v) for k, v in dict(raw.get("fail") or {}).items()},
            fail_at={
                str(k): frozenset(int(s) for s in v)
                for k, v in dict(raw.get("fail_at") or {}).items()
            },
            give_up={str(k): float(v) for k, v in dict(raw.get("give_up") or {}).items()},
            no_call=frozenset(str(arm) for arm in raw.get("no_call") or ()),
            error={
                str(k): frozenset(int(s) for s in v)
                for k, v in dict(raw.get("error") or {}).items()
            },
            refuse_key=bool(raw.get("refuse_key", False)),
        )

    def as_mapping(self) -> dict[str, Any]:
        return {
            "fail": dict(self.fail),
            "fail_at": {arm: sorted(seeds) for arm, seeds in self.fail_at.items()},
            "give_up": dict(self.give_up),
            "no_call": sorted(self.no_call),
            "error": {arm: sorted(seeds) for arm, seeds in self.error.items()},
            "refuse_key": self.refuse_key,
        }

    def fails(self, arm: str, seed: int) -> bool:
        return seed in self.fail_at.get(arm, frozenset()) or _share(
            arm, seed, "fail"
        ) < self.fail.get(arm, 0.0)

    def errs(self, arm: str, seed: int) -> bool:
        return arm in self.error and (not self.error[arm] or seed in self.error[arm])

    def gives_up(self, arm: str, seed: int) -> bool:
        return _share(arm, seed, "give-up") < self.give_up.get(arm, 0.0)


def _turns(messages: Sequence[Mapping[str, Any]], start: int) -> tuple[list[Call], list[str]]:
    """The calls made and the replies seen after the task's own prompt."""
    calls: list[Call] = []
    replies: list[str] = []
    for message in messages[start:]:
        if message.get("role") == "assistant":
            for call in message.get("tool_calls") or []:
                function = call.get("function", call)
                calls.append(
                    (str(function.get("name")), _canonical_arguments(function.get("arguments")))
                )
        elif message.get("role") == "tool":
            content = message.get("content")
            replies.append(content if isinstance(content, str) else json.dumps(content))
    return calls, replies


def _match(
    registry: Registry, messages: Sequence[Mapping[str, Any]], tools: Sequence[Any]
) -> tuple[Entry, list[Call], list[str]] | None:
    system = ""
    rest = list(messages)
    if rest and rest[0].get("role") == "system":
        system = str(rest[0].get("content") or "")
        rest = rest[1:]
    names = tuple(sorted(str((tool.get("function") or tool).get("name")) for tool in tools or ()))
    canonical = [_canonical_message(message) for message in rest]
    for entry in registry.get((system, _first_user(rest)), []):
        if entry.tools != names or tuple(canonical[: len(entry.prompt)]) != entry.prompt:
            continue
        calls, replies = _turns(rest, len(entry.prompt))
        if (
            list(entry.calls[: len(calls)]) == calls
            and list(entry.replies[: len(replies)]) == replies
        ):
            return entry, calls, replies
    return None


def _entries(fake: K9Fake, body: Mapping[str, Any]) -> list[Entry]:
    found = _match(fake.registry, list(body.get("messages") or []), body.get("tools") or [])
    return [] if found is None else [found[0]]


def reply_for(body: Mapping[str, Any], registry: Registry, behaviour: Behaviour) -> dict[str, Any]:
    """The completion the fake answers `body` with."""
    messages = list(body.get("messages") or [])
    found = _match(registry, messages, body.get("tools") or [])
    message: dict[str, Any] = {"role": "assistant", "content": "ready"}
    finish = "stop"
    if found is not None:
        entry, calls, replies = found
        made = len(calls)
        message = {"role": "assistant", "content": "Done."}
        stop = (
            (made == 0 and entry.arm in behaviour.no_call)
            or (
                bool(replies)
                and replies[-1].split()[1:2] == ["unavailable"]
                and behaviour.gives_up(entry.arm, entry.seed)
            )
            or made >= len(entry.calls)
            or (made == len(entry.calls) - 1 and behaviour.fails(entry.arm, entry.seed))
        )
        if not stop:
            name, arguments = entry.calls[made]
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"{CALL_PREFIX}{made}",
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                ],
            }
            finish = "tool_calls"
    prompt_tokens = max(
        1, (len(json.dumps(messages)) + len(json.dumps(body.get("tools") or []))) // 4
    )
    return {
        "id": "chatcmpl-k9",
        "object": "chat.completion",
        "created": 0,
        "model": body.get("model"),
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": COMPLETION_TOKENS,
            "total_tokens": prompt_tokens + COMPLETION_TOKENS,
        },
    }


class K9Fake:
    """The fake on 127.0.0.1, on a thread.  `served` is the one model name it answers to when
    it is set (as vLLM does); otherwise it answers to any."""

    def __init__(
        self,
        registry: Registry,
        behaviour: Behaviour,
        *,
        served: str | None = None,
        port: int = 0,
    ) -> None:
        self.registry = registry
        self.behaviour = behaviour
        self.served = served
        self.posts: list[dict[str, Any]] = []
        self.gets: list[str] = []
        self.on_first_chat: Callable[[], None] | None = None
        self._lock = threading.Lock()
        fake = self

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
                path = self.path.split("?")[0].rstrip("/")
                with fake._lock:
                    fake.gets.append(path)
                if path == "/health":
                    self._send(200, {})
                elif path == "/version":
                    self._send(200, {"version": os.environ.get("FAKE_VERSION", VERSION)})
                elif fake.behaviour.refuse_key and "/models" in path:
                    self._send(
                        401,
                        {
                            "error": {
                                "message": "Incorrect API key provided.",
                                "type": "invalid_request_error",
                                "code": "invalid_api_key",
                            }
                        },
                    )
                elif path.endswith("/models"):
                    names = [fake.served] if fake.served else ["k9-fake"]
                    self._send(
                        200,
                        {"object": "list", "data": [{"id": n, "object": "model"} for n in names]},
                    )
                elif "/models/" in path:
                    self._send(200, {"id": path.split("/models/", 1)[1], "object": "model"})
                else:
                    self._send(404, {"error": {"message": "not found"}})

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                with fake._lock:
                    first = not fake.posts
                    fake.posts.append(body)
                if first and fake.on_first_chat is not None:
                    fake.on_first_chat()
                if not self.path.rstrip("/").endswith("/chat/completions"):
                    self._send(404, {"error": {"message": "not found"}})
                    return
                if any(
                    fake.behaviour.errs(entry.arm, entry.seed) for entry in _entries(fake, body)
                ):
                    self._send(500, {"error": {"message": "the server failed", "code": 500}})
                    return
                if fake.served is not None and body.get("model") != fake.served:
                    self._send(
                        404,
                        {
                            "error": {
                                "message": f"The model `{body.get('model')}` does not exist.",
                                "code": 404,
                            }
                        },
                    )
                    return
                self._send(200, reply_for(body, fake.registry, fake.behaviour))

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._server.daemon_threads = True
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def start(self) -> str:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.base_url

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(10)

    def chat_calls(self) -> int:
        with self._lock:
            return len(self.posts)


@contextmanager
def running(
    arms: Sequence[str],
    seeds: Sequence[int],
    behaviour: Behaviour,
    *,
    cache: Path | None = None,
    port: int = 0,
) -> Iterator[K9Fake]:
    """The fake on a thread for the block's length, on `port` (a free one when 0)."""
    fake = K9Fake(cached_registry(arms, seeds, cache), behaviour, port=port)
    fake.start()
    try:
        yield fake
    finally:
        fake.close()


def main(argv: list[str]) -> int:
    """`k9_fake.py serve <model> [--flag value ...]`: the parts of `vllm serve` it needs."""
    if not argv or argv[0] != "serve":
        print("usage: k9_fake.py serve <model> ...", file=sys.stderr)
        return 2
    args = argv[1:]
    port, served = 8000, args[0] if args else "model"
    for i, token in enumerate(args):
        if token == "--port":
            port = int(args[i + 1])
        elif token == "--served-model-name":
            served = args[i + 1]
    arms = json.loads(os.environ["K9_FAKE_ARMS"])
    seeds = json.loads(os.environ["K9_FAKE_SEEDS"])
    behaviour = Behaviour.from_mapping(json.loads(os.environ.get("K9_FAKE_BEHAVIOUR") or "{}"))
    cache = os.environ.get("K9_FAKE_CACHE")
    registry = cached_registry(arms, seeds, Path(cache) if cache else None)
    print(f"k9 fake serving {served} on 127.0.0.1:{port}", flush=True)
    K9Fake(registry, behaviour, served=served, port=port).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
