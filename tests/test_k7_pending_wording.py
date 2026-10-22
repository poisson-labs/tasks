"""Pending a decision: how a task-shape request is worded.

**This file waits on a decision** and is its own commit, so if it is declined it is dropped whole.

The design names the template (`ledger-goals/v1`) and says it lists one line per goal; it gives no
words.  The frozen `tests/test_k7_request.py` holds each goal line to naming its target's record
id, ledger and goal stage and no other, and the rest of the request to being the same at every
width.  Recommended: B's own words, so the request differs from B's only where the knob needs it.
Each goal line is B's third line with the record and its ledger named, the record id in double
quotes as B quotes it: `Raise record "<id>" of the <ledger> ledger through <stage>, and no
further.`  The request is B's second line (the stage ladder), then the goal lines, then B's fourth
line (the entry code, in double quotes, which every record shares); B's first line, which names one
record, is the goal lines' to say.  If the answer is no, the words are the build's, inside the
frozen tests, and this file is dropped.
"""

from __future__ import annotations

from tests.k3_support import SPEC, made
from tests.k7_support import ARMS, SPLITS, base, request, targets


def test_the_request_is_bs_ladder_line_the_goal_lines_and_bs_entry_code_line() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            b_lines = request(base(seed, split)).split("\n")
            assert len(b_lines) == 4, (seed, split)
            for arm_id in ARMS[:3]:
                bundle = made(arm_id, seed, split)
                lines = request(bundle).split("\n")
                found = targets(bundle)
                assert lines[0] == b_lines[1] and lines[-1] == b_lines[3], (arm_id, seed, split)
                said = lines[1:-1]
                wanted = {
                    f'Raise record "{record}" of the {ledger} ledger through '
                    f"{SPEC.stage_names[goal - 1]}, and no further."
                    for (ledger, record), goal in found.items()
                }
                assert len(said) == len(found) and set(said) == wanted, (arm_id, seed, split)
