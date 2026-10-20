"""Site-level audit: crawl, analyse every page, aggregate into one verdict."""
from __future__ import annotations

import hashlib
import re
import statistics as st
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .analysis import PageAnalysis, analyse_page
from .fetch import Cache, Fetcher, normalize, resolve_base, same_site
from .scoring import SEVERITY_ORDER, grade_of

__version__ = "0.1.1"


@dataclass
class SiteReport:
    base_url: str
    started_at: str = ""
    duration_s: float = 0.0
    options: dict = field(default_factory=dict)
    pages: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    consistency: dict = field(default_factory=dict)
    top_findings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    offsite: list = field(default_factory=list)
    duplicates: list = field(default_factory=list)
    skipped: list = field(default_factory=list)


CANONICAL_RE = re.compile(
    r"""<link[^>]+rel=["']?canonical["']?[^>]*>""", re.I)
HREF_RE = re.compile(r"""href=["']([^"']+)["']""", re.I)


def canonical_of(html: str, base: str) -> str | None:
    m = CANONICAL_RE.search(html[:200_000])
    if not m:
        return None
    h = HREF_RE.search(m.group(0))
    if not h:
        return None
    from urllib.parse import urljoin
    try:
        return normalize(urljoin(base, h.group(1)))
    except Exception:
        return None


def _render_cause(err: str) -> str:
    if "bot challenge" in err:
        return "bot challenge"
    m = re.search(r"HTTP \d{3}", err)
    return m.group(0) if m else ("timeout" if "Timeout" in err else err.split(":")[0] or "unknown")


def _failure_breakdown(errors: list[str]) -> dict:
    """Group fetch failures by cause so 50 dead sitemap entries read as one problem."""
    import re
    counts: Counter = Counter()
    examples: dict[str, str] = {}
    for e in errors:
        cause = re.sub(r"^\S+?: ", "", e).strip()
        cause = re.sub(r"\[Errno -?\d+\] .*", "name resolution failed", cause)
        counts[cause] += 1
        examples.setdefault(cause, e.split(":")[0] + ":" + e.split(":")[1]
                            if ":" in e else e)
    return {"total": sum(counts.values()),
            "by_cause": [{"cause": c, "count": n, "example": examples.get(c, "")}
                         for c, n in counts.most_common()]}


def _spread_score(values: list[float], tol: float) -> float:
    """100 when every page agrees, falling as the spread grows past `tol`."""
    vals = [v for v in values if v]
    if len(vals) < 2:
        return 100.0
    spread = max(vals) - min(vals)
    return round(max(0.0, 100.0 * (1 - max(0.0, spread - tol) / max(tol * 3, 1e-9))), 1)


def consistency(pages: list[PageAnalysis]) -> dict:
    ok = [p for p in pages if p.ok and p.scores]
    out: dict = {}
    fonts = [p.typography.primary.body_font_px for p in ok
             if p.typography and p.typography.primary]
    lhs = [p.typography.primary.line_height_ratio for p in ok
           if p.typography and p.typography.primary]
    cprl = [p.typography.primary.chars_per_line for p in ok
            if p.typography and p.typography.primary]
    fams: Counter = Counter()
    for p in ok:
        if p.typography and p.typography.primary:
            for f in p.typography.primary.font_families:
                fams[f["family"]] += f["chars"]

    ok = [p for p in ok if p.scores.overall is not None]
    lix = [m.value for p in ok for m in p.scores.metrics if m.key == "lix" and m.value]
    titles = [p.title.strip() for p in ok if p.title.strip()]
    dupes = [t for t, n in Counter(titles).items() if n > 1]
    no_desc = [p.final_url for p in ok if p.structure and not p.structure.meta_description]
    declared = Counter(p.lang_declared or "(none)" for p in ok)
    used = Counter(p.lang_used for p in ok)

    out["body_font_px"] = {"values": sorted(set(fonts)), "score": _spread_score(fonts, 2.0)}
    out["line_height"] = {"values": sorted(set(lhs)), "score": _spread_score(lhs, 0.15)}
    out["chars_per_line"] = {"min": min(cprl) if cprl else 0, "max": max(cprl) if cprl else 0,
                             "score": _spread_score(cprl, 20)}
    out["font_families"] = [{"family": f, "chars": c} for f, c in fams.most_common(8)]
    out["reading_level"] = {
        "lix_min": min(lix) if lix else None, "lix_max": max(lix) if lix else None,
        "lix_stdev": round(st.pstdev(lix), 1) if len(lix) > 1 else 0.0,
        "score": _spread_score(lix, 12),
    }
    out["duplicate_titles"] = dupes[:10]
    out["pages_without_meta_description"] = no_desc[:20]
    out["languages_declared"] = dict(declared)
    out["languages_measured"] = dict(used)
    # Only what was measured on these pages can agree or disagree.
    for k, vals in (("body_font_px", fonts), ("line_height", lhs), ("chars_per_line", cprl),
                    ("reading_level", lix)):
        out[k]["measured"] = bool(vals)
    sub = [out[k]["score"] for k in ("body_font_px", "line_height", "chars_per_line",
                                     "reading_level") if out[k]["measured"]] or [100.0]
    penalty = 6 * len(dupes) + 2 * len(no_desc) + (10 if len(used) > 1 and len(declared) == 1 else 0)
    out["score"] = round(max(0.0, sum(sub) / len(sub) - penalty), 1)
    return out


