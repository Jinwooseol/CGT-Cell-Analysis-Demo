from pathlib import Path

from PySide6.QtCore import QObject, QThreadPool, Signal

from cgt_cell_analysis_demo.core.workers.base_worker import BaseWorker
from cgt_cell_analysis_demo.core.workers.cell_counting import CellCounting
from cgt_cell_analysis_demo.core.workers.merge_cell_count_pcr import MergeCellCountPcr
from cgt_cell_analysis_demo.core.workers.model_training import ModelTrainingWorker
from cgt_cell_analysis_demo.core.workers.optical_well_indexing import OpticalWellIndexWorker
from cgt_cell_analysis_demo.core.workers.pcr_well_indexing import PcrWellIndexingWorker
from cgt_cell_analysis_demo.core.workers.well_index_common import RefPaths
from cgt_cell_analysis_demo.util.logger import log_format


class PipelineController(QObject):
    log = Signal(str)
    progress = Signal(int, int)  # step, percent
    done = Signal(int, dict)  # step, artifacts
    error = Signal(int, str)
    auto_trigger_step2 = Signal(str, str)  # sample_id, well_image_folder
    auto_trigger_step3 = Signal(str, str)  # sample_id, pcr_folder
    auto_trigger_step4 = Signal(str, str)  # sample_id, merge_folder
    # Training specific signals could be added later if needed

    def __init__(self):
        super().__init__()
        self.pool = QThreadPool.globalInstance()
        self.active_workers = {}
        self.auto_chain_enabled = True  # Enable automatic step chaining

    def run_step1(self, sample_id: str, tiles_dir: str, ref_paths: RefPaths, out_dir: str):
        self.log.emit(
            log_format(
                f"[Step1] start sample={sample_id}, tiles_dir={tiles_dir}, out_dir={out_dir}"
            )
        )
        worker = OpticalWellIndexWorker(tiles_dir, ref_paths, out_dir)
        self._wire_worker(worker, 1)
        self.pool.start(worker)

    # -------- Training entry points --------
    def run_training(
        self,
        sample_id: str,
        image_folder: str,
        label_csv: str,
        out_dir: str,
        config: dict | None = None,
    ):
        self.log.emit(
            log_format(
                f"[Train] start sample={sample_id}, images={image_folder}, labels={label_csv}, out_dir={out_dir}"
            )
        )
        worker = ModelTrainingWorker(
            sample_id, image_folder, label_csv, out_dir, config=config or {}
        )
        self._wire_worker(worker, 101)  # Use 101 as training step id to avoid collision
        self.pool.start(worker)

    def run_step2(self, sample_id: str, folder: str, out_dir: str, config: dict = None):
        self.log.emit(
            log_format(f"[Step2] start sample={sample_id}, folder={folder}, out_dir={out_dir}")
        )
        # Pass the config dict wholesale; the worker will resolve effective params itself
        cfg = config or {}
        self.log.emit(log_format(f"[Step2] config={cfg}"))
        worker = CellCounting(sample_id, folder, out_dir, config=cfg)
        self._wire_worker(worker, 2)
        self.pool.start(worker)

    def run_step3(self, sample_id: str, folder: str, ref_paths: RefPaths, out_dir: str):
        """Formerly Step 4: PCR Image Indexing"""
        self.log.emit(
            log_format(f"[Step3] start sample={sample_id}, folder={folder}, out_dir={out_dir}")
        )
        worker = PcrWellIndexingWorker(folder, ref_paths, out_dir)
        self._wire_worker(worker, 3)
        self.pool.start(worker)

    def run_step4(
        self, sample_id: str, step2_output_folder: str, step3_output_folder: str, out_dir: str
    ):
        """Step 4: Merge Cell Count with PCR Data"""
        self.log.emit(
            log_format(
                f"[Step4] start sample={sample_id}, cell count folder={step2_output_folder}, labeled rawdata folder={step3_output_folder}, out_dir={out_dir}"
            )
        )

        worker = MergeCellCountPcr(sample_id, step2_output_folder, step3_output_folder, out_dir)
        self._wire_worker(worker, 4)
        self.pool.start(worker)

    # ---- internal: common signal wiring ----
    def _wire_worker(self, worker: BaseWorker, step: int):
        self.active_workers[step] = worker
        worker.signals.log.connect(lambda m: self.log.emit(f"[Step{step}] {m}"))
        worker.signals.progress.connect(lambda p: self.progress.emit(step, p))
        worker.signals.done.connect(lambda a: self._on_step_done(step, a))
        worker.signals.error.connect(lambda e: self.error.emit(step, e))

    def _on_step_done(self, step: int, artifacts: dict):
        """Handle step completion and trigger automatic chaining"""
        self.done.emit(step, artifacts)

        # Auto-trigger step 2 when step 1 completes
        if step == 1 and self.auto_chain_enabled:
            self._trigger_step2_from_step1(artifacts)

        # Auto-trigger step 3 when step 2 completes
        if step == 2 and self.auto_chain_enabled:
            self._trigger_step3_from_step2(artifacts)

        # Auto-trigger step 4 when step 3 completes
        if step == 3 and self.auto_chain_enabled:
            self._trigger_step4_from_step3(artifacts)

    def _trigger_step2_from_step1(self, step1_artifacts: dict):
        """Automatically trigger step 2 using step 1 output"""
        try:
            # Extract sample_id and output directory from step 1 artifacts
            out_dir = step1_artifacts.get("output_folder", "")
            if not out_dir:
                self.log.emit(
                    log_format("[AutoChain] No output directory found in step 1 artifacts")
                )
                return

            # Construct the Well_Image folder path
            well_image_folder = str(Path(out_dir) / "Well_Image")

            # Check if Well_Image folder exists
            if not Path(well_image_folder).exists():
                self.log.emit(
                    log_format(f"[AutoChain] Well_Image folder not found: {well_image_folder}")
                )
                return

            # Check if Well_Image folder has any images
            well_image_path = Path(well_image_folder)
            image_files = (
                list(well_image_path.glob("*.png"))
                + list(well_image_path.glob("*.jpg"))
                + list(well_image_path.glob("*.jpeg"))
            )
            if not image_files:
                self.log.emit(
                    log_format(
                        f"[AutoChain] No images found in Well_Image folder: {well_image_folder}"
                    )
                )
                return

            # Extract sample_id from the output directory path
            sample_id = Path(out_dir).parent.name

            self.log.emit(
                log_format(
                    f"[AutoChain] Triggering Step 2 with Well_Image folder: {well_image_folder} ({len(image_files)} images found)"
                )
            )
            self.auto_trigger_step2.emit(sample_id, well_image_folder)

        except Exception as e:
            self.log.emit(log_format(f"[AutoChain] Error triggering step 2: {str(e)}"))

    def _trigger_step3_from_step2(self, step2_artifacts: dict):
        """Automatically trigger step 3 using the already selected PCR folder"""
        try:
            # Extract sample_id from the output directory path
            out_dir = step2_artifacts.get("output_folder", "")
            if not out_dir:
                self.log.emit(
                    log_format("[AutoChain] No output directory found in step 2 artifacts")
                )
                return

            sample_id = Path(out_dir).parent.name
            self.log.emit(log_format(f"[AutoChain] Triggering Step 3 for sample: {sample_id}"))

            # Emit signal to main window to handle step 3 auto-trigger
            # The main window will use the already selected PCR folder
            self.auto_trigger_step3.emit(sample_id, out_dir)

        except Exception as e:
            self.log.emit(log_format(f"[AutoChain] Error triggering step 3: {str(e)}"))

    def _trigger_step4_from_step3(self, step3_artifacts: dict):
        """Automatically trigger step 4 using step 3 output"""
        try:
            # Extract sample_id from the output directory path
            out_dir = step3_artifacts.get("output_folder", "")
            if not out_dir:
                self.log.emit(
                    log_format("[AutoChain] No output directory found in step 3 artifacts")
                )
                return

            sample_id = Path(out_dir).parent.name
            self.log.emit(log_format(f"[AutoChain] Triggering Step 4 for sample: {sample_id}"))

            # Emit signal to main window to handle step 4 auto-trigger
            # The main window will use the same folder as step 3 (PCR folder)
            self.auto_trigger_step4.emit(sample_id, out_dir)

        except Exception as e:
            self.log.emit(log_format(f"[AutoChain] Error triggering step 4: {str(e)}"))

    # ---- control API ----
    def cancel_step(self, step: int):
        if step in self.active_workers:
            self.log.emit(f"[Step{step}] cancel requested")
            self.active_workers[step].request_cancel()


