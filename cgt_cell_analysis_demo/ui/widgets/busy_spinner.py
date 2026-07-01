from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class BusySpinner(QWidget):
    """
    Lightweight indeterminate busy spinner.
    - Drawn directly with QPainter, no external gif/image needed.
    - 12 segments with a fading rotation effect.
    """

    def __init__(
        self,
        parent=None,
        size: int = 18,
        line_width: int = 2,
        color: QColor | None = None,
        interval_ms: int = 80,
    ):
        super().__init__(parent)
        self._size = size
        self._line_width = line_width
        self._color = color or QColor(30, 144, 255)  # DodgerBlue
        self._step = 0
        self._count = 12
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(QSize(self._size, self._size))
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setVisible(False)

    def start(self):
        if not self._timer.isActive():
            self._timer.start()
        self.setVisible(True)

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        self.setVisible(False)
        self._step = 0
        self.update()

    def setColor(self, color: QColor):
        self._color = color
        self.update()

    def setLineWidth(self, w: int):
        self._line_width = max(1, w)
        self.update()

    def setSpeed(self, interval_ms: int):
        self._timer.setInterval(max(10, interval_ms))

    def sizeHint(self) -> QSize:
        return QSize(self._size, self._size)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def _tick(self):
        self._step = (self._step + 1) % self._count
        self.update()

    def paintEvent(self, _):
        # Draw: a rotating ring of 12 segments, each faded by position
        s = min(self.width(), self.height())
        radius = (s - self._line_width) / 2.0
        center = s / 2.0

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.translate(center, center)

        for i in range(self._count):
            # Fade relative to the current step (trailing segments are dimmer)
            idx = (self._step + i) % self._count
            alpha = int(255 * (0.2 + 0.8 * (i + 1) / self._count))  # 20% ~ 100%
            col = QColor(self._color)
            col.setAlpha(alpha)

            pen = QPen(col, self._line_width, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            painter.save()
            # Each segment is spaced 360/12 = 30 degrees apart
            painter.rotate(30 * idx)
            # Draw short radial ticks from the inner toward the outer radius, leaving the center empty,
            # producing a rotating "dotted" busy effect.
            y1 = -radius * 0.6
            y2 = -radius
            painter.drawLine(0, int(y1), 0, int(y2))
            painter.restore()

        painter.end()
