"""Tests for the pure geometry / well-matching helpers in well_index_common."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cgt_cell_analysis_demo.core.workers.well_index_common import (
    estimate_grid_properties,
    find_overlap_transform,
    match_well_index,
    snap_grid_to_detected_points,
    stitch_optical_images_from_folder,
)


def test_find_overlap_transform_identity():
    pts = [(0, 0), (100, 0), (0, 100), (100, 100)]
    affine = find_overlap_transform(pts, pts)
    assert affine.shape == (2, 3)
    # Identity mapping -> ~[[1,0,0],[0,1,0]]
    np.testing.assert_allclose(affine, np.array([[1, 0, 0], [0, 1, 0]]), atol=1e-3)


def test_find_overlap_transform_translation():
    src = [(0, 0), (100, 0), (0, 100), (100, 100)]
    dst = [(x + 10, y + 5) for x, y in src]
    affine = find_overlap_transform(src, dst)
    np.testing.assert_allclose(affine[:, 2], np.array([10, 5]), atol=1e-2)


def test_find_overlap_transform_insufficient_points_returns_identity():
    affine = find_overlap_transform([(0, 0), (1, 1)], [(0, 0), (1, 1)])
    np.testing.assert_array_equal(affine, np.eye(2, 3, dtype=np.float32))


def test_snap_grid_to_detected_points_snaps_within_tolerance():
    estimated = [(0, 0), (100, 100)]
    detected = [(1, 1)]
    snapped = snap_grid_to_detected_points(estimated, detected, tolerance=5.0)
    assert snapped[0] == (1, 1)  # snapped to nearby detection
    assert snapped[1] == (100, 100)  # no detection nearby -> unchanged


def test_snap_grid_with_no_detections_returns_rounded():
    estimated = [(2.4, 3.6)]
    snapped = snap_grid_to_detected_points(estimated, [], tolerance=5.0)
    assert snapped == [(2, 4)]


def test_estimate_grid_properties_recovers_spacing():
    # Anisotropic grid: x spacing 100 (6 cols), y spacing 50 (4 rows).
    pts = [(c * 100, r * 50) for r in range(4) for c in range(6)]
    axes, hx, hy = estimate_grid_properties(pts)
    assert axes.shape == (2, 2)
    spacings = sorted([hx, hy])
    np.testing.assert_allclose(spacings, [50, 100], rtol=0.15)


def test_match_well_index_basic():
    ref = pd.DataFrame(
        {
            "Well Number": [1, 2, 3],
            "X coordination": [0, 100, 200],
            "Y coordination": [0, 0, 0],
        }
    )
    target = pd.DataFrame(
        {
            "Well Number": [10, 20, 30],
            "X coordination": [1, 101, 201],
            "Y coordination": [0, 0, 0],
        }
    )
    out = match_well_index(ref, target, threshold=25.0)
    assert len(out) == 3
    assert set(out["Absolute Well Number"]) == {1, 2, 3}
    assert set(out["Well Number"]) == {10, 20, 30}


def test_match_well_index_empty_inputs():
    empty = pd.DataFrame(columns=["Well Number", "X coordination", "Y coordination"])
    out = match_well_index(empty, empty)
    assert out.empty
    assert "Absolute Well Number" in out.columns


def test_stitch_missing_folder_returns_false(tmp_path):
    assert stitch_optical_images_from_folder(tmp_path / "nope", tmp_path / "o.png") is False


def test_stitch_wrong_image_count_returns_false(tmp_path):
    # Two empty .bmp files -> not the required 36 -> graceful False.
    for i in range(2):
        (tmp_path / f"{i}.bmp").write_bytes(b"\x00")
    assert stitch_optical_images_from_folder(tmp_path, tmp_path / "o.png") is False


@pytest.mark.parametrize("n", [0, 2, 5])
def test_snap_preserves_length(n):
    estimated = [(i, i) for i in range(n)]
    snapped = snap_grid_to_detected_points(estimated, [(0, 0)], tolerance=1.0)
    assert len(snapped) == n
