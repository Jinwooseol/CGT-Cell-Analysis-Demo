"""Headless command-line runner for the cell-analysis pipeline.

The desktop GUI is one front-end for the pipeline; this module is a second,
display-free one. It drives the exact same worker classes used by the GUI,
which keeps a single source of truth for the processing logic and makes the
pipeline scriptable, testable, and CI-friendly.

Examples
--------
Run the full four-stage pipeline for one sample::

    cgt-cli run --sample S001 \
        --optical-tiles data/S001/optical \
        --pcr data/S001/pcr \
        --out-root work

Run a single stage::

    cgt-cli optical --tiles data/S001/optical --out work/S001/01_optical
    cgt-cli count   --images work/S001/01_optical/Well_Image --out work/S001/02_count

Validate configuration / referenced resources::

    cgt-cli validate --require-model
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from cgt_cell_analysis_demo import __version__
from cgt_cell_analysis_demo.config import AppConfig
from cgt_cell_analysis_demo.util.logger import configure_logging, get_logger

log = get_logger("cli")

# Stage sub-directory names used by the `run` orchestration.
STAGE_DIRS = {
    "optical": "01_optical_indexing",
    "count": "02_cell_counting",
    "pcr": "03_pcr_indexing",
    "merge": "04_merge_results",
}


# --------------------------------------------------------------------------- #
# Worker driver
# --------------------------------------------------------------------------- #
class WorkerError(RuntimeError):
    """Raised when a pipeline worker reports an error signal."""


def _ensure_qapp() -> Any:
    """Create (once) a headless QCoreApplication so worker QObjects can emit signals."""
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv[:1])
    return app


def _drive_worker(worker: Any, *, show_progress: bool = True) -> dict[str, Any]:
    """Run a ``BaseWorker`` synchronously and return its ``done`` artifacts.

    Worker log/progress/done/error signals are connected to console output.
    Because ``worker.run()`` runs in the calling thread with direct signal
    connections, slots execute inline — no Qt event loop is required.
    """
    _ensure_qapp()

    result: dict[str, Any] = {}
    failure: dict[str, str] = {}
    last_pct = -1

    def on_log(msg: str) -> None:
        log.info(msg)

    def on_progress(pct: int) -> None:
        nonlocal last_pct
        if show_progress and pct >= last_pct + 10:
            last_pct = pct - (pct % 10)
            log.info("  progress: %d%%", pct)

    def on_done(artifacts: dict) -> None:
        result.update(artifacts or {})

    def on_error(message: str) -> None:
        failure["message"] = message

    worker.signals.log.connect(on_log)
    worker.signals.progress.connect(on_progress)
    worker.signals.done.connect(on_done)
    worker.signals.error.connect(on_error)

    worker.run()

    if failure:
        raise WorkerError(failure["message"])
    return result


# --------------------------------------------------------------------------- #
# Stage helpers
# --------------------------------------------------------------------------- #
def _load_config(args: argparse.Namespace) -> AppConfig:
    cfg = AppConfig.from_file(args.config).resolve_paths()
    return cfg


def stage_optical(cfg: AppConfig, tiles: Path, out: Path) -> dict[str, Any]:
    from cgt_cell_analysis_demo.core.workers.optical_well_indexing import OpticalWellIndexWorker

    out.mkdir(parents=True, exist_ok=True)
    worker = OpticalWellIndexWorker(str(tiles), cfg.ref_paths(), str(out))
    return _drive_worker(worker)


def stage_count(cfg: AppConfig, images: Path, out: Path, sample_id: str) -> dict[str, Any]:
    from cgt_cell_analysis_demo.core.workers.cell_counting import CellCounting

    out.mkdir(parents=True, exist_ok=True)
    worker = CellCounting(sample_id, str(images), str(out), config=cfg.cell_counting_config())
    return _drive_worker(worker)


def stage_pcr(cfg: AppConfig, pcr: Path, out: Path) -> dict[str, Any]:
    from cgt_cell_analysis_demo.core.workers.pcr_well_indexing import PcrWellIndexingWorker

    out.mkdir(parents=True, exist_ok=True)
    worker = PcrWellIndexingWorker(str(pcr), cfg.ref_paths(), str(out))
    return _drive_worker(worker)


def stage_merge(count_dir: Path, pcr_dir: Path, out: Path, sample_id: str) -> dict[str, Any]:
    from cgt_cell_analysis_demo.core.workers.merge_cell_count_pcr import MergeCellCountPcr

    out.mkdir(parents=True, exist_ok=True)
    worker = MergeCellCountPcr(sample_id, str(count_dir), str(pcr_dir), str(out))
    return _drive_worker(worker)


# --------------------------------------------------------------------------- #
# Command handlers
# --------------------------------------------------------------------------- #
def cmd_optical(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    stage_optical(cfg, Path(args.tiles), Path(args.out))
    log.info("Optical indexing complete -> %s", args.out)
    return 0


def cmd_count(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    stage_count(cfg, Path(args.images), Path(args.out), args.sample)
    log.info("Cell counting complete -> %s", args.out)
    return 0


def cmd_pcr(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    stage_pcr(cfg, Path(args.pcr), Path(args.out))
    log.info("PCR indexing complete -> %s", args.out)
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    stage_merge(Path(args.count_dir), Path(args.pcr_dir), Path(args.out), args.sample)
    log.info("Merge complete -> %s", args.out)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    sample = args.sample
    root = Path(args.out_root) / sample

    log.info("=== Pipeline start: sample=%s ===", sample)

    optical_out = root / STAGE_DIRS["optical"]
    stage_optical(cfg, Path(args.optical_tiles), optical_out)

    well_images = optical_out / "Well_Image"
    count_out = root / STAGE_DIRS["count"]
    stage_count(cfg, well_images, count_out, sample)

    pcr_out = root / STAGE_DIRS["pcr"]
    stage_pcr(cfg, Path(args.pcr), pcr_out)

    merge_out = root / STAGE_DIRS["merge"]
    stage_merge(count_out, pcr_out, merge_out, sample)

    log.info("=== Pipeline complete: results in %s ===", root)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    cfg = AppConfig.from_file(args.config).resolve_paths()
    problems = cfg.validate(require_refs=True, require_model=args.require_model)
    if problems:
        log.error("Configuration is INVALID:")
        for p in problems:
            log.error("  - %s", p)
        return 1
    log.info("Configuration is valid.")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    cfg = AppConfig.from_file(args.config).resolve_paths()
    log.info("cgt-cell-analysis-demo %s", __version__)
    log.info("Configuration (resolved):")
    for key, value in cfg.to_dict().items():
        log.info("  %-24s %s", key, value)
    return 0


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def _add_config_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--config",
        default=None,
        help="Path to a JSON config file (default: project config.json).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cgt-cli",
        description="Headless runner for the CGT cell-analysis pipeline.",
    )
    parser.add_argument("--version", action="version", version=f"cgt-cli {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable DEBUG-level logging.")
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    handlers: dict[str, Callable[[argparse.Namespace], int]] = {}

    # run (full pipeline)
    p_run = sub.add_parser("run", help="Run the full four-stage pipeline for one sample.")
    p_run.add_argument("--sample", required=True, help="Sample identifier.")
    p_run.add_argument("--optical-tiles", required=True, help="Folder of optical tile images.")
    p_run.add_argument("--pcr", required=True, help="Folder with PCR image + rawData CSVs.")
    p_run.add_argument("--out-root", default="work", help="Root output folder (default: work).")
    _add_config_arg(p_run)
    handlers["run"] = cmd_run

    # optical
    p_opt = sub.add_parser("optical", help="Stage 1: optical well indexing.")
    p_opt.add_argument("--tiles", required=True, help="Folder of optical tile images.")
    p_opt.add_argument("--out", required=True, help="Output folder.")
    _add_config_arg(p_opt)
    handlers["optical"] = cmd_optical

    # count
    p_cnt = sub.add_parser("count", help="Stage 2: AI cell counting.")
    p_cnt.add_argument("--images", required=True, help="Folder of cropped well images.")
    p_cnt.add_argument("--out", required=True, help="Output folder.")
    p_cnt.add_argument("--sample", default="sample", help="Sample identifier.")
    _add_config_arg(p_cnt)
    handlers["count"] = cmd_count

    # pcr
    p_pcr = sub.add_parser("pcr", help="Stage 3: PCR well indexing.")
    p_pcr.add_argument("--pcr", required=True, help="Folder with PCR image + rawData CSVs.")
    p_pcr.add_argument("--out", required=True, help="Output folder.")
    _add_config_arg(p_pcr)
    handlers["pcr"] = cmd_pcr

    # merge
    p_mrg = sub.add_parser("merge", help="Stage 4: merge cell counts with PCR data.")
    p_mrg.add_argument("--count-dir", required=True, help="Stage 2 output folder.")
    p_mrg.add_argument("--pcr-dir", required=True, help="Stage 3 output folder.")
    p_mrg.add_argument("--out", required=True, help="Output folder.")
    p_mrg.add_argument("--sample", default="sample", help="Sample identifier.")
    handlers["merge"] = cmd_merge

    # validate
    p_val = sub.add_parser("validate", help="Validate config and referenced resources.")
    p_val.add_argument(
        "--require-model", action="store_true", help="Also require the model weights file."
    )
    _add_config_arg(p_val)
    handlers["validate"] = cmd_validate

    # info
    p_info = sub.add_parser("info", help="Print version and resolved configuration.")
    _add_config_arg(p_info)
    handlers["info"] = cmd_info

    parser.set_defaults(_handlers=handlers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging("DEBUG" if args.verbose else "INFO")

    handler = args._handlers[args.command]
    try:
        return handler(args)
    except WorkerError as exc:
        log.error("Pipeline failed: %s", exc)
        return 1
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.error("Interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
