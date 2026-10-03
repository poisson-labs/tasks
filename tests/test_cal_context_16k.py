"""Model B's context is 16,384 tokens, the probe reads the longest prompts, and a refused card
says which rule refused it.

On Colab, phase 3 ran all 14 arms and the card refused.  The driver's last line said "CAL24:
refused", but the no-call share was 0.000 in every cell.  The refusal was the instrument-rate
gate: `depth:d1+h8` had 26 of 300 episodes (0.087) end as `context_length`, and `depth:d2+h5`
had 12.  Those two control arms open with a seeded history of eight and five turns, so their
prompts are the longest on the card.  Qwen's chat template spells the sixteen tool schemas out
as JSON, and prompts reached 6,129 and 6,081 tokens.  The cap left 8,192 - 2,048 = 6,144 for the
prompt, so vLLM refused the next call.  The wheel ends such an episode as `context_length` with
the trace not ok, and the card counts that as an instrument failure.  That is right: the cap is
a serving choice, not the model's difficulty.

The probe exists to catch this before the card: it stops when a prompt passes 75% of the room
the cap leaves.  But it ran only `depth:d5` and `depth:d8`, which carry no history, so it never
saw a long prompt.

Decided 2026-09-28, all four:
1. `--max-model-len` 16384.  The decoding, including the 2,048-token completion limit, is
   unchanged, so the card stays comparable with model A's.
2. The probe also runs the two history controls, for their prompts, context stops and
   instrument failures only.  The floor stays a question about the hardest levels.
3. The phase 3 line names the refusal it printed as CAL24.
4. The pin's note, which said a context stop is the model's own, is corrected.

The model B prep file pins `--max-model-len` at "8192" in one assertion
(`test_the_serve_flags_are_the_pinned_ones`).  That line is retrofitted to "16384" in its own
commit, and nothing else in that file moves.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.test_cal_qwen_prep import needs_uv, rig  # noqa: F401  (the rig fixture)

from poisson_tasks import calibration as cal

MODEL = "Qwen/Qwen3-8B@b968826d9c46dd6066d109eabc6255188de91218"
HISTORY_CONTROLS = ("depth:d1+h8", "depth:d2+h5")


def run_module() -> Any:
    import importlib

    return importlib.import_module("poisson_tasks.calibration_run")


def _record(arm: str, seed: int, *, leaky: bool, label: str | None = None) -> cal.EpisodeRecord:
    """A passing record when `leaky`, a `wrong_state` one otherwise, or the label given."""
    label = label or ("passed" if leaky else "wrong_state")
    return cal.EpisodeRecord(
        task_id=f"{arm}-{seed}", arm_id=arm, model=MODEL, seed=seed, attempt=0,
        strict=label == "passed", leaky=leaky, label=label, turns=3,
        sampled_calls=2, prompt_tokens=100, cached_input_tokens=0, completion_tokens=10,
        reasoning_tokens=0,
    )


# ---------------------------------------------------------------------------
# the pin
# ---------------------------------------------------------------------------


def test_the_context_is_16384_and_the_completion_limit_is_unchanged() -> None:
    pin = run_module().QWEN3_8B
    args = pin.serve_args("/tmp/t.jinja")
    assert args[args.index("--max-model-len") + 1] == "16384"
    assert pin.max_model_len == 16384
    assert cal.DECODING["max_tokens"] == 2048


def test_the_longest_prompt_seen_on_colab_is_inside_the_probes_headroom() -> None:
    """6,129 tokens was the largest prompt a history control sent before the cap refused the
    next call.  At 16,384 it sits under the probe's 75% line, so a probe that saw it would
    let the card run; at 8,192 the same probe stops."""
    module = run_module()
    room = module.QWEN3_8B.max_model_len - int(cal.DECODING["max_tokens"])
    assert 6129 <= module.HEADROOM * room
    assert 6129 > module.HEADROOM * (8192 - int(cal.DECODING["max_tokens"]))


# ---------------------------------------------------------------------------
# the probe
# ---------------------------------------------------------------------------


def test_the_probe_runs_the_history_controls() -> None:
    module = run_module()
    assert set(HISTORY_CONTROLS) <= set(module.PROBE_CONTEXT_ARMS)
    assert not set(module.PROBE_CONTEXT_ARMS) & set(module.PROBE_ARMS)


def test_the_floor_is_read_on_the_hardest_levels_only() -> None:
    """History controls that fail leaky do not floor a model that does the hardest levels."""
    module = run_module()
    records = [_record("depth:d5", s, leaky=True) for s in range(6)]
    records += [_record(arm, s, leaky=False) for arm in HISTORY_CONTROLS for s in range(20)]
    verdict = module.probe_verdict(records, {}, max_prompt_tokens=1000, context_stops=0,
                                   prompt_cap=14336, floor_arms=module.PROBE_ARMS)
    assert verdict.proceed, verdict.reasons
    assert verdict.leaky == 1.0


def test_an_instrument_failure_on_a_history_control_still_stops_the_probe() -> None:
    module = run_module()
    records = [_record("depth:d5", s, leaky=True) for s in range(6)]
    records += [_record("depth:d1+h8", 0, leaky=False, label="api_error")]
    verdict = module.probe_verdict(records, {}, max_prompt_tokens=1000, context_stops=0,
                                   prompt_cap=14336, floor_arms=module.PROBE_ARMS)
    assert not verdict.proceed


def _probe_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                history: dict[str, int]) -> tuple[int, dict[str, Any]]:
    """The driver's `probe` step on a passed phase 1, with no server and no episode run: every
    arm comes back with twelve passing records, the hardest levels' prompts at 3,000 tokens
    and no context stop, and the history controls' trace facts as given."""
    module = run_module()
    ctx = module.Context(local=tmp_path / "local", durable=tmp_path / "durable", port=1,
                         mirror_interval=60.0)
    ctx.local.mkdir(parents=True)
    (ctx.local / "phase1.json").write_text(json.dumps({"passed": True}))

    def arm_rows(_run_dir: Path, arm: str, _served: str) -> tuple[Any, ...]:
        rows = [_record(arm, seed, leaky=True) for seed in range(12)]
        facts = {"episodes": 12, "max_prompt_tokens": 3000, "context_stops": 0}
        if arm in HISTORY_CONTROLS:
            facts.update(history)
        return rows, {}, facts

    monkeypatch.setattr(module, "_serving", lambda _ctx: {})
    monkeypatch.setattr(module, "_run_arms", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "_arm_rows", arm_rows)
    code = module.cmd_probe(ctx)
    return code, json.loads((ctx.local / "probe.json").read_text())


