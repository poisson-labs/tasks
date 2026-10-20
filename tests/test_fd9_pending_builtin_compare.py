"""Pending, FD9 Session A's yes/no 4: `card --compare published` on the built-in tasks.

Spec §16.11 (G12) says `card --compare published` reads the written card, needs no `--force`, opens
with its verdict ("`different  <one sentence>` for your own tools, or the earlier-build sentence for
built-in tasks"), writes `card/compare.md`, prints neither card, and exits 0.  FD9.17 pins it on your
own tools.  On the built-in tasks the spec does not name the verdict word, or what `compare.md`
holds, since this release sets no built-in card beside the published ones.

**Recommend yes: on the built-in tasks it is the same shape: exit 0, the verdict `different` with the
earlier-build sentence, and `compare.md` holding that sentence.**  If no, it stays a refusal in one
line (exit 1) on the built-in tasks, as today.
"""

from __future__ import annotations

import pytest

from tests.fd5_support import World, invoke, world
from tests.fd9_support import PROG, States, run_folder, states

__all__ = ["states", "world"]


def test_fd9_pending_compare_on_the_built_in_tasks_says_different_and_writes_compare_md(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = run_folder(states.copy("D", world.work))
    ran = invoke(["card", "--compare", "published"], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 0 and ran.word == "different", ran
    compare = folder / "card" / "compare.md"
    assert compare.is_file() and compare.read_text(encoding="utf-8").strip()
