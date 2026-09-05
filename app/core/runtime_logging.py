from __future__ import annotations

import asyncio
import base64
import binascii
import copy
import json
import logging
import re
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import Request
from uvicorn.config import LOGGING_CONFIG
from uvicorn.logging import AccessFormatter, DefaultFormatter

from app.core.types import JsonValue
from app.core.utils.request_id import get_request_id

_SENSITIVE_LOG_VALUE_PATTERNS = (
    re.compile(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key)(\s*[=:]\s*)([^\s,&]+)"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=:-]+"),
    re.compile(r"(?i)(authorization\s*[=:]\s*)(?!\s*bearer\b)([^,&]+)"),
)
_LINE_BREAKS = re.compile(r"(\r\n|\n|\r)")
_BASIC_TOKEN_PATTERN = re.compile(
    r"(?i)((?:(?:proxy-)?authorization['\"]?\s*[=:]\s*['\"]?)?)(basic\s+)([A-Za-z0-9+/=]*)"
)
_BASIC_TOKEN_PRECHECKS = ("Basic ", "basic ", "BASIC ")
_REDACTION_FAILED_PLACEHOLDER = "[REDACTED: log redaction failed]"
_JSON_SENSITIVE_LOG_VALUE_PATTERN = re.compile(
    r'(?i)("[^"]*(?:password|passwd|pwd|token|secret|api[_-]?key|authorization)"\s*:\s*")'
    r'(?:\\.|[^"\\])*(?:\\(?=\Z))?("|(?=\Z))'
)
_USERINFO_PATTERN = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/?#\s@\"]+)@")
_PYTHON_REPR_SENSITIVE_LOG_VALUE_PATTERN = re.compile(
    r"(?i)('[^'\\]*(?:password|passwd|pwd|token|secret|api[_-]?key|authorization)'\s*:\s*)"
    r"(b?'(?:\\.|[^'\\])*'|b?\"(?:\\.|[^\"\\])*\"|\[[^\[\]]*\]|\([^()]*\)|\{[^{}]*\}|[^,}\]\)\s]+)"
)
_SENSITIVE_LOG_KEY_PATTERN = re.compile(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|authorization)$")
_SECRET_HINTS = (
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "api_key",
    "api-key",
    "apikey",
    "bearer",
    "basic",
    "authorization",
)
_LOG_REDACTION = "[REDACTED]"


def _redact_log_value(value: str | None) -> str | None:
    collapsed = _collapse_log_value(value)
    if collapsed is None:
        return None
    return _redact_secret_patterns(_USERINFO_PATTERN.sub(_redact_userinfo, collapsed))


def _redact_secret_patterns_on_line(text: str) -> str:
    redacted = _JSON_SENSITIVE_LOG_VALUE_PATTERN.sub(_redact_json_secret, text)
    redacted = _SENSITIVE_LOG_VALUE_PATTERNS[0].sub(_redact_keyed_secret, redacted)
    redacted = _SENSITIVE_LOG_VALUE_PATTERNS[1].sub(_redact_bearer_token, redacted)
    redacted = _BASIC_TOKEN_PATTERN.sub(_redact_basic_token, redacted)
    redacted = _SENSITIVE_LOG_VALUE_PATTERNS[2].sub(_redact_authorization_value, redacted)
    return _PYTHON_REPR_SENSITIVE_LOG_VALUE_PATTERN.sub(_redact_python_repr_secret, redacted)


def _map_log_lines(text: str, transform: Callable[[str], str]) -> str:
    if "\n" not in text and "\r" not in text:
        return transform(text)
    return "".join(transform(part) if index % 2 == 0 else part for index, part in enumerate(_LINE_BREAKS.split(text)))


def _redact_secret_patterns(text: str) -> str:
    return _map_log_lines(text, _redact_secret_patterns_on_line)


def _redact_basic_tokens_on_line(text: str) -> str:
    return _BASIC_TOKEN_PATTERN.sub(_redact_basic_token, text)


