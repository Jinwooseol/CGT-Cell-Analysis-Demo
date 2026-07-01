"""Smoke test for the cell-counting model architecture (CPU, untrained)."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("timm")


def test_regressor_forward_shape():
    from cgt_cell_analysis_demo.model.cell_counting_ai_model import CellCountingRegressor

    model = CellCountingRegressor(pretrained=False).eval()
    # Batch of 2 so BatchNorm1d layers are happy in eval mode regardless.
    x = torch.randn(2, 3, 224, 224)
    with torch.no_grad():
        out = model(x)
    assert tuple(out.shape) == (2, 1)
