"""The bytes every own-tools task in these tests is made from, frozen by digest.

A task's id covers its tool file's digest (spec §2.2), so a fixture whose bytes moved, even by a
space, moves every task made from it, and a frozen expectation read off one would move unseen.
These are O1's fixtures, which O2 reuses and adds none to; the digests are each file's SHA-256 as
O1 Session A committed it.  The tasks the build makes from them are pinned by content digests
Session B adds after its build, as the knobs' sessions did.
"""

from __future__ import annotations

import hashlib

from tests.o1_support import FIXTURES

DIGESTS = {
    "acme-mcp-tools-list.json": "0de506261513f27acb6672ce74a25b7ce1967e97d49cf174c53068d00d5243e7",
    "acme-openai-chat.json": "5038e1bbef2e2e65c00227bf715cae357b8af056005591e35d8edc4b3251c647",
    "acme-openapi-3.0.json": "25944a0c778442455f72f6f05d42e68e68651ee47cf4a18e0a51faaa9f13f998",
    "acme-openapi-3.1.yaml": "ae58133dfa705fb890a927ce383aca5c1ccf0d7c9644795899902ca2a38da627",
    "petstore-openapi-3.0.json": "00441c05add60f28da55eb4563d3fb6bbda364ba8eb7b381e2e2c98613005c82",
    "mcp-everything-tools-list.json": "97068e1c2ec7d0a85d1302d66e17617f26c076a984d5e09568a310a59279eed4",
}


def test_every_fixture_an_own_task_is_made_from_has_its_recorded_bytes() -> None:
    found = {name: hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() for name in DIGESTS}
    assert found == DIGESTS
