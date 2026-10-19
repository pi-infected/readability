"""Accessibility of the reading experience (the subset that changes whether text is readable)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..extract import Doc
from ..lang import LangPack
from ..text import ACRONYM_RE, words

VALID_LANG = re.compile(r"^[a-z]{2,3}(-[a-zA-Z0-9]{2,8})*$")


@dataclass
class A11yReport:
    lang_declared: str | None = None
    lang_detected: str | None = None
    lang_confidence: float = 0.0
    lang_valid: bool = False
    lang_mismatch: bool = False
    n_images: int = 0
    images_missing_alt: int = 0
    images_decorative: int = 0
    alt_coverage: float = 1.0
    long_alts: int = 0
    filename_alts: int = 0
    has_h1: bool = False
    multiple_h1: bool = False
    heading_skips: int = 0
    has_main_landmark: bool = False
    has_skip_link: bool = False
    title_present: bool = False
    meta_description_present: bool = False
    weak_links: int = 0
    ambiguous_links: int = 0
    unexplained_acronyms: list = field(default_factory=list)
    uppercase_blocks: int = 0
    rem_scaling: bool | None = None
    reduced_motion_css: bool | None = None
    animated_elements: int = 0
    tables_without_headers: int = 0

    def as_dict(self) -> dict:
        return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


IMG_FILE = re.compile(r"\.(png|jpe?g|gif|webp|svg|avif)$", re.I)


def analyse(doc: Doc, lp: LangPack, structure_report, detected: tuple[str, float],
            probe: dict | None = None, declared: str | None = None) -> A11yReport:
    r = A11yReport()
    # The served declaration is the one that counts: a crawler, a reader mode and anyone
    # whose script did not run never see the value hydration writes later.
    r.lang_declared = declared if declared is not None else doc.lang
    r.lang_detected, r.lang_confidence = detected
    r.lang_valid = bool(r.lang_declared and VALID_LANG.match(r.lang_declared))
    if r.lang_declared and r.lang_detected and r.lang_confidence > 0.35:
        r.lang_mismatch = r.lang_declared.split("-")[0].lower() != r.lang_detected

    imgs = doc.images
    r.n_images = len(imgs)
    r.images_missing_alt = sum(1 for i in imgs if not i.has_alt)
    r.images_decorative = sum(1 for i in imgs if i.decorative)
    r.alt_coverage = 1.0 - (r.images_missing_alt / len(imgs)) if imgs else 1.0
    r.long_alts = sum(1 for i in imgs if i.alt and len(i.alt) > 150)
    r.filename_alts = sum(1 for i in imgs if i.alt and IMG_FILE.search(i.alt.strip()))

    r.has_h1 = structure_report.h1_count >= 1
    r.multiple_h1 = structure_report.h1_count > 1
    r.heading_skips = len(structure_report.level_skips)
    r.has_main_landmark = bool(doc.landmarks.get("main"))
    r.has_skip_link = bool(doc.landmarks.get("skip_link"))
    r.title_present = bool(doc.title.strip())
    r.meta_description_present = bool(doc.meta_description)
    r.weak_links = sum(x["count"] for x in structure_report.weak_link_texts)
    r.ambiguous_links = len(structure_report.ambiguous_link_texts)

    text = doc.prose_text
    seen = {}
    for a in ACRONYM_RE.findall(text):
        if a.lower() in lp.stopwords or len(a) < 3:
            continue
        seen[a] = seen.get(a, 0) + 1
    explained = set()
    for a in seen:
        if re.search(rf"\({re.escape(a)}\)|{re.escape(a)}\s*\(", text):
            explained.add(a)
    if doc.abbr:
        explained |= set(list(seen)[:doc.abbr])
    r.unexplained_acronyms = [{"acronym": a, "count": n} for a, n in
                              sorted(seen.items(), key=lambda kv: -kv[1]) if a not in explained][:10]

    if probe:
        c = probe.get("counts", {})
        r.rem_scaling = probe.get("remScaling")
        r.reduced_motion_css = c.get("reducedMotionCSS")
        r.animated_elements = c.get("animated", 0)
        r.tables_without_headers = max(0, c.get("tables", 0) - c.get("tablesWithHeaders", 0))
    else:
        r.tables_without_headers = 0
    return r
