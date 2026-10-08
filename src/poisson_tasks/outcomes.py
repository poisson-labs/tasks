"""What each outcome label means, in one plain sentence.

The labels are `tasks.OUTCOMES`; the sentences are kept here and never in `tasks.py`, whose bytes
are part of every task id.  `tests/test_fd4_outcomes.py` says what each name does.
"""

from __future__ import annotations

import types
from collections.abc import Mapping
from typing import Any

__all__ = ["MEANING", "describe"]

MEANING: Mapping[str, str] = types.MappingProxyType({})
"""One sentence per outcome label."""


def describe(verdict: Any) -> str:
    """The sentence for a verdict: a `tasks.Verdict`, by its strict label, or a label."""
    raise NotImplementedError("FD4: outcomes.describe")
