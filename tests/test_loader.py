import numpy as np
import pytest

from clipcara.player import WaveformLoader
from clipcara.timeline import fmt_time


def test_fmt_time():
    assert fmt_time(None) == "--:--"
    assert fmt_time(-1) == "--:--"
    assert fmt_time(83500) == "01:23"
    assert fmt_time(75 * 60000) == "1:15:00"


@pytest.mark.parametrize("key", ["wav16", "wav24", "mp3"])
def test_peaks(tone_files, key):
    peaks, s_ms, e_ms = WaveformLoader(str(tone_files[key]))._compute_peaks()
    assert s_ms == 0
    assert 4900 <= e_ms <= 5200
    assert peaks.ndim == 2 and peaks.shape[1] == 3
    assert len(peaks) > 1000
    # envelope of a 0.5-amplitude sine (mp3 may overshoot slightly)
    assert 0.4 < peaks[:, 1].max() < 0.6
    assert -0.6 < peaks[:, 0].min() < -0.4
    # rms of a full-bin sine is amplitude / sqrt(2); mean over all bins
    # stays close even with codec padding at the edges
    assert 0.2 < peaks[:, 2].mean() < 0.5
    assert not np.isnan(peaks).any()


def test_undecodable_file_raises(tone_files):
    with pytest.raises(Exception):
        WaveformLoader(str(tone_files["garbage"]))._compute_peaks()


def test_cancel_returns_none(tone_files):
    loader = WaveformLoader(str(tone_files["wav16"]))
    loader.cancel()
    assert loader._compute_peaks() is None


def test_view_slice_peaks(tone_files):
    loader = WaveformLoader(str(tone_files["wav16"]),
                            start_ms=1000, end_ms=2000, bins=100)
    peaks, s_ms, e_ms = loader._compute_peaks()
    assert (s_ms, e_ms) == (1000, 2000)
    assert len(peaks) == 100
    # every bin of a continuous 0.5 sine reaches the envelope
    assert 0.45 < peaks[:, 1].min() < 0.55
    assert 0.3 < peaks[:, 2].mean() < 0.4
