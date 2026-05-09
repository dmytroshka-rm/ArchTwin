from __future__ import annotations

"""
isa_cad/core/logging.py
========================
Centralised structlog configuration for the ISA-CAD agent.

Usage
-----
    from isa_cad.core.logging import get_logger

    log = get_logger(__name__)
    log.info("node.start", node="context_freshness", session_id="s-001")
    log.warning("fidelity.stale", source="pricing_data", age_hours=200)
    log.error("llm.failed", reviewer="cost", error=str(exc))

Configuration
-------------
Call ``configure_logging()`` once at startup (the CLI and tests do this
automatically).  All subsequent ``get_logger()`` calls share the same
pipeline.

Log levels are controlled via ``ISA_CAD_LOG_LEVEL`` (default: INFO).
Set ``ISA_CAD_LOG_JSON=1`` to emit JSON lines instead of coloured text
(use this in production / log aggregation).
"""

import logging
import os
import sys

import structlog

_configured = False


def configure_logging(
    level: str | None = None,
    json_logs: bool | None = None,
) -> None:
    """
    Configure the structlog + stdlib logging pipeline.

    Parameters
    ----------
    level
        Log level string ("DEBUG", "INFO", "WARNING", "ERROR").
        Defaults to ``ISA_CAD_LOG_LEVEL`` env var, then "INFO".
    json_logs
        Emit JSON lines when True, coloured console output when False.
        Defaults to ``ISA_CAD_LOG_JSON`` env var (truthy = JSON).
    """
    global _configured

    effective_level = (level or os.getenv("ISA_CAD_LOG_LEVEL", "INFO")).upper()
    effective_json  = json_logs if json_logs is not None else bool(
        os.getenv("ISA_CAD_LOG_JSON", "")
    )

    # stdlib root logger
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, effective_level, logging.INFO),
    )

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if effective_json:
        # Production: machine-readable JSON lines
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: coloured, human-readable
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, effective_level, logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str = "isa_cad") -> structlog.BoundLogger:
    """
    Return a bound structlog logger.  Configures logging with defaults
    on first call if ``configure_logging()`` has not been called yet.
    """
    global _configured
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)
