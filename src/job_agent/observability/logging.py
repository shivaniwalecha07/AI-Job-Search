"""structlog-based structured logging (see ARCHITECTURE.md 21). No PII in logs."""
from __future__ import annotations

import logging

import structlog

from job_agent.settings import get_settings

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    level = getattr(logging, get_settings().log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=level)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(),
        ],
    )
    _configured = True


def get_logger(name: str = "job_agent") -> structlog.stdlib.BoundLogger:
    configure_logging()
    return structlog.get_logger(name)
