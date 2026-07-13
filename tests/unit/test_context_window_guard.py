from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.exceptions import ContextWindowExceededError
from app.core.openai.requests import ResponsesRequest
from app.modules.proxy import request_policy


def _registry() -> SimpleNamespace:
    model = SimpleNamespace(slug="gpt-5.3-codex-spark", context_window=128_000)
    return SimpleNamespace(get_models_with_fallback=lambda: {model.slug: model})


def _settings() -> SimpleNamespace:
    return SimpleNamespace(model_context_window_overrides={})


def test_estimable_context_overflow_is_rejected_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(request_policy, "get_settings", _settings)
    payload = ResponsesRequest(
        model="gpt-5.3-codex-spark",
        instructions="",
        input="x" * 500_000,
    )

    with pytest.raises(ContextWindowExceededError, match="context window"):
        request_policy.enforce_context_window(payload, registry=_registry())


def test_context_guard_allows_smaller_inline_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(request_policy, "get_settings", _settings)
    payload = ResponsesRequest(
        model="gpt-5.3-codex-spark",
        instructions="",
        input="x" * 300_000,
    )

    request_policy.enforce_context_window(payload, registry=_registry())


def test_context_window_error_uses_websocket_error_envelope() -> None:
    from app.modules.proxy._service.websocket.helpers import _app_error_to_websocket_event

    event = _app_error_to_websocket_event(
        ContextWindowExceededError(
            model="gpt-5.3-codex-spark",
            estimated_tokens=120_000,
            guard_limit=115_200,
            context_window=128_000,
        )
    )

    assert event["type"] == "error"
    assert event["status"] == 400
    assert event["error"] == {
        "message": "Estimated input for model 'gpt-5.3-codex-spark' is too large for its context window; "
        "reduce the input or use a model with a larger context window.",
        "type": "invalid_request_error",
        "code": "context_length_exceeded",
    }


def test_context_guard_skips_opaque_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(request_policy, "get_settings", _settings)
    payload = ResponsesRequest(
        model="gpt-5.3-codex-spark",
        instructions="",
        input="x" * 500_000,
        previous_response_id="resp_previous",
    )

    request_policy.enforce_context_window(payload, registry=_registry())


def _oversized_input_items() -> list[dict[str, object]]:
    return [{"role": "user", "content": "x" * 500_000}]


def test_context_guard_exempts_terminal_compaction_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(request_policy, "get_settings", _settings)
    payload = ResponsesRequest(
        model="gpt-5.3-codex-spark",
        instructions="",
        input=[*_oversized_input_items(), {"type": "compaction_trigger"}],
    )

    request_policy.enforce_context_window(payload, registry=_registry())


def test_context_guard_rejects_non_terminal_compaction_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(request_policy, "get_settings", _settings)
    payload = ResponsesRequest(
        model="gpt-5.3-codex-spark",
        instructions="",
        input=[{"type": "compaction_trigger"}, *_oversized_input_items()],
    )

    with pytest.raises(ContextWindowExceededError, match="context window"):
        request_policy.enforce_context_window(payload, registry=_registry())


def test_context_guard_rejects_duplicated_compaction_trigger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(request_policy, "get_settings", _settings)
    payload = ResponsesRequest(
        model="gpt-5.3-codex-spark",
        instructions="",
        input=[
            {"type": "compaction_trigger"},
            *_oversized_input_items(),
            {"type": "compaction_trigger"},
        ],
    )

    with pytest.raises(ContextWindowExceededError, match="context window"):
        request_policy.enforce_context_window(payload, registry=_registry())
