// Injected into the page. Returns everything the typography/comfort metrics need.
() => {
  const px = (v) => { const n = parseFloat(v); return isNaN(n) ? 0 : n; };

  // Chromium reports author colours verbatim (oklch, color(), lab...). Paint one
  // pixel and read it back so everything downstream is plain sRGB rgba().
  const _cvs = document.createElement('canvas'); _cvs.width = _cvs.height = 1;
  const _ctx = _cvs.getContext('2d', { willReadFrequently: true });
  const _cc = new Map();
  const toRGBA = (c) => {
    if (!c) return 'rgba(0, 0, 0, 0)';
    if (/^rgba?\(\s*[\d.]+\s*,/.test(c)) return c;
    if (_cc.has(c)) return _cc.get(c);
    let out = c;
    try {
      _ctx.clearRect(0, 0, 1, 1);
      _ctx.fillStyle = '#000';
      _ctx.fillStyle = c;
      _ctx.fillRect(0, 0, 1, 1);
      const d = _ctx.getImageData(0, 0, 1, 1).data;
      out = `rgba(${d[0]}, ${d[1]}, ${d[2]}, ${(d[3] / 255).toFixed(3)})`;
    } catch (e) {}
    _cc.set(c, out);
    return out;
  };
  // An element can report itself visible while an ancestor hides it: opacity:0 on a
  // wrapper, or max-height:0 with overflow:hidden on a hover-reveal panel. Counting that
  // text presented a page's hover descriptions as if they were its body copy.
  const hiddenAncestor = (el) => {
    let cur = el, hops = 0;
    while (cur && cur.nodeType === 1 && hops++ < 12) {
      const cs = getComputedStyle(cur);
      if (cs.display === 'none' || cs.visibility === 'hidden' || px(cs.opacity) === 0) return 'hidden';
      const clipped = cs.overflow === 'hidden' || cs.overflowY === 'hidden';
      if (clipped && cur.clientHeight === 0 && cur.scrollHeight > 0) return 'collapsed';
      cur = cur.parentElement;
    }
    return null;
  };
  const vis = (el, cs) => !(cs.display === 'none' || cs.visibility === 'hidden' ||
                            px(cs.opacity) === 0 || (el.offsetWidth === 0 && el.offsetHeight === 0)
                            || hiddenAncestor(el));

  // `rgb(0, 0, 0)` ends in ", 0)" but its last component is the blue channel, not an
  // alpha. Reading it as alpha made every pure-black background look transparent, so the
  // walk fell through to the body and reported white text on white.
  const alphaOf = (c) => {
    const m = String(c).match(/^rgba?\(([^)]+)\)/);
    if (!m) return 1;
    const parts = m[1].split(',').map(s => s.trim());
    return parts.length >= 4 ? (parseFloat(parts[3]) || 0) : 1;
  };

  function bgChain(el) {
    let cur = el, image = null;
    const layers = [];
    while (cur && cur.nodeType === 1) {
      const cs = getComputedStyle(cur);
      if (cs.backgroundImage && cs.backgroundImage !== 'none' && !image) image = cs.backgroundImage.slice(0, 120);
      const c = cs.backgroundColor;
      const rc = toRGBA(c);
      const a = rc && rc !== 'transparent' ? alphaOf(rc) : 0;
      if (a > 0.001) {
        layers.push(rc);
        if (a >= 0.999) break;      // opaque: nothing behind it can show through
      }
      cur = cur.parentElement;
    }
    return { layers, image };
  }

  function lineCount(el) {
    try {
      const r = document.createRange();
      r.selectNodeContents(el);
      const rects = Array.from(r.getClientRects()).filter(x => x.width > 0 && x.height > 0);
      const tops = new Set(rects.map(x => Math.round(x.top / 2)));
      return Math.max(1, tops.size);
    } catch (e) { return 1; }
  }

  const root = document.querySelector('main, [role="main"], article') || document.body;
  const SEL = 'p,li,h1,h2,h3,h4,h5,h6,blockquote,td,th,dd,dt,figcaption,summary';
  const nodes = Array.from(root.querySelectorAll(SEL));
  const elements = [];
  const sizes = {}, families = {}, lhs = {};

  for (const el of nodes) {
    if (el.querySelector(SEL)) continue;               // container, not a leaf text block
    const txt = (el.textContent || '').replace(/\s+/g, ' ').trim();
    if (txt.length < 2) continue;
    const cs = getComputedStyle(el);
    if (!vis(el, cs)) continue;
    const rect = el.getBoundingClientRect();
    const bg = bgChain(el);
    const lines = lineCount(el);
    const fontPx = px(cs.fontSize);
    const lhPx = cs.lineHeight === 'normal' ? fontPx * 1.2 : px(cs.lineHeight);
    const links = Array.from(el.querySelectorAll('a')).slice(0, 6).map(a => {
      const acs = getComputedStyle(a);
      return { color: toRGBA(acs.color), decoration: acs.textDecorationLine, weight: acs.fontWeight,
               text: (a.textContent || '').trim().slice(0, 60) };
    });
    const key = fontPx.toFixed(1);
    sizes[key] = (sizes[key] || 0) + txt.length;
    const fam = (cs.fontFamily || '').split(',')[0].replace(/["']/g, '').trim();
    families[fam] = (families[fam] || 0) + txt.length;
    const lhr = fontPx ? +(lhPx / fontPx).toFixed(2) : 0;
    lhs[lhr] = (lhs[lhr] || 0) + txt.length;

    elements.push({
      tag: el.tagName.toLowerCase(),
      text: txt.slice(0, 90),
      cls: (el.className && el.className.toString ? el.className.toString() : '').slice(0, 80),
      chars: txt.length,
      words: txt.split(/\s+/).length,
      fontPx, weight: parseInt(cs.fontWeight) || 400,
      family: fam,
      generic: /serif/i.test(cs.fontFamily) && !/sans/i.test(cs.fontFamily) ? 'serif'
             : /mono/i.test(cs.fontFamily) ? 'mono' : 'sans',
      lineHeightPx: lhPx, lineHeightRatio: lhr,
      letterSpacing: cs.letterSpacing === 'normal' ? 0 : px(cs.letterSpacing),
      wordSpacing: cs.wordSpacing === 'normal' ? 0 : px(cs.wordSpacing),
      color: toRGBA(cs.color),
      bgLayers: bg.layers, bgImage: bg.image,
      align: cs.textAlign, transform: cs.textTransform,
      hyphens: cs.hyphens, textWrap: cs.textWrap || cs.textWrapStyle || '',
      widthPx: Math.round(rect.width), heightPx: Math.round(rect.height),
      top: Math.round(rect.top + window.scrollY),
      lines, charsPerLine: +(txt.length / lines).toFixed(1),
      marginTop: px(cs.marginTop), marginBottom: px(cs.marginBottom),
      links,
      opacity: px(cs.opacity),
    });
  }

  // Vertical rhythm: gap between consecutive paragraphs vs their line height.
  const ps = elements.filter(e => e.tag === 'p');
  let gaps = [];
  for (let i = 1; i < nodes.length; i++) {
    const a = nodes[i - 1], b = nodes[i];
    if (a.tagName !== 'P' || b.tagName !== 'P' || a.parentElement !== b.parentElement) continue;
    const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const lh = px(getComputedStyle(b).lineHeight) || px(getComputedStyle(b).fontSize) * 1.2;
    const g = rb.top - ra.bottom;
    if (g >= 0 && g < 200 && lh) gaps.push(g / lh);
  }

  // Text a reader can only reach by hovering does not exist on a touch screen.
  const hoverBases = [];
  try {
    for (const sheet of Array.from(document.styleSheets)) {
      let rules; try { rules = Array.from(sheet.cssRules || []); } catch (e) { continue; }
      // A CSSStyleRule also exposes `cssRules` (empty, but an object, so truthy) now that
      // CSS nesting exists. Read the selector first, then descend only if there is
      // something to descend into.
      const walk = (rs) => {
        for (const r of rs) {
          const sel = r.selectorText;
          if (sel && sel.indexOf(':hover') !== -1) {
            for (const one of sel.split(',')) {
              const base = one.split(':hover')[0].trim();
              if (base && base.length > 1 && hoverBases.indexOf(base) === -1) hoverBases.push(base);
            }
          }
          if (r.cssRules && r.cssRules.length) walk(Array.from(r.cssRules));
        }
      };
      walk(rules);
    }
  } catch (e) {}
  let hoverOnly = 0, hoverOnlyChars = 0;
  try {
    for (const el of Array.from(root.querySelectorAll(SEL))) {
      if (el.querySelector(SEL)) continue;
      const txt = (el.textContent || '').trim();
      if (txt.length < 20) continue;
      const cs = getComputedStyle(el);
      if (!hiddenAncestor(el) && vis(el, cs)) continue;
      // Ask the stylesheets, not the class names: any :hover rule whose non-hover part
      // matches this element or an ancestor is what reveals it. Class-name sniffing only
      // caught Tailwind.
      let revealed = false;
      for (const base of hoverBases) {
        try {
          if (el.matches(base) || el.closest(base)) { revealed = true; break; }
        } catch (e) {}
      }
      if (revealed) { hoverOnly++; hoverOnlyChars += txt.length; }
    }
  } catch (e) {}

  // What actually covers the first screen: sticky headers, cookie walls, chat bubbles.
  const overlays = [];
  const GRID = 40;
  const covered = new Set();
  const vw = window.innerWidth, vh = window.innerHeight;
  for (const el of Array.from(document.body.querySelectorAll('*'))) {
    const cs = getComputedStyle(el);
    if (cs.position !== 'fixed' && cs.position !== 'sticky') continue;
    if (!vis(el, cs)) continue;
    if (el.closest('[aria-hidden="true"]')) continue;
    const r = el.getBoundingClientRect();
    const w = Math.min(r.right, vw) - Math.max(r.left, 0);
    const h = Math.min(r.bottom, vh) - Math.max(r.top, 0);
    if (w <= 0 || h <= 0) continue;
    const area = (w * h) / (vw * vh);
    if (area < 0.005) continue;
    if (overlays.some(o => o.el && el.contains(o.el))) continue;
    overlays.push({ el, tag: el.tagName.toLowerCase(),
      cls: (el.className && el.className.toString ? el.className.toString() : '').slice(0, 60),
      position: cs.position, area: +area.toFixed(4), height: Math.round(h),
      text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 70) });
    for (let gx = 0; gx < GRID; gx++) {
      for (let gy = 0; gy < GRID; gy++) {
        const x = (gx + 0.5) * vw / GRID, y = (gy + 0.5) * vh / GRID;
        if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) covered.add(gx + ',' + gy);
      }
    }
  }
  overlays.forEach(o => { delete o.el; });
  const occlusion = covered.size / (GRID * GRID);

  // How much of the page's own text is readable on the first screen.
  let firstScreenChars = 0;
  for (const el of nodes) {
    const r = el.getBoundingClientRect();
    if (r.top < vh && r.bottom > 0) firstScreenChars += (el.textContent || '').trim().length;
  }

  // Zoom robustness: does body text scale when the user raises their default font size?
  // Text sized in px ignores that preference; rem/em based text follows it.
  let remScaling = null;
  try {
    const probeEl = ps.length ? root.querySelector('p') : document.body;
    const before = parseFloat(getComputedStyle(probeEl).fontSize);
    const prev = document.documentElement.style.fontSize;
    document.documentElement.style.fontSize = '24px';
    const after = parseFloat(getComputedStyle(probeEl).fontSize);
    document.documentElement.style.fontSize = prev;
    remScaling = after > before * 1.15;
  } catch (e) {}

  const bodyCS = getComputedStyle(document.body);
  const htmlCS = getComputedStyle(document.documentElement);

  return {
    url: location.href,
    viewport: { width: window.innerWidth, height: window.innerHeight, dpr: devicePixelRatio },
    scrollWidth: document.scrollingElement.scrollWidth,
    scrollHeight: document.scrollingElement.scrollHeight,
    overflowX: document.scrollingElement.scrollWidth > window.innerWidth + 2,
    rootFontPx: px(htmlCS.fontSize),
    bodyBg: toRGBA(bodyCS.backgroundColor),
    bodyColor: toRGBA(bodyCS.color),
    colorScheme: htmlCS.colorScheme || '',
    mainWidth: Math.round(root.getBoundingClientRect().width),
    elements,
    sizeHistogram: sizes,
    familyHistogram: families,
    lineHeightHistogram: lhs,
    paragraphGaps: gaps,
    remScaling,
    hoverOnly, hoverOnlyChars,
    overlays: overlays.sort((a, b) => b.area - a.area).slice(0, 6),
    occlusion: +occlusion.toFixed(4),
    firstScreenChars,
    fonts: (() => {
      const info = { status: 'n/a', count: 0, blocking: 0, local_only: 0, families: [] };
      // A @font-face whose src is only local() downloads nothing and can hide nothing.
      // next/font emits one per family ("Roboto Flex Fallback") carrying size-adjust
      // metrics; counting those made this fire on every Next.js site ever built.
      const srcByFamily = new Map();
      try {
        for (const sheet of Array.from(document.styleSheets)) {
          let rules; try { rules = Array.from(sheet.cssRules || []); } catch (e) { continue; }
          for (const r of rules) {
            if (r.constructor && r.constructor.name === 'CSSFontFaceRule') {
              const fam = (r.style.getPropertyValue('font-family') || '').replace(/["']/g, '').trim();
              const src = r.style.getPropertyValue('src') || '';
              const prev = srcByFamily.get(fam) || [];
              prev.push(src);
              srcByFamily.set(fam, prev);
            }
          }
        }
      } catch (e) {}
      const downloads = (fam) => {
        const srcs = srcByFamily.get(fam);
        if (!srcs || !srcs.length) return !/fallback$/i.test(fam);   // unknown: judge by name
        return srcs.some(s => /url\(/i.test(s));
      };
      try {
        info.status = document.fonts.status;
        info.count = document.fonts.size;
        document.fonts.forEach(f => {
          const fam = (f.family || '').replace(/["']/g, '').trim();
          const dl = downloads(fam);
          info.families.push({ family: fam, display: f.display || 'auto', weight: f.weight,
                               downloads: dl });
          if (!dl) { info.local_only++; return; }
          if (!f.display || f.display === 'auto' || f.display === 'block') info.blocking++;
        });
      } catch (e) {}
      info.families = info.families.slice(0, 12);
      return info;
    })(),
    metrics: window.__readlens || {},
    counts: {
      images: document.images.length,
      imagesNoAlt: Array.from(document.images).filter(i => !i.hasAttribute('alt')).length,
      iframes: document.querySelectorAll('iframe').length,
      videos: document.querySelectorAll('video').length,
      animated: document.querySelectorAll('[class*=animate],[class*=marquee]').length,
      reducedMotionCSS: Array.from(document.styleSheets).some(sh => {
        try { return Array.from(sh.cssRules || []).some(r => (r.conditionText || '').includes('prefers-reduced-motion')); }
        catch (e) { return false; }
      }),
      tablesWithHeaders: Array.from(document.querySelectorAll('table')).filter(t => t.querySelector('th')).length,
      tables: document.querySelectorAll('table').length,
      abbr: document.querySelectorAll('abbr').length,
      langAttr: document.documentElement.getAttribute('lang') || '',
    },
  };
}
