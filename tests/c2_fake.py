"""A stand-in model for the version 2 card's run: plays any of its 56 arms' tasks, the four on
acme's tool file among them, and answers as each of the three providers does, so a run costs
nothing and what it should record is known before it starts.

It is `tests/k9_fake.py` grown, and it keeps that file's rules: a request is matched on the task's
system message, its user message, its seeded exchanges and its tool names, then on the calls made
and the replies seen so far; the task's reference calls are played in order, one per turn, then a
plain reply; which tasks fail is fixed by a hash of the arm and the seed.  What is new:

**The four own-tools arms.**  `landed:l0`, `landed:l1`, `lagged:g0` and `lagged:g1` are made by the
own-tools generator from `tests/fixtures/o1/acme-openai-chat.json` with the three reads declared
(`ACME_READS`), under the set name `ACME_NAME`, at the same seeds as the built-in arms.

**How a provider answers** (`Provider`).
* `answers_as`: the `model` every completion carries; `None` repeats the request's.
* `reasoning`: the reasoning tokens every completion reports in
  `usage.completion_tokens_details`; `None` sends no details at all, as Anthropic's
  OpenAI-compatible endpoint does.
* `refuses`: request fields the provider answers 400 to when they are present, as current Claude
  models do to `top_p`.
* `cached`: the cached tokens every completion reports in `usage.prompt_tokens_details`.

**Calls cut by the completion cap** (`length`: arm to seeds; no seeds, every seed).  The first
completion of such a task ends `finish_reason: "length"` with no tool call and no text, as a
reasoning model that spends its whole allowance thinking does.

As a process (`python tests/c2_fake.py serve <model> --port P --served-model-name N`, the
notebook driver's `vllm` stand-in) it reads `C2_FAKE_ARMS`, `C2_FAKE_SEEDS`, `C2_FAKE_BEHAVIOUR`,
`C2_FAKE_PROVIDER` (JSON) and `C2_FAKE_CACHE`, and appends one JSON line per chat request to the
file `C2_FAKE_LOG` names: the arm and seed it was played as, and the body without its
conversation.  Nothing here asserts anything.
"""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

if __name__ == "__main__":
    # run as the driver's `vllm`: the repository root is not on the path of a script in tests/
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.k9_fake import (  # noqa: E402
    COMPLETION_TOKENS,
    Behaviour,
    Entry,
    Registry,
    _canonical_arguments,
    _canonical_message,
    _first_user,
    _match,
    reply_for,
)

HERE = Path(__file__).resolve().parent
ACME_FILE = HERE / "fixtures" / "o1" / "acme-openai-chat.json"
ACME_NAME = "acme-openai-chat"
ACME_READS = ("get_order", "search_orders", "list_channels")
OWN_KNOBS = ("landed", "lagged")
VERSION = "0.31.2"
"""What the fake's `/version` answers unless `FAKE_VERSION` says otherwise.  Not a pin: the
tests read the version the driver expects from the driver's own pin and set `FAKE_VERSION`."""


def is_own(arm: str) -> bool:
    return arm.split(":", 1)[0] in OWN_KNOBS


def acme_toolset() -> Any:
    """acme's OpenAI tool file as the run reads it: the three reads declared, nothing else."""
    from poisson_tasks import own

    reading = own.read_tools(ACME_FILE.read_bytes(), format="auto", name=ACME_NAME)
    return own.apply_effects(reading.toolset, read=ACME_READS, write=())


def bundle_for(arm: str, seed: int, toolset: Any = None) -> Any:
    """The task of `arm` at `seed`, from the generator that makes it."""
    if is_own(arm):
        from poisson_tasks.knobs import ArmSpec
        from poisson_tasks.own import generator

        knob, level = arm.split(":", 1)
        spec = ArmSpec(
            knob=knob,
            level=int(level[1:]),
            control=None,
            strictness="strict",
            split="eval",
            generator_version=generator.GENERATOR_VERSION,
        )
        return generator.generate(
            acme_toolset() if toolset is None else toolset, spec, seed, flows=(), intents={}
        )
    from poisson_tasks import calibration_run as run
    from poisson_tasks.tasks import generate

    return generate(run.spec_for(arm), seed)


def build_registry(arms: Sequence[str], seeds: Sequence[int]) -> Registry:
    """Every task of `arms` at `seeds`, keyed by its system and user messages, in arm order."""
    registry: Registry = {}
    toolset = acme_toolset() if any(is_own(arm) for arm in arms) else None
    for arm in arms:
        for seed in seeds:
            bundle = bundle_for(arm, seed, toolset)
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
                    (str(name), _canonical_arguments(arguments))
                    for name, arguments in bundle.reference_calls
                ),
                replies=tuple(str(reply) for reply in bundle.reference_observations),
            )
            registry.setdefault((str(bundle.system_prompt), _first_user(messages)), []).append(
                entry
            )
    return registry


