from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, cast

import pytest

import app.core.clients.codex_continuation as codex_continuation_module
from app.core.clients.codex_continuation import (
    CodexContinuationConfig,
    _record_continuation_decision,
    fold_responses_stream_with_codex_continuation,
    should_apply_codex_continuation,
)
from app.core.types import JsonObject, JsonValue
from app.core.utils.sse import format_sse_event, parse_sse_data_json

pytestmark = pytest.mark.unit


class _ObservedCounter:
    def __init__(self) -> None:
        self.samples: list[dict[str, object]] = []

    def labels(self, **labels: str):
        sample: dict[str, object] = {"labels": dict(labels), "value": 0.0}
        self.samples.append(sample)

        def inc(amount: float = 1.0) -> None:
            sample["value"] = cast(float, sample["value"]) + amount

        return SimpleNamespace(inc=inc)


@pytest.fixture
def decision_counter(monkeypatch: pytest.MonkeyPatch) -> _ObservedCounter:
    counter = _ObservedCounter()
    monkeypatch.setattr(codex_continuation_module, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(codex_continuation_module, "codex_continuation_decision_total", counter, raising=False)
    return counter


def _event(payload: dict[str, JsonValue]) -> str:
    return format_sse_event(payload)


def _created(response_id: str) -> dict[str, JsonValue]:
    return {
        "type": "response.created",
        "response": {
            "id": response_id,
            "status": "in_progress",
            "output": [],
        },
    }


def _reasoning_events(*, output_index: int, item_id: str, encrypted_content: str) -> list[dict[str, JsonValue]]:
    item: dict[str, JsonValue] = {
        "id": item_id,
        "type": "reasoning",
        "encrypted_content": encrypted_content,
    }
    return [
        {
            "type": "response.output_item.added",
            "output_index": output_index,
            "item": {"id": item_id, "type": "reasoning"},
        },
        {
            "type": "response.output_item.done",
            "output_index": output_index,
            "item": item,
        },
    ]


def _message_events(*, output_index: int, item_id: str, text: str) -> list[dict[str, JsonValue]]:
    return [
        {
            "type": "response.output_item.added",
            "output_index": output_index,
            "item": {
                "id": item_id,
                "type": "message",
                "role": "assistant",
                "content": [],
            },
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


def _function_call_events(*, output_index: int, item_id: str, call_id: str, name: str) -> list[dict[str, JsonValue]]:
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


def _completed(
    response_id: str,
    *,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
) -> dict[str, JsonValue]:
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
                "input_tokens_details": {"cached_tokens": 25},
                "output_tokens_details": {"reasoning_tokens": reasoning_tokens},
            },
        },
    }


