"""Continuation helpers for the standalone middleware proxy.

The truncation math and Responses-API request builders now live in
:mod:`app.core.clients.codex_truncation` (the shipped ``app`` package is the
single source of truth) and are re-exported here so ``middleware.app`` /
``middleware.proxy`` and their tests keep importing them from ``middleware.codex``.
The synthetic continue-pair helpers below are used only by this standalone
proxy, so they stay local.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.core.clients.codex_truncation import (
    DEFAULT_TRUNCATION_STEP,
    ENCRYPTED_INCLUDE,
    build_round_payload,
    commentary_message,
    is_truncation_pattern,
    merge_include,
    reasoning_enabled,
    reasoning_tokens,
    should_continue,
    tier_n,
)

# Re-exported for the standalone middleware proxy + tests; the canonical
# definitions live in app.core.clients.codex_truncation.
__all__ = [
    "DEFAULT_TRUNCATION_STEP",
    "ENCRYPTED_INCLUDE",
    "build_round_payload",
    "commentary_message",
    "continue_call_id",
    "continue_pair",
    "declares_continue_tool",
    "is_truncation_pattern",
    "merge_include",
    "reasoning_enabled",
    "reasoning_tokens",
    "repair_followup_input",
    "should_continue",
    "tier_n",
]

# --- synthetic continue pair ------------------------------------------------


def continue_call_id(reasoning_id: str) -> str:
    """Deterministic call_id derived from the reasoning id it follows.

    Same reasoning id => same pair, so the within-turn tail and the (optional)
    cross-turn repair emit byte-identical bytes (prompt-cache stable).
    """
    return "call_" + hashlib.sha1(reasoning_id.encode("utf-8")).hexdigest()[:24]


def continue_pair(
    reasoning_id: str,
    *,
    tool_name: str,
    output_text: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A synthetic (function_call, function_call_output) that nudges the model
    to resume reasoning. Never declared as a real tool (NO_TOOLS mode)."""
    call_id = continue_call_id(reasoning_id)
    call = {
        "type": "function_call",
        "call_id": call_id,
        "name": tool_name,
        "arguments": json.dumps({"continue": True}),
    }
    output = {
        "type": "function_call_output",
        "call_id": call_id,
        "output": output_text,
    }
    return call, output


def declares_continue_tool(body: dict[str, Any], tool_name: str) -> bool:
    """Collision rule: the agent itself DECLARES a tool with our continue name
    in its `tools` array (not merely referencing it in input history)."""
    for tool in body.get("tools") or []:
        if isinstance(tool, dict) and tool.get("name") == tool_name:
            return True
    return False


def repair_followup_input(
    input_items: list[Any],
    id_store,
    *,
    tool_name: str,
    output_text: str,
) -> list[Any]:
    """repair_followup="stateful": re-insert a continue pair AFTER each reasoning
    item whose id we recorded during a prior turn's continuation. Keyed strictly
    by recorded id (never by adjacency, which would corrupt naturally consecutive
    reasoning items). Idempotent: skips if the pair is already present."""
    out: list[Any] = []
    n = len(input_items)
    for i, item in enumerate(input_items):
        out.append(item)
        if not (isinstance(item, dict) and item.get("type") == "reasoning"):
            continue
        rid = item.get("id")
        if not rid or rid not in id_store:
            continue
        call_id = continue_call_id(rid)
        nxt = input_items[i + 1] if i + 1 < n else None
        already = isinstance(nxt, dict) and nxt.get("type") == "function_call" and nxt.get("call_id") == call_id
        if already:
            continue
        call, output = continue_pair(rid, tool_name=tool_name, output_text=output_text)
        out.append(call)
        out.append(output)
    return out
