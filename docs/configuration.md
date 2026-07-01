# Configuration

Configuration is a single JSON document modelled by the typed `AppConfig` dataclass
(`cgt_cell_analysis_demo/config.py`).

## Files

- `config.example.json` — the committed template.
- `config.json` — your local copy (git-ignored). Create it with
  `cp config.example.json config.json`.

If `config.json` is absent, both the GUI and CLI fall back to the schema defaults.

## Schema

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `sensor_map` | path | `reference_data/ref_sensor_map_hd.tif` | Reference sensor map (optical + PCR). |
| `marker_7x7` | path | `reference_data/ref_marker_position_7x7.csv` | Optical reference markers. |
| `marker_5x5` | path | `reference_data/ref_marker_position_5x5.csv` | PCR reference markers. |
| `well_csv` | path | `reference_data/ref_well_position.csv` | Reference well coordinates. |
| `ai_model_weights_path` | path | `models/demo_model_weights.pth` | Cell-counting model weights (not shipped). |
| `batch_size` | int | `32` | Inference batch size; must be > 0. |
| `confidence_threshold` | float | `0.5` | Fractional-score rounding threshold; must be in `[0, 1]`. |
| `image_size` | int | `224` | Model input resolution. |
| `use_gpu` | bool | `true` | Use CUDA when available. |
| `use_half_precision` | bool | `false` | FP16 inference (GPU only). |
| `num_workers` | int | `4` | Image-loading threads; must be > 0. |
| `output_format` | str | `"csv"` | Output format. |
| `include_metadata` | bool | `true` | Include metadata in outputs. |
| `developer_mode` | bool | `false` | Enable extra developer UI. |

Unknown keys are ignored on load, and missing keys fall back to defaults — the schema can evolve
without breaking older config files.

## Path resolution

Path-valued keys may be absolute or relative. Relative paths are resolved against the **project
root** by `AppConfig.resolve_paths()`. The CLI and GUI both resolve paths before use, so a config
checked into a repo stays portable across machines.

## Validation

`AppConfig.validate()` returns a list of human-readable problems (empty when valid):

- reference files exist (when `require_refs=True`),
- model weights exist (when `require_model=True`),
- numeric fields are within their valid ranges.

The CLI surfaces this via `cgt-cli validate`.

## Programmatic use

```python
from cgt_cell_analysis_demo.config import AppConfig

cfg = AppConfig.from_file("config.json").resolve_paths()
problems = cfg.validate(require_model=True)
if problems:
    raise SystemExit("\n".join(problems))

ref_paths = cfg.ref_paths()                 # -> RefPaths for the indexing workers
counting_cfg = cfg.cell_counting_config()   # -> dict for the cell-counting worker
```
