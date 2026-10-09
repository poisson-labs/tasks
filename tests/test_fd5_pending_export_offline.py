"""Pending a yes/no: `export` opens no socket.

FD5.16 has `export` refuse a key over plain http to another machine "with the `ConfigError`
`check_key` raises" (FD2 Session A's yes/no 4).  `providers.check_key` raises that before any
connection, but when it does not raise it makes the free request, sending the key to the
endpoint; and the check that raises is private (`providers._refuse_plain_http_key`), which the
command may not call (FD5.7).  Writing a config file needs neither the key nor the network.

**Recommended yes:** `export` makes no network request and reads no key: `providers` gains one
public name that makes only the plain-http refusal (as `check_key` and `server_facts` make it),
with no request, and `export` calls that.  `tests/test_fd5_export.py` already pins the refusal's
text and that nothing is written; this pins that no socket is opened when the config is taken.

**A no** drops this file's commit: `export` may call `check_key`, which then makes one free
request with the key to the configured endpoint each time it runs.
"""

from __future__ import annotations

import pytest

from tests.fd2_fakes import SENTINEL
from tests.fd5_support import World, config, invoke, prog, world

__all__ = ["prog", "world"]


def test_fd5_16_export_opens_no_socket(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
    made = config().config_from_init_args(["--tasks-per-level", "1"])
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")
    ran = invoke(["export", "--to", "verifiers"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert [kind for kind, _ in ran.events if kind in ("getaddrinfo", "connect")] == []
