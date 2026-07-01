from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cgt_cell_analysis_demo.model.job import JobStatus, TestJob


class ProgressMonitorPanel(QWidget):
    """Panel that displays progress of multiple tests running simultaneously"""

    switch_to_pipeline = Signal()  # Signal to switch back to pipeline panel
    log = Signal(str)

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.running_tests = {}  # job_id -> test_info
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_display)
        self.update_timer.start(1000)  # Update every second

    def setup_ui(self):
        """Setup the progress monitor UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header section
        header_layout = QHBoxLayout()

        # Title
        title_label = QLabel("Test Progress Monitor")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2c3e50; margin: 5px;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # Switch to pipeline button
        self.switch_btn = QPushButton("Switch to Pipeline")
        self.switch_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
        self.switch_btn.clicked.connect(self.switch_to_pipeline.emit)
        header_layout.addWidget(self.switch_btn)

        layout.addLayout(header_layout)

        # Summary section
        self.summary_frame = QFrame()
        self.summary_frame.setStyleSheet("""
            QFrame {
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        summary_layout = QHBoxLayout(self.summary_frame)

        self.total_label = QLabel("Total Tests: 0")
        self.running_label = QLabel("Running: 0")
        self.completed_label = QLabel("Completed: 0")
        self.failed_label = QLabel("Failed: 0")

        for label in [
            self.total_label,
            self.running_label,
            self.completed_label,
            self.failed_label,
        ]:
            label.setStyleSheet("font-weight: bold; color: #2c3e50; margin: 5px;")
            summary_layout.addWidget(label)

        summary_layout.addStretch()
        layout.addWidget(self.summary_frame)

        # Scrollable area for individual test progress
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #bdc3c7;
                border-radius: 6px;
                background-color: white;
            }
        """)

        # Container for test progress widgets
        self.tests_container = QWidget()
        self.tests_layout = QVBoxLayout(self.tests_container)
        self.tests_layout.setContentsMargins(10, 10, 10, 10)
        self.tests_layout.setSpacing(8)

        scroll_area.setWidget(self.tests_container)
        layout.addWidget(scroll_area)

        # No tests message
        self.no_tests_label = QLabel("No tests currently running")
        self.no_tests_label.setAlignment(Qt.AlignCenter)
        self.no_tests_label.setStyleSheet("""
            color: #7f8c8d;
            font-size: 14px;
            font-style: italic;
            padding: 20px;
        """)
        self.tests_layout.addWidget(self.no_tests_label)
        self.tests_layout.addStretch()

    def add_test(self, job: TestJob):
        """Add a new test to the progress monitor"""
        job_id = job.job_id
        if job_id not in self.running_tests:
            test_widget = self.create_test_widget(job)
            self.running_tests[job_id] = {"job": job, "widget": test_widget}

            # Remove no tests message if it exists
            if (
                self.tests_layout.itemAt(0)
                and self.tests_layout.itemAt(0).widget() == self.no_tests_label
            ):
                self.tests_layout.removeWidget(self.no_tests_label)
                self.no_tests_label.hide()

            # Insert at the beginning
            self.tests_layout.insertWidget(0, test_widget)
            self.update_summary()

    def create_test_widget(self, job: TestJob):
        """Create a widget for displaying individual test progress"""
        group_box = QGroupBox(f"Test: {job.sample_id}")
        group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                margin: 5px;
                padding-top: 10px;
                background-color: #f8f9fa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #2c3e50;
            }
        """)

        layout = QVBoxLayout(group_box)
        layout.setContentsMargins(15, 20, 15, 15)
        layout.setSpacing(8)

        # Test info row
        info_layout = QHBoxLayout()

        # Job ID
        job_id_label = QLabel(f"Job ID: {job.job_id}")
        job_id_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        info_layout.addWidget(job_id_label)

        info_layout.addStretch()

        # Status
        status_label = QLabel(job.status.value.title())
        status_label.setStyleSheet("""
            color: #27ae60;
            font-weight: bold;
            font-size: 12px;
            padding: 4px 8px;
            background-color: #d5f4e6;
            border-radius: 4px;
        """)
        info_layout.addWidget(status_label)

        layout.addLayout(info_layout)

        # Data availability
        data_layout = QHBoxLayout()
        optical_label = QLabel("Optical: ✓" if job.optical_dir else "Optical: ✗")
        pcr_label = QLabel("PCR: ✓" if job.pcr_dir else "PCR: ✗")

        for label in [optical_label, pcr_label]:
            label.setStyleSheet("color: #2c3e50; font-size: 11px; margin-right: 15px;")
            data_layout.addWidget(label)

        data_layout.addStretch()
        layout.addLayout(data_layout)

        # Progress section
        progress_layout = QVBoxLayout()

        # Current step
        step_label = QLabel(f"Current Step: {job.current_step}")
        step_label.setStyleSheet("color: #34495e; font-weight: bold; font-size: 12px;")
        progress_layout.addWidget(step_label)

        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(job.percent)
        progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #bdc3c7;
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(progress_bar)

        # Progress percentage
        percent_label = QLabel(f"{job.percent}%")
        percent_label.setAlignment(Qt.AlignCenter)
        percent_label.setStyleSheet("color: #2c3e50; font-weight: bold; font-size: 11px;")
        progress_layout.addWidget(percent_label)

        layout.addLayout(progress_layout)

        # Store references for updates
        group_box.job_id = job.job_id
        group_box.status_label = status_label
        group_box.step_label = step_label
        group_box.progress_bar = progress_bar
        group_box.percent_label = percent_label

        return group_box

    def update_test(self, job: TestJob):
        """Update an existing test's progress"""
        job_id = job.job_id
        if job_id in self.running_tests:
            test_info = self.running_tests[job_id]
            test_info["job"] = job
            widget = test_info["widget"]

            # Update status
            status_text = job.status.value.title()
            status_color = self.get_status_color(job.status)
            widget.status_label.setText(status_text)
            widget.status_label.setStyleSheet(f"""
                color: {status_color};
                font-weight: bold;
                font-size: 12px;
                padding: 4px 8px;
                background-color: {self.get_status_bg_color(job.status)};
                border-radius: 4px;
            """)

            # Update step
            widget.step_label.setText(f"Current Step: {job.current_step}")

            # Update progress
            widget.progress_bar.setValue(job.percent)
            widget.percent_label.setText(f"{job.percent}%")

            # Update progress bar color based on status
            if job.status == JobStatus.failed:
                widget.progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 2px solid #e74c3c;
                        border-radius: 5px;
                        text-align: center;
                        font-weight: bold;
                    }
                    QProgressBar::chunk {
                        background-color: #e74c3c;
                        border-radius: 3px;
                    }
                """)
            elif job.status == JobStatus.done:
                widget.progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 2px solid #27ae60;
                        border-radius: 5px;
                        text-align: center;
                        font-weight: bold;
                    }
                    QProgressBar::chunk {
                        background-color: #27ae60;
                        border-radius: 3px;
                    }
                """)
            else:
                widget.progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 2px solid #bdc3c7;
                        border-radius: 5px;
                        text-align: center;
                        font-weight: bold;
                    }
                    QProgressBar::chunk {
                        background-color: #3498db;
                        border-radius: 3px;
                    }
                """)

            self.update_summary()

    def remove_test(self, job_id: str):
        """Remove a completed or failed test from the monitor"""
        if job_id in self.running_tests:
            test_info = self.running_tests[job_id]
            widget = test_info["widget"]
            self.tests_layout.removeWidget(widget)
            widget.deleteLater()
            del self.running_tests[job_id]

            # Show no tests message if no tests remain
            if not self.running_tests:
                self.tests_layout.addWidget(self.no_tests_label)
                self.no_tests_label.show()

            self.update_summary()

    def get_status_color(self, status: JobStatus):
        """Get color for status text"""
        colors = {
            JobStatus.pending: "#f39c12",
            JobStatus.running: "#3498db",
            JobStatus.done: "#27ae60",
            JobStatus.failed: "#e74c3c",
        }
        return colors.get(status, "#7f8c8d")

    def get_status_bg_color(self, status: JobStatus):
        """Get background color for status"""
        colors = {
            JobStatus.pending: "#fef5e7",
            JobStatus.running: "#e3f2fd",
            JobStatus.done: "#d5f4e6",
            JobStatus.failed: "#fdeaea",
        }
        return colors.get(status, "#f8f9fa")

    def update_summary(self):
        """Update the summary statistics"""
        total = len(self.running_tests)
        running = sum(
            1 for info in self.running_tests.values() if info["job"].status == JobStatus.running
        )
        completed = sum(
            1 for info in self.running_tests.values() if info["job"].status == JobStatus.done
        )
        failed = sum(
            1 for info in self.running_tests.values() if info["job"].status == JobStatus.failed
        )

        self.total_label.setText(f"Total Tests: {total}")
        self.running_label.setText(f"Running: {running}")
        self.completed_label.setText(f"Completed: {completed}")
        self.failed_label.setText(f"Failed: {failed}")

    def update_display(self):
        """Periodically update the display"""
        # This method can be used for any periodic updates
        pass

    def clear_all_tests(self):
        """Clear all tests from the monitor"""
        for job_id in list(self.running_tests.keys()):
            self.remove_test(job_id)
