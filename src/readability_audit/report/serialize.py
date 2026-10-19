"""Turn the analysis objects into plain JSON-safe structures."""
from __future__ import annotations

import time
from dataclasses import is_dataclass


def _plain(v):
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, dict):
        return {str(k): _plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [_plain(x) for x in v]
    if hasattr(v, "as_dict"):
        return _plain(v.as_dict())
    if is_dataclass(v):
        return {k: _plain(x) for k, x in v.__dict__.items()}
    return str(v)


def page_to_dict(pa, *, include_evidence: bool = True) -> dict:
    d = {
        "url": pa.url,
        "final_url": pa.final_url,
        "status": pa.status,
        "error": pa.error,
        "title": pa.title,
        "language": {"declared": pa.lang_declared,
                     "declared_after_render": pa.lang_declared_rendered,
                     "used_for_metrics": pa.lang_used,
                     "rules": getattr(pa, "lang_rules", pa.lang_used)},
        "fetch_ms": pa.fetch_ms,
        "rendered": pa.rendered,
        "fetched_at": (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(pa.fetched_at))
                       if pa.fetched_at else None),
        "from_cache": pa.from_cache,
        "revalidated": pa.revalidated,
    }
    if not pa.ok:
        return d
    d["page_type"] = pa.scores.page_type if pa.scores else None
    d["score"] = pa.scores.overall if pa.scores else None
    d["grade"] = pa.scores.grade if pa.scores else None
    d["pillars"] = pa.scores.pillars if pa.scores else {}
    d["extraction"] = pa.extraction
    d["counts"] = pa.counts
    d["formulas"] = {k: {"name": f.name, "value": f.value, "unit": f.unit,
                         "band": f.band, "note": f.note} for k, f in pa.formulas.items()}
    from ..metrics.formulas import consensus_grade
    d["formulas_consensus_grade"] = consensus_grade(pa.formulas)
    d["syntax"] = _plain(pa.syntax)
    d["lexical"] = _plain(pa.lexical)
    d["structure"] = _plain(pa.structure)
    d["typography"] = _plain(pa.typography)
    d["accessibility"] = _plain(pa.a11y)
    d["metrics"] = [m.as_dict() for m in (pa.scores.metrics if pa.scores else [])]
    d["findings"] = [f.as_dict() for f in pa.findings]
    if include_evidence:
        d["hardest_paragraphs"] = pa.hardest_paragraphs
        d["rewrite_hints"] = [h.as_dict() for h in pa.hints]
        d["screenshots"] = pa.screenshots
    return d


SCHEMA_VERSION = 1


def methodology(pages: list) -> list[dict]:
    """One entry per metric, deduplicated: what it is, its band, its weight, why."""
    seen: dict[str, dict] = {}
    for p in pages:
        for m in (p.get("metrics") or []):
            e = seen.setdefault(m["key"], {
                "key": m["key"], "label": m["label"], "pillar": m["pillar"],
                "unit": m["unit"], "why": m.get("why", ""), "advice": m.get("advice", ""),
                "bands": [],
            })
            band = {"ideal": m["ideal"], "tolerable": m["tolerable"], "weight": m["weight"],
                    "page_type": p.get("page_type")}
            if band not in e["bands"]:
                e["bands"].append(band)
    return sorted(seen.values(), key=lambda d: (d["pillar"], d["label"]))


def site_to_dict(rep, *, include_evidence: bool = True, artifacts: list | None = None) -> dict:
    from ..scoring import PILLARS
    from ..validation import PROVENANCE

    pages = [page_to_dict(p, include_evidence=include_evidence) for p in rep.pages]
    meth = methodology(pages)
    # A metric's advice and rationale are the same on every page: they are stated once,
    # in `methodology`, instead of 500 times (a third of a large site's JSON).
    for p in pages:
        for m in p.get("metrics") or []:
            m.pop("advice", None)
            m.pop("why", None)
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "readability", "version": rep.options.get("version", "0.1.0")},
        "base_url": rep.base_url,
        "started_at": rep.started_at,
        "duration_s": rep.duration_s,
        "options": rep.options,
        "coverage": (rep.summary or {}).get("coverage", {}),
        "summary": rep.summary,
        "consistency": rep.consistency,
        "top_findings": rep.top_findings,
        "errors": rep.errors,
        "redirected_offsite": getattr(rep, "offsite", []),
        "duplicates_skipped": getattr(rep, "duplicates", []),
        "not_html_skipped": getattr(rep, "skipped", []),
        "pages": pages,
        # Everything needed to read the numbers above without another file.
        "scoring": {
            "pillars": {k: {"label": v[0], "description": v[1], "weight": v[2]}
                        for k, v in PILLARS.items()},
            "band_score": "100 inside the ideal band, 60 at the edge of the tolerable "
                          "range, 0 one span beyond. Pillars are weighted means minus a "
                          "penalty per concrete defect, capped so a pillar degrades "
                          "rather than collapses.",
            "site_score": "70% mean page score, 20% worst page, 10% consistency. Pages "
                          "with no readable content are unscorable and left out.",
        },
        "methodology": meth,
        "validation": PROVENANCE,
        "artifacts": artifacts or [],
    }
