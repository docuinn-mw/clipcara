import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, QUrl, QThread
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput


class WaveformLoader(QThread):
    finished = pyqtSignal(np.ndarray, int)

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath

    def run(self):
        from pydub import AudioSegment
        audio = AudioSegment.from_file(self.filepath)
        samples = np.array(audio.get_array_of_samples())
        if audio.channels == 2:
            samples = samples.reshape((-1, 2)).mean(axis=1)
        samples = samples.astype(np.float32) / (2**15)
        self.finished.emit(samples, audio.frame_rate)


class AudioPlayer(QObject):
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    playbackStateChanged = pyqtSignal(bool)
    waveformReady = pyqtSignal(np.ndarray, int)

    def __init__(self):
        super().__init__()
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self.durationChanged.emit)
        self._player.playbackStateChanged.connect(self._on_state_changed)

        self._filepath = None
        self._loader = None

        self.loop_enabled = False
        self.mark_a = None
        self.mark_b = None

    def _on_position_changed(self, pos):
        if self.loop_enabled and self.mark_a is not None and self.mark_b is not None:
            a = min(self.mark_a, self.mark_b)
            b = max(self.mark_a, self.mark_b)
            if pos >= b:
                self._player.setPosition(int(a))
        self.positionChanged.emit(pos)

    def _on_state_changed(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.playbackStateChanged.emit(playing)

    def open(self, filepath):
        self._filepath = filepath
        self._player.setSource(QUrl.fromLocalFile(filepath))
        self._start_waveform_load(filepath)

    def _start_waveform_load(self, filepath):
        if self._loader is not None and self._loader.isRunning():
            self._loader.quit()
            self._loader.wait()
        self._loader = WaveformLoader(filepath)
        self._loader.finished.connect(self._on_waveform_loaded)
        self._loader.start()

    def _on_waveform_loaded(self, samples, sample_rate):
        self.waveformReady.emit(samples, sample_rate)

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
