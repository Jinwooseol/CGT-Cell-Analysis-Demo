from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QFont, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cgt_cell_analysis_demo.util.logger import log_format


class DraggableLabel(QLabel):
    """Custom label that supports drag-to-pan functionality"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dragging = False
        self.last_pan_point = QPoint()
        self.pan_offset = QPoint(0, 0)
        self.preview_panel = None
        self.setMouseTracking(True)

    def set_preview_panel(self, panel):
        """Set reference to the preview panel for callbacks"""
        self.preview_panel = panel

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for drag start"""
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.last_pan_point = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for dragging"""
        if self.dragging and event.buttons() & Qt.LeftButton:
            # Calculate the drag delta (mouse movement)
            delta = event.pos() - self.last_pan_point
            self.last_pan_point = event.pos()

            # Update pan offset directly (1:1 mapping with mouse movement)
            self.pan_offset += delta

            # Update the image display through the preview panel
            if self.preview_panel:
                self.preview_panel.pan_offset = self.pan_offset
                self.preview_panel._update_image_with_pan()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release to stop dragging"""
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def reset_pan(self):
        """Reset pan offset"""
        self.pan_offset = QPoint(0, 0)
        if self.preview_panel:
            self.preview_panel.pan_offset = self.pan_offset

    def wheelEvent(self, event: QWheelEvent):
        """Handle wheel events for zooming"""
        if self.preview_panel:
            self.preview_panel.wheelEvent(event)
        else:
            super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to reset zoom"""
        if self.preview_panel:
            self.preview_panel.mouseDoubleClickEvent(event)
        else:
            super().mouseDoubleClickEvent(event)


class PreviewPanel(QWidget):
    log = Signal(str)

    def __init__(self, title="Preview"):
        super().__init__()
        self.title = title
        self.current_file = None
        self.zoom_level = 100
        self.current_sample_data = None
        self.optical_images = []
        self.current_tile_index = 0
        self.zoom_with_ctrl = True  # Set to False for direct wheel zooming

        # Pan offset for image positioning
        self.pan_offset = QPoint(0, 0)

        # Flag to prevent recursive calls
        self._updating_combo = False

        # Make the preview panel flexible with gradual shrinking
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(150, 100)  # Set minimum size for gradual shrinking
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)  # No margins
        layout.setSpacing(5)  # Reduce spacing

        # Add clean panel styling
        self.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
            }
        """)

        # Title label
        title_label = QLabel(self.title)
        title_label.setFont(QFont("Arial", 9, QFont.Bold))
        layout.addWidget(title_label)

        # Toolbar
        toolbar_layout = QHBoxLayout()

        # Zoom controls
        zoom_out_btn = QPushButton("🔍-")
        zoom_out_btn.setToolTip("Zoom Out")
        zoom_out_btn.clicked.connect(self._zoom_out)
        toolbar_layout.addWidget(zoom_out_btn)

        zoom_in_btn = QPushButton("🔍+")
        zoom_in_btn.setToolTip("Zoom In")
        zoom_in_btn.clicked.connect(self._zoom_in)
        toolbar_layout.addWidget(zoom_in_btn)

        self.resolution_combo = QComboBox()
        self.resolution_combo.setEditable(True)  # Allow custom text display
        self.resolution_combo.setMinimumWidth(70)
        self.resolution_combo.setInsertPolicy(QComboBox.NoInsert)  # Don't add custom items to list
        self.resolution_combo.addItems(["100%", "80%", "50%", "25%", "10%", "5%", "2%", "1%"])
        self.resolution_combo.setCurrentText("100%")
        self.resolution_combo.currentTextChanged.connect(self._on_resolution_changed)
        toolbar_layout.addWidget(self.resolution_combo)

        toolbar_layout.addStretch()

        # Navigation controls
        self.prev_btn = QPushButton(" ◀ ")
        self.prev_btn.setToolTip("Previous")
        self.prev_btn.clicked.connect(self._previous)
        self.prev_btn.setVisible(False)
        toolbar_layout.addWidget(self.prev_btn)

        self.next_btn = QPushButton(" ▶ ")
        self.next_btn.setToolTip("Next")
        self.next_btn.clicked.connect(self._next)
        self.next_btn.setVisible(False)
        toolbar_layout.addWidget(self.next_btn)

        toolbar_layout.addStretch()

        # Tile selection combo (for optical images)
        self.tile_combo = QComboBox()
        self.tile_combo.setMinimumWidth(100)
        self.tile_combo.currentTextChanged.connect(self._on_tile_changed)
        self.tile_combo.setVisible(False)
        toolbar_layout.addWidget(self.tile_combo)

        layout.addLayout(toolbar_layout)

        # Preview area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(200)
        self.scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Preview widget
        self.preview_widget = DraggableLabel()
        self.preview_widget.setAlignment(Qt.AlignCenter)
        self.preview_widget.setMinimumSize(400, 300)
        self.preview_widget.setToolTip(
            "Mouse wheel: Zoom in/out (Ctrl+wheel or direct wheel depending on settings)\nDouble-click: Reset zoom to 100%\nDrag: Pan around the image"
        )
        self.preview_widget.set_preview_panel(self)  # Set reference to this panel
        self.preview_widget.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                border: 1px solid #cccccc;
            }
        """)

        # Draw grid pattern
        self._draw_grid_pattern()

        self.scroll_area.setWidget(self.preview_widget)
        layout.addWidget(self.scroll_area)

    def _draw_grid_pattern(self):
        """Draw a subtle grid pattern on the preview widget"""
        pixmap = QPixmap(400, 300)
        pixmap.fill(Qt.white)

        painter = QPainter(pixmap)
        painter.setPen(QPen(Qt.lightGray, 1))

        # Draw grid
        for x in range(0, 400, 20):
            painter.drawLine(x, 0, x, 300)
        for y in range(0, 300, 20):
            painter.drawLine(0, y, 400, y)

        painter.end()

        self.preview_widget.setPixmap(pixmap)

    def load_file(self, file_path: str):
        """Load a file for preview"""
        self.current_file = file_path
        # Reset pan offset when loading new file
        self.pan_offset = QPoint(0, 0)
        self.preview_widget.reset_pan()
        path = Path(file_path)

        if path.suffix.lower() in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"]:
            self._load_image(file_path)
        else:
            self._show_placeholder(f"File: {path.name}")

    def _load_image(self, file_path: str):
        """Load and display an image"""
        try:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                # Scale based on zoom level
                scaled_pixmap = self._scale_pixmap(pixmap)
                # Apply pan offset if dragging
                if not self.pan_offset.isNull():
                    panned_pixmap = self._apply_pan_to_pixmap(scaled_pixmap)
                    self.preview_widget.setPixmap(panned_pixmap)
                else:
                    self.preview_widget.setPixmap(scaled_pixmap)
            else:
                self._show_placeholder("Invalid image file")
        except Exception as e:
            self._show_placeholder(f"Error loading image: {e}")

    def _scale_pixmap(self, pixmap: QPixmap):
        """Scale pixmap based on current zoom level"""
        if self.zoom_level == 100:
            self._original_scaled_pixmap = pixmap
            return pixmap

        scale_factor = self.zoom_level / 100.0
        new_size = pixmap.size() * scale_factor
        scaled_pixmap = pixmap.scaled(new_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._original_scaled_pixmap = scaled_pixmap
        return scaled_pixmap

    def _show_placeholder(self, text: str):
        """Show placeholder text"""
        pixmap = QPixmap(400, 300)
        pixmap.fill(Qt.lightGray)

        painter = QPainter(pixmap)
        painter.setPen(Qt.black)
        painter.setFont(QFont("Arial", 12))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()

        self.preview_widget.setPixmap(pixmap)

    def _zoom_in(self, mouse_pos=None):
        """Zoom in, optionally centered on mouse position"""
        old_zoom = self.zoom_level

        if self.zoom_level < 10:
            self.zoom_level = min(self.zoom_level + 1, 10)
        elif self.zoom_level < 50:
            self.zoom_level = min(self.zoom_level + 5, 50)
        else:
            self.zoom_level = min(self.zoom_level + 10, 400)

        self._update_zoom_with_center(mouse_pos, old_zoom)

    def _zoom_out(self, mouse_pos=None):
        """Zoom out, optionally centered on mouse position"""
        old_zoom = self.zoom_level

        if self.zoom_level <= 10:
            self.zoom_level = max(self.zoom_level - 1, 1)
        elif self.zoom_level <= 50:
            self.zoom_level = max(self.zoom_level - 5, 1)
        else:
            self.zoom_level = max(self.zoom_level - 10, 1)

        self._update_zoom_with_center(mouse_pos, old_zoom)

    def _update_zoom_with_center(self, mouse_pos, old_zoom):
        """Update zoom with optional mouse-centered positioning"""
        # Update the zoom display first (prevent recursion)
        self._updating_combo = True
        custom_text = f"{self.zoom_level}%"
        self.resolution_combo.setCurrentText(custom_text)
        self._updating_combo = False

        if mouse_pos is not None and self.current_file and self.preview_widget.pixmap():
            # Calculate the zoom factor
            zoom_factor = self.zoom_level / old_zoom if old_zoom > 0 else 1.0

            if zoom_factor != 1.0:  # Only adjust if zoom actually changed
                # Get widget size and center
                widget_size = self.preview_widget.size()
                widget_center = QPoint(widget_size.width() // 2, widget_size.height() // 2)

                # Calculate the offset from widget center to mouse position
                offset_from_center = mouse_pos - widget_center

                # Calculate the adjustment needed to keep the mouse point stationary
                # When zooming in (factor > 1), we need to move the image more
                # When zooming out (factor < 1), we need to move the image less
                adjustment_x = int(offset_from_center.x() * (1.0 - zoom_factor))
                adjustment_y = int(offset_from_center.y() * (1.0 - zoom_factor))

                # Update the pan offset
                self.pan_offset = QPoint(
                    self.pan_offset.x() + adjustment_x, self.pan_offset.y() + adjustment_y
                )

        # Refresh the image display without resetting pan offset
        if self.current_file:
            self._refresh_image_display()

    def _refresh_image_display(self):
        """Refresh the image display while preserving pan offset"""
        if not self.current_file:
            return

        path = Path(self.current_file)
        if path.suffix.lower() in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"]:
            self._load_image(self.current_file)
        else:
            self._show_placeholder(f"File: {path.name}")

    def _update_zoom(self):
        """Update zoom display and refresh preview"""
        # Reset pan offset when zoom changes
        self.pan_offset = QPoint(0, 0)
        self.preview_widget.reset_pan()

        custom_text = f"{self.zoom_level}%"
        self.resolution_combo.setCurrentText(custom_text)

        if self.current_file:
            self._refresh_image_display()

    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel events for zooming"""
        # Check if we should zoom with Ctrl key or directly
        should_zoom = False

        if self.zoom_with_ctrl:
            # Zoom only when Ctrl key is pressed
            should_zoom = event.modifiers() & Qt.ControlModifier
        else:
            # Always zoom with wheel (when over the preview area)
            should_zoom = True

        if should_zoom:
            # Get the wheel delta (positive for zoom in, negative for zoom out)
            delta = event.angleDelta().y()

            # Get mouse position relative to the preview widget
            mouse_pos = event.position().toPoint()

            if delta > 0:
                # Zoom in centered on mouse position
                self._zoom_in(mouse_pos)
            else:
                # Zoom out centered on mouse position
                self._zoom_out(mouse_pos)

            # Accept the event to prevent it from being passed to parent widgets
            event.accept()
        else:
            # If not zooming, let the event be handled normally (scrolling)
            super().wheelEvent(event)

    def _on_resolution_changed(self, resolution: str):
        """Handle resolution change from combo box"""
        if self._updating_combo:
            return  # Prevent recursion when updating programmatically

        if not resolution.endswith("%"):
            return  # Invalid format, ignore

        try:
            self.zoom_level = int(resolution[:-1])
        except ValueError:
            return  # Invalid format, ignore

        # Update zoom without triggering resolution combo change
        self._update_zoom_direct()

    def _update_zoom_direct(self):
        """Update zoom without updating resolution combo (to prevent recursion)"""
        # Reset pan offset when zoom changes
        self.pan_offset = QPoint(0, 0)
        self.preview_widget.reset_pan()

        if self.current_file:
            self._refresh_image_display()

    def _previous(self):
        """Go to previous tile image"""
        if hasattr(self, "tile_numbers") and self.tile_numbers and self.current_tile_index > 0:
            self.current_tile_index -= 1
            self._show_optical_images()
            # Update tile combo to reflect current selection
            if self.current_tile_index < len(self.tile_numbers):
                current_tile = self.tile_numbers[self.current_tile_index]
                self.tile_combo.setCurrentText(str(current_tile))
            # Update button states
            self.prev_btn.setEnabled(self.current_tile_index > 0)
            self.next_btn.setEnabled(self.current_tile_index < len(self.tile_numbers) - 1)

    def _next(self):
        """Go to next tile image"""
        if (
            hasattr(self, "tile_numbers")
            and self.tile_numbers
            and self.current_tile_index < len(self.tile_numbers) - 1
        ):
            self.current_tile_index += 1
            self._show_optical_images()
            # Update tile combo to reflect current selection
            if self.current_tile_index < len(self.tile_numbers):
                current_tile = self.tile_numbers[self.current_tile_index]
                self.tile_combo.setCurrentText(str(current_tile))
            # Update button states
            self.prev_btn.setEnabled(self.current_tile_index > 0)
            self.next_btn.setEnabled(self.current_tile_index < len(self.tile_numbers) - 1)

    def set_image_data(self, image_path: Path):
        """Set the current image data and load the image"""
        self.current_file = image_path
        self._load_image(image_path)
        self.log.emit(log_format(f"Image selected: {image_path}"))

    def set_sample_data(self, sample_data: dict):
        """Set the current sample data and load appropriate images"""
        self.current_sample_data = sample_data
        self._load_sample_images()

    def _load_sample_images(self):
        """Load images based on the current sample data"""
        if not self.current_sample_data:
            self._show_placeholder("No sample selected")
            return

        sample_name = self.current_sample_data.get("sample_name", "")
        optical_folder = self.current_sample_data.get("optical_folder")
        pcr_folder = self.current_sample_data.get("pcr_folder")
        training_folder = self.current_sample_data.get("training_folder")

        self.log.emit(log_format(f"Loading images for sample: {sample_name}"))
        self.log.emit(log_format(f"Optical folder: {optical_folder}"))
        self.log.emit(log_format(f"PCR folder: {pcr_folder}"))
        self.log.emit(log_format(f"Training folder: {training_folder}"))

        # Load images based on panel title
        if "Optical" in self.title:
            # This is the optical images panel
            if optical_folder:
                self._load_optical_images(optical_folder)
                self.log.emit(log_format(f"Loaded {len(self.optical_images)} optical images"))
                if hasattr(self, "tile_numbers"):
                    self.log.emit(log_format(f"Found tiles: {self.tile_numbers}"))
                self._show_optical_images()
            else:
                self._show_placeholder("No optical images available")
        elif "PCR" in self.title:
            # This is the PCR 1cycle image panel
            if pcr_folder:
                self._load_pcr_images(pcr_folder)
                self.log.emit(
                    log_format(f"Well_1cycle path: {getattr(self, 'well_1cycle_path', None)}")
                )
                self._show_pcr_images()
            else:
                self._show_placeholder("No PCR 1cycle image available")
        elif "Training" in self.title:
            # This is the training images panel
            if training_folder:
                self._load_training_images(training_folder)
                self.log.emit(log_format(f"Loaded {len(self.training_images)} training images"))
            else:
                self._show_placeholder("No training images available")
        else:
            # Fallback for other panels
            self._show_placeholder("No content available")

    def _load_training_images(self, training_folder: str):
        """Load training images from the training folder"""
        training_path = Path(training_folder)
        self.training_images = list(training_path.glob("*.png"))

        self.log.emit(log_format(f"Loaded {len(self.training_images)} training images"))

    def _load_optical_images(self, optical_folder: str):
        """Load optical images from the Well_Image directory"""
        # Look for Well_Image directory in the optical folder
        well_image_dir = Path(optical_folder)

        if well_image_dir.exists():
            # Find all PNG files in the Well_Image directory
            image_files = list(well_image_dir.glob("*.bmp"))
            self.optical_images = sorted([str(f) for f in image_files])

            # Group images by tile number (extract from filename pattern)
            self._group_optical_images_by_tile()
        else:
            self.optical_images = []

    def _group_optical_images_by_tile(self):
        """Group optical images by tile number based on filename pattern"""
        self.tile_groups = {}

        for image_path in self.optical_images:
            filename = Path(image_path).name
            # Extract tile number from filename pattern like "Well_1019_6.png"
            # The last number before .png is the tile number
            try:
                parts = filename.replace(".bmp", "").split("_")
                if len(parts) >= 3:
                    tile_number = int(parts[-1])
                    if tile_number not in self.tile_groups:
                        self.tile_groups[tile_number] = []
                    self.tile_groups[tile_number].append(image_path)
            except (ValueError, IndexError):
                # Skip files that don't match the expected pattern
                continue

        # Sort tile numbers
        self.tile_numbers = sorted(self.tile_groups.keys())

    def _load_pcr_images(self, pcr_folder: str):
        """Load PCR well_1cycle image"""
        pcr_path = Path(pcr_folder)

        # Look for well_1cycle.png in the directory
        well_1cycle_path = pcr_path / "well_1cycle.png"
        if well_1cycle_path.exists():
            self.well_1cycle_path = str(well_1cycle_path)
        else:
            # Look in subdirectories
            self.well_1cycle_path = None
            for subdir in pcr_path.iterdir():
                if subdir.is_dir():
                    well_1cycle_path = subdir / "well_1cycle.png"
                    if well_1cycle_path.exists():
                        self.well_1cycle_path = str(well_1cycle_path)
                        break

            # If still not found, look in work directory structure
            if not self.well_1cycle_path:
                work_dir = Path(pcr_folder).parent.parent / "work"
                if work_dir.exists():
                    for sample_dir in work_dir.iterdir():
                        if sample_dir.is_dir():
                            pcr_indexing_dir = sample_dir / "04_pcr_image_indexing"
                            if pcr_indexing_dir.exists():
                                well_1cycle_dir = pcr_indexing_dir / "well_1cycle"
                                if well_1cycle_dir.exists():
                                    well_1cycle_path = well_1cycle_dir / "well_1cycle.png"
                                    if well_1cycle_path.exists():
                                        self.well_1cycle_path = str(well_1cycle_path)
                                        break

    def _on_tile_changed(self, tile_text: str):
        """Handle tile combo change"""
        # Prevent recursive calls
        if self._updating_combo:
            return

        if tile_text and tile_text != "Tile Number":
            try:
                tile_number = int(tile_text)
                if hasattr(self, "tile_numbers") and tile_number in self.tile_numbers:
                    self.current_tile_index = self.tile_numbers.index(tile_number)
                    self._show_optical_images()
            except (ValueError, IndexError):
                pass

    def _show_optical_images(self):
        """Show optical images for the current tile"""
        if not hasattr(self, "tile_numbers") or not self.tile_numbers:
            self._show_placeholder("No optical images available")
            return

        # Show tile combo for optical images
        self._update_tile_combo()
        self.tile_combo.setVisible(True)
        self.prev_btn.setVisible(True)
        self.next_btn.setVisible(True)

        # Update button states based on current position
        self.prev_btn.setEnabled(self.current_tile_index > 0)
        self.next_btn.setEnabled(self.current_tile_index < len(self.tile_numbers) - 1)

        # Set a smaller initial zoom for optical images (they are typically large)
        if self.zoom_level == 100:  # Only if at default zoom
            self.zoom_level = 25  # Start at 25% for optical images
            self.resolution_combo.setCurrentText("25%")

        # Show the first tile by default
        if self.current_tile_index < len(self.tile_numbers):
            tile_number = self.tile_numbers[self.current_tile_index]
            tile_images = self.tile_groups[tile_number]

            if tile_images:
                # Show the first image of the tile
                self.load_file(tile_images[0])
            else:
                self._show_placeholder(f"No images found for tile {tile_number}")
        else:
            self._show_placeholder("No optical images available")

    def _show_pcr_images(self):
        """Show PCR well_1cycle image"""
        # Hide tile combo and label for PCR images
        self.tile_combo.setVisible(False)
        self.prev_btn.setVisible(False)
        self.next_btn.setVisible(False)

        if hasattr(self, "well_1cycle_path") and self.well_1cycle_path:
            self.load_file(self.well_1cycle_path)
        else:
            self._show_placeholder("No PCR well_1cycle image available")

    def set_tile_index(self, tile_index: int):
        """Set the current tile index for optical images"""
        if hasattr(self, "tile_numbers") and 0 <= tile_index < len(self.tile_numbers):
            self.current_tile_index = tile_index
            if self.type_combo.currentText() == "Optical":
                self._show_optical_images()

    def get_available_tiles(self):
        """Get list of available tile numbers"""
        if hasattr(self, "tile_numbers"):
            return self.tile_numbers
        return []

    def set_zoom_with_ctrl(self, use_ctrl: bool):
        """Set whether zoom requires Ctrl key or not"""
        self.zoom_with_ctrl = use_ctrl

    def toggle_zoom_mode(self):
        """Toggle between Ctrl+wheel and direct wheel zooming"""
        self.zoom_with_ctrl = not self.zoom_with_ctrl
        return self.zoom_with_ctrl

    def reset_zoom(self):
        """Reset zoom to 100%"""
        self.zoom_level = 10
        self._update_zoom()

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to reset zoom"""
        self.reset_zoom()
        super().mouseDoubleClickEvent(event)

    def _update_image_with_pan(self):
        """Update the image display with current pan offset"""
        if self.current_file and self.preview_widget.pixmap():
            # Get the original scaled pixmap and apply pan to it
            if hasattr(self, "_original_scaled_pixmap") and self._original_scaled_pixmap:
                panned_pixmap = self._apply_pan_to_pixmap(self._original_scaled_pixmap)
                self.preview_widget.setPixmap(panned_pixmap)
            else:
                # Fallback: apply pan to current pixmap
                current_pixmap = self.preview_widget.pixmap()
                panned_pixmap = self._apply_pan_to_pixmap(current_pixmap)
                self.preview_widget.setPixmap(panned_pixmap)

    def _apply_pan_to_pixmap(self, pixmap: QPixmap):
        """Apply pan offset to a pixmap"""
        if self.pan_offset.isNull():
            return pixmap

        # Create a new pixmap with the same size as the preview widget
        widget_size = self.preview_widget.size()
        result_pixmap = QPixmap(widget_size)
        result_pixmap.fill(Qt.transparent)

        # Create a painter to draw the panned image
        painter = QPainter(result_pixmap)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # Calculate the position to draw the image with pan offset
        # Center the image and apply the pan offset directly
        x = (widget_size.width() - pixmap.width()) // 2 + self.pan_offset.x()
        y = (widget_size.height() - pixmap.height()) // 2 + self.pan_offset.y()

        # Draw the image at the panned position
        painter.drawPixmap(x, y, pixmap)
        painter.end()

        return result_pixmap

    def _update_tile_combo(self):
        """Update the tile combo with available tile numbers"""
        self.tile_combo.clear()

        if hasattr(self, "tile_numbers") and self.tile_numbers:
            self.tile_combo.addItem("Tile Number")
            for tile_number in self.tile_numbers:
                self.tile_combo.addItem(str(tile_number))

            # Set the current tile number if available
            self._updating_combo = True  # Prevent recursive calls
            if hasattr(self, "current_tile_index") and self.current_tile_index < len(
                self.tile_numbers
            ):
                current_tile = self.tile_numbers[self.current_tile_index]
                self.tile_combo.setCurrentText(str(current_tile))
            else:
                self.tile_combo.setCurrentText("Tile Number")
            self._updating_combo = False  # Re-enable calls
        else:
            self._updating_combo = True  # Prevent recursive calls
            self.tile_combo.addItem("No tiles available")
            self.tile_combo.setCurrentText("No tiles available")
            self._updating_combo = False  # Re-enable calls
