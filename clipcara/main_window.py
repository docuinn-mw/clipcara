import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QSlider, QMessageBox,
    QComboBox, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut

from .loops import LoopStore
from .player import AudioPlayer, WaveformLoader, export_region
from .timeline import Timeline, fmt_time


BASE = "#1e1e2e"
SURFACE = "#313244"
SURFACE1 = "#45475a"
SURFACE2 = "#585b70"
TEXT = "#cdd6f4"
SUBTEXT = "#a6adc8"
MAUVE = "#cba6f7"
PINK = "#f5c2e7"
GREEN = "#a6e3a1"
RED = "#f38ba8"


STYLESHEET = f"""
QMainWindow, QWidget {{ background-color: {BASE}; color: {TEXT}; }}
QLabel {{ color: {TEXT}; font-size: 13px; }}
QPushButton {{
    background-color: {SURFACE};
    color: {TEXT};
    border: 1px solid {SURFACE1};
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 13px;
    min-width: 40px;
}}
QPushButton:hover {{ background-color: {SURFACE1}; }}
QPushButton:pressed {{ background-color: {SURFACE2}; }}
QPushButton:checked {{ background-color: {MAUVE}; color: {BASE}; }}
QSlider::groove:horizontal {{
    background: {SURFACE1};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {MAUVE};
    width: 14px;
    height: 14px;
    margin: -4px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {MAUVE};
    border-radius: 3px;
}}
"""