def cached_registry(arms: Sequence[str], seeds: Sequence[int], cache: Path | None) -> Registry:
    """`build_registry`, kept in `cache` between runs: the history arms take a second or two a
    task to make.  The file is keyed by the arms, the seeds, both generators' source and the
    tool file."""
    if cache is None:
        return build_registry(arms, seeds)
    import poisson_tasks.own.generator as own_module
    import poisson_tasks.tasks as tasks_module

    source = (
        Path(tasks_module.__file__).read_bytes()
        + Path(own_module.__file__).read_bytes()
        + ACME_FILE.read_bytes()
    )
    key = hashlib.sha256(json.dumps([list(arms), list(seeds)]).encode() + source).hexdigest()
    path = Path(cache).with_name(f"{Path(cache).name}-{key[:16]}.pickle")
    if path.exists():
        loaded: Registry = pickle.loads(path.read_bytes())
        return loaded
    registry = build_registry(arms, seeds)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(f".{os.getpid()}.part")
    partial.write_bytes(pickle.dumps(registry))
    os.replace(partial, path)
    return registry


@dataclass(frozen=True)
class Provider:
    answers_as: str | None = None
    reasoning: int | None = 20
    refuses: tuple[str, ...] = ()
    cached: int = 0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> Provider:
        return cls(
            answers_as=raw.get("answers_as"),
            reasoning=raw.get("reasoning", 20),
            refuses=tuple(raw.get("refuses") or ()),
            cached=int(raw.get("cached") or 0),
        )

    def as_mapping(self) -> dict[str, Any]:
        return asdict(self)


OPENAI_LIKE = Provider(reasoning=20)
"""OpenAI and vLLM: every completion reports its reasoning tokens."""
CLAUDE_LIKE = Provider(reasoning=None, refuses=("top_p", "reasoning_effort"))
"""Anthropic's OpenAI-compatible endpoint: no reasoning count in any answer, and a 400 to a
request that carries `top_p` or `reasoning_effort`.  The real endpoint ignores
`reasoning_effort`; the fake refuses it so that a run which sends it cannot pass unnoticed."""


@dataclass
class Play:
    """The whole of how the fake behaves: which tasks fail and how (`behaviour`), which are cut
    by the completion cap (`length`), and how the provider answers (`provider`)."""

    behaviour: Behaviour = field(default_factory=Behaviour)
    length: dict[str, frozenset[int]] = field(default_factory=dict)
    provider: Provider = OPENAI_LIKE

    def cut(self, arm: str, seed: int) -> bool:
        return arm in self.length and (not self.length[arm] or seed in self.length[arm])

    def as_env(self) -> dict[str, str]:
        behaviour = dict(self.behaviour.as_mapping())
        behaviour["length"] = {arm: sorted(seeds) for arm, seeds in self.length.items()}
        return {
            "C2_FAKE_BEHAVIOUR": json.dumps(behaviour),
            "C2_FAKE_PROVIDER": json.dumps(self.provider.as_mapping()),
        }

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Play:
        raw = json.loads(env.get("C2_FAKE_BEHAVIOUR") or "{}")
        return cls(
            behaviour=Behaviour.from_mapping(raw),
            length={
                str(arm): frozenset(int(seed) for seed in seeds)
                for arm, seeds in dict(raw.get("length") or {}).items()
            },
            provider=Provider.from_mapping(json.loads(env.get("C2_FAKE_PROVIDER") or "{}")),
        )


def completion(body: Mapping[str, Any], registry: Registry, play: Play) -> dict[str, Any]:
    """The completion the fake answers `body` with, as the provider would send it."""
    reply = reply_for(body, registry, play.behaviour)
    found = _match(registry, list(body.get("messages") or []), body.get("tools") or [])
    if found is None and play.provider.reasoning:
        # a request that is no task's (a driver's own check): a reasoning model shows its thinking
        reply["choices"][0]["message"]["reasoning_content"] = "The user wants one word."
    if found is not None:
        entry, calls, _replies = found
        if not calls and play.cut(entry.arm, entry.seed):
            reply["choices"] = [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": ""},
                    "finish_reason": "length",
                }
            ]
    usage = reply["usage"]
    if play.provider.reasoning is not None:
        usage["completion_tokens_details"] = {
            "reasoning_tokens": min(int(play.provider.reasoning), COMPLETION_TOKENS)
        }
    if play.provider.cached:
        usage["prompt_tokens_details"] = {
            "cached_tokens": min(int(play.provider.cached), int(usage["prompt_tokens"]))
        }
    if play.provider.answers_as is not None:
        reply["model"] = play.provider.answers_as
    return reply