def redact_rendered_log_text(text: str, *, keyed_secrets: bool = True) -> str:
    """Mask URL userinfo, Basic tokens and, optionally, keyed secrets in rendered log text.

    This backstop covers every originating logger and never returns the original
    text if a redaction pass fails.
    """
    try:
        redacted = text
        if "@" in text and "://" in text:
            redacted = _USERINFO_PATTERN.sub(_redact_userinfo, redacted)
        if any(precheck in text for precheck in _BASIC_TOKEN_PRECHECKS):
            redacted = _map_log_lines(redacted, _redact_basic_tokens_on_line)
        if not keyed_secrets:
            return redacted
        folded = text.casefold()
        for hint in _SECRET_HINTS:
            if hint in folded:
                return _redact_secret_patterns(redacted)
        return redacted
    except Exception:
        return _REDACTION_FAILED_PLACEHOLDER


def _redact_record_text(record: logging.LogRecord, text: str) -> str:
    return redact_rendered_log_text(text, keyed_secrets=record.levelno >= logging.WARNING)


def _redact_userinfo(match: re.Match[str]) -> str:
    return f"{match.group(1)}{_LOG_REDACTION}@"


def _redact_keyed_secret(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}{_LOG_REDACTION}"


def _redact_json_secret(match: re.Match[str]) -> str:
    closer = match.group(2) or ""
    return f"{match.group(1)}{_LOG_REDACTION}{closer}"


def _is_fully_redacted_repr_value(value: str) -> bool:
    if value == _LOG_REDACTION:
        return True
    candidate = value[1:] if value.startswith("b") and len(value) > 1 else value
    if len(candidate) < 2 or candidate[0] not in "'\"" or candidate[-1] != candidate[0]:
        return False
    body = candidate[1:-1]
    if body == _LOG_REDACTION:
        return True
    scheme, sep, rest = body.partition(" ")
    return sep == " " and scheme.casefold() == "basic" and rest == _LOG_REDACTION


def _redact_python_repr_secret(match: re.Match[str]) -> str:
    value = match.group(2)
    if _is_fully_redacted_repr_value(value):
        return match.group(0)
    quote = value[0] if value[:1] in "'\"" else ""
    return f"{match.group(1)}{quote}{_LOG_REDACTION}{quote}"


def _is_canonical_basic_credential(token: str) -> bool:
    if not token:
        return False
    pad_len = (4 - len(token) % 4) % 4
    padded = token + ("=" * pad_len)
    try:
        decoded = base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError):
        return False
    if base64.b64encode(decoded).decode("ascii") != padded:
        return False
    return b":" in decoded


def _redact_basic_token(match: re.Match[str]) -> str:
    header_prefix, scheme, token = match.group(1), match.group(2), match.group(3)
    if not token:
        return match.group(0)
    if header_prefix or _is_canonical_basic_credential(token):
        return f"{header_prefix}{scheme}{_LOG_REDACTION}"
    return match.group(0)


def _redact_bearer_token(match: re.Match[str]) -> str:
    return f"{match.group(1)}{_LOG_REDACTION}"


def _redact_authorization_value(match: re.Match[str]) -> str:
    return f"{match.group(1)}{_LOG_REDACTION}"


def _utc_converter(seconds: float | None) -> time.struct_time:
    return time.gmtime(seconds)


class _RedactingFormatterMixin(logging.Formatter):
    """Redact the fully rendered record, including exception and stack text."""

    def format(self, record: logging.LogRecord) -> str:
        rendered = _redact_record_text(record, super().format(record))
        if rendered is _REDACTION_FAILED_PLACEHOLDER:
            return f"{self.formatTime(record, self.datefmt)} {record.levelname} {record.name} {rendered}"
        return rendered


class UtcDefaultFormatter(_RedactingFormatterMixin, DefaultFormatter):
    converter: Callable[[float | None], time.struct_time] = staticmethod(_utc_converter)


