---
name: readability
description: Audit a web page or site for readability and reading comfort with the readability CLI — text contrast (WCAG 2.2 + APCA), font size, line height, line length, mobile layout, writing clarity (LIX, Flesch, passive voice), structure and accessibility. Use when asked to check contrast, typography, legibility, readability, or "is this page easy to read", or to verify a CSS/content change actually improved it.
---

# readability

`readability` measures pages in headless Chromium and returns findings with evidence and a fix.

## Pick the narrowest command

- One page, one concern: `readability page URL --only contrast --format json`
- Several pages: `readability page URL1 URL2 --only typography --skip mobile --format json`
- Writing only (no browser, ~1s/page): `--only clarity` or `--only clarity,structure`
- A draft file: `readability text draft.md --only readability`
- A quick site overview: `readability audit SITE --per-section 1 --pages 30 --format json`
  (one page of each template)
- A site: `readability urls SITE --pages 100` first, then
  `readability audit SITE --pages N --include RE --exclude RE --only ... --format json`
- Every selector: `readability metrics --format json`

Selectors: pillars `clarity structure comfort access`; groups `readability style contrast
typography layout mobile headings links seo images`; or single metric keys.
Only the `comfort` pillar and `rem_scaling` need the browser; anything else skips it.

## Read the result

JSON on stdout, progress on stderr. Key fields of a page: `score` (null = not gradable),
`grade`, `pillars`, `metrics[]` (`key`, `value`, `display`, `target_display`, `score`, `severity`),
`findings[]` (`key`, `severity` critical>high>medium>low>info, `detail`, `fix`,
`evidence[]` with text, `color`, `background`, `ratio`, `apca_abs`, `apca_required`,
`font_px`). Exit codes: 0 ok, 1 fetch/parse error (page), 2 below `--fail-under`, 64 bad selector.

## Working loop

1. Measure narrowly, report the top findings with their evidence.
2. Fix the CSS or text the evidence points to.
3. Re-run the same command (add `--no-cache` if the content changed) and compare.
   For sites: `readability audit ... --json before.json`, then `readability diff before.json after.json`.

Do not present the score as a verdict: lead with findings and evidence. Respect robots.txt;
use `--ignore-robots` only on sites the user owns.
