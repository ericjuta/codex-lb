from __future__ import annotations

from typing import Iterable

from pydantic import ValidationError

from app.core import usage as usage_core
from app.core.balancer.types import ClassifiedFailure, FailureClass, FailurePhase, UpstreamError
from app.core.errors import OpenAIErrorDetail, OpenAIErrorEnvelope, is_upstream_usage_limit_message
from app.core.openai.models import OpenAIError
from app.core.plan_types import normalize_rate_limit_plan_type
from app.core.types import JsonValue
from app.core.usage.types import UsageWindowRow, UsageWindowSummary
from app.db.models import Account, AccountStatus, UsageHistory
from app.modules.proxy.types import (
    CreditStatusDetailsData,
    RateLimitStatusDetailsData,
    RateLimitWindowSnapshotData,
)

PLAN_TYPE_PRIORITY = (
    "enterprise",
    "business",
    "team",
    "pro",
    "plus",
    "education",
    "edu",
    "free_workspace",
    "free",
    "go",
    "guest",
    "quorum",
    "k12",
)

_DEACTIVATED_WORKSPACE_CODE = "deactivated_workspace"
_USAGE_LIMIT_CODE = "usage_limit_reached"
_RATE_LIMIT_CODES = frozenset({"rate_limit_exceeded", _USAGE_LIMIT_CODE})
_QUOTA_CODES = frozenset({"insufficient_quota", "usage_not_included", "quota_exceeded"})
# The one normalized code that carries no classification decision of its own:
# ``upstream_error`` is what a *missing* code normalizes to, which is exactly
# the shape a message has to speak for. Every other code already decided what
# the failure is, and a sentence must not reverse that decision.
#
# ``invalid_request_error`` is deliberately excluded even though upstream reuses
# it for rejections it has no code for: it is also upstream's catch-all for
# request-shaped 400s, whose message can quote request content back, so reading
# it off a message would let an echoed sentence bench a serving account.
_MESSAGE_CLASSIFIED_CODES = frozenset({"upstream_error"})
_TRANSIENT_CODES = frozenset(
    {"server_error", "upstream_error", "stream_incomplete", "overloaded_error", "server_is_overloaded"}
)
_CONNECT_PHASE_TRANSIENT_403_CODES = frozenset({"forbidden", "insufficient_permissions", "permission_error"})
_MODEL_CAPACITY_MESSAGE_MARKERS = ("selected model is at capacity",)


_MODEL_NOT_FOUND_CODE = "model_not_found"


def _is_account_model_unsupported_error(
    *,
    code: str | None,
    message: str | None,
    model: str | None,
) -> bool:
    """Match only the account-entitlement rejection for the requested model."""
    if code != "invalid_request_error" or message is None or model is None:
        return False
    normalized_message = " ".join(message.split())
    expected_message = f"The '{model}' model is not supported when using Codex with a ChatGPT account."
    return normalized_message == expected_message


def is_model_scoped_upstream_rejection(*, code: str | None) -> bool:
    """True when upstream rejected the requested model rather than the account.

    The exact ``model_not_found`` code is authoritative: it reproduces for that
    model whatever the serving account's health, so it is health-neutral. Model
    entitlement can still differ between subscription accounts, so before any
    output is visible a different account may answer it.
    """
    return code == _MODEL_NOT_FOUND_CODE


def is_pre_acceptance_model_rejection(*, code: str | None, message: str | None, model: str | None) -> bool:
    """The rejections that may move once to a replacement account before acceptance."""
    return is_model_scoped_upstream_rejection(code=code) or _is_account_model_unsupported_error(
        code=code,
        message=message,
        model=model,
    )


def is_upstream_model_capacity_error(message: str | None) -> bool:
    if message is None:
        return False
    normalized_message = " ".join(message.lower().split())
    return any(marker in normalized_message for marker in _MODEL_CAPACITY_MESSAGE_MARKERS)


def is_upstream_usage_limit_rejection(*, error_code: str, message: str | None) -> bool:
    """True when upstream says this account's usage limit is spent.

    Either the code names the limit or the message does. The message-only form
    is how the serialized ``response.failed`` frame arrives -- no status and no
    error code -- and it is the same rejection the coded form carries, so a
    caller keyed on the literal code alone answers "this account is fine" for a
    form upstream chooses freely. Deliberately status-free, and the message may
    decide only where the code decided nothing. Plain ``rate_limit_exceeded``
    throttling is not included: it says the request arrived too fast, not that
    the subscription window is exhausted.
    """
    return error_code == _USAGE_LIMIT_CODE or (
        error_code in _MESSAGE_CLASSIFIED_CODES and is_upstream_usage_limit_message(message)
    )


