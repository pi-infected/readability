"""Tokenisation: sentences, words, syllables. Language-aware, deterministic, no models."""
from __future__ import annotations

import functools
import re
import unicodedata

from .lang import LangPack

_PYPHEN_CACHE: dict[str, object] = {}

WORD_RE = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)
NUM_RE = re.compile(r"(?<![\w.])[+-]?\d[\d  ,.]*\s?(?:%|€|\$|£|k|M|Md|bn|x|×)?", re.UNICODE)
URL_RE = re.compile(r"https?://\S+|www\.\S+")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,6}(?:s)?\b")
SENT_END = re.compile(r"([.!?…]+[\"'»”’\)\]]*)(\s+|$)")
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def words(text: str) -> list[str]:
    return WORD_RE.findall(text)


def sentences(text: str, lp: LangPack) -> list[str]:
    """Split one block of text into sentences. Abbreviation- and number-aware."""
    # A block's own text can carry newlines from block boundaries or a wrapped Markdown
    # link. They are not sentence boundaries and must not survive into the word counts.
    text = re.sub(r"\s*\n\s*", " ", text).strip()
    if not text:
        return []
    def _protect(m):
        u = m.group(0)
        trail = ""
        while u and u[-1] in ".,;:!?)]":          # trailing punctuation is the sentence's
            trail, u = u[-1] + trail, u[:-1]
        return u.replace(".", "\x00") + trail

    protected = URL_RE.sub(_protect, text)
    out, start = [], 0
    for m in SENT_END.finditer(protected):
        end = m.end(1)
        chunk = protected[start:end]
        tail = re.findall(r"[^\W\d_]+\.?$", chunk.strip())
        last = (tail[-1].rstrip(".").lower() if tail else "")
        nxt_char = next((ch for ch in protected[m.end():m.end() + 3] if not ch.isspace()), "")
        # An abbreviation only continues the sentence when what follows is not a new one:
        # "janv. Il" ends a sentence, "Dr. Smith" and "e.g. this" do not.
        stripped = chunk.strip()
        # "J. R. R. Tolkien": a capital initial. Not "…/c." at the end of a URL.
        if (len(last) == 1 and last.isalpha() and m.group(1) == "."
                and stripped[-2:-1].isupper()):
            continue
        if last in lp.abbrev and (last in TITLES or not nxt_char.isupper()):
            continue
        # decimal / version number: don't break
        if re.search(r"\d[.,]$", chunk) and re.match(r"\s*\d", protected[end:end + 3]):
            continue
        nxt = protected[m.end():m.end() + 2]
        lower_next = bool(nxt) and nxt[0].islower()
        # A sentence may legitimately open with a lower-case word: product names, commands
        # and identifiers do it constantly on technical writing, and requiring a capital
        # merged three sentences into one 86-word monster. So the lower-case guard is kept
        # only for the two shapes that actually mean "mid-sentence":
        #   an ellipsis  ("Yes... it does")  and a dotted initialism  ("e.g. this works").
        if lower_next and len(m.group(1).rstrip("\"'»”’)]")) > 1:
            continue                                   # ellipsis or "?!"
        if lower_next and DOTTED_ABBREV.search(stripped):
            continue
        s = chunk.strip()
        if s:
            out.append(s)
        start = m.end()
    rest = protected[start:].strip()
    if rest:
        out.append(rest)
    return [s.replace("\x00", ".") for s in out if words(s)]


@functools.lru_cache(maxsize=100_000)
def _syll_pyphen(word: str, locale: str) -> int:
    import pyphen
    d = _PYPHEN_CACHE.get(locale)
    if d is None:
        try:
            d = pyphen.Pyphen(lang=locale)
        except Exception:
            d = False
        _PYPHEN_CACHE[locale] = d
    if not d:
        return 0
    return len(d.inserted(word).split("-"))


# Titles are always followed by a capitalised name, so they never end a sentence.
# "e.g.", "i.e.", "U.S.", "p. ex." — a run of single letters joined by dots.
DOTTED_ABBREV = re.compile(r"(?:\b[^\W\d_]\.){2,}$|\b[^\W\d_]\.\s?[^\W\d_]\.$")

TITLES = {"m", "mme", "mlle", "mr", "mrs", "ms", "dr", "pr", "prof", "st", "ste", "sr", "jr",
          "sir", "lord", "me", "mgr"}

VOWELS = "aeiouyàâäéèêëîïôöùûüÿœæ"

# French words ending in -ent that are NOT 3rd-person-plural verb forms, where the
# ending is pronounced. Verb forms ("parlent") drop it; these do not.
FR_ENT_PRONOUNCED = {
    "souvent", "comment", "cent", "dent", "vent", "lent", "accent", "agent", "argent",
    "urgent", "présent", "absent", "talent", "parent", "moment", "different", "différent",
    "content", "serpent", "arpent", "adjacent", "client", "patient", "orient", "récent",
    "décent", "ardent", "prudent", "évident", "excellent", "violent", "insolent", "opulent",
}


def _syll_heuristic(word: str, code: str) -> int:
    w = word.lower()
    groups = re.findall(f"[{VOWELS}]+", w)
    n = len(groups)
    if code == "fr":
        # silent final e / es / ent (3rd person plural)
        if re.search(r"[^aeiouyàâäéèêëîïôöùûü]e$", w) and n > 1:
            n -= 1
        elif re.search(r"[^aeiouy]es$", w) and n > 1:
            n -= 1
        elif (re.search(r"[^aeiouym]ent$", w) and n > 1
              and not w.endswith(("ient", "ment")) and w not in FR_ENT_PRONOUNCED):
            n -= 1
    else:
        if w.endswith("e") and not w.endswith(("le", "ee", "ie")) and n > 1:
            n -= 1
        if w.endswith("ed") and n > 1 and not re.search(r"[td]ed$", w):
            n -= 1
    return max(1, n)


@functools.lru_cache(maxsize=4)
def _syllapy():
    try:
        import syllapy
        return syllapy
    except Exception:
        return None


def syllables(word: str, lp: LangPack) -> int:
    w = word.lower().strip("'’-")
    if not w:
        return 0
    if lp.code == "en":
        # CMUdict-backed counts beat any letter heuristic for English.
        sp = _syllapy()
        if sp is not None:
            try:
                n = sp.count(w)
                if n:
                    return n
            except Exception:
                pass
    h = _syll_heuristic(w, lp.code)
    if not lp.pyphen:
        return h
    n = _syll_pyphen(w, lp.pyphen)
    if not n:
        return h
    # Languages with a silent final -e (fr) need the heuristic's subtraction, which
    # hyphenation dictionaries do not model. Elsewhere the dictionary under-counts.
    if lp.code == "fr":
        # fr_FR hyphenation points are not syllable boundaries (it refuses to split
        # "orange"); the silent-e heuristic is measurably closer. Verified in tests.
        return h
    return max(1, h, n)


def is_long(word: str, lp: LangPack) -> bool:
    return len(word) > 6  # LIX definition


def is_polysyllabic(word: str, lp: LangPack, threshold: int = 3) -> bool:
    return syllables(word, lp) >= threshold


def reading_time_seconds(word_count: int, lang: str = "en") -> float:
    """Silent reading speed. Brysbaert 2019 meta-analysis: ~238 wpm (en), ~214 (fr)."""
    wpm = {"en": 238, "fr": 214, "es": 228, "de": 224, "it": 217, "nl": 228, "pt": 219}.get(lang, 230)
    return word_count / wpm * 60
