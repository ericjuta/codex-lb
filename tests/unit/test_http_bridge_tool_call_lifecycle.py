from __future__ import annotations

import pytest

from app.modules.proxy._service.http_bridge.upstream_events import (
    _durable_pending_tool_call_manifest,
    _record_http_bridge_tool_call_lifecycle,
)
from app.modules.proxy._service.support import _WebSocketRequestState

pytestmark = pytest.mark.unit


def _request_state() -> _WebSocketRequestState:
    return _WebSocketRequestState(
        request_id="req_1",
        model=None,
        service_tier=None,
        reasoning_effort=None,
        api_key_reservation=None,
        started_at=0.0,
    )


def _record(state: _WebSocketRequestState, event_type: str, item_type: str, call_id: str) -> None:
    _record_http_bridge_tool_call_lifecycle(
        state,
        event_type=event_type,
        payload={"item": {"type": item_type, "call_id": call_id}},
    )


def _completed(*items: tuple[str, str]) -> dict:
    return {"response": {"output": [{"type": item_type, "call_id": call_id} for item_type, call_id in items]}}


def test_complete_supported_lifecycle_produces_manifest() -> None:
    state = _request_state()
    _record(state, "response.output_item.added", "function_call", "call_1")
    _record(state, "response.output_item.done", "function_call", "call_1")

    assert _durable_pending_tool_call_manifest(
        state,
        _completed(("function_call", "call_1")),
    ) == {"call_1": "function_call"}


@pytest.mark.parametrize("missing_event", ["added", "done"])
def test_incomplete_lifecycle_has_unknown_manifest(missing_event: str) -> None:
    state = _request_state()
    if missing_event != "added":
        _record(state, "response.output_item.added", "function_call", "call_1")
    if missing_event != "done":
        _record(state, "response.output_item.done", "function_call", "call_1")

    assert (
        _durable_pending_tool_call_manifest(
            state,
            _completed(("function_call", "call_1")),
        )
        is None
    )


def test_duplicate_or_mismatched_lifecycle_has_unknown_manifest() -> None:
    duplicate = _request_state()
    _record(duplicate, "response.output_item.added", "function_call", "call_1")
    _record(duplicate, "response.output_item.added", "function_call", "call_1")
    _record(duplicate, "response.output_item.done", "function_call", "call_1")
    assert (
        _durable_pending_tool_call_manifest(
            duplicate,
            _completed(("function_call", "call_1")),
        )
        is None
    )

    mismatched = _request_state()
    _record(mismatched, "response.output_item.added", "function_call", "call_1")
    _record(mismatched, "response.output_item.done", "custom_tool_call", "call_1")
    assert (
        _durable_pending_tool_call_manifest(
            mismatched,
            _completed(("function_call", "call_1")),
        )
        is None
    )


def test_terminal_only_tool_call_has_unknown_manifest() -> None:
    assert (
        _durable_pending_tool_call_manifest(
            _request_state(),
            _completed(("function_call", "call_1")),
        )
        is None
    )


def test_parallel_unsupported_call_invalidates_supported_manifest() -> None:
    state = _request_state()
    _record(state, "response.output_item.added", "function_call", "call_1")
    _record(state, "response.output_item.done", "function_call", "call_1")
    _record(state, "response.output_item.added", "computer_call", "computer_1")
    _record(state, "response.output_item.done", "computer_call", "computer_1")

    assert (
        _durable_pending_tool_call_manifest(
            state,
            _completed(("function_call", "call_1"), ("computer_call", "computer_1")),
        )
        is None
    )
