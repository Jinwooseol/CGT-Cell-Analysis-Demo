"""CSV input/output helpers.

The instrument exports used by this pipeline carry a two-row metadata header
above the tabular body (row 0-1 are free-form metadata, row 2 is the column
header). These helpers centralise reading and re-writing that layout so the
workers do not each re-implement the header juggling.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_table(path: str | Path, **kwargs) -> pd.DataFrame:
    """Read a plain CSV into a DataFrame."""
    return pd.read_csv(path, **kwargs)


def write_table(df: pd.DataFrame, path: str | Path, *, index: bool = False) -> None:
    """Write a DataFrame to CSV, creating parent directories as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index)


def read_two_row_header(
    path: str | Path, *, encoding: str = "utf-8", drop_unnamed: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read an instrument export with a two-row metadata header.

    Args:
        path: Source CSV path.
        encoding: File encoding (default UTF-8).
        drop_unnamed: Drop trailing ``Unnamed: N`` columns produced by ragged rows.

    Returns:
        ``(header, body)`` where ``header`` is the first two raw rows and
        ``body`` is the tabular data with its column header at row index 2.
    """
    header = pd.read_csv(path, encoding=encoding, nrows=2, header=None)
    body = pd.read_csv(path, encoding=encoding, header=2)
    if drop_unnamed:
        body = body.loc[:, ~body.columns.str.contains(r"^Unnamed")]
    return header, body


def write_two_row_header(
    header: pd.DataFrame, body: pd.DataFrame, path: str | Path, *, encoding: str = "utf-8"
) -> None:
    """Write a two-row metadata header followed by a tabular body.

    Mirrors :func:`read_two_row_header`: the metadata header is written without a
    column row, then the body is appended with its own column header.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    header.to_csv(path, index=False, mode="w", header=False, encoding=encoding)
    body.to_csv(path, index=False, mode="a", header=True, encoding=encoding)
