"""Choose what to measure: `--only` / `--skip` over pillars, groups and metric keys.

Measuring less is also measuring faster. The browser pass is most of an audit's wall
clock, so a selection that needs no rendered metric skips the browser entirely, and one
that needs nothing from the phone viewport renders the desktop only.
"""
from __future__ import annotations

from dataclasses import dataclass

# key -> (pillar, label, needs). needs: "" (served HTML is enough), "desktop", "mobile".
METRICS = {
    "lix": ("clarity", "Reading difficulty (LIX)", ""),
    "flesch": ("clarity", "Flesch reading ease (per-language)", ""),
    "asl": ("clarity", "Average sentence length", ""),
    "long_sentences": ("clarity", "Sentences over the length cap", ""),
    "rhythm": ("clarity", "Sentence length variation", ""),
    "passive": ("clarity", "Passive voice", ""),
    "nominalization": ("clarity", "Nominalisations", ""),
    "connectives": ("clarity", "Transition words", ""),
    "polysyllabic": ("clarity", "Long-word load", ""),
    "word_rarity": ("clarity", "Vocabulary rarity (Zipf)", ""),
    "hedging": ("clarity", "Filler and marketing words", ""),
    "diversity": ("clarity", "Vocabulary diversity (MATTR)", ""),
    "headings_density": ("structure", "Headings per 1000 words", ""),
    "unbroken_run": ("structure", "Longest stretch without a heading", ""),
    "paragraph_length": ("structure", "Average paragraph length", ""),
    "long_paragraphs": ("structure", "Paragraphs over 120 words", ""),
    "link_density": ("structure", "Link text share of the body", ""),
    "scannability": ("structure", "Scannability", ""),
    "title_length": ("structure", "Title length", ""),
    "meta_description": ("structure", "Meta description length", ""),
    "boilerplate": ("structure", "Boilerplate share of the page text", ""),
    "font_size": ("comfort", "Body text size (desktop)", "desktop"),
    "small_text": ("comfort", "Text rendered below 16px", "desktop"),
    "line_height": ("comfort", "Line height", "desktop"),
    "measure": ("comfort", "Line length (characters per line)", "desktop"),
    "paragraph_gap": ("comfort", "Space between paragraphs", "desktop"),
    "contrast": ("comfort", "Body text contrast (WCAG 2.2)", "desktop"),
    "apca": ("comfort", "Perceptual contrast (APCA Lc)", "desktop"),
    "justified": ("comfort", "Justified text without hyphenation", "desktop"),
    "uppercase": ("comfort", "Text set in capitals", "desktop"),
    "type_sizes": ("comfort", "Distinct type sizes", "desktop"),
    "occlusion": ("comfort", "First screen covered by fixed chrome", "desktop"),
    "cls": ("comfort", "Layout shift while loading", "desktop"),
    "mobile_font": ("comfort", "Body text size (mobile)", "mobile"),
    "mobile_measure": ("comfort", "Line length on mobile", "mobile"),
    "alt_coverage": ("access", "Images with alt text", ""),
    "heading_order": ("access", "Heading level skips", ""),
    "weak_links": ("access", "Uninformative link text", ""),
    "acronyms": ("access", "Acronyms never expanded", ""),
    "rem_scaling": ("access", "Text follows the browser's font size", "desktop"),
}

# Findings that are not a metric but belong to one, so `--only contrast` keeps
# `contrast_fail`. Anything else follows its pillar.
FINDING_OWNER = {
    "contrast_fail": "contrast", "apca_fail": "apca", "overflow_mobile": "mobile_measure",
    "no_mobile_layout": "mobile_font",
    "overflow_desktop": "measure", "alt_missing": "alt_coverage",
    "alt_filename": "alt_coverage", "ambiguous_links": "weak_links",
    "no_meta_desc": "meta_description", "font_display": "font_size",
    "no_dark_mode": "contrast",
}

PILLARS = ("clarity", "structure", "comfort", "access")

