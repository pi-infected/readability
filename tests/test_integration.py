import json
from pathlib import Path

import pytest

from readability_audit.analysis import analyse_page
from readability_audit.fetch import Page

FIXTURE = Path(__file__).parent / "fixtures" / "sample.html"


def _page():
    return Page(FIXTURE.as_uri(), FIXTURE.as_uri(), 200, FIXTURE.read_text(encoding="utf8"))


def test_static_analysis_end_to_end():
    pa = analyse_page(_page())
    assert pa.ok
    assert pa.lang_used == "en"
    assert pa.structure.h1_count == 1
    assert pa.structure.n_paragraphs >= 3
    assert pa.counts["words"] > 50
    assert "lix" in pa.formulas
    assert 0 <= pa.scores.overall <= 100
    assert pa.scores.grade in "ABCDEF"


def test_footer_is_not_counted_as_content():
    pa = analyse_page(_page())
    assert "Footer text" not in pa.structure.title
    joined = " ".join(h["text"] for h in pa.hardest_paragraphs)
    assert "Footer text" not in joined


def test_serialisation_is_json_safe():
    from readability_audit.report.serialize import page_to_dict
    d = page_to_dict(analyse_page(_page()))
    json.dumps(d)                     # must not raise
    assert d["score"] is not None
    assert d["metrics"] and d["structure"]["word_count"] > 0


def test_audience_profiles_change_targets():
    from readability_audit.scoring import build_metrics
    pa = analyse_page(_page())
    gen = {m.key: m.ideal for m in build_metrics(pa, "general")}
    kid = {m.key: m.ideal for m in build_metrics(pa, "children")}
    assert gen["lix"] != kid["lix"]


