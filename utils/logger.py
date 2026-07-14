"""
Structured logging setup for the Lead Discovery Engine.

Provides a single configured logger used across all modules, writing
to both console and a rotating log file. Log level and file path are
controlled via config.Settings so behaviour is consistent everywhere.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def configure_logging(log_level: str, log_file: Path) -> None:
    """Configure the root logger once per process.

    Safe to call multiple times; subsequent calls are no-ops so tests
    and repeated imports don't duplicate handlers.
    """
    global _configured
    if _configured:
        return

    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Call configure_logging() once at startup
    before using loggers obtained here."""
    return logging.getLogger(name)