def keeps_account_in_the_walk(classified: ClassifiedFailure) -> bool:
    """True when this failure describes the requested model, so the account stays selectable.

    Selected-model capacity is a property of the model, not of the account: excluding
    each account in turn would rotate the whole pool over a condition no account can
    serve. Only the ``retryable_transient`` class qualifies, because it is the one whose
    health write leaves the account usable; ``rate_limit``/``quota`` bench the account,
    and an account-scoped usage-limit sentence outranks a capacity match.
    """
    message = classified["error"].get("message")
    return (
        classified["failure_class"] == "retryable_transient"
        and is_upstream_model_capacity_error(message)
        and not is_upstream_usage_limit_message(message)
    )


def classify_upstream_failure(
    *,
    error_code: str,
    error: UpstreamError,
    http_status: int | None,
    phase: FailurePhase,
) -> ClassifiedFailure:
    failure_class: FailureClass
    if error_code == _DEACTIVATED_WORKSPACE_CODE:
        # Only the exact structured code proves the workspace is gone; a bare
        # HTTP 402 may describe a payment incident and proves nothing terminal.
        failure_class = "account_unavailable"
    elif error_code in _RATE_LIMIT_CODES:
        failure_class = "rate_limit"
    elif error_code in _QUOTA_CODES:
        failure_class = "quota"
    elif is_upstream_usage_limit_rejection(error_code=error_code, message=error.get("message")):
        # The same rejection in the delivery form that carries no code: a spent
        # account cannot be waited out on itself, so it must not reach the
        # transient branch below.
        failure_class = "rate_limit"
    elif phase == "connect" and http_status == 403 and error_code in _CONNECT_PHASE_TRANSIENT_403_CODES:
        failure_class = "retryable_transient"
    elif (
        error_code in _TRANSIENT_CODES
        or is_upstream_model_capacity_error(error.get("message"))
        or (http_status is not None and http_status >= 500)
    ):
        failure_class = "retryable_transient"
    else:
        failure_class = "non_retryable"
    return ClassifiedFailure(
        failure_class=failure_class,
        phase=phase,
        error_code=error_code,
        error=error,
        http_status=http_status,
    )


def _header_account_id(account_id: str | None) -> str | None:
    if not account_id:
        return None
    if account_id.startswith(("email_", "local_")):
        return None
    return account_id


def _select_accounts_for_limits(accounts: Iterable[Account]) -> list[Account]:
    return [
        account
        for account in accounts
        if account.status not in (AccountStatus.REAUTH_REQUIRED, AccountStatus.DEACTIVATED, AccountStatus.PAUSED)
    ]


def _summarize_window(
    rows: list[UsageWindowRow],
    account_map: dict[str, Account],
    window: str,
) -> UsageWindowSummary | None:
    if not rows:
        return None
    return usage_core.summarize_usage_window(rows, account_map, window)


def _window_snapshot(
    summary: UsageWindowSummary | None,
    rows: list[UsageWindowRow],
    window: str,
    now_epoch: int,
) -> RateLimitWindowSnapshotData | None:
    if summary is None:
        return None

    used_percent = _normalize_used_percent(summary.used_percent, rows)
    if used_percent is None:
        return None

    reset_at = summary.reset_at
    if reset_at is None:
        return None

    window_minutes = summary.window_minutes or usage_core.default_window_minutes(window)
    if not window_minutes:
        return None

    limit_window_seconds = int(window_minutes * 60)
    reset_after_seconds = max(0, int(reset_at) - now_epoch)

    return RateLimitWindowSnapshotData(
        used_percent=_percent_to_int(used_percent),
        limit_window_seconds=limit_window_seconds,
        reset_after_seconds=reset_after_seconds,
        reset_at=int(reset_at),
    )


