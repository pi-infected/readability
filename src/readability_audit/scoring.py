"""Declarative scoring: every metric carries its target band, its weight and its advice."""
from __future__ import annotations

from dataclasses import dataclass, field

def pillar_weights(config: dict | None) -> dict:
    w = dict(config.get("pillar_weights") or {}) if config else {}
    return w


PILLARS = {
    "clarity": ("Clarity", "How much effort the sentences and vocabulary demand", 0.30),
    "structure": ("Structure", "How well the page is organised and scannable", 0.25),
    "comfort": ("Comfort", "How the rendered text feels to the eye", 0.30),
    "access": ("Accessibility", "Whether everyone can actually read it", 0.15),
}

AUDIENCE = {
    "general":   {"lix": (30, 45), "lix_tol": (20, 55), "asl": (12, 20), "asl_tol": (8, 26),
                  "poly": (0.06, 0.18), "fre": (55, 85)},
    "technical": {"lix": (35, 50), "lix_tol": (25, 60), "asl": (13, 23), "asl_tol": (9, 30),
                  "poly": (0.08, 0.22), "fre": (40, 75)},
    "academic":  {"lix": (40, 58), "lix_tol": (30, 68), "asl": (15, 27), "asl_tol": (10, 34),
                  "poly": (0.10, 0.28), "fre": (25, 65)},
    "children":  {"lix": (15, 30), "lix_tol": (10, 38), "asl": (6, 13), "asl_tol": (4, 17),
                  "poly": (0.0, 0.08), "fre": (80, 100)},
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "ok": 5}

# A pillar loses points for each concrete defect found in it, on top of its metric
# average — otherwise one broken thing drowns in twenty things that are fine.
FINDING_PENALTY = {"critical": 16.0, "high": 9.0, "medium": 4.0, "low": 1.5, "info": 0.0}
# A page with an unfixed critical defect cannot be graded above this.
MAX_PILLAR_PENALTY = 35.0
CRITICAL_CAP = 79.0
HIGH_CAP = 88.0

# Page types read differently, so their targets differ.
PAGE_TYPE_OVERRIDES = {
    "landing": {
        "measure": ((32, 80), (24, 95)),
        "mobile_measure": ((24, 60), (18, 70)),
        "font_size": ((15, 21), (13, 24)),
        "small_text": ((0, 0.40), (0, 0.75)),
        "connectives": ((0.12, 0.60), (0.04, 0.85)),
        "headings_density": ((3, 25), (1.5, 45)),
        "paragraph_length": ((15, 70), (8, 110)),
        "link_density": ((0.02, 0.30), (0, 0.50)),
        "boilerplate": ((0, 0.60), (0, 0.80)),
        "asl": ((8, 20), (5, 26)),
    },
    "index": {
        # Bringhurst's measure is about running prose. A grid of teaser cards is
        # legitimately narrower, and penalising it measures the layout, not the reading.
        "measure": ((32, 80), (24, 95)),
        "mobile_measure": ((24, 60), (18, 70)),
        "font_size": ((14, 21), (12, 24)),
        "small_text": ((0, 0.55), (0, 0.9)),
        "connectives": ((0.12, 0.60), (0.04, 0.85)),
        "headings_density": ((3, 40), (1, 70)),
        "link_density": ((0.05, 0.95), (0, 1.20)),
        "paragraph_length": ((10, 70), (5, 110)),
        "boilerplate": ((0, 0.70), (0, 0.90)),
        "scannability": ((0.55, 1.0), (0.35, 1.0)),
    },
    "doc": {
        "headings_density": ((4, 20), (2, 32)),
        "word_rarity": ((3.3, 5.5), (2.8, 6.5)),
        "polysyllabic": None,
    },
    "legal": {
        "asl": ((12, 26), (8, 34)),
        "lix": ((30, 55), (20, 68)),
        "long_sentences": ((0, 0.25), (0, 0.45)),
        "passive": ((0, 0.20), (0, 0.35)),
        "nominalization": ((0, 0.09), (0, 0.16)),
    },
    "article": {},
}


LOCALES = {"en", "fr", "de", "es", "it", "pt", "nl", "ja", "zh", "ru", "pl", "tr", "ko",
           "en-us", "en-gb", "fr-fr", "pt-br", "zh-cn"}


def _path_parts(url: str) -> list[str]:
    from urllib.parse import urlparse
    parts = [p for p in urlparse(url).path.split("/") if p]
    if parts and parts[0].lower() in LOCALES:
        parts = parts[1:]
    return parts


def classify_page(pa) -> str:
    """Landing / index / article / doc / legal. Different shapes, different targets."""
    stt = pa.structure
    if stt is None:
        return "article"
    url = (pa.final_url or pa.url).lower()
    parts = _path_parts(url)
    depth = len(parts)
    words = stt.word_count

    if any(k in url for k in ("/legal", "/terms", "/privacy", "/cgu", "/mentions",
                              "conditions", "policy", "cookies")):
        return "legal"
    if stt.n_code_blocks >= 3 or any(k in url for k in ("/docs/", "/documentation", "/api/",
                                                        "/reference/", "/faq")):
        return "doc"
    if depth == 0:
        return "landing"
    if stt.link_density > 0.35:
        return "index"
    if words < 300 and stt.links_in_main > 12:
        return "index"
    if depth == 1 and stt.links_in_main > 20 and stt.mean_paragraph_words < 45:
        return "index"
    if depth <= 1 and words < 1200 and (stt.link_density > 0.08 or stt.n_list_items > 8):
        return "landing"
    return "article"


