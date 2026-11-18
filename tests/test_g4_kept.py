"""What the 0.5.0 generator change moves and what it must not: spread's tasks and nothing else's,
frozen as tests.

The change edits the built-in generator's modules and the own-tools generator's, so both hashes
move and every task id with them.  A task's content is every field but the ones that follow the
hash (`task_id`, `generator_hash` and, on the built-in tools, `pins`).  Ruled 2026-11-15: only
spread's content moves.  Every other dial's tasks, built-in and on a user's own tools, the 840
tasks the published cards measured, and the knob probe's record are as 0.4.2 left them.

The kept files hold each dial's content digests and compare the tasks with them
(`tests/test_k4_kept.py` to `tests/test_k8b_kept.py`, `tests/test_f2_kept.py`,
`tests/test_bd_kept.py`, `tests/test_o2b_kept.py`).  A build that moved another dial's tasks would
fail there, unless it also moved the digest it is compared with.  This file holds the tables
themselves, so that way out is closed.

Shapes decided here
-------------------

**1. No table but spread's moved**: each kept table that holds no spread row is, row for row,
the table 0.4.2 held: similarity and faults, history, block, arguments, shape, timeouts and
ratelimits, baddata on the built-in tools; timeouts, ratelimits and landed, and baddata and lagged,
on a user's own; and the 118 own-tools rows of the eight older knobs that are not spread's.  Each
is held by one digest of the table, measured on 0.4.2's tree (`917d2e7`).  Green on that tree by
construction; it guards the build.

**2. Every spread row moved**: the built-in spread table has the eight rows it had (four levels,
two splits) and the own-tools table the eighteen it had (six fixture sets, three levels), and no
row holds the digest 0.4.2 held.  Every one moves, level 4 too, where no answer is empty: the
request's sentence changes at every level.  The build writes the new digests, each in its kept
file, and those files' own tests compare the tasks with them.

**3. The 840 published tasks** are the fixture 0.4.2 held, by its bytes, and each regenerates with
the content stored there (`tests/test_k1_content.py`'s comparison, run from here against a digest
this file holds).

**4. The probe's record**: `knob_status.json`, which names the generator the probe ran on and what
it found, is the file 0.4.2 shipped, byte for byte, in the tree and as the package reads it.  The
probe ran on generator `b460964d...`; a later generator does not rewrite what it measured.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.resources
import json
from pathlib import Path
from typing import Any

import pytest

from tests import test_k1_content as published
from tests import test_k8b_kept, test_o2b_kept

REPO = Path(__file__).resolve().parent.parent

# Each kept table with no spread row: how many rows it has and its digest, at 0.4.2.
TABLES_AT_0_4_2 = {
    ("test_k4_kept", "MAIN"): (18, "a1c42570c8e0b64239d29070624963c627e2b4bd95eebbe36f0565b64ee16b2e"),
    ("test_k5_kept", "MAIN"): (8, "efd785c7be65ad7f95e8dc57866c5065a4468581c2420b5bbf194ce32b9e60f4"),
    ("test_k6_kept", "MAIN"): (10, "35eb9041bc370f5d349de2e0f5cd6a563acfd3b03654cef4e4de0804633bc438"),
    ("test_k7_kept", "MAIN"): (10, "5e5661771ef10baa39e1981a0cd1864bb801a2ab3743abc130d6039cbced5d87"),
    ("test_k8_kept", "MAIN"): (8, "ca0dd1bf7770f938e48baee651eed73c87b89caa78c4f9bdb359dd98cfd1f6b3"),
    ("test_f2_kept", "MAIN"): (20, "ef8f7be39951608522d2c3a308b74081277dc10c82cb4969175c4acf7aca32c2"),
    ("test_f2_kept", "OWN"): (58, "31e4595e3baf463d6080072a20dc6d7dea991a75c83f32ee33d9f9fa2473de80"),
    ("test_bd_kept", "MAIN"): (8, "c4977de338430859b36ec70064de99e3ceaf910bf1a694fcb01c5af8b74cd493"),
    ("test_bd_kept", "OWN"): (27, "919fc8f76751901d29153da6192b27ae9fca3734c86a2235e8806768a4c1f12a"),
}
OWN_REST_AT_0_4_2 = (118, "cfe9a8c8d6cd9d51f48c42b57dceaacd6b9480aa50a3ad15c4b12078979b8986")

# Spread's digests at 0.4.2, which no row may hold from 0.5.0.
SPREAD_AT_0_4_2 = {
    ("spread:p1", "eval"): "140856100a6fa0e2112de5c0eb2a15f02b1cd5143fbdb4f2d08fc4b9d658fa9f",
    ("spread:p1", "train"): "e4b50421fc165480d6638b8c4861a059da25e4ca5df1a026ca439fb2bdb4fce4",
    ("spread:p2", "eval"): "edf3f502396b1883a059c009f3cdd96bca0a6c1705d5a926942954533ed54f19",
    ("spread:p2", "train"): "e46ccff85326f48047fed7f5b4bc773d5cce53624ed71d2c5187923acdd5d464",
    ("spread:p3", "eval"): "d10f5941f9382968fa955eb59579675d5ede86ff9789664dc59720f1b996f2f2",
    ("spread:p3", "train"): "8967d8499541611354fe28c98ec1596b86353a20ad329d6db1334825fa316cba",
    ("spread:p4", "eval"): "013736ea1f46864ed8154551d51ed457547cb686928db6c8b39bd78ca235cdd3",
    ("spread:p4", "train"): "beaf35cad77bb1e961cb95b20f067582a0732f80c888e95bbca6145cf42e6746",
}
OWN_SPREAD_AT_0_4_2 = {
    ("acme-mcp", "spread:p1"): "dcf107529090d84b86d2d3abe534da339cc180bcf30e540cb052bc4202697e0e",
    ("acme-mcp", "spread:p2"): "5f8d297e8775d42a24a2b3b766ded5af8da61b76b06cb93326ff605531a9d82a",
    ("acme-mcp", "spread:p4"): "fb1443270a18293c0bffd1f5a34a62e0a566e93306d50d5cd60bae051fde2f28",
    ("acme-openai", "spread:p1"): "686678f4a9b36e1bdbb570e1395bf7f18d8da063dcd3000af7484dc5ce011219",
    ("acme-openai", "spread:p2"): "3bc566b6b354a6fb218efd3f6372b06fbe72b20b6aa451318c27cb4dfb5fe41c",
    ("acme-openai", "spread:p4"): "deef62de542413eaea57fc7b1e855e49f9f93ff35a95aca65f331f997492d0b1",
    ("acme-openapi-3.0", "spread:p1"): "43e4536b3650468e9154e345c1a6bdcf6d8cbe270d1b73484625e2ee08f0f8a6",
    ("acme-openapi-3.0", "spread:p2"): "2427fc7682c13691d46c1c1ca7f7d681e8bc506803969f91f5e85c6cdfbb252b",
    ("acme-openapi-3.0", "spread:p4"): "d71582709d04f814ede008910bac4805e79948e92bb57117f1d1a3c4c3772400",
    ("acme-openapi-3.1", "spread:p1"): "f7f4470a80c69ebe9150cd049a210915fb8e918a0306d920b6940e620552a57a",
    ("acme-openapi-3.1", "spread:p2"): "7935d740b7a43122ef5f4cf6e561b6ecb9734c1b245b392054d922bb25399846",
    ("acme-openapi-3.1", "spread:p4"): "1807b69b26e6e1f43e708790860397bce26068e7d02cd039ddaf3f57a40b4bb2",
    ("everything", "spread:p1"): "b2d1fe58cfb17a38566d19370d72ca174653d1d63a0a34584d0f1997798a4e87",
    ("everything", "spread:p2"): "6f374203cbbcac52021111fb3a1dd33e5784a52c115ffda60bd8ae95b6b416cb",
    ("everything", "spread:p4"): "eafde224a4619fa2319217a6f95aa2b415a34542fcdc802ab855b04cdea776b2",
    ("petstore", "spread:p1"): "28bc962e31ffb024066b170b37acee0aed5dd184680897ae9d2431390dd1a59c",
    ("petstore", "spread:p2"): "5fe6e4945c4d630139e0c0188e1a99c019fbe0c321bc62736b3f30e348cc48fa",
    ("petstore", "spread:p4"): "4b3f9d849e35997f506a78b0657ac41a79c61f2b9c32583b852e216e99ac3738",
}
PUBLISHED_FIXTURE_AT_0_4_2 = "84ded2aabfb5542a0614f0220ae2634a326493ae8b3e56680734f1ba534a8d6e"
KNOB_STATUS_AT_0_4_2 = "6a9cc69cf9ebb34d9a7627d540648a20b97b0e0a9048b29c3ae99715dbdae9c5"
PROBE_GENERATOR = "b460964dc153fab4535af3b39abd41d50198f3dcc644ae3e43ddee85544b57f9"


def table_digest(table: dict[tuple[str, str], str]) -> str:
    """One digest of a kept table: its rows sorted, each a key and its digest, as compact JSON."""
    rows = sorted([list(key), value] for key, value in table.items())
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def is_spread(arm_id: str) -> bool:
    return arm_id.partition(":")[0] == "spread"


@pytest.mark.parametrize(("name", "attribute"), sorted(TABLES_AT_0_4_2))
def test_a_kept_table_with_no_spread_row_is_the_one_0_4_2_held(name: str, attribute: str) -> None:
    """Shape 1."""
    table: dict[tuple[str, str], str] = getattr(importlib.import_module(f"tests.{name}"), attribute)
    rows, digest = TABLES_AT_0_4_2[(name, attribute)]
    assert not any(is_spread(part) for key in table for part in key), (name, attribute)
    assert len(table) == rows, (name, attribute)
    assert table_digest(table) == digest, (name, attribute)


def test_the_own_tools_rows_that_are_not_spreads_are_the_ones_0_4_2_held() -> None:
    """Shape 1, the own-tools table, which holds spread's rows among the others'."""
    rest = {key: value for key, value in test_o2b_kept.MAIN.items() if not is_spread(key[1])}
    rows, digest = OWN_REST_AT_0_4_2
    assert len(rest) == rows
    assert table_digest(rest) == digest


@pytest.mark.parametrize("row", sorted(SPREAD_AT_0_4_2))
def test_every_built_in_spread_row_moved(row: tuple[str, str]) -> None:
    """Shape 2."""
    assert set(test_k8b_kept.MAIN) == set(SPREAD_AT_0_4_2)
    assert test_k8b_kept.MAIN[row] != SPREAD_AT_0_4_2[row], row


@pytest.mark.parametrize("row", sorted(OWN_SPREAD_AT_0_4_2))
def test_every_own_tools_spread_row_moved(row: tuple[str, str]) -> None:
    """Shape 2."""
    kept = {key: value for key, value in test_o2b_kept.MAIN.items() if is_spread(key[1])}
    assert set(kept) == set(OWN_SPREAD_AT_0_4_2)
    assert kept[row] != OWN_SPREAD_AT_0_4_2[row], row


def test_the_840_published_tasks_are_the_fixture_0_4_2_held_and_keep_their_content() -> None:
    """Shape 3."""
    assert published.FIXTURE_SHA256 == PUBLISHED_FIXTURE_AT_0_4_2
    assert hashlib.sha256(published.FIXTURE.read_bytes()).hexdigest() == PUBLISHED_FIXTURE_AT_0_4_2
    stored = published.fixture()["tasks"]
    assert len(stored) == 840
    moved: list[tuple[Any, Any, list[str]]] = []
    for entry in stored:
        new = published.as_stored(published.regenerated()[(entry["arm_id"], entry["seed"])])
        old = entry["bundle"]
        names = [name for name in old if name not in published.MOVING and new[name] != old[name]]
        if names:
            moved.append((entry["arm_id"], entry["seed"], names))
    assert not moved, moved[:5]


def test_the_probes_record_is_the_file_0_4_2_shipped() -> None:
    """Shape 4."""
    in_tree = (REPO / "src" / "poisson_tasks" / "knob_status.json").read_bytes()
    assert hashlib.sha256(in_tree).hexdigest() == KNOB_STATUS_AT_0_4_2
    packaged = importlib.resources.files("poisson_tasks").joinpath("knob_status.json").read_bytes()
    assert hashlib.sha256(packaged).hexdigest() == KNOB_STATUS_AT_0_4_2
    assert PROBE_GENERATOR in packaged.decode("utf-8")
