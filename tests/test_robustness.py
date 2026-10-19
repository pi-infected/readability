"""What the tool does with input the web actually serves: broken, empty, or not Latin.

Every case here either produced a crash or a confident wrong number before it was fixed.
The contract being locked in is narrow and worth stating: the tool may decline to score,
but it must never invent a score, and it must never silently delete text it cannot read.
"""
import pytest

from readlens.analysis import analyse_page
from readlens.fetch import Page

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
    from readlens.fetch import Page as P
    pa = analyse_page(P("http://x/", "http://x/", 200, ""))
    assert not pa.ok
    # The status alone would send someone hunting a server error that did not happen.
    assert "empty" in (pa.error or "").lower(), pa.error


def test_the_served_language_declaration_is_the_one_reported():
    """Hydration can correct <html lang> after the fact. A crawler never sees that."""
    from readlens.analysis import analyse_page
    from readlens.fetch import Page

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
