"""Pending, FD9 Session A's yes/no 5: the `card` step below a refused card's replies.

Ruled 2026-10-20 (yes/no 3, no): when the card is refused, step 1 is the replies view and `card`
stays offered below it, and FD9.8 has no exception.  But `card` on a folder whose card is refused
shows the refusal and exits 1 (FD5's frozen codes, `card`'s verdict `refused`), and FD9.8 says no
offered step's command exits 1 or 2.  Both cannot hold for that one step.

**Recommend yes: `card` stays offered below the replies, and FD9.8 holds for every step but that
one, whose exit 1 is the refusal it is there to show; step 1, which the session leads with, never
fails.**  If no, `card` is not offered when the card is refused (its steps are the replies and the
refusal's own `next:`), FD9.7's check that `card` is offered goes, and FD9.8 has no exception.
"""

from __future__ import annotations

import pytest

from tests.fd5_support import World, invoke, world
from tests.fd9_support import PROG, Keys, States, home_blocks, in_session, states, steps_of

__all__ = ["states", "world"]


def test_fd9_pending_the_card_step_below_a_refused_cards_replies_exits_1_with_the_refusal(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    states.copy("D-refused", world.work)
    shown = in_session(Keys(["quit"]), monkeypatch)
    blocks = home_blocks(shown.out)
    assert blocks, shown
    steps = steps_of(blocks[0])
    number = steps.index("card") + 1
    assert number > 1, steps
    session = in_session(Keys([str(number), "quit"]), monkeypatch)
    commands = session.same_as()
    assert commands and commands[0][1] == "card", session
    shell = invoke(commands[0][1:], prog=PROG, monkeypatch=monkeypatch, check=False)
    assert shell.code == 1 and shell.word == "refused", shell
