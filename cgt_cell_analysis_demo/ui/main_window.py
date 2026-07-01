import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from cgt_cell_analysis_demo import (
    __config_path__,
    __models_path__,
    __project_path__,
    __reference_data_path__,
    __resource_path__,
    __version__,
)
from cgt_cell_analysis_demo.core.pipeline_controller import PipelineController
from cgt_cell_analysis_demo.core.workers.well_index_common import RefPaths
from cgt_cell_analysis_demo.model.job import JobStatus, TestJob
from cgt_cell_analysis_demo.ui.panels.control_panel import ControlPanel
from cgt_cell_analysis_demo.ui.panels.file_tree_panel import FileTreePanel
from cgt_cell_analysis_demo.ui.panels.log_panel import LogPanel
from cgt_cell_analysis_demo.ui.panels.pipeline_panel import PipelinePanel
from cgt_cell_analysis_demo.ui.panels.preview_panel import PreviewPanel as NewPreviewPanel
from cgt_cell_analysis_demo.ui.panels.progress_monitor_panel import ProgressMonitorPanel
from cgt_cell_analysis_demo.ui.panels.queue_panel import QueuePanel
from cgt_cell_analysis_demo.ui.panels.settings_dialog import SettingsDialog
from cgt_cell_analysis_demo.ui.widgets.loading_screen import LoadingScreen
from cgt_cell_analysis_demo.util.logger import log_format


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CGT Cell Analysis Demo")
        self.resize(1400, 800)

        # Set application icon
        icon_path = __resource_path__ / "icn_app_logo.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
            # Store icon path for potential Windows-specific handling
            self._icon_path = icon_path

        # Set main window styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QToolBar {
                background-color: #e8e8e8;
                border: none;
                border-bottom: 1px solid #d0d0d0;
                spacing: 3px;
                padding: 4px;
            }
            QToolBar::separator {
                background-color: #d0d0d0;
                width: 1px;
                margin: 4px 2px;
            }
        """)

        print("Initializing Main Window...")

        # Create main layout
        self.setup_ui()

        # Create loading screen
        self.loading_screen = LoadingScreen(self)

        # Initialize panels for Processing page
        self.file_tree_panel = FileTreePanel(panel_type="Processing")
        self.preview_panel_1 = NewPreviewPanel("Optical Images")
        self.preview_panel_2 = NewPreviewPanel("PCR 1st Cycle Image")
        self.control_panel = ControlPanel()
        self.log_panel = LogPanel()

        # Legacy panels for compatibility
        self.pipeline_panel = PipelinePanel()
        self.progress_monitor_panel = ProgressMonitorPanel()
        self.queue_panel = QueuePanel()

        # Initialize panels for Training page (separate instances)
        self.training_file_tree_panel = FileTreePanel(panel_type="Training")
        self.training_control_panel = ControlPanel()
        self.training_preview_panel_1 = NewPreviewPanel("Training Images")
        self.training_pipeline_panel = PipelinePanel(mode="training")
        self.training_progress_monitor_panel = ProgressMonitorPanel()

        # Configuration
        self.configuration = {}
        self.config_file_path = __config_path__

        # Current selected sample
        self.current_sample_id = "SampleA"  # Default sample ID

        # Current page tracking
        self.current_page = "processing"  # Default to processing page

        # Setup sidebar and main layout
        self.setup_sidebar()
        self.setup_main_layout()

        # Connect signals
        self.setup_connections()

        # Tool bar
        self._build_toolbar()
        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Create a custom widget for status text
        self.status_widget = QWidget()
        self.status_layout = QHBoxLayout(self.status_widget)
        self.status_layout.setContentsMargins(15, 0, 15, 5)
        self.status_layout.setSpacing(5)
        # Make status widget expand to fill the status bar
        self.status_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # Developer mode center label (hidden by default)
        self.dev_label = QLabel("")
        self.dev_label.setStyleSheet("color: #aa0000; font-weight: normal;")
        self.dev_label.setVisible(False)

        # Right-aligned app version label
        self.version_label = QLabel(f"version {__version__}")
        self.version_label.setStyleSheet("color: #666666;")

        # Add widgets to layout
        self.status_layout.addWidget(self.dev_label)
        self.status_layout.addStretch()
        self.status_layout.addWidget(self.version_label)

        # Add the custom widget to status bar with stretch so it occupies full width
        self.status.addPermanentWidget(self.status_widget, 1)

        self.pipeline_panel.run_step.connect(self._on_run_step)
        self.pipeline_panel.stop_step.connect(self._on_stop_step)
        self.pipeline_panel.log.connect(self._append_log)
        self.pipeline_panel.switch_to_progress_monitor.connect(self._switch_to_progress_monitor)

        # Connect progress monitor signals
        self.progress_monitor_panel.switch_to_pipeline.connect(self._switch_to_pipeline)
        self.progress_monitor_panel.log.connect(self._append_log)

        # Connect Pipeline Controller
        self.controller = PipelineController()
        self.controller.log.connect(self._append_log)
        self.controller.progress.connect(self._on_progress)
        self.controller.done.connect(self._on_step_done)
        self.controller.error.connect(self._on_step_error)
        self.controller.auto_trigger_step2.connect(self._on_auto_trigger_step2)
        self.controller.auto_trigger_step3.connect(self._on_auto_trigger_step3)
        self.controller.auto_trigger_step4.connect(self._on_auto_trigger_step4)

        # Load saved configuration and initialize defaults after UI is set up
        self._load_configuration()
        self._initialize_default_configuration()

        # Developer mode (hidden by default; toggle with shortcut)
        self.developer_mode = bool(self.configuration.get("developer_mode", False))
        self._apply_developer_mode(self.developer_mode)

        # Hidden shortcut to toggle developer mode
        self._dev_toggle_shortcut = QShortcut(QKeySequence("Ctrl+Alt+D"), self)
        self._dev_toggle_shortcut.activated.connect(self._toggle_developer_mode)

    def setup_ui(self):
        """Setup the main UI structure"""
        pass

    def setup_sidebar(self):
        """Setup the sidebar menu like Qt Creator"""
        # Create sidebar
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(100)  # Slightly reduced width
        self.sidebar.setSizePolicy(
            QSizePolicy.Fixed, QSizePolicy.Expanding
        )  # Fixed width, expanding height
        self.sidebar.setFocusPolicy(Qt.NoFocus)
        self.sidebar.setStyleSheet("""
            QListWidget {
                background-color: #14213D;
                border: none;
                border-right: 0px;
                font-size: 12px;
                padding: 0px 0px;
                outline: none;
            }
            QListWidget::item {
                padding: 15px 0px;
                border: none;
                color: #ffffff;
                margin: 0px;
                outline: none;
                width: 100%;
            }
            QListWidget::item:selected {
                background-color: #1e3a8a;
                border: none;
                border-left: 3px solid #0078d4;
                outline: none;
            }
            QListWidget::item:hover {
                background-color: #1e40af;
            }
        """)
        # Display icons above text and stack items vertically
        self.sidebar.setViewMode(QListView.IconMode)
        self.sidebar.setFlow(QListView.TopToBottom)
        self.sidebar.setMovement(QListView.Static)
        self.sidebar.setIconSize(QSize(30, 30))
        # Ensure text is not elided and allow wrapping for multi-line labels
        self.sidebar.setTextElideMode(Qt.ElideNone)
        self.sidebar.setWordWrap(True)
        # Fix uniform height for each sidebar item (icon + two text lines)
        fixed_item_height = 92
        self.sidebar.setGridSize(QSize(100, fixed_item_height))
        self.sidebar.setSpacing(0)

        # Add menu items
        self.processing_item = QListWidgetItem(
            QIcon(str((__resource_path__ / "icn_processing.svg").resolve())), "Processing"
        )
        self.results_item = QListWidgetItem(
            QIcon(str((__resource_path__ / "icn_results_menu.svg").resolve())),
            "Results\n(Coming Soon)",
        )
        self.training_item = QListWidgetItem(
            QIcon(str((__resource_path__ / "icn_ai_training_menu.svg").resolve())), "AI Training"
        )
        # Ensure each item uses the same fixed height
        for _it in (self.processing_item, self.results_item, self.training_item):
            _it.setSizeHint(QSize(100, fixed_item_height))

        self.sidebar.addItem(self.processing_item)
        self.sidebar.addItem(self.results_item)
        self.sidebar.addItem(self.training_item)
        # Center-align text for all items
        self.processing_item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.results_item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.training_item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        # Hide training by default until developer mode is enabled
        self.training_item.setHidden(True)

        # Set default selection
        self.sidebar.setCurrentRow(0)

        # Create stacked widget for content
        self.content_stack = QStackedWidget()

        # Create pages
        self.processing_page = QWidget()
        self.results_page = QWidget()
        self.training_page = QWidget()

        # Add pages to stack
        self.content_stack.addWidget(self.processing_page)
        self.content_stack.addWidget(self.results_page)
        self.content_stack.addWidget(self.training_page)

        # Connect sidebar selection to stack
        self.sidebar.currentRowChanged.connect(self.content_stack.setCurrentIndex)
        # Also track current page changes for toolbar functionality
        self.sidebar.currentRowChanged.connect(self._on_page_changed)

    def setup_main_layout(self):
        """Setup the main layout with sidebar and content"""
        # Setup Processing Page
        self.setup_processing_page()

        # Setup Results Page
        self.setup_results_page()

        # Setup Training Page
        self.setup_training_page()

        # Create main horizontal splitter (sidebar + content + log)
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setHandleWidth(0)  # No gap between sidebar and content
        main_splitter.setContentsMargins(0, 0, 0, 0)
        main_splitter.setStyleSheet("QSplitter::handle { width: 0px; }")
        main_splitter.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )  # Fill available space

        # Add sidebar
        main_splitter.addWidget(self.sidebar)

        # Create content area with vertical splitter
        content_splitter = QSplitter(Qt.Vertical)
        content_splitter.setChildrenCollapsible(False)
        content_splitter.setHandleWidth(1)
        content_splitter.setContentsMargins(0, 0, 0, 0)
        content_splitter.setStyleSheet(
            "QSplitter::handle:vertical { background-color: #404040; height: 1px; }"
        )
        content_splitter.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )  # Fill available space

        # Add styling to log panel wrapper
        log_wrapper = QWidget()
        self._log_wrapper = log_wrapper  # keep reference for hide/show
        log_layout = QVBoxLayout(log_wrapper)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(self.log_panel)

        content_splitter.addWidget(self.content_stack)
        content_splitter.addWidget(log_wrapper)
        content_splitter.setStretchFactor(0, 4)  # Content
        content_splitter.setStretchFactor(1, 1)  # Log panel
        self._content_splitter = content_splitter

        # Ensure content area expands to fill remaining space
        content_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Add content area to main splitter
        main_splitter.addWidget(content_splitter)
        main_splitter.setStretchFactor(0, 0)  # Sidebar fixed width (no stretch)
        main_splitter.setStretchFactor(1, 1)  # Content area expands to fill remaining space

        # Set initial sizes to ensure proper alignment
        main_splitter.setSizes([100, 1200])  # Sidebar: 100px, Content: remaining space

        self.setCentralWidget(main_splitter)

    # Allow double-click on splitter handle to toggle log pane
    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    def setup_processing_page(self):
        """Setup the Processing page layout"""
        # Create main horizontal splitter for Processing page
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(True)
        main_splitter.setHandleWidth(2)  # No gap between panels
        main_splitter.setContentsMargins(0, 0, 0, 0)  # Remove all margins
        main_splitter.setStyleSheet(
            "QSplitter::handle:horizontal { background-color: #2b2b2b; width: 1px; }"
        )

        # Left panel (File Management + Control at bottom)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        # Splitter to allow resizing between tree and control panel
        left_vertical_splitter = QSplitter(Qt.Vertical)
        left_vertical_splitter.setChildrenCollapsible(False)
        left_vertical_splitter.setHandleWidth(2)
        left_vertical_splitter.setContentsMargins(0, 0, 0, 0)
        left_vertical_splitter.setStyleSheet(
            "QSplitter::handle:vertical { background-color: #bdbdbd; height: 1px; }"
        )
        left_vertical_splitter.addWidget(self.file_tree_panel)
        # Wrap control panel into a container for margins if needed
        control_wrapper_left = QWidget()
        control_layout_left = QVBoxLayout(control_wrapper_left)
        control_layout_left.setContentsMargins(0, 0, 0, 0)
        control_layout_left.setSpacing(0)
        control_layout_left.addWidget(self.control_panel)
        # Fix control panel height so it does not expand
        fixed_ctrl_h = 40
        control_wrapper_left.setMinimumHeight(fixed_ctrl_h)
        control_wrapper_left.setMaximumHeight(fixed_ctrl_h)
        control_wrapper_left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_vertical_splitter.addWidget(control_wrapper_left)
        left_vertical_splitter.setStretchFactor(0, 4)
        left_vertical_splitter.setStretchFactor(1, 0)
        left_vertical_splitter.setSizes([600, fixed_ctrl_h])
        left_layout.addWidget(left_vertical_splitter)
        # Minimum width for the left column
        left_panel.setMinimumWidth(150)

        # Right panel (Pipeline + Previews) - Now using vertical splitter
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Create vertical splitter for pipeline and preview panels
        right_vertical_splitter = QSplitter(Qt.Vertical)
        right_vertical_splitter.setChildrenCollapsible(True)  # Allow panels to collapse
        right_vertical_splitter.setHandleWidth(2)  # Visible splitter line
        right_vertical_splitter.setContentsMargins(0, 0, 0, 0)
        right_vertical_splitter.setStyleSheet("""
            QSplitter::handle:vertical { background-color: #bdbdbd; height: 1px; }
        """)

        # Create a stacked widget for pipeline and progress monitor
        self.pipeline_stack = QStackedWidget()
        self.pipeline_stack.addWidget(self.pipeline_panel)
        self.pipeline_stack.addWidget(self.progress_monitor_panel)

        # Preview panels in horizontal layout
        preview_splitter = QSplitter(Qt.Horizontal)
        preview_splitter.setChildrenCollapsible(True)  # Allow panels to collapse
        preview_splitter.setContentsMargins(0, 0, 0, 0)  # Remove all margins
        preview_splitter.setHandleWidth(2)
        preview_splitter.setStyleSheet(
            "QSplitter::handle:horizontal { background-color: #e0e0e0; width: 1px; }"
        )
        preview_splitter.addWidget(self.preview_panel_1)
        preview_splitter.addWidget(self.preview_panel_2)
        preview_splitter.setStretchFactor(0, 1)
        preview_splitter.setStretchFactor(1, 1)
        preview_splitter.setSizes([400, 400])  # Set initial sizes

        # Add pipeline and preview panels to vertical splitter
        right_vertical_splitter.addWidget(self.pipeline_stack)
        right_vertical_splitter.addWidget(preview_splitter)

        # Set stretch factors for vertical splitter
        right_vertical_splitter.setStretchFactor(0, 1)  # Pipeline panel
        right_vertical_splitter.setStretchFactor(1, 1)  # Preview panels

        # Set initial sizes (pipeline panel gets more space initially)
        right_vertical_splitter.setSizes([300, 500])

        right_layout.addWidget(right_vertical_splitter)

        # Add panels to main splitter
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_panel)
        main_splitter.setStretchFactor(0, 1)  # Left panel flexible
        main_splitter.setStretchFactor(1, 4)  # Right panel gets more space

        # Allow panels to be resizable
        main_splitter.setChildrenCollapsible(False)  # Allow panels to collapse
        main_splitter.setSizes([300, 800])  # Set initial sizes

        # Set layout for Processing page (no extra bottom control; it's in left panel now)
        processing_layout = QVBoxLayout(self.processing_page)
        processing_layout.setContentsMargins(0, 0, 0, 0)
        processing_layout.setSpacing(0)
        processing_layout.addWidget(main_splitter)

    def setup_results_page(self):
        """Setup the Results page layout"""
        # Create layout for Results page
        results_layout = QVBoxLayout(self.results_page)
        results_layout.setContentsMargins(0, 0, 0, 0)  # Remove all margins
        results_layout.setSpacing(0)  # Remove spacing

        # Add a placeholder label for now
        results_label = QLabel("Results Tab - Coming Soon")
        results_label.setAlignment(Qt.AlignCenter)
        results_label.setStyleSheet("font-size: 16px; color: #666;")
        results_layout.addWidget(results_label)

        # Add the queue panel for results
        results_layout.addWidget(self.queue_panel)

    def setup_training_page(self):
        """Setup the Training page layout"""
        # Create main horizontal splitter for Training page (with dark separator)
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setHandleWidth(2)
        main_splitter.setContentsMargins(0, 0, 0, 0)  # Remove all margins
        main_splitter.setStyleSheet(
            "QSplitter::handle:horizontal { background-color: #2b2b2b; width: 1px; }"
        )

        # Left panel (File Management + Control at bottom for Training Images)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        # Splitter to allow resizing between tree and control panel
        left_vertical_splitter = QSplitter(Qt.Vertical)
        left_vertical_splitter.setChildrenCollapsible(False)
        left_vertical_splitter.setHandleWidth(2)
        left_vertical_splitter.setContentsMargins(0, 0, 0, 0)
        left_vertical_splitter.setStyleSheet(
            "QSplitter::handle:vertical { background-color: #bdbdbd; height: 1px; }"
        )
        left_vertical_splitter.addWidget(self.training_file_tree_panel)
        # Wrap control panel into a container for margins if needed
        control_wrapper_left = QWidget()
        control_layout_left = QVBoxLayout(control_wrapper_left)
        control_layout_left.setContentsMargins(0, 0, 0, 0)
        control_layout_left.setSpacing(0)
        control_layout_left.addWidget(self.training_control_panel)
        # Fix control panel height so it does not expand
        fixed_ctrl_h = 40
        control_wrapper_left.setMinimumHeight(fixed_ctrl_h)
        control_wrapper_left.setMaximumHeight(fixed_ctrl_h)
        control_wrapper_left.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_vertical_splitter.addWidget(control_wrapper_left)
        left_vertical_splitter.setStretchFactor(0, 4)
        left_vertical_splitter.setStretchFactor(1, 0)
        left_vertical_splitter.setSizes([600, fixed_ctrl_h])
        left_layout.addWidget(left_vertical_splitter)
        # Minimum width for the left column
        left_panel.setMinimumWidth(150)

        # Right panel (Pipeline + Previews) - Now using vertical splitter
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Create vertical splitter for pipeline and preview panels
        right_vertical_splitter = QSplitter(Qt.Vertical)
        right_vertical_splitter.setChildrenCollapsible(True)  # Allow panels to collapse
        right_vertical_splitter.setHandleWidth(2)  # Visible splitter line
        right_vertical_splitter.setContentsMargins(0, 0, 0, 0)
        right_vertical_splitter.setStyleSheet(
            "QSplitter::handle:vertical { background-color: #bdbdbd; height: 2px; }"
        )

        # Create a stacked widget for pipeline and progress monitor
        self.training_pipeline_stack = QStackedWidget()
        self.training_pipeline_stack.addWidget(self.training_pipeline_panel)
        self.training_pipeline_stack.addWidget(self.training_progress_monitor_panel)

        # Preview panel (single)
        preview_splitter = QSplitter(Qt.Horizontal)
        preview_splitter.setChildrenCollapsible(True)  # Allow panels to collapse
        preview_splitter.setContentsMargins(0, 0, 0, 0)  # Remove all margins
        preview_splitter.setHandleWidth(2)
        preview_splitter.setStyleSheet(
            "QSplitter::handle:horizontal { background-color: #e0e0e0; width: 2px; }"
        )
        preview_splitter.addWidget(self.training_preview_panel_1)
        preview_splitter.setStretchFactor(0, 1)

        # Add pipeline and preview panels to vertical splitter
        right_vertical_splitter.addWidget(self.training_pipeline_stack)
        right_vertical_splitter.addWidget(preview_splitter)

        # Set stretch factors for vertical splitter
        right_vertical_splitter.setStretchFactor(0, 1)  # Pipeline panel
        right_vertical_splitter.setStretchFactor(1, 1)  # Preview panels

        # Set initial sizes (pipeline panel gets more space initially)
        right_vertical_splitter.setSizes([300, 500])

        right_layout.addWidget(right_vertical_splitter)

        # Add panels to main splitter
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_panel)
        main_splitter.setStretchFactor(0, 1)  # Left panel flexible
        main_splitter.setStretchFactor(1, 4)  # Right panel gets more space

        # Allow panels to be resizable
        main_splitter.setChildrenCollapsible(False)  # Allow panels to collapse
        main_splitter.setSizes([300, 800])  # Set initial sizes

        # Set layout for Training page
        training_layout = QVBoxLayout(self.training_page)
        training_layout.setContentsMargins(0, 0, 0, 0)  # Remove all margins
        training_layout.setSpacing(0)  # Remove spacing
        training_layout.addWidget(main_splitter)

    def setup_connections(self):
        """Setup signal connections"""
        # File tree panel connections (Processing page)
        self.file_tree_panel.log.connect(self._append_log)
        self.file_tree_panel.files_found.connect(self._on_files_found)
        self.file_tree_panel.samples_found.connect(self._on_samples_found)
        self.file_tree_panel.sample_selected.connect(self._on_sample_selected)
        self.file_tree_panel.image_selected.connect(self._on_image_selected)
        self.file_tree_panel.loading_started.connect(self.show_loading_screen, Qt.QueuedConnection)
        self.file_tree_panel.loading_finished.connect(self.hide_loading_screen, Qt.QueuedConnection)

        # Training file tree panel connections
        self.training_file_tree_panel.log.connect(self._append_log)
        self.training_file_tree_panel.files_found.connect(self._on_training_files_found)
        self.training_file_tree_panel.samples_found.connect(self._on_training_samples_found)
        self.training_file_tree_panel.sample_selected.connect(self._on_training_sample_selected)
        self.training_file_tree_panel.image_selected.connect(self._on_image_selected)
        self.training_file_tree_panel.loading_started.connect(
            self.show_loading_screen, Qt.QueuedConnection
        )
        self.training_file_tree_panel.loading_finished.connect(
            self.hide_loading_screen, Qt.QueuedConnection
        )

        # Control panel connections
        self.control_panel.save_clicked.connect(self._on_save_clicked)
        self.control_panel.save_path_changed.connect(self._on_save_path_changed)

        # Training control panel connections
        self.training_control_panel.save_clicked.connect(self._on_save_clicked)
        self.training_control_panel.save_path_changed.connect(self._on_save_path_changed)

        # Pipeline panel connections (Processing page)
        self.pipeline_panel.request_samples.connect(self._on_request_samples)
        self.pipeline_panel.select_first_sample.connect(self._on_select_first_sample)
        self.pipeline_panel.stop_step.connect(self._on_stop_step)
        self.pipeline_panel.save_result.connect(self._on_save_result)
        self.pipeline_panel.log.connect(self._append_log)
        self.pipeline_panel.sample_completed.connect(self._on_sample_completed)
        self.pipeline_panel.sample_failed.connect(self._on_sample_failed)
        self.pipeline_panel.current_sample_changed.connect(self._on_current_sample_changed)

        # Training pipeline panel connections
        self.training_pipeline_panel.request_samples.connect(self._on_training_request_samples)
        self.training_pipeline_panel.select_first_sample.connect(
            self._on_training_select_first_sample
        )
        self.training_pipeline_panel.stop_step.connect(self._on_training_stop_step)
        self.training_pipeline_panel.log.connect(self._append_log)
        self.training_pipeline_panel.current_sample_changed.connect(
            self._on_training_current_sample_changed
        )
        # Hook training Run via existing run_step signal
        self.training_pipeline_panel.run_step.connect(self._on_training_run_step)

        # Connect Pipeline Controller
        self.controller = PipelineController()
        self.controller.log.connect(self._append_log)
        self.controller.progress.connect(self._on_progress)
        self.controller.done.connect(self._on_step_done)
        self.controller.error.connect(self._on_step_error)

        # Preview panel connections (Processing page)
        self.preview_panel_1.log.connect(self._append_log)
        self.preview_panel_2.log.connect(self._append_log)

        # Training preview panel connections
        self.training_preview_panel_1.log.connect(self._append_log)

    def _build_toolbar(self):
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, tb)

        act_file = QAction(QIcon(), "File", self)
        act_info = QAction(QIcon(), "Info", self)
        act_settings = QAction(QIcon(), "Settings", self)

        act_file.triggered.connect(self._on_file_toolbar)
        act_info.triggered.connect(self._on_info_toolbar)

        tb.addAction(act_file)
        tb.addSeparator()
        tb.addAction(act_settings)
        tb.addSeparator()
        tb.addAction(act_info)

        act_settings.triggered.connect(self._open_settings_dialog)

    def _open_settings_dialog(self):
        dlg = SettingsDialog(self)
        # load current config
        if self.configuration:
            dlg.set_configuration(self.configuration)
        if dlg.exec() == QDialog.Accepted:
            self.configuration = dlg.get_configuration()
            self._save_configuration()  # Save configuration to file
            self._append_log(log_format("Settings updated and saved"))

    def _on_page_changed(self, index: int):
        """Handle page changes from sidebar selection"""
        page_names = ["processing", "results", "training"]
        if 0 <= index < len(page_names):
            self.current_page = page_names[index]
            self._append_log(log_format(f"Switched to {self.current_page} page"))
        else:
            self.current_page = "unknown"
            self._append_log(log_format(f"Unknown page index: {index}"))

    def _on_file_toolbar(self):
        """Handle file toolbar button - add folder to file tree panel"""
        # Call the appropriate file tree panel's add folder function based on current page
        if self.current_page == "processing":
            self._append_log(log_format("Adding folder to processing file tree"))
            self.file_tree_panel._add_folder()
        elif self.current_page == "training":
            self._append_log(log_format("Adding folder to training file tree"))
            self.training_file_tree_panel._add_folder()
        elif self.current_page == "results":
            self._append_log(log_format("Results page - file tree functionality not available"))
            return
        else:
            self._append_log(
                log_format(f"Unknown current page: {self.current_page}. Cannot add folder.")
            )
            return

    def _on_info_toolbar(self):
        QMessageBox.information(
            self, "CGT Cell Analysis Demo", f"CGT Cell Analysis Demo v{__version__} (Jinwoo Seol)"
        )

    def show_loading_screen(self, message="Loading..."):
        """Show the loading screen for file/folder operations"""
        self.loading_screen.show_loading(message)

    def hide_loading_screen(self):
        """Hide the loading screen"""
        self.loading_screen.hide_loading()

    def is_loading_screen_visible(self):
        """Check if loading screen is currently visible"""
        return self.loading_screen.is_visible()

    def _append_log(self, text: str):
        # Append text to the log panel
        self.log_panel.append(text)

    def _on_run_step(self, step: int, folder: str, sample_id: str = None):
        self._append_log(log_format(f"Running Step{step} with Folder: {folder}"))
        # Reflect sample and step in header
        self.pipeline_panel.set_current_sample(self.current_sample_id)
        self.pipeline_panel.set_current_step(step)
        # Update file tree status color for current sample
        try:
            self.file_tree_panel.set_sample_status(self.current_sample_id, "processing")
        except Exception:
            pass

        # Update UI to show step is running
        self.pipeline_panel.set_step_running(step, True)
        self.pipeline_panel.update_progress(step, 0)

        out_dir_path = self.control_panel.get_save_path()
        if sample_id is None:
            sample_name = self.current_sample_id
        else:
            sample_name = sample_id
        out_dir = out_dir_path + "/" + sample_name
        if step == 1:
            step_out_dir = out_dir + "/01_optical_index_extract"
            ref = RefPaths(
                sensor_map_tif=Path(self.configuration.get("sensor_map", "")),
                marker_7x7_csv=Path(self.configuration.get("marker_7x7", ""))
                if self.configuration.get("marker_7x7")
                else None,
                marker_5x5_csv=Path(self.configuration.get("marker_5x5", ""))
                if self.configuration.get("marker_5x5")
                else None,
                well_csv=Path(self.configuration.get("well_csv", ""))
                if self.configuration.get("well_csv")
                else None,
            )
            self.controller.run_step1(sample_name, folder, ref, step_out_dir)
        elif step == 2:
            step_out_dir = out_dir + "/02_cell_counting"
            # Pass cell counting configuration
            cell_counting_config = {
                "model_weights_path": self.configuration.get("ai_model_weights_path", ""),
                "batch_size": self.configuration.get("batch_size", 32),
                "confidence_threshold": self.configuration.get("confidence_threshold", 0.5),
                "output_format": self.configuration.get("output_format", "both"),
                "use_gpu": self.configuration.get("use_gpu", True),
                "image_size": self.configuration.get("image_size", 224),
            }
            self.controller.run_step2(sample_name, folder, step_out_dir, cell_counting_config)

        elif step == 3:
            step_out_dir = out_dir + "/03_pcr_image_indexing"  # Formerly Step 4
            ref = RefPaths(
                sensor_map_tif=Path(self.configuration.get("sensor_map", "")),
                marker_7x7_csv=Path(self.configuration.get("marker_7x7", ""))
                if self.configuration.get("marker_7x7")
                else None,
                marker_5x5_csv=Path(self.configuration.get("marker_5x5", ""))
                if self.configuration.get("marker_5x5")
                else None,
                well_csv=Path(self.configuration.get("well_csv", ""))
                if self.configuration.get("well_csv")
                else None,
            )
            self.controller.run_step3(sample_name, folder, ref, step_out_dir)

        elif step == 4:
            step_out_dir = out_dir + "/04_merge"  # Formerly Step 5
            # Get additional folder information for Step 4 (no input folder for Step 4)
            step_folders = self.pipeline_panel.get_all_folders(step)
            cell_count_folder = step_folders.get("cell_count", "")
            labeled_rawdata_folder = step_folders.get("labeled_rawdata", "")

            self._append_log(
                log_format(
                    f"[Step {step}] Using folders - Cell Count: {cell_count_folder}, Labeled RawData: {labeled_rawdata_folder}"
                )
            )
            # For Step 4, we don't use the main input folder, so pass empty string
            self.controller.run_step4(
                sample_name, cell_count_folder, labeled_rawdata_folder, step_out_dir
            )

        else:
            self._append_log(log_format(f"Invalid Step: {step}"))

    def _on_stop_step(self, step: int):
        """Handle stop step request"""
        self._append_log(log_format(f"Stopping Step{step}"))
        self.controller.cancel_step(step)

        # Reset sample status to idle when stopping
        try:
            self.file_tree_panel.set_sample_status(self.current_sample_id, "idle")
        except Exception:
            pass

    def _on_save_result(self):
        """Handle save result request"""
        try:
            self._append_log(log_format("Saving final CSV results..."))

            # Get the current sample ID
            sample_id = self.current_sample_id
            if not sample_id:
                self._append_log(log_format("No sample selected for saving results", level="Error"))
                return

            # Get the work directory from configuration
            sample_output_folder = Path(self.control_panel.get_save_path()) / sample_id

            # Check if Step 4 (Merge) has been completed
            merge_folder = sample_output_folder / "04_merge"
            if not merge_folder.exists():
                self._append_log(
                    log_format(
                        "Step 4 (Merge) not completed yet. Please run the full pipeline first.",
                        level="Error",
                    )
                )
                return

            # Look for all files in the merge folder
            all_files = list(merge_folder.glob("*"))
            # Filter out directories, keep only files
            files_to_save = [f for f in all_files if f.is_file()]
            if not files_to_save:
                self._append_log(log_format("No files found in merge folder", level="Error"))
                return

            # Ask user to select save location
            save_dir = QFileDialog.getExistingDirectory(
                self,
                "Select Directory to Save Results",
                str(sample_output_folder),
                QFileDialog.ShowDirsOnly,
            )

            if not save_dir:
                self._append_log(log_format("Save cancelled by user"))
                return

            save_path = Path(save_dir)

            # Copy all files to the selected directory
            saved_files = []
            for file_to_save in files_to_save:
                dest_file = save_path / file_to_save.name
                import shutil

                shutil.copy2(file_to_save, dest_file)
                saved_files.append(dest_file.name)
                self._append_log(log_format(f"Saved: {dest_file.name}"))

            self._append_log(
                log_format(f"Successfully saved {len(saved_files)} files to: {save_path}")
            )
            self._append_log(log_format(f"Files saved: {', '.join(saved_files)}"))

        except Exception as e:
            self._append_log(log_format(f"Failed to save results: {str(e)}", level="Error"))

    def _on_step_done(self, step: int, artifacts: dict):
        """Handle step completion"""
        self._append_log(log_format(f"[Done] Step{step}: {artifacts}"))
        if step == 101:
            self.training_pipeline_panel.set_step_running(1, False)
            self.training_pipeline_panel.update_progress(1, 100)
            self.training_pipeline_panel._set_state("Done")
        else:
            self.pipeline_panel.set_step_running(step, False)
            self.pipeline_panel.update_progress(step, 100)
            self.pipeline_panel._set_state("Done")
            # Mark sample as done (for the simple case where Step 4 finishes)
            try:
                if step == 4:
                    self.file_tree_panel.set_sample_status(self.current_sample_id, "done")
                    # Trigger sample completion for batch processing
                    if (
                        hasattr(self.pipeline_panel, "_is_batch_processing")
                        and self.pipeline_panel._is_batch_processing
                    ):
                        self.pipeline_panel._on_sample_completed(self.current_sample_id)
                else:
                    # For intermediate steps, keep processing status
                    self.file_tree_panel.set_sample_status(self.current_sample_id, "processing")
            except Exception:
                pass

    def _on_step_error(self, step: int, error: str):
        """Handle step error"""
        self._append_log(log_format(f"[Error] Step{step}: {error}"))
        if step == 101:
            self.training_pipeline_panel.set_step_running(1, False)
            self.training_pipeline_panel._set_state("Error")
        else:
            self.pipeline_panel.set_step_running(step, False)
            self.pipeline_panel._set_state("Error")
            # Mark sample as error
            try:
                self.file_tree_panel.set_sample_status(self.current_sample_id, "error")
                # Trigger sample failure for batch processing
                if (
                    hasattr(self.pipeline_panel, "_is_batch_processing")
                    and self.pipeline_panel._is_batch_processing
                ):
                    self.pipeline_panel._on_sample_failed(self.current_sample_id, error)
            except Exception:
                pass

    def _on_auto_trigger_step2(self, sample_id: str, well_image_folder: str):
        """Handle automatic step 2 triggering from step 1 completion"""
        self._append_log(
            log_format(f"[AutoChain] Automatically starting Step 2 for sample: {sample_id}")
        )

        # Convert to absolute path
        well_image_folder_abs = str(Path(well_image_folder).resolve())
        self._append_log(
            log_format(f"[AutoChain] Using Well_Image folder: {well_image_folder_abs}")
        )

        self.pipeline_panel.set_input_folder(2, well_image_folder_abs)
        self._on_run_step(2, well_image_folder_abs, sample_id)

    def _on_auto_trigger_step3(self, sample_id: str, step2_output_folder: str):
        """Handle automatic step 3 triggering from step 2 completion"""
        self._append_log(
            log_format(f"[AutoChain] Automatically starting Step 3 for sample: {sample_id}")
        )

        # Convert to absolute path
        step2_output_folder_abs = str(Path(step2_output_folder).resolve())
        self.pipeline_panel.set_additional_folder(4, "cell_count", step2_output_folder_abs)

        # Get the already selected PCR folder from the pipeline panel
        pcr_folder = self.pipeline_panel._folder_edits[3].text()
        if not pcr_folder:
            self._append_log(
                log_format(
                    "[AutoChain] No PCR folder selected for Step 3. Please select a PCR folder first."
                )
            )
            return

        # Convert PCR folder to absolute path
        pcr_folder_abs = str(Path(pcr_folder).resolve())
        self._append_log(log_format(f"[AutoChain] Using PCR folder: {pcr_folder_abs}"))
        self._on_run_step(3, pcr_folder_abs, sample_id)

    def _on_auto_trigger_step4(self, sample_id: str, step3_output_folder: str):
        """Handle automatic step 4 triggering from step 3 completion"""
        self._append_log(
            log_format(f"[AutoChain] Automatically starting Step 4 for sample: {sample_id}")
        )

        # Convert to absolute path
        step3_output_folder_abs = str(Path(step3_output_folder).resolve())
        self.pipeline_panel.set_additional_folder(4, "labeled_rawdata", step3_output_folder_abs)

        # Check if both required folders are set for Step 4
        cell_count_folder = self.pipeline_panel.get_additional_folder(4, "cell_count")
        labeled_rawdata_folder = self.pipeline_panel.get_additional_folder(4, "labeled_rawdata")

        if not cell_count_folder:
            self._append_log(
                log_format(
                    "[AutoChain] No Cell Count Data folder set for Step 4. Please run Step 2 first."
                )
            )
            return

        if not labeled_rawdata_folder:
            self._append_log(
                log_format(
                    "[AutoChain] No Labeled RawData folder set for Step 4. Please run Step 3 first."
                )
            )
            return

        # Convert to absolute paths for logging
        cell_count_folder_abs = str(Path(cell_count_folder).resolve())
        labeled_rawdata_folder_abs = str(Path(labeled_rawdata_folder).resolve())

        self._append_log(
            log_format(f"[AutoChain] Using Cell Count folder: {cell_count_folder_abs}")
        )
        self._append_log(
            log_format(f"[AutoChain] Using Labeled RawData folder: {labeled_rawdata_folder_abs}")
        )
        self._on_run_step(4, "", sample_id)  # Step 4 doesn't use main input folder

    def _on_current_sample_changed(self, sample_id: str):
        """Handle when current sample changes during batch processing."""
        self.current_sample_id = sample_id
        self._append_log(log_format(f"[Batch] Current sample changed to: {sample_id}"))

    def _on_sample_completed(self, sample_id: str):
        """Handle when a sample's processing is completed in batch mode."""
        self._append_log(log_format(f"[Batch] Sample {sample_id} completed successfully"))

        # Update file tree status
        try:
            self.file_tree_panel.set_sample_status(sample_id, "done")
        except Exception:
            pass

    def _on_sample_failed(self, sample_id: str, error: str):
        """Handle when a sample's processing fails in batch mode."""
        self._append_log(log_format(f"[Batch] Sample {sample_id} failed: {error}"))

        # Update file tree status
        try:
            self.file_tree_panel.set_sample_status(sample_id, "idle")
        except Exception:
            pass

    def _on_progress(self, step: int, val: int):
        if step == 101:
            self.training_pipeline_panel.update_progress(1, val)
        else:
            self.pipeline_panel.update_progress(step, val)

    def _run_one_job(self, job: TestJob):
        # Create/update a job
        job.status = JobStatus.running
        self.queue_panel.add_or_update_row(
            job.job_id,
            job.sample_id,
            bool(job.optical_dir),
            bool(job.pcr_dir),
            job.status.value,
            job.current_step,
            job.percent,
        )

        # Create the out/sample directory
        os.makedirs(Path(job.out_root) / job.sample_id, exist_ok=True)

        # Pass job_id to the controller (so callbacks know which job is running)
        def bind_progress(step, pct, job_id=job.job_id):
            self._on_job_progress(job_id, step, pct)

        def bind_done(step, arts, job_id=job.job_id):
            self._on_job_step_done(job_id, step, arts)

        def bind_error(step, msg, job_id=job.job_id):
            self._on_job_step_error(job_id, step, msg)

        # Temporarily bind controller callbacks to this job (best effort)
        self.controller.progress.disconnect() if self.controller.progress.receivers() else None
        self.controller.done.disconnect() if self.controller.done.receivers() else None
        self.controller.error.disconnect() if self.controller.error.receivers() else None
        self.controller.progress.connect(bind_progress)
        self.controller.done.connect(bind_done)
        self.controller.error.connect(bind_error)

        # Run the stages (only those optical/pcr inputs that are present)
        self.controller.run_job_all(
            sample_id=job.sample_id,
            optical_dir=Path(job.optical_dir) if job.optical_dir else None,
            pcr_dir=Path(job.pcr_dir) if job.pcr_dir else None,
        )

    # ---------- job progress update ----------
    def _on_job_progress(self, job_id: str, step: int, pct: int):
        job = self.jobs[job_id]
        job.current_step = step
        job.percent = pct
        self.queue_panel.add_or_update_row(
            job.job_id,
            job.sample_id,
            bool(job.optical_dir),
            bool(job.pcr_dir),
            job.status.value,
            job.current_step,
            job.percent,
        )
        # Update progress monitor
        self.progress_monitor_panel.update_test(job)

    def _on_job_step_done(self, job_id: str, step: int, arts: dict):
        job = self.jobs[job_id]
        self._append_log(log_format(f"[{job.sample_id}] Step{step} Done"))
        if step == 4:  # Now the final step is 4 (formerly 5)
            job.status = JobStatus.done
            job.percent = 100
            self.queue_panel.add_or_update_row(
                job.job_id,
                job.sample_id,
                bool(job.optical_dir),
                bool(job.pcr_dir),
                job.status.value,
                job.current_step,
                job.percent,
            )
            # Update progress monitor
            self.progress_monitor_panel.update_test(job)
            # Trigger the next stage
            self.batch.mark_done(job)

    def _on_job_step_error(self, job_id: str, step: int, msg: str):
        job = self.jobs[job_id]
        job.status = JobStatus.failed
        self.queue_panel.add_or_update_row(
            job.job_id,
            job.sample_id,
            bool(job.optical_dir),
            bool(job.pcr_dir),
            job.status.value,
            step,
            job.percent,
        )
        # Update progress monitor
        self.progress_monitor_panel.update_test(job)
        self._append_log(log_format(f"[{job.sample_id}] Step{step} ERROR: {msg}"))

    # ---------- batch manager events ----------
    def _on_job_added(self, job: TestJob):
        self.queue_panel.add_or_update_row(
            job.job_id,
            job.sample_id,
            bool(job.optical_dir),
            bool(job.pcr_dir),
            job.status.value,
            job.current_step,
            job.percent,
        )
        # Add to progress monitor
        self.progress_monitor_panel.add_test(job)

    def _on_job_updated(self, job: TestJob):
        self.queue_panel.add_or_update_row(
            job.job_id,
            job.sample_id,
            bool(job.optical_dir),
            bool(job.pcr_dir),
            job.status.value,
            job.current_step,
            job.percent,
        )
        # Update progress monitor
        self.progress_monitor_panel.update_test(job)

    # New event handlers for the restructured UI
    def _on_files_found(self, files: list):
        """Handle files found by the file tree panel"""
        self._append_log(log_format(f"Found {len(files)} files"))

        # Update pipeline panel with found files
        self.pipeline_panel.set_available_files(files)

    def _on_samples_found(self, samples: list):
        """Handle samples found by the file tree panel"""
        self._append_log(log_format(f"Found {len(samples)} test samples"))

        # Log sample details
        for sample in samples:
            sample_id = sample["sample_id"]
            optical_count = (
                len(sample["optical_data"]["image_folders"]) if sample["optical_data"] else 0
            )
            pcr_count = (
                len(sample["pcr_data"]["odpi_files"]) + len(sample["pcr_data"]["data_folders"])
                if sample["pcr_data"]
                else 0
            )

            self._append_log(
                log_format(
                    f"Sample '{sample_id}': {optical_count} optical folders, {pcr_count} PCR items"
                )
            )

        # Update pipeline panel with sample information
        self.pipeline_panel.set_available_samples(samples)

    def _on_request_samples(self):
        """Handle request for samples from pipeline panel"""
        self._append_log(log_format("Pipeline requested samples from file tree"))

        # Get current samples from file tree panel in the order they appear in the tree
        samples = self.file_tree_panel.get_current_samples()

        if samples:
            self._append_log(log_format(f"Retrieved {len(samples)} samples from file tree"))
            # Log the order of samples to confirm they are in the correct order
            for i, sample in enumerate(samples):
                sample_id = sample.get("sample_id", "Unknown")
                self._append_log(log_format(f"Sample {i + 1}: {sample_id}"))
            # Update pipeline panel with sample information
            self.pipeline_panel.set_available_samples(samples)
        else:
            self._append_log(
                log_format(
                    "No samples found in file tree. Please add folders to the file tree first."
                )
            )

    def _on_select_first_sample(self):
        """Handle request to select first sample in file tree"""
        self._append_log(log_format("Pipeline requested selection of first sample in file tree"))

        # Get current samples from file tree panel
        samples = self.file_tree_panel.get_samples_in_tree_order()

        if samples:
            # Select the first valid sample in the file tree
            first_sample = samples[0]
            sample_id = first_sample["sample_id"]

            # Find the corresponding tree item and select it
            if (
                hasattr(self.file_tree_panel, "sample_items")
                and sample_id in self.file_tree_panel.sample_items
            ):
                tree_item = self.file_tree_panel.sample_items[sample_id]
                self.file_tree_panel.tree.setCurrentItem(tree_item)
                self._append_log(log_format(f"Selected first sample in file tree: {sample_id}"))
            else:
                self._append_log(log_format(f"Could not find tree item for sample: {sample_id}"))
        else:
            self._append_log(log_format("No samples available to select"))

    def _on_save_clicked(self):
        """Handle save button clicked"""
        self._append_log(log_format("Save button clicked - directory selected"))

    def _on_save_path_changed(self, path: str):
        """Handle save path change"""
        self._append_log(log_format(f"Save path changed: {path}"))

    def _switch_to_pipeline(self):
        """Switch from progress monitor to pipeline panel"""
        self.pipeline_stack.setCurrentWidget(self.pipeline_panel)
        self._append_log(log_format("Switched to Pipeline Panel"))

    def _switch_to_progress_monitor(self):
        """Switch from pipeline panel to progress monitor"""
        self.pipeline_stack.setCurrentWidget(self.progress_monitor_panel)
        self._append_log(log_format("Switched to Progress Monitor"))

    def _load_configuration(self):
        """Load saved configuration from file"""
        try:
            if self.config_file_path.exists():
                with open(self.config_file_path, encoding="utf-8") as f:
                    saved_config = json.load(f)
                    # Merge defaults into loaded config to ensure required keys exist
                    merged = dict(self.configuration)
                    merged.update(saved_config or {})
                    # Ensure all default keys exist
                    changed = False
                    for key, value in self._default_config().items():
                        if key not in merged:
                            merged[key] = value
                            changed = True

                    # Convert relative paths to absolute paths based on bundle structure
                    merged = self._resolve_config_paths(merged)

                    self.configuration = merged
                    # Persist back if we added missing keys
                    if changed:
                        with open(self.config_file_path, "w", encoding="utf-8") as wf:
                            json.dump(self.configuration, wf, indent=2, ensure_ascii=False)
                        self._append_log(log_format("Updated configuration with missing defaults"))
                    self._append_log(log_format("Loaded saved configuration"))
            else:
                self._append_log(log_format("No saved configuration found, using defaults"))
        except Exception as e:
            self._append_log(log_format(f"Error loading configuration: {str(e)}"))
            self._append_log(log_format("Using default configuration"))

    def _resolve_config_paths(self, config):
        """Resolve relative paths in configuration to absolute paths based on bundle structure"""
        # Path keys that need to be resolved
        path_keys = ["sensor_map", "marker_7x7", "marker_5x5", "well_csv", "ai_model_weights_path"]

        resolved_config = config.copy()
        for key in path_keys:
            if key in resolved_config:
                path_value = resolved_config[key]
                if isinstance(path_value, str):
                    # Check if it's already an absolute path
                    if Path(path_value).is_absolute():
                        # Keep absolute paths as-is
                        resolved_config[key] = path_value
                    else:
                        # Convert relative path to absolute based on bundle structure
                        if key == "ai_model_weights_path":
                            # For models, just use the filename directly
                            resolved_config[key] = str(__models_path__ / Path(path_value).name)
                        else:
                            # For reference data, just use the filename directly
                            resolved_config[key] = str(
                                __reference_data_path__ / Path(path_value).name
                            )

        return resolved_config

    def _save_configuration(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file_path, "w", encoding="utf-8") as f:
                json.dump(self.configuration, f, indent=2, ensure_ascii=False)
            self._append_log(log_format("Configuration saved"))
        except Exception as e:
            self._append_log(log_format(f"Error saving configuration: {str(e)}"))

    def _initialize_default_configuration(self):
        """Initialize default reference data and configuration"""

        # Default reference data paths
        default_ref_data_dir = __reference_data_path__
        default_models_dir = __models_path__

        # Default configuration (only set if not already loaded from file)
        default_config = {
            # Reference Map files
            "sensor_map": str(default_ref_data_dir / "ref_Sensor_Map_HD.tif"),
            "marker_7x7": str(default_ref_data_dir / "ref_Marker_Position_7X7.csv"),
            "marker_5x5": str(default_ref_data_dir / "ref_Marker_Position_5X5.csv"),
            "well_csv": str(default_ref_data_dir / "ref_Well_Position.csv"),
            # AI Models
            "ai_model_weights_path": str(default_models_dir / "white_ori_ViTRegressor_weights.pth"),
            # Cell Counting specific settings
            "batch_size": 32,
            "confidence_threshold": 0.5,
            # Output settings (Excel option removed; CSV always written)
            "include_metadata": True,
            # Processing settings
            "use_gpu": True,
            "num_workers": 4,
            "image_size": 224,
            # Developer mode
            "developer_mode": False,
        }

        # Only set defaults for keys that don't already exist
        for key, value in default_config.items():
            if key not in self.configuration:
                self.configuration[key] = value

        # Log the default configuration
        self._append_log(log_format("Default configuration initialized"))
        self._append_log(log_format(f"Reference data directory: {default_ref_data_dir}"))
        self._append_log(log_format(f"Models directory: {default_models_dir}"))

        # Check if default directories exist and create them if needed
        self._ensure_default_directories_exist()

    def _default_config(self) -> dict:
        """Return a dict of default configuration keys/values."""
        default_ref_data_dir = __reference_data_path__
        default_models_dir = __models_path__
        return {
            "sensor_map": str(default_ref_data_dir / "ref_Sensor_Map_HD.tif"),
            "marker_7x7": str(default_ref_data_dir / "ref_Marker_Position_7X7.csv"),
            "marker_5x5": str(default_ref_data_dir / "ref_Marker_Position_5X5.csv"),
            "well_csv": str(default_ref_data_dir / "ref_Well_Position.csv"),
            "ai_model_weights_path": str(default_models_dir / "white_ori_ViTRegressor_weights.pth"),
            "batch_size": 64,
            "confidence_threshold": 0.5,
            "output_format": "csv",
            "include_metadata": True,
            "use_gpu": True,
            "use_half_precision": True,
            "num_workers": 4,
            "image_size": 224,
            "developer_mode": False,
        }

    def _ensure_default_directories_exist(self):
        """Ensure default directories exist, create them if they don't"""
        # In PyInstaller bundle, directories are already included
        # In development, create them if they don't exist
        if not getattr(sys, "frozen", False):
            # Only create directories in development mode
            project_root = __project_path__

            # Create reference data directory structure
            ref_dirs = [
                project_root / "reference_data",
            ]

            # Create models directory structure
            model_dirs = [
                project_root / "models",
            ]

            # Create all directories
            for directory in ref_dirs + model_dirs:
                directory.mkdir(parents=True, exist_ok=True)

        # Check for missing reference files and log notices
        self._check_reference_files()

    def _check_reference_files(self):
        """Check for missing reference files and log notices"""
        ref_data_dir = __reference_data_path__

        # Reference files to check
        reference_files = {
            "ref_Sensor_Map_HD.tif": "Reference sensor map for well indexing",
            "ref_Marker_Position_7X7.csv": "7x7 marker positions for optical well indexing",
            "ref_Marker_Position_5X5.csv": "5x5 marker positions for PCR well indexing",
            "ref_Well_Position.csv": "Well position reference data",
        }

        missing_files = []
        for filename, description in reference_files.items():
            file_path = ref_data_dir / filename
            if not file_path.exists():
                missing_files.append(f"{filename} ({description})")

        if missing_files:
            self._append_log(log_format("Notice: The following reference files are missing:"))
            for file_info in missing_files:
                self._append_log(log_format(f"  - {file_info}"))
            self._append_log(
                log_format(
                    "Please add these files to the reference_data directory for full functionality."
                )
            )
        else:
            self._append_log(log_format("All reference files found in reference_data directory."))

    def get_default_configuration(self):
        """Get the current default configuration"""
        return self.configuration.copy()

    def update_configuration(self, new_config):
        """Update configuration with new values"""
        self.configuration.update(new_config)
        self._save_configuration()  # Auto-save when configuration is updated
        self._append_log(log_format("Configuration updated and saved"))

    # ---------- Developer mode helpers ----------
    def _apply_developer_mode(self, enabled: bool):
        self.training_item.setHidden(not enabled)
        # If disabling while training is selected, move selection to Processing
        if not enabled and self.sidebar.currentItem() is self.training_item:
            self.sidebar.setCurrentItem(self.processing_item)
        # Feedback
        msg = "Developer Mode ON" if enabled else "Developer Mode OFF"
        # Show centered developer label without touching main status label
        self.dev_label.setText("Developer Mode" if enabled else "")
        self.dev_label.setVisible(enabled)
        if enabled:
            self._append_log(log_format(msg))

    def _toggle_developer_mode(self):
        self.developer_mode = not self.developer_mode
        # Persist to configuration
        self.configuration["developer_mode"] = self.developer_mode
        self._save_configuration()
        # Apply UI state
        self._apply_developer_mode(self.developer_mode)

    def _on_sample_selected(self, sample_data: dict):
        """Handle when a sample is selected in the file tree"""
        sample_name = sample_data.get("sample_name", "")
        optical_folder = sample_data.get("optical_folder")
        pcr_folder = sample_data.get("pcr_folder")

        # Check if this is a valid sample selection
        if not sample_name:
            # Clear all pipeline inputs
            self.pipeline_panel.set_input_folder(1, "")
            self.pipeline_panel.set_input_folder(2, "")
            self.pipeline_panel.set_input_folder(3, "")
            self.pipeline_panel.set_additional_folder(4, "cell_count", "")
            self.pipeline_panel.set_additional_folder(4, "labeled_rawdata", "")
            self._append_log(log_format("Pipeline inputs cleared - no sample selected"))

            # Clear preview panels
            self.preview_panel_1.set_sample_data(None)
            self.preview_panel_2.set_sample_data(None)
            return

        # Update current sample ID
        self.current_sample_id = sample_name
        self._append_log(log_format(f"Setting up pipeline for sample: {sample_name}"))

        # Set Step 1 input folder (Optical)
        if optical_folder:
            self.pipeline_panel.set_input_folder(1, optical_folder)
            self._append_log(log_format(f"Step 1 input set to: {optical_folder}"))
        else:
            self.pipeline_panel.set_input_folder(1, "")
            self._append_log(log_format("No optical folder found for Step 1"))

        # Clear Step 2 input folder
        self.pipeline_panel.set_input_folder(2, "")

        # Set Step 3 input folder (PCR)
        if pcr_folder:
            self.pipeline_panel.set_input_folder(3, pcr_folder)
            self._append_log(log_format(f"Step 3 input set to: {pcr_folder}"))
        else:
            self.pipeline_panel.set_input_folder(3, "")
            self._append_log(log_format("No PCR folder found for Step 3"))

        # Clear Step 4 additional folders (no input folder for Step 4)
        self.pipeline_panel.set_additional_folder(4, "cell_count", "")
        self.pipeline_panel.set_additional_folder(4, "labeled_rawdata", "")

        # Update preview panels with sample data
        self.preview_panel_1.set_sample_data(sample_data)
        self.preview_panel_2.set_sample_data(sample_data)

    # Training page specific signal handlers
    def _on_training_files_found(self, files: list):
        """Handle files found by the training file tree panel"""
        self._append_log(log_format(f"[Training] Found {len(files)} files"))

        # Update training pipeline panel with found files
        self.training_pipeline_panel.set_available_files(files)

    def _on_training_samples_found(self, samples: list):
        """Handle samples found by the training file tree panel"""
        self._append_log(log_format(f"[Training] Found {len(samples)} training samples"))

        # Log sample details
        for sample in samples:
            sample_id = sample["sample_id"]
            optical_count = (
                len(sample["optical_data"]["image_folders"]) if sample["optical_data"] else 0
            )
            pcr_count = (
                len(sample["pcr_data"]["odpi_files"]) + len(sample["pcr_data"]["data_folders"])
                if sample["pcr_data"]
                else 0
            )

            self._append_log(
                log_format(
                    f"[Training] Sample '{sample_id}': {optical_count} optical folders, {pcr_count} PCR items"
                )
            )

        # Update training pipeline panel with sample information
        self.training_pipeline_panel.set_available_samples(samples)

    def _on_training_request_samples(self):
        """Handle request for samples from training pipeline panel"""
        self._append_log(log_format("[Training] Pipeline requested samples from file tree"))

        # Get current samples from training file tree panel in the order they appear in the tree
        samples = self.training_file_tree_panel.get_current_samples()

        if samples:
            self._append_log(
                log_format(f"[Training] Retrieved {len(samples)} samples from file tree")
            )
            # Log the order of samples to confirm they are in the correct order
            for i, sample in enumerate(samples):
                sample_id = sample.get("sample_id", "Unknown")
                self._append_log(log_format(f"[Training] Sample {i + 1}: {sample_id}"))
            # Update training pipeline panel with sample information
            self.training_pipeline_panel.set_available_samples(samples)
        else:
            self._append_log(
                log_format(
                    "[Training] No samples found in file tree. Please add folders to the file tree first."
                )
            )

    def _on_training_select_first_sample(self):
        """Handle request to select first sample in training file tree"""
        self._append_log(
            log_format("[Training] Pipeline requested selection of first sample in file tree")
        )

        # Get current samples from training file tree panel
        samples = self.training_file_tree_panel.get_current_samples()

        if samples:
            # Select the first valid sample in the file tree
            first_sample = samples[0]
            sample_id = first_sample["sample_id"]

            # Find the corresponding tree item and select it
            if (
                hasattr(self.training_file_tree_panel, "sample_items")
                and sample_id in self.training_file_tree_panel.sample_items
            ):
                tree_item = self.training_file_tree_panel.sample_items[sample_id]
                self.training_file_tree_panel.tree.setCurrentItem(tree_item)
                self._append_log(
                    log_format(f"[Training] Selected first sample in file tree: {sample_id}")
                )
            else:
                self._append_log(
                    log_format(f"[Training] Could not find tree item for sample: {sample_id}")
                )
        else:
            self._append_log(log_format("[Training] No samples available to select"))

    def _on_training_current_sample_changed(self, sample_id: str):
        """Handle when current sample changes during training batch processing."""
        self.current_sample_id = sample_id
        self._append_log(log_format(f"[Training] Current sample changed to: {sample_id}"))

    def _on_training_sample_selected(self, sample_data: dict):
        """Handle when a sample is selected in the training file tree"""
        training_folder = sample_data.get("training_folder", "")

        self.training_pipeline_panel.set_input_folder(1, training_folder)

        self._append_log(
            log_format(f"[Training] Setting up pipeline for training folder: {training_folder}")
        )

        # Update training preview panel with sample data
        self.training_preview_panel_1.set_sample_data(sample_data)

    def _on_image_selected(self, panel_type: str, image_path: Path):
        """Handle when an image is selected in the training file tree"""
        self._append_log(log_format(f"[Training] Image selected: {image_path}"))

        # Update training preview panel with image data
        if panel_type == "Training":
            self.training_preview_panel_1.set_image_data(image_path)
        else:
            self.preview_panel_1.set_image_data(image_path)

    def _on_training_stop_step(self, step: int):
        """Handle stop step request for training"""
        self._append_log(log_format(f"[Training] Stopping Step{step}"))
        # For now, just log the request - you can add training-specific stop logic later

    def _on_training_run_step(self, step: int, folder: str):
        """Handle Run button in training panel.
        Step 1: image folder (folder), plus label CSV from additional field.
        """
        # Only implement step 1 for training
        if step != 1:
            self._append_log(log_format(f"[Training] Unsupported step: {step}"))
            return
        image_folder = folder
        label_csv = image_folder + "/cell_count_labels.csv"
        if not image_folder:
            self._append_log(log_format("[Training] Image folder not selected"))
            return
        if not label_csv:
            self._append_log(log_format("[Training] Label CSV not selected"))
            return

        out_dir = self.training_control_panel.get_save_path()

        # Compose training config from settings with performance optimizations
        train_cfg = {
            "epochs": 10,
            "lr": 1e-3,
            "batch_size": self.configuration.get("batch_size", 16),  # Optimized default
            "image_size": self.configuration.get("image_size", 224),
            "model_name": "efficientnet_b4",
            "use_gpu": self.configuration.get("use_gpu", True),
            # Performance optimizations
            "num_workers": self.configuration.get("num_workers", 4),
            "pin_memory": self.configuration.get("pin_memory", True),
            "persistent_workers": self.configuration.get("persistent_workers", True),
            "use_amp": self.configuration.get("use_amp", True),  # Automatic Mixed Precision
            "compile_model": self.configuration.get(
                "compile_model", True
            ),  # PyTorch 2.0 compilation (enabled by default)
            "gradient_accumulation_steps": self.configuration.get(
                "gradient_accumulation_steps", 2
            ),  # Gradient accumulation
            "early_stopping_patience": self.configuration.get(
                "early_stopping_patience", 5
            ),  # Early stopping
        }

        # Update UI state
        self.training_pipeline_panel.set_current_sample(self.current_sample_id)
        self.training_pipeline_panel.set_current_step(step)
        self.training_pipeline_panel.set_step_running(step, True)
        self.training_pipeline_panel.update_progress(step, 0)
        self._append_log(
            log_format(
                f"[Training] Starting training: images={image_folder}, labels={label_csv}, out_dir={out_dir}"
            )
        )

        # Launch training through controller
        self.controller.run_training(
            self.current_sample_id, image_folder, label_csv, out_dir, config=train_cfg
        )

    def _is_processing_active(self):
        """Check if any processing steps are currently active"""
        # Check if any steps are running in the pipeline panel
        if hasattr(self.pipeline_panel, "_running_steps") and self.pipeline_panel._running_steps:
            return True

        # Check if batch processing is active
        if (
            hasattr(self.pipeline_panel, "_is_batch_processing")
            and self.pipeline_panel._is_batch_processing
        ):
            return True

        # Check if any workers are active in the controller
        if hasattr(self.controller, "active_workers") and self.controller.active_workers:
            return True

        return False

    def _stop_current_processing(self):
        """Stop all current processing activities"""
        # Stop all running steps in pipeline panel
        if hasattr(self.pipeline_panel, "_running_steps") and self.pipeline_panel._running_steps:
            for step in list(self.pipeline_panel._running_steps):
                self.controller.cancel_step(step)
                self.pipeline_panel.set_step_running(step, False)

        # Stop batch processing if active
        if (
            hasattr(self.pipeline_panel, "_is_batch_processing")
            and self.pipeline_panel._is_batch_processing
        ):
            self.pipeline_panel._is_batch_processing = False
            self._append_log(log_format("[Pipeline] Batch processing stopped"))

        # Stop any active workers in controller
        if hasattr(self.controller, "active_workers") and self.controller.active_workers:
            for worker in self.controller.active_workers.values():
                worker.request_cancel()

        # Reset sample status to idle
        try:
            self.file_tree_panel.set_sample_status(self.current_sample_id, "idle")
        except Exception:
            pass

        # Reset pipeline state
        self.pipeline_panel._set_state("Idle")
        self.pipeline_panel.reset_all_progress()

    def showEvent(self, event):
        """Override showEvent to ensure Windows taskbar icon is properly set"""
        super().showEvent(event)

        # Apply Windows-specific icon handling after window is shown
        if hasattr(self, "_icon_path") and self._icon_path.exists():
            try:
                from cgt_cell_analysis_demo.app import _set_windows_taskbar_icon

                _set_windows_taskbar_icon(self.winId(), self._icon_path)
            except Exception:
                pass
