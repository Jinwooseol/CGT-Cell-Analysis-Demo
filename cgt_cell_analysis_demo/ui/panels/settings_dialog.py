from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    """Settings dialog with a left navigation list and stacked pages.

    Pages:
      - Reference Map: Sensor Map, Marker 7x7, Marker 5x5, Well Position
      - AI Models: Single model path selection for now
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(1000, 600)
        self._build_ui()

    def _build_ui(self):
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Content area (horizontal splitter)
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Left sidebar
        left_sidebar = self._create_left_sidebar()
        content_layout.addWidget(left_sidebar)

        # Right content area
        right_content = self._create_right_content()
        content_layout.addWidget(right_content, 1)

        main_layout.addLayout(content_layout)

        # Bottom buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

    def _create_left_sidebar(self):
        """Create left sidebar with filter and categories"""
        sidebar = QWidget()
        sidebar.setFixedWidth(250)
        sidebar.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                border-right: 1px solid #d0d0d0;
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Filter section
        filter_frame = QFrame()
        filter_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-bottom: 1px solid #d0d0d0;
            }
        """)
        filter_layout = QVBoxLayout(filter_frame)
        filter_layout.setContentsMargins(10, 10, 10, 10)

        filter_label = QLabel("Filter")
        filter_label.setFont(QFont("Arial", 9, QFont.Bold))
        filter_layout.addWidget(filter_label)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Search settings...")
        self.filter_edit.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
            }
        """)
        filter_layout.addWidget(self.filter_edit)

        layout.addWidget(filter_frame)

        # Categories list
        self.categories_list = QListWidget()
        self.categories_list.setFocusPolicy(Qt.NoFocus)
        self.categories_list.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: transparent;
            }
            QListWidget::item {
                padding: 8px 12px;
                border: none;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #e1e1e1;
            }
        """)

        # Add categories
        categories = ["Reference Map", "AI Models", "Cell Counting"]
        for category in categories:
            item = QListWidgetItem(category)
            item.setFont(QFont("Arial", 9))
            self.categories_list.addItem(item)

        layout.addWidget(self.categories_list)

        return sidebar

    def _create_right_content(self):
        """Create right content area with stacked pages"""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked widget for pages
        self.pages = QStackedWidget()
        layout.addWidget(self.pages)

        # Reference Map page
        ref_page = self._create_reference_map_page()
        self.pages.addWidget(ref_page)

        # AI Models page
        ai_page = self._create_ai_models_page()
        self.pages.addWidget(ai_page)

        # Cell Counting page
        cell_counting_page = self._create_cell_counting_page()
        self.pages.addWidget(cell_counting_page)

        # Connect navigation
        self.categories_list.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.categories_list.setCurrentRow(0)

        return content

    def _create_reference_map_page(self):
        """Create Reference Map settings page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Title
        title = QLabel("Reference Map")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)

        # Reference files group
        ref_group = QGroupBox("Reference Files")
        ref_group.setFont(QFont("Arial", 10, QFont.Bold))
        ref_layout = QFormLayout(ref_group)
        ref_layout.setSpacing(15)

        self.ed_sensor_map = QLineEdit()
        self.ed_marker_7x7 = QLineEdit()
        self.ed_marker_5x5 = QLineEdit()
        self.ed_well_csv = QLineEdit()

        btn_sensor = QPushButton("Browse")
        btn_marker77 = QPushButton("Browse")
        btn_marker55 = QPushButton("Browse")
        btn_well = QPushButton("Browse")

        btn_sensor.clicked.connect(lambda: self._pick_file(self.ed_sensor_map))
        btn_marker77.clicked.connect(lambda: self._pick_file(self.ed_marker_7x7))
        btn_marker55.clicked.connect(lambda: self._pick_file(self.ed_marker_5x5))
        btn_well.clicked.connect(lambda: self._pick_file(self.ed_well_csv))

        ref_layout.addRow("Sensor Map (TIF)", self._with_btn(self.ed_sensor_map, btn_sensor))
        ref_layout.addRow("Marker 7x7 (CSV)", self._with_btn(self.ed_marker_7x7, btn_marker77))
        ref_layout.addRow("Marker 5x5 (CSV)", self._with_btn(self.ed_marker_5x5, btn_marker55))
        ref_layout.addRow("Well Position (CSV)", self._with_btn(self.ed_well_csv, btn_well))

        layout.addWidget(ref_group)
        layout.addStretch()

        return page

    def _create_ai_models_page(self):
        """Create AI Models settings page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Title
        title = QLabel("AI Models")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)

        # AI Model group
        ai_group = QGroupBox("Model Configuration")
        ai_group.setFont(QFont("Arial", 10, QFont.Bold))
        ai_layout = QFormLayout(ai_group)
        ai_layout.setSpacing(15)

        self.ed_ai_model = QLineEdit()
        btn_model = QPushButton("Browse")
        btn_model.clicked.connect(lambda: self._pick_file(self.ed_ai_model))
        ai_layout.addRow("AI Model (ONNX/Torch/PTH)", self._with_btn(self.ed_ai_model, btn_model))

        layout.addWidget(ai_group)
        layout.addStretch()

        return page

    def _create_cell_counting_page(self):
        """Create Cell Counting settings page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Title
        title = QLabel("Cell Counting")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)

        # Processing settings group
        processing_group = QGroupBox("Processing Settings")
        processing_group.setFont(QFont("Arial", 10, QFont.Bold))
        processing_layout = QFormLayout(processing_group)
        processing_layout.setSpacing(15)

        self.ed_batch_size = QLineEdit()
        self.ed_confidence_threshold = QLineEdit()
        self.ed_image_size = QLineEdit()
        self.ed_num_workers = QLineEdit()
        self.cb_use_gpu = QCheckBox("Use GPU")
        self.cb_use_gpu.setChecked(True)
        self.cb_use_half_precision = QCheckBox("Use Half Precision (FP16)")
        self.cb_use_half_precision.setChecked(True)

        processing_layout.addRow("Batch Size", self.ed_batch_size)
        processing_layout.addRow("Confidence Threshold", self.ed_confidence_threshold)
        processing_layout.addRow("Image Size", self.ed_image_size)
        processing_layout.addRow("Number of Workers", self.ed_num_workers)
        processing_layout.addRow("", self.cb_use_gpu)
        processing_layout.addRow("", self.cb_use_half_precision)

        layout.addWidget(processing_group)

        # (Excel option removed; CSV is always saved by the worker)
        layout.addStretch()

        return page

    def _with_btn(self, line: QLineEdit, btn: QPushButton) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        h.addWidget(line)
        h.addWidget(btn)
        return w

    def _pick_file(self, target: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*.*)")
        if path:
            target.setText(path)

    def set_configuration(self, cfg: dict):
        # Use provided configuration or defaults
        self.ed_sensor_map.setText(cfg.get("sensor_map", ""))
        self.ed_marker_7x7.setText(cfg.get("marker_7x7", ""))
        self.ed_marker_5x5.setText(cfg.get("marker_5x5", ""))
        self.ed_well_csv.setText(cfg.get("well_csv", ""))
        self.ed_ai_model.setText(cfg.get("ai_model_weights_path", ""))

        # Cell counting settings
        self.ed_batch_size.setText(str(cfg.get("batch_size", 64)))
        self.ed_confidence_threshold.setText(str(cfg.get("confidence_threshold", 0.5)))
        self.ed_image_size.setText(str(cfg.get("image_size", 224)))
        self.ed_num_workers.setText(str(cfg.get("num_workers", 4)))
        self.cb_use_gpu.setChecked(cfg.get("use_gpu", True))
        self.cb_use_half_precision.setChecked(cfg.get("use_half_precision", True))

        # (Excel option removed; no output format settings)

    def get_configuration(self) -> dict:
        return {
            "sensor_map": self.ed_sensor_map.text(),
            "marker_7x7": self.ed_marker_7x7.text(),
            "marker_5x5": self.ed_marker_5x5.text(),
            "well_csv": self.ed_well_csv.text(),
            "ai_model_weights_path": self.ed_ai_model.text(),
            "batch_size": int(self.ed_batch_size.text() or 64),
            "confidence_threshold": float(self.ed_confidence_threshold.text() or 0.5),
            "image_size": int(self.ed_image_size.text() or 224),
            "num_workers": int(self.ed_num_workers.text() or 4),
            "use_gpu": self.cb_use_gpu.isChecked(),
            "use_half_precision": self.cb_use_half_precision.isChecked(),
        }
