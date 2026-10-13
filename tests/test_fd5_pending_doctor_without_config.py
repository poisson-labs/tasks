"""Pending a yes/no: `doctor` with no settings file checks the environment alone.

Spec §4.7: `doctor` "says whether this environment can run the config" and works without one, from
flags (§4.0).  What it says with no `tasks.toml` and no `--config` is not written down.

**Recommended yes:** with no settings file, `doctor` reports on the environment (Python, the
package, the tokenizer, the harness, the platform), says there is no settings file and that
`init` writes one, and is ready, exit 0, when the tokenizer is in place on macOS or Linux.  Its
`next:` is `init`.

**A no** drops this file's commit: `doctor` with no settings file is not ready (exit 4), naming
`init` as the fix.
"""

from __future__ import annotations

import pytest

from tests.fd5_support import World, invoke, next_commands, prog, world

__all__ = ["prog", "world"]


def test_fd5_17_doctor_with_no_settings_file_is_ready_on_the_environment_alone(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["doctor", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert ran.word == "ok", ran
    assert any(command.startswith(f"{prog} init") for command in next_commands(ran.out)) or \
        f"{prog} init" in ran.out, ran