async def _collect_events(chunks: AsyncIterator[str]) -> list[dict[str, JsonValue]]:
    events: list[dict[str, JsonValue]] = []
    async for chunk in chunks:
        payload = parse_sse_data_json(chunk)
        if payload is not None:
            events.append(payload)
    return events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("created_tier", "terminal_tier"),
    [
        pytest.param("auto", "priority", id="created-auto-terminal-priority"),
        pytest.param("auto", "default", id="created-auto-terminal-default"),
        pytest.param(None, "priority", id="created-absent-terminal-priority"),
        pytest.param("auto", None, id="created-auto-terminal-omitted"),
    ],
)
async def test_fold_responses_stream_continues_truncated_round_and_reuses_payload_shape(
    decision_counter: _ObservedCounter,
    monkeypatch: pytest.MonkeyPatch,
    created_tier: str | None,
    terminal_tier: str | None,
) -> None:
    base_payload: JsonObject = {
        "model": "gpt-5.5",
        "instructions": "solve",
        "input": [{"role": "user", "content": "question"}],
        "previous_response_id": "resp_previous",
        "service_tier": "priority",
        "stream": True,
    }
    base_payload_snapshot = deepcopy(base_payload)
    first_created = _created("resp_visible")
    created_response = cast(dict[str, JsonValue], first_created["response"])
    created_response["model"] = "gpt-5.5"
    created_response["metadata"] = {"user_label": "visible"}
    if created_tier is not None:
        created_response["service_tier"] = created_tier
    first_terminal = _completed("resp_visible", input_tokens=100, output_tokens=600, reasoning_tokens=516)
    cast(dict[str, JsonValue], first_terminal["response"])["service_tier"] = "priority"
    hidden_created = _created("resp_hidden")
    cast(dict[str, JsonValue], hidden_created["response"])["service_tier"] = "flex"
    hidden_terminal = _completed("resp_hidden", input_tokens=120, output_tokens=20, reasoning_tokens=10)
    if terminal_tier is not None:
        cast(dict[str, JsonValue], hidden_terminal["response"])["service_tier"] = terminal_tier
    round_events = [
        [
            first_created,
            *_reasoning_events(output_index=0, item_id="rs_1", encrypted_content="enc1"),
            *_message_events(output_index=1, item_id="msg_partial", text="partial answer"),
            first_terminal,
        ],
        [
            hidden_created,
            *_reasoning_events(output_index=0, item_id="rs_2", encrypted_content="enc2"),
            *_message_events(output_index=1, item_id="msg_final", text="final answer"),
            hidden_terminal,
        ],
    ]
    reconstruction_inputs: list[tuple[dict[str, Any] | None, dict[str, Any] | None]] = []
    reconstruction_snapshots: list[tuple[dict[str, Any] | None, dict[str, Any] | None]] = []
    real_reconstruct_terminal = codex_continuation_module._reconstruct_terminal

    def observe_reconstruct_terminal(
        terminal: dict[str, Any] | None,
        base_response: dict[str, Any] | None,
        output_items: list[dict[str, Any]],
        usage: dict[str, Any],
        seq: int,
        rounds: list[dict[str, Any]],
        stopped_reason: str | None,
        billed_usage: dict[str, Any] | None,
    ) -> dict[str, Any]:
        reconstruction_inputs.append((terminal, base_response))
        reconstruction_snapshots.append((deepcopy(terminal), deepcopy(base_response)))
        return real_reconstruct_terminal(
            terminal,
            base_response,
            output_items,
            usage,
            seq,
            rounds,
            stopped_reason,
            billed_usage,
        )

    monkeypatch.setattr(codex_continuation_module, "_reconstruct_terminal", observe_reconstruct_terminal)
    opened_payloads: list[JsonObject] = []

    async def open_round(payload: JsonObject) -> AsyncGenerator[str, None]:
        opened_payloads.append(payload)
        events = round_events[len(opened_payloads) - 1]
        for event in events:
            yield _event(event)

    events = await _collect_events(
        fold_responses_stream_with_codex_continuation(
            base_payload=base_payload,
            open_round=open_round,
            config=CodexContinuationConfig(max_continue=1, rechunk_size=64),
        )
    )

    assert len(opened_payloads) == 2
    assert opened_payloads[0]["service_tier"] == "priority"
    assert opened_payloads[1]["service_tier"] == "priority"
    assert base_payload == base_payload_snapshot
    assert opened_payloads[0]["previous_response_id"] == "resp_previous"
    assert opened_payloads[0]["include"] == ["reasoning.encrypted_content"]
    assert "previous_response_id" not in opened_payloads[1]
    assert len(reconstruction_inputs) == 1
    captured_terminal, captured_created = reconstruction_inputs[0]
    terminal_snapshot, created_snapshot = reconstruction_snapshots[0]
    assert captured_terminal == terminal_snapshot
    assert captured_created == created_snapshot
    assert captured_terminal is not None
    assert captured_created is not None
    captured_terminal_response = cast(dict[str, JsonValue], captured_terminal["response"])
    captured_created_response = cast(dict[str, JsonValue], captured_created)
    assert captured_terminal_response["id"] == "resp_hidden"
    if terminal_tier is None:
        assert "service_tier" not in captured_terminal_response
    else:
        assert captured_terminal_response["service_tier"] == terminal_tier
    assert captured_created_response["id"] == "resp_visible"
    if created_tier is None:
        assert "service_tier" not in captured_created_response
    else:
        assert captured_created_response["service_tier"] == created_tier
    replay_input = cast(list[JsonValue], opened_payloads[1]["input"])
    assert replay_input[0] == {"role": "user", "content": "question"}
    assert replay_input[1] == {
        "id": "rs_1",
        "type": "reasoning",
        "encrypted_content": "enc1",
    }
    assert replay_input[2] == {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "Continue thinking..."}],
        "phase": "commentary",
    }

    event_types = [event["type"] for event in events]
    assert event_types.count("response.created") == 1
    assert event_types.count("response.completed") == 1
    assert event_types.count("response.output_item.done") == 3
    assert [event["sequence_number"] for event in events] == list(range(len(events)))
    assert events[0]["type"] == "response.created"
    emitted_created = cast(dict[str, JsonValue], events[0]["response"])
    if created_tier is None:
        assert "service_tier" not in emitted_created
    else:
        assert emitted_created["service_tier"] == created_tier

    deltas = "".join(
        str(event.get("delta", "")) for event in events if event.get("type") == "response.output_text.delta"
    )
    assert "final answer" in deltas
    assert "partial answer" not in deltas

    terminal = events[-1]
    response = cast(dict[str, JsonValue], terminal["response"])
    assert response["id"] == "resp_visible"
    assert response["model"] == "gpt-5.5"
    if terminal_tier is None:
        assert "service_tier" not in response
    else:
        assert response["service_tier"] == terminal_tier
    metadata = cast(dict[str, JsonValue], response["metadata"])
    assert metadata["user_label"] == "visible"
    assert metadata["proxy_rounds"] == [
        {"round": 1, "reasoning_tokens": 516, "n": 1},
        {"round": 2, "reasoning_tokens": 10, "n": None},
    ]
    assert metadata["proxy_billed_usage"] == {
        "input_tokens": 220,
        "output_tokens": 620,
        "total_tokens": 840,
        "input_tokens_details": {"cached_tokens": 50},
        "output_tokens_details": {"reasoning_tokens": 526},
    }
    usage = cast(dict[str, JsonValue], response["usage"])
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 536
    assert usage["total_tokens"] == 636
    assert usage["output_tokens_details"] == {"reasoning_tokens": 526}

    # Round 1 hits the truncation fingerprint and continues; round 2 does not
    # (reasoning_tokens=10) and emits no decision sample.
    assert decision_counter.samples == [
        {
            "labels": {
                "transport": "http",
                "decision": "continue",
                "tier": "1",
                "client": "unknown",
                "effort": "unknown",
            },
            "value": 1.0,
        }
    ]