def band_score(v: float, ideal: tuple[float, float], tol: tuple[float, float]) -> float:
    """100 inside the ideal band, 60 at the tolerable edge, 0 one more span out."""
    a, b = ideal
    c, d = tol
    if v is None:
        return 100.0
    if a <= v <= b:
        return 100.0
    if v < a:
        span = max(a - c, 1e-9)
        if v >= c:
            return 60.0 + 40.0 * (v - c) / span
        return max(0.0, 60.0 * (1 - (c - v) / span))
    span = max(d - b, 1e-9)
    if v <= d:
        return 60.0 + 40.0 * (d - v) / span
    return max(0.0, 60.0 * (1 - (v - d) / span))


@dataclass
class Metric:
    key: str
    label: str
    pillar: str
    value: float | None
    unit: str = ""
    ideal: tuple = (0, 0)
    tolerable: tuple = (0, 0)
    weight: float = 1.0
    advice: str = ""
    why: str = ""
    evidence: list = field(default_factory=list)
    score: float = 100.0
    display: str = ""
    target_display: str = ""

    def _fmt(self, v: float) -> str:
        if self.unit == "%":
            return f"{v:.0%}"
        if isinstance(v, float) and v != int(v):
            return f"{v:.3g}" if abs(v) < 10 else f"{v:.1f}".rstrip("0").rstrip(".")
        return f"{v:g}"

    def finalise(self) -> "Metric":
        self.score = round(band_score(self.value, self.ideal, self.tolerable), 1)
        self.target_display = f"{self._fmt(self.ideal[0])}-{self._fmt(self.ideal[1])}" + (
            f" {self.unit}" if self.unit and self.unit != "%" else "")
        if not self.display:
            self.display = ("n/a" if self.value is None else
                            (f"{self.value:.0%}" if self.unit == "%" else
                             f"{self._fmt(self.value)}{(' ' + self.unit) if self.unit and self.unit != '%' else ''}"))
        return self

    @property
    def severity(self) -> str:
        if self.score >= 85:
            return "ok"
        if self.score >= 70:
            return "low"
        if self.score >= 50:
            return "medium"
        if self.score >= 30:
            return "high"
        return "critical"

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "pillar": self.pillar,
                "value": self.value, "display": self.display, "unit": self.unit,
                "ideal": list(self.ideal), "tolerable": list(self.tolerable),
                "target_display": self.target_display,
                "weight": self.weight, "score": self.score, "severity": self.severity,
                "advice": self.advice, "why": self.why, "evidence": self.evidence[:6]}


@dataclass
class Finding:
    key: str
    title: str
    severity: str
    pillar: str
    detail: str
    fix: str
    evidence: list = field(default_factory=list)
    score: float | None = None
    params: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "severity": self.severity,
                "pillar": self.pillar, "detail": self.detail, "fix": self.fix,
                "evidence": self.evidence[:6], "score": self.score, "params": self.params}


@dataclass
class Scores:
    overall: float | None = 0.0
    grade: str = ""
    pillars: dict = field(default_factory=dict)
    metrics: list = field(default_factory=list)
    page_type: str = "article"

    def as_dict(self) -> dict:
        return {"overall": self.overall, "grade": self.grade, "page_type": self.page_type,
                "pillars": self.pillars,
                "metrics": [m.as_dict() for m in self.metrics]}


def grade_of(score: float) -> str:
    for cut, g in ((90, "A"), (80, "B"), (70, "C"), (60, "D"), (45, "E")):
        if score >= cut:
            return g
    return "F"


def _m(*a, **kw) -> Metric:
    return Metric(*a, **kw).finalise()


MIN_PROSE_WORDS = 150       # below this, language metrics measure fragments, not writing
LOW_CONFIDENCE_WORDS = 400  # between the two, they are indicative only


def apply_config(ms: list[Metric], config: dict | None) -> list[Metric]:
    """Let a project retune the targets it disagrees with, without forking the tool."""
    if not config:
        return ms
    bands = config.get("bands") or {}
    weights = config.get("weights") or {}
    drop = set(config.get("disable") or [])
    out = []
    for m in ms:
        if m.key in drop:
            continue
        b = bands.get(m.key)
        if b:
            if "ideal" in b:
                m.ideal = tuple(b["ideal"])
            if "tolerable" in b:
                m.tolerable = tuple(b["tolerable"])
            m.finalise()
        if m.key in weights:
            m.weight = float(weights[m.key])
        out.append(m)
    return out