def aggregate_findings(pages: list[PageAnalysis]) -> list[dict]:
    bykey: dict[str, dict] = defaultdict(lambda: {"pages": [], "severity": "info", "title": "",
                                                  "pillar": "", "fix": "", "example": None,
                                                  "by_severity": defaultdict(set)})
    for p in pages:
        for f in p.findings:
            e = bykey[f.key]
            e["pillar"] = f.pillar
            e["pages"].append(p.final_url or p.url)
            e["by_severity"][f.severity].add(p.final_url or p.url)
            # The example shows the worst occurrence, so it matches the severity shown.
            worse = SEVERITY_ORDER.get(f.severity, 9) < SEVERITY_ORDER.get(e["severity"], 9)
            if worse:
                e["severity"] = f.severity
            if e["example"] is None or worse:
                e["title"], e["fix"] = f.title, f.fix
                e["example"] = {"url": p.final_url or p.url, "detail": f.detail,
                                "evidence": f.evidence[:4], "params": f.params}
    out = []
    n = max(1, len([p for p in pages if p.ok]))
    for key, e in bykey.items():
        out.append({"key": key, "title": e["title"], "severity": e["severity"],
                    "pillar": e["pillar"], "fix": e["fix"],
                    "affected_pages": len(set(e["pages"])),
                    # The headline severity is the worst page's; this says how many share it.
                    "pages_by_severity": {sev: len(us) for sev, us in sorted(
                        e["by_severity"].items(), key=lambda kv: SEVERITY_ORDER.get(kv[0], 9))},
                    "share": round(len(set(e["pages"])) / n, 3),
                    "example": e["example"], "pages": sorted(set(e["pages"]))[:25]})
    out.sort(key=lambda d: (SEVERITY_ORDER.get(d["severity"], 9), -d["affected_pages"]))
    return out


