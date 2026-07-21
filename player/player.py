import numpy as np
import soundfile as sf
from PyQt6.QtCore import QObject, pyqtSignal, QUrl, QThread
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput


class WaveformLoader(QThread):
    loaded = pyqtSignal(np.ndarray)  # (bins, 2) float32: per-bin min/max
    failed = pyqtSignal(str)

    BINS = 4096

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            peaks = self._compute_peaks()
        except Exception as e:
            if not self._cancelled:
                self.failed.emit(str(e))
            return
        if peaks is not None and len(peaks) and not self._cancelled:
            self.loaded.emit(peaks)

    def _compute_peaks(self):
        with sf.SoundFile(self.filepath) as f:
            frames = f.frames
            if frames <= 0:
                raise ValueError("file contains no audio frames")
            bins = int(min(self.BINS, frames))
            edges = (np.arange(bins + 1, dtype=np.int64) * frames) // bins
            peaks = np.zeros((bins, 2), dtype=np.float32)
            for b in range(bins):
                if self._cancelled:
                    return None
                data = f.read(int(edges[b + 1] - edges[b]),
                              dtype="float32", always_2d=True)
                if len(data) == 0:
                    # frame count was an estimate (e.g. some mp3s)
                    return peaks[:b].copy()
                mono = data.mean(axis=1)
                peaks[b, 0] = mono.min()
                peaks[b, 1] = mono.max()
            return peaks


class AudioPlayer(QObject):
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    playbackStateChanged = pyqtSignal(bool)
    waveformReady = pyqtSignal(np.ndarray)
    waveformFailed = pyqtSignal(str)
    mediaError = pyqtSignal(str)

    # Loop only on a natural playback crossing of B; a seek jump larger
    # than this lands past B without snapping back to A.
    LOOP_SNAP_MS = 2000

    def __init__(self):
        super().__init__()
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self.durationChanged.emit)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)

        self._filepath = None
        self._loader = None
        self._pending_loaders = set()
        self._last_pos = 0

        self.loop_enabled = False
        self.mark_a = None
        self.mark_b = None

    def _on_position_changed(self, pos):
        if self.loop_enabled and self.mark_a is not None and self.mark_b is not None:
            a = min(self.mark_a, self.mark_b)
            b = max(self.mark_a, self.mark_b)
            if self._last_pos < b <= pos and pos - self._last_pos < self.LOOP_SNAP_MS:
                self._player.setPosition(int(a))
        self._last_pos = pos
        self.positionChanged.emit(pos)

    def _on_state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.playbackStateChanged.emit(playing)

    def _on_media_status(self, status):
        # A loop whose B sits at (or was clamped to) the end of the track
        # never satisfies pos >= b before playback stops; restart here.
        if (status == QMediaPlayer.MediaStatus.EndOfMedia
                and self.loop_enabled
                and self.mark_a is not None and self.mark_b is not None):
            self._player.setPosition(int(min(self.mark_a, self.mark_b)))
            self._player.play()

    def _on_error(self, error, error_string):
        if error != QMediaPlayer.Error.NoError:
            self.mediaError.emit(error_string or "Unable to play this file")

    def open(self, filepath):
        self._filepath = filepath
        self._last_pos = 0
        self._player.setSource(QUrl.fromLocalFile(filepath))
        self._start_waveform_load(filepath)

    def _start_waveform_load(self, filepath):
        if self._loader is not None:
            self._loader.cancel()
        loader = WaveformLoader(filepath)
        self._pending_loaders.add(loader)
        loader.loaded.connect(
            lambda peaks, l=loader: self._on_waveform_loaded(l, peaks))
        loader.failed.connect(
            lambda msg, l=loader: self._on_waveform_failed(l, msg))
        loader.finished.connect(
            lambda l=loader: self._on_loader_finished(l))
        self._loader = loader
        loader.start()

    def _on_loader_finished(self, loader):
        self._pending_loaders.discard(loader)
        loader.deleteLater()

    def _on_waveform_loaded(self, loader, peaks):
        if loader is self._loader:
            self.waveformReady.emit(peaks)

    def _on_waveform_failed(self, loader, message):
        if loader is self._loader:
            self.waveformFailed.emit(message)

    def shutdown(self):
        for loader in list(self._pending_loaders):
            loader.cancel()
        for loader in list(self._pending_loaders):
            loader.wait(2000)
        self._player.stop()

    def play(self):
        self._player.play()

    def pause(self):
        self._player.pause()

    def toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        else:
            self.play()

    def stop(self):
        self._player.stop()

    def seek(self, position_ms):
        self._player.setPosition(int(position_ms))

    def skip_relative(self, delta_ms):
        pos = self._player.position()
        new_pos = max(0, min(pos + delta_ms, self._player.duration()))
        self._player.setPosition(int(new_pos))

    @property
    def position(self):
        return self._player.position()

    @property
    def duration(self):
        return self._player.duration()

    @property
    def is_playing(self):
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def set_volume(self, volume):
        self._audio_output.setVolume(volume / 100.0)

    @property
    def volume(self):
        return int(self._audio_output.volume() * 100)

    def set_marks(self, a=None, b=None):
        if a is not None:
            self.mark_a = a
        if b is not None:
            self.mark_b = b

    def clear_marks(self):
        self.mark_a = None
        self.mark_b = None

    def toggle_loop(self):
        self.loop_enabled = not self.loop_enabled
        return self.loop_enabled
