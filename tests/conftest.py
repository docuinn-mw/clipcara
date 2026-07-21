import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
import soundfile as sf
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="session")
def tone_files(tmp_path_factory):
    """5s stereo 440 Hz sine at 0.5 amplitude, in several formats."""
    d = tmp_path_factory.mktemp("audio")
    sr = 44100
    t = np.arange(5 * sr) / sr
    sig = 0.5 * np.sin(2 * np.pi * 440 * t)
    stereo = np.stack([sig, sig], axis=1)
    files = {}
    for key, name, subtype in [
        ("wav16", "tone16.wav", "PCM_16"),
        ("wav24", "tone24.wav", "PCM_24"),
        ("mp3", "tone.mp3", None),
    ]:
        path = d / name
        sf.write(path, stereo, sr, subtype=subtype)
        files[key] = path
    garbage = d / "garbage.m4a"
    garbage.write_bytes(b"not audio at all")
    files["garbage"] = garbage
    return files


def wait_until(predicate, timeout_ms=10000):
    """Spin the Qt event loop until predicate() is true or timeout."""
    if predicate():
        return True
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(50)
    poll.timeout.connect(lambda: predicate() and loop.quit())
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(timeout_ms)
    loop.exec()
    return predicate()
