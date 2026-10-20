"""Pending, FD9 Session A's yes/no 2: the banner below 40 columns.

Spec §16.10's widths: the full form from 80 columns, the narrow form from 40 to 79, and below 40 the
one line `Poisson Tasks <version>`.  They were written for banners of 45 to 74 columns.  The ruled
banner is 26 columns by 2 rows and is its own narrow form, so it would fit down to 26 columns.

**Recommend yes: the spec's rule stands, so below 40 columns the banner is the one line.**  If no,
the two-row banner shows down to 26 columns and the one line only below that.
"""

from __future__ import annotations

from tests.fd5_support import World, world
from tests.fd9_support import MARK, States, pretty_env, pty_session, states, version

__all__ = ["states", "world"]


def test_fd9_pending_below_40_columns_the_banner_is_one_line(
    states: States, world: World
) -> None:
    work = states.copy("B", world.work)
    with pty_session([], env=pretty_env(world), cwd=work, columns=30) as session:
        session.quiet(1.5)
        session.type("quit", settle=0)
        assert session.wait() == 0
    lines = [line for line in session.plain.splitlines() if line.strip()]
    assert version() in lines[0] and MARK not in session.plain, lines[:3]
