import numpy as np
import pytest
import soundfile as sf

from clipcara.player import export_region


def test_export_region_roundtrip(tone_files, tmp_path):
    dst = tmp_path / "clip.wav"
    export_region(str(tone_files["wav16"]), str(dst), 1000, 2500)
    data, sr = sf.read(dst, always_2d=True)
    assert sr == 44100
    assert data.shape == (int(1.5 * sr), 2)
    # same 0.5-amplitude sine content
    rms = np.sqrt((data ** 2).mean())
    assert 0.3 < rms < 0.4


def test_export_preserves_subtype(tone_files, tmp_path):
    dst = tmp_path / "clip24.wav"
    export_region(str(tone_files["wav24"]), str(dst), 0, 1000)
    assert sf.info(dst).subtype == "PCM_24"


def test_export_clamps_to_file_end(tone_files, tmp_path):
    dst = tmp_path / "tail.wav"
    export_region(str(tone_files["wav16"]), str(dst), 4000, 99000)
    assert sf.info(dst).frames == 44100  # last second only


def test_export_empty_region_raises(tone_files, tmp_path):
    with pytest.raises(ValueError):
        export_region(str(tone_files["wav16"]), str(tmp_path / "x.wav"),
                      3000, 3000)
