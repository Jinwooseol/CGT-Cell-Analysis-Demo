from pathlib import Path

from PySide6.QtCore import QEvent, QModelIndex, QSize, Qt, QThread, Signal
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHeaderView,
    QMenu,
    QSizePolicy,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cgt_cell_analysis_demo import __resource_path__
from cgt_cell_analysis_demo.util.logger import log_format


class BaseFileLoadingWorker(QThread):
    """Base background thread worker for file loading operations"""

    finished = Signal()
    error = Signal(str)

    def __init__(self, file_tree_panel, path):
        super().__init__()
        self.file_tree_panel = file_tree_panel
        self.path = path

    def run(self):
        """Run the file loading operation in background thread"""
        try:
            # Perform the file loading operations
            self.file_tree_panel._add_folder_to_tree(self.path)
            self.file_tree_panel._search_files_recursively(self.path)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class BaseFileTreePanel(QWidget):
    """Base class for file tree panels with common functionality"""

    # Signals
    log = Signal(str)
    files_found = Signal(list)  # Emit list of found files when search completes
    samples_found = Signal(list)  # Emit list of found samples when search completes
    sample_selected = Signal(dict)  # Emit sample data when a sample is selected
    image_selected = Signal(str, Path)  # Emit panel type and image path when an image is selected
    loading_started = Signal(str)  # Emit when file loading starts
    loading_finished = Signal()  # Emit when file loading finishes

    def __init__(self, panel_type="Processing"):
        super().__init__()
        self.panel_type = panel_type
        self.setAcceptDrops(True)
        # Make the file tree panel flexible
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Map sample_id/name to the corresponding top-level tree item
        self.sample_items: dict[str, QTreeWidgetItem] = {}
        # Store found samples for later retrieval
        self.current_samples: list = []
        # Background worker for file loading
        self.file_loading_worker = None
        self.setup_ui()

    def setup_ui(self):
        """Setup the UI components - to be overridden by subclasses"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)  # Reduce margins
        layout.setSpacing(0)  # Reduce spacing

        # Toolbar
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

        # Add folder action
        add_folder_action = QAction(
            QIcon(str((__resource_path__ / "icn_add_folder.svg").resolve())), "", self
        )
        add_folder_action.setToolTip(self._get_add_folder_tooltip())
        add_folder_action.triggered.connect(self._add_folder)
        toolbar.addAction(add_folder_action)

        layout.addWidget(toolbar)

        # Tree widget
        self.tree = QTreeWidget()
        # Set header labels based on panel type
        if self.panel_type == "Training":
            self.tree.setHeaderLabels(["Name", "Type", "Path", "Label"])
        else:
            self.tree.setHeaderLabels(["Name", "Type", "Path"])
        self.tree.setDragDropMode(QAbstractItemView.DropOnly)
        self.tree.setAcceptDrops(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)

        # Set custom styling for selection
        self.tree.setStyleSheet("""
            QTreeWidget::item:selected {
                background-color: #0066CC;
                color: white;
            }
            QTreeWidget::item:hover {
                background-color: #0066CC;
                color: white;
            }
            QTreeWidget::item:selected:active {
                background-color: #004499;
                color: white;
            }
        """)

        # Configure header
        header = self.tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)

        layout.addWidget(self.tree)

        # Connect signals
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemSelectionChanged.connect(self._on_item_selection_changed)
        # Install event filter on the viewport to detect clicks on empty space
        self.tree.viewport().installEventFilter(self)

        # Enable context menu
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)

    def _get_add_folder_tooltip(self):
        """Get the tooltip text for add folder button - to be overridden"""
        return "Add Folder"

    def _get_dialog_title(self):
        """Get the dialog title for folder selection - to be overridden"""
        return "Select Folder"

    def _get_loading_message(self, path_name):
        """Get the loading message - to be overridden"""
        return f"Loading files from {path_name}..."

    def _get_sample_type_text(self):
        """Get the sample type text - to be overridden"""
        return "Sample"

    def _get_context_menu_text(self):
        """Get the context menu text - to be overridden"""
        return "New Folder"

    def _get_remove_tooltip(self):
        """Get the remove tooltip text - to be overridden"""
        return "Select a sample to remove from tree"

    def _get_clear_message(self):
        """Get the clear selection message - to be overridden"""
        return "File tree selection cleared"

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.is_dir():
                        self._start_file_loading(path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self._get_dialog_title())
        if folder:
            path = Path(folder)
            self._start_file_loading(path)

    def _start_file_loading(self, path: Path):
        """Start file loading in background thread"""
        # Clean up any existing worker
        if self.file_loading_worker and self.file_loading_worker.isRunning():
            self.file_loading_worker.terminate()
            self.file_loading_worker.wait()

        # Emit loading started signal BEFORE starting the operation
        self.loading_started.emit(self._get_loading_message(path.name))

        # Create and start background worker
        self.file_loading_worker = self._create_loading_worker(path)
        self.file_loading_worker.finished.connect(self._on_file_loading_finished)
        self.file_loading_worker.error.connect(self._on_file_loading_error)
        self.file_loading_worker.start()

    def _create_loading_worker(self, path: Path):
        """Create the appropriate loading worker - to be overridden"""
        return BaseFileLoadingWorker(self, path)

    def _on_file_loading_finished(self):
        """Handle file loading completion"""
        self.loading_finished.emit()
        self.file_loading_worker = None

    def _on_file_loading_error(self, error_msg: str):
        """Handle file loading error"""
        self.log.emit(log_format(f"Error loading files: {error_msg}"))
        self.loading_finished.emit()
        self.file_loading_worker = None

    def _add_folder_to_tree(self, path: Path):
        """Add a folder to the tree widget - to be overridden by subclasses"""
        raise NotImplementedError("Subclasses must implement _add_folder_to_tree")

    def _search_files_recursively(self, root_path: Path):
        """Search for samples - to be overridden by subclasses"""
        raise NotImplementedError("Subclasses must implement _search_files_recursively")

    def _add_sample_to_tree(self, parent_item: QTreeWidgetItem, sample_path: Path):
        """Add a single sample to the tree"""
        if parent_item is None:
            # Add directly to tree root
            sample_item = QTreeWidgetItem(self.tree)
        else:
            # Add as child of parent
            sample_item = QTreeWidgetItem(parent_item)

        sample_item.setText(0, sample_path.name)
        sample_item.setText(1, self._get_sample_type_text())
        sample_item.setText(2, str(sample_path))
        sample_item.setData(0, Qt.UserRole, str(sample_path))

        # Add label data for training panels
        if self.panel_type == "Training":
            labels = self._load_labels_from_csv(sample_path)
            if labels:
                # Show count of labels found
                label_count = len(labels)
                sample_item.setText(3, f"{label_count} labels")
            else:
                sample_item.setText(3, "No labels")

        # Register for status coloring
        try:
            self.sample_items[sample_path.name] = sample_item
        except Exception:
            pass

        # Add sample-specific data - to be overridden
        self._add_sample_data(sample_item, sample_path)

        # Expand sample item
        sample_item.setExpanded(False)

    def _add_sample_data(self, sample_item: QTreeWidgetItem, sample_path: Path):
        """Add sample-specific data - to be overridden by subclasses"""
        pass

    def set_sample_status(self, sample_id: str, status: str):
        """Set the visual status color of a sample item.
        status: 'processing' | 'done' | 'idle'
        """
        item = self.sample_items.get(sample_id)
        if not item:
            return
        color = None
        s = (status or "").lower()
        if s == "processing":
            color = QColor("#ff9800")  # Orange
        elif s == "done":
            color = QColor("#2e7d32")  # Green
        else:
            color = QColor("#000000")  # Black
        # Apply to name column
        item.setForeground(0, color)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        """Handle double click on tree item"""
        path = item.data(0, Qt.UserRole)
        if path:
            self.log.emit(log_format(f"Selected: {path}"))

    def _on_item_selection_changed(self):
        """Handle item selection change"""
        current_item = self.tree.currentItem()
        if current_item and self._is_sample_item(current_item):
            self._handle_sample_selection(current_item)
        elif self._is_image_item(current_item):
            self._handle_image_selection(current_item)
        else:
            # Clear pipeline inputs when non-sample is selected
            self._clear_pipeline_inputs()

    def _handle_sample_selection(self, item: QTreeWidgetItem):
        """Handle when a sample is selected - to be overridden by subclasses"""
        raise NotImplementedError("Subclasses must implement _handle_sample_selection")

    def _handle_image_selection(self, item: QTreeWidgetItem):
        """Handle when an image is selected - to be overridden by subclasses"""
        raise NotImplementedError("Subclasses must implement _handle_image_selection")

    def _clear_pipeline_inputs(self):
        """Clear all pipeline inputs when non-sample is selected - to be overridden"""
        raise NotImplementedError("Subclasses must implement _clear_pipeline_inputs")

    def _is_sample_item(self, item: QTreeWidgetItem) -> bool:
        """Check if the item represents a sample - to be overridden by subclasses"""
        raise NotImplementedError("Subclasses must implement _is_sample_item")

    def _is_image_item(self, item: QTreeWidgetItem) -> bool:
        """Check if the item represents an image - to be overridden by subclasses"""
        raise NotImplementedError("Subclasses must implement _is_image_item")

    def _is_folder_already_in_tree(self, path: Path) -> bool:
        """Check if a folder is already in the tree"""

        def check_item(item):
            if item is None:
                return False

            item_path = item.data(0, Qt.UserRole)
            if item_path and Path(item_path) == path:
                return True

            # Check children
            for i in range(item.childCount()):
                if check_item(item.child(i)):
                    return True

            return False

        # Check all top-level items
        for i in range(self.tree.topLevelItemCount()):
            if check_item(self.tree.topLevelItem(i)):
                return True

        return False

    def _show_context_menu(self, position):
        """Show context menu at the specified position"""
        item = self.tree.itemAt(position)

        # Create context menu
        context_menu = QMenu(self)

        # New Folder action
        new_folder_action = QAction(f"📁 {self._get_context_menu_text()}", self)
        new_folder_action.triggered.connect(self._add_folder)
        context_menu.addAction(new_folder_action)

        context_menu.addSeparator()

        # Remove action (only enabled when a sample is selected)
        remove_action = QAction("❌ Remove from Tree", self)
        remove_action.triggered.connect(self._delete_selected_item)

        # Enable remove for sample items
        if item and self._is_sample_item(item):
            remove_action.setEnabled(True)
            remove_action.setToolTip(f"Remove '{item.text(0)}' from tree")
        else:
            remove_action.setEnabled(False)
            remove_action.setToolTip(self._get_remove_tooltip())

        context_menu.addAction(remove_action)

        # Show context menu
        context_menu.exec(self.tree.mapToGlobal(position))

    def _delete_selected_item(self):
        """Remove the currently selected sample item from the tree (no file deletion)"""
        current_item = self.tree.currentItem()
        if not current_item:
            self.log.emit(log_format("Nothing selected for removal"))
            return

        is_sample = self._is_sample_item(current_item)
        if not is_sample:
            self.log.emit(log_format(self._get_remove_tooltip()))
            return

        name = current_item.text(0)

        # Confirm removal from tree
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Remove from Tree",
            f"Remove sample '{name}' from the file tree?\n\nThis will only remove it from the list, not delete the actual files.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                parent = current_item.parent()
                if parent:
                    parent.removeChild(current_item)
                else:
                    self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(current_item))

                self.log.emit(log_format(f"Removed sample '{name}' from file tree"))

            except Exception as e:
                self.log.emit(log_format(f"Error removing sample '{name}' from tree: {str(e)}"))

    def get_current_samples(self):
        """Get the list of currently found samples in the order they appear in the tree"""
        # Ensure samples are always sorted alphabetically to match tree order
        if self.current_samples:
            # Sort by sample_id to ensure consistent ordering
            sorted_samples = sorted(self.current_samples, key=lambda x: x.get("sample_id", ""))
            return sorted_samples
        return self.current_samples

    def get_samples_in_tree_order(self):
        """Get samples in the order they appear in the file tree (top to bottom)"""
        # Get samples from the tree in the order they appear
        samples_in_order = []

        # Iterate through the tree items in order
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item:
                # Check if this is a sample item by looking at the type column
                item_type = item.text(1) if item.columnCount() > 1 else ""
                if item_type == "Sample":
                    sample_id = item.text(0)  # Sample name
                    # Find the corresponding sample data
                    for sample in self.current_samples:
                        if sample.get("sample_id") == sample_id:
                            samples_in_order.append(sample)
                            break
                elif item_type == "Root":
                    # This is a root item, get its children
                    for j in range(item.childCount()):
                        child_item = item.child(j)
                        if child_item:
                            child_type = child_item.text(1) if child_item.columnCount() > 1 else ""
                            if child_type == "Sample":
                                sample_id = child_item.text(0)  # Sample name
                                # Find the corresponding sample data
                                for sample in self.current_samples:
                                    if sample.get("sample_id") == sample_id:
                                        samples_in_order.append(sample)
                                        break

        # If no samples found in tree order, fall back to current_samples
        if not samples_in_order and self.current_samples:
            self.log.emit(
                log_format("Warning: Could not get samples in tree order, using current_samples")
            )
            return self.current_samples

        return samples_in_order

    def eventFilter(self, obj, event):
        """Handle events for the tree widget"""
        if obj == self.tree.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            # Check if click is on empty space (no item under cursor)
            item = self.tree.itemAt(event.pos())
            if item is None:
                # Clicked on empty space - clear selection
                self.tree.clearSelection()
                # Also clear the current index to ensure no item remains current
                try:
                    self.tree.setCurrentIndex(QModelIndex())
                except Exception:
                    pass
                self._clear_pipeline_inputs()
                self.log.emit(log_format(self._get_clear_message()))
                return True  # Event handled
        return super().eventFilter(obj, event)
