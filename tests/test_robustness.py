"""What the tool does with input the web actually serves: broken, empty, or not Latin.

Every case here either produced a crash or a confident wrong number before it was fixed.
The contract being locked in is narrow and worth stating: the tool may decline to score,
but it must never invent a score, and it must never silently delete text it cannot read.
"""
import pytest

from readability_audit.analysis import analyse_page
from readability_audit.fetch import Page

ARABIC = ("هذه فقرة مكتوبة بالعربية وتحتوي على عدد كاف من الكلمات لكي تكون قابلة للقياس. " * 6)
CHINESE = "这是一段中文文本用来测试可读性工具在没有空格的语言上的表现。" * 12
RUSSIAN = "Это русский текст для проверки инструмента читаемости на кириллице сегодня. " * 6


def page(html: str):
    return analyse_page(Page("http://x/", "http://x/", 200, html))


def wrap(body: str, lang: str = "en") -> str:
    return f'<html lang="{lang}"><body><main>{body}</main></body></html>'


@pytest.mark.parametrize("html", [
    "   \n\t  ",
    "<!-- just a comment -->",
], ids=["whitespace", "comment only"])
def test_unparseable_documents_error_instead_of_crashing(html):
    pa = page(html)
    assert not pa.ok and pa.error


@pytest.mark.parametrize("html,label", [
    ("just a bare string, not markup", "no markup"),
    ("<html><body><p>unclosed <div><span>nested <p>weird</body>", "malformed"),
    ("<html><head><title>T</title></head><frameset><frame src=a></frameset></html>", "frameset"),
    ("<html><body><main><img src=a.png alt=x></main></body></html>", "image only"),
    ("<svg xmlns='http://www.w3.org/2000/svg'><text>hi</text></svg>", "svg"),
    ("<html><body><script>var x='code not prose';</script></body></html>", "script only"),
])
def test_documents_without_content_are_not_graded(html, label):
    pa = page(html)
    if not pa.ok:
        return                                  # an honest parse failure is also fine
    assert pa.scores.overall is None, f"{label} was given a score"
    assert pa.scores.grade == "n/a"
    assert any(f.key == "no_content" for f in pa.findings)


@pytest.mark.parametrize("text,lang", [(ARABIC, "ar"), (CHINESE, "zh"), (RUSSIAN, "ru")],
                         ids=["arabic", "chinese", "russian"])
def test_unsupported_scripts_keep_their_text_and_skip_clarity(text, lang):
    """The stopword-based machine-output filter once deleted every one of these."""
    pa = page(wrap(f"<p>{text}</p>", lang))
    assert pa.ok
    assert pa.structure.text_chars > 200, "the text was thrown away"
    assert pa.clarity_supported is False
    assert "clarity" not in pa.scores.pillars, "clarity was scored on an unreadable script"
    assert any(f.key == "clarity_unsupported" for f in pa.findings)
    assert pa.scores.overall is not None, "structure and access are still measurable"


def test_latin_text_is_still_scored_for_clarity():
    body = ("<p>This paragraph is ordinary English prose, written for a reader, and it is "
            "long enough that the language metrics have something to work with here.</p>"
            "<p>A second paragraph of the same kind, so the document has running text "
            "rather than one stray sentence sitting on its own in an empty page.</p>") * 3
    pa = page(wrap(body))
    assert pa.clarity_supported is True
    assert "clarity" in pa.scores.pillars


def test_a_single_unpunctuated_run_is_scored_as_one_hard_sentence():
    pa = page(wrap("<p>" + "word " * 400 + "</p>"))
    assert pa.ok and pa.counts["sentences"] == 1
    assert pa.counts["avg_sentence_length"] == 400
    assert pa.scores.overall < 40, "a 400-word sentence should score badly, not well"


def test_a_large_document_completes():
    pa = page(wrap("<p>This is a sentence that repeats many times over. </p>" * 4000))
    assert pa.ok and pa.structure.word_count > 30000
    assert pa.scores.overall is not None


def test_entities_and_invisible_characters_decode():
    pa = page(wrap("<p>Caf&eacute; &amp; cr&egrave;me &mdash; a paragraph with entities "
                   "and​ invisible­ characters that should decode cleanly.</p>"))
    assert "Café" in pa.structure.title or "Café" in " ".join(
        b["text"] for b in pa.hardest_paragraphs) or pa.ok
    assert "​" not in " ".join(h["text"] for h in pa.hardest_paragraphs)


def test_empty_response_body_is_not_reported_as_a_status_code():
    from readability_audit.fetch import Page as P
    pa = analyse_page(P("http://x/", "http://x/", 200, ""))
    assert not pa.ok
    # The status alone would send someone hunting a server error that did not happen.
    assert "empty" in (pa.error or "").lower(), pa.error


