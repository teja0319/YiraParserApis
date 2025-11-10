"""
Core logging configuration
"""

import logging
import sys
from typing import Optional

from server.config.settings import get_settings
from server.core.tenant_context import get_current_tenant


class TenantContextFilter(logging.Filter):
    """Attach tenant context to each log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.tenant_id = get_current_tenant() or "-"
        return True


def configure_logging(level: Optional[str] = None) -> None:
    """
    Configure application logging

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    settings = get_settings()
    log_level = level or settings.log_level

    # Create logger
    logger = logging.getLogger("medical_parser")
    logger.setLevel(getattr(logging, log_level))

    # Remove existing handlers to avoid duplicate logs when reconfiguring
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level))
    console_handler.addFilter(TenantContextFilter())

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [tenant:%(tenant_id)s] %(message)s"
    )
    console_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get logger instance for a module

    Args:
        name: Module name

    Returns:
        Logger instance
    """
    return logging.getLogger(f"medical_parser.{name}")
