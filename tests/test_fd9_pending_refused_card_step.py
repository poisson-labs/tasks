"""Pending, FD9 Session A's yes/no 3: step 1 of a folder whose card was refused.

Spec §16.3's table makes `card` step 1 when the run's card was refused ("`card` (shows the
refusal)"), and FD9.8 says no offered step's command exits 1 or 2.  A refused card exits 1 by
FD5's codes, so the two cannot both hold for that step.  The frozen FD9.8 test leaves that one step
out, and FD9.7 still pins `card` as step 1.

**Recommend yes: the refused card stays step 1, and its exit 1 is the exception to FD9.8,** since
the refusal is what the person needs to read (its `next:` leads on).  If no, step 1 there becomes
the refusal's own `next:` (`generate --show --arm <arm>`), and FD9.7's table entry changes.
"""

from __future__ import annotations

import pytest

from tests.fd5_support import World, invoke, world
from tests.fd9_support import PROG, Keys, States, in_session, states

__all__ = ["states", "world"]


def test_fd9_pending_a_refused_cards_step_1_is_card_and_its_command_exits_1(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    states.copy("D-refused", world.work)
    session = in_session(Keys(["1", "quit"]), monkeypatch)
    commands = session.same_as()
    assert commands and commands[0][1] == "card", session
    shell = invoke(commands[0][1:], prog=PROG, monkeypatch=monkeypatch, check=False)
    assert shell.code == 1 and shell.word == "refused", shell