def _normalize_used_percent(
    value: float | None,
    rows: Iterable[UsageWindowRow],
) -> float | None:
    if value is not None:
        return value
    values = [row.used_percent for row in rows if row.used_percent is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _percent_to_int(value: float) -> int:
    bounded = max(0.0, min(100.0, value))
    return int(bounded)


def _rate_limit_details(
    primary: RateLimitWindowSnapshotData | None,
    secondary: RateLimitWindowSnapshotData | None,
    monthly: RateLimitWindowSnapshotData | None = None,
    *,
    limit_reached: bool | None = None,
) -> RateLimitStatusDetailsData | None:
    if not primary and not secondary and not monthly:
        return None
    if limit_reached is None:
        used_percents = [window.used_percent for window in (primary, secondary, monthly) if window]
        limit_reached = any(used >= 100 for used in used_percents)
    return RateLimitStatusDetailsData(
        allowed=not limit_reached,
        limit_reached=limit_reached,
        primary_window=primary,
        secondary_window=secondary,
        monthly_window=monthly,
    )


def _aggregate_credits(entries: Iterable[UsageHistory]) -> tuple[bool, bool, float] | None:
    has_data = False
    has_credits = False
    unlimited = False
    balance_total = 0.0

    for entry in entries:
        credits_has = entry.credits_has
        credits_unlimited = entry.credits_unlimited
        credits_balance = entry.credits_balance
        if credits_has is None and credits_unlimited is None and credits_balance is None:
            continue
        has_data = True
        if credits_has is True:
            has_credits = True
        if credits_unlimited is True:
            unlimited = True
        if credits_balance is not None and not credits_unlimited:
            try:
                balance_total += float(credits_balance)
            except (TypeError, ValueError):
                continue

    if not has_data:
        return None
    if unlimited:
        has_credits = True
    return has_credits, unlimited, balance_total


def _credits_snapshot(entries: Iterable[UsageHistory]) -> CreditStatusDetailsData | None:
    aggregate = _aggregate_credits(entries)
    if aggregate is None:
        return None
    has_credits, unlimited, balance_total = aggregate
    balance_value = str(round(balance_total, 2))
    return CreditStatusDetailsData(
        has_credits=has_credits,
        unlimited=unlimited,
        balance=balance_value,
        approx_local_messages=None,
        approx_cloud_messages=None,
    )


def _plan_type_for_accounts(accounts: Iterable[Account]) -> str:
    normalized = [_normalize_plan_type(account.plan_type) for account in accounts]
    filtered = [plan for plan in normalized if plan is not None]
    if not filtered:
        return "guest"
    unique = set(filtered)
    if len(unique) == 1:
        return filtered[0]
    for plan in PLAN_TYPE_PRIORITY:
        if plan in unique:
            return plan
    return "guest"


def _normalize_plan_type(value: str | None) -> str | None:
    return normalize_rate_limit_plan_type(value)


def _rate_limit_headers(
    window_label: str,
    summary: UsageWindowSummary,
) -> dict[str, str]:
    used_percent = summary.used_percent
    window_minutes = summary.window_minutes
    if used_percent is None or window_minutes is None:
        return {}
    headers = {
        f"x-codex-{window_label}-used-percent": str(float(used_percent)),
        f"x-codex-{window_label}-window-minutes": str(int(window_minutes)),
    }
    reset_at = summary.reset_at
    if reset_at is not None:
        headers[f"x-codex-{window_label}-reset-at"] = str(int(reset_at))
    return headers


def _credits_headers(entries: Iterable[UsageHistory]) -> dict[str, str]:
    aggregate = _aggregate_credits(entries)
    if aggregate is None:
        return {}
    has_credits, unlimited, balance_total = aggregate
    balance_value = f"{balance_total:.2f}"
    return {
        "x-codex-credits-has-credits": "true" if has_credits else "false",
        "x-codex-credits-unlimited": "true" if unlimited else "false",
        "x-codex-credits-balance": balance_value,
    }


def _normalize_error_code(code: str | None, error_type: str | None) -> str:
    value = code or error_type
    if not value:
        return "upstream_error"
    return value.lower()


def _parse_openai_error(payload: OpenAIErrorEnvelope) -> OpenAIError | None:
    error = payload.get("error")
    if not error:
        return None
    try:
        return OpenAIError.model_validate(error)
    except ValidationError:
        if not isinstance(error, dict):
            return None
        return OpenAIError(
            message=_coerce_str(error.get("message")),
            type=_coerce_str(error.get("type")),
            code=_coerce_str(error.get("code")),
            param=_coerce_str(error.get("param")),
            plan_type=_coerce_str(error.get("plan_type")),
            resets_at=_coerce_number(error.get("resets_at")),
            resets_in_seconds=_coerce_number(error.get("resets_in_seconds")),
        )


def _coerce_str(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None


def _coerce_number(value: JsonValue) -> int | float | None:
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _apply_error_metadata(target: OpenAIErrorDetail, error: OpenAIError | None) -> None:
    if not error:
        return
    if error.plan_type is not None:
        target["plan_type"] = error.plan_type
    if error.resets_at is not None:
        target["resets_at"] = error.resets_at
    if error.resets_in_seconds is not None:
        target["resets_in_seconds"] = error.resets_in_seconds


def _upstream_error_from_openai(error: OpenAIError | None) -> UpstreamError:
    if not error:
        return {}
    data = error.model_dump(exclude_none=True)
    payload: UpstreamError = {}
    message = data.get("message")
    if isinstance(message, str):
        payload["message"] = message
    resets_at = data.get("resets_at")
    if isinstance(resets_at, (int, float)):
        payload["resets_at"] = resets_at
    resets_in_seconds = data.get("resets_in_seconds")
    if isinstance(resets_in_seconds, (int, float)):
        payload["resets_in_seconds"] = resets_in_seconds
    return payload
