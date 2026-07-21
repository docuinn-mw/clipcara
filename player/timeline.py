import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath


class Timeline(QWidget):
    seekRequested = pyqtSignal(int)
    regionSelected = pyqtSignal(int, int)

    BASE = QColor("#1e1e2e")
    SURFACE = QColor("#313244")
    TEXT = QColor("#cdd6f4")
    SUBTEXT = QColor("#a6adc8")
    MAUVE = QColor("#cba6f7")
    PINK = QColor("#f5c2e7")
    GREEN = QColor("#a6e3a1")
    RED = QColor("#f38ba8")
    YELLOW = QColor("#f9e2af")

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

        self.raw_samples = None
        self.sample_rate = None
        self.waveform_peaks = []

        self.position = 0
        self.duration = 0

        self.mark_a = None
        self.mark_b = None

        self._dragging = False
        self._drag_start = 0
        self._drag_current = 0

    def set_waveform(self, samples, sample_rate):
        self.raw_samples = samples
        self.sample_rate = sample_rate
        self._compute_peaks()
        self.update()

    def _compute_peaks(self):
        if self.raw_samples is None or len(self.raw_samples) == 0:
            self.waveform_peaks = []
            return
        num_points = max(1, self.width())
        chunk = max(1, len(self.raw_samples) // num_points)
        self.waveform_peaks = [
            (self.raw_samples[i:i+chunk].min(),
             self.raw_samples[i:i+chunk].max())
            for i in range(0, len(self.raw_samples), chunk)
        ]

    def set_position(self, pos_ms):
        self.position = pos_ms
        self.update()

    def set_duration(self, dur_ms):
        self.duration = dur_ms
        self.update()

    def set_marks(self, a=None, b=None):
        if a is not None:
            self.mark_a = a
        if b is not None:
            self.mark_b = b
        self.update()

    def clear_marks(self):
        self.mark_a = None
        self.mark_b = None
        self.update()

    def _ms_to_x(self, ms):
        if self.duration <= 0:
            return 0
        return int(ms * self.width() / self.duration)

    def _x_to_ms(self, x):
        w = self.width()
        if w <= 0:
            return 0
        return int(max(0, x * self.duration / w))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.raw_samples is not None:
            self._compute_peaks()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        mid_y = h / 2

        painter.fillRect(0, 0, w, h, self.BASE)

        if self.duration <= 0 or not self.waveform_peaks:
            painter.setPen(self.SUBTEXT)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Open an audio file")
            return

        self._draw_waveform(painter, w, h, mid_y)
        self._draw_ab_region(painter, w, h)
        self._draw_markers(painter, w, h)
        self._draw_position(painter, w, h)
        self._draw_drag_region(painter, w, h)

    def _draw_waveform(self, painter, w, h, mid_y):
        n = len(self.waveform_peaks)
        if n < 2:
            return
        scale = h / 2 - 4

        path = QPainterPath()
        path.moveTo(0.0, mid_y)
        for i, (_, hi) in enumerate(self.waveform_peaks):
            x = i * w / n
            y = mid_y - max(min(hi, 1.0), -1.0) * scale
            path.lineTo(x, y)
        path.lineTo(w, mid_y)
        for i in range(n - 1, -1, -1):
            lo, _ = self.waveform_peaks[i]
            x = i * w / n
            y = mid_y - max(min(lo, 1.0), -1.0) * scale
            path.lineTo(x, y)
        path.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.MAUVE)
        painter.drawPath(path)

    def _draw_ab_region(self, painter, w, h):
        if self.mark_a is not None and self.mark_b is not None:
            a = min(self.mark_a, self.mark_b)
            b = max(self.mark_a, self.mark_b)
            ax = self._ms_to_x(a)
            bx = self._ms_to_x(b)
            painter.fillRect(ax, 0, bx - ax, h,
                             QColor(203, 166, 247, 30))

    def _draw_drag_region(self, painter, w, h):
        if not self._dragging:
            return
        a = min(self._drag_start, self._drag_current)
        b = max(self._drag_start, self._drag_current)
        if b - a > 500:
            ax = self._ms_to_x(a)
            bx = self._ms_to_x(b)
            painter.fillRect(ax, 0, bx - ax, h,
                             QColor(249, 226, 175, 30))

    def _draw_markers(self, painter, w, h):
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)

        if self.mark_a is not None:
            x = self._ms_to_x(self.mark_a)
            painter.setPen(QPen(self.GREEN, 2))
            painter.drawLine(x, 0, x, h)
            painter.setPen(self.GREEN)
            painter.drawText(x + 4, 16, "A")

        if self.mark_b is not None:
            x = self._ms_to_x(self.mark_b)
            painter.setPen(QPen(self.RED, 2))
            painter.drawLine(x, 0, x, h)
            painter.setPen(self.RED)
            painter.drawText(x + 4, 16, "B")

    def _draw_position(self, painter, w, h):
        x = self._ms_to_x(self.position)
        painter.setPen(QPen(self.PINK, 2))
        painter.drawLine(x, 0, x, h)

        # Time tooltip near position
        minutes = self.position // 60000
        seconds = (self.position // 1000) % 60
        time_str = f"{minutes:02d}:{seconds:02d}"
        painter.setPen(self.PINK)
        painter.drawText(x + 4, h - 6, time_str)

    def mousePressEvent(self, event):
        if self.duration <= 0:
            return

        ms = self._x_to_ms(int(event.position().x()))

        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = ms
            self._drag_current = ms
            self.seekRequested.emit(ms)

    def mouseMoveEvent(self, event):
        if self._dragging:
            ms = self._x_to_ms(int(event.position().x()))
            self._drag_current = ms
            self.update()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            ms = self._x_to_ms(int(event.position().x()))
            self._drag_current = ms
            dragged = abs(self._drag_current - self._drag_start)
            if dragged > 500:
                a = min(self._drag_start, self._drag_current)
                b = max(self._drag_start, self._drag_current)
                self.regionSelected.emit(a, b)
            self.update()

    def mouseDoubleClickEvent(self, event):
        if self.duration <= 0:
            return
        ms = self._x_to_ms(int(event.position().x()))
        half_window = 2000
        a = max(0, ms - half_window)
        b = min(self.duration, ms + half_window)
        self.regionSelected.emit(a, b)