GROUPS = {
    "readability": ["lix", "flesch", "asl", "long_sentences", "polysyllabic"],
    "style": ["passive", "nominalization", "connectives", "hedging", "rhythm",
              "word_rarity", "diversity"],
    "contrast": ["contrast", "apca"],
    "typography": ["font_size", "small_text", "line_height", "measure", "paragraph_gap",
                   "justified", "uppercase", "type_sizes"],
    "layout": ["occlusion", "cls", "measure", "mobile_measure"],
    "mobile": ["mobile_font", "mobile_measure"],
    "headings": ["headings_density", "unbroken_run", "heading_order"],
    "links": ["link_density", "weak_links"],
    "seo": ["title_length", "meta_description"],
    "images": ["alt_coverage"],
}
# `contrast` is both a group and a metric; as a selector it means the group.
GROUP_HELP = {
    "readability": "the classic formulas: LIX, Flesch, sentence length, long words",
    "style": "passive voice, nominalisations, filler, rhythm, vocabulary",
    "contrast": "WCAG 2.2 ratio + APCA Lc on the real background",
    "typography": "size, line height, line length, spacing, capitals, type scale",
    "layout": "sticky chrome over the first screen, layout shift, line length",
    "mobile": "body size and line length at 390px",
    "headings": "heading density, longest unbroken run, level skips",
    "links": "link density and uninformative link text",
    "seo": "title and meta description length",
    "images": "alt-text coverage",
}


class SelectionError(ValueError):
    pass


def _expand(tokens: list[str]) -> tuple[set[str], set[str]]:
    pillars, metrics = set(), set()
    for raw in tokens:
        for t in (x.strip().lower() for x in raw.split(",")):
            if not t:
                continue
            if t in ("access", "accessibility", "a11y"):
                pillars.add("access")
            elif t in PILLARS:
                pillars.add(t)
            elif t in GROUPS:
                metrics.update(GROUPS[t])
            elif t in METRICS:
                metrics.add(t)
            else:
                raise SelectionError(
                    f"unknown selector {t!r}. Pillars: {', '.join(PILLARS)}. "
                    f"Groups: {', '.join(GROUPS)}. Metrics: `readability metrics`.")
    return pillars, metrics


@dataclass
class Selection:
    only_pillars: frozenset = frozenset()
    only_metrics: frozenset = frozenset()
    skip_pillars: frozenset = frozenset()
    skip_metrics: frozenset = frozenset()

    @classmethod
    def parse(cls, only=None, skip=None) -> "Selection":
        op, om = _expand(list(only or []))
        sp, sm = _expand(list(skip or []))
        return cls(frozenset(op), frozenset(om), frozenset(sp), frozenset(sm))

    @classmethod
    def from_config(cls, config: dict | None) -> "Selection":
        c = config or {}
        return cls.parse(c.get("only"), c.get("skip"))

    @property
    def everything(self) -> bool:
        return not (self.only_pillars or self.only_metrics or self.skip_pillars
                    or self.skip_metrics)

    def metric_ok(self, key: str, pillar: str) -> bool:
        if pillar in self.skip_pillars or key in self.skip_metrics:
            return False
        if self.only_pillars or self.only_metrics:
            return pillar in self.only_pillars or key in self.only_metrics
        return True

    def finding_ok(self, key: str, pillar: str) -> bool:
        owner = FINDING_OWNER.get(key, key)
        if owner in METRICS:
            return self.metric_ok(owner, METRICS[owner][0])
        if pillar in self.skip_pillars:
            return False
        if self.only_pillars or self.only_metrics:
            return pillar in self.only_pillars
        return True

    def _needs(self, where: str) -> bool:
        return any(n == where and self.metric_ok(k, p) for k, (p, _, n) in METRICS.items())

    @property
    def needs_mobile(self) -> bool:
        return self._needs("mobile")

    @property
    def needs_render(self) -> bool:
        return self.needs_mobile or self._needs("desktop")

    @property
    def check_dark(self) -> bool:
        return self.finding_ok("no_dark_mode", "comfort")

    def viewports(self, all_viewports: dict) -> dict:
        if self.needs_mobile:
            return dict(all_viewports)
        return {k: v for k, v in all_viewports.items() if k != "mobile"}

    def as_config(self) -> dict:
        return {"only": sorted(self.only_pillars | self.only_metrics),
                "skip": sorted(self.skip_pillars | self.skip_metrics)}
