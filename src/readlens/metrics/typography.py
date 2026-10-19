"""Reading comfort of the rendered page: size, measure, rhythm, contrast, colour."""
from __future__ import annotations

import statistics as st
from dataclasses import dataclass, field

from ..color import apca, apca_min_lc, contrast_ratio, parse, wcag_level

BODY_TAGS = {"p", "li", "blockquote", "td", "dd", "figcaption"}
WHITE = (255.0, 255.0, 255.0, 1.0)


def _wmedian(pairs: list[tuple[float, float]]) -> float:
    """Median of values weighted by chars."""
    if not pairs:
        return 0.0
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total / 2:
            return v
    return pairs[-1][0]


@dataclass
class ViewportTypography:
    name: str = ""
    width: int = 0
    body_font_px: float = 0.0
    min_body_font_px: float = 0.0
    pct_text_below_16px: float = 0.0
    line_height_ratio: float = 0.0
    pct_tight_line_height: float = 0.0
    chars_per_line: float = 0.0
    dominant_block: dict = field(default_factory=dict)
    measure_outliers: list = field(default_factory=list)
    pct_lines_too_wide: float = 0.0
    pct_lines_too_narrow: float = 0.0
    content_width_px: int = 0
    paragraph_gap_ratio: float = 0.0
    pct_justified: float = 0.0
    pct_centered_long: float = 0.0
    pct_uppercase: float = 0.0
    letter_spacing_body: float = 0.0
    font_families: list = field(default_factory=list)
    distinct_sizes: int = 0
    min_contrast_ratio: float = 0.0
    median_contrast_ratio: float = 0.0
    median_apca_lc: float = 0.0
    contrast_failures: list = field(default_factory=list)
    apca_failures: list = field(default_factory=list)
    text_on_image: int = 0
    overflow_x: bool = False
    cls: float = 0.0
    lcp_ms: float = 0.0
    occlusion: float = 0.0            # share of the first screen covered by fixed chrome
    overlays: list = field(default_factory=list)
    first_screen_chars: int = 0
    links_underlined: float = 0.0
    link_contrast_vs_text: float = 0.0
    n_text_elements: int = 0
    webfonts: int = 0
    webfonts_blocking: int = 0
    blocking_font_families: list = field(default_factory=list)
    hover_only_blocks: int = 0
    hover_only_chars: int = 0
    justified_without_hyphens: float = 0.0

    def as_dict(self) -> dict:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


@dataclass
class TypographyReport:
    viewports: dict = field(default_factory=dict)
    dark_mode_supported: bool | None = None
    color_scheme: str = ""
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "viewports": {k: v.as_dict() for k, v in self.viewports.items()},
            "dark_mode_supported": self.dark_mode_supported,
            "color_scheme": self.color_scheme,
            "error": self.error,
        }

    @property
    def primary(self) -> ViewportTypography | None:
        return self.viewports.get("desktop") or (next(iter(self.viewports.values()), None))


