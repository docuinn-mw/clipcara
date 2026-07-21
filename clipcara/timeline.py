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
    viewChanged = pyqtSignal(int, int)  # visible start/end ms

    DRAG_THRESHOLD_PX = 4
    MIN_VIEW_SPAN_MS = 1000

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

        self.peaks = None  # (N, 3) float32 min/max/rms covering the whole file
        self.view_peaks = None  # higher-resolution peaks for a zoomed slice
        self.view_peaks_range = None  # (start_ms, end_ms) covered by view_peaks
        self.waveform_peaks = []  # per-pixel (lo, hi, rms), display-normalized
        self._gain = 1.0

        self.position = 0
        self.duration = 0
        self._view = None  # None = whole file; else (start_ms, end_ms)

        self.mark_a = None
        self.mark_b = None

        self._dragging = False
        self._drag_start = 0
        self._drag_current = 0
        self._press_x = 0
        self._cur_x = 0

    # --- view window --------------------------------------------------

    @property
    def view_start(self):
        return 0 if self._view is None else self._view[0]

    @property
    def view_end(self):
        return self.duration if self._view is None else self._view[1]

    def _set_view(self, start, end):
        span = end - start
        if self.duration <= 0 or span >= self.duration:
            new = None
        else:
            start = max(0, min(start, self.duration - span))
            new = (int(start), int(start + span))
        if new != self._view:
            self._view = new
            self._compute_display_peaks()
            self.update()
            self.viewChanged.emit(self.view_start, self.view_end)

    def zoom_full(self):
        self._set_view(0, self.duration)

    def zoom_to(self, a, b):
        if self.duration <= 0 or b <= a:
            return
        margin = max((b - a) * 0.1, 100)
        span = max(b - a + 2 * margin, self.MIN_VIEW_SPAN_MS)
        center = (a + b) / 2
        self._set_view(center - span / 2, center + span / 2)

    def wheelEvent(self, event):
        if self.duration <= 0:
            return
        dy = event.angleDelta().y()
        dx = event.angleDelta().x()
        span = self.view_end - self.view_start
        if dy:
            factor = 1.25 ** (dy / 120.0)
            new_span = max(self.MIN_VIEW_SPAN_MS,
                           min(span / factor, self.duration))
            # keep the audio under the cursor fixed while zooming
            anchor = self._x_to_ms(int(event.position().x()))
            frac = event.position().x() / max(1, self.width())
            start = anchor - frac * new_span
            self._set_view(start, start + new_span)
        elif dx:
            shift = -dx / 120.0 * span * 0.15
            self._set_view(self.view_start + shift, self.view_end + shift)
        event.accept()

    # --- data -----------------------------------------------------------

    def set_waveform(self, peaks):
        self.peaks = peaks
        if peaks is None:
            self.view_peaks = None
            self.view_peaks_range = None
            self._view = None
        self._compute_display_peaks()
        self.update()

    def set_view_peaks(self, peaks, start_ms, end_ms):
        self.view_peaks = peaks
        self.view_peaks_range = (start_ms, end_ms)
        self._compute_display_peaks()
        self.update()

    def _source_for_view(self):
        """Pick the peak array to draw from: the high-resolution zoom
        slice when it covers the current view at better density than
        the whole-file peaks, else the whole-file peaks."""
        vs, ve = self.view_start, self.view_end
        if (self.view_peaks is not None and self.view_peaks_range is not None
                and ve > vs):
            s, e = self.view_peaks_range
            if s <= vs and ve <= e and e > s:
                view_density = len(self.view_peaks) / (e - s)
                base_density = (0 if self.peaks is None or self.duration <= 0
                                else len(self.peaks) / self.duration)
                if view_density >= base_density:
                    return self.view_peaks, s, e
        if self.peaks is not None:
            return self.peaks, 0, self.duration
        return None, 0, 0

    def _compute_display_peaks(self):
        src, s_ms, e_ms = self._source_for_view()
        vs, ve = self.view_start, self.view_end
        if src is None or len(src) == 0 or e_ms <= s_ms or ve <= vs:
            self.waveform_peaks = []
            return
        # Normalize against the whole file so zooming doesn't rescale,
        # capping the boost so near-silence isn't blown up to full scale.
        norm_src = self.peaks if self.peaks is not None and len(self.peaks) else src
        amp = max(float(np.abs(norm_src[:, :2]).max()), 1e-6)
        self._gain = min(1.0 / amp, 100.0)

        n = len(src)
        i0 = int(np.floor((vs - s_ms) / (e_ms - s_ms) * n))
        i1 = int(np.ceil((ve - s_ms) / (e_ms - s_ms) * n))
        i0 = max(0, min(i0, n - 1))
        i1 = max(i0 + 1, min(i1, n))
        sl = src[i0:i1]

        w = max(1, self.width())
        m = len(sl)
        if m <= w:
            cols = sl
        else:
            edges = (np.arange(w + 1, dtype=np.int64) * m) // w
            cols = np.array([
                (sl[edges[i]:edges[i + 1], 0].min(),
                 sl[edges[i]:edges[i + 1], 1].max(),
                 np.sqrt(np.mean(sl[edges[i]:edges[i + 1], 2] ** 2)))
                for i in range(w)
            ])
        self.waveform_peaks = [
            (float(lo) * self._gain, float(hi) * self._gain,
             float(rms) * self._gain)
            for lo, hi, rms in cols
        ]

    def set_position(self, pos_ms):
        self.position = pos_ms
        if self._view is not None:
            vs, ve = self._view
            if pos_ms < vs or pos_ms > ve:
                # keep the playhead visible: page the view along
                span = ve - vs
                start = pos_ms - span * 0.1
                self._set_view(start, start + span)
        self.update()

    def set_duration(self, dur_ms):
        self.duration = dur_ms
        self._compute_display_peaks()
        self.update()

    def set_marks(self, a, b):
        self.mark_a = a
        self.mark_b = b
        self.update()

    def clear_marks(self):
        self.mark_a = None
        self.mark_b = None
        self.update()

    # --- coordinate mapping ----------------------------------------------

    def _ms_to_x(self, ms):
        span = self.view_end - self.view_start
        if span <= 0:
            return 0
        return int((ms - self.view_start) * self.width() / span)

    def _x_to_ms(self, x):
        w = self.width()
        span = self.view_end - self.view_start
        if w <= 0 or span <= 0:
            return 0
        ms = self.view_start + x * span / w
        return int(min(max(0, ms), self.duration))

    def _is_drag(self):
        return abs(self._cur_x - self._press_x) > self.DRAG_THRESHOLD_PX

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.peaks is not None or self.view_peaks is not None:
            self._compute_display_peaks()

    # --- painting ---------------------------------------------------------

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
        self._draw_view_indicator(painter, w, h)

    def _envelope_path(self, w, mid_y, scale, top_idx, bottom_idx,
                       bottom_sign=1.0):
        n = len(self.waveform_peaks)
        path = QPainterPath()
        path.moveTo(0.0, mid_y)
        for i in range(n):
            x = i * w / n
            v = self.waveform_peaks[i][top_idx]
            path.lineTo(x, mid_y - max(min(v, 1.0), -1.0) * scale)
        path.lineTo(w, mid_y)
        for i in range(n - 1, -1, -1):
            x = i * w / n
            v = self.waveform_peaks[i][bottom_idx] * bottom_sign
            path.lineTo(x, mid_y - max(min(v, 1.0), -1.0) * scale)
        path.closeSubpath()
        return path

    def _draw_waveform(self, painter, w, h, mid_y):
        n = len(self.waveform_peaks)
        if n < 2:
            return
        scale = h / 2 - 4

        painter.setPen(Qt.PenStyle.NoPen)

        # translucent min/max peak envelope
        envelope = QColor(self.MAUVE)
        envelope.setAlpha(110)
        painter.setBrush(envelope)
        painter.drawPath(self._envelope_path(w, mid_y, scale, 1, 0))

        # solid +/- RMS body showing loudness shape within the envelope
        painter.setBrush(self.MAUVE)
        painter.drawPath(self._envelope_path(w, mid_y, scale, 2, 2,
                                             bottom_sign=-1.0))

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

    def _draw_view_indicator(self, painter, w, h):
        """Thin bar along the bottom showing where the view sits in the file."""
        if self._view is None:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.SURFACE)
        painter.drawRect(0, h - 3, w, 3)
        x0 = int(self.view_start * w / self.duration)
        x1 = max(x0 + 2, int(self.view_end * w / self.duration))
        painter.setBrush(self.SUBTEXT)
        painter.drawRect(x0, h - 3, x1 - x0, 3)

    # --- mouse -------------------------------------------------------------

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
