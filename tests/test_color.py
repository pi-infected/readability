import pytest

from readlens.color import apca, blend, contrast_ratio, parse, wcag_level

W, K = parse("#ffffff"), parse("#000000")


def test_parse_forms():
    assert parse("#fff") == (255, 255, 255, 1.0)
    assert parse("rgb(1, 2, 3)") == (1.0, 2.0, 3.0, 1.0)
    assert parse("rgba(1, 2, 3, 0.5)")[3] == 0.5
    assert parse("transparent")[3] == 0.0
    assert parse("nonsense") is None


def test_wcag_reference_values():
    assert contrast_ratio(K, W) == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio(parse("#777777"), W) == pytest.approx(4.48, abs=0.01)
    assert contrast_ratio(W, W) == pytest.approx(1.0, abs=0.001)


def test_apca_reference_values():
    # published APCA-W3 reference pairs
    assert apca(K, W) == pytest.approx(106.0, abs=0.3)
    assert apca(W, K) == pytest.approx(-107.9, abs=0.3)


def test_apca_polarity():
    assert apca(K, W) > 0 and apca(W, K) < 0


def test_alpha_blend():
    half = parse("rgba(0,0,0,0.5)")
    assert blend(half, W)[0] == pytest.approx(127.5)
    assert 3.0 < contrast_ratio(half, W) < 5.0


def test_wcag_levels():
    assert wcag_level(4.6, 16) == "AA"
    assert wcag_level(7.5, 16) == "AAA"
    assert wcag_level(3.2, 16) == "fail"
    assert wcag_level(3.2, 24) == "AA"          # large text threshold