class UtcAccessFormatter(_RedactingFormatterMixin, AccessFormatter):
    converter: Callable[[float | None], time.struct_time] = staticmethod(_utc_converter)


_MAX_JSON_LOG_DEPTH = 32
_CYCLIC_JSON_LOG_PLACEHOLDERS: dict[type, str] = {dict: "{...}", list: "[...]", tuple: "(...)"}


def _redact_json_log_value(
    record: logging.LogRecord,
    value: object,
    *,
    _ancestors: frozenset[int] = frozenset(),
    _depth: int = 0,
) -> object:
    if isinstance(value, str):
        return _redact_record_text(record, value)
    if not isinstance(value, (dict, list, tuple)):
        return value
    if id(value) in _ancestors:
        return next(marker for kind, marker in _CYCLIC_JSON_LOG_PLACEHOLDERS.items() if isinstance(value, kind))
    if _depth >= _MAX_JSON_LOG_DEPTH:
        return _redact_record_text(record, _safe_str(value))
    ancestors = _ancestors | {id(value)}
    depth = _depth + 1
    if isinstance(value, dict):
        return {
            _redact_json_log_key(record, key): _redact_json_log_item(record, key, item, ancestors, depth)
            for key, item in value.items()
        }
    return [_redact_json_log_value(record, item, _ancestors=ancestors, _depth=depth) for item in value]


def _safe_str(value: object) -> str:
    try:
        return str(value)
    except Exception:
        return f"<unprintable {type(value).__name__}>"


def _redact_json_log_key(record: logging.LogRecord, key: object) -> object:
    return _redact_record_text(record, key) if isinstance(key, str) else key


def _is_secret_json_log_key(record: logging.LogRecord, key: object) -> bool:
    return record.levelno >= logging.WARNING and isinstance(key, str) and bool(_SENSITIVE_LOG_KEY_PATTERN.search(key))


def _redact_json_log_item(
    record: logging.LogRecord, key: object, value: object, ancestors: frozenset[int], depth: int
) -> object:
    if value is not None and _is_secret_json_log_key(record, key):
        return _LOG_REDACTION
    return _redact_json_log_value(record, value, _ancestors=ancestors, _depth=depth)


class JsonFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_record_text(record, record.getMessage()),
        }

        try:
            from app.core.tracing.otel import get_current_span_id, get_current_trace_id

            trace_id = get_current_trace_id()
            span_id = get_current_span_id()
            if trace_id:
                log_entry["trace_id"] = trace_id
            if span_id:
                log_entry["span_id"] = span_id
        except Exception:
            pass

        excluded_keys = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "message",
            "taskName",
        }

        for key, value in record.__dict__.items():
            if key in excluded_keys:
                continue
            safe_key = str(_redact_json_log_key(record, key))
            if value is not None and _is_secret_json_log_key(record, key):
                log_entry[safe_key] = _LOG_REDACTION
                continue
            try:
                redacted = _redact_json_log_value(record, value)
            except Exception:
                redacted = value
            try:
                json.dumps(redacted)
                log_entry[safe_key] = redacted
            except Exception:
                log_entry[safe_key] = _redact_record_text(record, _safe_str(redacted))

        if record.exc_info:
            log_entry["exception"] = _redact_record_text(record, self.formatException(record.exc_info))

        return json.dumps(log_entry, default=str)


class JsonAccessFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, JsonValue] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "type": "access",
            "client": getattr(record, "client_addr", None),
            "request": cast(JsonValue, _redact_json_log_value(record, getattr(record, "request_line", None))),
            "status": getattr(record, "status_code", None),
        }
        return json.dumps(log_entry, default=str)


type LogConfigValue = str | bool | None | dict[str, "LogConfigValue"]
type LogConfig = dict[str, LogConfigValue]


