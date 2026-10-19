import pytest

from readability_audit.scoring import band_score, grade_of


def test_band_score_inside_ideal():
    assert band_score(10, (5, 15), (0, 20)) == 100


def test_band_score_at_tolerable_edge():
    assert band_score(0, (5, 15), (0, 20)) == pytest.approx(60)
    assert band_score(20, (5, 15), (0, 20)) == pytest.approx(60)


def test_band_score_falls_to_zero_one_span_beyond():
    assert band_score(25, (5, 15), (0, 20)) == pytest.approx(0, abs=0.01)
    assert band_score(-5, (5, 15), (0, 20)) == pytest.approx(0, abs=0.01)
    assert band_score(100, (5, 15), (0, 20)) == 0


def test_band_score_monotonic():
    vals = [band_score(v, (5, 15), (0, 20)) for v in range(0, 6)]
    assert vals == sorted(vals)


def test_grades():
    assert grade_of(95) == "A"
    assert grade_of(80) == "B"
    assert grade_of(70) == "C"
    assert grade_of(10) == "F"
