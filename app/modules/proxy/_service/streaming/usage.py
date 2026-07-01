"""Usage-accounting helpers shared across streaming transports.

These pure helpers translate upstream usage (agent-facing `response.usage` or the
proxy's aggregated `metadata.proxy_billed_usage`) into the token counts codex-lb
settles and logs. They live in a leaf module so both the HTTP streaming path
(`streaming.mixin`) and the WebSocket path (`websocket.mixin`) can reuse them
without a circular import.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class _StreamUsageAccounting:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None


def _token_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _usage_accounting_from_mapping(usage: Mapping[str, Any]) -> _StreamUsageAccounting | None:
    input_tokens = _token_int(usage.get("input_tokens"))
    output_tokens = _token_int(usage.get("output_tokens"))
    if input_tokens is None or output_tokens is None:
        return None

    cached_input_tokens = None
    input_details = usage.get("input_tokens_details")
    if isinstance(input_details, Mapping):
        cached_input_tokens = _token_int(input_details.get("cached_tokens"))

    reasoning_tokens = None
    output_details = usage.get("output_tokens_details")
    if isinstance(output_details, Mapping):
        reasoning_tokens = _token_int(output_details.get("reasoning_tokens"))

    return _StreamUsageAccounting(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _usage_accounting_from_response_usage(usage: Any) -> _StreamUsageAccounting:
    input_tokens = usage.input_tokens if usage else None
    output_tokens = usage.output_tokens if usage else None
    cached_input_tokens = usage.input_tokens_details.cached_tokens if usage and usage.input_tokens_details else None
    reasoning_tokens = usage.output_tokens_details.reasoning_tokens if usage and usage.output_tokens_details else None
    return _StreamUsageAccounting(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
    )


def _proxy_billed_usage_from_event_payload(event_payload: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if event_payload is None:
        return None
    response_payload = event_payload.get("response")
    if not isinstance(response_payload, Mapping):
        return None
    metadata = response_payload.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    billed_usage = metadata.get("proxy_billed_usage")
    return billed_usage if isinstance(billed_usage, Mapping) else None


def _stream_usage_accounting(
    usage: Any,
    billed_usage_payload: Mapping[str, Any] | None,
) -> _StreamUsageAccounting:
    if billed_usage_payload is not None:
        billed_accounting = _usage_accounting_from_mapping(billed_usage_payload)
        if billed_accounting is not None:
            return billed_accounting
    return _usage_accounting_from_response_usage(usage)