@pytest.mark.asyncio
async def test_fold_responses_stream_hidden_eof_synthetic_terminal_omits_service_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_payload: JsonObject = {
        "model": "gpt-5.5",
        "input": [{"role": "user", "content": "question"}],
        "service_tier": "priority",
        "stream": True,
    }
    synthetic_inputs: list[dict[str, Any] | None] = []
    synthetic_snapshots: list[dict[str, Any] | None] = []
    real_synthetic_incomplete = codex_continuation_module._synthetic_incomplete

    def observe_synthetic_incomplete(
        base_response: dict[str, Any] | None,
        output_items: list[dict[str, Any]],
        usage: dict[str, Any],
        seq: int,
        reason: str,
        rounds: list[dict[str, Any]],
        billed_usage: dict[str, Any] | None,
    ) -> dict[str, Any]:
        synthetic_inputs.append(base_response)
        synthetic_snapshots.append(deepcopy(base_response))
        return real_synthetic_incomplete(
            base_response,
            output_items,
            usage,
            seq,
            reason,
            rounds,
            billed_usage,
        )

    monkeypatch.setattr(codex_continuation_module, "_synthetic_incomplete", observe_synthetic_incomplete)
    opened_payloads: list[JsonObject] = []

    async def open_round(payload: JsonObject) -> AsyncGenerator[str, None]:
        opened_payloads.append(payload)
        if len(opened_payloads) != 1:
            return

        created = _created("resp_visible")
        created_response = cast(dict[str, JsonValue], created["response"])
        created_response["model"] = "gpt-5.5"
        created_response["metadata"] = {"user_label": "visible"}
        created_response["service_tier"] = "auto"
        yield _event(created)
        for event in _reasoning_events(output_index=0, item_id="rs_1", encrypted_content="enc1"):
            yield _event(event)
        completed = _completed("resp_visible", input_tokens=100, output_tokens=600, reasoning_tokens=516)
        cast(dict[str, JsonValue], completed["response"])["service_tier"] = "default"
        yield _event(completed)

    events = await _collect_events(
        fold_responses_stream_with_codex_continuation(
            base_payload=base_payload,
            open_round=open_round,
            config=CodexContinuationConfig(max_continue=1, rechunk_size=64),
        )
    )

    assert len(opened_payloads) == 2
    assert len(synthetic_inputs) == 1
    captured_created = synthetic_inputs[0]
    assert captured_created == synthetic_snapshots[0]
    assert captured_created is not None
    assert captured_created["service_tier"] == "auto"
    assert opened_payloads[0]["service_tier"] == "priority"
    assert opened_payloads[1]["service_tier"] == "priority"
    assert "previous_response_id" not in opened_payloads[1]
    assert [event["type"] for event in events] == [
        "response.created",
        "response.output_item.added",
        "response.output_item.done",
        "response.incomplete",
    ]
    assert [event["sequence_number"] for event in events] == list(range(len(events)))
    assert cast(dict[str, JsonValue], events[0]["response"])["service_tier"] == "auto"

    terminal = events[-1]
    assert terminal["type"] == "response.incomplete"
    response = cast(dict[str, JsonValue], terminal["response"])
    assert response["id"] == "resp_visible"
    assert response["model"] == "gpt-5.5"
    assert "service_tier" not in response
    assert response["status"] == "incomplete"
    assert response["incomplete_details"] == {"reason": "upstream_eof"}
    assert response["output"] == [
        {
            "id": "rs_1",
            "type": "reasoning",
            "encrypted_content": "enc1",
        }
    ]
    assert events[2]["item"] == cast(list[JsonValue], response["output"])[0]
    assert response["usage"] == {
        "input_tokens": 100,
        "output_tokens": 516,
        "total_tokens": 616,
        "input_tokens_details": {"cached_tokens": 25},
        "output_tokens_details": {"reasoning_tokens": 516},
    }
    metadata = cast(dict[str, JsonValue], response["metadata"])
    assert metadata["user_label"] == "visible"
    assert metadata["proxy_stopped_reason"] == "upstream_eof"
    assert metadata["proxy_rounds"] == [
        {"round": 1, "reasoning_tokens": 516, "n": 1},
        {"round": 2, "reasoning_tokens": None, "n": None},
    ]
    assert metadata["proxy_billed_usage"] == {
        "input_tokens": 100,
        "output_tokens": 600,
        "total_tokens": 700,
        "input_tokens_details": {"cached_tokens": 25},
        "output_tokens_details": {"reasoning_tokens": 516},
    }


