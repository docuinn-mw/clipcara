import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

from player.timeline import Timeline


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
