from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from cgt_cell_analysis_demo import __resource_path__
from cgt_cell_analysis_demo.util.logger import log_format


class PipelinePanel(QWidget):
    log = Signal(str)
    run_step = Signal(int, str)  # request MainWindow to run a step (step, folder)
    stop_step = Signal(int)  # request MainWindow to stop a step (step)
    save_result = Signal()  # request MainWindow to save results
    switch_to_progress_monitor = Signal()  # Switch to progress monitor
    sample_completed = Signal(str)  # Emit when a sample's processing is completed
    sample_failed = Signal(str, str)  # Emit when a sample's processing fails (sample_id, error)
    request_samples = Signal()  # Request samples from file tree panel
    select_first_sample = Signal()  # Request selection of first sample in file tree
    current_sample_changed = Signal(str)  # Emit when current sample changes during batch processing

    def __init__(self, mode: str = "processing"):
        super().__init__()
        self._mode = mode  # 'processing' or 'training'
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # No margins
        layout.setSpacing(0)  # Compact spacing

        # Allow the panel to be resizable
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Top toolbar
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar { background-color: #14213D; border: none; }
            QToolButton { color: #ffffff; padding: 4px 6px; }
            QToolButton:hover { background-color: #1e40af; }
            QToolButton:pressed { background-color: #1e3a8a; }
        """)
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setFixedHeight(30)
        # Run current
        act_run = QAction(QIcon(str((__resource_path__ / "icn_run.svg").resolve())), "Run", self)
        act_run.setToolTip("Run current pipeline")
        act_run.triggered.connect(self._run_current)
        toolbar.addAction(act_run)
        # Run all
        act_run_all = QAction(
            QIcon(str((__resource_path__ / "icn_run_all.svg").resolve())), "Run All", self
        )
        act_run_all.setToolTip("Run all steps (auto chain)")
        act_run_all.triggered.connect(self._run_all)
        toolbar.addAction(act_run_all)
        toolbar.addSeparator()
        # Stop
        act_stop = QAction(QIcon(str((__resource_path__ / "icn_stop.svg").resolve())), "Stop", self)
        act_stop.setToolTip("Stop running steps")
        act_stop.triggered.connect(self._stop_all)
        toolbar.addAction(act_stop)
        toolbar.addSeparator()
        # Save Result
        act_save = QAction(
            QIcon(str((__resource_path__ / "icn_results_menu.svg").resolve())), "Save Result", self
        )
        act_save.setToolTip("Save final CSV results")
        act_save.triggered.connect(self._save_result)
        toolbar.addAction(act_save)
        layout.addWidget(toolbar)

        # Status header (current sample, step, state, progress)
        header_w = QWidget()
        header_h = QHBoxLayout(header_w)
        header_h.setContentsMargins(5, 0, 5, 0)
        header_h.setSpacing(8)
        header_w.setFixedHeight(28)
        header_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._lbl_sample = QLabel("Sample: -")
        self._lbl_sample.setStyleSheet("color: #333; font-weight: bold;")

        self._lbl_step = QLabel("Step: -")
        self._lbl_step.setStyleSheet("color: #555;")

        self._lbl_state = QLabel("Idle")
        self._lbl_state.setFixedHeight(20)
        self._lbl_state.setStyleSheet("""
            QLabel { padding: 2px 6px; border-radius: 8px; background: #9e9e9e; color: white; }
        """)

        self._header_prog = QProgressBar()
        self._header_prog.setFixedWidth(160)
        self._header_prog.setMinimumHeight(12)
        self._header_prog.setValue(0)
        self._header_prog.setTextVisible(False)

        header_h.addWidget(self._lbl_sample)
        header_h.addSpacing(6)
        header_h.addWidget(self._lbl_step)
        header_h.addSpacing(6)
        header_h.addWidget(self._lbl_state)
        header_h.addSpacing(10)
        header_h.addWidget(self._header_prog)
        header_h.addStretch()
        layout.addWidget(header_w)

        # Scrollable content area for cards so toolbar/header stay fixed
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; }")
        self._content = QWidget()
        self._cards_vbox = QVBoxLayout(self._content)
        self._cards_vbox.setContentsMargins(5, 5, 5, 5)
        self._cards_vbox.setSpacing(6)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

        # Per-step widgets
        self._progress_bars = {}
        self._folder_edits = {}
        self._run_buttons = {}
        self._running_steps = set()  # Track which steps are currently running

        # Additional folder edits for specific steps (e.g., Step 4 Merge step)
        self._additional_folder_edits = {}  # For additional folder inputs per step
        step_defs = [
            (1, "Step1: Optical Index & Extract"),
            (2, "Step2: Cell Counting"),
            (3, "Step3: PCR Image Indexing"),
            (4, "Step4: Merge"),
        ]
        if self._mode == "training":
            step_defs = [(1, "Step1: Training cell count")]
        for step, title in step_defs:
            grp, prog, btn = self._make_step_card(step, title)
            self._progress_bars[step] = prog
            self._run_buttons[step] = btn
            self._cards_vbox.addWidget(grp)
        self._cards_vbox.addStretch(1)

        # File list for display
        self.available_files = []
        self.available_samples = []

    # --------- Header helpers ---------
    def set_current_sample(self, sample_id: str):
        self._lbl_sample.setText(f"Sample: {sample_id if sample_id else '-'}")

        # Emit signal for batch processing to update main window's current sample ID
        if hasattr(self, "_is_batch_processing") and self._is_batch_processing:
            self.current_sample_changed.emit(sample_id)

    def set_current_step(self, step: int):
        self._lbl_step.setText(f"Step: {step}")

    def _set_state(self, state: str):
        state = state.capitalize()
        self._lbl_state.setText(state)
        color = {
            "Idle": "#9e9e9e",
            "Running": "#1976d2",
            "Done": "#2e7d32",
            "Error": "#c62828",
        }.get(state, "#9e9e9e")
        self._lbl_state.setStyleSheet(
            f"QLabel {{ padding: 2px 6px; border-radius: 8px; background: {color}; color: white; }}"
        )

    def _first_step(self) -> int:
        """Return the first step id for this panel mode."""
        return 1

    def _all_steps(self) -> list:
        """Return ordered list of step ids present in this panel."""
        if self._mode == "training":
            return [1]
        return [1, 2, 3, 4]

    def _run_current(self):
        """Run the first step (entry point)."""
        self.reset_all_progress()
        step = self._first_step()
        # Defer to the existing button handler
        self._on_run_clicked(step)

    def _run_all(self):
        """Run all samples one by one through the complete pipeline, starting from the first (top) sample."""
        self.log.emit(
            log_format(
                "[Pipeline] Run All triggered - processing all samples from first (top) sample"
            )
        )
        self.reset_all_progress()
        # Check if we have samples to process
        if not self.available_samples:
            self.log.emit(
                log_format("[Pipeline] No samples available, requesting samples from file tree")
            )
            # Request samples from the file tree panel
            self.request_samples.emit()
            # After emitting the signal, check again
            if not self.available_samples:
                self.log.emit(log_format("[Pipeline] No samples available to process"))
                return

        # Request selection of first sample in file tree for better UI feedback
        self.log.emit(
            log_format("[Pipeline] Selecting first sample in file tree for visual feedback")
        )
        self.select_first_sample.emit()

        # Initialize sample queue - ensure we start from the first (top) sample
        # Get samples in the order they appear in the file tree (already sorted alphabetically)
        self._sample_queue = [
            sample for sample in self.available_samples if sample.get("is_valid", False)
        ]

        # Log the order of samples to be processed (already sorted from file tree)
        if self._sample_queue:
            self.log.emit(log_format("[Pipeline] Sample queue (already sorted alphabetically):"))
            for i, sample in enumerate(self._sample_queue):
                sample_id = sample.get("sample_id", "Unknown")
                self.log.emit(log_format(f"[Pipeline]   {i + 1}. {sample_id}"))

        # Ensure samples are processed in the order they appear in the file tree
        # This is important for starting from the first (top) sample
        if self._sample_queue:
            # Log the first sample to confirm we're starting from the top
            first_sample = self._sample_queue[0]
            first_sample_id = first_sample.get("sample_id", "Unknown")
            self.log.emit(
                log_format(f"[Pipeline] Starting from first (top) sample: {first_sample_id}")
            )

        self._current_sample_index = 0
        self._is_batch_processing = True

        if not self._sample_queue:
            self.log.emit(log_format("[Pipeline] No valid samples found to process"))
            return

        # Log the order of samples to be processed
        self.log.emit(
            log_format(f"[Pipeline] Starting batch processing of {len(self._sample_queue)} samples")
        )
        for i, sample in enumerate(self._sample_queue):
            sample_id = sample.get("sample_id", "Unknown")
            self.log.emit(log_format(f"[Pipeline] Sample {i + 1}: {sample_id}"))

        # Start processing the first sample
        self._process_next_sample()

    def _process_next_sample(self):
        """Process the next sample in the queue."""
        if not hasattr(self, "_is_batch_processing") or not self._is_batch_processing:
            return

        if self._current_sample_index >= len(self._sample_queue):
            # All samples processed
            self._is_batch_processing = False
            self.log.emit(
                log_format("[Pipeline] Batch processing completed - all samples processed")
            )
            self._set_state("Done")
            return

        # Get current sample
        current_sample = self._sample_queue[self._current_sample_index]
        sample_id = current_sample["sample_id"]

        self.log.emit(
            log_format(
                f"[Pipeline] Processing sample {self._current_sample_index + 1}/{len(self._sample_queue)}: {sample_id}"
            )
        )

        # Reset all progress bars to 0% for the new sample
        self.reset_all_progress()

        # Set up pipeline for this sample
        self._setup_sample_pipeline(current_sample)

        # Start processing with step 1
        self._run_current()

    def _setup_sample_pipeline(self, sample):
        """Set up pipeline inputs for a specific sample."""
        sample_id = sample["sample_id"]

        # Update current sample display
        self.set_current_sample(sample_id)

        # Set up optical folder for step 1
        if sample.get("optical_data"):
            optical_path = sample["optical_data"]["path"]
            self.set_input_folder(1, optical_path)
            self.log.emit(
                log_format(f"[Pipeline] Sample {sample_id} - Step 1 input set to: {optical_path}")
            )
        else:
            self.set_input_folder(1, "")
            self.log.emit(log_format(f"[Pipeline] Sample {sample_id} - No optical data available"))

        # Clear step 2 input (will be set by auto-chain)
        self.set_input_folder(2, "")

        # Set up PCR folder for step 3
        if sample.get("pcr_data"):
            pcr_path = sample["pcr_data"]["path"]
            self.set_input_folder(3, pcr_path)
            self.log.emit(
                log_format(f"[Pipeline] Sample {sample_id} - Step 3 input set to: {pcr_path}")
            )
        else:
            self.set_input_folder(3, "")
            self.log.emit(log_format(f"[Pipeline] Sample {sample_id} - No PCR data available"))

        # Clear step 4 additional folders (will be set by auto-chain)
        self.set_additional_folder(4, "cell_count", "")
        self.set_additional_folder(4, "labeled_rawdata", "")

    def _on_sample_completed(self, sample_id: str):
        """Handle when a sample's processing is completed."""
        if not hasattr(self, "_is_batch_processing") or not self._is_batch_processing:
            return

        self.log.emit(log_format(f"[Pipeline] Sample {sample_id} processing completed"))

        # Emit signal for external handling
        self.sample_completed.emit(sample_id)

        # Move to next sample
        self._current_sample_index += 1

        # Process next sample after a short delay
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1000, self._process_next_sample)  # 1 second delay between samples

    def _on_sample_failed(self, sample_id: str, error: str):
        """Handle when a sample's processing fails."""
        if not hasattr(self, "_is_batch_processing") or not self._is_batch_processing:
            return

        self.log.emit(log_format(f"[Pipeline] Sample {sample_id} processing failed: {error}"))

        # Emit signal for external handling
        self.sample_failed.emit(sample_id, error)

        # Move to next sample even if current one failed
        self._current_sample_index += 1

        # Process next sample after a short delay
        from PySide6.QtCore import QTimer

        QTimer.singleShot(2000, self._process_next_sample)  # 2 second delay after error

    def _stop_all(self):
        """Stop any running steps and batch processing."""
        # Stop batch processing if active
        if hasattr(self, "_is_batch_processing") and self._is_batch_processing:
            self._is_batch_processing = False
            self.log.emit(log_format("[Pipeline] Batch processing stopped"))

        if not self._running_steps:
            self.log.emit(log_format("[Pipeline] No running steps to stop"))
            return
        for step in list(self._running_steps):
            self.stop_step.emit(step)
            self.set_step_running(step, False)
        self.log.emit(log_format("[Pipeline] Stop requested for running steps"))

    def _save_result(self):
        """Handle save result button click"""
        self.log.emit(log_format("[Pipeline] Save result requested"))
        self.save_result.emit()

    def _get_additional_folders_for_step(self, step: int) -> dict:
        """Get additional folder definitions for a specific step"""
        additional_folders = {}

        if step == 4:
            additional_folders = {
                "cell_count": "Cell Count Data Folder",
                "labeled_rawdata": "Labeled RawData Folder",
            }

        return additional_folders

    def _make_step_card(self, step: int, title: str):
        grp = QGroupBox(title)
        grp.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #aaa;
                margin-top: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
            }
        """)
        # Constrain the card height to keep the layout compact
        grp.setMaximumHeight(170)
        grp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        v = QVBoxLayout(grp)
        v.setContentsMargins(8, 12, 8, 2)  # Compact margins
        v.setSpacing(2)  # Compact spacing

        # Compact form layout
        form1 = QFormLayout()
        form1.setSpacing(4)
        form1.setLabelAlignment(Qt.AlignLeft)

        ed_folder_root = QLineEdit()
        ed_folder_root.setStyleSheet("""
            QLineEdit {
                padding: 4px;
                border: 1px solid #ccc;
                border-radius: 3px;
                font-size: 11px;
            }
        """)
        self._folder_edits[step] = ed_folder_root

        btn_folder = QPushButton("Select Folder")
        btn_folder.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        btn_folder.clicked.connect(lambda: self._pick_dir(step))

        # Add input folder for all steps except Step 4
        if step != 4:
            form1.addRow("Input Folder", self._with_btn(ed_folder_root, btn_folder))

        # Add additional input folders for specific steps
        additional_folders = self._get_additional_folders_for_step(step)
        if additional_folders:
            self._additional_folder_edits[step] = {}
            for folder_type, folder_label in additional_folders.items():
                ed_folder = QLineEdit()
                ed_folder.setStyleSheet("""
                    QLineEdit {
                        padding: 4px;
                        border: 1px solid #ccc;
                        border-radius: 3px;
                        font-size: 11px;
                    }
                """)
                self._additional_folder_edits[step][folder_type] = ed_folder

                btn_folder = QPushButton("Select Folder")
                btn_folder.setStyleSheet("""
                    QPushButton {
                        background-color: #6c757d;
                        color: white;
                        border: none;
                        border-radius: 3px;
                        padding: 4px 8px;
                        font-size: 10px;
                    }
                    QPushButton:hover {
                        background-color: #5a6268;
                    }
                """)
                btn_folder.clicked.connect(
                    lambda checked, s=step, ft=folder_type: self._pick_dir(s, ft)
                )

                form1.addRow(folder_label, self._with_btn(ed_folder, btn_folder))

        v.addLayout(form1)

        # Compact run button and progress
        form2 = QFormLayout()
        form2.setSpacing(4)

        btn_run = QPushButton("Run")
        btn_run.setMinimumHeight(18)
        btn_run.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        btn_run.clicked.connect(lambda: self._on_run_clicked(step))

        prog = QProgressBar()
        prog.setValue(0)
        prog.setMinimumHeight(18)
        prog.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 3px;
                text-align: center;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #007bff;
                border-radius: 2px;
            }
        """)

        form2.addRow(btn_run, prog)
        v.addLayout(form2)

        return grp, prog, btn_run

    def update_progress(self, step: int, val: int):
        if step in self._progress_bars:
            self._progress_bars[step].setValue(val)
        # Also reflect in header when it's the active step
        self._header_prog.setValue(val)

    def reset_all_progress(self):
        """Reset all progress bars to 0%"""
        for progress_bar in self._progress_bars.values():
            progress_bar.setValue(0)
        self._header_prog.setValue(0)
        self.log.emit(log_format("[Pipeline] Reset all progress bars to 0%"))

    def _with_btn(self, line: QLineEdit, btn: QPushButton):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)  # Compact spacing between line edit and button
        h.addWidget(line)
        h.addWidget(btn)
        return w

    def _on_run_clicked(self, step: int):
        """Handle Run/Stop button clicks"""
        if step in self._running_steps:
            # Currently running, so stop it
            self.stop_step.emit(step)
            # Immediately change button back to Run for restart capability
            self.set_step_running(step, False)
        else:
            # Not running, so start it
            # Check input folder validation (skip for Step 4)
            if step != 4 and (self._folder_edits[step].text() == ""):
                self.log.emit(log_format(f"[Pipeline] Folder not selected for Step{step}"))
                return

            # Additional validation for steps with additional folders
            additional_folders = self._get_additional_folders_for_step(step)
            if additional_folders:
                missing_folders = []
                folder_info = []

                for folder_type, folder_label in additional_folders.items():
                    folder_path = self.get_additional_folder(step, folder_type)
                    if not folder_path:
                        missing_folders.append(folder_label)
                    else:
                        folder_info.append(f"{folder_label}: {folder_path}")

                if missing_folders:
                    for missing in missing_folders:
                        self.log.emit(
                            log_format(f"[Pipeline] {missing} not selected for Step {step}")
                        )
                    return

                if folder_info:
                    input_info = f"Input: {self._folder_edits[step].text()}" if step != 4 else ""
                    separator = ", " if input_info and folder_info else ""
                    self.log.emit(
                        log_format(
                            f"[Pipeline] Step {step} folders - {input_info}{separator}{', '.join(folder_info)}"
                        )
                    )

            # For Step 4, we don't have an input folder, so we'll pass empty string
            # The actual folder paths will be retrieved in the main window
            folder = self._folder_edits[step].text() if step != 4 else ""
            # Reset progress bar to 0% at the moment Run is clicked
            if step in self._progress_bars:
                self._progress_bars[step].setValue(0)
            self.run_step.emit(step, folder)
            # Update header state on start
            self.set_current_step(step)
            self._set_state("Running")

    def set_step_running(self, step: int, running: bool):
        """Update UI to reflect step running state"""
        if step in self._run_buttons:
            if running:
                self._running_steps.add(step)
                self._run_buttons[step].setText("Stop")
                self._run_buttons[step].setStyleSheet("""
                    QPushButton {
                        background-color: #ff6b6b;  /* Only background changed */
                        color: white;
                        border: none;
                        border-radius: 3px;
                        padding: 6px 12px;
                        font-size: 10px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #ff8f8f;  /* Only background changed */
                    }
                """)
                self._set_state("Running")

            else:
                self._running_steps.discard(step)
                self._run_buttons[step].setText("Run")
                self._run_buttons[step].setStyleSheet("""
                    QPushButton {
                        background-color: #28a745;
                        color: white;
                        border: none;
                        border-radius: 3px;
                        padding: 6px 12px;
                        font-size: 10px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background-color: #218838;
                    }
                """)
                # Return to idle only if no steps are running
                if not self._running_steps:
                    self._set_state("Idle")

    def set_input_folder(self, step: int, folder_path: str):
        """Set the input folder path for a specific step"""
        if step in self._folder_edits:
            self._folder_edits[step].setText(folder_path)
            if folder_path:
                self.log.emit(
                    log_format(f"[Pipeline] Step {step} input folder set to: {folder_path}")
                )
            else:
                self.log.emit(log_format(f"[Pipeline] Step {step} input folder cleared"))

    def set_additional_folder(self, step: int, folder_type: str, folder_path: str):
        """Set additional folder path for a specific step"""
        if (
            step in self._additional_folder_edits
            and folder_type in self._additional_folder_edits[step]
        ):
            self._additional_folder_edits[step][folder_type].setText(folder_path)
            additional_folders = self._get_additional_folders_for_step(step)
            folder_label = additional_folders.get(
                folder_type, folder_type.replace("_", " ").title()
            )
            if folder_path:
                self.log.emit(
                    log_format(f"[Pipeline] Step {step} {folder_label} set to: {folder_path}")
                )
            else:
                self.log.emit(log_format(f"[Pipeline] Step {step} {folder_label} cleared"))

    def get_additional_folder(self, step: int, folder_type: str) -> str:
        """Get additional folder path for a specific step"""
        if (
            step in self._additional_folder_edits
            and folder_type in self._additional_folder_edits[step]
        ):
            return self._additional_folder_edits[step][folder_type].text()
        return ""

    def get_all_folders(self, step: int) -> dict:
        """Get all folder paths for a specific step"""
        folders = {}

        # Add input folder for all steps except Step 4
        if step != 4:
            folders["input"] = self._folder_edits.get(step, QLineEdit()).text()

        # Add additional folders if they exist for this step
        if step in self._additional_folder_edits:
            additional_folders = self._get_additional_folders_for_step(step)
            for folder_type in additional_folders.keys():
                folders[folder_type] = self.get_additional_folder(step, folder_type)

        return folders

    def _pick_dir(self, step: int, folder_type: str = None):
        if (
            folder_type
            and step in self._additional_folder_edits
            and folder_type in self._additional_folder_edits[step]
        ):
            # Handle additional folders for specific steps
            additional_folders = self._get_additional_folders_for_step(step)
            folder_label = additional_folders.get(
                folder_type, folder_type.replace("_", " ").title()
            )
            # Allow file selection for label CSV in training mode
            if folder_type == "label_csv":
                path, _ = QFileDialog.getOpenFileName(
                    self, f"Select {folder_label}", "", "CSV Files (*.csv);;All Files (*.*)"
                )
            else:
                path = QFileDialog.getExistingDirectory(self, f"Select {folder_label}", "")
            if path:
                self._additional_folder_edits[step][folder_type].setText(path)
                self.log.emit(log_format(f"[Pipeline] {folder_label} Selected: {path}"))
        else:
            # Handle regular input folder
            path = QFileDialog.getExistingDirectory(self, "Select Folder", "")
            if path:
                if step in self._folder_edits:
                    self._folder_edits[step].setText(path)
                self.log.emit(log_format(f"[Pipeline] Folder Selected: {path}"))

    def set_available_files(self, files: list):
        """Set the list of available files found by file tree panel"""
        self.available_files = files
        self.log.emit(log_format(f"[Pipeline] Updated with {len(files)} files"))

        # Auto-populate folder paths if files are available
        if files:
            # Group files by parent directory
            folders = {}
            for file_info in files:
                parent_dir = file_info.get("parent_folder", "")
                if parent_dir not in folders:
                    folders[parent_dir] = []
                folders[parent_dir].append(file_info)

    def set_available_samples(self, samples: list):
        """Set the list of available samples found by file tree panel"""
        self.available_samples = samples
        self.log.emit(log_format(f"[Pipeline] Updated with {len(samples)} samples"))

        # Auto-populate folder paths with sample paths
        if samples:
            # Log sample structure details
            for sample in samples:
                sample_id = sample["sample_id"]
                self.log.emit(log_format(f"[Pipeline] Sample '{sample_id}':"))

                if sample["optical_data"]:
                    optical_info = sample["optical_data"]
                    self.log.emit(
                        log_format(
                            f"  - Optical: {len(optical_info['image_folders'])} folders, {optical_info['total_images']} images"
                        )
                    )

                if sample["pcr_data"]:
                    pcr_info = sample["pcr_data"]
                    self.log.emit(
                        log_format(
                            f"  - PCR: {len(pcr_info['odpi_files'])} .odpi files, {len(pcr_info['data_folders'])} data folders"
                        )
                    )