def _analyse_viewport(name: str, data: dict) -> ViewportTypography:
    v = ViewportTypography(name=name, width=data.get("viewport", {}).get("width", 0))
    els = [e for e in data.get("elements", []) if e.get("chars", 0) >= 2]
    v.n_text_elements = len(els)
    body = [e for e in els if e["tag"] in BODY_TAGS and e["chars"] >= 40]
    pool = body or els
    if not pool:
        return v

    chars_total = sum(e["chars"] for e in pool) or 1
    v.body_font_px = round(_wmedian([(e["fontPx"], e["chars"]) for e in pool]), 1)
    v.min_body_font_px = round(min(e["fontPx"] for e in pool), 1)
    v.pct_text_below_16px = sum(e["chars"] for e in pool if e["fontPx"] < 16) / chars_total
    v.line_height_ratio = round(_wmedian([(e["lineHeightRatio"], e["chars"]) for e in pool]), 2)
    v.pct_tight_line_height = sum(e["chars"] for e in pool if 0 < e["lineHeightRatio"] < 1.4) / chars_total

    multi = [e for e in pool if e["lines"] >= 2]
    if multi:
        mchars = sum(e["chars"] for e in multi)
        # The page's measure is the measure of its main body of text. A char-weighted
        # median let a grid of narrow cards decide for a page whose prose column is fine,
        # and buried a narrow block inside a healthy page. Outliers are listed instead.
        dominant = max(multi, key=lambda e: e["chars"])
        v.chars_per_line = round(dominant["charsPerLine"], 1)
        v.dominant_block = {"tag": dominant["tag"], "chars": dominant["chars"],
                            "width_px": dominant["widthPx"],
                            "chars_per_line": dominant["charsPerLine"],
                            "text": (dominant.get("text") or "")[:80]}
        v.measure_outliers = [
            {"tag": e["tag"], "chars": e["chars"], "width_px": e["widthPx"],
             "chars_per_line": e["charsPerLine"], "text": (e.get("text") or "")[:60]}
            for e in sorted(multi, key=lambda e: -e["chars"])
            if e is not dominant and (e["charsPerLine"] > 90 or e["charsPerLine"] < 32)][:6]
        v.pct_lines_too_wide = sum(e["chars"] for e in multi if e["charsPerLine"] > 90) / mchars
        v.pct_lines_too_narrow = sum(e["chars"] for e in multi if e["charsPerLine"] < 40) / mchars
    else:
        v.chars_per_line = round(_wmedian([(e["charsPerLine"], e["chars"]) for e in pool]), 1)

    v.content_width_px = int(_wmedian([(e["widthPx"], e["chars"]) for e in pool]))
    gaps = data.get("paragraphGaps") or []
    v.paragraph_gap_ratio = round(st.median(gaps), 2) if gaps else 0.0

    v.pct_justified = sum(e["chars"] for e in pool if e["align"] == "justify") / chars_total
    # Justification is only a problem when the browser cannot break words to absorb it.
    v.justified_without_hyphens = sum(
        e["chars"] for e in pool
        if e["align"] == "justify" and (e.get("hyphens") or "none") in ("none", "manual")
    ) / chars_total
    v.pct_centered_long = sum(e["chars"] for e in pool
                              if e["align"] == "center" and e["chars"] > 200) / chars_total
    v.pct_uppercase = sum(e["chars"] for e in els
                          if e.get("transform") == "uppercase" and e["chars"] > 25) / \
        (sum(e["chars"] for e in els) or 1)
    v.letter_spacing_body = round(_wmedian([(e["letterSpacing"], e["chars"]) for e in pool]), 2)

    fams = sorted(data.get("familyHistogram", {}).items(), key=lambda kv: -kv[1])
    v.font_families = [{"family": f, "chars": c} for f, c in fams[:6]]
    v.distinct_sizes = len([s for s, c in data.get("sizeHistogram", {}).items() if c > 30])

    ratios, lcs = [], []
    for e in els:
        fg = parse(e.get("color"))
        bgs = e.get("bgLayers") or []
        bg = parse(bgs[0]) if bgs else WHITE
        if not fg or not bg:
            continue
        if bg[3] < 1.0:
            from ..color import blend
            bg = blend(bg, WHITE)
        if e.get("bgImage"):
            v.text_on_image += 1
        cr = contrast_ratio(fg, bg)
        lc = apca(fg, bg)
        ratios.append((cr, e["chars"]))
        lcs.append((lc if lc >= 0 else -lc, e["chars"]))
        lvl = wcag_level(cr, e["fontPx"], e["weight"] >= 700)
        need = apca_min_lc(e["fontPx"], e["weight"])
        item = {"tag": e["tag"], "font_px": e["fontPx"], "weight": e["weight"],
                "ratio": round(cr, 2), "apca_lc": lc, "apca_abs": abs(lc),
                "apca_required": need,
                "apca_note": "apca_lc is signed (negative = light text on dark); "
                             "compare apca_abs against apca_required",
                "color": e["color"], "background": bgs[0] if bgs else "rgb(255,255,255)",
                "text": (e.get("text") or "")[:90], "chars": e["chars"], "level": lvl}
        if lvl == "fail":
            v.contrast_failures.append(item)
        elif abs(lc) < need - 7.5:
            v.apca_failures.append(item)
    if ratios:
        v.min_contrast_ratio = round(min(r for r, _ in ratios), 2)
        v.median_contrast_ratio = round(_wmedian(ratios), 2)
        v.median_apca_lc = round(_wmedian(lcs), 1)
    v.contrast_failures = sorted(v.contrast_failures, key=lambda d: d["ratio"])[:12]
    v.apca_failures = sorted(v.apca_failures, key=lambda d: abs(d["apca_lc"]))[:12]

    # links inside body text
    links = [l for e in pool for l in (e.get("links") or [])]
    if links:
        v.links_underlined = sum(1 for l in links if "underline" in (l.get("decoration") or "")) / len(links)
        pairs = []
        for e in pool:
            base = parse(e.get("color"))
            for l in (e.get("links") or []):
                lc = parse(l.get("color"))
                if base and lc:
                    pairs.append(contrast_ratio(lc, base))
        if pairs:
            v.link_contrast_vs_text = round(st.median(pairs), 2)

    fonts = data.get("fonts") or {}
    v.webfonts = int(fonts.get("count") or 0)
    v.webfonts_blocking = int(fonts.get("blocking") or 0)
    v.blocking_font_families = [
        {"family": f.get("family"), "display": f.get("display"), "weight": f.get("weight")}
        for f in (fonts.get("families") or [])
        if f.get("downloads") and (f.get("display") or "auto") in ("auto", "block")][:6]
    v.hover_only_blocks = int(data.get("hoverOnly") or 0)
    v.hover_only_chars = int(data.get("hoverOnlyChars") or 0)
    v.occlusion = round(float(data.get("occlusion") or 0), 4)
    v.overlays = data.get("overlays") or []
    v.first_screen_chars = int(data.get("firstScreenChars") or 0)
    v.overflow_x = bool(data.get("overflowX"))
    m = data.get("metrics") or {}
    v.cls = round(float(m.get("cls") or 0), 4)
    v.lcp_ms = round(float(m.get("lcp") or 0), 1)
    return v


def analyse(render_result) -> TypographyReport:
    r = TypographyReport(error=getattr(render_result, "error", None))
    for name, data in (getattr(render_result, "viewports", {}) or {}).items():
        r.viewports[name] = _analyse_viewport(name, data)
    dm = getattr(render_result, "dark_mode", None)
    if dm:
        primary = (render_result.viewports.get("desktop") or {})
        light_bg = primary.get("bodyBg")
        r.color_scheme = dm.get("scheme", "")
        r.dark_mode_supported = bool(
            "dark" in (dm.get("scheme") or "") or (light_bg and dm.get("bg") and
                                                   parse(dm["bg"]) != parse(light_bg))
        )
    return r
