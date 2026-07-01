"""Logging utilities.

Two complementary facilities live here:

* :func:`log_format` — formats a single message string in the application's
  legacy style ``"<ts> <Level>: File:(..\\file.py) Line:(123) <message>"``. The
  pipeline workers emit these strings over Qt signals so the GUI log panel and
  the CLI can render identical text.
* :func:`configure_logging` / :func:`get_logger` — a thin wrapper over the
  standard :mod:`logging` module for headless use (CLI, tests), so console
  verbosity is controllable via a single call.
"""

from __future__ import annotations

import inspect
import logging
from datetime import datetime
from pathlib import Path

_ROOT_LOGGER_NAME = "cgt"
_configured = False


def _shorten_path(p: Path, leading_parents: int = 2) -> str:
    """Return a display path like ``..\\..\\filename.ext`` to mimic the sample style."""
    return ("..\\" * max(0, leading_parents)) + p.name


def log_format(message: str, *, level: str = "Debug", stack_depth: int = 1) -> str:
    """Format logs as ``"YYYY-MM-DD HH:MM:SS <Level>: File:(..\\file.py) Line:(123) <msg>"``.

    ``stack_depth=1`` means the immediate caller of this function.
    """
    try:
        frame = inspect.stack()[stack_depth]
        file_path = Path(frame.filename)
        line_no = frame.lineno
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{ts} {level}: File:({_shorten_path(file_path)}) Line:({line_no}) {message}"
    except Exception:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"{ts} {level}: {message}"


def configure_logging(level: int | str = logging.INFO, *, fmt: str | None = None) -> logging.Logger:
    """Configure and return the application's root logger.

    Idempotent: repeated calls only adjust the level, never stacking handlers.

    Args:
        level: A logging level (``logging.INFO``) or its name (``"INFO"``).
        fmt: Optional custom ``logging`` format string.
    """
    global _configured
    logger = logging.getLogger(_ROOT_LOGGER_NAME)
    if isinstance(level, str):
        level = logging.getLevelName(level.upper())
    logger.setLevel(level)
    if not _configured:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(fmt or "%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
        _configured = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child of the application logger (e.g. ``get_logger("cli")``)."""
    if not name:
        return logging.getLogger(_ROOT_LOGGER_NAME)
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")