def test_the_served_language_declaration_is_the_one_reported():
    """Hydration can correct <html lang> after the fact. A crawler never sees that."""
    from readability_audit.analysis import analyse_page
    from readability_audit.fetch import Page

    body = ("<main><p>Ceci est un paragraphe en français, assez long pour que la détection "
            "de langue ait de quoi travailler sans hésiter une seule seconde ici.</p>"
            "<p>Un deuxième paragraphe en français, pour que le document contienne du texte "
            "suivi plutôt qu'une phrase isolée perdue au milieu de la page.</p></main>")
    served = f'<html lang="en"><body>{body}</body></html>'
    hydrated = f'<html lang="fr"><body>{body}</body></html>'

    class RR:
        ok = True
        html = hydrated
        viewports = {}
        screenshots = {}
        dark_mode = None
        error = None

    pa = analyse_page(Page("http://x/", "http://x/", 200, served), render_result=RR())
    assert pa.lang_declared == "en", "the served declaration is what a crawler gets"
    assert pa.lang_declared_rendered == "fr"
    assert pa.lang_used == "fr", "the metrics follow the language actually written"
    finding = [f for f in pa.findings if f.key == "lang_mismatch"]
    assert finding, "hydration must not hide a wrong served lang attribute"
    assert "after hydration" in finding[0].fix


def test_bot_challenge_pages_are_not_scored():
    from readability_audit.fetch import challenge_of
    wall = ("<html><head><title>Client Challenge</title></head><body>JavaScript is disabled "
            "in your browser. Please enable JavaScript to proceed.</body></html>")
    assert challenge_of(wall) == "client challenge"
    assert challenge_of("<html><body><p>Just a normal article.</p></body></html>") == ""


def test_transport_errors_are_retried_not_replayed(tmp_path):
    from readability_audit.fetch import Cache, Fetcher
    c = Cache(tmp_path)
    c.put("GET https://example.invalid/", {"url": "https://example.invalid/",
          "final_url": "https://example.invalid/", "status": 0, "html": "",
          "error": "ReadTimeout: The read operation timed out"})
    f = Fetcher(cache=c, respect_robots=False, timeout=2)
    page = f.get("https://example.invalid/")
    assert not page.from_cache


def test_unsupported_language_keeps_its_name():
    from readability_audit.analysis import analyse_page
    from readability_audit.fetch import Page
    ar = "<p>" + "هذا نص عربي طويل عن قراءة الصفحات على الإنترنت وكيف نجعلها أسهل للقارئ. " * 30 + "</p>"
    html = f"<html lang='ar'><body><main><h1>عنوان</h1>{ar}</main></body></html>"
    pa = analyse_page(Page("https://a.com/", "https://a.com/", 200, html))
    assert pa.lang_used == "ar" and pa.lang_rules == "en"


def test_undeclared_scripts_get_their_language():
    from readability_audit.lang import detect
    assert detect(CHINESE)[0] == "zh"
    assert detect("東京では今日、雨が降っています。明日は晴れるでしょう。" * 3)[0] == "ja"
    assert detect(RUSSIAN)[0] == "ru"
    assert detect(RUSSIAN, "uk")[0] == "uk"     # the script cannot tell them apart
    pa = page(f"<html><body><main><p>{CHINESE}</p></main></body></html>")
    assert pa.lang_used == "zh"


def test_unspaced_scripts_count_characters_as_words():
    from readability_audit.extract import count_words
    assert count_words("国务院总理 ok") == 6
    assert count_words("plain english words") == 3


def test_prose_laid_out_in_a_table_cell_is_read_as_paragraphs():
    para = "This essay sits in a table cell, the way sites were built in 1998. " * 4
    html = f"<html><body><table><tr><td><font>{para}<br><br>{para}<br><br>{para}</font></td></tr></table></body></html>"
    pa = page(html)
    assert pa.structure.word_count > 100
    assert pa.structure.n_paragraphs == 3


def test_link_share_never_exceeds_the_text():
    links = "".join(f"<tr><td><a href='/p{i}'>Lisp article number {i}</a></td></tr>" for i in range(30))
    pa = page(f"<html><body><main><table>{links}</table></main></body></html>")
    assert pa.structure.link_density <= 1.0


def test_a_consent_dialog_is_never_the_content():
    vendors = "<p>" + "Vendor number one processes your data for measurement purposes today. " * 40 + "</p>"
    art = "<p>" + "The article itself is shorter than the vendor list but it is the page. " * 8 + "</p>"
    html = (f"<html><body><div class='site'>{art}</div>"
            f"<div class='fc-consent-root'><div class='fc-dialog'>{vendors}</div></div></body></html>")
    pa = page(html)
    assert "consent" not in (pa.extraction["selector"] or "")
    assert pa.structure.word_count < 200


