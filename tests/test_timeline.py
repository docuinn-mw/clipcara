import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

from clipcara.timeline import Timeline


@pytest.fixture
def tl(qapp):
    t = Timeline()
    t.resize(800, 220)
    t.set_duration(5000)
    t.show()
    yield t
    t.close()


def test_x_to_ms_clamps(tl):
    assert tl._x_to_ms(tl.width() * 3) == 5000
    assert tl._x_to_ms(-50) == 0


def test_jitter_click_creates_no_region(tl):
    regions = []
    tl.regionSelected.connect(lambda a, b: regions.append((a, b)))
    QTest.mousePress(tl, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(tl, QPoint(101, 100))
    QTest.mouseRelease(tl, Qt.MouseButton.LeftButton, pos=QPoint(101, 100))
    assert regions == []


def test_drag_creates_region(tl):
    regions = []
    tl.regionSelected.connect(lambda a, b: regions.append((a, b)))
    QTest.mousePress(tl, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
    QTest.mouseMove(tl, QPoint(300, 100))
    QTest.mouseRelease(tl, Qt.MouseButton.LeftButton, pos=QPoint(300, 100))
    assert len(regions) == 1
    a, b = regions[0]
    assert 0 < a < b <= 5000


def test_click_seeks(tl):
    seeks = []
    tl.seekRequested.connect(seeks.append)
    QTest.mouseClick(tl, Qt.MouseButton.LeftButton, pos=QPoint(400, 100))
    assert seeks and 0 < seeks[0] < 5000


def test_zoom_to_and_full(tl):
    tl.set_duration(60000)
    tl.zoom_to(10000, 20000)
    assert 8000 < tl.view_start < 10000
    assert 20000 < tl.view_end < 22000
    # mapping now covers only the view
    assert tl._x_to_ms(0) == tl.view_start
    assert tl._x_to_ms(tl.width()) == tl.view_end
    tl.zoom_full()
    assert tl.view_start == 0 and tl.view_end == 60000


def test_view_clamps_to_file(tl):
    tl.set_duration(60000)
    tl._set_view(55000, 65000)  # would extend past the end
    assert tl.view_end == 60000 and tl.view_start == 50000
    tl._set_view(-5000, 5000)
    assert tl.view_start == 0 and tl.view_end == 10000


def test_view_follows_playhead(tl):
    tl.set_duration(60000)
    tl._set_view(10000, 20000)
    tl.set_position(25000)  # beyond the right edge
    assert tl.view_start <= 25000 <= tl.view_end
    tl.set_position(2000)  # loop wrap back before the view
    assert tl.view_start <= 2000 <= tl.view_end


def test_view_change_emits_signal(tl):
    tl.set_duration(60000)
    views = []
    tl.viewChanged.connect(lambda s, e: views.append((s, e)))
    tl.zoom_to(10000, 20000)
    assert len(views) == 1
    s, e = views[0]
    assert s < 10000 and e > 20000
