"""Pending a decision: a card of leaky arms, or of
the train split, is not comparable with a card of strict arms on the eval split.

An arm's id names neither its strictness nor its split, and no field of `_COMPARABLE` holds them,
so two cards whose blocks agree on every field it lists can still score another predicate (a
leaky arm passes an overshoot) or be other tasks (the train split's).  Read side by side, the
numbers would look comparable and are not: the decision that a card compares nothing it cannot
compare.  `comparable` names a field for them; which is the build's.  The control is two runs
of one strict plan.
"""

from __future__ import annotations

import pytest

from tests.fd3_support import calibration, needs_uv
from tests.fd4_support import RunFolders, fd4_runs, one_line

__all__ = ["fd4_runs"]

pytestmark = needs_uv


@pytest.mark.parametrize("scenario", ["leaky", "train"])
def test_fd4_5_a_leaky_or_train_split_card_is_not_comparable_with_a_strict_eval_one(
    fd4_runs: RunFolders, scenario: str
) -> None:
    strict = calibration().card_from_run(fd4_runs["strict"].folder).artifact
    again = calibration().card_from_run(fd4_runs["strict_again"].folder).artifact
    other = calibration().card_from_run(fd4_runs[scenario].folder).artifact
    assert calibration().comparable(strict, again).field is None
    assert [cell["arm_id"] for cell in other.cells] == [cell["arm_id"] for cell in strict.cells]
    answer = calibration().comparable(strict, other)
    assert answer.field is not None and one_line(answer.reason)
    assert calibration().comparable(other, strict).field == answer.field
