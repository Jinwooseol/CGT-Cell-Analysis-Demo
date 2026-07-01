from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QSplashScreen

from cgt_cell_analysis_demo import __resource_path__, __version__


class SplashScreen(QSplashScreen):
    """
    A custom splash screen for application startup.
    Shows immediately while heavy libraries load in the background.
    """

    def __init__(self):
        # Internal state for animated dots
        self._dot_count = 0
        self._base_message = "Initializing"
        self._last_message = ""
        self._dot_timer = QTimer()
        self._dot_timer.setInterval(280)
        self._dot_timer.timeout.connect(self._tick_dots)

        # Create a custom pixmap for the splash screen
        pixmap = self._create_splash_pixmap()
        super().__init__(pixmap)

        # Set window flags for better appearance
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.SplashScreen | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Set up the splash screen content
        self._setup_content()

        # Show immediately and start simple animation
        self.show()
        QApplication.processEvents()  # Force immediate display
        self._dot_timer.start()

    def _setup_content(self):
        """Optional runtime setup hook for additional widgets or effects.
        Currently unused because all visuals are drawn onto the pixmap.
        Kept for future extensibility and to avoid attribute errors.
        """
        # No-op
        return

    def _create_splash_pixmap(self, message: str | None = None):
        """Create a minimalist, modern splash pixmap with optional message text"""
        # Slightly larger canvas for a more premium look
        width, height = 520, 340
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # Background: resource image if available, otherwise soft gradient
        bg_path = __resource_path__ / "img_splash_bg.png"
        if bg_path.exists():
            try:
                bg = QPixmap(str(bg_path))
                if not bg.isNull():
                    # Cover: keep aspect, fill entire canvas
                    bg_scaled = bg.scaled(
                        width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                    )
                    # Center crop
                    x = (bg_scaled.width() - width) // 2
                    y = (bg_scaled.height() - height) // 2
                    painter.drawPixmap(0, 0, bg_scaled, x, y, width, height)
                    # Apply subtle dark overlay to improve text contrast
                    painter.fillRect(0, 0, width, height, QColor(0, 0, 0, 60))
                else:
                    raise RuntimeError("BG pixmap null")
            except Exception:
                gradient = QLinearGradient(0, 0, width, height)
                gradient.setColorAt(0.0, QColor(245, 248, 255))
                gradient.setColorAt(1.0, QColor(235, 242, 252))
                painter.fillRect(0, 0, width, height, QBrush(gradient))
        else:
            gradient = QLinearGradient(0, 0, width, height)
            gradient.setColorAt(0.0, QColor(245, 248, 255))
            gradient.setColorAt(1.0, QColor(235, 242, 252))
            painter.fillRect(0, 0, width, height, QBrush(gradient))

        # Center card with rounded corners and subtle shadow
        card_rect_w, card_rect_h = 420, 230
        card_x = (width - card_rect_w) // 2
        card_y = (height - card_rect_h) // 2

        # Shadow (drawn first, slightly offset and blurred look via alpha)
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(card_x + 2, card_y + 4, card_rect_w, card_rect_h, 18, 18)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 30))

        # Card
        card_path = QPainterPath()
        card_path.addRoundedRect(card_x, card_y, card_rect_w, card_rect_h, 18, 18)
        painter.fillPath(card_path, QColor(255, 255, 255, 240))

        # Accent line on top of card
        painter.setPen(QColor(30, 144, 255, 180))  # DodgerBlue accent
        painter.drawLine(card_x + 18, card_y + 18, card_x + card_rect_w - 18, card_y + 18)

        # App icon (if available)
        icon_path = __resource_path__ / "icn_app_logo.ico"
        if icon_path.exists():
            try:
                icon_pix = QPixmap(str(icon_path))
                if not icon_pix.isNull():
                    icon_size = 72
                    scaled = icon_pix.scaled(
                        icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                    ix = card_x + (card_rect_w - icon_size) // 2
                    iy = card_y + 34
                    painter.drawPixmap(ix, iy, scaled)
            except Exception:
                pass

        # Title
        painter.setPen(QColor(35, 41, 70))
        title_font = QFont("Segoe UI", 22, QFont.Bold)
        painter.setFont(title_font)
        title_text = "cgt_cell_analysis_demo"
        tw = QFontMetrics(title_font).horizontalAdvance(title_text)
        painter.drawText(card_x + (card_rect_w - tw) // 2, card_y + 130, title_text)

        # Subtitle
        painter.setPen(QColor(90, 100, 130))
        subtitle_font = QFont("Segoe UI", 11)
        painter.setFont(subtitle_font)
        subtitle_text = "Preparing workspace"
        sw = QFontMetrics(subtitle_font).horizontalAdvance(subtitle_text)
        painter.drawText(card_x + (card_rect_w - sw) // 2, card_y + 155, subtitle_text)

        # Version
        painter.setPen(QColor(130, 140, 165))
        version_font = QFont("Segoe UI", 9)
        painter.setFont(version_font)
        v_text = f"v{__version__}"
        vw = QFontMetrics(version_font).horizontalAdvance(v_text)
        v_y = card_y + card_rect_h - 28
        painter.drawText(card_x + (card_rect_w - vw) // 2, v_y, v_text)

        # Optional message just BELOW version line
        if message:
            painter.setPen(QColor(70, 80, 105))
            msg_font = QFont("Segoe UI", 10)
            painter.setFont(msg_font)
            mw = QFontMetrics(msg_font).horizontalAdvance(message)
            painter.drawText(card_x + (card_rect_w - mw) // 2, v_y + 16, message)

        # Loading dots baseline (dots are drawn via update_message)
        painter.end()
        return pixmap

    def _draw_background(self, painter, rect):
        """Deprecated: background handled in _create_splash_pixmap"""
        return

    def _draw_icon(self, painter, rect):
        """Draw the application icon"""
        icon_path = __resource_path__ / "icn_app_logo.ico"
        if icon_path.exists():
            try:
                icon_pixmap = QPixmap(str(icon_path))
                if not icon_pixmap.isNull():
                    # Scale icon to appropriate size
                    icon_size = 80
                    scaled_icon = icon_pixmap.scaled(
                        icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )

                    # Center the icon
                    x = (rect.width() - icon_size) // 2
                    y = 40
                    painter.drawPixmap(x, y, scaled_icon)
            except Exception:
                # If icon loading fails, continue without it
                pass

    def _draw_title(self, painter, rect):
        """Draw the application title"""
        painter.setPen(QColor(50, 50, 50))

        # Main title
        title_font = QFont("Arial", 24, QFont.Bold)
        painter.setFont(title_font)

        title_text = "cgt_cell_analysis_demo"
        title_metrics = QFontMetrics(title_font)
        title_width = title_metrics.horizontalAdvance(title_text)
        title_x = (rect.width() - title_width) // 2
        title_y = 140

        painter.drawText(title_x, title_y, title_text)

        # Subtitle
        subtitle_font = QFont("Arial", 12)
        painter.setFont(subtitle_font)
        painter.setPen(QColor(100, 100, 100))

        subtitle_text = "Cell Growth Tracking Application"
        subtitle_metrics = QFontMetrics(subtitle_font)
        subtitle_width = subtitle_metrics.horizontalAdvance(subtitle_text)
        subtitle_x = (rect.width() - subtitle_width) // 2
        subtitle_y = title_y + 25

        painter.drawText(subtitle_x, subtitle_y, subtitle_text)

    def _draw_version(self, painter, rect):
        """Draw version information"""
        painter.setPen(QColor(120, 120, 120))
        version_font = QFont("Arial", 10)
        painter.setFont(version_font)

        version_text = f"Version {__version__}"
        version_metrics = QFontMetrics(version_font)
        version_width = version_metrics.horizontalAdvance(version_text)
        version_x = (rect.width() - version_width) // 2
        version_y = rect.height() - 60

        painter.drawText(version_x, version_y, version_text)

    def _draw_loading_area(self, painter, rect):
        """Deprecated: handled by update_message with animated dots"""
        return

    def update_message(self, message):
        """Update the loading message right below the version label"""
        if message:
            self._base_message = message
        dots = "." * (self._dot_count % 4)
        text = f"{self._base_message}{dots}"
        self._last_message = text
        # Redraw the pixmap with the new message placed under the version
        self.setPixmap(self._create_splash_pixmap(text))
        QApplication.processEvents()

    def _tick_dots(self):
        self._dot_count = (self._dot_count + 1) % 4
        # Trigger a repaint using the base message (without dots); update_message appends dots
        self.update_message(self._base_message)

    def finish_loading(self, main_window):
        """Finish loading and transition to main window"""
        # Update message
        self.update_message("Loading complete!")

        # Wait a moment for user to see the completion message
        QTimer.singleShot(500, lambda: self._transition_to_main(main_window))

    def _transition_to_main(self, main_window):
        """Transition to main window"""
        # Show main window
        main_window.show()

        # Hide splash screen
        self._dot_timer.stop()
        self.hide()

        # Clean up
        self.deleteLater()
