"""Tests for the logging utilities."""

from __future__ import annotations

import logging
import re

from cgt_cell_analysis_demo.util.logger import configure_logging, get_logger, log_format


def test_log_format_structure():
    line = log_format("hello world", level="Info")
    assert "hello world" in line
    assert "Info:" in line
    # Timestamp prefix: YYYY-MM-DD HH:MM:SS
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ", line)


def test_log_format_includes_file_and_line():
    line = log_format("msg")
    assert "File:(" in line
    assert "Line:(" in line


def test_configure_logging_is_idempotent():
    a = configure_logging("INFO")
    handlers_before = len(a.handlers)
    b = configure_logging("DEBUG")
    assert a is b
    assert len(b.handlers) == handlers_before  # no duplicate handlers
    assert b.level == logging.DEBUG


def test_get_logger_namespacing():
    assert get_logger("cli").name == "cgt.cli"
    assert get_logger().name == "cgt"
