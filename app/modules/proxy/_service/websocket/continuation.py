"""Push-based Codex continuation fold for the downstream WebSocket transport.

The HTTP path folds continuation rounds with the pull-based
``fold_responses_stream_with_codex_continuation`` engine. The WebSocket relay
cannot hand over its read loop (it owns upstream reconnect / failover / retry),
so this module ports the engine's per-round state machine to a **push** model:
the relay feeds one upstream event at a time via :meth:`process_event`, and the
fold returns the downstream events to emit plus, when a round truncates on the
``518*n - 2`` fingerprint, the continuation request body to resend upstream.

It reuses the exact helpers behind the HTTP engine so the reconstructed stream
(index/sequence rewriting, buffered final answer, summed usage, proxy metadata)
is byte-compatible with the HTTP fold.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.clients.codex_continuation import (
    CodexContinuationConfig,
    _agent_usage,
    _BufferedOutput,
    _event_type,
    _find_buffer,
    _flush_entry,
    _input_items,
    _int_value,
    _item_payload,
    _reconstruct_terminal,
    _response_payload,
    _response_usage,
    _Seq,
    _stopped_reason,
    _sum_usage,
)
from app.core.clients.codex_truncation import (
    build_round_payload,
    commentary_message,
    reasoning_tokens,
    should_continue,
    tier_n,
)

_TERMINAL_EVENT_TYPES = frozenset({"response.completed", "response.failed", "response.incomplete"})


@dataclass(slots=True)
class _FoldOutcome:
    """Result of feeding one upstream event to the fold.

    ``downstream`` are the (rewritten) events to send to the client now.
    ``continuation_request`` is a Responses request body to resend upstream as a
    hidden continuation round (``None`` unless a truncated round is being
    continued). ``terminal_event`` is set only on the final reconstructed
    terminal; the relay finalizes/settles with it (it carries
    ``metadata.proxy_billed_usage``).
    """

    downstream: list[dict[str, Any]] = field(default_factory=list)
    continuation_request: dict[str, Any] | None = None
    terminal_event: dict[str, Any] | None = None
    billed_usage: dict[str, Any] | None = None


class _WebSocketContinuationFold:
    """Per-request push-based continuation fold state machine."""

    def __init__(self, config: CodexContinuationConfig, base_body: dict[str, Any]) -> None:
        self._config = config
        self._base_body = base_body
        self._original_input = _input_items(base_body.get("input"))
        self._seq = _Seq()
        self._downstream_output_index = 0
        self._round_number = 0
        self._base_response: dict[str, Any] | None = None
        self._final_output: list[dict[str, Any]] = []
        self._total_usage: dict[str, Any] = {}
        self._first_usage: dict[str, Any] | None = None
        self._replay_tail: list[Any] = []
        self._rounds_info: list[dict[str, Any]] = []
        self._begin_round()

    def _begin_round(self) -> None:
        self._round_number += 1
        self._output_index_map: dict[Any, int] = {}
        self._item_kind: dict[Any, str] = {}
        self._buffered_outputs: list[_BufferedOutput] = []
        self._round_reasoning: list[dict[str, Any]] = []

    def process_event(self, event: dict[str, Any]) -> _FoldOutcome:
        event_type = _event_type(event)

        if event_type in {"response.created", "response.in_progress"}:
            if self._round_number == 1:
                if event_type == "response.created":
                    self._base_response = _response_payload(event)
                event["sequence_number"] = self._seq.next()
                return _FoldOutcome(downstream=[event])
            # Hidden continuation rounds do not re-emit response.created.
            return _FoldOutcome()

        if event_type in _TERMINAL_EVENT_TYPES:
            return self._on_terminal(event)

        upstream_output_index = event.get("output_index")
        if event_type == "response.output_item.added":
            item = _item_payload(event)
            if item.get("type") == "reasoning":
                self._item_kind[upstream_output_index] = "reasoning"
                self._output_index_map[upstream_output_index] = self._downstream_output_index
                event["output_index"] = self._downstream_output_index
                self._downstream_output_index += 1
                event["sequence_number"] = self._seq.next()
                return _FoldOutcome(downstream=[event])
            self._item_kind[upstream_output_index] = "buffered"
            self._buffered_outputs.append(
                _BufferedOutput(
                    upstream_output_index=upstream_output_index,
                    item_type=item.get("type") if isinstance(item.get("type"), str) else None,
                    events=[event],
                    item=item,
                )
            )
            return _FoldOutcome()

        kind = self._item_kind.get(upstream_output_index)
        if kind == "reasoning":
            if upstream_output_index in self._output_index_map:
                event["output_index"] = self._output_index_map[upstream_output_index]
            event["sequence_number"] = self._seq.next()
            if event_type == "response.output_item.done":
                reasoning_item = _item_payload(event)
                self._round_reasoning.append(reasoning_item)
                self._final_output.append(reasoning_item)
            return _FoldOutcome(downstream=[event])
        if kind == "buffered":
            entry = _find_buffer(self._buffered_outputs, upstream_output_index)
            if entry is not None:
                entry.events.append(event)
                if event_type == "response.output_item.done":
                    entry.item = _item_payload(event) or entry.item
            return _FoldOutcome()

        event["sequence_number"] = self._seq.next()
        return _FoldOutcome(downstream=[event])

    def _on_terminal(self, terminal: dict[str, Any]) -> _FoldOutcome:
        usage = _response_usage(terminal)
        _sum_usage(self._total_usage, usage)
        if self._round_number == 1:
            self._first_usage = usage

        round_reasoning_tokens = reasoning_tokens(usage)
        truncation_tier = tier_n(round_reasoning_tokens, self._config.truncation_step)
        self._rounds_info.append(
            {"round": self._round_number, "reasoning_tokens": round_reasoning_tokens, "n": truncation_tier}
        )
        has_encrypted_content = bool(self._round_reasoning and self._round_reasoning[-1].get("encrypted_content"))
        within_output_cap = self._config.max_total_output_tokens == 0 or (
            _int_value(self._total_usage.get("output_tokens")) < self._config.max_total_output_tokens
        )
        should_continue_round = (
            self._config.enabled
            and _event_type(terminal) == "response.completed"
            and should_continue(
                round_reasoning_tokens,
                min_n=self._config.min_n,
                max_n=self._config.max_n,
                step=self._config.truncation_step,
            )
            and has_encrypted_content
            and self._round_number <= self._config.max_continue
            and within_output_cap
        )
        stopped_reason = _stopped_reason(
            should_continue_round=should_continue_round,
            reasoning_token_count=round_reasoning_tokens,
            has_encrypted_content=has_encrypted_content,
            round_number=self._round_number,
            within_output_cap=within_output_cap,
            config=self._config,
        )

        if should_continue_round:
            marker = commentary_message(self._config.marker_text)
            self._replay_tail.extend([*self._round_reasoning, marker])
            next_payload = build_round_payload(
                self._base_body,
                input_items=[*self._original_input, *self._replay_tail],
                force_include_encrypted=self._config.force_include_encrypted,
                drop_previous_response_id=True,
            )
            self._begin_round()
            return _FoldOutcome(continuation_request=next_payload)

        downstream: list[dict[str, Any]] = []
        for entry in self._buffered_outputs:
            for event in _flush_entry(entry, self._downstream_output_index, self._seq, self._config):
                downstream.append(event)
            self._downstream_output_index += 1
            self._final_output.append(entry.item)

        terminal_event = _reconstruct_terminal(
            terminal,
            self._base_response,
            self._final_output,
            _agent_usage(self._first_usage, self._total_usage, usage, flushed_final=True),
            self._seq.next(),
            self._rounds_info,
            stopped_reason,
            self._total_usage,
        )
        downstream.append(terminal_event)
        return _FoldOutcome(
            downstream=downstream,
            terminal_event=terminal_event,
            billed_usage=dict(self._total_usage),
        )