class C2Fake:
    """The fake on 127.0.0.1, on a thread.  `served` is the one model name it answers to when it
    is set (as vLLM does); otherwise it answers to any.  `posts` holds every chat request's body
    in the order it arrived, and `matched` the arm and seed each was played as."""

    def __init__(
        self, registry: Registry, play: Play, *, served: str | None = None, port: int = 0
    ) -> None:
        self.registry = registry
        self.play = play
        self.served = served
        self.posts: list[dict[str, Any]] = []
        self.matched: list[tuple[str, int] | None] = []
        self.gets: list[str] = []
        self.on_first_chat: Any = None
        self.log: Path | None = None
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

            def do_GET(self) -> None:  # noqa: N802 - the base class's name
                path = self.path.split("?")[0].rstrip("/")
                with fake._lock:
                    fake.gets.append(path)
                if path == "/health":
                    self._send(200, {})
                elif path == "/version":
                    self._send(200, {"version": os.environ.get("FAKE_VERSION", VERSION)})
                elif fake.play.behaviour.refuse_key and "/models" in path:
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
                    names = [fake.served] if fake.served else ["c2-fake"]
                    self._send(
                        200,
                        {"object": "list", "data": [{"id": n, "object": "model"} for n in names]},
                    )
                elif "/models/" in path:
                    self._send(200, {"id": path.split("/models/", 1)[1], "object": "model"})
                else:
                    self._send(404, {"error": {"message": "not found"}})

            def do_POST(self) -> None:  # noqa: N802 - the base class's name
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                found = _match(
                    fake.registry, list(body.get("messages") or []), body.get("tools") or []
                )
                entry = None if found is None else found[0]
                with fake._lock:
                    first = not fake.posts
                    fake.posts.append(body)
                    fake.matched.append(None if entry is None else (entry.arm, entry.seed))
                    if fake.log is not None:
                        line = {
                            "arm": None if entry is None else entry.arm,
                            "seed": None if entry is None else entry.seed,
                            "sampling": {
                                key: value
                                for key, value in body.items()
                                if key not in ("messages", "tools", "tool_choice")
                            },
                        }
                        with fake.log.open("a", encoding="utf-8") as handle:
                            handle.write(json.dumps(line) + "\n")
                if first and fake.on_first_chat is not None:
                    fake.on_first_chat()
                if not self.path.rstrip("/").endswith("/chat/completions"):
                    self._send(404, {"error": {"message": "not found"}})
                    return
                refused = [name for name in fake.play.provider.refuses if name in body]
                if refused:
                    self._send(
                        400,
                        {
                            "error": {
                                "type": "invalid_request_error",
                                "message": f"`{refused[0]}` is not supported by this model.",
                            }
                        },
                    )
                    return
                if entry is not None and fake.play.behaviour.errs(entry.arm, entry.seed):
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
                self._send(200, completion(body, fake.registry, fake.play))

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

    def chats(self) -> int:
        with self._lock:
            return len(self.posts)

    def bodies(self, arm: str | None = None) -> list[dict[str, Any]]:
        """The chat requests' bodies, or those played as `arm`."""
        with self._lock:
            return [
                body
                for body, found in zip(self.posts, self.matched, strict=True)
                if arm is None or (found is not None and found[0] == arm)
            ]


@contextmanager
def running(
    arms: Sequence[str],
    seeds: Sequence[int],
    play: Play | None = None,
    *,
    cache: Path | None = None,
    port: int = 0,
    served: str | None = None,
) -> Iterator[C2Fake]:
    """The fake on a thread for the block's length, on `port` (a free one when 0)."""
    fake = C2Fake(cached_registry(arms, seeds, cache), play or Play(), served=served, port=port)
    fake.start()
    try:
        yield fake
    finally:
        fake.close()


def main(argv: list[str]) -> int:
    """`c2_fake.py serve <model> [--flag value ...]`: the parts of `vllm serve` it needs."""
    if not argv or argv[0] != "serve":
        print("usage: c2_fake.py serve <model> ...", file=sys.stderr)
        return 2
    args = argv[1:]
    port, served = 8000, args[0] if args else "model"
    for i, token in enumerate(args):
        if token == "--port":
            port = int(args[i + 1])
        elif token == "--served-model-name":
            served = args[i + 1]
    arms = json.loads(os.environ["C2_FAKE_ARMS"])
    seeds = json.loads(os.environ["C2_FAKE_SEEDS"])
    cache = os.environ.get("C2_FAKE_CACHE")
    registry = cached_registry(arms, seeds, Path(cache) if cache else None)
    print(f"c2 fake serving {served} on 127.0.0.1:{port}", flush=True)
    fake = C2Fake(registry, Play.from_env(os.environ), served=served, port=port)
    if os.environ.get("C2_FAKE_LOG"):
        fake.log = Path(os.environ["C2_FAKE_LOG"])
    fake.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