def build_log_config() -> LogConfig:
    from app.core.config.settings import get_settings

    config = copy.deepcopy(LOGGING_CONFIG)
    formatters = config.setdefault("formatters", {})
    handlers = config.setdefault("handlers", {})
    settings = get_settings()

    if settings.log_format == "json":
        formatters["default"] = {
            "()": "app.core.runtime_logging.JsonFormatter",
        }
    else:
        formatters["default"] = {
            "()": "app.core.runtime_logging.UtcDefaultFormatter",
            "fmt": "%(asctime)s %(levelprefix)s %(name)s %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%SZ",
            "use_colors": None,
        }

    if settings.log_format == "json":
        formatters["access"] = {
            "()": "app.core.runtime_logging.JsonAccessFormatter",
        }
    else:
        formatters["access"] = {
            "()": "app.core.runtime_logging.UtcAccessFormatter",
            "fmt": '%(asctime)s %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            "datefmt": "%Y-%m-%dT%H:%M:%SZ",
            "use_colors": None,
        }

    # Uvicorn's stock config only wires uvicorn.* loggers. Attach the same
    # default handler to the root logger so application loggers such as
    # app.core.balancer.logic surface in docker logs at INFO.
    handlers.setdefault(
        "default", {"class": "logging.StreamHandler", "formatter": "default", "stream": "ext://sys.stderr"}
    )
    config["root"] = {
        "handlers": ["default"],
        "level": "INFO",
    }
    return cast(LogConfig, config)


class _RedactedRepr:
    """Stand-in whose repr is the redacted rendering of the original object."""

    __slots__ = ("_text",)

    def __init__(self, text: str) -> None:
        self._text = text

    def __repr__(self) -> str:
        return self._text


class _SanitizedStackSummary(traceback.StackSummary):
    """Redacted frames whose repr is format() so uvloop handle_traceback keeps source text."""

    def __repr__(self) -> str:
        return "".join(self.format()).rstrip("\n")

    def __str__(self) -> str:
        return repr(self)


_REDACTING_LOOP_HANDLER_MARKER = "_codex_lb_redacting_loop_handler"
_LOOP_CONTEXT_REDACTION_FAILED = "[REDACTED: loop context redaction failed]"
_LOOP_HANDLER_FAILURE_MESSAGE = "Unhandled error in exception handler"


def _sanitize_loop_repr(value: object) -> object:
    try:
        rendered = repr(value)
    except Exception as exc:
        return _RedactedRepr(f"<{type(value).__name__} repr failed: {type(exc).__name__}>")
    redacted = redact_rendered_log_text(rendered)
    return value if redacted == rendered else _RedactedRepr(redacted)


def _sanitize_loop_message(value: object) -> object:
    if isinstance(value, str):
        return redact_rendered_log_text(value)
    return _sanitize_loop_repr(value)


def _sanitize_loop_exception(value: object) -> object:
    if not isinstance(value, BaseException):
        return _sanitize_loop_repr(value)
    rendered_str = _safe_str(value)
    rendered_repr = repr(value)
    try:
        formatted_tb = "".join(traceback.format_exception(value))
    except Exception:
        formatted_tb = rendered_str
    redacted_str = redact_rendered_log_text(rendered_str)
    redacted_repr = redact_rendered_log_text(rendered_repr)
    redacted_tb = redact_rendered_log_text(formatted_tb)
    if redacted_str == rendered_str and redacted_repr == rendered_repr and redacted_tb == formatted_tb:
        return value
    snapshot = Exception(redacted_str)
    snapshot.__cause__ = None
    snapshot.__context__ = None
    snapshot.__suppress_context__ = True
    if redacted_tb and redacted_tb != redacted_str:
        snapshot.add_note(redacted_tb)
    return snapshot


