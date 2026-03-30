"""Structured JSON logging via structlog.

Import this module once at application startup to configure logging.
All subsequent structlog.get_logger() calls will use these settings.
"""

import logging

import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structlog for JSON output with context vars."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
