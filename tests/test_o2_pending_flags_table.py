"""Pending a decision: the own-tools flags are `config.OWN_INIT_FLAGS`, beside `INIT_FLAGS`.

**Why it is open.**  The design lists the flags; where `config` keeps them is not said.  The frozen
`test_fd1_1_the_flag_table_covers_every_key_with_the_spec_flags` holds every flag of
`config.INIT_FLAGS` to the front door's list and every key it sets to the settings file's, so an
own-tools flag in `INIT_FLAGS` fails it.

**Recommended.**  A table of their own, `OWN_INIT_FLAGS`, the same `InitFlag` rows, read by
`config_from_init_args` with `INIT_FLAGS`; that frozen test stays as it is.  If it is declined, the
build puts them in `INIT_FLAGS` and retrofits that frozen test, a recorded commit after the
decision.
"""

from __future__ import annotations

from tests.o2_support import config


def test_the_own_flags_are_a_table_of_their_own() -> None:
    cfg = config()
    rows = {flag.flag: flag.key for flag in cfg.OWN_INIT_FLAGS}
    assert rows == {"--own-file": "own.file", "--own-format": "own.format", "--own-name": "own.name",
                    "--own-read": "own.read", "--own-write": "own.write",
                    "--own-intent": "own.intents", "--own-flow": "own.flow"}
    assert all(isinstance(flag, cfg.InitFlag) for flag in cfg.OWN_INIT_FLAGS)
    assert not {flag.flag for flag in cfg.INIT_FLAGS} & set(rows)
