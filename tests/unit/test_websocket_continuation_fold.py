from __future__ import annotations

from typing import Any

import pytest

from app.core.clients.codex_continuation import CodexContinuationConfig
from app.modules.proxy._service.websocket.continuation import _WebSocketContinuationFold

pytestmark = pytest.mark.unit


def _reasoning_events(*, output_index: int, item_id: str, encrypted_content: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "response.output_item.added",
            "output_index": output_index,
            "item": {"id": item_id, "type": "reasoning"},
        },
        {
            "type": "response.output_item.done",
            "output_index": output_index,
            "item": {"id": item_id, "type": "reasoning", "encrypted_content": encrypted_content},
        },
    ]


def _message_events(*, output_index: int, item_id: str, text: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "response.output_item.added",
            "output_index": output_index,
            "item": {"id": item_id, "type": "message", "role": "assistant", "content": []},
        },
        {
            "type": "response.output_text.delta",
            "output_index": output_index,
            "item_id": item_id,
            "content_index": 0,
            "delta": text,
        },
        {
            "type": "response.output_item.done",
            "output_index": output_index,
            "item": {
                "id": item_id,
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
        },
    ]


def _completed(response_id: str, *, input_tokens: int, output_tokens: int, reasoning_tokens: int) -> dict[str, Any]:
    return {
        "type": "response.completed",
        "response": {
            "id": response_id,
            "status": "completed",
            "output": [],
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
            },
        },
    }


def _drive(fold: _WebSocketContinuationFold, events: list[dict[str, Any]]):
    downstream: list[dict[str, Any]] = []
    continuation = None
    terminal = None
    for event in events:
        outcome = fold.process_event(event)
        downstream.extend(outcome.downstream)
        if outcome.continuation_request is not None:
            continuation = outcome.continuation_request
        if outcome.terminal_event is not None:
            terminal = outcome.terminal_event
    return downstream, continuation, terminal


def test_ws_fold_continues_truncated_round_then_reconstructs_final() -> None:
    fold = _WebSocketContinuationFold(
        CodexContinuationConfig(max_continue=1, rechunk_size=64),
        {
            "model": "gpt-5.5",
            "instructions": "solve",
            "input": [{"role": "user", "content": "question"}],
            "previous_response_id": "resp_previous",
            "stream": True,
        },
    )

    round_one = [
        {"type": "response.created", "response": {"id": "resp_visible", "status": "in_progress", "output": []}},
        *_reasoning_events(output_index=0, item_id="rs_1", encrypted_content="enc1"),
        *_message_events(output_index=1, item_id="msg_partial", text="partial answer"),
        _completed("resp_visible", input_tokens=100, output_tokens=600, reasoning_tokens=516),
    ]
    down1, continuation, terminal1 = _drive(fold, round_one)

    # The truncated round streams reasoning live but buffers/suppresses its final
    # answer and does not terminate; a continuation round is requested. A
    # chained turn's hidden round keeps the anchor: the incremental input only
    # resolves against the previous response's stored context.
    assert continuation is not None
    assert terminal1 is None
    assert continuation["previous_response_id"] == "resp_previous"
    assert continuation["include"] == ["reasoning.encrypted_content"]
    replay_input = continuation["input"]
    assert replay_input[0] == {"role": "user", "content": "question"}
    assert {"id": "rs_1", "type": "reasoning", "encrypted_content": "enc1"} in replay_input
    assert replay_input[-1] == {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "Continue thinking..."}],
        "phase": "commentary",
    }
    down1_types = [event["type"] for event in down1]
    assert down1_types.count("response.created") == 1
    assert "response.completed" not in down1_types
    assert not any("partial answer" in str(event.get("delta", "")) for event in down1)

    round_two = [
        {"type": "response.created", "response": {"id": "resp_hidden", "status": "in_progress", "output": []}},
        *_reasoning_events(output_index=0, item_id="rs_2", encrypted_content="enc2"),
        *_message_events(output_index=1, item_id="msg_final", text="final answer"),
        _completed("resp_hidden", input_tokens=120, output_tokens=20, reasoning_tokens=10),
    ]
    down2, continuation2, terminal2 = _drive(fold, round_two)

    assert continuation2 is None
    assert terminal2 is not None
    # Hidden round does not re-emit response.created.
    assert all(event["type"] != "response.created" for event in down2)
    all_events = [*down1, *down2]
    types = [event["type"] for event in all_events]
    assert types.count("response.created") == 1
    assert types.count("response.completed") == 1
    deltas = "".join(str(e.get("delta", "")) for e in all_events if e.get("type") == "response.output_text.delta")
    assert "final answer" in deltas
    assert "partial answer" not in deltas

    # Continuous, monotonic sequence numbers across folded rounds.
    seqs = [event["sequence_number"] for event in all_events]
    assert seqs == list(range(len(all_events)))

    response = terminal2["response"]
    assert response["id"] == "resp_visible"
    metadata = response["metadata"]
    assert metadata["proxy_billed_usage"]["input_tokens"] == 220
    assert metadata["proxy_billed_usage"]["output_tokens"] == 620
    assert metadata["proxy_rounds"] == [
        {"round": 1, "reasoning_tokens": 516, "n": 1},
        {"round": 2, "reasoning_tokens": 10, "n": None},
    ]


def test_ws_fold_passes_through_non_truncated_round() -> None:
    fold = _WebSocketContinuationFold(
        CodexContinuationConfig(rechunk_size=64),
        {"model": "gpt-5.5", "input": [{"role": "user", "content": "hi"}], "stream": True},
    )
    events = [
        {"type": "response.created", "response": {"id": "resp_ok", "status": "in_progress", "output": []}},
        *_reasoning_events(output_index=0, item_id="rs_1", encrypted_content="enc1"),
        *_message_events(output_index=1, item_id="msg_ok", text="all done"),
        _completed("resp_ok", input_tokens=100, output_tokens=200, reasoning_tokens=300),
    ]
    downstream, continuation, terminal = _drive(fold, events)
    assert continuation is None
    assert terminal is not None
    deltas = "".join(str(e.get("delta", "")) for e in downstream if e.get("type") == "response.output_text.delta")
    assert "all done" in deltas
    assert [e["type"] for e in downstream].count("response.completed") == 1
    assert terminal["response"]["metadata"]["proxy_billed_usage"]["output_tokens"] == 200
