"""Pending a decision: where the key is read from, and a key check that cannot check.

**The question.**  The driver "loads it from .env at run time without printing it, and stops with
one line saying where it looked if it is missing or refused".  Which file, which variable, and
what a free check that answers neither yes nor no means, are open.

**Proposed:** the `.env` of the folder the command runs in (`--env-file` names another), a
`MODEL_API_KEY=` line (the name model A's card was run with; `export ` and quotes are allowed),
and the front door's one free request: refused, missing model or unreachable stop in one line; a
check that cannot tell (a 429 or a 500 on the free request) does not stop the run, whose first
call will show.  **A no** names another file or variable, or stops on a check that cannot tell.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def test_the_key_is_a_model_api_key_line_with_export_and_quotes_allowed(tmp_path: Path) -> None:
    from poisson_tasks import knob_probe as probe

    env = tmp_path / ".env"
    env.write_text('# keys\nOPENAI_API_KEY=sk-other\nexport MODEL_API_KEY="sk-quoted"\n')
    assert probe.load_key(env) == "sk-quoted"
    assert probe.KEY_VAR == "MODEL_API_KEY"
    args = probe.build_parser().parse_args(["run", "--folder", "f", "--cap", "4"])
    assert args.env_file == Path(".env")


def test_a_check_that_cannot_tell_does_not_stop_the_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from poisson_tasks import knob_probe as probe
    from poisson_tasks import providers, runs

    class Started(Exception):
        pass

    def check(model: Any, **kwargs: Any) -> providers.KeyCheck:
        return providers.KeyCheck(providers.NOT_CHECKABLE, "api.openai.com", None, "429")

    def start(*args: Any, **kwargs: Any) -> Any:
        raise Started

    monkeypatch.setattr(providers, "check_key", check)
    monkeypatch.setattr(runs, "run_plan", start)
    monkeypatch.setenv("MODEL_API_KEY", "unset")
    monkeypatch.delenv("MODEL_API_KEY")
    (tmp_path / ".env").write_text("MODEL_API_KEY=sk-k9-PENDING\n")
    tiny = probe.Design(
        arms=("similarity:s0", "similarity:s3"),
        phase1_seeds=probe.PHASE1_SEEDS,
        probe_seeds=probe.PROBE_SEEDS[:2],
    )
    with pytest.raises(Started):
        probe.run_probe(tmp_path / "run", cap=1.0, env_file=tmp_path / ".env", design=tiny)
    assert (tmp_path / "run" / "record.json").exists()
