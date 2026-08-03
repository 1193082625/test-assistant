import pytest

from app.composition import cover_canvas, cover_ratio


def test_legacy_canvas_size():
    assert cover_canvas() == (800, 1200)


def test_legacy_canvas_ratio():
    assert cover_ratio() == pytest.approx(2 / 3)
