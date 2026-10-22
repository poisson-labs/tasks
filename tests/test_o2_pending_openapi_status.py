"""Pending a decision: which 4xx an OpenAPI-shaped error carries for each code.

**Why it is open.**  The design: "an OpenAPI-shaped `{"status": 4xx or 503, "detail": "..."}`", with
the codes `not_found`, `invalid_arguments`, `not_ready` and `unavailable`; 503 is `unavailable`'s,
and the 4xx of the other three is not said.

**Recommended.**  404 for `not_found`, 422 for `invalid_arguments` (the request was read and
its content is wrong), 409 for `not_ready` (the store is not in the state the call needs).  A no
picks others; the `status` stays one integer per code.
"""

from __future__ import annotations

import json

from tests.o2_support import simulator


def test_each_code_has_its_status() -> None:
    sim = simulator()
    found = {code: json.loads(sim.error("openapi", code, "m").text)["status"] for code in sim.ERROR_CODES}
    assert found == {"not_found": 404, "invalid_arguments": 422, "not_ready": 409, "unavailable": 503}
