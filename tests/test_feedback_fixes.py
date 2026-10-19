"""Regressions for the false positives two site owners reported from real audits.

Each test names the symptom that was seen in a delivered report.
"""
import pytest

from readlens.color import apca_min_lc
from readlens.extract import flat_text, parse
from readlens.fetch import looks_like_page
from readlens.lang import pack
from readlens.text import sentences

EN = pack("en")


# --- reported: "PowerInvsSayWhatObjective" counted as a word ------------------
def test_block_boundaries_do_not_glue_words():
    import lxml.html
    el = lxml.html.fromstring(
        "<a><div><h3>PowerIn</h3><span>vs</span><h3>SayWhat</h3>"
        "<p>Objective comparison between them.</p></div></a>")
    words = flat_text(el).split()
    assert "PowerIn" in words and "SayWhat" in words and "vs" in words, words
    assert all(len(w) < 20 for w in words), words


def test_inline_markup_is_not_broken_apart():
    import lxml.html
    el = lxml.html.fromstring("<p>an <em>anti</em>pattern stays one word</p>")
    assert "antipattern" in flat_text(el)


# --- reported: three sentences counted as one 86-word sentence ---------------
@pytest.mark.parametrize("text,n", [
    ("Two head-to-heads are worth reading. rtk vs token-optimizer puts a filter "
     "against an index. graphify goes further than that.", 3),
    ("Dr. Smith paid on Jan. 3. He said e.g. this works! Yes... it does.", 3),
    ("The U.S. dollar fell. Then it rose.", 2),
])
def test_a_sentence_may_open_with_a_lowercase_word(text, n):
    assert len(sentences(text, EN)) == n


# --- reported: apca_required identical for 14px and 16px ---------------------
def test_apca_requirement_falls_with_size_and_with_weight():
    sizes = [12, 14, 16, 18, 24, 36]
    req = [apca_min_lc(s, 400) for s in sizes]
    assert req == sorted(req, reverse=True), req
    for s in sizes:
        assert apca_min_lc(s, 400) > apca_min_lc(s, 700), s
    assert apca_min_lc(14, 400) > apca_min_lc(16, 400)


# --- reported: /api/checkout audited for typography, twice ------------------
@pytest.mark.parametrize("url,ok", [
    ("https://a.com/api/checkout?plan=pro", False),
    ("https://a.com/_next/static/x", False),
    ("https://a.com/cdn-cgi/l/email-protection", False),
    ("https://a.com/en/pricing", True),
    ("https://a.com/en/post.html", True),
])
def test_application_endpoints_are_not_content(url, ok):
    assert looks_like_page(url) is ok


# --- reported: reported URL was "?plan=pro&amp;locale=en" -------------------
def test_hrefs_are_entity_decoded():
    from html import unescape
    assert unescape("/api/x?a=1&amp;b=2") == "/api/x?a=1&b=2"
    d = parse('<html><body><main><p>text here that is long enough to be a paragraph block</p>'
              '<a href="/x?a=1&amp;b=2">link</a></main></body></html>', "https://a.com/")
    assert any(l.href.endswith("/x?a=1&b=2") for l in d.links), [l.href for l in d.links]


# --- rendered checks: hidden text, dark cards, local-only fonts -------------
@pytest.mark.render
def test_hidden_and_hover_only_text_is_not_measured(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from pathlib import Path

    from readlens.metrics.typography import analyse
    from readlens.render import Renderer

    fixture = Path(__file__).parent / "fixtures" / "hidden.html"
    with Renderer(viewports={"desktop": (1440, 900)}, check_dark=False) as r:
        if r.error:
            pytest.skip(r.error)
        res = r.render(fixture.as_uri())
    assert res.ok, res.error
    v = analyse(res).primary
    probe = res.viewports["desktop"]

    # the 12px hover-revealed description must not count as body text
    assert v.pct_text_below_16px == 0.0
    assert probe["hoverOnly"] >= 1 and probe["hoverOnlyChars"] > 50
    # white on a black card resolves to the card, not to the page background
    assert v.min_contrast_ratio > 4.5, v.contrast_failures
    # a @font-face whose src is only local() downloads nothing and hides nothing
    assert probe["fonts"]["blocking"] == 0
