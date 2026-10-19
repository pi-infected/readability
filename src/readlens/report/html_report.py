"""Render the audit as a self-contained HTML page (also the source for the PDF)."""
from __future__ import annotations

import base64
from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .i18n import strings
from .serialize import site_to_dict


def localise(data: dict, lang: str) -> dict:
    """Swap metric and finding copy into the report language. English is the source."""
    if (lang or "en").startswith("en"):
        return data
    if not lang.startswith("fr"):
        return data
    from .copy_fr import BANDS, DETAIL, FINDINGS, METRICS, NOTES, PAGE_TYPES, UNITS

    def tr_unit(s: str | None) -> str | None:
        if not s:
            return s
        for en, fr in sorted(UNITS.items(), key=lambda kv: -len(kv[0])):
            if s.endswith(" " + en):
                return s[: -len(en)] + fr
        return s

    def fix_metric(m: dict) -> None:
        d = m.get("display") or ""
        for en, fr in BANDS.items():
            if f"({en})" in d:
                m["display"] = d.replace(f"({en})", f"({fr})")
                break
        tr = METRICS.get(m.get("key"))
        if not tr:
            return
        label, advice, why = tr
        m["label"], m["advice"] = label, advice
        m["target_display"] = tr_unit(m.get("target_display"))
        m["display"] = tr_unit(m.get("display"))
        if why:
            m["why"] = why

    def fix_finding(f: dict) -> None:
        key = f.get("key")
        params = f.get("params") or {}
        if key in FINDINGS:
            title, fixtext = FINDINGS[key]
            f["title"] = title
            try:
                f["fix"] = fixtext.format(**params)
            except Exception:
                f["fix"] = fixtext
            if key in DETAIL and params:
                try:
                    f["detail"] = DETAIL[key].format(**params)
                except Exception:
                    pass
        elif key in METRICS:
            label, advice, why = METRICS[key]
            f["title"], f["fix"] = label, advice
            if params.get("display") is not None:
                p2 = {"display": tr_unit(params["display"]),
                      "target": tr_unit(params.get("target"))}
                f["detail"] = DETAIL["metric"].format(**p2) + (f" {why}" if why else "")

    for p in data.get("pages", []):
        if p.get("page_type") in PAGE_TYPES:
            p["page_type"] = PAGE_TYPES[p["page_type"]]
        for f in (p.get("formulas") or {}).values():
            f["band"] = BANDS.get(f.get("band"), f.get("band"))
            f["note"] = NOTES.get(f.get("note"), f.get("note"))
        for m in p.get("metrics", []):
            fix_metric(m)
        for f in p.get("findings", []):
            fix_finding(f)
    types = data.get("summary", {}).get("page_types") or {}
    if types:
        data["summary"]["page_types"] = {PAGE_TYPES.get(k, k): v for k, v in types.items()}
    for f in data.get("top_findings", []):
        ex = f.get("example") or {}
        proxy = {"key": f.get("key"), "title": f.get("title"), "fix": f.get("fix"),
                 "detail": ex.get("detail"), "params": ex.get("params") or {}}
        fix_finding(proxy)
        f["title"], f["fix"] = proxy["title"], proxy["fix"]
        if ex and proxy.get("detail"):
            ex["detail"] = proxy["detail"]
    return data

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

GRADE_SEV = {"A": "ok", "B": "ok", "C": "medium", "D": "high", "E": "high", "F": "critical"}


def color_for(score: float) -> str:
    if score >= 85:
        return "#1a7f4b"
    if score >= 70:
        return "#4b8f2f"
    if score >= 55:
        return "#b8860b"
    if score >= 40:
        return "#c2701c"
    return "#a51f1f"


def _path(url: str) -> str:
    p = urlparse(url)
    return (p.path or "/") + (("?" + p.query) if p.query else "")


def _embed(path: str | None) -> str | None:
    if not path:
        return None
    f = Path(path)
    if not f.exists() or f.stat().st_size > 3_500_000:
        return None
    return "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode()


def _metric(page: dict, key: str):
    for m in page.get("metrics", []):
        if m["key"] == key:
            return m
    return None


def _row(p: dict) -> dict:
    typo = (p.get("typography") or {}).get("viewports", {}) or {}
    desk = typo.get("desktop") or (next(iter(typo.values()), {}) if typo else {})
    lixm = _metric(p, "lix")
    return {
        "final_url": p.get("final_url") or p.get("url"),
        "path": _path(p.get("final_url") or p.get("url")),
        "title": p.get("title") or "",
        "page_type": p.get("page_type") or "—",
        "score": p.get("score"),
        "grade": p.get("grade") or "—",
        "sevclass": GRADE_SEV.get(p.get("grade") or "", "info"),
        "words": (p.get("structure") or {}).get("word_count", 0),
        "lix": lixm["value"] if lixm else None,
        "font_px": desk.get("body_font_px"),
        "contrast": desk.get("median_contrast_ratio"),
        "cpl": desk.get("chars_per_line"),
        "pillars": p.get("pillars") or {},
        "metrics": p.get("metrics") or [],
        "findings": p.get("findings") or [],
        "formulas": p.get("formulas") or {},
        "hardest_paragraphs": p.get("hardest_paragraphs") or [],
        "hints": p.get("rewrite_hints") or [],
        "lang_used": (p.get("language") or {}).get("used_for_metrics"),
        "lang_declared": (p.get("language") or {}).get("declared"),
        "lang_after_render": (p.get("language") or {}).get("declared_after_render"),
        "screenshot": _embed(((p.get("screenshots") or {}).get("desktop"))),
        "screenshot_mobile": _embed(((p.get("screenshots") or {}).get("mobile"))),
    }


def build_html(report, *, lang: str = "en", detail: int = 6, show_findings: int = 12,
               screenshots: bool = True, data: dict | None = None) -> str:
    data = localise(data or site_to_dict(report), lang)
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
    tpl = env.get_template("report.html.j2")

    ok_pages = [p for p in data["pages"] if not p.get("error")]
    rows = [_row(p) for p in ok_pages]
    rows.sort(key=lambda r: (r["score"] is None, r["score"] or 0))
    if not screenshots:
        for r in rows:
            r["screenshot"] = r["screenshot_mobile"] = None

    methodology, seen = [], set()
    for p in ok_pages:
        for m in p.get("metrics", []):
            if m["key"] not in seen:
                seen.add(m["key"])
                methodology.append(m)
    methodology.sort(key=lambda m: (m["pillar"], m["label"]))

    return tpl.render(
        data=data, t=strings(lang), ui_lang=lang, pages=rows,
        detail_pages=rows[:detail], methodology=methodology,
        color_for=color_for, show_findings=show_findings,
    )


def write_html(report, path: str | Path, **kw) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build_html(report, **kw), encoding="utf8")
    return p
