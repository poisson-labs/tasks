"""C2.4: what each request carries, per model, as it reaches the endpoint.

The design's table of how each model is called:

| | gpt-6-luna | claude-haiku-5-5 | Qwen3.8-27B |
|---|---|---|---|
| path | the `openai` preset, api.openai.com | the `anthropic` preset, Anthropic's OpenAI-compatible endpoint | the calibration path against vLLM |
| temperature | 1.0 | 1.0 | 1.0 |
| top_p | 1.0 | not sent | 1.0 |
| reasoning effort | low | not sent (the model runs at its default) | low, thinking on |
| completion tokens per call | 8,192 | 8,192 | 8,192 |

Every request body of a whole run, phase 1 and the four own-tools arms included, is read from the
fake server that received it.  The two hosted models are driven here; the same check on the
notebook's path to vLLM is in `tests/test_c2_notebook.py`, which holds the fake as its server.

Readings made here: the limit travels as `max_completion_tokens`, as every card's has since the
first run (`tests/test_cal_decoding_wire.py`), on all three paths; and a body carries nothing
else that decides sampling, so thinking is whatever the model's default is.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.c2_fake import CLAUDE_LIKE, Play
from tests.c2_support import (
    ARMS,
    CAPS,
    DECODING,
    ENDPOINTS,
    HAIKU,
    LUNA,
    MAX_TOKENS,
    NANO,
    NOT_SENT,
    PRICES,
    bodies,
    card_run,
    clean_run,
    drive,
    lines,
    needs_uv,
    read,
    registry_cache,
    sampling,
)

OPENAI_BODY = {
    "model": LUNA,
    "temperature": 1.0,
    "top_p": 1.0,
    "reasoning_effort": "low",
    "max_completion_tokens": MAX_TOKENS,
}
CLAUDE_BODY = {"model": HAIKU, "temperature": 1.0, "max_completion_tokens": MAX_TOKENS}


def test_the_typed_decodings_are_the_designs_rows() -> None:
    """A guard on the support file's table."""
    assert MAX_TOKENS == 8192
    assert DECODING[LUNA] == {
        "temperature": 1.0, "top_p": 1.0, "reasoning_effort": "low", "max_tokens": 8192}
    assert DECODING[HAIKU] == {
        "temperature": 1.0, "top_p": "not sent", "reasoning_effort": "not sent", "max_tokens": 8192}


def test_each_hosted_models_row_is_its_preset_endpoint_decoding_price_and_cap() -> None:
    models = card_run().MODELS
    assert set(models) == {LUNA, HAIKU, NANO}
    assert (models[LUNA].provider, models[HAIKU].provider) == ("openai", "anthropic")
    for name in (LUNA, HAIKU):
        row = models[name]
        assert row.role == "card"
        assert row.base_url == ENDPOINTS[name]
        assert dict(row.decoding) == DECODING[name]
        price = row.price
        assert (price.input, price.cached_input, price.output, price.read_on) == PRICES[name]
        assert row.cap == CAPS[name]
    assert models[LUNA].api_surface == "OpenAI chat completions"
    assert models[HAIKU].api_surface == "Anthropic OpenAI-compatible endpoint"


def test_the_endpoints_are_the_settings_files_own_presets() -> None:
    from poisson_tasks import config

    models = card_run().MODELS
    assert models[LUNA].base_url == config.PRESETS["openai"].endpoint
    assert models[HAIKU].base_url == config.PRESETS["anthropic"].endpoint


@pytest.fixture(scope="module")
def luna(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return clean_run(LUNA, tmp_path_factory)


@pytest.fixture(scope="module")
def haiku(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return clean_run(HAIKU, tmp_path_factory)


@needs_uv
def test_every_openai_request_carries_temperature_top_p_effort_low_and_8192(
    luna: dict[str, Any],
) -> None:
    assert luna["code"] == 0, luna["out"] + luna["err"]
    sent = bodies(luna)
    assert len(sent) > 2 * len(ARMS)
    for body in sent:
        assert sampling(body) == OPENAI_BODY, sampling(body)


@needs_uv
def test_every_claude_request_carries_temperature_and_8192_and_nothing_else(
    haiku: dict[str, Any],
) -> None:
    assert haiku["code"] == 0, haiku["out"] + haiku["err"]
    sent = bodies(haiku)
    assert len(sent) > 2 * len(haiku["design"].arms)
    for body in sent:
        assert "top_p" not in body and "reasoning_effort" not in body, sampling(body)
        assert sampling(body) == CLAUDE_BODY, sampling(body)


@needs_uv
@pytest.mark.parametrize("model", [LUNA, HAIKU])
def test_no_request_names_the_limit_max_tokens(
    model: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    for body in bodies(clean_run(model, tmp_path_factory)):
        assert "max_tokens" not in body


@needs_uv
@pytest.mark.parametrize("model", [LUNA, HAIKU])
def test_the_own_tools_arms_and_phase_1_are_called_the_same_way(
    model: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    found = clean_run(model, tmp_path_factory)
    expected = OPENAI_BODY if model == LUNA else CLAUDE_BODY
    for arm in ("landed:l1", "lagged:g1", "history:t2400", "depth:d1"):
        sent = bodies(found, arm)
        assert sent, arm
        assert all(sampling(body) == expected for body in sent), arm
    assert all(matched is not None for matched in found["matched"]), "a request was no task's"


@needs_uv
@pytest.mark.parametrize("model", [LUNA, HAIKU])
def test_the_record_holds_the_decoding_as_sent_with_each_unsent_field_named(
    model: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    found = clean_run(model, tmp_path_factory)
    record = read(found["folder"] / "record.json")
    assert record["decoding"] == DECODING[model]
    unsent = [name for name, value in record["decoding"].items() if value == NOT_SENT]
    assert unsent == ([] if model == LUNA else ["top_p", "reasoning_effort"])
    assert record["max_model_calls"] == 32 and record["model"] == model


@needs_uv
def test_a_claude_run_ends_with_no_refused_call(haiku: dict[str, Any]) -> None:
    """The fake refuses `top_p` and `reasoning_effort` with a 400, as current Claude models
    refuse `top_p`: no episode of the run carries an instrument label."""
    labels = {row["label"] for row in lines(haiku["folder"])}
    assert labels <= {"passed", "wrong_state"}, labels


@needs_uv
def test_the_openai_decoding_sent_to_a_claude_endpoint_stops_at_phase_1(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The fake bites: a run that sends `top_p` to it has every call refused, which phase 1
    reads as instrument failures, so the run stops there."""
    found = drive(
        tmp_path_factory.mktemp("c2-wrong-decoding"),
        registry_cache(tmp_path_factory),
        model=LUNA,
        play=Play(provider=CLAUDE_LIKE),
    )
    assert found["code"] == 2, found["out"] + found["err"]
    assert not read(found["folder"] / "phase1.json")["passed"]
