from readlens.extract import own_text, parse
import lxml.html

HTML = """
<html lang="fr"><head><title>Titre</title>
<meta name="description" content="Une description">
</head><body>
<nav><a href="/a">Accueil</a><a href="/b">Blog</a></nav>
<main>
  <header><h1>Le titre de l'article</h1></header>
  <div class="body">
    Un premier paragraphe qui vit directement dans un div et qui doit compter comme du texte.
    <div>Un second bloc imbrique avec assez de texte pour etre retenu comme un paragraphe.</div>
  </div>
  <p>Un vrai paragraphe avec un <a href="https://ext.example/x">lien externe</a> dedans.</p>
  <ul><li>Premier element de liste assez long pour compter</li><li>Deuxieme element de liste</li></ul>
  <pre><code>print("hello")</code></pre>
  <img src="/a.png"><img src="/b.png" alt="">
  <img src="/c.png" alt="une photo">
</main>
<footer><p>Pied de page</p></footer>
</body></html>
"""


def _doc():
    return parse(HTML, "https://example.test/page")


def test_metadata():
    d = _doc()
    assert d.lang == "fr"
    assert d.title == "Titre"
    assert d.meta_description == "Une description"


def test_h1_inside_header_is_kept():
    d = _doc()
    assert any(b.kind == "h1" for b in d.blocks)
    assert d.landmarks["h1"] == 1


def test_div_paragraphs_are_captured():
    d = _doc()
    texts = " ".join(b.text for b in d.blocks if b.kind == "p")
    assert "premier paragraphe" in texts
    assert "second bloc" in texts


def test_text_is_a_partition_no_duplicates():
    d = _doc()
    joined = " ".join(b.text for b in d.blocks)
    assert joined.count("second bloc imbrique") == 1
    assert joined.count("vrai paragraphe") == 1


def test_links_and_images():
    d = _doc()
    ext = [l for l in d.links if not l.internal]
    assert len(ext) == 1 and ext[0].href.startswith("https://ext.example")
    assert len(d.images) == 3
    assert sum(1 for i in d.images if not i.has_alt) == 1
    assert sum(1 for i in d.images if i.decorative) == 1


def test_code_block_detected():
    d = _doc()
    assert d.code_blocks == 1


def test_own_text_excludes_block_children():
    el = lxml.html.fromstring("<div>keep <span>this</span><p>drop this</p> and tail</div>")
    t = own_text(el)
    assert "keep this" in t and "and tail" in t and "drop this" not in t


def test_coverage_is_none_without_a_reference():
    from readlens.extract import _coverage
    assert _coverage("some text", None) == (None, "")
    assert _coverage("some text", "too short") == (None, "")


def test_coverage_flags_both_directions():
    from readlens.extract import _coverage
    ref = "x" * 1000
    assert _coverage("x" * 950, ref)[1] == ""
    assert "incomplete" in _coverage("x" * 300, ref)[1]
    assert "inflated" in _coverage("x" * 3000, ref)[1]


def test_parse_records_extraction_confidence():
    d = parse(HTML, "https://example.test/page", reference_text="Le titre de l'article " * 40)
    assert d.extraction_coverage is not None
    assert isinstance(d.extraction_note, str)


NARROW = """
<html lang="en"><body><main>
  <div class="teaser"><p>A dense little teaser block that scores well on its own because it
  is compact prose with no links at all inside it whatsoever.</p></div>
  <div class="rest">
    <p>The real article continues here for several paragraphs and carries most of the words
    on the page, which is what any honest extraction has to come back with.</p>
    <p>Second paragraph of the real article, again with a decent amount of running text so
    that the totals are clearly dominated by this region rather than by the teaser.</p>
    <p>Third paragraph of the real article, still going, still the bulk of the page text and
    still the thing a reader came for.</p>
  </div>
</main></body></html>
"""


def test_fallback_widens_the_region_when_coverage_is_poor():
    from readlens.extract import parse as p2
    full = p2(NARROW, "https://example.test/n")
    # a reference three times our text forces the < 0.6 fallback path
    forced = p2(NARROW, "https://example.test/n", reference_text=full.text + "y" * len(full.text) * 3)
    assert forced.extraction_coverage is not None
    assert len(forced.text) >= len(full.text)      # never returns less than the first pass


INLINE_PARAS = ("<html lang='en'><body><main><div class='prose'>"
                + "".join(f"<span>Paragraph number {i} of this article, written as an inline "
                          f"element that the stylesheet renders as a block, which is how a "
                          f"reader actually sees it on the page.</span>" for i in range(6))
                + "</div></main></body></html>")


def test_inline_tagged_paragraphs_are_split_not_merged():
    """A div of display:block spans is thirty paragraphs, not one 2000-word run."""
    d = parse(INLINE_PARAS, "https://example.test/a")
    paras = [b for b in d.blocks if b.kind == "p"]
    assert len(paras) == 6, [b.words for b in paras]
    assert max(b.words for b in paras) < 40
    assert d.inline_paragraph_containers == 1


def test_a_normal_paragraph_with_inline_children_is_not_split():
    html = ("<html lang='en'><body><main><p>An ordinary paragraph with a "
            "<a href='/x'>link inside it</a> and some <strong>bold words</strong> that must "
            "stay part of the same paragraph rather than becoming three of them.</p>"
            "</main></body></html>")
    d = parse(html, "https://example.test/b")
    paras = [b for b in d.blocks if b.kind == "p"]
    assert len(paras) == 1
    assert d.inline_paragraph_containers == 0