@pytest.mark.asyncio
async def test_fold_responses_stream_stops_and_delivers_truncated_round_tool_calls(
    decision_counter: _ObservedCounter,
) -> None:
    # A truncated round that emitted a client-answered tool call must not be
    # continued past: the anchorless replay would discard the call and
    # re-think, risking a duplicate side-effect call. The fold stops, flushes
    # the buffered call, and reports the overriding stopped reason.
    opened_payloads: list[JsonObject] = []

    async def open_round(payload: JsonObject) -> AsyncGenerator[str, None]:
        opened_payloads.append(payload)
        yield _event(_created("resp_visible"))
        for event in _reasoning_events(output_index=0, item_id="rs_1", encrypted_content="enc1"):
            yield _event(event)
        for event in _function_call_events(output_index=1, item_id="fc_1", call_id="call_next", name="shell"):
            yield _event(event)
        yield _event(_completed("resp_visible", input_tokens=100, output_tokens=600, reasoning_tokens=516))

    events = await _collect_events(
        fold_responses_stream_with_codex_continuation(
            base_payload={
                "model": "gpt-5.5",
                "instructions": "solve",
                "input": [{"role": "user", "content": "question"}],
                "stream": True,
            },
            open_round=open_round,
            config=CodexContinuationConfig(max_continue=3, rechunk_size=64),
        )
    )

    # No hidden continuation round is opened.
    assert len(opened_payloads) == 1

    terminal = events[-1]
    assert terminal["type"] == "response.completed"
    response = cast(dict[str, JsonValue], terminal["response"])
    output_items = cast(list[dict[str, JsonValue]], response["output"])
    assert any(item.get("type") == "function_call" and item.get("call_id") == "call_next" for item in output_items)
    delivered_call_ids = [
        cast(dict[str, JsonValue], event["item"])["call_id"]
        for event in events
        if event.get("type") == "response.output_item.done"
        and cast(dict[str, JsonValue], event.get("item", {})).get("type") == "function_call"
    ]
    assert delivered_call_ids == ["call_next"]
    metadata = cast(dict[str, JsonValue], response["metadata"])
    assert metadata["proxy_stopped_reason"] == "buffered_tool_calls"
    assert [event["sequence_number"] for event in events] == list(range(len(events)))
    assert decision_counter.samples == [
        {
            "labels": {
                "transport": "http",
                "decision": "buffered_tool_calls",
                "tier": "1",
                "client": "unknown",
                "effort": "unknown",
            },
            "value": 1.0,
        }
    ]


