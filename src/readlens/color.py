"""Colour parsing, WCAG 2.x contrast ratio and APCA (WCAG 3 draft) lightness contrast."""
from __future__ import annotations

import re

RGB_RE = re.compile(r"rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.%]+))?\s*\)")
HEX_RE = re.compile(r"^#([0-9a-fA-F]{3,8})$")

NAMED = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0), "green": (0, 128, 0),
    "blue": (0, 0, 255), "gray": (128, 128, 128), "grey": (128, 128, 128),
    "transparent": (0, 0, 0), "silver": (192, 192, 192), "navy": (0, 0, 128),
}


def parse(css: str | None) -> tuple[float, float, float, float] | None:
    """Return (r, g, b, alpha) with r/g/b in 0-255, or None if unparseable."""
    if not css:
        return None
    s = css.strip().lower()
    if s in ("transparent", "rgba(0, 0, 0, 0)"):
        return (0.0, 0.0, 0.0, 0.0)
    m = RGB_RE.match(s)
    if m:
        a = m.group(4)
        alpha = 1.0
        if a is not None:
            alpha = float(a[:-1]) / 100 if a.endswith("%") else float(a)
        return (float(m.group(1)), float(m.group(2)), float(m.group(3)), alpha)
    m = HEX_RE.match(s)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return (r, g, b, a)
    if s in NAMED:
        r, g, b = NAMED[s]
        return (r, g, b, 0.0 if s == "transparent" else 1.0)
    return None


def blend(fg: tuple, bg: tuple) -> tuple:
    """Alpha-composite fg over opaque bg."""
    a = fg[3]
    return (fg[0] * a + bg[0] * (1 - a), fg[1] * a + bg[1] * (1 - a),
            fg[2] * a + bg[2] * (1 - a), 1.0)


def _lin(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple) -> float:
    return 0.2126 * _lin(rgb[0]) + 0.7152 * _lin(rgb[1]) + 0.0722 * _lin(rgb[2])


def contrast_ratio(fg: tuple, bg: tuple) -> float:
    """WCAG 2.x contrast ratio, 1.0-21.0."""
    if fg[3] < 1.0:
        fg = blend(fg, bg)
    l1, l2 = luminance(fg), luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# --- APCA (Accessible Perceptual Contrast Algorithm), W3 constants ----------
_TRC = 2.4
_NORM_BG, _NORM_TXT, _REV_TXT, _REV_BG = 0.56, 0.57, 0.62, 0.65
_BLK_THRS, _BLK_CLMP = 0.022, 1.414
_SCALE, _LO_OFFSET, _LO_CLIP, _DELTA_Y_MIN = 1.14, 0.027, 0.1, 0.0005


def _apca_y(rgb: tuple) -> float:
    y = (0.2126729 * (rgb[0] / 255) ** _TRC + 0.7151522 * (rgb[1] / 255) ** _TRC
         + 0.0721750 * (rgb[2] / 255) ** _TRC)
    return y + (_BLK_THRS - y) ** _BLK_CLMP if y < _BLK_THRS else y


def apca(fg: tuple, bg: tuple) -> float:
    """APCA lightness contrast Lc. |Lc| >= 75 for body text, 60 for large, 45 for headlines."""
    if fg[3] < 1.0:
        fg = blend(fg, bg)
    ytxt, ybg = _apca_y(fg), _apca_y(bg)
    if abs(ybg - ytxt) < _DELTA_Y_MIN:
        return 0.0
    if ybg > ytxt:                                   # dark text on light background
        sapc = (ybg ** _NORM_BG - ytxt ** _NORM_TXT) * _SCALE
        lc = 0.0 if sapc < _LO_CLIP else (sapc - _LO_OFFSET) * 100
    else:                                            # light text on dark background
        sapc = (ybg ** _REV_BG - ytxt ** _REV_TXT) * _SCALE
        lc = 0.0 if sapc > -_LO_CLIP else (sapc + _LO_OFFSET) * 100
    return round(lc, 1)


def wcag_level(ratio: float, font_px: float, bold: bool = False) -> str:
    """AA/AAA judgement for a given text size. Large text = 18.66px bold or 24px."""
    large = font_px >= 24 or (bold and font_px >= 18.66)
    if large:
        return "AAA" if ratio >= 4.5 else ("AA" if ratio >= 3.0 else "fail")
    return "AAA" if ratio >= 7.0 else ("AA" if ratio >= 4.5 else "fail")


# APCA's own lookup makes the requirement fall as size rises AND as weight rises. A
# three-bucket approximation made 14px and 16px demand the same contrast, which hid
# genuinely thin 14px text. Interpolated, and monotonic in both directions.
_APCA_BY_SIZE = [(12, 100.0), (14, 100.0), (16, 90.0), (18, 84.0), (21, 78.0),
                 (24, 75.0), (28, 68.0), (32, 63.0), (36, 60.0), (48, 55.0)]
_APCA_BY_WEIGHT = {300: 12.0, 400: 0.0, 500: -4.0, 600: -8.0, 700: -12.0, 800: -15.0}


def apca_min_lc(font_px: float, weight: int = 400) -> float:
    """Minimum Lc APCA asks for at this size and weight."""
    pts = _APCA_BY_SIZE
    if font_px <= pts[0][0]:
        base = pts[0][1]
    elif font_px >= pts[-1][0]:
        base = pts[-1][1]
    else:
        base = pts[-1][1]
        for (s0, l0), (s1, l1) in zip(pts, pts[1:]):
            if s0 <= font_px <= s1:
                base = l0 + (l1 - l0) * (font_px - s0) / (s1 - s0)
                break
    keys = sorted(_APCA_BY_WEIGHT)
    w = min(keys, key=lambda k: abs(k - weight))
    return round(max(45.0, min(108.0, base + _APCA_BY_WEIGHT[w])), 1)
