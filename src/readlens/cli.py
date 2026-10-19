"""readlens — audit the readability and reading comfort of a website."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import site as site_mod


def load_config(path: str | None) -> dict | None:
    """Project overrides for target bands, metric weights and pillar weights."""
    if not path:
        return None
    f = Path(path)
    text = f.read_text(encoding="utf8")
    if f.suffix.lower() == ".toml":
        try:
            import tomllib
        except ModuleNotFoundError:          # Python 3.10
            import tomli as tomllib
        return tomllib.loads(text)
    return json.loads(text)


def _regex(parts: list[str] | None) -> str | None:
    """Several --include/--exclude patterns mean "any of them"."""
    parts = [x for x in (parts or []) if x]
    return "|".join(f"(?:{x})" for x in parts) if parts else None


def setup(a) -> tuple[dict, object]:
    """Config file + --only/--skip -> (config carrying the selection, selection)."""
    from .select import Selection, SelectionError
    cfg = load_config(getattr(a, "config", None)) or {}
    try:
        sel = Selection.parse(list(cfg.get("only") or []) + list(a.only or []),
                              list(cfg.get("skip") or []) + list(a.skip or []))
    except SelectionError as e:
        sys.stderr.write(f"readlens: {e}\n")
        raise SystemExit(64)
    return {**cfg, "_selection": sel}, sel


def _wants_json(a) -> bool:
    return getattr(a, "format", "text") == "json"


def _dump(obj) -> None:
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def write_csv(data: dict, path: str | Path) -> Path:
    import csv
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cols = ["url", "type", "score", "grade", "clarity", "structure", "comfort", "access",
            "words", "lix", "font_px", "line_height", "chars_per_line", "contrast_ratio",
            "apca_lc", "occlusion", "findings", "critical"]
    with p.open("w", newline="", encoding="utf8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for pg in data.get("pages", []):
            if pg.get("error"):
                continue
            typo = ((pg.get("typography") or {}).get("viewports") or {}).get("desktop") or {}
            pil = pg.get("pillars") or {}
            lix = next((m["value"] for m in pg.get("metrics", []) if m["key"] == "lix"), None)
            f = pg.get("findings") or []
            w.writerow([
                pg.get("final_url"), pg.get("page_type"), pg.get("score"), pg.get("grade"),
                pil.get("clarity", {}).get("score"), pil.get("structure", {}).get("score"),
                pil.get("comfort", {}).get("score"), pil.get("access", {}).get("score"),
                (pg.get("structure") or {}).get("word_count"), lix,
                typo.get("body_font_px"), typo.get("line_height_ratio"),
                typo.get("chars_per_line"), typo.get("median_contrast_ratio"),
                typo.get("median_apca_lc"), typo.get("occlusion"),
                len(f), sum(1 for x in f if x["severity"] == "critical"),
            ])
    return p

C = {"reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m", "red": "\033[31m",
     "yellow": "\033[33m", "green": "\033[32m", "orange": "\033[38;5;208m", "cyan": "\033[36m"}
SEV_COLOR = {"critical": "red", "high": "orange", "medium": "yellow", "low": "dim", "info": "dim"}


def _c(s: str, col: str, use: bool) -> str:
    return f"{C[col]}{s}{C['reset']}" if use and col in C else str(s)


def _grade_col(g: str) -> str:
    return {"A": "green", "B": "green", "C": "yellow", "D": "orange", "E": "red", "F": "red"}.get(g, "dim")


def _bar(score: float, width: int = 22) -> str:
    n = int(round(score / 100 * width))
    return "█" * n + "·" * (width - n)


def print_report(rep, color: bool = True, top: int = 10) -> None:
    s = rep.summary
    w = sys.stdout.write
    w("\n" + _c(f"{rep.base_url}", "bold", color) + "\n")
    note = rep.options.get("concurrency_note")
    w(_c(f"{s['pages_analysed']} pages · {s['total_words']} words · {rep.duration_s}s"
         f" · {s['rendered']} rendered"
         + (f" · concurrency {rep.options.get('concurrency')} ({note})" if note else "") + "\n",
         "dim", color))
    w(f"\n  {_c(str(s['score']), 'bold', color)}/100  "
      f"{_c(s['grade'], _grade_col(s['grade']), color)}   {_bar(s['score'])}\n")
    w(_c(f"  mean {s['mean_page_score']} · worst {s['worst_page_score']} ·"
         f" best {s['best_page_score']} · consistency {s['consistency_score']}\n", "dim", color))
    w("\n")
    for k, v in s["pillars"].items():
        w(f"  {k:<14}{v:>5.1f}  {_bar(v)}\n")

    if rep.top_findings:
        w("\n" + _c("what to fix first", "bold", color) + "\n")
        for f in rep.top_findings[:top]:
            tag = _c(f"{f['severity']:<8}", SEV_COLOR.get(f["severity"], "dim"), color)
            w(f"  {tag} {f['title'][:52]:<52} {f['affected_pages']}/{s['pages_analysed']} pages\n")

    w("\n" + _c("pages", "bold", color) + "\n")
    rows = sorted([p for p in rep.pages if p.ok and p.scores],
                  key=lambda p: (p.scores.overall is None, p.scores.overall or 0))
    for p in rows:
        from urllib.parse import urlparse
        path = urlparse(p.final_url).path or "/"
        g = _c(p.scores.grade, _grade_col(p.scores.grade), color)
        shown = f"{p.scores.overall:>5.1f}" if p.scores.overall is not None else "    —"
        w(f"  {shown} {g}  {p.scores.page_type:<8} {path[:48]:<48}"
          f" {_c(str(len(p.findings)) + ' findings', 'dim', color)}\n")
    for e in rep.errors[:5]:
        w(_c(f"  ! {e}\n", "red", color))
    w("\n")


def cmd_audit(a) -> int:
    out_dir = Path(a.out) if a.out else None
    shots = (out_dir / "screenshots") if (out_dir and a.screenshots) else None
    quiet = a.quiet

    def progress(i, n, url, phase="fetch"):
        if not quiet:
            sys.stderr.write(f"\r  {phase} [{i}/{n}] {url[:62]:<64}")
            sys.stderr.flush()

    config, sel = setup(a)
    quiet = quiet or _wants_json(a)
    rep = site_mod.audit(
        a.url, max_pages=a.pages, render=not a.no_render, audience=a.audience,
        include=_regex(a.include), exclude=_regex(a.exclude), delay=a.delay,
        cache_dir=None if a.no_cache else a.cache, screenshot_dir=shots,
        lang=a.lang, urls=a.url_list or None, respect_robots=not a.ignore_robots,
        use_sitemap=not a.no_sitemap, progress=None if quiet else progress,
        config=config, concurrency=a.concurrency, selection=sel, max_depth=a.depth,
    )
    if not quiet:
        sys.stderr.write("\r" + " " * 84 + "\r")

    from .report.html_report import build_html
    from .report.serialize import site_to_dict
    langs = a.report_lang if isinstance(a.report_lang, list) else [a.report_lang]
    detail = len(rep.pages) if a.detail == 0 else a.detail
    rep.options["report_langs"] = langs
    rep.options["detail_sections"] = detail

    def suffix(lang: str) -> str:
        """Only the extra languages get a suffix, so the primary keeps its plain name."""
        return "" if lang == langs[0] else f"-{lang}"

    # Plan the artifacts first so the JSON can list every file the run produced,
    # including itself, and a consumer never has to guess what else exists.
    planned = []
    json_path = (Path(a.json) if a.json else (out_dir / "readlens.json" if out_dir else None))
    if json_path:
        planned.append({"role": "data", "format": "json", "path": str(json_path)})
    csv_path = (Path(a.csv) if a.csv else (out_dir / "readlens.csv" if out_dir else None))
    if csv_path:
        planned.append({"role": "table", "format": "csv", "path": str(csv_path)})
    for lang in langs:
        for fmt, flag in (("html", a.html), ("pdf", a.pdf)):
            if not (flag or out_dir):
                continue
            base = Path(flag) if (flag and lang == langs[0]) else (
                Path(flag).with_suffix(f"{suffix(lang)}.{fmt}") if flag
                else out_dir / f"readlens{suffix(lang)}.{fmt}")
            planned.append({"role": "report", "format": fmt, "language": lang,
                            "path": str(base)})
    if shots:
        planned.append({"role": "screenshots", "format": "png", "path": str(shots)})

    data = site_to_dict(rep, include_evidence=not a.compact, artifacts=planned)

    written = []
    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf8")
        written.append(json_path)
    if csv_path:
        written.append(write_csv(data, csv_path))

    # Every report is rendered from the one `data` above, so the languages can never
    # describe different crawls.
    for lang in langs:
        html = None
        if a.html or a.pdf or out_dir:
            html = build_html(rep, lang=lang, detail=detail, screenshots=bool(shots),
                              data=json.loads(json.dumps(data)))
        if a.html or out_dir:
            p = (Path(a.html) if (a.html and lang == langs[0])
                 else (Path(a.html).with_suffix(f"{suffix(lang)}.html") if a.html
                       else out_dir / f"readlens{suffix(lang)}.html"))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(html, encoding="utf8")
            written.append(p)
        if a.pdf or out_dir:
            from .report.pdf import write_pdf
            p = (Path(a.pdf) if (a.pdf and lang == langs[0])
                 else (Path(a.pdf).with_suffix(f"{suffix(lang)}.pdf") if a.pdf
                       else out_dir / f"readlens{suffix(lang)}.pdf"))
            try:
                write_pdf(html, p, base_url=a.url)
                written.append(p)
            except Exception as e:
                sys.stderr.write(f"pdf failed ({lang}): {type(e).__name__}: {e}\n")

    if _wants_json(a):
        _dump(data)
    elif not quiet:
        print_report(rep, color=sys.stdout.isatty() and not a.no_color, top=a.top)
        for p in written:
            print(f"  wrote {p}")
        print()
    if a.fail_under and rep.summary["score"] < a.fail_under:
        return 2
    return 0


def _print_page(pa, a, color: bool) -> None:
    print(f"\n{_c(pa.title or pa.final_url, 'bold', color)}\n{_c(pa.final_url, 'dim', color)}")
    shown = pa.scores.overall if pa.scores.overall is not None else "—"
    print(f"\n  {_c(str(shown), 'bold', color)}/100 "
          f"{_c(pa.scores.grade, _grade_col(pa.scores.grade), color)}  "
          f"{pa.scores.page_type} · {pa.lang_used} · {pa.structure.word_count} words · "
          f"{pa.structure.reading_time_min} min"
          + ("" if pa.rendered else " · not rendered") + "\n")
    for k, v in pa.scores.pillars.items():
        print(f"  {k:<14}{v['score']:>5.1f}  {_bar(v['score'])}")
    print(f"\n{_c('metrics', 'bold', color)}")
    for m in sorted(pa.scores.metrics, key=lambda m: m.score):
        col = SEV_COLOR.get(m.severity, "green")
        label = _c(f"{m.label[:34]:<34}", col, color)
        target = _c(f"target {m.target_display}", "dim", color)
        print(f"  {m.score:>5.1f} {label} {m.display:>16}  {target}")
    print(f"\n{_c('findings', 'bold', color)}")
    for x in pa.findings[:a.top]:
        print(f"  {_c(f'{x.severity:<8}', SEV_COLOR.get(x.severity, 'dim'), color)} {x.title}")
        print(f"           {_c(x.detail[:150], 'dim', color)}")
        if x.fix:
            print(f"           → {x.fix[:150]}")
        for ev in (x.evidence or [])[:a.evidence]:
            print(f"           {_c('· ' + _evidence(ev), 'dim', color)}")


def _evidence(ev) -> str:
    if not isinstance(ev, dict):
        return str(ev)[:120]
    first = ("color", "background", "ratio", "apca_abs", "apca_required", "font_px")
    keys = [k for k in first if k in ev] + [k for k in ev if k not in first]
    facts = [f"{k} {ev[k]}" for k in keys
             if k not in ("text", "apca_note", "apca_lc", "chars")
             and isinstance(ev[k], (int, float, str)) and len(str(ev[k])) < 24][:6]
    text = f"\"{ev['text'][:60]}…\"\n             " if ev.get("text") else ""
    return text + " · ".join(facts)


def cmd_page(a) -> int:
    from .analysis import analyse_url
    from .fetch import Cache, Fetcher
    from .report.serialize import page_to_dict
    config, sel = setup(a)
    render = not a.no_render and sel.needs_render
    f = Fetcher(cache=Cache(None if a.no_cache else Path(a.cache)))
    renderer = None
    if render:
        from .render import DEFAULT_VIEWPORTS, Renderer
        renderer = Renderer(sel.viewports(DEFAULT_VIEWPORTS), check_dark=sel.check_dark,
                            concurrency=1).__enter__()
        if renderer.error:
            sys.stderr.write(f"readlens: {renderer.error} (continuing without the browser)\n")
    color = sys.stdout.isatty() and not a.no_color
    results, code = [], 0
    try:
        for url in a.url:
            pa = analyse_url(url, f, render=render, renderer=renderer, lang_override=a.lang,
                             audience=a.audience, config=config)
            if not pa.ok:
                print(f"error: {url}: {pa.error}", file=sys.stderr)
                code = 1
                continue
            results.append(page_to_dict(pa))
            if a.fail_under and (pa.scores.overall or 0) < a.fail_under:
                code = max(code, 2)
            if not _wants_json(a):
                _print_page(pa, a, color)
    finally:
        f.close()
        if renderer is not None:
            renderer.__exit__()
    out = results[0] if len(a.url) == 1 and results else results
    if _wants_json(a):
        _dump(out)
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf8")
        if not _wants_json(a):
            print(f"\n  wrote {a.json}")
    if not _wants_json(a):
        print()
    return code


def cmd_urls(a) -> int:
    from .fetch import Cache, Fetcher, same_site
    f = Fetcher(cache=Cache(None if a.no_cache else Path(a.cache)), delay=a.delay,
                respect_robots=not a.ignore_robots)
    try:
        urls = f.discover(a.url, max_pages=a.pages, include=_regex(a.include),
                          exclude=_regex(a.exclude), use_sitemap=not a.no_sitemap,
                          max_depth=a.depth)
    finally:
        f.close()
    urls = [u for u in urls if same_site(a.url, u)]
    if _wants_json(a):
        _dump(urls)
    else:
        print("\n".join(urls))
    return 0


def cmd_metrics(a) -> int:
    from .select import GROUP_HELP, GROUPS, METRICS, PILLARS
    need = {"": "html", "desktop": "browser", "mobile": "browser, 390px"}
    if _wants_json(a):
        _dump({"pillars": list(PILLARS), "groups": GROUPS,
               "metrics": [{"key": k, "pillar": p, "label": l, "needs": need[n]}
                           for k, (p, l, n) in METRICS.items()]})
        return 0
    print("\npillars   " + "  ".join(PILLARS))
    print("\ngroups")
    for g, keys in GROUPS.items():
        print(f"  {g:<12} {GROUP_HELP[g]}\n  {'':<12} {', '.join(keys)}")
    print("\nmetrics")
    for k, (p, label, n) in METRICS.items():
        print(f"  {k:<18} {p:<10} {label:<42} {need[n]}")
    print("\nhtml-only selections skip the browser: e.g. --only clarity,structure\n")
    return 0


def cmd_text(a) -> int:
    from .analysis import analyse_page
    from .fetch import Page
    raw = sys.stdin.read() if a.path == "-" else Path(a.path).read_text(encoding="utf8")
    if "<html" not in raw[:2000].lower() and "<body" not in raw[:2000].lower():
        body = "".join(f"<p>{line}</p>" for line in raw.split("\n\n") if line.strip())
        raw = f"<html><body><main>{body}</main></body></html>"
    config, _ = setup(a)
    pa = analyse_page(Page("file://" + str(a.path), "file://" + str(a.path), 200, raw),
                      lang_override=a.lang, audience=a.audience, config=config)
    out = {"counts": pa.counts,
           "formulas": {k: {"name": f.name, "value": f.value, "band": f.band}
                        for k, f in pa.formulas.items()},
           "syntax": pa.syntax.as_dict(), "lexical": pa.lexical.as_dict(),
           "score": pa.scores.overall, "grade": pa.scores.grade,
           "metrics": [m.as_dict() for m in pa.scores.metrics],
           "findings": [f.as_dict() for f in pa.findings]}
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_diff(a) -> int:
    from urllib.parse import urlparse

    from .compare import diff, load
    d = diff(load(a.before), load(a.after))
    if _wants_json(a):
        _dump(d)
        return 0
    color = sys.stdout.isatty() and not a.no_color
    delta = d["delta"]
    arrow = "up" if delta > 0 else ("down" if delta < 0 else "flat")
    col = "green" if delta > 0 else ("red" if delta < 0 else "dim")
    print(f"\n{_c(d['base_url'] or '', 'bold', color)}")
    move = _c(f"{delta:+.1f} {arrow}", col, color)
    print(f"  {d['before']['score']} -> {d['after']['score']}  {move}"
          f"   {d['before']['grade']} -> {d['after']['grade']}")
    if d["pillar_delta"]:
        print("  " + " · ".join(f"{k} {v:+.1f}" for k, v in d["pillar_delta"].items()))
    if d["resolved"]:
        print("\n" + _c("resolved", "green", color))
        for r in d["resolved"][:12]:
            print(f"  + {r['title']} (was on {r['was']} pages)")
    if d["introduced"]:
        print("\n" + _c("new", "red", color))
        for r in d["introduced"][:12]:
            print(f"  - [{r['severity']}] {r['title']} ({r['pages']} pages)")
    moved = [r for r in d["pages"] if abs(r["delta"]) >= 0.5]
    if moved:
        print("\n" + _c("pages that moved", "bold", color))
        for r in moved[:20]:
            shift = _c(f"{r['delta']:+6.1f}", "green" if r["delta"] > 0 else "red", color)
            path = urlparse(r["url"]).path or "/"
            print(f"  {shift}  {r['before']} -> {r['after']}  {path}")
    if a.json:
        Path(a.json).write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf8")
        print(f"\n  wrote {a.json}")
    print()
    return 0


def cmd_benchmark(a) -> int:
    from .compare import rank
    from .report.serialize import site_to_dict
    config, sel = setup(a)
    reports = []
    for url in a.urls:
        if not (a.quiet or _wants_json(a)):
            sys.stderr.write(f"  auditing {url}\n")
        rep = site_mod.audit(url, max_pages=a.pages, render=not a.no_render,
                             audience=a.audience, cache_dir=None if a.no_cache else a.cache,
                             lang=a.lang, delay=a.delay, config=config, selection=sel,
                             concurrency=a.concurrency)
        reports.append(site_to_dict(rep, include_evidence=False))
    r = rank(reports)
    if _wants_json(a):
        _dump({"ranking": r, "reports": reports})
        return 0
    color = sys.stdout.isatty() and not a.no_color
    print(f"\n  {'#':<3}{'site':<40}{'score':>7}{'grade':>7}{'worst':>7}{'crit':>6}  pillars")
    for row in r["sites"]:
        pil = " ".join(f"{k[:4]} {v:.0f}" for k, v in (row["pillars"] or {}).items())
        g = _c(f"{row['grade']:>7}", _grade_col(row["grade"]), color)
        print(f"  {row['rank']:<3}{(row['site'] or '')[:38]:<40}{row['score']:>7}{g}"
              f"{row['worst_page']:>7}{row['critical']:>6}  {pil}")
    if a.json:
        Path(a.json).write_text(json.dumps({"ranking": r, "reports": reports}, indent=2,
                                           ensure_ascii=False), encoding="utf8")
        print(f"\n  wrote {a.json}")
    print()
    return 0


EPILOG = """examples:
  readlens page https://example.com/post                    one page, everything
  readlens page URL --only contrast                         WCAG + APCA contrast only
  readlens page URL --only clarity,structure                text only: no browser, ~1s
  readlens audit https://example.com --pages 30 --exclude '/tag/' --out report/
  readlens audit https://example.com --only typography --skip mobile --format json
  readlens urls https://example.com --pages 200 --include '/blog/'
  readlens text draft.md --only readability
  readlens metrics                                          every selector you can pass
