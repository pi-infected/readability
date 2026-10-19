"""Classic readability indices, computed from our own language-aware token counts."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..lang import LangPack
from ..text import syllables, words


@dataclass
class Counts:
    sentences: int = 0
    words: int = 0
    letters: int = 0
    syllables: int = 0
    polysyllabic: int = 0     # >= 3 syllables
    monosyllabic: int = 0
    long_words: int = 0       # > 6 chars (LIX)
    complex_words: int = 0    # Fog: >= 3 syllables, minus common suffix inflections

    @property
    def asl(self) -> float:            # average sentence length (words)
        return self.words / self.sentences if self.sentences else 0.0

    @property
    def asw(self) -> float:            # average syllables per word
        return self.syllables / self.words if self.words else 0.0

    @property
    def awl(self) -> float:            # average word length (letters)
        return self.letters / self.words if self.words else 0.0

    def as_dict(self) -> dict:
        return {
            "sentences": self.sentences, "words": self.words, "letters": self.letters,
            "syllables": self.syllables, "polysyllabic_words": self.polysyllabic,
            "long_words": self.long_words,
            "avg_sentence_length": round(self.asl, 2),
            "avg_syllables_per_word": round(self.asw, 3),
            "avg_word_length": round(self.awl, 2),
        }


FOG_SUFFIX = ("es", "ed", "ing")


def count(sents: list[str], lp: LangPack) -> Counts:
    c = Counts(sentences=len(sents))
    for s in sents:
        for w in words(s):
            c.words += 1
            c.letters += len(w)
            n = syllables(w, lp)
            c.syllables += n
            if n >= 3:
                c.polysyllabic += 1
                base = w.lower()
                stripped = next((base[:-len(sf)] for sf in FOG_SUFFIX if base.endswith(sf)), base)
                if syllables(stripped, lp) >= 3 and "-" not in w:
                    c.complex_words += 1
            elif n == 1:
                c.monosyllabic += 1
            if len(w) > 6:
                c.long_words += 1
    return c


def _band(value: float, cuts: list[tuple[float, str]]) -> str:
    for limit, label in cuts:
        if value < limit:
            return label
    return cuts[-1][1]


FLESCH_BANDS = [(30, "very difficult"), (50, "difficult"), (60, "fairly difficult"),
                (70, "standard"), (80, "fairly easy"), (90, "easy"), (1e9, "very easy")]
LIX_BANDS = [(25, "very easy"), (35, "easy"), (45, "standard"), (55, "difficult"),
             (1e9, "very difficult")]


@dataclass
class Formula:
    key: str
    name: str
    value: float
    unit: str          # "score" | "grade" | "index"
    band: str = ""
    note: str = ""


def compute(c: Counts, lp: LangPack, text: str = "") -> dict[str, Formula]:
    out: dict[str, Formula] = {}
    if c.sentences == 0 or c.words == 0:
        return out
    asl, asw, awl = c.asl, c.asw, c.awl

    if lp.flesch:
        a, b, cc, name = lp.flesch
        v = a - b * asl - cc * asw
        out["flesch_reading_ease"] = Formula(
            "flesch_reading_ease", name, round(v, 1), "score", _band(v, FLESCH_BANDS),
            "0-100, higher is easier",
        )

    fk = 0.39 * asl + 11.8 * asw - 15.59
    out["flesch_kincaid_grade"] = Formula("flesch_kincaid_grade", "Flesch-Kincaid Grade",
                                          round(fk, 1), "grade", "", "US school grade")

    fog = 0.4 * (asl + 100 * (c.complex_words / c.words))
    out["gunning_fog"] = Formula("gunning_fog", "Gunning Fog", round(fog, 1), "grade", "",
                                 "years of formal education")

    if c.sentences >= 3:
        smog = 1.043 * math.sqrt(c.polysyllabic * (30 / c.sentences)) + 3.1291
        note = "years of education" + ("" if c.sentences >= 30 else "; <30 sentences, indicative only")
        out["smog"] = Formula("smog", "SMOG", round(smog, 1), "grade", "", note)

    L = c.letters / c.words * 100
    S = c.sentences / c.words * 100
    cl = 0.0588 * L - 0.296 * S - 15.8
    out["coleman_liau"] = Formula("coleman_liau", "Coleman-Liau", round(cl, 1), "grade", "",
                                  "US school grade")

    ari = 4.71 * awl + 0.5 * asl - 21.43
    out["ari"] = Formula("ari", "Automated Readability Index", round(ari, 1), "grade", "",
                         "US school grade")

    lix = asl + 100 * (c.long_words / c.words)
    out["lix"] = Formula("lix", "LIX", round(lix, 1), "index", _band(lix, LIX_BANDS),
                         "language-independent; lower is easier")

    rix = c.long_words / c.sentences
    out["rix"] = Formula("rix", "RIX", round(rix, 2), "index", "", "long words per sentence")

    if lp.code == "de":
        ms = c.polysyllabic / c.words * 100
        sl = asl
        iw = c.long_words / c.words * 100
        es = c.monosyllabic / c.words * 100
        wstf = 0.1935 * ms + 0.1672 * sl + 0.1297 * iw - 0.0327 * es - 0.875
        out["wiener"] = Formula("wiener", "Wiener Sachtextformel 1", round(wstf, 1), "grade",
                                "", "German school grade")

    if lp.code == "en" and text:
        try:
            import textstat
            textstat.set_lang("en")
            dc = textstat.dale_chall_readability_score(text)
            out["dale_chall"] = Formula("dale_chall", "Dale-Chall", round(dc, 1), "score", "",
                                        "uses the 3000-word familiarity list")
        except Exception:
            pass
    return out


def consensus_grade(fs: dict[str, Formula]) -> float | None:
    """Median of the grade-level formulas — robust to one outlier."""
    vals = sorted(f.value for f in fs.values() if f.unit == "grade")
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    return round(vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2, 1)
