from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import app.core.clients.codex_continuation as codex_continuation_module
from app.core.clients.codex_continuation import CodexContinuationConfig
from app.modules.proxy._service.websocket.continuation import _WebSocketContinuationFold
from app.modules.proxy._service.websocket.helpers import _folded_terminal_function_call_ids

pytestmark = pytest.mark.unit


class _ObservedCounter:
    def __init__(self) -> None:
        self.samples: list[dict[str, object]] = []

    def labels(self, **labels: str):
        sample: dict[str, object] = {"labels": dict(labels), "value": 0.0}
        self.samples.append(sample)

        def inc(amount: float = 1.0) -> None:
            sample["value"] = float(sample["value"]) + amount

        return SimpleNamespace(inc=inc)


@pytest.fixture
def decision_counter(monkeypatch: pytest.MonkeyPatch) -> _ObservedCounter:
    counter = _ObservedCounter()
    monkeypatch.setattr(codex_continuation_module, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(codex_continuation_module, "codex_continuation_decision_total", counter, raising=False)
    return counter


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


def _function_call_events(*, output_index: int, item_id: str, call_id: str, name: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "response.output_item.added",
            "output_index": output_index,
            "item": {"id": item_id, "type": "function_call", "call_id": call_id, "name": name, "arguments": ""},
        },
        {
            "type": "response.output_item.done",
            "output_index": output_index,
            "item": {
                "id": item_id,
                "type": "function_call",
                "status": "completed",
                "call_id": call_id,
                "name": name,
                "arguments": "{}",
            },
        },
    ]


def test_ws_fold_chained_turn_with_buffered_tool_call_stops_and_delivers(decision_counter: _ObservedCounter) -> None:
    # A chained hidden round would anchor on the truncated round's response,
    # where an emitted tool call sits unanswered — the upstream rejects that.
    # The fold must stop and deliver the tool call instead of continuing.
    fold = _WebSocketContinuationFold(
        CodexContinuationConfig(max_continue=3, rechunk_size=64),
        {
            "model": "gpt-5.5",
            "instructions": "solve",
            "input": [{"type": "function_call_output", "call_id": "call_prev", "output": "done"}],
            "previous_response_id": "resp_previous",
            "stream": True,
        },
    )

    round_one = [
        {"type": "response.created", "response": {"id": "resp_visible", "status": "in_progress", "output": []}},
        *_reasoning_events(output_index=0, item_id="rs_1", encrypted_content="enc1"),
        *_function_call_events(output_index=1, item_id="fc_1", call_id="call_next", name="shell"),
        _completed("resp_visible", input_tokens=100, output_tokens=600, reasoning_tokens=516),
    ]
    downstream, continuation, terminal = _drive(fold, round_one)

    assert continuation is None
    assert terminal is not None
    assert terminal["type"] == "response.completed"
    output_items = terminal["response"]["output"]
    assert any(item.get("type") == "function_call" and item.get("call_id") == "call_next" for item in output_items)
    flushed_call_ids = [
        event["item"]["call_id"]
        for event in downstream
        if event.get("type") == "response.output_item.done" and event.get("item", {}).get("type") == "function_call"
    ]
    assert flushed_call_ids == ["call_next"]
    assert terminal["response"]["metadata"]["proxy_stopped_reason"] == "buffered_tool_calls"
    assert decision_counter.samples == [
        {
            "labels": {"transport": "websocket", "decision": "buffered_tool_calls", "tier": "1"},
            "value": 1.0,
        }
    ]


