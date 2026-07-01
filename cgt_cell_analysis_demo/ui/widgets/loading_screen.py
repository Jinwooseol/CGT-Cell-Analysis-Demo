from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget

from cgt_cell_analysis_demo.ui.widgets.busy_spinner import BusySpinner


class LoadingScreen(QWidget):
    """
    A general loading screen widget with semi-transparent overlay and loading animation.
    Can be used for any loading activity in the application.

    Usage:
        # Create loading screen (usually done in main window)
        loading_screen = LoadingScreen(parent_widget)

        # Show loading screen with message
        loading_screen.show_loading("Loading files...")

        # Hide loading screen when done
        loading_screen.hide_loading()

        # Check if visible
        if loading_screen.is_visible():
            print("Loading screen is currently visible")
    """

    def __init__(self, parent=None, message="Loading..."):
        super().__init__(parent)
        self._message = message
        self._is_visible = False

        # Set up the widget properties
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        # Create main layout
        self._setup_ui()

        # Set up animation
        self._setup_animation()

        # Initially hidden
        self.hide()

    def _setup_ui(self):
        """Setup the UI components"""
        # Main container widget with rounded corners and background
        self.container = QWidget()
        self.container.setFixedSize(300, 150)
        self.container.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 240);
                border-radius: 15px;
                border: 1px solid rgba(200, 200, 200, 100);
            }
        """)

        # Main layout for the container
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignCenter)

        # Loading spinner
        self.spinner = BusySpinner(self.container, size=40, line_width=3, interval_ms=60)
        self.spinner.setColor(QColor(30, 144, 255))  # DodgerBlue

        # Loading message
        self.message_label = QLabel(self._message)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet("""
            QLabel {
                color: #333333;
                font-size: 14px;
                font-weight: 500;
                background: transparent;
                border: none;
            }
        """)

        # Add widgets to layout
        layout.addWidget(self.spinner, 0, Qt.AlignCenter)
        layout.addWidget(self.message_label, 0, Qt.AlignCenter)

        # Main layout for the loading screen
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container, 0, Qt.AlignCenter)

    def _setup_animation(self):
        """Setup fade in/out animations"""
        # Fade in animation
        self.fade_in_effect = QGraphicsOpacityEffect()
        self.fade_in_effect.setOpacity(0.0)
        self.setGraphicsEffect(self.fade_in_effect)

        self.fade_in_animation = QPropertyAnimation(self.fade_in_effect, b"opacity")
        self.fade_in_animation.setDuration(300)
        self.fade_in_animation.setStartValue(0.0)
        self.fade_in_animation.setEndValue(1.0)
        self.fade_in_animation.setEasingCurve(QEasingCurve.OutCubic)

        # Fade out animation
        self.fade_out_animation = QPropertyAnimation(self.fade_in_effect, b"opacity")
        self.fade_out_animation.setDuration(200)
        self.fade_out_animation.setStartValue(1.0)
        self.fade_out_animation.setEndValue(0.0)
        self.fade_out_animation.setEasingCurve(QEasingCurve.InCubic)
        self.fade_out_animation.finished.connect(self._on_fade_out_finished)

    def show_loading(self, message=None):
        """Show the loading screen with optional message"""
        if message:
            self.set_message(message)

        if not self._is_visible:
            self._is_visible = True
            self.show()
            self.raise_()
            self.activateWindow()

            # Start spinner
            self.spinner.start()

            # Start fade in animation
            self.fade_in_effect.setOpacity(0.0)
            self.fade_in_animation.start()

    def hide_loading(self):
        """Hide the loading screen with fade out animation"""
        if self._is_visible:
            self._is_visible = False
            self.fade_out_animation.start()

    def _on_fade_out_finished(self):
        """Called when fade out animation is finished"""
        self.hide()
        self.spinner.stop()

    def set_message(self, message):
        """Update the loading message"""
        self._message = message
        self.message_label.setText(message)

    def is_visible(self):
        """Check if loading screen is currently visible"""
        return self._is_visible

    def resizeEvent(self, event):
        """Handle resize events to keep container centered"""
        super().resizeEvent(event)
        if self.parent():
            # Center the container within the parent widget
            parent_rect = self.parent().rect()
            container_rect = self.container.rect()

            x = (parent_rect.width() - container_rect.width()) // 2
            y = (parent_rect.height() - container_rect.height()) // 2

            self.container.move(x, y)

    def showEvent(self, event):
        """Handle show events"""
        super().showEvent(event)
        if self.parent():
            # Resize to match parent
            self.resize(self.parent().size())
            # Center the container
            self.resizeEvent(None)

    def paintEvent(self, event):
        """Custom paint event to draw semi-transparent background"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Draw semi-transparent background
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))  # Semi-transparent black

        super().paintEvent(event)
