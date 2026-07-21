import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QPainterPath


def fmt_time(ms):
    if ms is None or ms < 0:
        return "--:--"
    total_sec = ms // 1000
    h = total_sec // 3600
    m = (total_sec // 60) % 60
    s = total_sec % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class Timeline(QWidget):
    seekRequested = pyqtSignal(int)
    regionSelected = pyqtSignal(int, int)

    DRAG_THRESHOLD_PX = 4

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

        self.peaks = None  # (N, 2) float32 min/max pairs from the loader
        self.waveform_peaks = []

        self.position = 0
        self.duration = 0

        self.mark_a = None
        self.mark_b = None

        self._dragging = False
        self._drag_start = 0
        self._drag_current = 0
        self._press_x = 0
        self._cur_x = 0

    def set_waveform(self, peaks):
        self.peaks = peaks
        self._compute_display_peaks()
        self.update()

    def _compute_display_peaks(self):
        if self.peaks is None or len(self.peaks) == 0:
            self.waveform_peaks = []
            return
        n = len(self.peaks)
        w = max(1, self.width())
        if n <= w:
            self.waveform_peaks = [(float(lo), float(hi))
                                   for lo, hi in self.peaks]
            return
        edges = (np.arange(w + 1, dtype=np.int64) * n) // w
        self.waveform_peaks = [
            (float(self.peaks[edges[i]:edges[i + 1], 0].min()),
             float(self.peaks[edges[i]:edges[i + 1], 1].max()))
            for i in range(w)
        ]

    def set_position(self, pos_ms):
        self.position = pos_ms
        self.update()

    def set_duration(self, dur_ms):
        self.duration = dur_ms
        self.update()

    def set_marks(self, a, b):
        self.mark_a = a
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
        return int(min(max(0, x * self.duration / w), self.duration))

    def _is_drag(self):
        return abs(self._cur_x - self._press_x) > self.DRAG_THRESHOLD_PX

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.peaks is not None:
            self._compute_display_peaks()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        mid_y = h / 2

        painter.fillRect(0, 0, w, h, self.BASE)

        if self.duration <= 0:
            painter.setPen(self.SUBTEXT)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Open an audio file")
            return

        if self.waveform_peaks:
            self._draw_waveform(painter, w, h, mid_y)
        else:
            # No waveform (still loading or undecodable) — timeline stays usable
            painter.setPen(QPen(self.SURFACE, 2))
            painter.drawLine(0, int(mid_y), w, int(mid_y))
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
        if not self._dragging or not self._is_drag():
            return
        a = min(self._drag_start, self._drag_current)
        b = max(self._drag_start, self._drag_current)
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

        painter.setPen(self.PINK)
        painter.drawText(x + 4, h - 6, fmt_time(self.position))

    def mousePressEvent(self, event):
        if self.duration <= 0:
            return

        x = int(event.position().x())
        ms = self._x_to_ms(x)

        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._press_x = x
            self._cur_x = x
            self._drag_start = ms
            self._drag_current = ms
            self.seekRequested.emit(ms)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._cur_x = int(event.position().x())
            self._drag_current = self._x_to_ms(self._cur_x)
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            return
        self._dragging = False
        self._cur_x = int(event.position().x())
        self._drag_current = self._x_to_ms(self._cur_x)
        if self._is_drag():
            a = min(self._drag_start, self._drag_current)
            b = max(self._drag_start, self._drag_current)
            if a < b:
                self.regionSelected.emit(a, b)
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self.duration <= 0:
            return
        ms = self._x_to_ms(int(event.position().x()))
        half_window = 2000
        a = max(0, ms - half_window)
        b = min(self.duration, ms + half_window)
        if a < b:
            self.regionSelected.emit(a, b)
