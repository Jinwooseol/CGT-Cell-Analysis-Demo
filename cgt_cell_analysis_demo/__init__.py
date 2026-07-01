"""cgt_cell_analysis_demo package initialization."""

import sys
from pathlib import Path

__all__ = []


def _get_base_path() -> Path:
    """Return the base path for resources in dev and PyInstaller modes."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


_base_path = _get_base_path()
__project_path__ = _base_path
__resource_path__ = _base_path / "cgt_cell_analysis_demo" / "resources"
__reference_data_path__ = _base_path / "reference_data"
__models_path__ = _base_path / "models"
__config_path__ = _base_path / "config.json"
__version__ = "1.0.0-demo"