"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="readlens", description=__doc__, epilog=EPILOG,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"readlens {site_mod.__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="command")

    def fmt(sp):
        sp.add_argument("--format", choices=["text", "json"], default="text",
                        help="json: machine-readable result on stdout, progress on stderr")

    def select(sp):
        sp.add_argument("--only", action="append", metavar="SEL",
                        help="measure only these pillars, groups or metrics (comma list, "
                             "repeatable). See `readlens metrics`")
        sp.add_argument("--skip", action="append", metavar="SEL",
                        help="leave these pillars, groups or metrics out")

    def common(sp):
        select(sp)
        fmt(sp)
        sp.add_argument("--audience", default="general",
                        choices=["general", "technical", "academic", "children"],
                        help="shifts the clarity targets (default: general)")
        sp.add_argument("--lang", help="force the language used for linguistic metrics (en, fr, ...)")
        sp.add_argument("--no-render", action="store_true",
                        help="skip the browser pass (no comfort metrics)")
        sp.add_argument("--no-cache", action="store_true", help="always refetch")
        sp.add_argument("--cache", default=".readlens-cache", help="HTTP cache directory")
        sp.add_argument("--no-color", action="store_true")
        sp.add_argument("--top", type=int, default=10, help="findings shown in the terminal")
        sp.add_argument("--config", help="JSON or TOML file overriding bands, weights, only/skip")

    def scope(sp, pages: int):
        sp.add_argument("--pages", type=int, default=pages, help=f"page budget (default {pages})")
        sp.add_argument("--include", action="append", metavar="REGEX",
                        help="a URL must match one of these (repeatable)")
        sp.add_argument("--exclude", action="append", metavar="REGEX",
                        help="a URL matching any of these is dropped (repeatable)")
        sp.add_argument("--depth", type=int, default=2, help="link-crawl depth (default 2)")
        sp.add_argument("--no-sitemap", action="store_true", help="crawl links only")
        sp.add_argument("--ignore-robots", action="store_true")
        sp.add_argument("--delay", type=float, default=0.4, help="seconds between requests")

    a1 = sub.add_parser("audit", help="crawl a site and produce a report",
                        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EPILOG)
    a1.add_argument("url")
    scope(a1, 10)
    a1.add_argument("--url-list", nargs="*", metavar="URL",
                    help="analyse exactly these URLs instead of crawling")
    a1.add_argument("--json", help="write the JSON result here")
    a1.add_argument("--html", help="write the HTML report here")
    a1.add_argument("--pdf", help="write the PDF report here")
    a1.add_argument("--csv", help="write one row per page here")
    a1.add_argument("--concurrency", type=int, default=4,
                    help="pages rendered at once; clamped to what free RAM allows")
    a1.add_argument("--out", help="directory to write readlens.{json,csv,html,pdf} into")
    a1.add_argument("--report-lang", nargs="+", default=["en"], choices=["en", "fr"],
                    help="one or more report languages, all built from the same crawl")
    a1.add_argument("--detail", type=int, default=0,
                    help="per-page detail sections; 0 (the default) means every page")
    a1.add_argument("--screenshots", action="store_true", help="embed a screenshot per page")
    a1.add_argument("--compact", action="store_true", help="drop evidence from the JSON")
    a1.add_argument("--fail-under", type=float, help="exit 2 if the site score is below this")
    a1.add_argument("--quiet", action="store_true")
    common(a1)
    a1.set_defaults(func=cmd_audit)

    a2 = sub.add_parser("page", help="analyse one or more pages, no crawl")
    a2.add_argument("url", nargs="+")
    a2.add_argument("--json", help="write the JSON result here")
    a2.add_argument("--fail-under", type=float, help="exit 2 if a page scores below this")
    a2.add_argument("--evidence", type=int, default=2, metavar="N",
                    help="evidence lines shown per finding (default 2)")
    common(a2)
    a2.set_defaults(func=cmd_page)

    a3 = sub.add_parser("text", help="analyse a local text, Markdown or HTML file (- for stdin)")
    a3.add_argument("path")
    common(a3)
    a3.set_defaults(func=cmd_text)

    a6 = sub.add_parser("urls", help="list the pages an audit would visit, without analysing")
    a6.add_argument("url")
    scope(a6, 50)
    a6.add_argument("--no-cache", action="store_true")
    a6.add_argument("--cache", default=".readlens-cache")
    fmt(a6)
    a6.set_defaults(func=cmd_urls)

    a7 = sub.add_parser("metrics", help="list pillars, groups and metrics for --only/--skip")
    fmt(a7)
    a7.set_defaults(func=cmd_metrics)

    a4 = sub.add_parser("diff", help="compare two audit JSON files")
    a4.add_argument("before")
    a4.add_argument("after")
    a4.add_argument("--json", help="write the diff here")
    a4.add_argument("--no-color", action="store_true")
    fmt(a4)
    a4.set_defaults(func=cmd_diff)

    a5 = sub.add_parser("benchmark", help="audit several sites and rank them")
    a5.add_argument("urls", nargs="+")
    a5.add_argument("--pages", type=int, default=6)
    a5.add_argument("--delay", type=float, default=0.4)
    a5.add_argument("--concurrency", type=int, default=4)
    a5.add_argument("--json", help="write ranking and reports here")
    a5.add_argument("--quiet", action="store_true")
    common(a5)
    a5.set_defaults(func=cmd_benchmark)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
