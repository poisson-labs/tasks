"""Fake providers and a network guard for the `tests/test_fd2_*.py` tests: nothing in them leaves
this machine.

**`FakeServer`** answers HTTP on loopback with whatever replies a test routes to its paths, and
records every request it is sent: the method, the path, the headers, and the request's head as
text, so a test can look for a key's bytes in it.  A path no test routed answers 418, a status no
provider sends, so a request to the wrong path is never read as one of the statuses under test.
`HANG` as a reply accepts the request and never answers, until the server is closed.

**`network_guard`** records every socket event the process raises while it is active, through an
audit hook, and stops any of them that would leave the machine:
- a name lookup for anything but a loopback address, `localhost` or the fake domain fails as an
  unknown name (`socket.gaierror`);
- a connection to anything but a loopback address is refused (`ConnectionRefusedError`).
Names in the fake domain, `tasks-fake.test` and any name under it, resolve to 127.0.0.1.  So a
test can give an endpoint a host that is not loopback by its name (`http://tasks-fake.test:P`)
and still have it answered by a fake on this machine, if the code under test connects at all.

**`recording_writes`** records every path opened for writing while it is active, through the same
hook.

The audit hook is installed once, when this module is imported, and does nothing while neither is
active, so other tests in the same process are not affected by it.
"""

from __future__ import annotations

import ipaddress
import json
import os
import socket
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

FAKE_DOMAIN = "tasks-fake.test"
HANG = object()

Reply = tuple[int, Any]


@dataclass
class Request:
    method: str
    path: str
    headers: dict[str, str]
    head: str


@dataclass
class FakeServer:
    """One fake provider on 127.0.0.1, on a free port.  `routes` maps a path to a reply: a status
    and a body (a dict or list is sent as JSON, a str as text), or `HANG`."""

    routes: dict[str, Any] = field(default_factory=dict)
    requests: list[Request] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._stop = threading.Event()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _any(self) -> None:
                server.requests.append(Request(
                    method=self.command,
                    path=self.path,
                    headers={k.lower(): v for k, v in self.headers.items()},
                    head=self.requestline + "\n" + self.headers.as_string(),
                ))
                length = int(self.headers.get("content-length") or 0)
                if length:
                    self.rfile.read(length)
                reply = server.routes.get(self.path.split("?")[0], (418, {"unrouted": self.path}))
                if reply is HANG:
                    server._stop.wait(30)
                    return
                status, body = reply
                data = (json.dumps(body) if not isinstance(body, str) else body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json" if not isinstance(
                    body, str) else "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _any

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, args=(0.05,),
                                        daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def netloc(self) -> str:
        return f"127.0.0.1:{self.port}"

    @property
    def url(self) -> str:
        return f"http://{self.netloc}"

    def route(self, path: str, status: int, body: Any = None) -> FakeServer:
        self.routes[path] = (status, {} if body is None else body)
        return self

    def hang(self, path: str) -> FakeServer:
        self.routes[path] = HANG
        return self

    def seen(self) -> str:
        """Every request's head, as one text."""
        return "\n".join(request.head for request in self.requests)

    def close(self) -> None:
        self._stop.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(10)


def free_port() -> int:
    """A loopback port nothing listens on: bound, then closed."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


# --------------------------------------------------------------------------
# the guard
# --------------------------------------------------------------------------

_ACTIVE: list[list[tuple[str, Any]]] = []


def _loopback(host: Any) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    if not isinstance(host, str):
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


_WRITES: list[list[str]] = []
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


def _hook(event: str, args: tuple[Any, ...]) -> None:
    if _WRITES and event == "open":
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & _WRITE_FLAGS):
            _WRITES[-1].append(os.fsdecode(args[0]) if isinstance(args[0], (str, bytes)) else "")
        return
    if not _ACTIVE or not event.startswith("socket."):
        return
    events = _ACTIVE[-1]
    if event == "socket.getaddrinfo":
        host = args[0].decode() if isinstance(args[0], bytes) else args[0]
        events.append(("getaddrinfo", host))
        if not _loopback(host):
            raise socket.gaierror(socket.EAI_NONAME, f"{host}: the test allows no network")
    elif event == "socket.connect":
        address = args[1]
        events.append(("connect", address))
        if not (isinstance(address, tuple) and _loopback(address[0])):
            raise ConnectionRefusedError(f"{address}: the test allows no network")
    else:
        events.append((event, None))


sys.addaudithook(_hook)


@contextmanager
def network_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, Any]]]:
    """Record every socket event while active, and keep every one of them on this machine."""
    real = socket.getaddrinfo

    def lookup(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        name = host.decode() if isinstance(host, bytes) else host
        if isinstance(name, str) and (name == FAKE_DOMAIN or name.endswith("." + FAKE_DOMAIN)):
            return real("127.0.0.1", port, *args, **kwargs)
        return real(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    events: list[tuple[str, Any]] = []
    _ACTIVE.append(events)
    try:
        yield events
    finally:
        _ACTIVE.remove(events)


@contextmanager
def recording_writes() -> Iterator[list[str]]:
    """Every path opened for writing while active."""
    paths: list[str] = []
    _WRITES.append(paths)
    try:
        yield paths
    finally:
        _WRITES.remove(paths)


def connections(events: list[tuple[str, Any]]) -> set[int]:
    """The ports of every connection the guard saw made."""
    return {address[1] for kind, address in events if kind == "connect"}


# --------------------------------------------------------------------------
# a key nothing should ever show
# --------------------------------------------------------------------------

# Each key's part after the prefix is drawn from seven capital letters, the two keys from two
# sets that share none, so no four of them in a row occur in any text the code under test could
# write for itself, nor in the other key.
KEY_BODY = "QZXJVKWQXZJKVWZQJXKVWJZQXVKWJQZXKVJWQZKXJVWQZJXK"
SENTINEL = "sk-proj-" + KEY_BODY
OTHER_BODY = "PBPGYMHGBPBHBGPPFHHMPFMYMBBPFYBMHYYGGFGPGYBFFPGH"
OTHER_SENTINEL = "sk-proj-" + OTHER_BODY


def leaked(text: str, body: str = KEY_BODY) -> list[str]:
    """Every run of four characters of the key's body that `text` holds: the whole key, its
    first or last four characters as a masked key shows them, or any part between."""
    return sorted({body[i:i + 4] for i in range(len(body) - 3) if body[i:i + 4] in text})
