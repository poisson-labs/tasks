"""Pending a decision: a retry the harness refused still counts as calling the tool again.

The design's figure is the share of episodes that "received an `unavailable` from a tool and never
called that tool again".  A model that meets a planned failure and calls the same tool again with
arguments the `null` harness cannot parse has not given up: it tried, and failed to write the call.
So a later sampled call by the tool's name counts as calling it again whether or not the harness
forwarded it, and the record says `False`.  The other reading counts only calls that reached the
tool server, as the plan's own counting does, and says `True`.  Dropped if it is declined; the
build is then free to choose, and records its choice.
"""

from __future__ import annotations

from pathlib import Path

from tests.k3_support import CARD_SEEDS, episode, faults, gave_up, right

NOT_JSON = "{the record id"


def test_a_retry_the_harness_refused_is_still_a_retry(tmp_path: Path) -> None:
    bundle = faults(1, CARD_SEEDS[3])
    (name, args), _second = right(bundle)
    record = episode(tmp_path, bundle, [(name, args), (name, NOT_JSON)])
    assert (record.label, gave_up(record)) == ("malformed_call", False), record
