# Architecture

## Overview

The application uses a **controller-plus-worker** design with clear layer boundaries. The processing
core is independent of any front-end, so it can be driven by either the desktop GUI or the headless
CLI.

```
┌────────────┐      ┌────────────┐
│   UI (Qt)  │      │    CLI     │
└─────┬──────┘      └─────┬──────┘
      │  run_step / run         │  stage_*()
      ▼                         ▼
        ┌───────────────────────────┐
        │     PipelineController     │  (chains stages over QThreadPool)
        └─────────────┬─────────────┘
                      │ start worker
                      ▼
        ┌───────────────────────────┐
        │     Worker (QRunnable)     │  one per stage, cancellable
        └─────────────┬─────────────┘
                      │ uses
                      ▼
        io  ·  model  ·  geometry helpers
                      │
        signals: log · progress · done · error  ──► back to the front-end
```

## Layers

| Layer | Package | Responsibility |
|-------|---------|----------------|
| UI | `ui/` | PySide6 main window, panels (file tree, preview, pipeline, queue, log, progress), and dialogs. |
| CLI | `cli.py` | Display-free runner; drives the workers synchronously via a minimal `QCoreApplication`. |
| Controller | `core/pipeline_controller.py` | Starts each stage, wires worker signals, and auto-chains stage 1 → 2 → 4 (with 3 → 4). |
| Workers | `core/workers/` | `OpticalWellIndexWorker`, `CellCounting`, `PcrWellIndexingWorker`, `MergeCellCountPcr`, `ModelTrainingWorker`. |
| Config | `config.py` | Typed `AppConfig` (load/save/resolve/validate) shared by both front-ends. |
| I/O | `io/csv_io.py` | CSV helpers, including the instrument two-row-header format. |
| Model | `model/` | `CellCountingRegressor` (EfficientNet-B4 head) and job data models. |
| Geometry | `core/workers/well_index_common.py` | Contour/marker detection, PCA grid estimation, affine alignment, KD-tree matching, stitching. |
| Util | `util/logger.py` | `log_format` for signal strings; `configure_logging`/`get_logger` for headless logging. |

## Execution model

- Each stage is a `QRunnable` started on the global `QThreadPool`, so the GUI thread never blocks.
- Workers communicate exclusively through Qt signals (`log`, `progress`, `done`, `error`), which the
  GUI renders in panels and the CLI prints to the console.
- Cancellation is cooperative: workers call `check_abort()` at safe points and raise to unwind.
- In the CLI, `worker.run()` is invoked directly; because signals use direct connections, slots run
  inline and no event loop is needed.

## Data flow

1. **Optical Well Indexing** reads optical tiles, detects wells and markers, estimates the grid
   (PCA), aligns each tile to the reference layout (affine), matches wells (KD-tree), and writes
   cropped per-well images under `Well_Image/`.
2. **Cell Counting** loads those crops in batched, threaded fashion and runs the regressor to produce
   `Predicted_Cell_Count.csv` (per-well averaged scores).
3. **PCR Well Indexing** detects the 5×5 marker grid on PCR imagery, transforms the G/R channel well
   coordinates into the reference layout, and writes `Labeled_rawData_{G,R}.csv`.
4. **Merge Results** joins the cell-count table with the labeled PCR data on the absolute well number
   and writes `rawCellData_{G,R}.csv`.

## Why this structure

- The processing core is reusable and testable independently of the UI.
- Stage boundaries are explicit, making the pipeline easy to extend or reorder.
- Long-running image and inference work stays off the UI thread.
- The same code path backs both interactive (GUI) and automated (CLI/CI) execution.