def _sanitize_loop_traceback(value: object) -> object:
    try:
        frames = traceback.StackSummary.from_list(cast(Any, value))
    except Exception:
        return _sanitize_loop_repr(value)
    safe_frames = _SanitizedStackSummary()
    changed = False
    for frame in frames:
        safe_filename = redact_rendered_log_text(frame.filename)
        safe_name = redact_rendered_log_text(frame.name)
        if getattr(frame, "_lines", None) is None:
            # extract_stack(lookup_lines=False) leaves _lines unset; .line fills
            # it from linecache but still returns only the first physical line.
            frame.line
        source_text = getattr(frame, "_lines", None)
        if source_text is None:
            source_text = frame.line
        source_text = source_text or ""
        physical_lines = source_text.splitlines() or [""]
        safe_physical_lines = redact_rendered_log_text(source_text).splitlines() or [""]
        changed = (
            changed
            or safe_filename != frame.filename
            or safe_name != frame.name
            or safe_physical_lines != physical_lines
        )
        lineno = frame.lineno or 0
        for offset, line in enumerate(safe_physical_lines):
            # One FrameSummary per physical line: CPython 3.14 FrameSummary.line
            # keeps only the first line, and format_list rebuilds a plain StackSummary.
            safe_frames.append(traceback.FrameSummary(safe_filename, lineno + offset, safe_name, line=line))
    if not changed:
        formatted = "".join(frames.format())
        if redact_rendered_log_text(formatted) == formatted:
            return value
    return safe_frames


def _sanitize_loop_context(context: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in context.items():
        if key == "message":
            safe[key] = _sanitize_loop_message(value)
        elif key == "exception":
            safe[key] = _sanitize_loop_exception(value)
        elif key in {"source_traceback", "handle_traceback"}:
            safe[key] = _sanitize_loop_traceback(value)
        else:
            safe[key] = _sanitize_loop_repr(value)
    return safe


def _fail_closed_loop_context(context: dict[str, Any]) -> dict[str, Any]:
    try:
        failed: dict[str, Any] = {"message": _LOOP_CONTEXT_REDACTION_FAILED}
        for key, _value in context.items():
            if key in {"message", "exception", "source_traceback", "handle_traceback"}:
                continue
            failed[key] = _RedactedRepr(_LOOP_CONTEXT_REDACTION_FAILED)
        return failed
    except Exception:
        return {"message": _LOOP_CONTEXT_REDACTION_FAILED}


def _reraise_if_process_control(exc: BaseException) -> None:
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        raise exc


def install_redacting_loop_exception_handler(loop: asyncio.AbstractEventLoop) -> None:
    """Redact credential-bearing object reprs before the loop's default handler logs them."""
    # Worker processes spawned by uvicorn never run app.cli.main(); capture
    # ResourceWarning reprs here so they still hit the redacting formatters.
    logging.captureWarnings(True)
    previous = loop.get_exception_handler()
    if previous is not None and getattr(previous, _REDACTING_LOOP_HANDLER_MARKER, False):
        return

    def _delegate(target_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        if previous is None:
            target_loop.default_exception_handler(context)
        else:
            previous(target_loop, context)

    def _handler(target_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        try:
            safe_context = _sanitize_loop_context(context)
            try:
                _delegate(target_loop, safe_context)
            except BaseException as exc:
                _reraise_if_process_control(exc)
                fallback = dict(safe_context)
                fallback["message"] = _LOOP_HANDLER_FAILURE_MESSAGE
                target_loop.default_exception_handler(fallback)
        except BaseException as exc:
            _reraise_if_process_control(exc)
            try:
                target_loop.default_exception_handler(_fail_closed_loop_context(context))
            except BaseException as inner:
                _reraise_if_process_control(inner)
                return

    setattr(_handler, _REDACTING_LOOP_HANDLER_MARKER, True)
    loop.set_exception_handler(_handler)


def log_error_response(
    logger: logging.Logger,
    request: Request,
    status_code: int,
    code: str | None,
    message: str | None,
    *,
    category: str,
    exc_info: bool = False,
) -> None:
    level = logging.ERROR if status_code >= 500 else logging.WARNING
    logger.log(
        level,
        "%s request_id=%s method=%s path=%s status=%s",
        category,
        get_request_id(),
        request.method,
        request.url.path,
        status_code,
        exc_info=exc_info,
    )


def _collapse_log_value(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed or None