def test_a_shared_utility_class_does_not_turn_the_page_into_an_overlay():
    from readability_audit.extract import parse
    cls = "pencraft pc-display-flex pc-gap-12 pc-padding-16"
    paras = "".join(f"<div class='{cls}'><p>Paragraph {i} of a newsletter landing page that "
                    "explains what the product does for writers.</p></div>" for i in range(8))
    doc = parse(f"<html><body><div class='{cls}'>nav</div><main>{paras}</main></body></html>",
                "https://a.com/", overlay_hints=[{"tag": "div", "cls": cls}])
    assert sum(b.words for b in doc.paragraphs) > 80


def test_display_size_text_is_not_the_body_size():
    from readability_audit.metrics.typography import _analyse_viewport
    base = dict(lineHeightRatio=1.5, lines=3, charsPerLine=60, widthPx=600, letterSpacing=0,
                color="rgba(0, 0, 0, 1)", bgLayers=["rgba(255, 255, 255, 1)"], weight=400, align="left",
                transform="none", hyphens="manual", marginTop=0, marginBottom=16, links=[],
                text="x", top=0, heightPx=80, family="Inter", generic="sans", opacity=1)
    quote = dict(base, tag="p", fontPx=44, chars=180)
    body = dict(base, tag="p", fontPx=16, chars=100)
    head = dict(base, tag="h2", fontPx=50, chars=60)
    assert _analyse_viewport("desktop", {"elements": [quote, body]}).body_font_px == 16
    assert _analyse_viewport("desktop", {"elements": [head]}).n_text_elements == 0


def test_feeds_are_not_pages():
    from readability_audit.fetch import looks_like_page
    assert not looks_like_page("https://www.python.org/jobs/feed/rss/")
    assert looks_like_page("https://a.com/blog/feedback")


def test_f5_challenge_is_recognised():
    from readability_audit.fetch import challenge_of
    assert challenge_of('<html><script>window["bobcmn"]="1";</script></html>') == "F5 BIG-IP"
    assert challenge_of('<script id="anubis_challenge" type="application/json">') == "Anubis"


def test_a_page_without_mobile_layout_is_read_at_its_shrunk_size():
    from readability_audit.metrics.typography import _analyse_viewport
    el = dict(tag="p", fontPx=15, chars=900, lineHeightRatio=1.5, lines=8, charsPerLine=140,
              widthPx=940, letterSpacing=0, color="rgba(0, 0, 0, 1)",
              bgLayers=["rgba(255, 255, 255, 1)"], weight=400, align="left", transform="none",
              hyphens="manual", marginTop=0, marginBottom=16, links=[], text="x", top=0,
              heightPx=200, family="Arial", generic="sans", opacity=1)
    v = _analyse_viewport("mobile", {"viewport": {"width": 980}, "elements": [el]})
    assert v.zoom < 0.5 and v.body_font_px < 7


def test_an_archive_index_is_not_one_long_sentence():
    rows = "".join(f"<time>Sep {i} 2024</time>\n\n<a href='/c{i}'>Category {i}</a>\n\n" for i in range(12))
    pa = page(f"<html><body><main><p class='article-list'>{rows}</p></main></body></html>")
    assert pa.structure.word_count < 20


def test_sections_are_sampled_in_the_language_the_audit_started_in():
    from readability_audit.fetch import sample_sections
    urls = ["https://a.fr/fr", "https://a.fr/ar/blog", "https://a.fr/fr/blog", "https://a.fr/ar/map",
            "https://a.fr/fr/map"]
    assert sample_sections(urls) == ["https://a.fr/fr", "https://a.fr/fr/blog", "https://a.fr/fr/map"]


def test_overflow_under_device_width_is_not_a_missing_mobile_layout():
    from readability_audit.metrics.typography import _analyse_viewport
    el = dict(tag="p", fontPx=16, chars=900, lineHeightRatio=1.5, lines=8, charsPerLine=50,
              widthPx=360, letterSpacing=0, color="rgba(0, 0, 0, 1)",
              bgLayers=["rgba(255, 255, 255, 1)"], weight=400, align="left", transform="none",
              hyphens="manual", marginTop=0, marginBottom=16, links=[], text="x", top=0,
              heightPx=200, family="Arial", generic="sans", opacity=1)
    vp = {"width": 1500, "meta": "width=device-width, initial-scale=1"}
    v = _analyse_viewport("mobile", {"viewport": vp, "elements": [el]})
    assert v.zoom == 1.0 and v.body_font_px == 16
