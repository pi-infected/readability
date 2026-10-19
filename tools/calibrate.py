#!/usr/bin/env python
"""Confront the target bands with pages whose typography is deliberate.

The bands in scoring.py come from the literature (Bringhurst's measure, WCAG contrast,
Yoast's transition-word share). This script measures a reference set of pages that are
widely held up as well-set, and reports, per metric, how many of them our band accepts.

A band that rejects most of the reference set is either wrong or is asserting a standard
the web does not meet — and the report has to say which. Run:

    python tools/calibrate.py --out calibration/reference.json
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from readlens.analysis import analyse_page                      # noqa: E402
from readlens.fetch import Cache, Fetcher                       # noqa: E402
from readlens.render import Renderer                            # noqa: E402
from readlens.scoring import band_score                         # noqa: E402

# One page per site. Chosen because each is either a typography authority, a public
# service written under a plain-language mandate, or a publication whose reading
# experience is its product. Not a random sample of the web, on purpose.
REFERENCE = [
    ("practicaltypography.com", "https://practicaltypography.com/typography-in-ten-minutes.html"),
    ("mdn", "https://developer.mozilla.org/en-US/docs/Web/CSS/font-size"),
    ("nngroup", "https://www.nngroup.com/articles/legibility-readability-comprehension/"),
    ("wikipedia", "https://en.wikipedia.org/wiki/Typography"),
    ("web.dev", "https://web.dev/articles/font-best-practices"),
    ("css-tricks", "https://css-tricks.com/typography-for-developers/"),
    ("smashing", "https://www.smashingmagazine.com/2020/07/css-techniques-legibility/"),
    ("tailwind docs", "https://tailwindcss.com/docs/font-size"),
    ("service-public.fr", "https://www.service-public.fr/particuliers/vosdroits/F1966"),
    ("le monde", "https://www.lemonde.fr/"),
    ("stripe docs", "https://docs.stripe.com/payments/quickstart"),
    ("mozilla blog", "https://blog.mozilla.org/"),
    ("a list apart", "https://alistapart.com/article/on-web-typography/"),
]


def collect(urls, *, concurrency=4, audience="general") -> list[dict]:
    fetcher = Fetcher(cache=Cache(Path(".readlens-cache")), delay=0.6)
    pages, rows = [], []
    try:
        for name, url in urls:
            page = fetcher.get(url)
            if not page.ok:
                print(f"  skip {name}: {page.error or page.status}", file=sys.stderr)
                continue
            pages.append((name, page))
        renderer = Renderer(concurrency=concurrency)
        renderer.__enter__()
        try:
            if renderer.error:
                print(f"  no browser: {renderer.error}", file=sys.stderr)
                renders = {}
            else:
                print(f"  rendering {len(pages)} pages, concurrency {renderer.concurrency} "
                      f"({renderer.concurrency_note})", file=sys.stderr)
                renders = renderer.render_many([p.final_url for _, p in pages])
        finally:
            renderer.__exit__()
    finally:
        fetcher.close()

    for name, page in pages:
        pa = analyse_page(page, render_result=renders.get(page.final_url), audience=audience)
        if not pa.ok or not pa.scores:
            continue
        rows.append({
            "name": name, "url": pa.final_url, "page_type": pa.scores.page_type,
            "score": pa.scores.overall, "grade": pa.scores.grade,
            "metrics": {m.key: {"value": m.value, "ideal": list(m.ideal),
                                "tolerable": list(m.tolerable), "score": m.score,
                                "label": m.label, "pillar": m.pillar}
                        for m in pa.scores.metrics if m.value is not None},
        })
    return rows


def summarise(rows: list[dict]) -> list[dict]:
    keys: dict[str, dict] = {}
    for r in rows:
        for k, m in r["metrics"].items():
            e = keys.setdefault(k, {"key": k, "label": m["label"], "pillar": m["pillar"],
                                    "ideal": m["ideal"], "tolerable": m["tolerable"],
                                    "values": [], "by_site": {}})
            e["values"].append(m["value"])
            e["by_site"][r["name"]] = m["value"]
    out = []
    for e in keys.values():
        v = sorted(e["values"])
        n = len(v)
        if n < 4:
            continue
        lo, hi = e["ideal"]
        tlo, thi = e["tolerable"]
        e.update({
            "n": n,
            "min": round(v[0], 3), "max": round(v[-1], 3),
            "median": round(st.median(v), 3),
            "p10": round(v[max(0, int(n * 0.10) - 1)], 3),
            "p90": round(v[min(n - 1, int(n * 0.90))], 3),
            "in_ideal": sum(1 for x in v if lo <= x <= hi) / n,
            "in_tolerable": sum(1 for x in v if tlo <= x <= thi) / n,
            "mean_score": round(sum(band_score(x, tuple(e["ideal"]), tuple(e["tolerable"]))
                                    for x in v) / n, 1),
        })
        out.append(e)
    out.sort(key=lambda e: e["in_ideal"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="calibration/reference.json")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--audience", default="general")
    a = ap.parse_args()

    rows = collect(REFERENCE, concurrency=a.concurrency, audience=a.audience)
    summary = summarise(rows)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"pages": rows, "metrics": summary}, indent=2,
                                      ensure_ascii=False), encoding="utf8")

    print(f"\n{len(rows)} reference pages\n")
    print(f"{'metric':<38}{'n':>3}{'median':>9}{'p10':>8}{'p90':>8}"
          f"{'ideal':>16}{'in ideal':>10}{'in tol':>8}{'score':>7}")
    for e in summary:
        band = f"{e['ideal'][0]:g}-{e['ideal'][1]:g}"
        print(f"{e['label'][:36]:<38}{e['n']:>3}{e['median']:>9.2f}{e['p10']:>8.2f}"
              f"{e['p90']:>8.2f}{band:>16}{e['in_ideal']:>9.0%}{e['in_tolerable']:>8.0%}"
              f"{e['mean_score']:>7.1f}")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
