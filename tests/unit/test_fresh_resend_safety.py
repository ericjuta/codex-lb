from __future__ import annotations

from typing import cast

from app.core.types import JsonValue
from app.modules.proxy.fresh_resend_safety import (
    project_responses_input_for_fresh_resend,
    responses_input_suffix_matches_pending_tool_calls,
    responses_input_suffix_retains_prior_output,
)


def _function_pair(call_id: str) -> list[JsonValue]:
    return [
        {
            "type": "function_call",
            "call_id": call_id,
            "name": "lookup",
            "arguments": "{}",
            "status": "completed",
        },
        {
            "type": "function_call_output",
            "call_id": call_id,
            "output": "ok",
            "status": "completed",
        },
    ]


def test_projection_removes_response_owned_items_and_ids() -> None:
    items: list[JsonValue] = [
        {"type": "message", "role": "user", "content": "first"},
        {"type": "reasoning", "id": "rs_1", "summary": []},
        {
            "type": "message",
            "id": "msg_1",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "answer"}],
        },
        {"type": "message", "role": "user", "content": "next"},
    ]

    projection = project_responses_input_for_fresh_resend(items, stored_count=2)

    assert projection is not None
    assert projection.stored_prefix_count == 1
    assert projection.input_items[1] == {
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": "answer"}],
    }


def test_retained_output_suffix_requires_completed_assistant_before_fresh_input() -> None:
    prefix: list[JsonValue] = [{"type": "message", "role": "user", "content": "first"}]
    retained: list[JsonValue] = [
        {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "answer"}],
        },
        {"type": "message", "role": "user", "content": "next"},
    ]

    assert responses_input_suffix_retains_prior_output(prefix + retained, stored_count=1)
    assert not responses_input_suffix_retains_prior_output(
        prefix + [{"type": "message", "role": "user", "content": "next"}],
        stored_count=1,
    )
    assert not responses_input_suffix_retains_prior_output(
        prefix + list(reversed(retained)),
        stored_count=1,
    )


def test_retained_output_suffix_rejects_incomplete_tool_sequence() -> None:
    items: list[JsonValue] = [
        {"type": "message", "role": "user", "content": "first"},
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "lookup",
            "arguments": "{}",
            "status": "completed",
        },
        {
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "answer"}],
        },
        {"type": "message", "role": "user", "content": "next"},
    ]

    assert not responses_input_suffix_retains_prior_output(items, stored_count=1)


def test_direct_tool_loop_must_exactly_settle_manifest() -> None:
    prefix: list[JsonValue] = [{"type": "message", "role": "user", "content": "first"}]
    suffix = _function_pair("call_1") + _function_pair("call_2")
    manifest = {"call_1": "function_call", "call_2": "function_call"}

    assert responses_input_suffix_matches_pending_tool_calls(
        prefix + suffix,
        stored_count=1,
        pending_tool_calls=manifest,
    )
    assert not responses_input_suffix_matches_pending_tool_calls(
        prefix + _function_pair("call_1"),
        stored_count=1,
        pending_tool_calls=manifest,
    )


def test_direct_tool_loop_rejects_prefix_collision_and_extra_input() -> None:
    manifest = {"call_1": "function_call"}
    prefix_with_collision: list[JsonValue] = [{"type": "computer_call", "call_id": "call_1", "status": "completed"}]

    assert not responses_input_suffix_matches_pending_tool_calls(
        prefix_with_collision + _function_pair("call_1"),
        stored_count=1,
        pending_tool_calls=manifest,
    )
    assert not responses_input_suffix_matches_pending_tool_calls(
        [{"type": "message", "role": "user", "content": "first"}]
        + _function_pair("call_1")
        + [{"type": "message", "role": "user", "content": "extra"}],
        stored_count=1,
        pending_tool_calls=manifest,
    )


def test_direct_tool_loop_rejects_duplicate_or_non_direct_calls() -> None:
    prefix: list[JsonValue] = [{"type": "message", "role": "user", "content": "first"}]
    duplicate_suffix = _function_pair("call_1") + _function_pair("call_1")
    non_direct_suffix = _function_pair("call_1")
    non_direct_call = cast(dict[str, JsonValue], non_direct_suffix[0])
    non_direct_call["caller"] = {"type": "mcp"}

    assert not responses_input_suffix_matches_pending_tool_calls(
        prefix + duplicate_suffix,
        stored_count=1,
        pending_tool_calls={"call_1": "function_call"},
    )
    assert not responses_input_suffix_matches_pending_tool_calls(
        prefix + non_direct_suffix,
        stored_count=1,
        pending_tool_calls={"call_1": "function_call"},
    )