@pytest.mark.render
def test_rendered_metrics_and_reports(tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from readability_audit.render import Renderer
    with Renderer(viewports={"desktop": (1440, 900)}, check_dark=False) as r:
        if r.error:
            pytest.skip(r.error)
        rr = r.render(FIXTURE.as_uri())
    assert rr.ok, rr.error
    pa = analyse_page(_page(), render_result=rr)
    vp = pa.typography.primary
    assert vp.body_font_px == pytest.approx(16, abs=0.5)
    assert 1.5 <= vp.line_height_ratio <= 1.7
    assert vp.chars_per_line > 20
    # the .faint caption is #bbb on white: it must be caught
    assert any(f["ratio"] < 4.5 for f in vp.contrast_failures)

    class Rep:
        base_url = "test"
        started_at = "now"
        duration_s = 0.1
        options = {"audience": "general", "version": "test"}
        pages = [pa]
        summary = {}
        consistency = {}
        top_findings = []
        errors = []

    from readability_audit.site import aggregate_findings, consistency
    rep = Rep()
    rep.consistency = consistency([pa])
    rep.top_findings = aggregate_findings([pa])
    rep.summary = {"pages_analysed": 1, "score": pa.scores.overall, "grade": pa.scores.grade,
                   "mean_page_score": pa.scores.overall, "worst_page_score": pa.scores.overall,
                   "best_page_score": pa.scores.overall, "consistency_score": 100,
                   "pillars": {k: v["score"] for k, v in pa.scores.pillars.items()},
                   "page_types": {pa.scores.page_type: 1}, "total_words": 100,
                   "reading_time_min": 1, "severity_counts": {}, "rendered": 1}

    from readability_audit.report.html_report import build_html
    html = build_html(rep, lang="fr", detail=1)
    assert "Audit de lisibilité" in html and "<table" in html

    from readability_audit.report.pdf import write_pdf
    out = write_pdf(html, tmp_path / "r.pdf")
    assert out.exists() and out.stat().st_size > 5000


def test_concurrency_is_clamped_to_free_memory(monkeypatch):
    from readability_audit import render as R
    monkeypatch.setattr(R, "available_mb", lambda: 1000)      # floor 800 leaves 200 MB
    n, note = R.safe_concurrency(8)
    assert n == 1 and "one page at a time" in note
    monkeypatch.setattr(R, "available_mb", lambda: 1400)      # 600 MB of budget
    n, note = R.safe_concurrency(8)
    assert n == 2 and "reduced 8 to 2" in note
    monkeypatch.setattr(R, "available_mb", lambda: 8000)
    assert R.safe_concurrency(4)[0] == 4
    monkeypatch.setattr(R, "available_mb", lambda: None)
    assert R.safe_concurrency(3)[0] == 3                      # unknown: honour the request
    assert R.safe_concurrency(99)[0] <= R.MAX_CONCURRENCY


def test_memory_estimate_is_base_plus_marginal():
    from readability_audit.render import estimated_mb
    assert estimated_mb(1) < estimated_mb(2) < estimated_mb(4)
    assert estimated_mb(4) - estimated_mb(3) == estimated_mb(3) - estimated_mb(2)


def test_rendered_dom_is_preferred_over_the_served_html():
    """A client-rendered page must be measured on what the reader sees, not on the shell."""
    from readability_audit.analysis import analyse_page
    from readability_audit.fetch import Page

    shell = ('<html lang="en"><head><title>Shell</title></head><body>'
             '<div id="root"></div><script>/* builds the page */</script></body></html>')
    rendered = ('<html lang="en"><head><title>Shell</title></head><body><div id="root"><main>'
                '<h1>Built by script</h1>'
                '<p>This paragraph exists only after the script has run, and it carries enough '
                'running text for the language metrics to have something real to measure.</p>'
                '<p>A second paragraph, so the structure metrics see a document rather than a '
                'single stray run of text sitting on its own in an empty shell.</p>'
                '</main></div></body></html>')

    class RR:
        ok = True
        html = rendered
        viewports = {}
        screenshots = {}
        dark_mode = None
        error = None

    served_only = analyse_page(Page("http://x/", "http://x/", 200, shell))
    assert served_only.structure.prose_word_count == 0

    both = analyse_page(Page("http://x/", "http://x/", 200, shell), render_result=RR())
    assert both.structure.prose_word_count > 40
    assert both.extraction["source"] == "rendered DOM"
    assert both.extraction["content_needs_js"] is True
    assert both.extraction["opening_paragraphs_served"] == 0
    assert any(f.key == "js_dependent_text" and f.severity == "high" for f in both.findings)


def test_server_rendered_page_is_not_flagged_as_js_dependent():
    from readability_audit.analysis import analyse_page
    from readability_audit.fetch import Page
    page_html = FIXTURE.read_text(encoding="utf8")

    class RR:
        ok = True
        html = page_html
        viewports = {}
        screenshots = {}
        dark_mode = None
        error = None

    pa = analyse_page(Page("http://x/", "http://x/", 200, page_html), render_result=RR())
    assert pa.extraction["source"] == "served HTML"
    assert pa.extraction["content_needs_js"] is False
    assert not any(f.key == "js_dependent_text" for f in pa.findings)


def test_machine_output_is_not_scored_as_prose():
    """A terminal demo on a marketing page must not be measured as writing."""
    from readability_audit.analysis import analyse_page
    from readability_audit.fetch import Page
    demo = " ".join(
        '{"type":"tool_use","name":"Read","input":{"file_path":"src/handlers/session.ts"}}'
        for _ in range(6))
    html = ('<html lang="en"><body><main>'
            '<h1>A page with a terminal demo</h1>'
            '<p>This paragraph is ordinary prose and it should be measured as such, because '
            'it is written for a reader and it reads like a sentence that a person wrote.</p>'
            '<p>A second real paragraph, so that the document has enough running text for the '
            'language metrics to work with once the demo below has been set aside.</p>'
            f'<p>{demo}</p></main></body></html>')
    pa = analyse_page(Page("http://x/", "http://x/", 200, html))
    assert pa.extraction["machine_blocks_dropped"] == 1
    assert "tool_use" not in pa.structure.title
    joined = " ".join(h["text"] for h in pa.hardest_paragraphs)
    assert "tool_use" not in joined
    assert any(f.key == "machine_output" for f in pa.findings)


def test_reports_in_every_language_come_from_one_crawl(tmp_path):
    """Two languages must never describe two different crawls."""
    from readability_audit.report.html_report import build_html
    from readability_audit.report.serialize import site_to_dict

    pa = analyse_page(_page())

    class Rep:
        base_url = "https://example.test"
        started_at = "2026-01-01T00:00:00Z"
        duration_s = 1.0
        options = {"audience": "general", "version": "test"}
        pages = [pa]
        consistency = {}
        top_findings = []
        errors = []
        summary = {"pages_analysed": 1, "score": pa.scores.overall, "grade": pa.scores.grade,
                   "mean_page_score": pa.scores.overall, "worst_page_score": pa.scores.overall,
                   "best_page_score": pa.scores.overall, "consistency_score": 100,
                   "pillars": {k: v["score"] for k, v in pa.scores.pillars.items()},
                   "page_types": {pa.scores.page_type: 1}, "total_words": 100,
                   "reading_time_min": 1, "severity_counts": {}, "rendered": 0,
                   "coverage": {"discovered": 1, "analysed": 1, "scored": 1,
                                "unscorable": 0, "failed": 0, "rendered": 0}}

    rep = Rep()
    from readability_audit.site import consistency
    rep.consistency = consistency([pa])
    data = site_to_dict(rep)
    import json as _json
    en = build_html(rep, lang="en", detail=1, data=_json.loads(_json.dumps(data)))
    fr = build_html(rep, lang="fr", detail=1, data=_json.loads(_json.dumps(data)))
    assert rep.started_at in en and rep.started_at in fr
    assert en.count('class="page-sec"') == fr.count('class="page-sec"')
    assert "Coverage" in en and "Couverture" in fr
    # localisation must not leak between renders
    assert "Audit de lisibilité" not in en and "Readability audit" not in fr


def test_the_json_is_self_describing():
    from readability_audit.report.serialize import site_to_dict

    pa = analyse_page(_page())

    class Rep:
        base_url = "https://example.test"
        started_at = "now"
        duration_s = 1.0
        options = {"audience": "general", "version": "test"}
        pages = [pa]
        consistency = {}
        top_findings = []
        errors = []
        summary = {"coverage": {"discovered": 1, "analysed": 1, "scored": 1,
                                "unscorable": 0, "failed": 0, "rendered": 0}}

    d = site_to_dict(Rep(), artifacts=[{"role": "data", "format": "json", "path": "x.json"}])
    for key in ("schema_version", "coverage", "scoring", "methodology", "validation",
                "artifacts", "pages"):
        assert key in d, f"missing {key}"
    assert d["methodology"], "no metric definitions"
    # each metric is documented once, not repeated per page
    keys = [m["key"] for m in d["methodology"]]
    assert len(keys) == len(set(keys))
    assert d["validation"]["difficulty"]["pairs"]["total"] > 0


def test_browser_reported_overlays_are_stripped_from_the_content():
    """A cookie wall styled `div.fixed` carries no name a regex could catch."""
    from readability_audit.extract import parse
    # The overlay sits inside the content region, which is where it actually lands and
    # the only arrangement in which stripping it means anything.
    html = ('<html lang="en"><body><main>'
            '<p>The real article paragraph, long enough to be measured as running text by '
            'every one of the language metrics that read this document.</p>'
            '<div class="fixed inset-x-0 bottom-0 z-[60] border-t"><p>We use optional '
            'marketing-measurement cookies to understand how visitors find us.</p></div>'
            '</main></body></html>')
    hints = [{"tag": "div", "cls": "fixed inset-x-0 bottom-0 z-[60] border-t", "area": 0.07}]
    assert "cookies" in parse(html, "http://x/").text
    assert "cookies" not in parse(html, "http://x/", overlay_hints=hints).text


def test_an_offsite_redirect_is_not_audited_as_part_of_the_site():
    """`/go/partner` redirects are how a site links out. Their target is not its page."""
    from readability_audit.fetch import same_site
    assert same_site("https://a.com/", "https://www.a.com/x")
    assert not same_site("https://a.com/", "https://b.com/")


def test_canonical_and_identical_bodies_identify_a_duplicate():
    """No page is analysed twice, whichever way the duplicate arrives."""
    from readability_audit.site import canonical_of
    html = '<html><head><link rel="canonical" href="/en/x"/></head><body>hi</body></html>'
    assert canonical_of(html, "https://a.com/en/x?utm_source=nl") == "https://a.com/en/x"
    assert canonical_of(html, "https://a.com/en/x/") == "https://a.com/en/x"
    assert canonical_of("<html><head></head></html>", "https://a.com/") is None
