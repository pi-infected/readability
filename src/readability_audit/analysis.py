"""Per-page orchestration: fetch -> extract -> measure -> score."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .extract import Doc, EmptyDocument, parse, reference_text
from .fetch import Fetcher, Page
from .lang import LangPack, clarity_supported, detect, pack
from .metrics import a11y, formulas, lexical, structure, suggest, syntax
from .text import sentences


# Statuses that mean "not for this client" rather than "this page is broken".
REFUSED = {401: "login required", 402: "paywall: refused to automated clients",
           403: "refused: bot protection or access rules", 429: "rate limited: raise --delay"}


@dataclass
class PageAnalysis:
    url: str
    final_url: str = ""
    status: int = 0
    error: str | None = None
    title: str = ""
    lang_declared: str | None = None          # what the served HTML declares
    lang_declared_rendered: str | None = None  # what it declares after scripts run
    lang_used: str = "en"
    lang_rules: str = "en"                     # the rule set applied (falls back to en)
    clarity_supported: bool = True
    clarity_note: str = ""
    counts: dict = field(default_factory=dict)
    formulas: dict = field(default_factory=dict)
    syntax: object = None
    lexical: object = None
    structure: object = None
    typography: object = None
    a11y: object = None
    scores: object = None
    findings: list = field(default_factory=list)
    hardest_paragraphs: list = field(default_factory=list)
    hints: list = field(default_factory=list)
    screenshots: dict = field(default_factory=dict)
    fetch_ms: float = 0.0
    rendered: bool = False
    from_cache: bool = False
    revalidated: bool = False
    fetched_at: float = 0.0
    extraction: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


def _prose_sentences(doc: Doc, lp: LangPack) -> tuple[list[str], list[str]]:
    """(sentences from paragraphs/quotes, sentences from every prose block)."""
    from .extract import PARAGRAPH_KINDS, PROSE_KINDS
    para, allb = [], []
    for b in doc.blocks:
        if b.kind not in PROSE_KINDS:
            continue
        ss = sentences(b.text, lp)
        allb += ss
        if b.kind in PARAGRAPH_KINDS:
            para += ss
    return para, allb


def hardest_paragraphs(doc: Doc, lp: LangPack, limit: int = 5) -> list[dict]:
    out = []
    for b in doc.paragraphs:
        if b.words < 25:
            continue
        ss = sentences(b.text, lp)
        c = formulas.count(ss, lp)
        f = formulas.compute(c, lp)
        fre = f.get("flesch_reading_ease")
        lix = f.get("lix")
        out.append({
            "text": b.text[:300], "words": b.words,
            "flesch": fre.value if fre else None,
            "lix": lix.value if lix else None,
            "avg_sentence_length": round(c.asl, 1),
        })
    out.sort(key=lambda d: (d["lix"] if d["lix"] is not None else 0), reverse=True)
    return out[:limit]


def analyse_page(page: Page, *, render_result=None, lang_override: str | None = None,
                 audience: str = "general", config: dict | None = None) -> PageAnalysis:
    from . import scoring
    from .metrics import typography as typo

    pa = PageAnalysis(url=page.url, final_url=page.final_url, status=page.status,
                      fetch_ms=round(page.elapsed_ms, 1))
    if not page.ok:
        if page.error:
            pa.error = page.error
        elif not (page.html or "").strip():
            pa.error = f"empty response body (HTTP {page.status})"
        elif page.status in REFUSED:
            pa.error = f"HTTP {page.status} ({REFUSED[page.status]})"
        else:
            pa.error = f"HTTP {page.status}"
        return pa

    # The served HTML and the rendered DOM are different documents. Prefer the served
    # one when it actually carries the content — it is the cleaner document — and fall
    # back to the rendered DOM only when the page builds its text in the browser.
    rendered_html = getattr(render_result, "html", None) if render_result is not None else None
    # The browser knows which elements float over the content; the markup alone does not.
    overlay_hints = None
    if render_result is not None:
        vps = getattr(render_result, "viewports", {}) or {}
        probe0 = vps.get("desktop") or next(iter(vps.values()), None)
        if probe0:
            overlay_hints = probe0.get("overlays") or None
    try:
        served_doc = parse(page.html, page.final_url, reference_text=reference_text(page.html),
                           overlay_hints=overlay_hints)
    except EmptyDocument as exc:
        pa.error = str(exc)
        return pa
    except Exception as exc:
        pa.error = f"could not parse the document: {type(exc).__name__}: {exc}"
        return pa
    rendered_doc = None
    if rendered_html:
        try:
            rendered_doc = parse(rendered_html, page.final_url,
                                 reference_text=reference_text(rendered_html),
                                 overlay_hints=overlay_hints)
        except Exception:
            rendered_doc = None

    probe_text = served_doc.prose_text or (rendered_doc.prose_text if rendered_doc else "")
    declared = served_doc.lang.split("-")[0].lower() if served_doc.lang else None
    detected = detect(probe_text or served_doc.text, declared)
    # A wrong lang attribute is common; measuring French prose with English rules is
    # worse than ignoring the attribute, so confident detection wins.
    if lang_override:
        code = lang_override
    elif detected[1] >= 0.5 and detected[0] != declared:
        code = detected[0]
    else:
        code = declared or detected[0] or "en"
    lp = pack(code)
    clarity_ok, clarity_note = clarity_supported(code, probe_text or served_doc.text)

    # Strip machine output (JSON demos, build logs). The stopword half of that test only
    # holds where the profile matches the text: Arabic prose has no English stopwords and
    # the rule would delete the page.
    served_doc.drop_machine_blocks(lp.stopwords, stopwords_apply=clarity_ok)
    if rendered_doc is not None:
        rendered_doc.drop_machine_blocks(lp.stopwords, stopwords_apply=clarity_ok)

    doc = served_doc
    source = "served HTML"
    if rendered_doc is not None:
        served_prose = len(served_doc.prose_text)
        rendered_prose = len(rendered_doc.prose_text)
        if served_prose < 400 or served_prose < 0.6 * rendered_prose:
            doc, source = rendered_doc, "rendered DOM"

    # A crawler, a reader mode and anyone whose script did not run see the served value,
    # so that is the declaration. When hydration changes it, say both.
    pa.lang_declared = served_doc.lang
    if rendered_doc is not None and rendered_doc.lang != served_doc.lang:
        pa.lang_declared_rendered = rendered_doc.lang
    # The page's language, even where no rule set exists for it (Arabic, Japanese): those
    # pages are measured with neutral rules, which is not the same as being English.
    pa.lang_used = (code or lp.code).split("-")[0].lower()
    pa.lang_rules = lp.code
    pa.title = doc.title or served_doc.title
    pa.clarity_supported = clarity_ok
    pa.clarity_note = clarity_note
    pa.extraction = {"selector": doc.main_selector, "coverage": doc.extraction_coverage,
                     "note": doc.extraction_note, "source": source,
                     "machine_blocks_dropped": doc.machine_blocks,
                     "inline_paragraph_containers": doc.inline_paragraph_containers}
    if rendered_doc is not None:
        pa.extraction["served_prose_chars"] = len(served_doc.prose_text)
        pa.extraction["rendered_prose_chars"] = len(rendered_doc.prose_text)
        # The question a no-script reader cares about is not "is there more text after
        # JavaScript" — a decorative animation adds plenty. It is whether the article's
        # own opening paragraphs are in the served HTML at all.
        opening = [b.text for b in doc.paragraphs if len(b.text) >= 80][:3]
        served_haystack = re.sub(r"\s+", " ", served_doc.full_text).lower()
        hits = sum(1 for t in opening
                   if re.sub(r"\s+", " ", t[:60]).lower() in served_haystack)
        pa.extraction["opening_paragraphs_checked"] = len(opening)
        pa.extraction["opening_paragraphs_served"] = hits
        pa.extraction["content_needs_js"] = bool(opening) and hits == 0

    para_sents, all_sents = _prose_sentences(doc, lp)
    base = para_sents if len(para_sents) >= 5 else all_sents
    c = formulas.count(base, lp)
    pa.counts = c.as_dict()
    pa.counts["blocks"] = len(doc.blocks)
    pa.counts["sentences_all_blocks"] = len(all_sents)
    pa.formulas = formulas.compute(c, lp, doc.prose_text)
    pa.syntax = syntax.analyse(base, lp)
    pa.lexical = lexical.analyse(doc.prose_text, lp)
    pa.structure = structure.analyse(doc, lp)
    pa.hardest_paragraphs = hardest_paragraphs(doc, lp)
    if len(base) >= 4:
        from .metrics.syntax import LONG_SENT
        pa.hints = suggest.hints(base, lp, pa.syntax, pa.lexical,
                                 long_cut=LONG_SENT.get(lp.code, 25))

    probe = None
    if render_result is not None and getattr(render_result, "ok", False):
        pa.typography = typo.analyse(render_result)
        pa.rendered = True
        pa.screenshots = dict(getattr(render_result, "screenshots", {}) or {})
        probe = (render_result.viewports.get("desktop")
                 or next(iter(render_result.viewports.values()), None))
    elif render_result is not None:
        pa.typography = typo.analyse(render_result)

    pa.a11y = a11y.analyse(doc, lp, pa.structure, detected, probe,
                           declared=pa.lang_declared)
    pa.scores, pa.findings = scoring.score_page(pa, audience=audience, config=config)
    return pa


def analyse_url(url: str, fetcher: Fetcher, *, render: bool = False,
                screenshot_dir: Path | None = None, renderer=None, **kw) -> PageAnalysis:
    """`renderer` (an open render.Renderer) is reused across calls when given."""
    page = fetcher.get(url)
    rr = None
    if render and page.ok:
        if renderer is not None:
            rr = renderer.render(page.final_url)
        else:
            from .render import render as do_render
            rr = do_render(page.final_url, screenshot_dir=screenshot_dir)
    return analyse_page(page, render_result=rr, **kw)
