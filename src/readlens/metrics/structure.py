"""Page architecture: heading tree, paragraph shape, lists, links, scannability."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from ..extract import HEADING_KINDS, PARAGRAPH_KINDS, PROSE_KINDS, Doc
from ..lang import LangPack
from ..text import URL_RE, reading_time_seconds, sentences, words


@dataclass
class StructureReport:
    word_count: int = 0
    prose_word_count: int = 0      # paragraphs and quotes only, the running text
    text_chars: int = 0            # scripts without word spacing still have content
    reading_time_min: float = 0.0
    n_headings: int = 0
    heading_levels: list = field(default_factory=list)
    h1_count: int = 0
    level_skips: list = field(default_factory=list)
    empty_headings: int = 0
    long_headings: int = 0
    headings_per_1000w: float = 0.0
    longest_unbroken_words: int = 0     # longest stretch with no heading
    section_word_counts: list = field(default_factory=list)
    n_paragraphs: int = 0
    mean_paragraph_words: float = 0.0
    max_paragraph_words: int = 0
    pct_long_paragraphs: float = 0.0    # > 120 words
    pct_wall_paragraphs: float = 0.0    # > 200 words
    mean_sentences_per_paragraph: float = 0.0
    n_list_items: int = 0
    list_share: float = 0.0
    n_tables: int = 0
    n_code_blocks: int = 0
    emphasis_per_1000w: float = 0.0
    title: str = ""
    title_length: int = 0
    meta_description: str | None = None
    meta_description_length: int = 0
    n_links: int = 0
    links_in_main: int = 0
    link_density: float = 0.0           # link words / main words
    external_ratio: float = 0.0
    weak_link_texts: list = field(default_factory=list)
    bare_url_links: int = 0
    ambiguous_link_texts: list = field(default_factory=list)
    boilerplate_ratio: float = 0.0
    intro_words: int = 0
    scannability: float = 0.0

    def as_dict(self) -> dict:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def analyse(doc: Doc, lp: LangPack) -> StructureReport:
    r = StructureReport()
    paras = doc.paragraphs
    heads = doc.headings
    prose_words = sum(b.words for b in doc.blocks if b.kind in PROSE_KINDS)
    r.word_count = prose_words
    r.prose_word_count = sum(b.words for b in doc.blocks if b.kind in PARAGRAPH_KINDS)
    r.text_chars = len(doc.text)
    r.reading_time_min = round(reading_time_seconds(prose_words, lp.code) / 60, 1)

    levels = [int(b.kind[1]) for b in heads]
    r.heading_levels = levels
    r.n_headings = len(heads)
    # h1 is counted page-wide: a title in a banner outside the content region is still
    # the page's title.
    r.h1_count = max(doc.landmarks.get("h1", 0), sum(1 for l in levels if l == 1))
    prev = 1 if (r.h1_count and (not levels or levels[0] != 1)) else None
    for i, l in enumerate(levels):
        if prev is not None and l > prev + 1:
            r.level_skips.append({"at": i, "from": f"h{prev}", "to": f"h{l}",
                                  "text": heads[i].text[:80]})
        prev = l
    r.empty_headings = sum(1 for b in heads if not b.text.strip())
    r.long_headings = sum(1 for b in heads if b.words > 12)
    r.headings_per_1000w = r.n_headings / max(prose_words, 1) * 1000

    # words between headings
    run, runs = 0, []
    for b in doc.blocks:
        if b.kind in HEADING_KINDS:
            runs.append(run)
            run = 0
        elif b.kind in PROSE_KINDS:
            run += b.words
    runs.append(run)
    r.section_word_counts = runs
    r.longest_unbroken_words = max(runs) if runs else prose_words

    if paras:
        pw = [b.words for b in paras]
        r.n_paragraphs = len(paras)
        r.mean_paragraph_words = sum(pw) / len(pw)
        r.max_paragraph_words = max(pw)
        r.pct_long_paragraphs = sum(1 for n in pw if n > 120) / len(pw)
        r.pct_wall_paragraphs = sum(1 for n in pw if n > 200) / len(pw)
        r.mean_sentences_per_paragraph = sum(len(sentences(b.text, lp)) for b in paras) / len(paras)
        r.intro_words = pw[0]

    lis = [b for b in doc.blocks if b.kind == "li"]
    r.n_list_items = len(lis)
    r.list_share = sum(b.words for b in lis) / max(prose_words, 1)
    r.n_tables = doc.tables
    r.n_code_blocks = doc.code_blocks
    r.emphasis_per_1000w = sum(doc.emphasis.values()) / max(prose_words, 1) * 1000

    r.title = doc.title
    r.title_length = len(doc.title)
    r.meta_description = doc.meta_description
    r.meta_description_length = len(doc.meta_description or "")

    r.n_links = len(doc.links)
    main_links = [l for l in doc.links if l.in_main]
    r.links_in_main = len(main_links)
    link_words = sum(len(words(l.text)) for l in main_links)
    r.link_density = link_words / max(prose_words, 1)
    if doc.links:
        r.external_ratio = sum(1 for l in doc.links if not l.internal) / len(doc.links)

    weak = {}
    by_text: dict[str, set] = {}
    for l in main_links:
        t = re.sub(r"\s+", " ", l.text.strip().lower())
        if not t:
            continue
        if t in lp.weak_link:
            weak[t] = weak.get(t, 0) + 1
        if URL_RE.match(t):
            r.bare_url_links += 1
        by_text.setdefault(t, set()).add(l.href)
    r.weak_link_texts = [{"text": t, "count": n} for t, n in
                         sorted(weak.items(), key=lambda p: -p[1])[:10]]
    r.ambiguous_link_texts = [{"text": t, "targets": len(h), "hrefs": sorted(h)[:6]}
                              for t, h in by_text.items() if len(h) > 1][:10]

    r.boilerplate_ratio = doc.boilerplate_ratio

    # Scannability: how easy the page is to skim. 0-1.
    parts = [
        min(1.0, r.headings_per_1000w / 5),                            # ~1 heading / 200 words
        1.0 - min(1.0, r.pct_long_paragraphs * 2),
        min(1.0, (r.n_list_items > 0) * 0.6 + min(r.list_share * 2, 0.4)),
        1.0 - min(1.0, max(0, r.longest_unbroken_words - 300) / 700),
        min(1.0, r.emphasis_per_1000w / 8),
    ]
    r.scannability = sum(parts) / len(parts)
    return r