class PlaceholderWorker(BaseWorker):
    """Placeholder worker for unimplemented pipeline steps"""

    def __init__(self, step_name: str, sample_id: str, folder: str, out_dir: str):
        super().__init__()
        self.step_name = step_name
        self.sample_id = sample_id
        self.folder = folder
        self.out_dir = out_dir

    def run(self):
        try:
            self.signals.log.emit(
                log_format(
                    f"[{self.step_name}] Processing sample={self.sample_id}, folder={self.folder}"
                )
            )

            # Simulate work with frequent cancellation checks
            import time

            for progress in [25, 50, 75, 100]:
                self.check_abort()  # Check for cancellation before each step
                self.signals.progress.emit(progress)

                if progress == 25:
                    self.signals.log.emit(log_format(f"[{self.step_name}] Initializing..."))
                elif progress == 50:
                    self.signals.log.emit(log_format(f"[{self.step_name}] Processing..."))
                elif progress == 75:
                    self.signals.log.emit(log_format(f"[{self.step_name}] Finalizing..."))

                # Shorter sleep with more frequent checks for immediate cancellation
                for _ in range(10):  # 10 x 0.1s = 1s total, but with 10 cancellation checks
                    self.check_abort()
                    time.sleep(0.1)

            self.signals.done.emit({"out_dir": self.out_dir, "step": self.step_name})

        except RuntimeError as e:
            if "canceled" in str(e).lower():
                self.signals.log.emit(log_format(f"[{self.step_name}] Canceled by user"))
            else:
                self.signals.error.emit(
                    log_format(f"[{self.step_name}] Error: {str(e)}", level="Error")
                )
        except Exception as e:
            self.signals.error.emit(
                log_format(f"[{self.step_name}] Error: {str(e)}", level="Error")
            )
