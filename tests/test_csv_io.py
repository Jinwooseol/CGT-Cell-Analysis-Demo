"""Tests for the CSV I/O helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from cgt_cell_analysis_demo.io.csv_io import (
    read_table,
    read_two_row_header,
    write_table,
    write_two_row_header,
)


def test_table_roundtrip(tmp_path: Path):
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    path = tmp_path / "nested" / "t.csv"
    write_table(df, path)  # also creates parent dirs
    assert path.exists()
    back = read_table(path)
    pd.testing.assert_frame_equal(df, back)


def test_two_row_header_roundtrip(tmp_path: Path):
    path = tmp_path / "instrument.csv"
    # Two metadata rows, then a header row, then body.
    path.write_text(
        "meta,info,2026\n"
        "device,plateX,\n"
        "Well Number,X coordination,Y coordination\n"
        "1,856,180\n"
        "2,957,180\n",
        encoding="utf-8",
    )
    header, body = read_two_row_header(path)
    assert header.shape[0] == 2
    assert list(body.columns) == ["Well Number", "X coordination", "Y coordination"]
    assert len(body) == 2

    out = tmp_path / "out.csv"
    write_two_row_header(header, body, out)
    header2, body2 = read_two_row_header(out)
    pd.testing.assert_frame_equal(body.reset_index(drop=True), body2.reset_index(drop=True))


def test_two_row_header_drops_unnamed(tmp_path: Path):
    path = tmp_path / "ragged.csv"
    path.write_text(
        "m,,\n,,\nWell Number,Value,\n1,10,\n",
        encoding="utf-8",
    )
    _, body = read_two_row_header(path, drop_unnamed=True)
    assert all(not c.startswith("Unnamed") for c in body.columns)
