"""Pending, FD9 Session A's yes/no 1: the one-line banner's words.

Spec §16.8 and §16.10, and ruling B3 as asked, say that with `--plain` and `TERM=dumb` (and below 40
columns) the banner is the one line `Poisson Tasks <version>`.  The ruled banner's README
(`banners-round-7/pick/README.md`) writes it `Poisson Labs  tasks 0.1.0`, after the new banner's own
words.  The frozen test pins one line holding the version and no art; this pins the words.

**Recommend yes: the spec's words, `Poisson Tasks <version>`.**  If no, the line is
`Poisson Labs  tasks <version>` and this test changes to say so.
"""

from __future__ import annotations

from tests.fd5_support import World, world
from tests.fd9_support import States, pretty_env, pty_session, states, version

__all__ = ["states", "world"]


def test_fd9_pending_with_plain_the_banner_is_poisson_tasks_and_the_version(
    states: States, world: World
) -> None:
    work = states.copy("B", world.work)
    with pty_session(["--plain"], env=pretty_env(world), cwd=work) as session:
        session.quiet(1.5)
        session.type("quit", settle=0)
        assert session.wait() == 0
    lines = [line for line in session.plain.splitlines() if line.strip()]
    assert lines[0].strip() == f"Poisson Tasks {version()}", lines[:2]
