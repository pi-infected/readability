"""Turn raw HTML into a normalised document model (main content + structure)."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import lxml.html
from lxml.html import HtmlElement

from .text import WORD_RE

DROP_TAGS = ("script", "style", "noscript", "svg", "template", "iframe", "object", "canvas")
CHROME_TAGS = ("nav", "header", "footer", "aside", "form")
CHROME_HINT = re.compile(
    r"(^|[-_ ])(nav|menu|sidebar|footer|header|breadcrumb|cookie|consent|banner|toolbar|"
    r"share|social|related|promo|advert|ads?|subscribe|newsletter|skip|pagination|widget)([-_ ]|$)",
    re.I,
)
MAIN_SELECTORS = [
    "main", "[role='main']", "article", "#main", "#content", "#main-content",
    ".prose", ".markdown-body", ".post-content", ".entry-content", ".article-body",
    ".content", "#docs-content", "[data-content]",
]
BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre",
              "figcaption", "dt", "dd", "td", "th", "summary"}

HEADING_KINDS = {"h1", "h2", "h3", "h4", "h5", "h6"}
# A definition list answer or a <summary> is a paragraph; an FAQ built from <dl> would
# otherwise measure as an empty page.
PARAGRAPH_KINDS = {"p", "blockquote", "dd", "summary"}
PROSE_KINDS = PARAGRAPH_KINDS | HEADING_KINDS | {"li", "dt", "figcaption"}

WS = re.compile(r"[ \t  ]+")
NL = re.compile(r"\n{3,}")


def clean_text(s: str) -> str:
    s = s.replace("​", "").replace("\xad", "")
    s = WS.sub(" ", s)
    s = NL.sub("\n\n", s)
    return s.strip()


@dataclass
class Block:
    kind: str
    text: str
    depth: int = 0
    chars: int = 0
    words: int = 0
    dom_path: str = ""

    def __post_init__(self):
        self.chars = len(self.text)
        self.words = len(self.text.split())


@dataclass
class Link:
    text: str
    href: str
    internal: bool
    in_main: bool


@dataclass
class Image:
    src: str
    alt: str | None
    has_alt: bool
    decorative: bool
    width: str | None = None
    height: str | None = None


MACHINE_PUNCT = set("{}[]()<>|/\\=+*_→⠧⠏`\"")


def looks_like_machine_output(text: str, stopwords: set, min_words: int = 8, *,
                              stopwords_apply: bool = True) -> bool:
    """JSON blobs, shell transcripts and build logs are not prose.

    Decorative terminal animations put thousands of characters of tool-call JSON on a
    marketing page. Scoring them as writing measures the demo, not the page. Prose in the
    reference material sits at 0.39-0.49 stopwords and 0.00 punctuation density; machine
    output sits at 0.17 and 0.13, so the thresholds have a wide margin either side.

    `stopwords_apply` must be False whenever the profile does not match the text's actual
    language: Arabic prose contains no English stopwords, and the rule would delete the
    whole page. The punctuation signal is language-independent and always applies.
    """
    words = WORD_RE.findall(text)
    if len(words) < min_words:
        return False                      # too short to judge; headings live here
    punct = sum(1 for c in text if c in MACHINE_PUNCT) / max(len(text), 1)
    if punct > 0.10:
        return True
    if not stopwords_apply:
        return False
    stop = sum(1 for w in words if w.lower() in stopwords) / len(words)
    return stop < 0.12


@dataclass
class Doc:
    url: str
    lang: str | None
    title: str
    meta_description: str | None
    blocks: list[Block] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    text: str = ""
    prose_text: str = ""
    full_text: str = ""
    html_bytes: int = 0
    main_selector: str = ""
    tables: int = 0
    code_blocks: int = 0
    emphasis: dict = field(default_factory=dict)
    inline_code: int = 0
    abbr: int = 0
    landmarks: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)
    extraction_coverage: float | None = None   # our text / an independent extractor's
    extraction_note: str = ""
    machine_blocks: int = 0
    inline_paragraph_containers: int = 0

    @property
    def headings(self) -> list[Block]:
        return [b for b in self.blocks if b.kind in HEADING_KINDS]

    @property
    def paragraphs(self) -> list[Block]:
        return [b for b in self.blocks if b.kind in PARAGRAPH_KINDS]

    def drop_machine_blocks(self, stopwords: set, *, stopwords_apply: bool = True) -> int:
        """Remove machine output from the document. Returns how many blocks went."""
        keep, dropped = [], 0
        for b in self.blocks:
            if b.kind in PARAGRAPH_KINDS and looks_like_machine_output(
                    b.text, stopwords, stopwords_apply=stopwords_apply):
                dropped += 1
                continue
            keep.append(b)
        if dropped:
            self.blocks = keep
            self.text = clean_text("\n\n".join(b.text for b in keep))
            self.prose_text = clean_text("\n\n".join(b.text for b in keep
                                                      if b.kind in PROSE_KINDS))
        self.machine_blocks = dropped
        return dropped

    @property
    def boilerplate_ratio(self) -> float:
        if not self.full_text:
            return 0.0
        return max(0.0, 1.0 - len(self.text) / len(self.full_text))


def _strip(tree: HtmlElement, tags) -> None:
    for el in tree.xpath("|".join(f"//{t}" for t in tags)) if tags else []:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)


def flat_text(el: HtmlElement) -> str:
    """Text of an element with block boundaries preserved.

    lxml's text_content() concatenates without separators, so `<h3>PowerIn</h3><span>vs
    </span><h3>SayWhat</h3>` comes back as "PowerInvsSayWhat" — a word that exists in no
    language and poisons every vocabulary metric downstream. Blocks get a newline, inline
    runs are joined as written.
    """
    parts: list[str] = []

    def walk(node: HtmlElement) -> None:
        tag = node.tag if isinstance(node.tag, str) else ""
        block = tag in BLOCK_LEVEL
        if block:
            parts.append("\n")
        if node.text:
            parts.append(node.text)
        for child in node:
            if isinstance(child.tag, str):
                walk(child)
            if child.tail:
                parts.append(child.tail)
        if block:
            parts.append("\n")

    walk(el)
    return clean_text("".join(parts))


def _visible_text(el: HtmlElement) -> str:
    return flat_text(el)


def _density(el: HtmlElement) -> float:
    """Text length weighted against link-text length (nav-heavy blocks score low)."""
    txt = len(_visible_text(el))
    if txt < 40:
        return 0.0
    link_txt = sum(len(_visible_text(a)) for a in el.iter("a"))
    ps = len(el.xpath(".//p")) + len(el.xpath(".//li")) * 0.25
    return txt * (1 - min(0.95, link_txt / max(txt, 1))) * (1 + min(ps, 40) / 20)


def _dom_path(el: HtmlElement) -> str:
    parts = []
    cur = el
    while cur is not None and getattr(cur, "tag", None) and isinstance(cur.tag, str):
        tag = cur.tag
        cid = cur.get("id")
        if cid:
            parts.append(f"{tag}#{cid}")
            break
        cls = (cur.get("class") or "").split()
        parts.append(tag + ("." + cls[0] if cls else ""))
        cur = cur.getparent()
        if len(parts) > 6:
            break
    return " > ".join(reversed(parts))


def _depth(el: HtmlElement) -> int:
    d, cur = 0, el.getparent()
    while cur is not None:
        d += 1
        cur = cur.getparent()
    return d


SEMANTIC_BONUS = {"main": 1.4, "article": 1.3, "section": 1.05}


def pick_main(tree: HtmlElement) -> tuple[HtmlElement, str]:
    """Pick the densest prose container, preferring the most specific node.

    Scores every plausible container, then among all nodes within 12% of the
    best score keeps the DEEPEST one, so <body> never wins over <main>.
    """
    semantic: set[int] = set()
    keep_alive = []
    for sel in MAIN_SELECTORS:
        try:
            found = tree.cssselect(sel)
        except Exception:
            continue
        for el in found[:4]:
            keep_alive.append(el)
            semantic.add(id(el))

    cands: list[tuple[float, int, HtmlElement]] = []
    for el in tree.iter("div", "section", "article", "main", "body"):
        keep_alive.append(el)
        s = _density(el)
        if s <= 0:
            continue
        s *= SEMANTIC_BONUS.get(el.tag, 1.0)
        if id(el) in semantic:
            s *= 1.25
        cands.append((s, _depth(el), el))
    if not cands:
        return tree, "body"
    best_score = max(c[0] for c in cands)
    finalists = [c for c in cands if c[0] >= best_score * 0.88]
    finalists.sort(key=lambda c: (c[1], c[0]))
    _, _, best = finalists[-1]
    return best, _dom_path(best)


BLOCK_LEVEL = {
    "address", "article", "aside", "blockquote", "details", "dialog", "dd", "div", "dl", "dt",
    "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hgroup", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table",
    "tbody", "td", "tfoot", "th", "thead", "tr", "ul", "summary", "picture", "video", "audio",
}
CONTAINER_TAGS = {"div", "section", "article", "main", "figure", "details", "header", "footer",
                  "aside", "form", "label"}
MIN_RUN_CHARS = 25


def own_text(el: HtmlElement) -> str:
    """Text belonging to this element only: its own runs plus inline descendants.

    Every text node in the tree therefore belongs to exactly one block, which is what
    makes the block list a partition of the page instead of a pile of overlaps.
    """
    parts = [el.text or ""]
    for child in el:
        if not isinstance(child.tag, str):
            parts.append(child.tail or "")
            continue
        if child.tag in BLOCK_LEVEL:
            parts.append(child.tail or "")          # skip the block, keep what follows it
        else:
            parts.append(flat_text(child))
            parts.append(child.tail or "")
    return clean_text("".join(parts))


def _kind_of(el: HtmlElement) -> str | None:
    tag = el.tag
    if not isinstance(tag, str):
        return None
    if tag == "pre":
        return "code"
    if tag in ("td", "th"):
        return "cell"
    if tag in BLOCK_TAGS:
        return tag
    # Sites that never use <p> still have paragraphs: any container holding a run of
    # text of its own is one, whatever its children are.
    if tag in CONTAINER_TAGS:
        return "p"
    return None


def _list_depth(el: HtmlElement) -> int:
    d, cur = 0, el.getparent()
    while cur is not None and isinstance(cur.tag, str):
        if cur.tag in ("ul", "ol"):
            d += 1
        cur = cur.getparent()
    return d


def _overlay_matcher(hints: list[dict] | None):
    """Match the fixed and sticky elements the browser reported, by tag and class prefix.

    A cookie wall styled `div.fixed` carries no semantic name a regex could find, but the
    rendered page already told us it floats over the content. Using that beats guessing.
    """
    if not hints:
        return lambda el: False
    sigs = [(h.get("tag", "").lower(), (h.get("cls") or "").strip()[:40])
            for h in hints if h.get("cls")]
    sigs = [s for s in sigs if len(s[1]) >= 8]

    def match(el: HtmlElement) -> bool:
        tag = el.tag if isinstance(el.tag, str) else ""
        cls = (el.get("class") or "").strip()
        if not cls:
            return False
        for htag, hcls in sigs:
            if tag == htag and cls.startswith(hcls):
                # Never drop the article because it happens to be sticky.
                return len((el.text_content() or "")) < 2000
        return False

    return match


def _collect(body: HtmlElement, main: HtmlElement, url: str, host: str,
             overlay_hints: list[dict] | None = None) -> dict:
    """Strip chrome from the chosen region, then read every block, link and count out of it."""
    is_overlay = _overlay_matcher(overlay_hints)
    inline_containers = [0]
    for el in list(main.iter()):
        if not isinstance(el.tag, str) or el is main:
            continue
        idcls = f"{el.get('id') or ''} {el.get('class') or ''}"
        hidden = el.get("hidden") is not None or el.get("aria-hidden") == "true"
        # An article's title often lives in a <header> inside the content; dropping it
        # loses the h1 and makes the page look untitled.
        if el.tag in ("header", "footer") and el.xpath(".//h1 | .//h2"):
            continue
        if (el.tag in CHROME_TAGS or hidden or is_overlay(el)
                or (CHROME_HINT.search(idcls) and _density(el) < 400)):
            p = el.getparent()
            if p is not None:
                p.remove(el)

    blocks: list[Block] = []
    for el in main.iter():
        kind = _kind_of(el)
        if kind is None:
            continue
        text = el.text_content().strip() if kind == "code" else own_text(el)
        if not text:
            continue
        # Some sites write their paragraphs as inline tags styled display:block. Read as
        # markup that is one 2000-word run; read as a page it is thirty paragraphs. Split
        # on the children rather than reporting a paragraph nobody can see.
        if kind == "p" and el.tag in CONTAINER_TAGS:
            runs = [c for c in el if isinstance(c.tag, str) and c.tag not in BLOCK_LEVEL
                    and len((c.text_content() or "").strip()) >= MIN_RUN_CHARS]
            if len(runs) >= 3 and sum(len(c.text_content() or "") for c in runs) >= 0.6 * len(text):
                inline_containers[0] += 1
                for c in runs:
                    rt = flat_text(c)
                    if rt:
                        blocks.append(Block(kind="p", text=rt, dom_path=_dom_path(c)))
                continue
        is_heading = kind in HEADING_KINDS
        if not is_heading and kind not in ("code", "cell") and len(text) < MIN_RUN_CHARS:
            continue
        depth = _list_depth(el) if kind == "li" else 0
        blocks.append(Block(kind=kind, text=text, depth=depth, dom_path=_dom_path(el)))

    links: list[Link] = []
    main_anchors = list(main.iter("a"))  # keep proxies alive: lxml recycles id()
    main_ids = {id(a) for a in main_anchors}
    for a in body.iter("a"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "#")):
            continue
        abs_href = urljoin(url, href)
        links.append(Link(
            text=_visible_text(a), href=abs_href,
            internal=urlparse(abs_href).netloc.lower().removeprefix("www.") == host.removeprefix("www."),
            in_main=id(a) in main_ids,
        ))

    return {
        "blocks": blocks,
        "links": links,
        "text": clean_text("\n\n".join(b.text for b in blocks)),
        "prose": clean_text("\n\n".join(b.text for b in blocks if b.kind in PROSE_KINDS)),
        "tables": len(main.xpath(".//table")),
        "emphasis": {"strong": len(main.xpath(".//strong | .//b")),
                     "em": len(main.xpath(".//em | .//i")),
                     "mark": len(main.xpath(".//mark"))},
        "inline_code": len(main.xpath(".//code[not(ancestor::pre)]")),
        "abbr": len(main.xpath(".//abbr")),
        "inline_paragraph_containers": inline_containers[0],
    }


def _coverage(text: str, reference: str | None) -> tuple[float | None, str]:
    """How much of an independent extractor's text we account for. 1.0 is agreement."""
    if not reference or len(reference) < 200:
        return None, ""
    c = len(text) / len(reference)
    if c < 0.6:
        note = "the content region looks incomplete against an independent extractor"
    elif c > 2.5:
        note = "the content region looks inflated: navigation or boilerplate is probably inside it"
    else:
        note = ""
    return round(c, 3), note


def reference_text(html: str) -> str | None:
    """A second opinion on where the content is. Trafilatura if present, else nothing."""
    try:
        import trafilatura
        return trafilatura.extract(html, include_comments=False, include_tables=True) or None
    except Exception:
        return None


class EmptyDocument(ValueError):
    """The response carried no markup to parse."""


def parse(html: str, url: str, lang_hint: str | None = None,
          reference_text: str | None = None, overlay_hints: list[dict] | None = None) -> Doc:
    if not html or not html.strip():
        raise EmptyDocument("the document is empty")
    try:
        tree = lxml.html.fromstring(html)
    except Exception as exc:                 # lxml raises on whitespace-only input
        raise EmptyDocument(f"the document could not be parsed: {exc}") from exc
    try:
        tree.make_links_absolute(url, resolve_base_href=True)
    except Exception:
        pass

    title_el = tree.xpath("//title/text()")
    title = clean_text(title_el[0]) if title_el else ""
    lang = (tree.get("lang") or (tree.xpath("//html/@lang") or [None])[0] or lang_hint)
    if lang:
        lang = lang.strip().lower()
    meta = {}
    for m in tree.xpath("//meta"):
        name = (m.get("name") or m.get("property") or "").lower()
        if name and m.get("content"):
            meta.setdefault(name, m.get("content").strip())
    desc = meta.get("description") or meta.get("og:description")

    landmarks = {
        "main": len(tree.xpath("//main | //*[@role='main']")),
        "nav": len(tree.xpath("//nav | //*[@role='navigation']")),
        "header": len(tree.xpath("//header")),
        "footer": len(tree.xpath("//footer")),
        "article": len(tree.xpath("//article")),
        "skip_link": bool(tree.xpath("//a[contains(translate(text(),'SKIP','skip'),'skip')][starts-with(@href,'#')]")),
        "h1": len(tree.xpath("//h1")),
        "lang_attr": bool(lang),
    }

    # images & links from the WHOLE page (a11y is page-wide)
    images: list[Image] = []
    for img in tree.xpath("//img"):
        alt = img.get("alt")
        images.append(Image(
            src=img.get("src") or img.get("data-src") or "",
            alt=alt, has_alt=alt is not None,
            decorative=(alt is not None and alt.strip() == "") or img.get("role") == "presentation",
            width=img.get("width"), height=img.get("height"),
        ))

    _strip(tree, DROP_TAGS)
    full_text = clean_text(tree.text_content())
    body = tree.body if tree.body is not None else tree
    host = urlparse(url).netloc.lower()

    # Try the densest content region first. If an independent extractor finds far more
    # text than we did, the region was wrong and every language metric would be measured
    # on scraps, so fall back to the whole body and keep whichever covers better.
    pristine = copy.deepcopy(body) if reference_text else None
    main, sel = pick_main(body)
    collected = _collect(body, main, url, host, overlay_hints)
    coverage, note = _coverage(collected["text"], reference_text)

    if pristine is not None and coverage is not None and coverage < 0.6:
        alt = _collect(pristine, pristine, url, host, overlay_hints)
        alt_cov, alt_note = _coverage(alt["text"], reference_text)
        if alt_cov is not None and alt_cov > coverage:
            collected, coverage, note = alt, alt_cov, alt_note
            sel = "body (fallback: the content region missed most of the text)"

    return Doc(
        url=url, lang=lang, title=title, meta_description=desc,
        blocks=collected["blocks"], links=collected["links"], images=images,
        text=collected["text"], prose_text=collected["prose"], full_text=full_text,
        html_bytes=len(html.encode("utf8", "ignore")),
        main_selector=sel,
        tables=collected["tables"],
        emphasis=collected["emphasis"],
        inline_code=collected["inline_code"],
        abbr=collected["abbr"],
        code_blocks=len([b for b in collected["blocks"] if b.kind == "code"]),
        landmarks=landmarks, meta=meta,
        extraction_coverage=coverage, extraction_note=note,
        inline_paragraph_containers=collected["inline_paragraph_containers"],
    )