def build_metrics(pa, audience: str = "general", page_type: str = "article") -> list[Metric]:
    prof = AUDIENCE.get(audience, AUDIENCE["general"])
    ms: list[Metric] = []
    f, sx, lx, stt = pa.formulas, pa.syntax, pa.lexical, pa.structure
    prose_words = stt.prose_word_count if stt else 0
    # A link index or a landing page is not "unclear writing" — it is not writing. Nor is
    # a script the word- and syllable-based measures cannot read.
    score_language = prose_words >= MIN_PROSE_WORDS and getattr(pa, "clarity_supported", True)
    lang_weight = 1.0 if prose_words >= LOW_CONFIDENCE_WORDS else 0.5

    # ---------------- clarity ----------------
    lix = f.get("lix") if score_language else None
    if lix:
        ms.append(_m("lix", "Reading difficulty (LIX)", "clarity", lix.value, "index",
                     prof["lix"], prof["lix_tol"], 2.0,
                     "Shorten sentences and swap long words for short ones. LIX counts only "
                     "sentence length and words over six letters, so both levers are blunt and reliable.",
                     "LIX is language-independent, which is why it is the primary difficulty score here.",
                     display=f"{lix.value:g} ({lix.band})"))
    fre = f.get("flesch_reading_ease") if score_language else None
    if fre:
        lo, hi = prof["fre"]
        ms.append(_m("flesch", fre.name, "clarity", fre.value, "score",
                     (lo, hi), (lo - 20, min(hi + 20, 120)), 1.2,
                     "Lower the syllable count per word and the words per sentence.",
                     "Flesch reading ease, with the coefficients calibrated for this page's language.",
                     display=f"{fre.value:g} ({fre.band})"))
    if sx and sx.n_sentences >= 4 and score_language:
        ms.append(_m("asl", "Average sentence length", "clarity", round(sx.mean_len, 1), "words",
                     prof["asl"], prof["asl_tol"], 1.5,
                     "Split the sentences over 30 words. One idea per sentence.",
                     "Sentence length is the single strongest predictor of reading effort."))
        ms.append(_m("long_sentences", "Sentences over the length cap", "clarity",
                     sx.pct_long, "%", (0, 0.18), (0, 0.32), 1.2,
                     "Rewrite the longest sentences; they are listed in the evidence.",
                     "A reader holds a clause in working memory until the verb resolves.",
                     evidence=sx.longest_sentences))
        ms.append(_m("rhythm", "Sentence length variation", "clarity",
                     round(sx.variation, 2), "cv", (0.45, 1.10), (0.25, 1.60), 0.8,
                     "Alternate short and long sentences. Uniform length reads as a drone.",
                     "Coefficient of variation of sentence length: rhythm, not difficulty."))
        # Validated against 104 labelled pairs (calibration/difficulty.json): passive
        # share ranks the harder text correctly only 61% of the time, and not
        # significantly in either language alone. It is a plain-language style concern,
        # not a difficulty predictor, so it carries half the weight and says so.
        ms.append(_m("passive", "Passive voice", "clarity", sx.passive_ratio, "%",
                     (0, 0.14), (0, 0.28), 0.5,
                     "Name the actor: 'the parser rejects it', not 'it is rejected'.",
                     "A style signal, not a difficulty one: on labelled easy/hard pairs it "
                     "ranks the harder text correctly only 61% of the time.",
                     evidence=[{"text": s} for s in sx.passive_examples]))
        ms.append(_m("nominalization", "Nominalisations", "clarity", sx.nominalization_ratio, "%",
                     (0, 0.05), (0, 0.10), 0.8,
                     "Turn abstract nouns back into verbs: 'we decide', not 'the making of a decision'.",
                     "Nominalisation is the main source of institutional fog."))
        # Calibration: reference median 23%, so Yoast's 30% floor rejects the majority of
        # well-written pages. Lowered to the measured median, minus a margin.
        ms.append(_m("connectives", "Transition words", "clarity", sx.connective_ratio, "%",
                     (0.18, 0.65), (0.08, 0.85), 0.7,
                     "Signal the joins between ideas: however, because, so, instead.",
                     "Yoast-style check: connectives make the argument's shape visible."))
    if lx and lx.n_words >= 80 and score_language:
        ms.append(_m("polysyllabic", "Long-word load", "clarity", lx.pct_polysyllabic, "%",
                     prof["poly"], (prof["poly"][0], prof["poly"][1] + 0.10), 1.0,
                     "Prefer the shorter synonym where one exists.",
                     "Words of three or more syllables drive every classic difficulty formula."))
        if lx.mean_zipf:
            ms.append(_m("word_rarity", "Vocabulary rarity", "clarity", lx.mean_zipf, "zipf",
                         (3.6, 5.5), (3.0, 6.5), 1.0,
                         "Define the rare terms on first use, or replace them.",
                         "Mean Zipf frequency over content words (7 = 'the', 3 = specialist).",
                         evidence=lx.rare_words[:8],
                         display=f"{lx.mean_zipf:g} zipf"))
        ms.append(_m("hedging", "Filler and marketing words", "clarity", lx.hedge_ratio, "%",
                     (0, 0.010), (0, 0.025), 0.8,
                     "Cut the intensifiers and the superlatives. Replace each with a fact.",
                     "Hedges and hype dilute the sentence without adding information.",
                     evidence=lx.hedges_found[:8]))
        ms.append(_m("diversity", "Vocabulary diversity", "clarity", lx.mattr, "ratio",
                     (0.55, 0.85), (0.40, 0.95), 0.5,
                     "Vary the wording, or trim the repetition.",
                     "Moving-average type-token ratio, window 100 words."))

    # ---------------- structure ----------------
    if stt and stt.word_count >= 120 and prose_words >= MIN_PROSE_WORDS:
        ms.append(_m("headings_density", "Headings per 1000 words", "structure",
                     round(stt.headings_per_1000w, 1), "per 1k", (3, 15), (1.5, 30), 1.3,
                     "Add a heading roughly every 200 to 300 words.",
                     "Headings are how a reader decides whether to read at all."))
        ms.append(_m("unbroken_run", "Longest stretch without a heading", "structure",
                     stt.longest_unbroken_words, "words", (0, 400), (0, 800), 1.2,
                     "Break the longest section with a sub-heading.",
                     "A wall of text with no exit signs is where readers leave."))
    if stt and stt.n_paragraphs >= 3:
        ms.append(_m("paragraph_length", "Average paragraph length", "structure",
                     round(stt.mean_paragraph_words, 1), "words", (30, 80), (15, 120), 1.2,
                     "Aim for three to five sentences per paragraph.",
                     "Paragraph size sets the visual density of the page."))
        ms.append(_m("long_paragraphs", "Paragraphs over 120 words", "structure",
                     stt.pct_long_paragraphs, "%", (0, 0.10), (0, 0.25), 1.0,
                     "Split them at the first change of idea.", ""))
    if stt:
        ms.append(_m("link_density", "Link text share of the body", "structure",
                     stt.link_density, "%", (0.01, 0.12), (0, 0.25), 0.8,
                     "Too few links leaves claims unsupported; too many turns prose into a menu.",
                     ""))
        ms.append(_m("scannability", "Scannability", "structure", stt.scannability, "ratio",
                     (0.7, 1.0), (0.45, 1.0), 1.2,
                     "Add headings, lists and emphasis so the page survives a 10-second skim.",
                     "Composite of heading density, paragraph size, lists and emphasis."))
        if stt.title_length:
            ms.append(_m("title_length", "Title length", "structure", stt.title_length, "chars",
                         (25, 65), (10, 90), 0.6,
                         "Aim for 30 to 60 characters so it survives search results and tabs.", ""))
        # Calibration (calibration/reference.json): only 15% of 13 deliberately-set
        # reference pages sit in the 110-165 SEO convention; the spread is 0 to 398.
        # This describes a search snippet, not how the page reads. Wide band, low weight.
        ms.append(_m("meta_description", "Meta description length", "structure",
                     stt.meta_description_length, "chars", (70, 200), (0, 320), 0.3,
                     "Write a 120-160 character summary; it is the first text most readers see.", ""))
        ms.append(_m("boilerplate", "Boilerplate share of the page text", "structure",
                     stt.boilerplate_ratio, "%", (0, 0.45), (0, 0.70), 0.8,
                     "Trim navigation, banners and repeated footers around the content.",
                     "Chrome that outweighs the content buries it."))

    # ---------------- comfort (rendered) ----------------
    tp = getattr(pa, "typography", None)
    vp = tp.primary if tp else None
    if vp:
        ms.append(_m("font_size", "Body text size (desktop)", "comfort", vp.body_font_px, "px",
                     (16, 21), (14, 24), 1.6,
                     "Set body copy to at least 16px; 17-19px reads best on the desktop web.",
                     "Below 16px the browser's default reader has to lean in."))
        ms.append(_m("small_text", "Text rendered below 16px", "comfort",
                     vp.pct_text_below_16px, "%", (0, 0.12), (0, 0.35), 1.0,
                     "Raise captions, labels and footnotes to 14px minimum, body to 16px.", ""))
        ms.append(_m("line_height", "Line height", "comfort", vp.line_height_ratio, "ratio",
                     (1.45, 1.75), (1.25, 2.0), 1.4,
                     "Set line-height between 1.5 and 1.7 for body copy.",
                     "Tight leading makes the eye lose the line on the return sweep."))
        ms.append(_m("measure", "Line length (characters per line)", "comfort",
                     vp.chars_per_line, "chars", (50, 80), (38, 95), 1.5,
                     "Cap the text column near 65 characters (about 34em).",
                     "Bringhurst's 45-75 character measure; beyond ~90 the return sweep fails.",
                     evidence=[dict(vp.dominant_block, column_width_px=vp.content_width_px)]
                     if getattr(vp, "dominant_block", None) else []))
        if vp.paragraph_gap_ratio > 0:
            ms.append(_m("paragraph_gap", "Space between paragraphs", "comfort",
                         vp.paragraph_gap_ratio, "line-heights", (0.5, 1.4), (0.25, 2.2), 0.9,
                         "Leave about one line of space between paragraphs.",
                         "Without a gap the paragraph break stops being visible."))
        ms.append(_m("contrast", "Body text contrast (WCAG)", "comfort",
                     vp.median_contrast_ratio, "ratio", (7.0, 21.0), (4.5, 21.0), 1.5,
                     "Darken the body colour until it clears 7:1 against its background.",
                     "WCAG 2.2 asks 4.5:1 for AA and 7:1 for AAA on body text.",
                     display=f"{vp.median_contrast_ratio:g}:1"))
        ms.append(_m("apca", "Perceptual contrast (APCA Lc)", "comfort",
                     abs(vp.median_apca_lc), "Lc", (75, 108), (60, 108), 1.0,
                     "APCA wants Lc 75 or better for body text, 90 for text under 18px.",
                     "APCA models perceived lightness, which WCAG 2's ratio does not.",
                     display=f"Lc {abs(vp.median_apca_lc):g}"))
        ms.append(_m("justified", "Justified text without hyphenation", "comfort",
                     vp.justified_without_hyphens, "%", (0, 0.02), (0, 0.15), 0.7,
                     "Use ragged-right, or keep justification and add hyphens: auto.",
                     "Justification without hyphenation opens rivers of white space."))
        ms.append(_m("uppercase", "Text set in capitals", "comfort", vp.pct_uppercase, "%",
                     (0, 0.03), (0, 0.10), 0.6,
                     "Reserve all-caps for short labels.",
                     "Capitals remove the word-shape cue that fast reading relies on."))
        if vp.n_text_elements >= 12:
            ms.append(_m("type_sizes", "Distinct type sizes", "comfort", vp.distinct_sizes, "sizes",
                         (2, 8), (1, 12), 0.4,
                         "Settle on a type scale of five or six steps.", ""))
        ms.append(_m("occlusion", "First screen covered by fixed chrome", "comfort",
                     vp.occlusion, "%", (0, 0.25), (0, 0.45), 1.0,
                     "Shrink the sticky header, dismiss the cookie wall on scroll, and keep "
                     "floating widgets small. Every pixel of it is a pixel not reading.",
                     "Measured by sampling the viewport against every fixed and sticky element.",
                     evidence=[{"text": f"{o['tag']}.{o['cls'][:30]} — {int(o['area'] * 100)}% "
                                        f"of the screen: {o['text'][:60]}"} for o in vp.overlays[:4]]))
        ms.append(_m("cls", "Layout shift while loading", "comfort", vp.cls, "CLS",
                     (0, 0.1), (0, 0.25), 0.6,
                     "Reserve space for images, ads and web fonts.",
                     "Text that jumps under the eye costs the reader their place."))
        mob = tp.viewports.get("mobile") if tp else None
        if mob:
            ms.append(_m("mobile_font", "Body text size (mobile)", "comfort", mob.body_font_px, "px",
                         (16, 20), (14, 22), 1.2,
                         "Keep mobile body text at 16px or more; smaller triggers zoom on iOS.", ""))
            ms.append(_m("mobile_measure", "Line length on mobile", "comfort",
                         mob.chars_per_line, "chars", (32, 60), (24, 70), 0.9,
                         "Give the text column 16px of side padding, no more.", ""))

    # ---------------- accessibility ----------------
    ac = getattr(pa, "a11y", None)
    if ac:
        ms.append(_m("alt_coverage", "Images with alt text", "access", ac.alt_coverage, "%",
                     (1.0, 1.0), (0.85, 1.0), 1.2,
                     "Give every content image an alt; mark decorative ones alt=\"\".", ""))
        ms.append(_m("heading_order", "Heading level skips", "access", ac.heading_skips, "skips",
                     (0, 0), (0, 2), 1.0,
                     "Never jump from h2 to h4; screen-reader users navigate by level.", ""))
        ms.append(_m("weak_links", "Uninformative link text", "access", ac.weak_links, "links",
                     (0, 0), (0, 3), 0.9,
                     "Replace 'click here' and 'read more' with the destination's name.", ""))
        ms.append(_m("acronyms", "Acronyms never expanded", "access",
                     len(ac.unexplained_acronyms), "terms", (0, 4), (0, 12), 0.5,
                     "Spell out each acronym once, on first use.", "",
                     evidence=ac.unexplained_acronyms))
        if ac.rem_scaling is not None:
            ms.append(_m("rem_scaling", "Text follows the browser's font size", "access",
                         1.0 if ac.rem_scaling else 0.0, "bool", (1, 1), (1, 1), 1.0,
                         "Size text in rem/em so a reader's larger default font is honoured.",
                         "Text pinned in px ignores the accessibility setting people actually use.",
                         display="yes" if ac.rem_scaling else "no"))
    if lang_weight != 1.0:
        for m in ms:
            if m.pillar == "clarity":
                m.weight *= lang_weight
    over = PAGE_TYPE_OVERRIDES.get(page_type, {})
    kept = []
    for m in ms:
        if m.key in over:
            band = over[m.key]
            if band is None:            # metric does not apply to this page type
                continue
            m.ideal, m.tolerable = band
            m.finalise()
        kept.append(m)
    return kept


