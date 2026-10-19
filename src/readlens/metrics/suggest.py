"""Sentence-level rewrite hints. Rule-based and conservative: it points, it does not rewrite."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..lang import LangPack
from ..text import words

SPLIT_MARKERS = {
    "en": [r",\s+(and|but|so|which|while|although|though|because|since|whereas)\s",
           r";\s", r"\s+—\s+", r",\s+(however|therefore|instead|yet)\b"],
    "fr": [r",\s+(et|mais|donc|qui|que|alors que|bien que|parce que|puisque|tandis que)\s",
           r";\s", r"\s+—\s+", r",\s+(cependant|toutefois|néanmoins|pourtant)\b"],
}

DENOMINALISE = {
    "en": [("ization", "ize"), ("isation", "ise"), ("ation", "ate"), ("ution", "ute"),
           ("ption", "pt"), ("ction", "ct"), ("ment", ""), ("ness", ""), ("ity", "")],
    "fr": [("isation", "iser"), ("ification", "ifier"), ("ation", "er"), ("ition", "ir"),
           ("ement", "er"), ("ité", ""), ("ance", "er"), ("ence", "er")],
}

HINT_TEXT = {
    "en": {
        "split": "{n} words. A natural break sits after word {at} (“{marker}”).",
        "passive": "Passive. Name who does it.",
        "nominal": "“{word}” is a verb wearing a noun's coat — try “{verb}”.",
        "hedge": "“{word}” adds no information. Cut it or replace it with a figure.",
        "start": "{n} sentences in a row open with “{word}”.",
    },
    "fr": {
        "split": "{n} mots. Une coupure naturelle se trouve après le mot {at} (« {marker} »).",
        "passive": "Voix passive. Nommez l'acteur.",
        "nominal": "« {word} » est un verbe déguisé en nom — essayez « {verb} ».",
        "hedge": "« {word} » n'apporte rien. Coupez, ou remplacez par un chiffre.",
        "start": "{n} phrases de suite commencent par « {word} ».",
    },
}


@dataclass
class Hint:
    kind: str
    severity: str
    text: str
    sentence: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "severity": self.severity, "text": self.text,
                "sentence": self.sentence[:260]}


def _denominalise(word: str, lp: LangPack) -> str | None:
    w = word.lower()
    for suf, rep in DENOMINALISE.get(lp.code, []):
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            stem = w[: -len(suf)] + rep
            return stem if len(stem) >= 4 else None
    return None


def _split_point(sentence: str, lp: LangPack) -> tuple[int, str] | None:
    best = None
    n_words = len(words(sentence))
    for pat in SPLIT_MARKERS.get(lp.code, SPLIT_MARKERS["en"]):
        for m in re.finditer(pat, sentence, re.I):
            at = len(words(sentence[: m.start()]))
            # prefer a break near the middle: two readable halves, not a stub
            balance = min(at, n_words - at)
            if balance < 5:
                continue
            if best is None or balance > best[0]:
                best = (balance, at, m.group(0).strip())
    return (best[1], best[2]) if best else None


def hints(sents: list[str], lp: LangPack, syntax_report, lexical_report,
          long_cut: int = 25, limit: int = 12) -> list[Hint]:
    txt = HINT_TEXT.get(lp.code, HINT_TEXT["en"])
    out: list[Hint] = []

    for s in sorted(sents, key=lambda x: -len(words(x)))[:6]:
        n = len(words(s))
        if n <= long_cut:
            break
        sp = _split_point(s, lp)
        if sp:
            out.append(Hint("split", "high" if n > long_cut * 1.6 else "medium",
                            txt["split"].format(n=n, at=sp[0], marker=sp[1]), s))
        else:
            out.append(Hint("split", "medium", txt["split"].format(n=n, at=n // 2, marker="…"), s))

    for s in (syntax_report.passive_examples or [])[:3]:
        out.append(Hint("passive", "medium", txt["passive"], s))

    seen = set()
    for item in (lexical_report.top_terms or []):
        w = item["term"]
        if len(w) < 7 or w in seen:
            continue
        v = _denominalise(w, lp)
        if v and v != w:
            seen.add(w)
            out.append(Hint("nominal", "low", txt["nominal"].format(word=w, verb=v)))
        if len(seen) >= 3:
            break

    for h in (lexical_report.hedges_found or [])[:3]:
        out.append(Hint("hedge", "low", txt["hedge"].format(word=h["term"])))

    if syntax_report.consecutive_same_start >= 3:
        starts = [words(s)[0] for s in sents if words(s)]
        run_word, run, best_word, best = None, 0, None, 0
        for w in starts:
            run = run + 1 if w == run_word else 1
            run_word = w
            if run > best:
                best, best_word = run, w
        if best_word:
            out.append(Hint("start", "low", txt["start"].format(n=best, word=best_word)))

    return out[:limit]
