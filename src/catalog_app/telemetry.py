from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import traceback
import warnings
from collections.abc import Callable
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, TypedDict

from pydantic import ValidationError

_log_context: ContextVar[dict[str, str]] = ContextVar("log_context", default={})
_console_stream = sys.stderr
_console_level = logging.INFO
_service = "mcp"
_redacted_values: tuple[str, ...] = ()
_telemetry_enabled = False
_log_sink: Callable[[dict[str, Any]], None] | None = None
_log_levels = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "alert": logging.CRITICAL,
    "emergency": logging.CRITICAL,
}
_ErrorFields = TypedDict(
    "_ErrorFields",
    {
        "exception.type": str,
        "exception.message": str,
        "exception.stacktrace": str,
    },
    total=False,
)


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        for secret in _redacted_values:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [REDACTED]", value)
        value = re.sub(
            r"(?i)https?://[\w-]+\.vault\.azure\.net[^\s\"'<>)]*",
            "[REDACTED_KEY_VAULT_URI]",
            value,
        )
        value = re.sub(
            r"(?i)/subscriptions/[^\s/]+/resourceGroups/[^\s/]+/providers/Microsoft\.ManagedIdentity/userAssignedIdentities/[^\s\"'<>)]*",
            "[REDACTED_IDENTITY]",
            value,
        )
        value = re.sub(r"(?i)(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", value)
        return re.sub(
            r"(?i)([?&](?:sig|token|key|secret|password|access_token)=)[^&\s]+",
            r"\1[REDACTED]",
            value,
        )
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return (
        value
        if value is None or isinstance(value, (bool, int, float))
        else _redact(str(value))
    )


def _error_fields(error: BaseException | None) -> _ErrorFields:
    if error is None:
        return {}
    if _service != "mcp":
        while error.__cause__ is not None:
            error = error.__cause__
        return {
            "exception.type": type(error).__name__,
            "exception.message": (
                f"{error.error_count()} Tool Input validation error(s)."
                if isinstance(error, ValidationError)
                else str(error)
            ),
            "exception.stacktrace": "\n".join(
                f"{frame.f_code.co_filename}:{line} in {frame.f_code.co_name}"
                for frame, line in traceback.walk_tb(error.__traceback__)
            ),
        }
    stack = traceback.TracebackException.from_exception(
        error,
        limit=sys.maxsize,
        capture_locals=True,
        compact=True,
        max_group_width=sys.maxsize,
        max_group_depth=sys.maxsize,
    )
    cause = stack
    while cause.__cause__ is not None:
        error = error.__cause__
        cause = cause.__cause__
    return {
        "exception.type": type(error).__name__,
        "exception.message": str(error),
        "exception.stacktrace": "".join(stack.format()).rstrip(),
    }


def _operator_log(
    level: str, event: str, *, export: bool = True, **fields: Any
) -> None:
    severity = _log_levels[level]
    if severity < _console_level:
        return
    entry = {
        "timestamp": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "level": "warn" if level == "warning" else level,
        "actor": "system",
        **_log_context.get(),
        "event": event,
        **fields,
        "service": _service,
        "pid": os.getpid(),
    }
    if _telemetry_enabled:
        from opentelemetry import trace

        span = trace.get_current_span().get_span_context()
        if span.is_valid:
            entry.update(traceId=f"{span.trace_id:032x}", spanId=f"{span.span_id:016x}")
    if _service != "mcp":
        entry = _redact(entry)
    _console_stream.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
    _console_stream.flush()
    sink = _log_sink
    if sink is not None:
        sink(entry)
    if _telemetry_enabled and export:
        body = entry.get("message", entry.get("exception.message", event))
        logging.getLogger("toolforge.operator").log(
            severity,
            body,
            extra={key: value for key, value in entry.items() if key != "message"},
        )


def configure(*, service: str = "mcp") -> None:
    global _console_level, _redacted_values, _service, _telemetry_enabled

    from .invocation import InvocationLogHandler, InvocationOutput

    _service = service
    level = os.environ.pop("TOOLFORGE_LOG_LEVEL", "info").lower()
    if level not in {"debug", "info", "warn", "warning", "error"}:
        raise ValueError("TOOLFORGE_LOG_LEVEL must be debug, info, warning, or error")
    _console_level = _log_levels[level]
    secret_values = json.loads(os.environ.pop("TOOLFORGE_LOG_REDACT_VALUES", "[]"))
    secret_values.extend(
        value
        for key, value in os.environ.items()
        if re.search(
            r"SECRET|TOKEN|PASSWORD|CONNECTION_STRING|IDENTITY_HEADER|MSI_SECRET", key
        )
    )
    _redacted_values = tuple(
        sorted({value for value in secret_values if value}, key=len, reverse=True)
    )
    logging.getLogger().handlers = [InvocationLogHandler()]
    logging.getLogger().setLevel(_console_level)

    def format_warning(
        message: Warning | str,
        category: type[Warning],
        filename: str,
        lineno: int,
        line: str | None = None,
    ) -> str:
        return f"{filename}:{lineno}: {category.__name__}: {message}\n"

    # ty rejects direct reassignment of this hook (astral-sh/ty#3962).
    setattr(warnings, "formatwarning", format_warning)
    logging.captureWarnings(True)
    for name in ("mcp", "uvicorn", "azure", "opentelemetry"):
        logging.getLogger(name).setLevel(_console_level)
    telemetry_logger = logging.getLogger("toolforge.operator")
    telemetry_logger.propagate = False
    telemetry_logger.setLevel(_console_level)
    sys.stdout = InvocationOutput(sys.stdout, "info", "stdout")
    sys.stderr = InvocationOutput(sys.stderr, "error", "stderr")
    sys.excepthook = lambda _kind, error, _tb: _operator_log(
        "error", "runtime.failed", **_error_fields(error)
    )
    threading.excepthook = lambda args: _operator_log(
        "error", "thread.failed", **_error_fields(args.exc_value)
    )
    sys.unraisablehook = lambda args: _operator_log(
        "error", "runtime.unraisable", **_error_fields(args.exc_value)
    )
    if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import SpanProcessor
        from opentelemetry.trace import Status

        class RedactingSpanProcessor(SpanProcessor):
            def on_end(self, span: Any) -> None:
                # Sanitize the export snapshot before Azure's batch processor sees it.
                span._name = _redact(span.name)
                span._attributes = {
                    key: _redact(
                        value.split("?", 1)[0].split("#", 1)[0]
                        if isinstance(value, str)
                        and key in {"http.target", "http.url", "url.full"}
                        else value
                    )
                    for key, value in (span.attributes or {}).items()
                    if not key.startswith(
                        (
                            "db.",
                            "http.request.header.",
                            "http.response.header.",
                            "exception.",
                        )
                    )
                    and key != "url.query"
                }
                # Management spans omit payload-bearing SDK events.
                span._events = []
                span._links = []
                span._status = Status(span.status.status_code)

        configure_azure_monitor(
            logger_name="toolforge.operator",
            resource=Resource.create({"service.name": service}),
            span_processors=[RedactingSpanProcessor()] if service != "mcp" else [],
            instrumentation_options={
                name: {"enabled": False}
                for name in ("azure_sdk", "psycopg2", "django", "flask", "fastapi")
            },
            enable_live_metrics=False,
        )
        _telemetry_enabled = True