def pillar_scores(ms: list[Metric], findings: list["Finding"] | None = None) -> dict:
    out = {}
    for key, (label, desc, weight) in PILLARS.items():
        sel = [m for m in ms if m.pillar == key]
        if not sel:
            continue
        tw = sum(m.weight for m in sel) or 1
        out[key] = {"label": label, "description": desc,
                    "score": round(sum(m.score * m.weight for m in sel) / tw, 1),
                    "weight": weight, "metrics": len(sel)}
    for f in (findings or []):
        if f.pillar in out:
            pen = FINDING_PENALTY.get(f.severity, 0.0)
            out[f.pillar]["penalty"] = round(out[f.pillar].get("penalty", 0.0) + pen, 1)
    for v in out.values():
        # Findings overlap (small text and low contrast are usually the same block), so
        # cap the stack: a pillar should degrade, not collapse.
        pen = min(v.get("penalty", 0.0), MAX_PILLAR_PENALTY)
        v["penalty"] = round(pen, 1)
        v["raw_score"] = v["score"]
        v["score"] = round(max(0.0, v["score"] - pen), 1)
    total_w = sum(v["weight"] for v in out.values()) or 1
    for v in out.values():
        v["effective_weight"] = round(v["weight"] / total_w, 3)
    return out


def discrete_findings(pa) -> list[Finding]:
    out: list[Finding] = []
    ac, stt = pa.a11y, pa.structure
    ex = getattr(pa, "extraction", None) or {}
    if ex.get("content_needs_js"):
        served = ex.get("served_prose_chars", 0)
        out.append(Finding(
            "js_dependent_text", "The page's text only exists after JavaScript runs", "high",
            "access",
            f"None of the opening paragraphs appear in the served HTML "
            f"({served} characters of prose served, "
            f"{ex.get('rendered_prose_chars', 0)} after rendering). Readers with a failed "
            "or slow script load, reader modes, and clients that do not run JavaScript "
            "get the shell.",
            "Server-render or pre-render the article text. The page can still hydrate on "
            "top of it."))
    if ex.get("inline_paragraph_containers"):
        out.append(Finding(
            "inline_paragraphs", "Paragraphs are marked up as inline elements", "low",
            "access",
            f"{ex['inline_paragraph_containers']} container(s) hold their paragraphs in "
            "inline tags styled display:block. They look right and read right, but the "
            "accessibility tree gets one undifferentiated run with no paragraph boundaries.",
            "Use <p> for paragraphs. Screen-reader users navigate by paragraph."))
    if ex.get("machine_blocks_dropped"):
        out.append(Finding(
            "machine_output", "Machine output sits in the page text", "info", "structure",
            f"{ex['machine_blocks_dropped']} blocks read as JSON, logs or shell transcripts "
            "rather than prose. They are excluded from the language metrics so the demo is "
            "not scored as writing.",
            "Nothing to fix if this is a deliberate terminal demo. Wrap it in <pre> so "
            "every tool and every screen reader treats it as code.",
            params={"n": ex["machine_blocks_dropped"]}))
    if ex.get("note"):
        cov = ex.get("coverage")
        out.append(Finding(
            "extraction_doubt", "The content region is uncertain on this page", "info",
            "structure",
            f"{ex['note']} (we account for {cov:.0%} of what an independent extractor "
            f"finds, region: {ex.get('selector', '?')}). Read this page's language "
            "metrics with that in mind.",
            "Check that the content region we picked is the article. If the page already "
            "has <main>, the mismatch is usually chrome sitting inside it or content "
            "sitting outside it.",
            params={"coverage": cov}))
    # Chinese and Japanese have content without having spaces, so a word count of one is
    # not an empty page. Characters decide; words only qualify the message.
    if stt is not None and stt.word_count < 25 and stt.text_chars < 200:
        out.append(Finding(
            "no_content", "The page has no readable content", "high", "structure",
            f"{stt.text_chars} characters of text in the whole document. There is nothing "
            "here to score for reading.",
            "If this page is meant to be read, it is not reaching the reader at all."))
    if not getattr(pa, "clarity_supported", True) and getattr(pa, "clarity_note", ""):
        out.append(Finding(
            "clarity_unsupported", "The writing is not scored on this page", "info", "clarity",
            f"{pa.clarity_note.capitalize()}. Structure, comfort and accessibility are "
            "measured as usual.",
            "Nothing to fix. Reported so the missing pillar is not read as a perfect one."))
    if stt is not None and stt.prose_word_count < MIN_PROSE_WORDS and getattr(
            pa, "clarity_supported", True):
        out.append(Finding(
            "little_prose", "Too little running text to judge the writing", "info", "clarity",
            f"Only {stt.prose_word_count} words sit in paragraphs; the rest is headings, list "
            "items and link labels. Language metrics are not scored on this page.",
            "If this page is meant to be read rather than skimmed, give it prose."))
    tp = getattr(pa, "typography", None)
    vp = tp.primary if tp else None

    if ac and ac.lang_mismatch:
        out.append(Finding(
            "lang_mismatch", "The declared language is not the language of the text", "high",
            "access",
            f"<html lang=\"{ac.lang_declared}\"> but the prose reads as "
            f"{ac.lang_detected} (confidence {ac.lang_confidence:.0%}).",
            f"Set lang=\"{ac.lang_detected}\" on this page. Screen readers pick the voice from it, "
            "and search engines pick the audience."
            + (f" The DOM corrects it to \"{pa.lang_declared_rendered}\" after hydration, "
               "which is too late for a crawler or a reader whose script did not run."
               if getattr(pa, "lang_declared_rendered", None) else ""),
            params={"detected": ac.lang_detected, "declared": ac.lang_declared},
            evidence=[{"element": "html", "attribute": "lang",
                       "value": ac.lang_declared, "source": "served HTML",
                       "detected_from_prose": ac.lang_detected}]))
    if ac and not ac.lang_declared:
        out.append(Finding("lang_missing", "No lang attribute on <html>", "medium", "access",
                           "The page never declares its language.",
                           "Add lang=\"…\" to the <html> element."))
    if ac and not ac.has_h1:
        out.append(Finding("no_h1", "The page has no h1", "high", "structure",
                           "Nothing declares what this page is about at the top level.",
                           "Give the page exactly one h1 that names its subject."))
    elif ac and ac.multiple_h1:
        out.append(Finding("many_h1", f"{stt.h1_count} h1 elements", "low", "structure",
                           "More than one top-level heading makes the outline ambiguous.",
                           "Keep one h1 and demote the rest to h2."))
    if stt and not stt.meta_description:
        out.append(Finding("no_meta_desc", "No meta description", "low", "structure",
                           "Search results and link previews will show an arbitrary excerpt.",
                           "Write a 120-160 character summary."))
    # Chinese and Japanese have content without having spaces, so a word count of one is
    # not an empty page. Characters decide; words only qualify the message.
    if stt is not None and stt.word_count < 25 and stt.text_chars < 200:
        out.append(Finding(
            "no_content", "The page has no readable content", "high", "structure",
            f"{stt.text_chars} characters of text in the whole document. There is nothing "
            "here to score for reading.",
            "If this page is meant to be read, it is not reaching the reader at all."))
    if not getattr(pa, "clarity_supported", True) and getattr(pa, "clarity_note", ""):
        out.append(Finding(
            "clarity_unsupported", "The writing is not scored on this page", "info", "clarity",
            f"{pa.clarity_note.capitalize()}. Structure, comfort and accessibility are "
            "measured as usual.",
            "Nothing to fix. Reported so the missing pillar is not read as a perfect one."))
    if stt is not None and stt.prose_word_count < MIN_PROSE_WORDS and getattr(
            pa, "clarity_supported", True):
        for f in out:
            if f.key == "little_prose":
                f.params = {"n": stt.prose_word_count}
    if vp and vp.contrast_failures:
        worst = vp.contrast_failures[0]
        out.append(Finding(
            "contrast_fail", f"{len(vp.contrast_failures)} text block{'s' if len(vp.contrast_failures) != 1 else ''} fail{'' if len(vp.contrast_failures) != 1 else 's'} WCAG AA contrast",
            "critical" if worst["ratio"] < 3 else "high", "comfort",
            f"The worst is {worst['ratio']}:1 at {worst['font_px']:g}px "
            f"({worst['color']} on {worst['background']}); AA needs 4.5:1.",
            "Darken the foreground or lighten the background until each clears 4.5:1.",
            evidence=vp.contrast_failures[:6]))
    if vp and vp.apca_failures and not vp.contrast_failures:
        out.append(Finding(
            "apca_fail", f"{len(vp.apca_failures)} text block{'s are' if len(vp.apca_failures) != 1 else ' is'} perceptually thin", "medium",
            "comfort",
            "They pass WCAG 2 but fall short of the APCA level for their size and weight.",
            "Raise the contrast or the font size for these blocks.",
            evidence=vp.apca_failures[:6]))
    if vp and vp.overflow_x:
        out.append(Finding("overflow_desktop", "The page scrolls sideways", "high", "comfort",
                           f"Content is {vp.width}px wide in a {vp.width}px viewport.",
                           "Find the element wider than the viewport and constrain it."))
    mob = tp.viewports.get("mobile") if tp else None
    if mob and mob.overflow_x:
        out.append(Finding("overflow_mobile", "The page scrolls sideways on mobile", "high",
                           "comfort", "Horizontal scrolling on a 390px viewport.",
                           "Use max-width:100% on media and avoid fixed pixel widths."))
    if ac and ac.tables_without_headers:
        out.append(Finding("table_headers", f"{ac.tables_without_headers} tables have no header row",
                           "medium", "access", "Data tables without <th> cannot be navigated by column.",
                           "Add <th scope=\"col\"> to the header row."))
    if ac and ac.images_missing_alt:
        out.append(Finding("alt_missing", f"{ac.images_missing_alt} images have no alt attribute",
                           "high" if ac.alt_coverage < 0.8 else "medium", "access",
                           f"{ac.images_missing_alt} of {ac.n_images} images.",
                           "Describe the image, or set alt=\"\" if it is decorative."))
    if ac and ac.filename_alts:
        out.append(Finding("alt_filename", f"{ac.filename_alts} alt texts are file names", "medium",
                           "access", "An alt of \"hero-2.png\" is read aloud verbatim.",
                           "Write what the image shows."))
    if stt and stt.ambiguous_link_texts:
        out.append(Finding("ambiguous_links",
                           f"{len(stt.ambiguous_link_texts)} link texts point at several destinations",
                           "low", "access",
                           "The same words lead to different pages, which is unusable out of context.",
                           "Make each link text describe its own destination.",
                           evidence=stt.ambiguous_link_texts[:6]))
    if tp and tp.dark_mode_supported is False:
        declared = (tp.color_scheme or "").strip()
        mono = declared in ("light", "dark", "only light", "only dark")
        out.append(Finding(
            "no_dark_mode", "No dark colour scheme", "info" if mono else "low", "comfort",
            "The page renders identically under prefers-color-scheme: dark."
            + (f" It declares color-scheme: {declared}, so this is a stated choice rather "
               "than an omission." if mono else ""),
            "Declare color-scheme and provide dark tokens; night reading is common."))
    if vp and vp.webfonts_blocking:
        out.append(Finding(
            "font_display", f"{vp.webfonts_blocking} web fonts can hide text while they load",
            "low", "comfort",
            "Their font-display is auto or block, so the browser paints nothing until the "
            "file arrives. Faces whose src is only local() are excluded: they download "
            "nothing and can hide nothing.",
            "Set font-display: swap (or optional) on those @font-face rules.",
            evidence=vp.blocking_font_families))
    if vp and vp.hover_only_chars >= 200:
        out.append(Finding(
            "hover_only_text", "Text that only appears on hover", "medium", "access",
            f"{vp.hover_only_blocks} blocks ({vp.hover_only_chars} characters) are revealed "
            "by :hover. A touch screen has no hover, so on a phone that text does not "
            "exist. It is excluded from the typography measurements for the same reason.",
            "Show it, or reveal it on focus and tap as well as hover."))
    if vp and vp.text_on_image:
        out.append(Finding("text_on_image", f"{vp.text_on_image} text blocks sit on a background image",
                           "low", "comfort", "Contrast there cannot be measured statically and varies "
                           "with the image.", "Put a solid or scrim layer behind the text."))
    return out