@pytest.mark.asyncio
async def test_fold_responses_stream_counts_terminal_stop_decision(
    decision_counter: _ObservedCounter,
) -> None:
    # min_n=2 leaves tier 1 outside the continuation window, so the truncated
    # round terminates the fold with a tier_out_of_window stop decision.
    async def open_round(payload: JsonObject) -> AsyncGenerator[str, None]:
        del payload
        yield _event(_created("resp_stop"))
        for event in _reasoning_events(output_index=0, item_id="rs_stop", encrypted_content="enc_stop"):
            yield _event(event)
        yield _event(_completed("resp_stop", input_tokens=50, output_tokens=550, reasoning_tokens=516))

    events = await _collect_events(
        fold_responses_stream_with_codex_continuation(
            base_payload={"model": "gpt-5.5", "instructions": "solve", "input": [], "stream": True},
            open_round=open_round,
            config=CodexContinuationConfig(min_n=2, rechunk_size=64),
        )
    )

    assert events[-1]["type"] == "response.completed"
    assert decision_counter.samples == [
        {
            "labels": {
                "transport": "http",
                "decision": "tier_out_of_window",
                "tier": "1",
                "client": "unknown",
                "effort": "unknown",
            },
            "value": 1.0,
        }
    ]


def test_record_continuation_decision_caps_tier_label(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = _ObservedCounter()
    monkeypatch.setattr(codex_continuation_module, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(codex_continuation_module, "codex_continuation_decision_total", counter, raising=False)

    _record_continuation_decision(transport="http", decision="continue", tier=3)
    _record_continuation_decision(transport="websocket", decision="max_continue", tier=11)

    assert [sample["labels"] for sample in counter.samples] == [
        {"transport": "http", "decision": "continue", "tier": "3", "client": "unknown", "effort": "unknown"},
        {"transport": "websocket", "decision": "max_continue", "tier": "10+", "client": "unknown", "effort": "unknown"},
    ]


def test_record_continuation_decision_noops_without_prometheus(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = _ObservedCounter()
    monkeypatch.setattr(codex_continuation_module, "PROMETHEUS_AVAILABLE", False)
    monkeypatch.setattr(codex_continuation_module, "codex_continuation_decision_total", counter, raising=False)

    _record_continuation_decision(transport="http", decision="continue", tier=1)

    assert counter.samples == []


@pytest.mark.asyncio
async def test_fold_responses_stream_drains_terminal_round_before_returning() -> None:
    round_drained = False

    async def open_round(payload: JsonObject) -> AsyncGenerator[str, None]:
        nonlocal round_drained
        del payload
        try:
            yield _event(_completed("resp_terminal", input_tokens=5, output_tokens=7, reasoning_tokens=3))
            yield "data: [DONE]\n\n"
        finally:
            round_drained = True

    chunks = [
        chunk
        async for chunk in fold_responses_stream_with_codex_continuation(
            base_payload={"model": "gpt-5.5", "input": [], "stream": True},
            open_round=open_round,
            config=CodexContinuationConfig(),
        )
    ]

    assert round_drained is True
    assert chunks[-1] == "data: [DONE]\n\n"
    terminal = parse_sse_data_json(chunks[-2])
    assert terminal is not None
    assert terminal["type"] == "response.completed"


def test_should_apply_codex_continuation_respects_explicit_reasoning_opt_out() -> None:
    config = CodexContinuationConfig()

    assert should_apply_codex_continuation(
        {"model": "gpt-5.5", "instructions": "hi", "input": [], "stream": True},
        config,
    )
    assert not should_apply_codex_continuation(
        {
            "model": "gpt-5.5",
            "instructions": "hi",
            "input": [],
            "stream": True,
            "reasoning": False,
        },
        config,
    )


def test_continuation_client_label_bounds_and_falls_back() -> None:
    assert codex_continuation_module.continuation_client_label("nanocodex") == "nanocodex"
    assert codex_continuation_module.continuation_client_label("Codex_CLI-RS") == "codex_cli-rs"
    assert codex_continuation_module.continuation_client_label(None) == "unknown"
    assert codex_continuation_module.continuation_client_label("") == "unknown"
    assert codex_continuation_module.continuation_client_label("!!!$$$") == "unknown"
    hostile = "a" * 100 + "$(rm -rf /)"
    bounded = codex_continuation_module.continuation_client_label(hostile)
    assert bounded == "a" * 32
    assert len(bounded) <= 32


def test_continuation_effort_label_closed_set() -> None:
    extract = codex_continuation_module.continuation_effort_label
    assert extract({"reasoning": {"effort": "high"}}) == "high"
    assert extract({"reasoning": {"effort": "xhigh"}}) == "xhigh"
    assert extract({"reasoning": {"effort": "turbo"}}) == "unknown"
    assert extract({"reasoning": {}}) == "unknown"
    assert extract({"reasoning": "high"}) == "unknown"
    assert extract({}) == "unknown"


@pytest.fixture
def reasoning_tokens_counter(monkeypatch: pytest.MonkeyPatch) -> _ObservedCounter:
    counter = _ObservedCounter()
    monkeypatch.setattr(codex_continuation_module, "PROMETHEUS_AVAILABLE", True)
    monkeypatch.setattr(
        codex_continuation_module,
        "codex_continuation_reasoning_tokens_total",
        counter,
        raising=False,
    )
    return counter


def test_reasoning_token_outcomes_classify_recovered_forfeited_natural(
    reasoning_tokens_counter: _ObservedCounter,
) -> None:
    record = codex_continuation_module._record_continuation_reasoning_tokens
    record(
        transport="http",
        decision="continue",
        should_continue_round=True,
        reasoning_token_count=1034,
        client_label="nanocodex",
        effort_label="high",
    )
    record(
        transport="websocket",
        decision="max_continue",
        should_continue_round=False,
        reasoning_token_count=516,
        client_label="nanocodex",
        effort_label="high",
    )
    record(
        transport="websocket",
        decision="buffered_tool_calls",
        should_continue_round=False,
        reasoning_token_count=516,
        client_label="unknown",
        effort_label="unknown",
    )
    # Zero-token terminals record nothing.
    record(
        transport="http",
        decision="stop",
        should_continue_round=False,
        reasoning_token_count=0,
        client_label="unknown",
        effort_label="unknown",
    )

    assert reasoning_tokens_counter.samples == [
        {
            "labels": {"transport": "http", "outcome": "recovered", "client": "nanocodex", "effort": "high"},
            "value": 1034.0,
        },
        {
            "labels": {"transport": "websocket", "outcome": "forfeited", "client": "nanocodex", "effort": "high"},
            "value": 516.0,
        },
        {
            "labels": {"transport": "websocket", "outcome": "natural", "client": "unknown", "effort": "unknown"},
            "value": 516.0,
        },
    ]


def test_reasoning_token_recording_noops_without_prometheus(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = _ObservedCounter()
    monkeypatch.setattr(codex_continuation_module, "PROMETHEUS_AVAILABLE", False)
    monkeypatch.setattr(
        codex_continuation_module,
        "codex_continuation_reasoning_tokens_total",
        counter,
        raising=False,
    )
    codex_continuation_module._record_continuation_reasoning_tokens(
        transport="http",
        decision="continue",
        should_continue_round=True,
        reasoning_token_count=516,
        client_label="nanocodex",
        effort_label="high",
    )
    assert counter.samples == []


@pytest.mark.asyncio
async def test_fold_labels_decision_with_client_and_effort(
    decision_counter: _ObservedCounter,
    reasoning_tokens_counter: _ObservedCounter,
) -> None:
    async def open_round(payload: JsonObject) -> AsyncGenerator[str, None]:
        del payload
        yield _event(_created("resp_lbl"))
        for event in _reasoning_events(output_index=0, item_id="rs_lbl", encrypted_content="enc_lbl"):
            yield _event(event)
        yield _event(_completed("resp_lbl", input_tokens=50, output_tokens=550, reasoning_tokens=516))

    events = await _collect_events(
        fold_responses_stream_with_codex_continuation(
            base_payload={
                "model": "gpt-5.5",
                "input": [],
                "stream": True,
                "reasoning": {"effort": "high"},
            },
            open_round=open_round,
            config=CodexContinuationConfig(min_n=2, rechunk_size=64),
            client_label="nanocodex",
        )
    )

    assert events[-1]["type"] == "response.completed"
    assert decision_counter.samples == [
        {
            "labels": {
                "transport": "http",
                "decision": "tier_out_of_window",
                "tier": "1",
                "client": "nanocodex",
                "effort": "high",
            },
            "value": 1.0,
        }
    ]
    assert reasoning_tokens_counter.samples == [
        {
            "labels": {"transport": "http", "outcome": "forfeited", "client": "nanocodex", "effort": "high"},
            "value": 516.0,
        }
    ]
