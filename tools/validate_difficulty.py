#!/usr/bin/env python
"""Test the difficulty metrics against labelled ground truth, in English and French.

Simple English Wikipedia and Vikidia are the same encyclopaedias written for a younger
reader. An article pair on one topic is therefore two texts about exactly the same thing
at two known difficulty levels — which is the only kind of evidence that can falsify a
readability metric without a paid corpus.

The test is ordinal and asks one question per pair: does the metric put the simple version
on the easy side of the hard one? Absolute calibration is not needed and not claimed.

    python tools/validate_difficulty.py --out calibration/difficulty.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import statistics as st
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from readlens.lang import pack                                   # noqa: E402
from readlens.metrics import lexical, syntax                     # noqa: E402
from readlens.metrics.formulas import compute, count             # noqa: E402
from readlens.text import sentences                              # noqa: E402

UA = "readlens/0.1 (readability research; contact via repository)"

WIKIS = {
    "en": {"easy": "https://simple.wikipedia.org/w/api.php",
           "hard": "https://en.wikipedia.org/w/api.php"},
    "fr": {"easy": "https://fr.vikidia.org/w/api.php",
           "hard": "https://fr.wikipedia.org/w/api.php"},
}

TOPICS = {
    "en": ["Photosynthesis", "Volcano", "Democracy", "Gravity", "Dinosaur", "Water", "Sun",
           "Moon", "Electricity", "Brain", "Ocean", "Mountain", "Money", "Computer",
           "Chocolate", "Evolution", "Vaccine", "Climate", "Bird", "Tree", "Earthquake",
           "Language", "Music", "Rainbow", "Magnet", "Blood", "Desert", "Glacier",
           "Telescope", "Bacteria", "Gold", "Salt", "Coffee", "Bridge", "Railway",
           "Vitamin", "Antarctica", "Amazon rainforest", "Solar System", "Galaxy",
           "Democracy in ancient Athens", "Middle Ages", "Renaissance", "Printing press",
           "Vaccination", "Electricity generation", "Photography", "Cinema", "Football",
           "Chess", "Bee", "Whale", "Butterfly", "Mushroom", "Wheat", "Rice", "Cotton",
           "Iron", "Plastic", "Paper"],
    "fr": ["Photosynthèse", "Volcan", "Démocratie", "Gravité", "Dinosaure", "Eau", "Soleil",
           "Lune", "Électricité", "Cerveau", "Océan", "Montagne", "Monnaie", "Ordinateur",
           "Chocolat", "Évolution", "Vaccin", "Climat", "Oiseau", "Arbre", "Séisme",
           "Langage", "Musique", "Arc-en-ciel", "Aimant", "Sang", "Désert", "Glacier",
           "Télescope", "Bactérie", "Or", "Sel", "Café", "Pont", "Chemin de fer",
           "Vitamine", "Antarctique", "Forêt amazonienne", "Système solaire", "Galaxie",
           "Moyen Âge", "Renaissance", "Imprimerie", "Vaccination", "Photographie",
           "Cinéma", "Football", "Échecs", "Abeille", "Baleine", "Papillon", "Champignon",
           "Blé", "Riz", "Coton", "Fer", "Plastique", "Papier", "Cheval", "Requin"],
}

# metric key -> (getter, direction) where direction is +1 when a HIGHER value means harder
METRICS = {
    "lix": (lambda f, s, l: f["lix"].value if "lix" in f else None, +1),
    "flesch": (lambda f, s, l: f["flesch_reading_ease"].value if "flesch_reading_ease" in f else None, -1),
    "flesch_kincaid": (lambda f, s, l: f["flesch_kincaid_grade"].value if "flesch_kincaid_grade" in f else None, +1),
    "gunning_fog": (lambda f, s, l: f["gunning_fog"].value if "gunning_fog" in f else None, +1),
    "coleman_liau": (lambda f, s, l: f["coleman_liau"].value if "coleman_liau" in f else None, +1),
    "ari": (lambda f, s, l: f["ari"].value if "ari" in f else None, +1),
    "rix": (lambda f, s, l: f["rix"].value if "rix" in f else None, +1),
    "avg_sentence_len": (lambda f, s, l: s.mean_len, +1),
    "pct_long_sentences": (lambda f, s, l: s.pct_long, +1),
    "pct_polysyllabic": (lambda f, s, l: l.pct_polysyllabic, +1),
    "pct_long_words": (lambda f, s, l: l.pct_long_words, +1),
    "word_rarity_zipf": (lambda f, s, l: l.mean_zipf or None, -1),
    "pct_rare_words": (lambda f, s, l: l.pct_rare, +1),
    "passive_ratio": (lambda f, s, l: s.passive_ratio, +1),
    "nominalization": (lambda f, s, l: s.nominalization_ratio, +1),
    "lexical_density": (lambda f, s, l: l.lexical_density, +1),
    "vocab_diversity": (lambda f, s, l: l.mattr, +1),
}

SECTION = re.compile(r"^\s*=+.*=+\s*$", re.M)
MIN_SENTENCES = 5          # a lead section is short; below this the formulas are noise


def fetch_batch(client: httpx.Client, api: str, titles: list[str], *, delay: float = 1.0,
                attempts: int = 4) -> dict[str, tuple[str | None, str]]:
    """Fetch up to 20 articles in one call. Returns {title: (text, status)}.

    A network failure must never be reported as a missing page: the caller has to be able
    to tell "this wiki has no article on X" from "the API refused us".
    """
    out: dict[str, tuple[str | None, str]] = {}
    last = "unknown"
    for attempt in range(attempts):
        time.sleep(delay * (1 + attempt * 2))          # polite, and backs off on refusal
        try:
            # exlimit only exceeds 1 for intro extracts. That is not a workaround: the
            # lead section covers the same scope in both wikis, where full articles
            # differ wildly in how much ground they cover.
            r = client.get(api, params={"action": "query", "prop": "extracts",
                                        "explaintext": 1, "exintro": 1, "format": "json",
                                        "titles": "|".join(titles), "redirects": 1,
                                        "exlimit": "max"})
            if r.status_code != 200:
                last = f"http {r.status_code}"
                continue
            data = r.json().get("query", {}) or {}
            # redirects and normalisations rename titles; map them back to what we asked
            alias = {}
            for key in ("normalized", "redirects"):
                for item in data.get(key, []) or []:
                    alias[item["to"]] = alias.get(item["from"], item["from"])
            for p_ in (data.get("pages") or {}).values():
                asked = alias.get(p_.get("title"), p_.get("title"))
                if "missing" in p_:
                    out[asked] = (None, "no such article")
                else:
                    text = p_.get("extract")
                    out[asked] = (text, "ok") if text else (None, "empty extract")
            if out:
                break
        except Exception as e:
            last = type(e).__name__
    for t in titles:
        out.setdefault(t, (None, last))
    return out


def clean(text: str, max_chars: int = 20000) -> str:
    text = SECTION.sub("", text)
    text = re.sub(r"\n{2,}", "\n\n", text).strip()
    return text[:max_chars]


def measure(text: str, code: str) -> dict:
    lp = pack(code)
    paras = [p for p in text.split("\n") if len(p.strip()) > 30]
    sents = [s for p in paras for s in sentences(p, lp)]
    if len(sents) < MIN_SENTENCES:
        return {}
    f = compute(count(sents, lp), lp, text)
    s = syntax.analyse(sents, lp)
    l = lexical.analyse(text, lp)
    out = {}
    for key, (get, _) in METRICS.items():
        try:
            v = get(f, s, l)
        except Exception:
            v = None
        if v is not None:
            out[key] = round(float(v), 4)
    out["_sentences"] = len(sents)
    out["_words"] = l.n_words
    return out


def sign_test_p(hits: int, n: int) -> float:
    """Two-sided binomial p under the null that the metric is a coin flip."""
    if n == 0:
        return 1.0
    k = max(hits, n - hits)
    tail = sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def fetch_full(client: httpx.Client, api: str, title: str, *, delay: float = 1.0,
               attempts: int = 3) -> tuple[str | None, str]:
    """Full article text. One title per call: the API caps exlimit at 1 without exintro."""
    last = "unknown"
    for attempt in range(attempts):
        time.sleep(delay * (1 + attempt * 2))
        try:
            r = client.get(api, params={"action": "query", "prop": "extracts",
                                        "explaintext": 1, "format": "json",
                                        "titles": title, "redirects": 1})
            if r.status_code != 200:
                last = f"http {r.status_code}"
                continue
            for p_ in ((r.json().get("query", {}) or {}).get("pages", {}) or {}).values():
                if "missing" in p_:
                    return None, "no such article"
                return (p_.get("extract"), "ok") if p_.get("extract") else (None, "empty")
        except Exception as e:
            last = type(e).__name__
    return None, last


def run(lang: str, topics: list[str], limit: int, delay: float = 1.0
        ) -> tuple[list[dict], list[dict]]:
    pairs, skipped = [], []
    wanted = topics[:limit]
    with httpx.Client(headers={"User-Agent": UA}, timeout=40, follow_redirects=True) as c:
        easy_all: dict[str, tuple[str | None, str]] = {}
        hard_all: dict[str, tuple[str | None, str]] = {}
        for i in range(0, len(wanted), 20):            # the API's own batch limit
            chunk = wanted[i:i + 20]
            easy_all |= fetch_batch(c, WIKIS[lang]["easy"], chunk, delay=delay)
            hard_all |= fetch_batch(c, WIKIS[lang]["hard"], chunk, delay=delay)
        for title in wanted:
            easy, se = easy_all.get(title, (None, "not returned"))
            hard, sh = hard_all.get(title, (None, "not returned"))
            if not easy or not hard:
                why = f"easy: {se}, hard: {sh}"
                skipped.append({"lang": lang, "topic": title, "reason": why})
                print(f"  skip {lang}/{title} ({why})", file=sys.stderr)
                continue
            me, mh = measure(clean(easy), lang), measure(clean(hard), lang)
            unit = "lead"
            if not me or not mh:
                # A short lead is common on the simple wikis. Refetch BOTH sides in full,
                # never one lead against one whole article: the unit must match inside a pair.
                fe, se2 = fetch_full(c, WIKIS[lang]["easy"], title, delay=delay)
                fh, sh2 = fetch_full(c, WIKIS[lang]["hard"], title, delay=delay)
                if fe and fh:
                    me, mh = measure(clean(fe), lang), measure(clean(fh), lang)
                    unit = "full"
                if not me or not mh:
                    why = (f"lead under {MIN_SENTENCES} sentences; full text "
                           f"easy: {se2}, hard: {sh2}")
                    skipped.append({"lang": lang, "topic": title, "reason": why})
                    print(f"  skip {lang}/{title} ({why})", file=sys.stderr)
                    continue
            pairs.append({"lang": lang, "topic": title, "unit": unit,
                          "easy": me, "hard": mh})
    return pairs, skipped


def score(pairs: list[dict]) -> list[dict]:
    out = []
    for key, (_, direction) in METRICS.items():
        hits, deltas = 0, []
        for p in pairs:
            if key not in p["easy"] or key not in p["hard"]:
                continue
            e, h = p["easy"][key], p["hard"][key]
            if e == h:
                continue
            deltas.append((h - e) * direction)
            if (h - e) * direction > 0:          # the hard text is on the hard side
                hits += 1
        n = len(deltas)
        if n < 5:
            continue
        out.append({"metric": key, "n": n, "accuracy": hits / n,
                    "mean_delta": round(st.mean(deltas), 4),
                    "median_delta": round(st.median(deltas), 4),
                    "p_value": round(sign_test_p(hits, n), 5)})
    out.sort(key=lambda d: -d["accuracy"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="calibration/difficulty.json")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--langs", nargs="*", default=["en", "fr"])
    ap.add_argument("--delay", type=float, default=1.0, help="base delay between API calls")
    a = ap.parse_args()

    all_pairs, all_skipped, report = [], [], {}
    for lang in a.langs:
        print(f"\n{lang}: fetching pairs", file=sys.stderr)
        pairs, skipped = run(lang, TOPICS[lang], a.limit, delay=a.delay)
        all_pairs += pairs
        all_skipped += skipped
        report[lang] = {"pairs": len(pairs), "skipped": len(skipped),
                        "metrics": score(pairs)}

    report["all"] = {"pairs": len(all_pairs), "skipped": len(all_skipped),
                     "metrics": score(all_pairs)}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"summary": report, "pairs": all_pairs,
                                       "skipped": all_skipped}, indent=2,
                                      ensure_ascii=False), encoding="utf8")

    for lang, r in report.items():
        print(f"\n{lang} — {r['pairs']} aligned pairs, {r.get('skipped', 0)} skipped")
        print(f"  {'metric':<22}{'n':>4}{'ranks correctly':>17}{'median delta':>14}{'p':>10}")
        for m in r["metrics"]:
            flag = "" if m["p_value"] < 0.05 else "   (not significant)"
            print(f"  {m['metric']:<22}{m['n']:>4}{m['accuracy']:>16.0%}"
                  f"{m['median_delta']:>14.3f}{m['p_value']:>10.4f}{flag}")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