def selection_of(config: dict | None):
    from .select import Selection
    if config and isinstance(config.get("_selection"), Selection):
        return config["_selection"]
    return Selection.from_config(config)


def score_page(pa, audience: str = "general", page_type: str | None = None,
               config: dict | None = None) -> tuple[Scores, list[Finding]]:
    page_type = page_type or classify_page(pa)
    sel = selection_of(config)
    ms = [m for m in apply_config(build_metrics(pa, audience, page_type), config)
          if sel.metric_ok(m.key, m.pillar)]

    findings = [f for f in discrete_findings(pa) if sel.finding_ok(f.key, f.pillar)]
    for m in ms:
        if m.severity in ("medium", "high", "critical"):
            findings.append(Finding(
                key=m.key, title=m.label, severity=m.severity, pillar=m.pillar,
                detail=f"{m.display} — target {m.target_display}."
                       + (f" {m.why}" if m.why else ""),
                fix=m.advice, evidence=m.evidence, score=m.score,
                params={"display": m.display, "target": m.target_display}))
    findings.sort(key=lambda x: (SEVERITY_ORDER.get(x.severity, 9), x.score if x.score is not None else 0))

    pil = pillar_scores(ms, findings)
    for k, v in pillar_weights(config).items():
        if k in pil:
            pil[k]["weight"] = float(v)
    total_w = sum(v["weight"] for v in pil.values()) or 1
    overall = round(sum(v["score"] * v["weight"] for v in pil.values()) / total_w, 1)
    n_crit = sum(1 for f in findings if f.severity == "critical")
    n_high = sum(1 for f in findings if f.severity == "high")
    if n_crit:
        overall = min(overall, CRITICAL_CAP - 1.5 * (n_crit - 1))
    elif n_high:
        overall = min(overall, HIGH_CAP - 1.0 * (n_high - 1))
    # A page with no text cannot be graded for reading. Saying so beats inventing a number.
    if not pil or (pa.structure is not None and pa.structure.word_count < 25
                   and pa.structure.text_chars < 200):
        scores = Scores(overall=None, grade="n/a", pillars=pil, metrics=ms)
        scores.page_type = page_type
        return scores, findings

    scores = Scores(overall=round(overall, 1), grade=grade_of(overall), pillars=pil, metrics=ms)
    scores.page_type = page_type
    return scores, findings
