"""Data checks found by auditing a whole real site (tokenade.net, 478 pages)."""
import pytest

from readability_audit.report.serialize import methodology
from readability_audit.scoring import Metric
from readability_audit.site import aggregate_findings

LOREM = ("Readers lose their place when a line runs too long, and they tire when it is too "
         "short, so the column is set to hold a comfortable number of characters per line. ")


def _page(tmp_path, body):
    f = tmp_path / "p.html"
    f.write_text(f"<html lang=en><body style='margin:0;font:16px/26px sans-serif'><main>{body}"
                 "</main></body></html>")
    return f.as_uri()


def _probe(uri):
    from readability_audit.render import Renderer
    with Renderer({"desktop": (1440, 900)}, check_dark=False, concurrency=1) as r:
        if r.error:
            pytest.skip(r.error)
        return r.render(uri).viewports["desktop"]


@pytest.mark.render
def test_line_length_ignores_inline_code_and_wrap_position(tmp_path):
    code = "<code style='padding:3px 6px;font-size:14px'>tokenade wrap</code>"
    v = _probe(_page(tmp_path, f"<p style='width:600px'>{LOREM} {code} {LOREM}</p>"))
    e = max(v["elements"], key=lambda e: e["chars"])
    # ~600px of 16px sans is 70-80 characters; chars/lines would read it as 60-ish.
    assert 65 <= e["charsPerLine"] <= 90, e


@pytest.mark.render
def test_paragraph_gap_skips_blocks_between_paragraphs(tmp_path):
    body = (f"<p style='margin:0 0 13px'>{LOREM}</p><pre style='height:300px'>x</pre>"
            f"<p style='margin:0 0 13px'>{LOREM}</p><p style='margin:0'>{LOREM}</p>")
    gaps = _probe(_page(tmp_path, body))["paragraphGaps"]
    assert gaps and max(gaps) < 1.0, gaps


def test_page_measure_is_the_main_column_not_the_longest_block():
    from readability_audit.metrics.typography import analyse

    class R:
        ok, error, dark_mode = True, None, None

        def __init__(self, els):
            self.viewports = {"desktop": {"elements": els, "counts": {}}}

    def el(width, cpl, chars):
        return {"tag": "p", "chars": chars, "widthPx": width, "charsPerLine": cpl, "lines": 4,
                "fontPx": 16, "lineHeightRatio": 1.6, "align": "left", "text": "x",
                "color": "rgb(0, 0, 0)", "bgLayers": ["rgb(255, 255, 255)"], "words": chars // 6,
                "letterSpacing": 0, "wordSpacing": 0, "transform": "none", "hyphens": "manual",
                "lineHeightPx": 26, "weight": 400, "family": "Inter", "generic": "sans",
                "heightPx": 104, "top": 0, "marginTop": 0, "marginBottom": 16, "links": [],
                "opacity": 1, "cls": "", "textWrap": ""}
    # one 926px intro paragraph, then the article in a 418px column
    t = analyse(R([el(926, 124, 370)] + [el(418, 58, 250)] * 6))
    assert t.primary.chars_per_line == 58


def test_aggregated_finding_says_how_many_pages_share_the_worst_severity():
    class F:
        def __init__(self, sev):
            self.key, self.title, self.severity, self.pillar = "connectives", "T", sev, "clarity"
            self.fix, self.detail, self.evidence, self.params = "f", "d", [], {}

    class P:
        def __init__(self, url, sev):
            self.final_url = self.url = url
            self.findings, self.ok = [F(sev)], True
    agg = aggregate_findings([P("a", "critical")] + [P(str(i), "medium") for i in range(9)])[0]
    assert agg["severity"] == "critical" and agg["affected_pages"] == 10
    assert agg["pages_by_severity"] == {"critical": 1, "medium": 9}


def test_displays_are_rounded():
    m = Metric("diversity", "d", "clarity", 0.737778, "ratio", (0.5, 0.9), (0.4, 1)).finalise()
    assert m.display == "0.738 ratio"


def test_methodology_keeps_the_advice_pages_no_longer_repeat():
    pages = [{"page_type": "article", "metrics": [
        {"key": "lix", "label": "L", "pillar": "clarity", "unit": "", "why": "w", "advice": "a",
         "ideal": [1, 2], "tolerable": [0, 3], "weight": 1}]}]
    assert methodology(pages)[0]["advice"] == "a"


@pytest.mark.render
def test_pages_without_paragraph_tags_are_still_measured(tmp_path):
    # Text in bare <div>s, and a <main> that holds only a collapsed menu.
    body = (f"<div style='width:600px'>{LOREM}</div><div style='width:600px'>{LOREM}</div>"
            "<ul style='display:none'><li>Home</li><li>Docs</li></ul>")
    f = tmp_path / "d.html"
    f.write_text(f"<html lang=en><body style='font:16px/26px sans-serif'><main>"
                 f"<ul hidden><li>Menu</li></ul></main>{body}</body></html>")
    els = _probe(f.as_uri())["elements"]
    assert sum(e["chars"] for e in els) > 300, els
