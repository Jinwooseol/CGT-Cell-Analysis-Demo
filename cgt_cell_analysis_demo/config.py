"""Typed application configuration.

This module centralises the configuration schema shared by the desktop GUI and
the headless command-line runner. It provides a single, well-documented
``AppConfig`` dataclass with helpers to load from / save to JSON, resolve
relative paths against the project root, validate referenced resources, and
project the configuration into the shapes expected by the pipeline workers.

The configuration file format is plain JSON (see ``config.example.json``).
Unknown keys are ignored on load, and missing keys fall back to defaults, so the
schema can evolve without breaking existing config files.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cgt_cell_analysis_demo import (
    __config_path__,
    __project_path__,
)

if TYPE_CHECKING:  # avoid importing the heavy CV stack at module import time
    from cgt_cell_analysis_demo.core.workers.well_index_common import RefPaths

# Keys whose values are filesystem paths and may be given relative to the
# project root. ``resolve_paths`` turns these into absolute paths.
PATH_KEYS: tuple[str, ...] = (
    "sensor_map",
    "marker_7x7",
    "marker_5x5",
    "well_csv",
    "ai_model_weights_path",
)


@dataclass(slots=True)
class AppConfig:
    """Validated configuration for the cell-analysis pipeline.

    Paths may be absolute or relative to the project root. Use
    :meth:`resolve_paths` to obtain a copy with all path fields made absolute.
    """

    # --- Reference data (used by optical / PCR well indexing) ---
    sensor_map: str = "reference_data/ref_sensor_map_hd.tif"
    marker_7x7: str = "reference_data/ref_marker_position_7x7.csv"
    marker_5x5: str = "reference_data/ref_marker_position_5x5.csv"
    well_csv: str = "reference_data/ref_well_position.csv"

    # --- Model inference (cell counting) ---
    ai_model_weights_path: str = "models/demo_model_weights.pth"
    batch_size: int = 32
    confidence_threshold: float = 0.5
    image_size: int = 224
    use_gpu: bool = True
    use_half_precision: bool = False
    num_workers: int = 4

    # --- Output / misc ---
    output_format: str = "csv"
    include_metadata: bool = True
    developer_mode: bool = False

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AppConfig:
        """Build a config from a dict, ignoring unknown keys."""
        data = data or {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def from_file(cls, path: str | Path | None = None) -> AppConfig:
        """Load configuration from JSON.

        Falls back to defaults when ``path`` does not exist. When ``path`` is
        ``None`` the project-level ``config.json`` is used.
        """
        path = Path(path) if path is not None else Path(__config_path__)
        if not path.exists():
            return cls()
        with path.open("r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------ #
    # Path handling
    # ------------------------------------------------------------------ #
    def resolve_paths(self, base: str | Path | None = None) -> AppConfig:
        """Return a copy with all path fields resolved to absolute paths.

        Relative paths are interpreted against ``base`` (the project root by
        default). Absolute paths are kept unchanged.
        """
        root = Path(base) if base is not None else Path(__project_path__)
        data = self.to_dict()
        for key in PATH_KEYS:
            value = data.get(key, "")
            if value and not Path(value).is_absolute():
                data[key] = str((root / value).resolve())
        return AppConfig.from_dict(data)

    def ref_paths(self) -> RefPaths:
        """Project the reference-data paths into a worker ``RefPaths`` object."""
        from cgt_cell_analysis_demo.core.workers.well_index_common import RefPaths

        return RefPaths(
            sensor_map_tif=Path(self.sensor_map),
            marker_7x7_csv=Path(self.marker_7x7) if self.marker_7x7 else None,
            marker_5x5_csv=Path(self.marker_5x5) if self.marker_5x5 else None,
            well_csv=Path(self.well_csv) if self.well_csv else None,
        )

    def cell_counting_config(self) -> dict[str, Any]:
        """Return the dict shape expected by the cell-counting worker."""
        return {
            "model_weights_path": self.ai_model_weights_path,
            "batch_size": self.batch_size,
            "confidence_threshold": self.confidence_threshold,
            "image_size": self.image_size,
            "use_gpu": self.use_gpu,
            "use_half_precision": self.use_half_precision,
            "num_workers": self.num_workers,
            "output_format": self.output_format,
        }

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def validate(self, *, require_refs: bool = True, require_model: bool = False) -> list[str]:
        """Return a list of human-readable problems (empty when valid).

        Args:
            require_refs: Verify that the reference-data files exist.
            require_model: Verify that the model-weights file exists.
        """
        resolved = self.resolve_paths()
        problems: list[str] = []

        if require_refs:
            for key in ("sensor_map", "marker_7x7", "marker_5x5", "well_csv"):
                value = getattr(resolved, key)
                if not value or not Path(value).exists():
                    problems.append(f"Reference file missing for '{key}': {value or '<empty>'}")

        if require_model:
            model = resolved.ai_model_weights_path
            if not model or not Path(model).exists():
                problems.append(f"Model weights not found: {model or '<empty>'}")

        if self.batch_size <= 0:
            problems.append(f"batch_size must be positive (got {self.batch_size})")
        if not 0.0 <= self.confidence_threshold <= 1.0:
            problems.append(
                f"confidence_threshold must be in [0, 1] (got {self.confidence_threshold})"
            )
        if self.num_workers <= 0:
            problems.append(f"num_workers must be positive (got {self.num_workers})")

        return problems
