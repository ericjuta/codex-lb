from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.openai.requests import ResponsesRequest
from app.core.types import JsonValue
from app.db.models import HttpBridgeSessionState
from app.modules.proxy._service.http_bridge.streaming import _classify_durable_full_resend
from app.modules.proxy.durable_bridge_coordinator import DurableBridgeLookup
from app.modules.proxy.service import _fingerprint_input_items

pytestmark = pytest.mark.unit


def _lookup(
    prefix: list[JsonValue],
    *,
    pending_tool_calls: dict[str, str] | None,
) -> DurableBridgeLookup:
    return DurableBridgeLookup(
        session_id="session-1",
        canonical_kind="session_header",
        canonical_key="sid-1",
        api_key_scope="__anonymous__",
        account_id="account-1",
        owner_instance_id=None,
        owner_epoch=1,
        lease_expires_at=datetime.now(timezone.utc),
        state=HttpBridgeSessionState.ACTIVE,
        latest_turn_state="turn-1",
        latest_response_id="resp-1",
        latest_input_item_count=len(prefix),
        latest_input_full_fingerprint=_fingerprint_input_items(prefix),
        latest_pending_tool_calls=pending_tool_calls,
    )


def _payload(items: list[JsonValue]) -> ResponsesRequest:
    return ResponsesRequest.model_validate({"model": "gpt-5.4", "instructions": "test", "input": items})


def test_classifies_retained_assistant_output_as_safe_fresh_context() -> None:
    prefix: list[JsonValue] = [{"role": "user", "content": [{"type": "input_text", "text": "old question"}]}]
    items: list[JsonValue] = [
        *prefix,
        {
            "role": "assistant",
            "content": [{"type": "output_text", "text": "old answer"}],
        },
        {"role": "user", "content": [{"type": "input_text", "text": "new question"}]},
    ]

    count, fingerprint, safe = _classify_durable_full_resend(
        _payload(items),
        _lookup(prefix, pending_tool_calls=None),
    )

    assert count == 1
    assert fingerprint == _fingerprint_input_items(prefix)
    assert safe is True


def test_classifies_only_exact_complete_pending_tool_loop_as_safe() -> None:
    prefix: list[JsonValue] = [{"role": "user", "content": [{"type": "input_text", "text": "run tool"}]}]
    settled_call: list[JsonValue] = [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "lookup",
            "arguments": "{}",
        },
        {"type": "function_call_output", "call_id": "call_1", "output": "done"},
    ]

    exact = _classify_durable_full_resend(
        _payload([*prefix, *settled_call]),
        _lookup(prefix, pending_tool_calls={"call_1": "function_call"}),
    )
    omitted = _classify_durable_full_resend(
        _payload([*prefix, *settled_call]),
        _lookup(
            prefix,
            pending_tool_calls={"call_1": "function_call", "call_2": "function_call"},
        ),
    )
    legacy = _classify_durable_full_resend(
        _payload([*prefix, *settled_call]),
        _lookup(prefix, pending_tool_calls=None),
    )

    assert exact[2] is True
    assert omitted[2] is False
    assert legacy[2] is False


def test_prefix_mismatch_is_not_trimmable_or_safe() -> None:
    stored_prefix: list[JsonValue] = [{"role": "user", "content": [{"type": "input_text", "text": "stored"}]}]
    payload_items: list[JsonValue] = [
        {"role": "user", "content": [{"type": "input_text", "text": "different"}]},
        {
            "role": "assistant",
            "content": [{"type": "output_text", "text": "answer"}],
        },
        {"role": "user", "content": [{"type": "input_text", "text": "next"}]},
    ]

    assert _classify_durable_full_resend(
        _payload(payload_items),
        _lookup(stored_prefix, pending_tool_calls=None),
    ) == (None, None, False)
