"""
Structured logging for StreamGuard.

Call setup_logging() once at application startup, then use
get_logger(__name__) in every module that needs to log.
"""

import logging
import sys
from pathlib import Path

import structlog

from streamguard.config.settings import settings


def setup_logging(
    log_level: str | None = None,
    log_format: str | None = None,
    log_file: Path | None = None,
) -> None:
    """
    Configure logging for the whole application.

    Args:
        log_level: DEBUG, INFO, WARNING, ERROR. Defaults to .env value.
        log_format: "console" (coloured, readable) or "json" (machine-readable).
        log_file: Optional path to also write logs to disk.
    """
    level_name = (log_level or settings.log_level).upper()
    fmt = (log_format or settings.log_format).lower()
    level = getattr(logging, level_name, logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        format="%(message)s",
        level=level,
        handlers=handlers,
        force=True,
    )

    # Steps every log entry passes through, in order
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Silence libraries that log too much at INFO level
    for noisy in ("urllib3", "asyncio", "matplotlib", "numexpr"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a logger. Pass __name__ so logs show which module they came from."""
    return structlog.get_logger(name)