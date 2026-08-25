import datetime
import json
import logging
import sys
from typing import Any, Dict

from app.core.config import settings

STANDARD_LOG_RECORD_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings containing standard fields and any
    extra contextual variables passed during logging calls.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "app": "mediora",
            "env": settings.app_env,
        }

        # Include exception tracebacks if present
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            log_payload["exception"] = record.exc_text

        # Include stack info if present
        if record.stack_info:
            log_payload["stack_info"] = self.formatStack(record.stack_info)

        # Extract any extra contextual parameters passed to logger calls
        for key, val in record.__dict__.items():
            if key not in STANDARD_LOG_RECORD_ATTRS and key not in log_payload:
                log_payload[key] = val

        return json.dumps(log_payload, default=str)


def setup_logging() -> None:
    """
    Configures root logger and framework loggers (e.g., Uvicorn) to output
    structured JSON lines to stdout.
    """
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Configure root handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Align Uvicorn loggers with root configuration
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(logger_name)
        uv_logger.handlers.clear()
        uv_logger.addHandler(handler)
        uv_logger.setLevel(log_level)
        uv_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """
    Convenience helper to retrieve a named logger configured with JSON formatting.
    """
    return logging.getLogger(name)
