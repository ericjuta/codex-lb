from __future__ import annotations

import asyncio
import gc
import linecache
import logging
import traceback
from collections.abc import Callable, Iterator

import pytest
import uvloop

from app.core import runtime_logging
from app.core.runtime_logging import install_redacting_loop_exception_handler
from tests.unit._proxy_test_helpers import runtime_basic_auth_url

pytestmark = pytest.mark.unit

_LOOP_FACTORIES = [
    pytest.param(asyncio.new_event_loop, id="asyncio"),
    pytest.param(uvloop.new_event_loop, id="uvloop"),
]
_PROXY_AUTHORITY = "183.110.26.193:6014"


class _LeakyConnection:
    password = "SECRETPW"

    def __repr__(self) -> str:
        proxy_url = runtime_basic_auth_url("smart-user", self.password, _PROXY_AUTHORITY)
        return f"Connection<ConnectionKey(host='chatgpt.com', port=443, proxy=URL('{proxy_url}'), proxy_auth=None)>"


class _ApostropheLeakyConnection(_LeakyConnection):
    # yarl leaves the RFC 3986 sub-delim ' unencoded in userinfo, so this is
    # the exact repr aiohttp produces for such a password.
    password = "S'ECRETPW"


class _ExplodingRepr:
    def __repr__(self) -> str:
        raise RuntimeError("repr failure")


