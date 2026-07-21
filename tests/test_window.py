import pytest

from clipcara.main_window import MainWindow
from tests.conftest import wait_until


@pytest.fixture
def win(qapp):
    w = MainWindow()
    w.resize(850, 480)
    w.show()
    yield w
    w.player.shutdown()
    w.close()


def test_initial_volume_matches_slider(win):
    assert abs(win.player._audio_output.volume() - 0.7) < 1e-6


def test_open_loads_duration_and_waveform(win, tone_files):
    win._open_file(str(tone_files["wav16"]))
    assert wait_until(lambda: win.player.duration > 0)
    assert wait_until(lambda: win.timeline.peaks is not None)
    assert len(win.timeline.waveform_peaks) > 0


def test_open_resets_marks_and_loop(win, tone_files):
    win._apply_marks(1000, 2000)
    win.player.loop_enabled = True
    win.loop_btn.setChecked(True)
    win._open_file(str(tone_files["wav16"]))
    assert win.player.mark_a is None and win.player.mark_b is None
    assert not win.player.loop_enabled
    assert not win.loop_btn.isChecked()


def _fake_position(win, ms, duration=5000):
    win.player._player.position = lambda: ms
    win.player._player.duration = lambda: duration


def test_mark_ordering(win):
    _fake_position(win, 2000)
    win._on_mark_a()
    assert win.player.mark_a == 2000 and win.player.mark_b is None

    _fake_position(win, 4000)
    win._on_mark_b()
    assert win.player.mark_a == 2000 and win.player.mark_b == 4000

    # a new In at/after the Out starts a fresh selection
    _fake_position(win, 4500)
    win._on_mark_a()
    assert win.player.mark_a == 4500 and win.player.mark_b is None

    # a new Out at/before the In starts a fresh selection
    _fake_position(win, 1000)
    win._on_mark_b()
    assert win.player.mark_b == 1000 and win.player.mark_a is None
    assert win.timeline.mark_a is None and win.timeline.mark_b == 1000


def test_region_select_enables_loop(win):
    win._on_region_selected(500, 1500)
    assert win.player.loop_enabled
    assert win.loop_btn.isChecked()
    assert win.player.mark_a == 500 and win.player.mark_b == 1500


def test_nudge_marks(win):
    _fake_position(win, 2000)
    win._on_mark_a()
    _fake_position(win, 4000)
    win._on_mark_b()

    win._nudge_mark("a", 50)
    assert win.player.mark_a == 2050
    win._nudge_mark("a", -100)
    assert win.player.mark_a == 1950
    win._nudge_mark("b", -50)
    assert win.player.mark_b == 3950

    win._nudge_mark("a", 99999)  # clamps at B
    assert win.player.mark_a == 3950
    win._nudge_mark("b", -99999)  # clamps at A
    assert win.player.mark_b == 3950
    win._nudge_mark("b", 99999)  # clamps at duration
    assert win.player.mark_b == 5000


def test_nudge_without_mark_is_noop(win):
    win._nudge_mark("a", 50)
    assert win.player.mark_a is None


def test_saved_loops_roundtrip(win, tone_files, tmp_path, monkeypatch):
    from clipcara.loops import LoopStore
    win.loop_store = LoopStore(str(tmp_path / "loops.json"))
    win._open_file(str(tone_files["wav16"]))
    assert not win.loop_combo.isEnabled()

    win._apply_marks(1000, 2500)
    monkeypatch.setattr("clipcara.main_window.QInputDialog.getText",
                        staticmethod(lambda *a, **k: ("my loop", True)))
    win._on_save_loop()
    assert win.loop_combo.count() == 1
    assert "my loop" in win.loop_combo.itemText(0)

    # clearing marks then recalling the loop restores and enables it
    win._on_clear_marks()
    win._on_loop_selected(0)
    assert win.player.mark_a == 1000 and win.player.mark_b == 2500
    assert win.player.loop_enabled

    win._on_delete_loop()
    assert win.loop_combo.count() == 0
    assert win.loop_store.loops_for(str(tone_files["wav16"])) == []


def test_loop_selection_seeks_into_loop(win, tone_files, tmp_path):
    from clipcara.loops import LoopStore
    win.loop_store = LoopStore(str(tmp_path / "loops.json"))
    win._open_file(str(tone_files["wav16"]))
    win.loop_store.add(str(tone_files["wav16"]), "x", 1000, 2500)
    win._refresh_loops()
    win._on_duration_changed(5000)  # media duration arrives async

    seeks = []
    win.player._player.setPosition = seeks.append
    win._on_loop_selected(0)
    assert 1000 in seeks  # playback jumps to the loop's A
    assert win.timeline.position == 1000  # UI reflects it immediately
    # playhead sits inside the zoomed view, so view-follow won't page away
    assert win.timeline.view_start <= 1000 <= win.timeline.view_end
    assert win.player.loop_enabled


def test_speed_steps_and_clamps(win):
    win._set_speed(1.0)
    win._change_speed(0.05)
    assert abs(win.player.playback_rate - 1.05) < 1e-4
    assert win.speed_label.text() == "1.05x"
    win._change_speed(0.05)  # stepping from the float32 value Qt returns
    assert win.speed_label.text() == "1.10x"
    win._set_speed(9.9)
    assert win.speed_label.text() == "2.00x"
    win._set_speed(0.1)
    assert win.speed_label.text() == "0.50x"
