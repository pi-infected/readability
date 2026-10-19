import json
from pathlib import Path

import pytest

from readability_audit.cli import main
from readability_audit.select import METRICS, Selection, SelectionError

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
    src = (Path(__file__).parents[1] / "src/readability_audit/scoring.py").read_text()
    assert set(re.findall(r'_m\("([a-z_]+)"', src)) == set(METRICS)


def test_diff_ignores_pillars_one_run_did_not_measure():
    from readability_audit.compare import diff

    def run(pillars, findings, sel):
        return {"summary": {"score": 80, "pillars": pillars}, "options": {"selection": sel},
                "top_findings": [{"key": k, "pillar": p, "title": k, "affected_pages": 1,
                                  "severity": "high"} for k, p in findings],
                "pages": [{"url": "u", "score": 80,
                           "pillars": {k: {"score": v} for k, v in pillars.items()}}]}
    full = run({"clarity": 80, "structure": 90}, [("lix", "clarity"), ("title_length", "structure")],
               {"only": [], "skip": []})
    narrow = run({"clarity": 85}, [], {"only": ["clarity"], "skip": []})
    d = diff(full, narrow)
    assert d["pillar_delta"] == {"clarity": 5} and d["pillars_not_compared"] == ["structure"]
    assert [r["key"] for r in d["resolved"]] == ["lix"] and d["selection_changed"]
    assert d["pages"][0]["pillars"] == {"clarity": 5}
