"""Sentence-level style metrics: length rhythm, passive voice, nominalisation, connectives."""
from __future__ import annotations

import re
import statistics as st
from dataclasses import dataclass, field

from ..lang import BE_FORMS, EN_IRREGULAR_PP, ETRE_FORMS, LangPack
from ..text import words

# English past participle: regular -ed, or a known irregular.
EN_PP = re.compile(r"^[a-z]+(ed|en|wn|ne|de|ung|ought|aught)$")
# French past participle: -é(e)(s), -i(e)(s), -u(e)(s), -is, -it, -ait? (avoid), -ert
FR_PP = re.compile(r"^[a-zàâçéèêëîïôûùüÿœ]+(é|ée|és|ées|i|ie|is|ies|it|its|u|ue|us|ues|ert|erte|erts|ertes)$")
FR_AGENT = re.compile(r"\bpar\s+(le|la|les|l'|un|une|des|leur|son|sa|ses|notre|votre)\b", re.I)

LONG_SENT = {"en": 25, "fr": 30}      # Yoast-style caps; French runs longer per idea
VERY_LONG = {"en": 40, "fr": 45}


@dataclass
class SyntaxReport:
    n_sentences: int = 0
    mean_len: float = 0.0
    median_len: float = 0.0
    p90_len: float = 0.0
    max_len: int = 0
    stdev_len: float = 0.0
    variation: float = 0.0            # coefficient of variation — reading rhythm
    pct_long: float = 0.0
    pct_very_long: float = 0.0
    pct_short: float = 0.0            # <= 8 words
    passive_ratio: float = 0.0
    nominalization_ratio: float = 0.0
    adverb_ratio: float = 0.0
    connective_ratio: float = 0.0
    question_ratio: float = 0.0
    comma_per_sentence: float = 0.0
    parenthetical_ratio: float = 0.0
    consecutive_same_start: int = 0
    start_variety: float = 1.0
    longest_sentences: list = field(default_factory=list)
    passive_examples: list = field(default_factory=list)

    def as_dict(self) -> dict:
        d = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.__dict__.items()}
        return d


def _is_passive_en(toks: list[str]) -> bool:
    low = [t.lower() for t in toks]
    for i, t in enumerate(low[:-1]):
        if t in BE_FORMS:
            for j in (i + 1, i + 2, i + 3):     # allow "was clearly not written"
                if j >= len(low):
                    break
                nxt = low[j]
                if nxt in EN_IRREGULAR_PP or (EN_PP.match(nxt) and len(nxt) > 4):
                    return True
                if nxt not in {"not", "never", "also", "already", "being", "then", "just",
                               "still", "often", "well", "clearly", "widely", "fully"} \
                        and not nxt.endswith("ly"):
                    break
    return False


def _is_passive_fr(sent: str, toks: list[str]) -> bool:
    low = [t.lower() for t in toks]
    for i, t in enumerate(low[:-1]):
        if t in ETRE_FORMS:
            for j in (i + 1, i + 2):
                if j >= len(low):
                    break
                nxt = low[j]
                if FR_PP.match(nxt) and len(nxt) > 3:
                    # "est fait par X" is passive; "est fatigué" (state) needs an agent or
                    # a clearly transitive participle, so require an agent or -é(e)(s).
                    return bool(FR_AGENT.search(sent)) or nxt.endswith(("é", "ée", "és", "ées"))
                if nxt not in {"pas", "plus", "jamais", "aussi", "déjà", "bien", "très", "alors"}:
                    break
    return False


def analyse(sents: list[str], lp: LangPack) -> SyntaxReport:
    r = SyntaxReport(n_sentences=len(sents))
    if not sents:
        return r
    tok = [words(s) for s in sents]
    lens = [len(t) for t in tok if t]
    if not lens:
        return r
    r.mean_len = sum(lens) / len(lens)
    r.median_len = st.median(lens)
    r.p90_len = sorted(lens)[max(0, int(len(lens) * 0.9) - 1)]
    r.max_len = max(lens)
    r.stdev_len = st.pstdev(lens) if len(lens) > 1 else 0.0
    r.variation = r.stdev_len / r.mean_len if r.mean_len else 0.0

    long_cut = LONG_SENT.get(lp.code, 25)
    vlong_cut = VERY_LONG.get(lp.code, 40)
    r.pct_long = sum(1 for n in lens if n > long_cut) / len(lens)
    r.pct_very_long = sum(1 for n in lens if n > vlong_cut) / len(lens)
    r.pct_short = sum(1 for n in lens if n <= 8) / len(lens)

    passive = 0
    for s, t in zip(sents, tok):
        if not t:
            continue
        hit = _is_passive_en(t) if lp.code == "en" else (_is_passive_fr(s, t) if lp.code == "fr" else False)
        if hit:
            passive += 1
            if len(r.passive_examples) < 5:
                r.passive_examples.append(s[:180])
    r.passive_ratio = passive / len(sents)

    all_words = [w.lower() for t in tok for w in t]
    n = len(all_words) or 1
    r.nominalization_ratio = sum(1 for w in all_words if len(w) > 6 and w.endswith(lp.nominal)) / n
    if lp.adverb:
        r.adverb_ratio = sum(1 for w in all_words if len(w) > 5 and w.endswith(lp.adverb)) / n

    conn = 0
    for s in sents:
        low = " " + s.lower() + " "
        if any((" " + c + " ") in low or low.lstrip().startswith(c + " ") for c in lp.connectives):
            conn += 1
    r.connective_ratio = conn / len(sents)

    r.question_ratio = sum(1 for s in sents if s.rstrip().endswith(("?", "? "))) / len(sents)
    r.comma_per_sentence = sum(s.count(",") for s in sents) / len(sents)
    r.parenthetical_ratio = sum(1 for s in sents if "(" in s or " - " in s or "—" in s) / len(sents)

    starts = [t[0].lower() for t in tok if t]
    run = best = 1
    for a, b in zip(starts, starts[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    r.consecutive_same_start = best
    r.start_variety = len(set(starts)) / len(starts) if starts else 1.0

    r.longest_sentences = [
        {"words": len(t), "text": s[:220]}
        for s, t in sorted(zip(sents, tok), key=lambda p: -len(p[1]))[:5] if len(t) > long_cut
    ]
    return r