def test_ws_fold_anchorless_turn_with_buffered_tool_call_stops_and_delivers(
    decision_counter: _ObservedCounter,
) -> None:
    # An anchorless full-history replay could technically continue past the
    # truncated round, but doing so would silently discard the buffered tool
    # call — real actionable output — and re-think, risking a duplicate
    # side-effect call. The fold must stop and deliver it, same as chained.
    fold = _WebSocketContinuationFold(
        CodexContinuationConfig(max_continue=3, rechunk_size=64),
        {
            "model": "gpt-5.5",
            "instructions": "solve",
            "input": [{"role": "user", "content": "question"}],
            "stream": True,
        },
    )

    round_one = [
        {"type": "response.created", "response": {"id": "resp_visible", "status": "in_progress", "output": []}},
        *_reasoning_events(output_index=0, item_id="rs_1", encrypted_content="enc1"),
        *_function_call_events(output_index=1, item_id="fc_1", call_id="call_next", name="shell"),
        _completed("resp_visible", input_tokens=100, output_tokens=600, reasoning_tokens=516),
    ]
    downstream, continuation, terminal = _drive(fold, round_one)

    assert continuation is None
    assert terminal is not None
    assert terminal["type"] == "response.completed"
    output_items = terminal["response"]["output"]
    assert any(item.get("type") == "function_call" and item.get("call_id") == "call_next" for item in output_items)
    flushed_call_ids = [
        event["item"]["call_id"]
        for event in downstream
        if event.get("type") == "response.output_item.done" and event.get("item", {}).get("type") == "function_call"
    ]
    assert flushed_call_ids == ["call_next"]
    assert terminal["response"]["metadata"]["proxy_stopped_reason"] == "buffered_tool_calls"
    assert decision_counter.samples == [
        {
            "labels": {"transport": "websocket", "decision": "buffered_tool_calls", "tier": "1"},
            "value": 1.0,
        }
    ]


def test_ws_fold_continues_truncated_round_then_reconstructs_final(decision_counter: _ObservedCounter) -> None:
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
    # chained turn's hidden round chains off the just-completed round's own
    # response id (the original anchor is consumed once the visible round
    # chains off it) and replays only that round's reasoning plus the marker.
    assert continuation is not None
    assert terminal1 is None
    assert continuation["previous_response_id"] == "resp_visible"
    assert continuation["include"] == ["reasoning.encrypted_content"]
    replay_input = continuation["input"]
    assert replay_input == [
        {"id": "rs_1", "type": "reasoning", "encrypted_content": "enc1"},
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Continue thinking..."}],
            "phase": "commentary",
        },
    ]
    down1_types = [event["type"] for event in down1]
    assert down1_types.count("response.created") == 1
    assert "response.completed" not in down1_types
    assert not any("partial answer" in str(event.get("delta", "")) for event in down1)
    assert decision_counter.samples == [
        {
            "labels": {"transport": "websocket", "decision": "continue", "tier": "1"},
            "value": 1.0,
        }
    ]

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
    # The non-truncated hidden round's terminal emits no decision sample.
    assert decision_counter.samples == [
        {
            "labels": {"transport": "websocket", "decision": "continue", "tier": "1"},
            "value": 1.0,
        }
    ]


def test_folded_terminal_function_call_ids_prune_only_delivered_calls() -> None:
    # Defense-in-depth invariant: the relay prunes pending-call tracking to
    # calls present in the folded terminal's delivered output. No fold mode
    # discards buffered tool calls anymore, but a regression that did must not
    # have the undelivered call treated as interrupted on the follow-up turn.
    terminal_payload = {
        "type": "response.completed",
        "response": {
            "id": "resp_folded",
            "status": "completed",
            "output": [
                {"id": "rs_1", "type": "reasoning"},
                {"id": "fc_1", "type": "function_call", "call_id": "call_delivered", "name": "shell"},
                {"id": "fc_2", "type": "function_call", "call_id": "", "name": "shell"},
                {"id": "msg_1", "type": "message", "role": "assistant", "content": []},
            ],
        },
    }

    assert _folded_terminal_function_call_ids(terminal_payload) == frozenset({"call_delivered"})
    assert _folded_terminal_function_call_ids({"type": "response.completed"}) == frozenset()


def test_ws_fold_passes_through_non_truncated_round(decision_counter: _ObservedCounter) -> None:
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
    assert decision_counter.samples == []
