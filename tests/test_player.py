from PyQt6.QtMultimedia import QMediaPlayer

from clipcara.player import AudioPlayer


def make_player(qapp):
    p = AudioPlayer()
    p.set_marks(1000, 3000)
    p.loop_enabled = True
    return p


def test_position_past_b_loops_to_a(qapp):
    p = make_player(qapp)
    seeks = []
    p._player.setPosition = seeks.append
    p._on_position_changed(3050)
    assert seeks == [1000]


def test_enabling_loop_beyond_b_snaps(qapp):
    p = make_player(qapp)
    seeks = []
    p._player.setPosition = seeks.append
    p._on_position_changed(4500)
    assert seeks == [1000]


def test_inside_region_does_not_snap(qapp):
    p = make_player(qapp)
    seeks = []
    p._player.setPosition = seeks.append
    p._on_position_changed(2000)
    assert seeks == []


def test_loop_off_never_snaps(qapp):
    p = make_player(qapp)
    p.loop_enabled = False
    seeks = []
    p._player.setPosition = seeks.append
    p._on_position_changed(4500)
    assert seeks == []


def test_end_of_media_restarts_loop(qapp):
    p = make_player(qapp)
    seeks, plays = [], []
    p._player.setPosition = seeks.append
    p._player.play = lambda: plays.append(1)
    p._on_media_status(QMediaPlayer.MediaStatus.EndOfMedia)
    assert seeks == [1000] and plays == [1]


def test_end_of_media_without_loop_stops(qapp):
    p = make_player(qapp)
    p.loop_enabled = False
    seeks = []
    p._player.setPosition = seeks.append
    p._on_media_status(QMediaPlayer.MediaStatus.EndOfMedia)
    assert seeks == []