@pytest.mark.parametrize("history", [
    {"max_prompt_tokens": 12000}, {"context_stops": 1},
], ids=["long_prompt", "context_stop"])
def test_the_probe_step_stops_on_what_only_a_history_control_saw(
    history: dict[str, int], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Colab card's failure, caught where it was missed: the hardest levels' prompts are
    short, and only a history control sends a prompt past 75% of the 14,336 tokens the cap
    leaves, or is ended by the cap.  The step's verdict reads those controls' trace facts
    and stops; the same probe without them proceeds."""
    code, report = _probe_step(tmp_path / "short", monkeypatch, {})
    assert (code, report["proceed"]) == (0, True), report["reasons"]
    code, report = _probe_step(tmp_path / "long", monkeypatch, history)
    assert (code, report["proceed"]) == (3, False), report["reasons"]
    assert report["leaky"] == 1.0, "the floor is not what stopped it"


def test_without_floor_arms_the_verdict_pools_every_record() -> None:
    """The call the model B prep tests make, unchanged."""
    module = run_module()
    records = [_record("depth:d5", s, leaky=False) for s in range(6)]
    verdict = module.probe_verdict(records, {}, max_prompt_tokens=1000, context_stops=0,
                                   prompt_cap=14336)
    assert not verdict.proceed


@needs_uv
def test_the_probe_reports_the_history_controls(rig: Any) -> None:  # noqa: F811
    r = rig()
    r.serve()
    r.run("preflight")
    r.run("phase1")
    r.run("probe")
    report = json.loads((r.durable / "probe.json").read_text())
    for arm in HISTORY_CONTROLS:
        assert arm in report["per_arm"], report["per_arm"].keys()
    assert report["max_prompt_tokens"] == max(
        facts["max_prompt_tokens"] for facts in report["per_arm"].values()
    )
    r.stop_server()


# ---------------------------------------------------------------------------
# the refusal, named
# ---------------------------------------------------------------------------


def test_a_refused_card_is_summarised_by_its_own_reason() -> None:
    reason = ("cell ('depth:d1+h8', 'm') refuses to publish: its instrument rate 0.087 "
              "exceeds the declared threshold 0.02")
    line = run_module().card_status({"cal24": "refused", "refusal": reason})
    assert reason in line
    assert "CAL24" not in line


def test_a_published_card_says_so() -> None:
    assert run_module().card_status({"cal24": "published"}) == "published"