def audit(base_url: str, *, max_pages: int = 10, render: bool = True, audience: str = "general",
          include: str | None = None, exclude: str | None = None, delay: float = 0.4,
          cache_dir: str | Path | None = ".readability-cache", screenshot_dir: Path | None = None,
          lang: str | None = None, urls: list[str] | None = None, respect_robots: bool = True,
          use_sitemap: bool = True, progress=None, viewports: dict | None = None,
          config: dict | None = None, concurrency: int = 4, selection=None,
          max_depth: int = 2, per_section: int = 0,
          user_agent: str | None = None) -> SiteReport:
    from .render import DEFAULT_VIEWPORTS
    from .select import Selection
    t0 = time.time()
    sel = selection or Selection.from_config(config)
    config = {**(config or {}), "_selection": sel}
    render = render and sel.needs_render
    viewports = sel.viewports(viewports or DEFAULT_VIEWPORTS)
    rep = SiteReport(base_url=base_url,
                     started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     options={"max_pages": max_pages, "render": render, "audience": audience,
                              "include": include, "exclude": exclude, "lang": lang,
                              "respect_robots": respect_robots, "version": __version__,
                              "selection": sel.as_config(), "viewports": sorted(viewports),
                              "per_section": per_section})
    fetcher = Fetcher(cache=Cache(Path(cache_dir) if cache_dir else None), delay=delay,
                      respect_robots=respect_robots, user_agent=user_agent)
    try:
        # A site that moved (www.a.fr -> a.gouv.fr) is audited where it lives; otherwise
        # every page it serves counts as an offsite redirect and nothing is measured.
        if not urls:
            moved = resolve_base(fetcher, base_url)
            if moved != base_url:
                rep.options["redirected_from"] = base_url
                base_url = rep.base_url = moved
        # Ask for spare candidates: redirects, canonicals and duplicates are dropped below,
        # and they should not eat into the page budget.
        targets = urls or fetcher.discover(base_url, max_pages=max_pages * 2, include=include,
                                           exclude=exclude, use_sitemap=use_sitemap,
                                           max_depth=max_depth, per_section=per_section)

        # Fetch first (cheap, cached, polite), then render the whole batch concurrently.
        fetched: list = []
        seen_final: set[str] = set()
        seen_canonical: dict[str, str] = {}
        seen_body: dict[str, str] = {}
        budget = len(targets) if urls else max_pages
        for i, url in enumerate(targets, 1):
            if len(fetched) >= budget:
                break
            if progress:
                progress(min(i, budget), budget, url, "fetch")
            page = fetcher.get(url)
            # A stylesheet or a PDF reached by a link is not a page, nor a failed one.
            ctype = {k.lower(): v for k, v in (page.headers or {}).items()}.get("content-type", "")
            if not page.error and "xml" in ctype and "html" not in ctype:
                page.error = f"not html ({ctype})"      # an RSS feed, a sitemap
            if (page.error or "").startswith("not html"):
                rep.skipped.append({"url": url, "reason": page.error})
                continue
            # An affiliate or outbound redirect leaves the site. Auditing where it lands
            # would put someone else's pages in this site's report and in its score.
            if page.ok and not same_site(base_url, page.final_url):
                rep.offsite.append({"url": url, "landed_on": page.final_url})
                continue
            if page.ok:
                # No page is analysed twice, whichever way the duplicate arrives: a
                # redirect onto one we have, a declared canonical, or the same bytes
                # served under two URLs.
                dup = None
                if page.final_url in seen_final:
                    dup = ("redirect", page.final_url)
                if dup is None:
                    canon = canonical_of(page.html, page.final_url)
                    if canon and same_site(base_url, canon):
                        if canon in seen_canonical and seen_canonical[canon] != page.final_url:
                            dup = ("canonical", seen_canonical[canon])
                        else:
                            seen_canonical.setdefault(canon, page.final_url)
                if dup is None:
                    digest = hashlib.sha256(page.html.encode("utf8", "ignore")).hexdigest()
                    if digest in seen_body:
                        dup = ("identical body", seen_body[digest])
                    else:
                        seen_body[digest] = page.final_url
                if dup:
                    rep.duplicates.append({"url": page.final_url, "reason": dup[0],
                                           "same_as": dup[1]})
                    continue
            seen_final.add(page.final_url)
            fetched.append(page)

        renders: dict = {}
        if render:
            from .render import Renderer
            renderer = Renderer(viewports, screenshot_dir=screenshot_dir,
                                concurrency=concurrency, check_dark=sel.check_dark)
            rep.options["concurrency"] = renderer.concurrency
            rep.options["concurrency_note"] = renderer.concurrency_note
            renderer.__enter__()
            try:
                if renderer.error:
                    rep.errors.append(renderer.error)
                else:
                    live = [p.final_url for p in fetched if p.ok]
                    renders = renderer.render_many(
                        live,
                        on_done=(lambda d, n, u: progress(d, n, u, "render")) if progress else None)
            finally:
                renderer.__exit__()

        for page in fetched:
            pa = analyse_page(page, render_result=renders.get(page.final_url),
                              lang_override=lang, audience=audience, config=config)
            pa.from_cache, pa.revalidated = page.from_cache, page.revalidated
            pa.fetched_at = page.fetched_at
            if not pa.ok:
                rep.errors.append(f"{page.url}: {pa.error}")
            rep.pages.append(pa)
    finally:
        fetcher.close()

    rep.consistency = consistency(rep.pages)
    ok = [p for p in rep.pages if p.ok and p.scores]
    # A page with no readable text is not a zero, it is unscorable. Averaging it in would
    # invent a verdict; leaving it out silently would hide it. It is counted separately.
    gradable = [p for p in ok if p.scores.overall is not None]
    ungradable = [p for p in ok if p.scores.overall is None]
    scores = [p.scores.overall for p in gradable]
    pillars: dict[str, list] = defaultdict(list)
    for p in gradable:
        for k, v in p.scores.pillars.items():
            pillars[k].append(v["score"])
    site_score = round(st.mean(scores), 1) if scores else 0.0
    # A reader lands on one page, not on the average, so the worst page counts; and a site
    # whose pages disagree with each other costs the reader a re-adjustment every click.
    worst = min(scores) if scores else 0.0
    cons = rep.consistency.get("score", 0.0)
    blended = round(0.70 * site_score + 0.20 * worst + 0.10 * cons, 1) if scores else 0.0
    rep.summary = {
        "coverage": {
            "discovered": len(rep.pages),
            "analysed": len(ok),
            "scored": len(gradable),
            "unscorable": len(ungradable),
            "failed": len(rep.pages) - len(ok),
            "redirected_offsite": len(rep.offsite),
        "duplicates_skipped": len(rep.duplicates),
            "duplicates_skipped": len(rep.duplicates),
            "rendered": sum(1 for p in ok if p.rendered),
        },
        "pages_analysed": len(ok),
        "pages_scored": len(gradable),
        "pages_without_content": len(ungradable),
        "pages_failed": len(rep.pages) - len(ok),
        "score": blended,
        "grade": grade_of(blended),
        "mean_page_score": site_score,
        "worst_page_score": worst,
        "best_page_score": max(scores) if scores else 0.0,
        "consistency_score": rep.consistency.get("score", 0.0),
        "pillars": {k: round(st.mean(v), 1) for k, v in pillars.items()},
        "page_types": dict(Counter(p.scores.page_type for p in ok)),
        "total_words": sum(p.structure.word_count for p in ok if p.structure),
        "unscorable_urls": [p.final_url or p.url for p in ungradable][:20],
        "fetch_failures": _failure_breakdown(rep.errors),
        "redirected_offsite": len(rep.offsite),
        "duplicates_skipped": len(rep.duplicates),
        "reading_time_min": round(sum(p.structure.reading_time_min for p in ok if p.structure), 1),
        "severity_counts": dict(Counter(f.severity for p in ok for f in p.findings)),
        "rendered": sum(1 for p in ok if p.rendered),
        # Pages analysed from their HTML only because the browser could not show them:
        # their comfort pillar is missing, which the score alone does not say.
        "render_failures": dict(Counter(
            _render_cause(getattr(p.typography, "error", "") or "")
            for p in ok if not p.rendered and p.typography is not None)),
    }
    rep.top_findings = aggregate_findings(ok)

    # A dead internal link costs a reader more than any typography metric, and it was
    # only ever visible in `errors`. It belongs at the top of the list.
    fails = rep.summary.get("fetch_failures", {})
    for cause in fails.get("by_cause", []):
        # Only "not found" is a broken link. A 403 or 429 is the server refusing this
        # client, which says nothing about the reader's experience.
        if not cause["cause"].startswith(("HTTP 404", "HTTP 410")):
            continue
        rep.top_findings.insert(0, {
            "key": "broken_internal_links",
            "title": f"{cause['count']} pages linked from this site do not exist",
            "severity": "high" if cause["count"] > 5 else "medium",
            "pillar": "structure",
            "fix": "Remove or repair the links, and drop the dead URLs from the sitemap. "
                   "A reader who follows one of these gets nothing.",
            "affected_pages": cause["count"],
            "share": round(cause["count"] / max(1, len(rep.pages)), 3),
            "example": {"url": cause.get("example", ""),
                        "detail": f"{cause['count']} URLs answered {cause['cause']}.",
                        "evidence": []},
            "pages": [e.split(": ")[0] for e in rep.errors if cause["cause"] in e][:25],
        })
        break

    # Cached text measured against a freshly rendered page is the one failure mode that
    # looks like success: the comfort numbers move, the language numbers do not.
    # A revalidated entry is not stale: the server confirmed the bytes.
    stale = [p for p in ok if getattr(p, "from_cache", False)
             and not getattr(p, "revalidated", False)]
    if stale and rep.options.get("render"):
        rep.summary["stale_text_warning"] = {
            "pages_served_from_cache": len(stale),
            "note": "These pages' text came from the disk cache while their typography was "
                    "measured on the live page. Re-run with --no-cache if the content has "
                    "changed since the cache was written.",
            "urls": [p.final_url for p in stale][:20],
        }
    rep.duration_s = round(time.time() - t0, 1)
    return rep
