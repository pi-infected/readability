#!/usr/bin/env python
"""Freeze a handful of labelled pairs so the ordinal test runs offline, forever."""
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from validate_difficulty import UA, WIKIS, clean, fetch_full  # noqa: E402

PAIRS = {"en": ["Volcano", "Democracy", "Dinosaur", "Ocean", "Bacteria", "Galaxy"],
         "fr": ["Volcan", "Démocratie", "Dinosaure", "Océan", "Bactérie", "Galaxie"]}
MAX = 4000


def grab(client, api, title):
    """Reuse the harness fetch: it retries, backs off, and never reports a refusal as data."""
    text, status = fetch_full(client, api, title, delay=1.2, attempts=4)
    if not text:
        print(f"    ({title}: {status})", file=sys.stderr)
    return text


def main():
    out = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=40, follow_redirects=True) as c:
        for lang, titles in PAIRS.items():
            for t in titles:
                easy = grab(c, WIKIS[lang]["easy"], t)
                hard = grab(c, WIKIS[lang]["hard"], t)
                if not easy or not hard:
                    print(f"skip {lang}/{t}", file=sys.stderr)
                    continue
                out.append({"lang": lang, "topic": t,
                            "easy": clean(easy, MAX), "hard": clean(hard, MAX)})
                print(f"  {lang}/{t}: {len(out[-1]['easy'])} vs {len(out[-1]['hard'])} chars")
    dest = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "difficulty_pairs.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")
    print(f"wrote {dest} ({len(out)} pairs, {dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
