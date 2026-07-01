"""Tests for the typed application configuration."""

from __future__ import annotations

import json
from pathlib import Path

from cgt_cell_analysis_demo.config import AppConfig


def test_defaults_are_sane():
    cfg = AppConfig()
    assert cfg.batch_size == 32
    assert 0.0 <= cfg.confidence_threshold <= 1.0
    assert cfg.output_format == "csv"


def test_from_dict_ignores_unknown_keys():
    cfg = AppConfig.from_dict({"batch_size": 8, "totally_unknown": 123})
    assert cfg.batch_size == 8
    assert not hasattr(cfg, "totally_unknown")


def test_roundtrip_save_and_load(tmp_path: Path):
    cfg = AppConfig(batch_size=16, use_gpu=False)
    path = tmp_path / "config.json"
    cfg.save(path)
    loaded = AppConfig.from_file(path)
    assert loaded.batch_size == 16
    assert loaded.use_gpu is False


def test_from_file_missing_returns_defaults(tmp_path: Path):
    cfg = AppConfig.from_file(tmp_path / "does_not_exist.json")
    assert cfg == AppConfig()


def test_resolve_paths_makes_absolute(tmp_path: Path):
    cfg = AppConfig(sensor_map="reference_data/x.tif")
    resolved = cfg.resolve_paths(base=tmp_path)
    assert Path(resolved.sensor_map).is_absolute()
    assert resolved.sensor_map.endswith("x.tif")


def test_resolve_paths_keeps_absolute(tmp_path: Path):
    abs_path = str((tmp_path / "abs.tif").resolve())
    cfg = AppConfig(sensor_map=abs_path)
    assert cfg.resolve_paths(base=tmp_path).sensor_map == abs_path


def test_cell_counting_config_shape():
    cfg = AppConfig(batch_size=4, confidence_threshold=0.25)
    cc = cfg.cell_counting_config()
    assert cc["model_weights_path"] == cfg.ai_model_weights_path
    assert cc["batch_size"] == 4
    assert cc["confidence_threshold"] == 0.25


def test_ref_paths_projection():
    cfg = AppConfig()
    rp = cfg.ref_paths()
    assert rp.sensor_map_tif == Path(cfg.sensor_map)
    assert rp.marker_7x7_csv == Path(cfg.marker_7x7)


def test_validate_flags_missing_refs(tmp_path: Path):
    cfg = AppConfig(sensor_map="nope/missing.tif")
    problems = cfg.validate(require_refs=True, require_model=False)
    assert any("sensor_map" in p for p in problems)


def test_validate_flags_bad_numbers():
    cfg = AppConfig(batch_size=0, confidence_threshold=5.0, num_workers=-1)
    problems = cfg.validate(require_refs=False)
    assert any("batch_size" in p for p in problems)
    assert any("confidence_threshold" in p for p in problems)
    assert any("num_workers" in p for p in problems)


def test_validate_passes_for_existing_refs(tmp_path: Path):
    for name in ("a.tif", "b.csv", "c.csv", "d.csv"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    cfg = AppConfig(
        sensor_map=str(tmp_path / "a.tif"),
        marker_7x7=str(tmp_path / "b.csv"),
        marker_5x5=str(tmp_path / "c.csv"),
        well_csv=str(tmp_path / "d.csv"),
    )
    assert cfg.validate(require_refs=True, require_model=False) == []


def test_example_config_matches_schema():
    """config.example.json should only contain keys the schema understands."""
    example = Path(__file__).resolve().parent.parent / "config.example.json"
    data = json.loads(example.read_text(encoding="utf-8"))
    cfg = AppConfig.from_dict(data)
    # Every example key should be a real field (no silent drops of valid keys).
    known = set(cfg.to_dict())
    assert set(data) <= known
