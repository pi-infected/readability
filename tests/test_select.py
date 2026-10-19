import json
from pathlib import Path

import pytest

from readlens.cli import main
from readlens.select import METRICS, Selection, SelectionError

SAMPLE = Path(__file__).parent / "fixtures" / "sample.html"


def test_html_only_selection_skips_the_browser():
    sel = Selection.parse(["clarity,structure"])
    assert not sel.needs_render
    assert not Selection.parse(["access"], ["rem_scaling"]).needs_render


def test_contrast_needs_desktop_only():
    sel = Selection.parse(["contrast"])
    assert sel.needs_render and not sel.needs_mobile
    assert set(sel.viewports({"desktop": 1, "mobile": 2})) == {"desktop"}
    assert sel.finding_ok("contrast_fail", "comfort")
    assert not sel.finding_ok("overflow_mobile", "comfort")
    assert not sel.metric_ok("lix", "clarity")


def test_skip_mobile_keeps_the_rest_of_comfort():
    sel = Selection.parse(skip=["mobile"])
    assert sel.metric_ok("font_size", "comfort") and not sel.metric_ok("mobile_font", "comfort")
    assert not sel.needs_mobile and sel.needs_render


def test_everything_by_default():
    sel = Selection.parse()
    assert sel.everything and sel.needs_mobile and sel.check_dark


def test_unknown_selector_is_an_error():
    with pytest.raises(SelectionError):
        Selection.parse(["contrats"])


def test_text_command_honours_only(capsys):
    assert main(["text", str(SAMPLE), "--only", "readability"]) == 0
    out = json.loads(capsys.readouterr().out)
    keys = {m["key"] for m in out["metrics"]}
    assert keys and keys <= {"lix", "flesch", "asl", "long_sentences", "polysyllabic"}
    assert all(f["pillar"] == "clarity" for f in out["findings"]
               if f["key"] in METRICS)


def test_metrics_command_json(capsys):
    assert main(["metrics", "--format", "json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert {m["key"] for m in out["metrics"]} == set(METRICS)


def test_catalog_matches_scoring():
    import re
    src = (Path(__file__).parents[1] / "src/readlens/scoring.py").read_text()
    assert set(re.findall(r'_m\("([a-z_]+)"', src)) == set(METRICS)
