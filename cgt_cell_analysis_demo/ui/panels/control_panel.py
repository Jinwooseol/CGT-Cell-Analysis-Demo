from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cgt_cell_analysis_demo import __project_path__


class ControlPanel(QWidget):
    save_clicked = Signal()
    save_path_changed = Signal(str)

    def __init__(self):
        super().__init__()
        # Make the control panel flexible
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # Reduce margins
        layout.setSpacing(0)  # Reduce spacing

        # Main control frame
        control_frame = QFrame()
        control_frame.setFrameStyle(QFrame.Box)
        control_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 0px;
            }
        """)

        control_layout = QVBoxLayout(control_frame)
        control_layout.setContentsMargins(5, 0, 5, 0)  # Slightly more padding
        control_layout.setSpacing(0)  # Slightly more spacing

        # Save path output section with buttons
        save_path_layout = QHBoxLayout()

        # Save Path button
        self.save_path_btn = QPushButton("Save Path")
        self.save_path_btn.setMinimumSize(80, 25)
        self.save_path_btn.setMaximumHeight(25)
        self.save_path_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                padding: 2px 2px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
        """)
        self.save_path_btn.clicked.connect(self._on_save_clicked)
        save_path_layout.addWidget(self.save_path_btn)

        self.save_path_edit = QLineEdit()
        self.save_path_edit.setPlaceholderText("Enter save output path...")
        self.save_path_edit.setText(str(__project_path__ / "work"))
        self.save_path_edit.setMinimumHeight(25)
        self.save_path_edit.setMaximumHeight(25)
        self.save_path_edit.textChanged.connect(self.save_path_changed.emit)
        save_path_layout.addWidget(self.save_path_edit)

        control_layout.addLayout(save_path_layout)

        layout.addWidget(control_frame)

        # Set size policy
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        self.setMinimumHeight(40)
        self.setMaximumHeight(40)

    def get_save_path(self):
        """Get the current save path as absolute path"""
        path_text = self.save_path_edit.text()
        if path_text:
            return str(Path(path_text).resolve())
        return path_text

    def set_save_path(self, path: str):
        """Set the save path"""
        self.save_path_edit.setText(path)

    def get_comment(self):
        """Get the current comment"""
        return self.comment_edit.text()

    def set_comment(self, comment: str):
        """Set the comment"""
        self.comment_edit.setText(comment)

    def _on_save_clicked(self):
        """Handle save button clicked - open directory dialog"""
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            # Convert to absolute path before storing
            absolute_directory = str(Path(directory).resolve())
            self.save_path_edit.setText(absolute_directory)
            self.save_clicked.emit()
