"""Pending a decision: `config` names `init`'s flag aliases publicly.

`init --help` says `--measure` is an alias of `--recipe` (pinned in `tests/test_fd5_help.py`).
Which flag is an alias of which is `config._ALIASES`, a private name, and the command may take
only names a module lists in `__all__`.  So either the command writes the alias into its
own help, a second copy of the library's table, or the table becomes public.

**Recommended:** `config.INIT_FLAG_ALIASES`, in `config.__all__`, a read-only mapping from the
older flag to the flag it stands for, `{"--measure": "--recipe"}`, the one table both the reader
and the help read.

**A no** drops this file's commit; the command's help then names the alias itself.
"""

from __future__ import annotations

from tests.fd5_support import config


def test_fd5_7_inits_flag_aliases_are_a_public_table() -> None:
    assert "INIT_FLAG_ALIASES" in config().__all__
    assert dict(config().INIT_FLAG_ALIASES) == {"--measure": "--recipe"}
    flags = {flag.flag for flag in config().INIT_FLAGS}
    for alias, target in config().INIT_FLAG_ALIASES.items():
        assert alias in flags and target in flags
    try:
        config().INIT_FLAG_ALIASES["--measure"] = "--knob"
    except TypeError:
        pass
    else:
        raise AssertionError("the table can be changed")
