"""Fail-closed proofs for preserving a full resend on a fresh durable bridge."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlsplit

from app.core.types import JsonValue

_TOOL_CALL_TYPE_BY_OUTPUT_TYPE = {
    "function_call_output": "function_call",
    "custom_tool_call_output": "custom_tool_call",
    "apply_patch_call_output": "apply_patch_call",
}
_TOOL_CALL_TYPES = frozenset(_TOOL_CALL_TYPE_BY_OUTPUT_TYPE.values())
_RESPONSE_OWNED_ITEM_TYPES = frozenset({"reasoning", "tool_search_call", "tool_search_output", "web_search_call"})
_INTERNAL_CHAT_MESSAGE_METADATA_FIELD = "internal_chat_message_metadata_passthrough"
_ALLOWED_INTERNAL_CHAT_MESSAGE_METADATA_FIELDS = frozenset({"turn_id"})
_MESSAGE_ROLES = frozenset({"assistant", "developer", "system", "user"})
_MESSAGE_CONTENT_TYPES = frozenset({"input_file", "input_image", "input_text", "output_text", "refusal", "text"})
_MESSAGE_FIELDS = frozenset({"content", "id", _INTERNAL_CHAT_MESSAGE_METADATA_FIELD, "phase", "role", "status", "type"})
_CONTENT_FIELDS = {
    "input_file": frozenset({"file_data", "file_id", "file_url", "filename", "type"}),
    "input_image": frozenset({"detail", "file_id", "image_url", "type"}),
    "input_text": frozenset({"text", "type"}),
    "output_text": frozenset({"text", "type"}),
    "refusal": frozenset({"refusal", "type"}),
    "text": frozenset({"text", "type"}),
}
_INPUT_ITEM_FIELDS = {
    "apply_patch_call": frozenset(
        {
            "call_id",
            "caller",
            "id",
            "input",
            _INTERNAL_CHAT_MESSAGE_METADATA_FIELD,
            "operation",
            "patch",
            "status",
            "type",
        }
    ),
    "apply_patch_call_output": frozenset(
        {"call_id", "caller", "id", _INTERNAL_CHAT_MESSAGE_METADATA_FIELD, "output", "status", "type"}
    ),
    "custom_tool_call": frozenset(
        {"call_id", "caller", "id", "input", _INTERNAL_CHAT_MESSAGE_METADATA_FIELD, "name", "status", "type"}
    ),
    "custom_tool_call_output": frozenset(
        {"call_id", "caller", "id", _INTERNAL_CHAT_MESSAGE_METADATA_FIELD, "output", "status", "type"}
    ),
    "function_call": frozenset(
        {"arguments", "call_id", "caller", "id", _INTERNAL_CHAT_MESSAGE_METADATA_FIELD, "name", "status", "type"}
    ),
    "function_call_output": frozenset(
        {"call_id", "caller", "id", _INTERNAL_CHAT_MESSAGE_METADATA_FIELD, "output", "status", "type"}
    ),
}
_ITEM_STATUSES = frozenset({"completed", "failed"})
_APPLY_PATCH_OPERATION_FIELDS = {
    "create_file": frozenset({"diff", "path", "type"}),
    "delete_file": frozenset({"path", "type"}),
    "update_file": frozenset({"diff", "path", "type"}),
}


@dataclass(frozen=True, slots=True)
class FreshResendProjection:
    input_items: list[JsonValue]
    stored_prefix_count: int


def project_responses_input_for_fresh_resend(
    input_items: list[JsonValue],
    *,
    stored_count: int,
) -> FreshResendProjection | None:
    """Remove response-owned bookkeeping after the durable prefix was verified."""

    if stored_count <= 0 or stored_count > len(input_items):
        return None

    projected_items: list[JsonValue] = []
    projected_stored_count = 0
    for index, item in enumerate(input_items):
        projected_item = _project_resend_item(item)
        if projected_item is not None:
            projected_items.append(projected_item)
        if index + 1 == stored_count:
            projected_stored_count = len(projected_items)

    return FreshResendProjection(
        input_items=projected_items,
        stored_prefix_count=projected_stored_count,
    )


def responses_input_suffix_retains_prior_output(
    input_items: list[JsonValue],
    *,
    stored_count: int,
) -> bool:
    """Prove that a stored prefix is followed by prior output and fresh input."""

    if stored_count <= 0 or len(input_items) <= stored_count:
        return False
    prefix_state = _direct_tool_call_prefix_state(input_items[:stored_count])
    if prefix_state is None:
        return False
    pending_calls, seen_call_ids = prefix_state
    retained_output_seen = False
    fresh_followup_seen = False
    for item in input_items[stored_count:]:
        if not isinstance(item, dict):
            return False
        item_type_value = item.get("type")
        if item_type_value is not None and not isinstance(item_type_value, str):
            return False
        item_type = item_type_value if isinstance(item_type_value, str) else None
        if item_type in _TOOL_CALL_TYPES:
            if item.get("status") not in (None, "completed"):
                return False
            call_id = item.get("call_id")
            if not isinstance(call_id, str) or not call_id or call_id in seen_call_ids:
                return False
            seen_call_ids.add(call_id)
            pending_calls.append((item_type, call_id))
            retained_output_seen = False
            fresh_followup_seen = False
            continue
        call_type = _TOOL_CALL_TYPE_BY_OUTPUT_TYPE.get(item_type or "")
        if call_type is not None:
            if item.get("status") not in (None, "completed", "failed"):
                return False
            call_id = item.get("call_id")
            if not isinstance(call_id, str) or not pending_calls:
                return False
            if pending_calls[0] != (call_type, call_id):
                return False
            pending_calls.popleft()
            continue
        if item_type in (None, "message") and item.get("role") == "assistant":
            if pending_calls or not _is_retained_response_message(item):
                return False
            retained_output_seen = True
            fresh_followup_seen = False
            continue
        if _is_fresh_followup_input(item):
            if not retained_output_seen or pending_calls:
                return False
            fresh_followup_seen = True
            continue
        return False
    return retained_output_seen and fresh_followup_seen and not pending_calls


def responses_input_suffix_matches_pending_tool_calls(
    input_items: list[JsonValue],
    *,
    stored_count: int,
    pending_tool_calls: Mapping[str, str],
) -> bool:
    """Prove that the suffix exactly settles the durable call manifest."""

    if stored_count <= 0 or len(input_items) <= stored_count or not pending_tool_calls:
        return False
    prefix_state = _direct_tool_call_prefix_state(input_items[:stored_count])
    if prefix_state is None or prefix_state[1] & pending_tool_calls.keys():
        return False
    suffix = input_items[stored_count:]
    if not all(
        isinstance(item, dict)
        and isinstance(item.get("type"), str)
        and item.get("type") in (_TOOL_CALL_TYPES | _TOOL_CALL_TYPE_BY_OUTPUT_TYPE.keys())
        for item in suffix
    ):
        return False
    if not _input_items_are_self_contained_direct_tool_loop(suffix):
        return False

    suffix_calls: dict[str, str] = {}
    suffix_outputs: dict[str, str] = {}
    for item in cast(list[dict[str, JsonValue]], suffix):
        item_type = cast(str, item["type"])
        call_id = cast(str, item["call_id"])
        if item_type in _TOOL_CALL_TYPES:
            suffix_calls[call_id] = item_type
        else:
            suffix_outputs[call_id] = _TOOL_CALL_TYPE_BY_OUTPUT_TYPE[item_type]
    expected = dict(pending_tool_calls)
    return suffix_calls == expected and suffix_outputs == expected


def _project_resend_item(item: JsonValue) -> JsonValue | None:
    if not isinstance(item, dict):
        return item
    item_type = item.get("type")
    if item_type is not None and not isinstance(item_type, str):
        return item
    if item_type == "reasoning" or (item_type in _RESPONSE_OWNED_ITEM_TYPES and item.get("status") == "completed"):
        return None
    if "id" not in item:
        return item
    projected_item = dict(item)
    projected_item.pop("id")
    return projected_item


def _input_items_are_self_contained_direct_tool_loop(input_items: list[JsonValue]) -> bool:
    unsettled_by_type: dict[str, set[str]] = {item_type: set() for item_type in _TOOL_CALL_TYPES}
    seen_call_ids: set[str] = set()
    settled_call_ids: set[str] = set()
    for item in input_items:
        if not isinstance(item, dict):
            return False
        if "type" in item and not _is_nonblank_string(item.get("type")):
            return False
        if item.get("id") not in (None, ""):
            return False
        if not _internal_chat_message_metadata_is_safe(item.get(_INTERNAL_CHAT_MESSAGE_METADATA_FIELD)):
            return False
        item_type_value = item.get("type")
        item_type = item_type_value if isinstance(item_type_value, str) else None
        if not _input_item_has_only_known_fields(item, item_type):
            return False
        call_id_value = item.get("call_id")
        call_id = call_id_value if isinstance(call_id_value, str) and call_id_value else None
        if item_type in _TOOL_CALL_TYPES:
            if (
                call_id is None
                or call_id in seen_call_ids
                or not _caller_is_direct(item)
                or not _tool_call_is_self_contained(item_type, item)
            ):
                return False
            seen_call_ids.add(call_id)
            unsettled_by_type[item_type].add(call_id)
            continue
        call_item_type = _TOOL_CALL_TYPE_BY_OUTPUT_TYPE.get(item_type or "")
        if call_item_type is not None:
            if (
                call_id is None
                or call_id not in unsettled_by_type[call_item_type]
                or call_id in settled_call_ids
                or not _caller_is_direct(item)
                or not _tool_output_is_self_contained(item_type or "", item)
            ):
                return False
            unsettled_by_type[call_item_type].remove(call_id)
            settled_call_ids.add(call_id)
    return all(not call_ids for call_ids in unsettled_by_type.values())


def _direct_tool_call_prefix_state(
    input_items: list[JsonValue],
) -> tuple[deque[tuple[str, str]], set[str]] | None:
    pending_calls: deque[tuple[str, str]] = deque()
    seen_call_ids: set[str] = set()
    for item in input_items:
        if not isinstance(item, dict):
            return None
        item_type_value = item.get("type")
        if item_type_value is not None and not isinstance(item_type_value, str):
            return None
        item_type = item_type_value if isinstance(item_type_value, str) else None
        if item_type in _TOOL_CALL_TYPES:
            if item.get("status") not in (None, "completed"):
                return None
            call_id = item.get("call_id")
            if not isinstance(call_id, str) or not call_id or call_id in seen_call_ids:
                return None
            seen_call_ids.add(call_id)
            pending_calls.append((item_type, call_id))
            continue
        call_type = _TOOL_CALL_TYPE_BY_OUTPUT_TYPE.get(item_type or "")
        if call_type is not None:
            if item.get("status") not in (None, "completed", "failed"):
                return None
            call_id = item.get("call_id")
            if not isinstance(call_id, str) or not pending_calls:
                return None
            if pending_calls[0] != (call_type, call_id):
                return None
            pending_calls.popleft()
            continue
        if pending_calls and (
            (item_type in (None, "message") and item.get("role") in _MESSAGE_ROLES)
            or item_type in {"input_file", "input_image", "input_text"}
        ):
            return None
        fallthrough_call_id = item.get("call_id")
        if isinstance(fallthrough_call_id, str) and fallthrough_call_id:
            seen_call_ids.add(fallthrough_call_id)
    return pending_calls, seen_call_ids


def _is_retained_response_message(item: Mapping[str, JsonValue]) -> bool:
    return (
        item.get("type") in (None, "message")
        and item.get("role") == "assistant"
        and item.get("status") in (None, "completed")
        and _message_has_valid_content(item)
    )


def _is_fresh_followup_input(item: Mapping[str, JsonValue]) -> bool:
    item_type = item.get("type")
    if item_type in {"input_file", "input_image", "input_text"}:
        return _input_content_part_is_self_contained(item, allow_output=False)
    return item_type in (None, "message") and item.get("role") == "user" and _message_has_valid_content(item)


def _tool_call_is_self_contained(item_type: str, item: Mapping[str, JsonValue]) -> bool:
    if item.get("status") not in (None, "completed"):
        return False
    if item_type == "function_call":
        return _is_nonblank_string(item.get("name")) and isinstance(item.get("arguments"), str)
    if item_type == "custom_tool_call":
        return _is_nonblank_string(item.get("name")) and isinstance(item.get("input"), str)
    if sum(field in item for field in ("operation", "patch", "input")) != 1:
        return False
    if "operation" in item:
        return _apply_patch_operation_is_self_contained(item.get("operation"))
    if "patch" in item:
        return _is_nonblank_string(item.get("patch"))
    return _is_nonblank_string(item.get("input"))


def _caller_is_direct(item: Mapping[str, JsonValue]) -> bool:
    caller = item.get("caller")
    return caller is None or caller == {"type": "direct"}


def _input_item_has_only_known_fields(item: Mapping[str, JsonValue], item_type: str | None) -> bool:
    allowed_fields = _INPUT_ITEM_FIELDS.get(item_type or "")
    if allowed_fields is None:
        return False
    status = item.get("status")
    return not any(key not in allowed_fields for key in item) and (
        status is None or (isinstance(status, str) and status in _ITEM_STATUSES)
    )


def _apply_patch_operation_is_self_contained(operation: JsonValue | None) -> bool:
    if not isinstance(operation, dict):
        return False
    operation_type = operation.get("type")
    allowed_fields = _APPLY_PATCH_OPERATION_FIELDS.get(operation_type) if isinstance(operation_type, str) else None
    if allowed_fields is None or set(operation) != allowed_fields:
        return False
    return _is_nonblank_string(operation.get("path")) and (
        operation_type == "delete_file" or isinstance(operation.get("diff"), str)
    )


def _tool_output_is_self_contained(item_type: str, item: Mapping[str, JsonValue]) -> bool:
    if item.get("status") not in (None, "completed", "failed"):
        return False
    output = item.get("output")
    if isinstance(output, str):
        return True
    if item_type == "apply_patch_call_output":
        return output is None and item.get("status") in {"completed", "failed"}
    return (
        isinstance(output, list)
        and bool(output)
        and all(
            isinstance(part, dict) and _input_content_part_is_self_contained(part, allow_output=False)
            for part in output
        )
    )


def _message_has_valid_content(item: Mapping[str, JsonValue]) -> bool:
    role = item.get("role")
    if role not in _MESSAGE_ROLES:
        return False
    phase = item.get("phase")
    if phase is not None and phase not in {"commentary", "final_answer"}:
        return False
    content = item.get("content")
    if role != "assistant" and isinstance(content, str):
        return _is_nonblank_string(content)
    if not isinstance(content, list) or not content:
        return False
    if role == "assistant":
        return all(
            isinstance(part, dict)
            and part.get("type") in {"output_text", "refusal"}
            and _input_content_part_is_self_contained(part, allow_output=True)
            for part in content
        )
    return all(
        isinstance(part, dict) and _input_content_part_is_self_contained(part, allow_output=False) for part in content
    )


def _input_content_part_is_self_contained(
    part: Mapping[str, JsonValue],
    *,
    allow_output: bool,
) -> bool:
    part_type = part.get("type")
    if part_type not in _MESSAGE_CONTENT_TYPES:
        return False
    typed_part = cast(str, part_type)
    if any(key not in _CONTENT_FIELDS[typed_part] for key in part):
        return False
    if part_type in {"input_text", "text"} or (allow_output and part_type == "output_text"):
        return _is_nonblank_string(part.get("text"))
    if allow_output and part_type == "refusal":
        return _is_nonblank_string(part.get("refusal"))
    if part_type == "input_image":
        return (part.get("detail") is None or isinstance(part.get("detail"), str)) and (
            _url_is_safe(part.get("image_url"), allow_data=True) or _is_nonblank_string(part.get("file_id"))
        )
    if part_type == "input_file":
        return (part.get("filename") is None or isinstance(part.get("filename"), str)) and (
            _is_nonblank_string(part.get("file_data"))
            or _is_nonblank_string(part.get("file_id"))
            or _url_is_safe(part.get("file_url"), allow_data=False)
        )
    return False


def _internal_chat_message_metadata_is_safe(value: JsonValue | None) -> bool:
    if value is None:
        return True
    return (
        isinstance(value, dict)
        and set(value) == _ALLOWED_INTERNAL_CHAT_MESSAGE_METADATA_FIELDS
        and _is_nonblank_string(value.get("turn_id"))
    )


def _url_is_safe(value: JsonValue | None, *, allow_data: bool) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        scheme = urlsplit(value).scheme.lower()
    except ValueError:
        return False
    return scheme in ({"data", "http", "https"} if allow_data else {"http", "https"})


def _is_nonblank_string(value: JsonValue | None) -> bool:
    return isinstance(value, str) and bool(value.strip())