class _Recorder(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    @property
    def messages(self) -> list[str]:
        return [record.getMessage() for record in self.records]

    @property
    def rendered(self) -> list[str]:
        formatter = logging.Formatter()
        rendered: list[str] = []
        for record in self.records:
            text = record.getMessage()
            if record.exc_info:
                text = f"{text}\n{formatter.formatException(record.exc_info)}"
            rendered.append(text)
        return rendered


@pytest.fixture
def asyncio_log() -> Iterator[_Recorder]:
    logger = logging.getLogger("asyncio")
    recorder = _Recorder()
    logger.addHandler(recorder)
    previous_level = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield recorder
    finally:
        logger.removeHandler(recorder)
        logger.setLevel(previous_level)


@pytest.fixture(params=_LOOP_FACTORIES)
def loop(request: pytest.FixtureRequest) -> Iterator[asyncio.AbstractEventLoop]:
    factory: Callable[[], asyncio.AbstractEventLoop] = request.param
    loop = factory()
    try:
        yield loop
    finally:
        loop.close()


def test_handler_redacts_credentialed_context_reprs(loop, asyncio_log) -> None:
    install_redacting_loop_exception_handler(loop)

    loop.call_exception_handler({"message": "Unclosed connection", "client_connection": _LeakyConnection()})

    (message,) = asyncio_log.messages
    assert message.startswith("Unclosed connection\nclient_connection: Connection<ConnectionKey(")
    assert "SECRETPW" not in message
    assert f"[REDACTED]@{_PROXY_AUTHORITY}" in message


def test_handler_redacts_apostrophe_password_in_context_repr(loop, asyncio_log) -> None:
    install_redacting_loop_exception_handler(loop)

    loop.call_exception_handler({"message": "Unclosed connection", "client_connection": _ApostropheLeakyConnection()})

    (message,) = asyncio_log.messages
    assert "S'ECRETPW" not in message
    assert "ECRETPW" not in message
    assert f"proxy=URL('http://[REDACTED]@{_PROXY_AUTHORITY}')" in message


def test_handler_keeps_secret_free_context_byte_identical(loop, asyncio_log) -> None:
    exc = RuntimeError("boom")
    context = {"message": "Task exception was never retrieved", "exception": exc, "future": object()}

    loop.default_exception_handler(dict(context))
    install_redacting_loop_exception_handler(loop)
    loop.call_exception_handler(context)

    baseline, redacted = asyncio_log.records
    assert redacted.getMessage() == baseline.getMessage()
    assert redacted.exc_info == baseline.exc_info
    assert redacted.exc_info is not None and redacted.exc_info[1] is exc


def test_install_is_idempotent(loop) -> None:
    install_redacting_loop_exception_handler(loop)
    handler = loop.get_exception_handler()

    install_redacting_loop_exception_handler(loop)

    assert loop.get_exception_handler() is handler


def test_handler_chains_previously_installed_handler(loop) -> None:
    seen: list[dict[str, object]] = []
    loop.set_exception_handler(lambda _loop, context: seen.append(dict(context)))
    install_redacting_loop_exception_handler(loop)

    loop.call_exception_handler({"message": "Unclosed connection", "client_connection": _LeakyConnection()})

    (context,) = seen
    assert context["message"] == "Unclosed connection"
    assert "SECRETPW" not in repr(context["client_connection"])
    assert f"[REDACTED]@{_PROXY_AUTHORITY}" in repr(context["client_connection"])


def test_handler_replaces_exploding_repr_with_opaque_stand_in(loop, asyncio_log) -> None:
    install_redacting_loop_exception_handler(loop)

    loop.call_exception_handler({"message": "Unclosed connection", "client_connection": _ExplodingRepr()})

    (message,) = asyncio_log.messages
    # The default handler never sees the raw object, so the message line
    # survives instead of asyncio's generic "Unhandled error in exception handler".
    assert message == "Unclosed connection\nclient_connection: <_ExplodingRepr repr failed: RuntimeError>"


def test_handler_fails_closed_when_redaction_pass_raises(loop, asyncio_log, monkeypatch) -> None:
    def _broken_redaction(text: str, **_kwargs: object) -> str:
        raise ValueError("redaction broke")

    monkeypatch.setattr(runtime_logging, "redact_rendered_log_text", _broken_redaction)
    install_redacting_loop_exception_handler(loop)
    exception_secret = runtime_basic_auth_url("u", "EXCPW", "h")
    exc = RuntimeError(exception_secret)

    loop.call_exception_handler(
        {"message": "Unclosed connection", "exception": exc, "client_connection": _LeakyConnection()}
    )

    (record,) = asyncio_log.records
    message = record.getMessage()
    rendered = asyncio_log.rendered[0]
    assert message.startswith("[REDACTED: loop context redaction failed]\n")
    assert "SECRETPW" not in message
    assert "SECRETPW" not in rendered
    assert "EXCPW" not in rendered
    assert "client_connection: [REDACTED: loop context redaction failed]" in message
    assert not record.exc_info
    assert all(value is not exc for value in vars(record).values())


@pytest.mark.parametrize("loop_factory", _LOOP_FACTORIES)
def test_unretrieved_task_exception_repr_is_redacted(loop_factory, asyncio_log) -> None:
    async def _main() -> None:
        install_redacting_loop_exception_handler(asyncio.get_running_loop())

        async def _boom() -> None:
            raise RuntimeError(runtime_basic_auth_url("u", "TASKPW", "h") + "/")

        task = asyncio.get_running_loop().create_task(_boom())
        await asyncio.sleep(0)
        assert task.done()
        del task
        gc.collect()
        await asyncio.sleep(0)

    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(_main())

    messages = [message for message in asyncio_log.messages if "Task exception was never retrieved" in message]
    assert messages, asyncio_log.messages
    assert all("TASKPW" not in message for message in messages)
    assert any("http://[REDACTED]@h/" in message for message in messages)


@pytest.mark.parametrize("loop_factory", _LOOP_FACTORIES)
def test_unretrieved_task_client_http_proxy_error_repr_is_redacted(loop_factory, asyncio_log) -> None:
    # Task repr embeds repr(exception); aiohttp's ClientHttpProxyError repr
    # carries the CONNECT Proxy-Authorization header, a reversible Basic token.
    import base64

    import aiohttp
    from aiohttp.client_reqrep import ClientRequest
    from yarl import URL

    from app.core.upstream_proxy import ResolvedProxyEndpoint

    token = base64.b64encode(b"smart-user:SECRETPW").decode()

    async def _main() -> None:
        running = asyncio.get_running_loop()
        install_redacting_loop_exception_handler(running)
        endpoint = ResolvedProxyEndpoint("ep", "https", "proxy.test", 8080, "smart-user", "SECRETPW")
        proxy_headers = endpoint.aiohttp_proxy_kwargs()["proxy_headers"]

        async def _boom() -> None:
            request = ClientRequest("CONNECT", URL("https://chatgpt.com/"), headers=proxy_headers, loop=running)
            raise aiohttp.ClientHttpProxyError(request.request_info, (), status=502, message="nope")

        task = running.create_task(_boom())
        await asyncio.sleep(0)
        assert task.done()
        assert token in repr(task)
        del task
        gc.collect()
        await asyncio.sleep(0)

    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.run(_main())

    messages = [message for message in asyncio_log.messages if "Task exception was never retrieved" in message]
    assert messages, asyncio_log.messages
    assert all(token not in message and "SECRETPW" not in message for message in messages)
    assert any("'Proxy-Authorization': 'Basic [REDACTED]'" in message for message in messages)
    assert all("SECRETPW" not in text and token not in text for text in asyncio_log.rendered)


class _CredentialedFuture:
    def __repr__(self) -> str:
        return f"<Future proxy={runtime_basic_auth_url('u', 'CHAINPW', 'h')}>"


def test_install_captures_warnings_in_worker_process(loop) -> None:
    import warnings

    logging.captureWarnings(False)
    logger = logging.getLogger("py.warnings")
    recorder = _Recorder()
    logger.addHandler(recorder)
    previous_propagate = logger.propagate
    logger.propagate = False
    try:
        install_redacting_loop_exception_handler(loop)
        warnings.warn("worker warning capture probe", UserWarning)
        install_redacting_loop_exception_handler(loop)
        warnings.warn("second worker warning capture probe", UserWarning)
        messages = "\n".join(recorder.messages)
        assert "worker warning capture probe" in messages
        assert "second worker warning capture probe" in messages
    finally:
        logger.removeHandler(recorder)
        logger.propagate = previous_propagate
        logging.captureWarnings(False)


def test_handler_falls_back_without_raw_context_when_previous_raises(loop, asyncio_log) -> None:
    def _boom(_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        raise RuntimeError(f"chained {context['future']!r}")

    loop.set_exception_handler(_boom)
    install_redacting_loop_exception_handler(loop)
    secret_url = runtime_basic_auth_url("u", "EXCPW", "h")

    loop.call_exception_handler(
        {
            "message": f"Task exception was never retrieved {secret_url}",
            "future": _CredentialedFuture(),
            "exception": RuntimeError(secret_url),
        }
    )

    assert asyncio_log.records
    rendered = "\n".join(asyncio_log.rendered)
    assert "CHAINPW" not in rendered
    assert "EXCPW" not in rendered
    assert "Unhandled error in exception handler" in asyncio_log.messages[0]
    assert "http://[REDACTED]@h" in rendered


def test_handler_falls_back_when_previous_raises_cancelled_error(loop, asyncio_log) -> None:
    def _boom(_loop: asyncio.AbstractEventLoop, _context: dict[str, object]) -> None:
        raise asyncio.CancelledError()

    loop.set_exception_handler(_boom)
    install_redacting_loop_exception_handler(loop)
    secret_url = runtime_basic_auth_url("u", "CANCELPW", "h")

    loop.call_exception_handler(
        {
            "message": f"Task exception was never retrieved {secret_url}",
            "future": _CredentialedFuture(),
            "exception": RuntimeError(secret_url),
        }
    )

    assert asyncio_log.records
    rendered = "\n".join(asyncio_log.rendered)
    assert "CANCELPW" not in rendered
    assert "CHAINPW" not in rendered
    assert "Unhandled error in exception handler" in asyncio_log.messages[0]
    assert "http://[REDACTED]@h" in rendered
    assert all("CANCELPW" not in text for text in asyncio_log.rendered)


def test_handler_sanitizes_message_and_exception_for_previous_handler(loop) -> None:
    seen: list[dict[str, object]] = []

    def _previous(_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        seen.append(dict(context))

    loop.set_exception_handler(_previous)
    install_redacting_loop_exception_handler(loop)
    secret_url = runtime_basic_auth_url("u", "MSGPW", "h")
    token = __import__("base64").b64encode(b"user:pass").decode()

    loop.call_exception_handler(
        {
            "message": f"failed {secret_url}",
            "exception": RuntimeError(f"Authorization: Basic {token}"),
        }
    )

    (context,) = seen
    assert "MSGPW" not in str(context["message"])
    assert "http://[REDACTED]@h" in str(context["message"])
    assert token not in str(context["exception"])
    assert token not in repr(context["exception"])
    assert "Basic [REDACTED]" in str(context["exception"]) or "[REDACTED]" in str(context["exception"])
    assert getattr(context["exception"], "__cause__", None) is None
    assert getattr(context["exception"], "__context__", None) is None


@pytest.mark.parametrize("traceback_key", ["source_traceback", "handle_traceback"])
def test_handler_redacts_source_traceback_line_with_credential(loop, asyncio_log, traceback_key, monkeypatch) -> None:
    seen: list[dict[str, object]] = []

    def _previous(target_loop: asyncio.AbstractEventLoop, context: dict[str, object]) -> None:
        seen.append(dict(context))
        target_loop.default_exception_handler(context)

    loop.set_exception_handler(_previous)
    install_redacting_loop_exception_handler(loop)
    secret_url = runtime_basic_auth_url("u", "TRACEPW", "h")
    source_lines = ["proxy = (\n", f"    {secret_url!r}\n", ")\n"]
    filename = "codex_lb_traceback_redact.py"
    monkeypatch.setitem(
        linecache.cache, filename, (sum(len(part) for part in source_lines), None, source_lines, filename)
    )
    probe = traceback.FrameSummary(filename, 1, "connect", lookup_line=False, end_lineno=3)
    assert getattr(probe, "_lines", "missing") is None
    assert secret_url not in (probe.line or "")
    assert "TRACEPW" in (getattr(probe, "_lines", "") or "")
    frames = [traceback.FrameSummary(filename, 1, "connect", lookup_line=False, end_lineno=3)]
    assert getattr(frames[0], "_lines", "missing") is None

    loop.call_exception_handler({"message": "callback failed", traceback_key: frames})

    (context,) = seen
    safe_frames = context[traceback_key]
    assert isinstance(safe_frames, list)
    safe_summaries: list[traceback.FrameSummary] = []
    safe_source_lines: list[str] = []
    for frame in safe_frames:
        assert isinstance(frame, traceback.FrameSummary)
        safe_summaries.append(frame)
        line = frame.line
        if isinstance(line, str) and line:
            assert "\n" not in line
            safe_source_lines.append(line)
    safe_source = "\n".join(safe_source_lines)
    safe_formatted = "".join(traceback.format_list(safe_summaries))
    rendered = "\n".join(asyncio_log.rendered)
    assert asyncio_log.records
    assert "TRACEPW" not in safe_source
    assert "TRACEPW" not in safe_formatted
    assert "TRACEPW" not in rendered
    assert "http://[REDACTED]@h" in safe_source
    assert "http://[REDACTED]@h" in safe_formatted
    assert "http://[REDACTED]@h" in rendered
    assert "proxy =" in safe_source
    assert "proxy =" in rendered
    assert "callback failed" in rendered
    assert filename in rendered


@pytest.mark.parametrize("traceback_key", ["source_traceback", "handle_traceback"])
def test_handler_redacts_form_feed_separated_password(loop, asyncio_log, traceback_key) -> None:
    install_redacting_loop_exception_handler(loop)
    frames = [traceback.FrameSummary("app.py", 1, "connect", line='connect(password =\f"FORMFEEDPW")')]

    loop.call_exception_handler({"message": "callback failed", traceback_key: frames})

    rendered = "\n".join(asyncio_log.rendered)
    assert "FORMFEEDPW" not in rendered
    assert "[REDACTED]" in rendered
    assert "callback failed" in rendered


def test_handler_fails_closed_with_credentialed_textual_fields(loop, asyncio_log, monkeypatch) -> None:
    def _broken_redaction(text: str, **_kwargs: object) -> str:
        raise ValueError("redaction broke")

    monkeypatch.setattr(runtime_logging, "redact_rendered_log_text", _broken_redaction)
    install_redacting_loop_exception_handler(loop)
    secret_url = runtime_basic_auth_url("u", "FAILPW", "h")

    loop.call_exception_handler(
        {
            "message": f"Unclosed connection {secret_url}",
            "exception": RuntimeError(secret_url),
            "client_connection": _LeakyConnection(),
        }
    )

    assert asyncio_log.records
    rendered = "\n".join(asyncio_log.rendered)
    assert "FAILPW" not in rendered
    assert "SECRETPW" not in rendered
    assert asyncio_log.messages[0].startswith("[REDACTED: loop context redaction failed]")
