"""Integration test: the merge worker driven headlessly end-to-end.

Exercises the real ``MergeCellCountPcr`` worker plus the shared
``io.csv_io`` two-row-header helpers and the CLI worker driver.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from cgt_cell_analysis_demo.cli import _drive_worker
from cgt_cell_analysis_demo.core.workers.merge_cell_count_pcr import MergeCellCountPcr


def _write_labeled(path: Path, abs_wells: list[int]) -> None:
    rows = "\n".join(f"{i + 1},{w},{i * 0.1:.1f}" for i, w in enumerate(abs_wells))
    path.write_text(
        "instrument,export\nchannel,meta\nWell Number,Absolute Well Number,Signal\n" + rows + "\n",
        encoding="utf-8",
    )


def test_merge_worker_produces_outputs(tmp_path, qapp):
    count_dir = tmp_path / "02_count"
    pcr_dir = tmp_path / "03_pcr"
    out_dir = tmp_path / "04_merge"
    count_dir.mkdir()
    pcr_dir.mkdir()

    # Stage 2 output: per-well cell counts.
    pd.DataFrame(
        {
            "Absolute Well Number": [1, 2, 3],
            "Average Cell Count Score": [1.2, 2.4, 0.0],
            "Cell Count": [1, 2, 0],
        }
    ).to_csv(count_dir / "Predicted_Cell_Count.csv", index=False)

    # Stage 3 output: labeled raw data for each channel.
    _write_labeled(pcr_dir / "Labeled_rawData_G.csv", [1, 2, 3])
    _write_labeled(pcr_dir / "Labeled_rawData_R.csv", [1, 2, 3])

    worker = MergeCellCountPcr("S001", str(count_dir), str(pcr_dir), str(out_dir))
    result = _drive_worker(worker, show_progress=False)

    assert result["sample_id"] == "S001"
    g_out = out_dir / "rawCellData_G.csv"
    r_out = out_dir / "rawCellData_R.csv"
    assert g_out.exists() and r_out.exists()

    # Body (header rows skipped) should carry the merged cell-count columns.
    body = pd.read_csv(g_out, header=2)
    assert "Cell Count" in body.columns
    assert "Average Cell Count Score" in body.columns
    assert len(body) == 3
