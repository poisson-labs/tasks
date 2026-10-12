"""Pending a yes/no: the notebook gives the knob probe two hours of phase 3.

**The question.**  The notebook's wall-clock allowance stops phase 3 cleanly when it runs out
(the card's is 6.0 hours).  The spec estimates the probe at about 1.0 hour of episodes on an L4
and 3 to 4 Colab units in all; it sets no allowance.

**Proposed: 2.0 hours** across every resume, twice the estimate.  A stop leaves the arms finished
standing and the knobs without both arms undecided.  **A no** names another allowance.
"""

from __future__ import annotations

from tests.test_k9_notebook import configuration


def test_the_knob_probes_allowance_is_two_hours_and_the_cards_is_unchanged() -> None:
    assert configuration("knob-probe")["WALL_CLOCK_HOURS"] == 2.0
    assert configuration("card")["WALL_CLOCK_HOURS"] == 6.0
