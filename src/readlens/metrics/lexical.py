"""Vocabulary metrics: diversity, density, word rarity, jargon, marketing fluff."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from ..lang import LangPack
from ..text import ACRONYM_RE, NUM_RE, syllables, words

try:
    from wordfreq import zipf_frequency
except Exception:  # pragma: no cover
    zipf_frequency = None

WORDFREQ_LANGS = {"en", "fr", "es", "de", "it", "pt", "nl"}


@dataclass
class LexicalReport:
    n_words: int = 0
    n_types: int = 0
    ttr: float = 0.0
    mattr: float = 0.0            # moving-average TTR (window 100) — length-robust
    hapax_ratio: float = 0.0
    lexical_density: float = 0.0  # content words / all words
    pct_long_words: float = 0.0
    pct_polysyllabic: float = 0.0
    mean_zipf: float = 0.0        # 7 = "the", 3 = specialist, <3 = rare
    pct_rare: float = 0.0         # zipf < 3.0
    rare_words: list = field(default_factory=list)
    acronym_ratio: float = 0.0
    acronyms: list = field(default_factory=list)
    number_density: float = 0.0   # concrete figures per 100 words
    hedge_ratio: float = 0.0
    hedges_found: list = field(default_factory=list)
    top_terms: list = field(default_factory=list)
    keyword_stuffing: float = 0.0  # max share of a single content word

    def as_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def _mattr(toks: list[str], window: int = 100) -> float:
    if len(toks) <= window:
        return len(set(toks)) / len(toks) if toks else 0.0
    ratios = []
    for i in range(0, len(toks) - window + 1, max(1, window // 4)):
        chunk = toks[i:i + window]
        ratios.append(len(set(chunk)) / window)
    return sum(ratios) / len(ratios)


def analyse(text: str, lp: LangPack) -> LexicalReport:
    r = LexicalReport()
    toks = [w.lower() for w in words(text)]
    if not toks:
        return r
    r.n_words = len(toks)
    counts = Counter(toks)
    r.n_types = len(counts)
    r.ttr = r.n_types / r.n_words
    r.mattr = _mattr(toks)
    r.hapax_ratio = sum(1 for v in counts.values() if v == 1) / r.n_types

    content = [w for w in toks if w not in lp.stopwords and len(w) > 2]
    r.lexical_density = len(content) / r.n_words
    r.pct_long_words = sum(1 for w in toks if len(w) > 6) / r.n_words
    r.pct_polysyllabic = sum(1 for w in toks if syllables(w, lp) >= 3) / r.n_words

    if zipf_frequency and lp.code in WORDFREQ_LANGS:
        zs = [(w, zipf_frequency(w, lp.code)) for w in set(content) if len(w) > 2]
        known = [z for _, z in zs if z > 0]
        if known:
            weighted = [(w, z) for w, z in zs]
            r.mean_zipf = round(sum(z for _, z in weighted) / len(weighted), 2)
            rare = sorted([(w, z) for w, z in weighted if z < 3.0], key=lambda p: p[1])
            r.pct_rare = sum(counts[w] for w, _ in rare) / r.n_words
            r.rare_words = [{"word": w, "zipf": round(z, 2), "count": counts[w]} for w, z in rare[:15]]

    acr = ACRONYM_RE.findall(text)
    acr = [a for a in acr if a.lower() not in lp.stopwords]
    r.acronym_ratio = len(acr) / r.n_words
    r.acronyms = [a for a, _ in Counter(acr).most_common(10)]

    r.number_density = len(NUM_RE.findall(text)) / r.n_words * 100

    low = " " + text.lower() + " "
    found = []
    for h in lp.hedges:
        n = low.count(" " + h + " ") if " " in h else counts.get(h, 0)
        if n:
            found.append((h, n))
    found.sort(key=lambda p: -p[1])
    r.hedge_ratio = sum(n for _, n in found) / r.n_words
    r.hedges_found = [{"term": h, "count": n} for h, n in found[:12]]

    top = [(w, n) for w, n in Counter(content).most_common(15)]
    r.top_terms = [{"term": w, "count": n, "share": round(n / r.n_words, 4)} for w, n in top]
    r.keyword_stuffing = top[0][1] / r.n_words if top else 0.0
    return r
