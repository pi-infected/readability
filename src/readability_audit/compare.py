"""Compare two audits of the same site, or several sites against each other."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf8"))


def _pages(d: dict) -> dict:
    return {p.get("final_url") or p.get("url"): p for p in d.get("pages", []) if not p.get("error")}


def diff(old: dict, new: dict) -> dict:
    """What changed between two runs: score, pillars, findings, per page."""
    po, pn = _pages(old), _pages(new)
    common = sorted(set(po) & set(pn))
    rows = []
    for url in common:
        a, b = po[url], pn[url]
        delta = round((b.get("score") or 0) - (a.get("score") or 0), 1)
        fa = {f["key"] for f in a.get("findings", [])}
        fb = {f["key"] for f in b.get("findings", [])}
        rows.append({
            "url": url,
            "before": a.get("score"), "after": b.get("score"), "delta": delta,
            "grade_before": a.get("grade"), "grade_after": b.get("grade"),
            "fixed": sorted(fa - fb), "new": sorted(fb - fa),
            # A pillar only one run measured has no delta: it was not compared.
            "pillars": {k: round(b["pillars"][k]["score"] - a["pillars"][k]["score"], 1)
                        for k in set(a.get("pillars") or {}) & set(b.get("pillars") or {})},
        })
    rows.sort(key=lambda r: r["delta"])

    so, sn = old.get("summary", {}), new.get("summary", {})
    # A finding about a pillar the other run did not measure is neither resolved nor new.
    both = set(so.get("pillars") or {}) & set(sn.get("pillars") or {})
    fa = {f["key"]: f for f in old.get("top_findings", []) if f.get("pillar") in both}
    fb = {f["key"]: f for f in new.get("top_findings", []) if f.get("pillar") in both}
    sel_a = (old.get("options") or {}).get("selection")
    sel_b = (new.get("options") or {}).get("selection")
    return {
        "base_url": new.get("base_url"),
        "before": {"at": old.get("started_at"), "score": so.get("score"), "grade": so.get("grade"),
                   "pages": so.get("pages_analysed")},
        "after": {"at": new.get("started_at"), "score": sn.get("score"), "grade": sn.get("grade"),
                  "pages": sn.get("pages_analysed")},
        "delta": round((sn.get("score") or 0) - (so.get("score") or 0), 1),
        "pillar_delta": {k: round(sn["pillars"][k] - so["pillars"][k], 1) for k in sorted(both)},
        "pillars_not_compared": sorted(set(so.get("pillars") or {}) ^ set(sn.get("pillars") or {})),
        "selection_changed": sel_a != sel_b,
        "selection": {"before": sel_a, "after": sel_b},
        "resolved": [{"key": k, "title": v["title"], "was": v["affected_pages"]}
                     for k, v in fa.items() if k not in fb],
        "introduced": [{"key": k, "title": v["title"], "severity": v["severity"],
                        "pages": v["affected_pages"]} for k, v in fb.items() if k not in fa],
        "changed": [{"key": k, "title": fb[k]["title"],
                     "before": fa[k]["affected_pages"], "after": fb[k]["affected_pages"]}
                    for k in set(fa) & set(fb)
                    if fa[k]["affected_pages"] != fb[k]["affected_pages"]],
        "pages": rows,
        "only_before": sorted(set(po) - set(pn)),
        "only_after": sorted(set(pn) - set(po)),
    }


def rank(reports: list[dict]) -> dict:
    """Line up several sites side by side."""
    rows = []
    for d in reports:
        s = d.get("summary", {})
        c = d.get("consistency", {})
        rows.append({
            "site": d.get("base_url"),
            "score": s.get("score"), "grade": s.get("grade"),
            "pages": s.get("pages_analysed"),
            "pillars": s.get("pillars", {}),
            "consistency": s.get("consistency_score"),
            "worst_page": s.get("worst_page_score"),
            "critical": s.get("severity_counts", {}).get("critical", 0),
            "body_font": (c.get("body_font_px") or {}).get("values"),
            "reading_level": (c.get("reading_level") or {}),
            "top_issue": (d.get("top_findings") or [{}])[0].get("title"),
        })
    rows.sort(key=lambda r: -(r["score"] or 0))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {"sites": rows}
