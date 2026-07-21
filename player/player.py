import numpy as np
import soundfile as sf
from PyQt6.QtCore import QObject, pyqtSignal, QUrl, QThread
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput


class WaveformLoader(QThread):
    loaded = pyqtSignal(np.ndarray)  # (bins, 3) float32: per-bin min/max/rms
    failed = pyqtSignal(str)

    BINS = 4096
    # Read in large blocks: libsndfile's mp3 decoder returns silent
    # frames for very small sequential reads, and big reads are faster.
    BLOCK = 1 << 17

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
            mins = np.full(bins, np.inf)
            maxs = np.full(bins, -np.inf)
            sumsq = np.zeros(bins)
            counts = np.zeros(bins, dtype=np.int64)
            pos = 0
            while pos < frames:
                if self._cancelled:
                    return None
                data = f.read(min(self.BLOCK, frames - pos),
                              dtype="float32", always_2d=True)
                n = len(data)
                if n == 0:
                    break  # frame count was an estimate
                mono = data.mean(axis=1).astype(np.float64)
                # bin index of each frame; every bin in [b0, b1] occurs,
                # so segment starts are strictly increasing
                idx = (pos + np.arange(n, dtype=np.int64)) * bins // frames
                b0, b1 = int(idx[0]), int(idx[-1])
                starts = np.searchsorted(idx, np.arange(b0, b1 + 1))
                seg = slice(b0, b1 + 1)
                mins[seg] = np.minimum(mins[seg],
                                       np.minimum.reduceat(mono, starts))
                maxs[seg] = np.maximum(maxs[seg],
                                       np.maximum.reduceat(mono, starts))
                sumsq[seg] += np.add.reduceat(mono * mono, starts)
                counts[seg] += np.diff(np.append(starts, n))
                pos += n
            filled = np.nonzero(counts > 0)[0]
            if len(filled) == 0:
                raise ValueError("file contains no audio frames")
            last = int(filled.max()) + 1
            peaks = np.zeros((last, 3), dtype=np.float32)
            peaks[:, 0] = mins[:last]
            peaks[:, 1] = maxs[:last]
            peaks[:, 2] = np.sqrt(sumsq[:last] / np.maximum(counts[:last], 1))
            return peaks


class AudioPlayer(QObject):
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    playbackStateChanged = pyqtSignal(bool)
    waveformReady = pyqtSignal(np.ndarray)
    waveformFailed = pyqtSignal(str)
    mediaError = pyqtSignal(str)

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

        self.loop_enabled = False
        self.mark_a = None
        self.mark_b = None

    def _on_position_changed(self, pos):
        # With loop on, playback is confined to [A, B]: anything at or
        # past B snaps back to A, including when loop was just enabled
        # with the playhead already beyond B.
        if self.loop_enabled and self.mark_a is not None and self.mark_b is not None:
            a = min(self.mark_a, self.mark_b)
            b = max(self.mark_a, self.mark_b)
            if pos >= b > a:
                self._player.setPosition(int(a))
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

    def set_playback_rate(self, rate):
        self._player.setPlaybackRate(rate)

    @property
    def playback_rate(self):
        return self._player.playbackRate()

    def set_volume(self, volume):
        self._audio_output.setVolume(volume / 100.0)

    @property
    def volume(self):
        return int(self._audio_output.volume() * 100)

    def set_marks(self, a, b):
        self.mark_a = a
        self.mark_b = b

    def clear_marks(self):
        self.mark_a = None
        self.mark_b = None

    def toggle_loop(self):
        self.loop_enabled = not self.loop_enabled
        return self.loop_enabled