class MainWindow(QMainWindow):
    NUDGE_MS = 50

    def __init__(self, filepath=None):
        super().__init__()
        self.setWindowTitle("Clipcara")
        self.setMinimumSize(850, 480)
        self.setStyleSheet(STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        self.player = AudioPlayer()
        self.loop_store = LoopStore()
        self._current_loops = []

        self._build_top_bar(layout)
        self._build_timeline(layout)
        self._build_info_bar(layout)
        self._build_controls(layout)
        self._build_volume(layout)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.waveformReady.connect(self._on_waveform_ready)
        self.player.waveformFailed.connect(self._on_waveform_failed)
        self.player.mediaError.connect(self._on_media_error)

        self.timeline.seekRequested.connect(self.player.seek)
        self.timeline.regionSelected.connect(self._on_region_selected)

        # zoomed views get re-decoded at higher resolution, debounced
        self.player.viewPeaksReady.connect(self.timeline.set_view_peaks)
        self.timeline.viewChanged.connect(self._on_view_changed)
        self._pending_view = None
        self._view_timer = QTimer(self)
        self._view_timer.setSingleShot(True)
        self._view_timer.setInterval(250)
        self._view_timer.timeout.connect(self._request_view_peaks)

        self._setup_shortcuts()
        self._refresh_loops()
        self._update_marks_label()

        if filepath:
            self._open_file(filepath)

    def _build_top_bar(self, layout):
        bar = QHBoxLayout()
        self.open_btn = QPushButton("Open")
        self.open_btn.clicked.connect(self._on_open)
        bar.addWidget(self.open_btn)

        self.file_label = QLabel("No file loaded")
        bar.addWidget(self.file_label, 1)

        self.loop_combo = QComboBox()
        self.loop_combo.setPlaceholderText("Saved loops")
        self.loop_combo.setMinimumWidth(160)
        self.loop_combo.activated.connect(self._on_loop_selected)
        bar.addWidget(self.loop_combo)

        self.save_loop_btn = QPushButton("Save Loop")
        self.save_loop_btn.clicked.connect(self._on_save_loop)
        bar.addWidget(self.save_loop_btn)

        self.del_loop_btn = QPushButton("Delete")
        self.del_loop_btn.clicked.connect(self._on_delete_loop)
        bar.addWidget(self.del_loop_btn)

        layout.addLayout(bar)

    def _build_timeline(self, layout):
        self.timeline = Timeline()
        layout.addWidget(self.timeline)

    def _build_info_bar(self, layout):
        info = QHBoxLayout()
        self.time_label = QLabel("--:-- / --:--")
        self.marks_label = QLabel("A: --  B: --  Loop: OFF")
        info.addWidget(self.time_label)
        info.addStretch()
        info.addWidget(self.marks_label)
        layout.addLayout(info)

    def _build_controls(self, layout):
        ctrl = QHBoxLayout()

        self.skip_back_btn = QPushButton("\u23EA -15s [\u2190]")
        self.skip_back_btn.clicked.connect(lambda: self.player.skip_relative(-15000))
        ctrl.addWidget(self.skip_back_btn)

        self.play_btn = QPushButton("\u25B6 Play [Space]")
        self.play_btn.clicked.connect(self._on_play)
        ctrl.addWidget(self.play_btn)

        self.stop_btn = QPushButton("\u23F9 Stop [S]")
        self.stop_btn.clicked.connect(self.player.stop)
        ctrl.addWidget(self.stop_btn)

        self.skip_fwd_btn = QPushButton("+15s \u23E9 [\u2192]")
        self.skip_fwd_btn.clicked.connect(lambda: self.player.skip_relative(15000))
        ctrl.addWidget(self.skip_fwd_btn)

        ctrl.addStretch()

        self.mark_a_btn = QPushButton("Mark A [I]")
        self.mark_a_btn.clicked.connect(self._on_mark_a)
        ctrl.addWidget(self.mark_a_btn)

        self.mark_b_btn = QPushButton("Mark B [O]")
        self.mark_b_btn.clicked.connect(self._on_mark_b)
        ctrl.addWidget(self.mark_b_btn)

        self.loop_btn = QPushButton("Loop [L]")
        self.loop_btn.setCheckable(True)
        self.loop_btn.clicked.connect(self._on_toggle_loop)
        ctrl.addWidget(self.loop_btn)

        self.clear_btn = QPushButton("Clear [Esc]")
        self.clear_btn.clicked.connect(self._on_clear_marks)
        ctrl.addWidget(self.clear_btn)

        self.export_btn = QPushButton("Export [E]")
        self.export_btn.setToolTip("Write the A-B region to a WAV file")
        self.export_btn.clicked.connect(self._on_export)
        ctrl.addWidget(self.export_btn)

        layout.addLayout(ctrl)

    def _build_volume(self, layout):
        vol = QHBoxLayout()
        vol.addWidget(QLabel("Vol"))
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.valueChanged.connect(self.player.set_volume)
        self.vol_slider.setValue(70)
        vol.addWidget(self.vol_slider, 1)

        vol.addSpacing(16)
        vol.addWidget(QLabel("Speed"))
        self.speed_down_btn = QPushButton("−")
        self.speed_down_btn.setToolTip("Slower — hotkey: [")
        self.speed_down_btn.clicked.connect(lambda: self._change_speed(-0.05))
        vol.addWidget(self.speed_down_btn)
        self.speed_label = QLabel("1.00x")
        self.speed_label.setMinimumWidth(48)
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_label.setToolTip("Press 1 to reset")
        vol.addWidget(self.speed_label)
        self.speed_up_btn = QPushButton("+")
        self.speed_up_btn.setToolTip("Faster — hotkey: ]")
        self.speed_up_btn.clicked.connect(lambda: self._change_speed(0.05))
        vol.addWidget(self.speed_up_btn)

        layout.addLayout(vol)

    def _setup_shortcuts(self):
        # Space = play/pause
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self._on_play)
        # I = mark A (in)
        QShortcut(QKeySequence(Qt.Key.Key_I), self, self._on_mark_a)
        # O = mark B (out)
        QShortcut(QKeySequence(Qt.Key.Key_O), self, self._on_mark_b)
        # L = toggle loop
        QShortcut(QKeySequence(Qt.Key.Key_L), self, self._on_toggle_loop)
        # Left = -15s
        QShortcut(QKeySequence(Qt.Key.Key_Left), self,
                  lambda: self.player.skip_relative(-15000))
        # Right = +15s
        QShortcut(QKeySequence(Qt.Key.Key_Right), self,
                  lambda: self.player.skip_relative(15000))
        # Escape = clear marks
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self._on_clear_marks)
        # Up = volume up
        QShortcut(QKeySequence(Qt.Key.Key_Up), self, self._vol_up)
        # Down = volume down
        QShortcut(QKeySequence(Qt.Key.Key_Down), self, self._vol_down)
        # S = stop
        QShortcut(QKeySequence(Qt.Key.Key_S), self, self.player.stop)
        # [ / ] = slower / faster, 1 = normal speed
        QShortcut(QKeySequence(Qt.Key.Key_BracketLeft), self,
                  lambda: self._change_speed(-0.05))
        QShortcut(QKeySequence(Qt.Key.Key_BracketRight), self,
                  lambda: self._change_speed(0.05))
        QShortcut(QKeySequence(Qt.Key.Key_1), self,
                  lambda: self._set_speed(1.0))
        # , / . = nudge A by 50ms; < / > = nudge B
        QShortcut(QKeySequence(","), self,
                  lambda: self._nudge_mark("a", -self.NUDGE_MS))
        QShortcut(QKeySequence("."), self,
                  lambda: self._nudge_mark("a", self.NUDGE_MS))
        QShortcut(QKeySequence("Shift+,"), self,
                  lambda: self._nudge_mark("b", -self.NUDGE_MS))
        QShortcut(QKeySequence("Shift+."), self,
                  lambda: self._nudge_mark("b", self.NUDGE_MS))
        # Z = zoom to A-B selection, F = full view
        QShortcut(QKeySequence(Qt.Key.Key_Z), self, self._zoom_to_selection)
        QShortcut(QKeySequence(Qt.Key.Key_F), self, self.timeline.zoom_full)
        # E = export A-B region
        QShortcut(QKeySequence(Qt.Key.Key_E), self, self._on_export)
        # Ctrl+O = open
        QShortcut(QKeySequence("Ctrl+O"), self, self._on_open)

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Audio File", "",
            "Audio Files (*.mp3 *.wav *.flac *.m4a *.ogg *.aac *.wma);;All Files (*)"
        )
        if not path:
            return
        self._open_file(path)

    def _open_file(self, path):
        self.file_label.setText(os.path.basename(path))
        self.statusBar().clearMessage()
        self.timeline.set_waveform(None)
        self.player.open(path)
        self.timeline.clear_marks()
        self.player.clear_marks()
        self.player.loop_enabled = False
        self.loop_btn.setChecked(False)
        self._refresh_loops()
        self._update_marks_label()

    def _on_play(self):
        if self.player.duration <= 0:
            return
        self.player.toggle_play()

    def _apply_marks(self, a, b):
        self.player.set_marks(a, b)
        self.timeline.set_marks(a, b)
        self._update_marks_label()

    def _on_mark_a(self):
        if self.player.duration <= 0:
            return
        pos = self.player.position
        b = self.player.mark_b
        if b is not None and b <= pos:
            b = None  # a new In at/after the Out starts a fresh selection
        self._apply_marks(pos, b)

    def _on_mark_b(self):
        if self.player.duration <= 0:
            return
        pos = self.player.position
        a = self.player.mark_a
        if a is not None and a >= pos:
            a = None  # a new Out at/before the In starts a fresh selection
        self._apply_marks(a, pos)

    def _on_toggle_loop(self):
        enabled = self.player.toggle_loop()
        self.loop_btn.setChecked(enabled)
        self._update_marks_label()

    def _on_clear_marks(self):
        self.player.clear_marks()
        self.timeline.clear_marks()
        self.loop_btn.setChecked(False)
        self.player.loop_enabled = False
        self._update_marks_label()

    def _on_region_selected(self, a, b):
        self.player.loop_enabled = True
        self.loop_btn.setChecked(True)
        self._apply_marks(a, b)

    def _on_position_changed(self, pos):
        self.timeline.set_position(pos)
        self._update_time_label()

    def _on_duration_changed(self, dur):
        self.timeline.set_duration(dur)
        self._update_time_label()

    def _on_playback_state_changed(self, playing):
        self.play_btn.setText("\u23F8 Pause" if playing else "\u25B6 Play")

    def _on_waveform_ready(self, peaks):
        self.timeline.set_waveform(peaks)

    def _on_waveform_failed(self, message):
        self.statusBar().showMessage(f"Waveform unavailable: {message}")

    def _on_media_error(self, message):
        QMessageBox.warning(self, "Playback error", message)

    def closeEvent(self, event):
        self.player.shutdown()
        super().closeEvent(event)

    def _update_time_label(self):
        cur = fmt_time(self.player.position)
        total = fmt_time(self.player.duration)
        self.time_label.setText(f"{cur} / {total}")

    def _update_marks_label(self):
        a = fmt_time(self.player.mark_a) if self.player.mark_a is not None else "--"
        b = fmt_time(self.player.mark_b) if self.player.mark_b is not None else "--"
        state = "ON" if self.player.loop_enabled else "OFF"
        self.marks_label.setText(f"A: {a}  B: {b}  Loop: {state}")
        has_region = (self.player.mark_a is not None
                      and self.player.mark_b is not None)
        self.export_btn.setEnabled(has_region)
        self.save_loop_btn.setEnabled(has_region)

    # --- marks: nudge and zoom -----------------------------------------

    def _nudge_mark(self, which, delta):
        a, b = self.player.mark_a, self.player.mark_b
        dur = self.player.duration
        if which == "a":
            if a is None:
                return
            a = max(0, min(a + delta, b if b is not None else dur))
        else:
            if b is None:
                return
            b = max(a if a is not None else 0, min(b + delta, dur))
        self._apply_marks(a, b)

    def _zoom_to_selection(self):
        a, b = self.player.mark_a, self.player.mark_b
        if a is not None and b is not None and a < b:
            self.timeline.zoom_to(a, b)

    # --- zoomed-view refinement ------------------------------------------

    def _on_view_changed(self, start_ms, end_ms):
        self._pending_view = (start_ms, end_ms)
        self._view_timer.start()

    def _request_view_peaks(self):
        if self._pending_view is None or self.player.duration <= 0:
            return
        start_ms, end_ms = self._pending_view
        span = end_ms - start_ms
        if span <= 0 or span >= self.player.duration:
            return
        width = max(self.timeline.width(), 512)
        base_bins_in_view = WaveformLoader.BINS * span / self.player.duration
        if base_bins_in_view >= width:
            return  # whole-file peaks already resolve this view
        self.player.request_view_peaks(start_ms, end_ms, min(width, 4096))

    # --- export -----------------------------------------------------------

    def _on_export(self):
        a, b = self.player.mark_a, self.player.mark_b
        src = self.player.filepath
        if a is None or b is None or a >= b or not src:
            return
        stem = os.path.splitext(os.path.basename(src))[0]
        times = f"{fmt_time(a)}-{fmt_time(b)}".replace(":", ".")
        default = os.path.join(os.path.dirname(src), f"{stem} {times}.wav")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Region", default, "WAV audio (*.wav)")
        if not path:
            return
        try:
            export_region(src, path, a, b)
        except Exception as e:
            QMessageBox.warning(self, "Export failed", str(e))
            return
        self.statusBar().showMessage(
            f"Exported {os.path.basename(path)}", 5000)

    # --- saved loops --------------------------------------------------------

    def _refresh_loops(self, select_name=None):
        self._current_loops = (self.loop_store.loops_for(self.player.filepath)
                               if self.player.filepath else [])
        self.loop_combo.clear()
        for loop in self._current_loops:
            self.loop_combo.addItem(
                f'{loop["name"]}  ({fmt_time(loop["a"])}-{fmt_time(loop["b"])})')
        self.loop_combo.setCurrentIndex(-1)
        if select_name is not None:
            for i, loop in enumerate(self._current_loops):
                if loop["name"] == select_name:
                    self.loop_combo.setCurrentIndex(i)
                    break
        self.loop_combo.setEnabled(bool(self._current_loops))
        self.del_loop_btn.setEnabled(self.loop_combo.currentIndex() >= 0)

    def _on_loop_selected(self, index):
        if not 0 <= index < len(self._current_loops):
            return
        loop = self._current_loops[index]
        self._on_region_selected(loop["a"], loop["b"])
        # jump into the loop so playback switches immediately and the
        # playhead sits inside the zoomed view (otherwise view-follow
        # pages the display back to the old position)
        self.player.seek(loop["a"])
        self.timeline.zoom_to(loop["a"], loop["b"])
        self.del_loop_btn.setEnabled(True)

    def _on_save_loop(self):
        a, b = self.player.mark_a, self.player.mark_b
        if a is None or b is None or a >= b or not self.player.filepath:
            return
        default = f"{fmt_time(a)}-{fmt_time(b)}"
        name, ok = QInputDialog.getText(self, "Save Loop", "Name:",
                                        text=default)
        if not ok or not name.strip():
            return
        self.loop_store.add(self.player.filepath, name.strip(), a, b)
        self._refresh_loops(select_name=name.strip())

    def _on_delete_loop(self):
        index = self.loop_combo.currentIndex()
        if not 0 <= index < len(self._current_loops):
            return
        self.loop_store.remove(self.player.filepath,
                               self._current_loops[index]["name"])
        self._refresh_loops()

    def _change_speed(self, delta):
        self._set_speed(self.player.playback_rate + delta)

    def _set_speed(self, rate):
        rate = max(0.5, min(2.0, round(rate * 20) / 20))
        self.player.set_playback_rate(rate)
        self.speed_label.setText(f"{rate:.2f}x")

    def _vol_up(self):
        v = min(100, self.vol_slider.value() + 10)
        self.vol_slider.setValue(v)

    def _vol_down(self):
        v = max(0, self.vol_slider.value() - 10)
        self.vol_slider.setValue(v)
