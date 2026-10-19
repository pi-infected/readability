# Calibration

The target bands in `src/readability_audit/scoring.py` started as assertions from the literature:
Bringhurst's 45–75 character measure, WCAG 2.2's 4.5:1 and 7:1, Yoast's 30% transition
words, the 110–165 character meta description. Assertions are cheap. This directory is
the attempt to make them accountable.

## Method

`tools/calibrate.py` audits 13 pages, one per site, chosen because each is
either a typography authority, a public service written under a plain-language mandate, or
a publication whose reading experience is its product. It then reports, for every metric,
where those pages actually fall and what share of them our band accepts.

```
python tools/calibrate.py --out calibration/reference.json
```

The reference set:

- [nngroup](https://www.nngroup.com/articles/legibility-readability-comprehension/) — article, score 96.7
- [mdn](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/font-size) — doc, score 91.3
- [mozilla blog](https://blog.mozilla.org/en/) — landing, score 83.5
- [web.dev](https://web.dev/articles/font-best-practices) — doc, score 79.0
- [smashing](https://www.smashingmagazine.com/2020/07/css-techniques-legibility/) — doc, score 79.0
- [service-public.fr](https://www.service-public.gouv.fr/particuliers/vosdroits/F1970) — article, score 77.7
- [practicaltypography.com](https://practicaltypography.com/typography-in-ten-minutes.html) — article, score 77.5
- [a list apart](https://alistapart.com/article/on-web-typography/) — article, score 76.6
- [tailwind docs](https://tailwindcss.com/docs/font-size) — doc, score 76.0
- [stripe docs](https://docs.stripe.com/payments/quickstart) — index, score 74.4
- [css-tricks](https://css-tricks.com/typography-for-developers/) — doc, score 72.4
- [le monde](https://www.lemonde.fr/) — landing, score 67.6
- [wikipedia](https://en.wikipedia.org/wiki/Typography) — article, score 52.7

## The rule for moving a band

A band moves when it encodes a **convention** the reference set contradicts. A band stays
when it encodes a **standard we intend to hold**, even where the web does not meet it.
Contrast, alt-text coverage, heading order, uninformative link text, all-caps and
justification are in the second group — and all of them score 77–100% on the reference set
anyway, so holding the line costs nothing in false alarms.

## What moved, and on what evidence

| band | was | now | evidence |
|---|---|---|---|
| Transition words | 25–60% | 18–65% | reference median 23%: Yoast's 30% floor rejects most well-written pages |
| Passive voice | 0–10% | 0–14% | reference median 11%; "avoid the passive" is advice, not a limit |
| Sentences over the cap | 0–15% | 0–18% | reference median sat exactly on the old ceiling |
| Longest stretch without a heading | 0–300 w | 0–400 w | reference median 324 words |
| First screen covered by fixed chrome | 0–18% | 0–25% | reference median 20% |
| Meta description length | 110–165 ch | 70–200 ch, weight 0.5→0.3 | 15% of the reference set met the SEO convention; the spread is 0–398. It describes a search snippet, not how a page reads |
| Long-word load (general) | 6–16% | 6–18% | weaker evidence, n=6, moved conservatively |

## Two defects the reference set found

Calibration is not only for tuning bands. Two of these pages scored so far below their
reputation that the tool, not the page, was the suspect — and both times it was the tool:

- **`docs.stripe.com` scored 48.4 (E).** The extraction had already flagged itself
  (`coverage 4.58 — the content region looks inflated`). The page is a link hub: 310 words,
  43 links, 8-word paragraphs. The classifier typed it `doc` because the URL contains
  `/docs`, so a menu was judged as an article. Shape now beats the URL keyword, and a
  documentation hub is typed `index` like any other. **48.4 → 74.4.**
- **`lemonde.fr` was penalised for a 28-character measure.** Bringhurst's 50–80 is about
  running prose; a grid of teaser cards is legitimately narrower. `measure` now relaxes to
  32–80 on landing and index pages only.

**Wikipedia at 52.7 (E) is not a defect.** 55% of its images carry no alt text, 40% of its
sentences are passive, its mean sentence runs to 26.7 words and its LIX is 61. English
Wikipedia has measured at college reading level for years. Under `--audience academic` its
LIX metric goes from 23 to 88 and its clarity pillar from 21 to 50 — the profile does its
job, and what survives (missing alt text, a 1485-word stretch with no heading) is real.

## What did not move, and why

- **Line length 50–80 characters** — only 46% of the reference set sits inside, but the
  median is 62.5, mid-band. The misses are narrow card and sidebar columns at the p10 end,
  not wide prose. The literature here is strong and the metric is the one comfort lever
  that matters most.
- **Contrast (WCAG 7:1 ideal, APCA Lc 75)** — 100% of the reference set already clears it.
  A band nothing fails is not a lax band; it means failures are real.
- **Average sentence length, headings per 1000 words, small text** — medians all sit
  inside their bands; the misses are at the tails and are page types (card grids, link
  indexes) that the page-type profiles already handle.

## Current standing

| metric | n | median | p10–p90 | ideal | in ideal | in tolerable |
|---|---|---|---|---|---|---|
| Meta description length | 13 | 158 | 0–398 | 70–200 | 38% | 85% |
| Line length (characters per line) | 13 | 62.5 | 27.1–82.7 | 50–80 | 46% | 77% |
| Scannability | 13 | 0.716 | 0.4–0.903 | 0.7–1 | 54% | 92% |
| First screen covered by fixed chrome | 13 | 0.203 | 0–1 | 0–0.25 | 54% | 69% |
| Average sentence length | 11 | 17.2 | 7.5–20.1 | 12–20 | 55% | 82% |
| Headings per 1000 words | 11 | 6.6 | 0–46 | 3–15 | 55% | 64% |
| Average paragraph length | 13 | 32.8 | 5.7–50.5 | 30–80 | 62% | 69% |
| Link text share of the body | 13 | 0.088 | 0.031–0.623 | 0.01–0.12 | 62% | 69% |
| Text rendered below 16px | 13 | 0.021 | 0–0.626 | 0–0.12 | 62% | 69% |
| Reading difficulty (LIX) | 11 | 41.2 | 32.3–50.9 | 30–45 | 64% | 91% |
| Flesch Reading Ease | 11 | 59.1 | 23.6–69 | 55–85 | 64% | 91% |
| Sentences over the length cap | 11 | 0.155 | 0.024–0.235 | 0–0.18 | 64% | 91% |
| Passive voice | 11 | 0.121 | 0.003–0.246 | 0–0.14 | 64% | 91% |
| Longest stretch without a heading | 11 | 326 | 69–1769 | 0–400 | 64% | 73% |
| Long-word load | 6 | 0.163 | 0.096–0.265 | 0.06–0.18 | 67% | 100% |
| Title length | 13 | 45 | 16–79 | 25–65 | 69% | 92% |
| Boilerplate share of the page text | 13 | 0.272 | 0–0.74 | 0–0.45 | 69% | 85% |
| Body text size (desktop) | 13 | 16 | 14–20.4 | 16–21 | 69% | 100% |
| Line height | 13 | 1.64 | 1.2–1.85 | 1.45–1.75 | 69% | 92% |
| Line length on mobile | 13 | 37.4 | 17–47.6 | 32–60 | 69% | 92% |
| Layout shift while loading | 13 | 0.001 | 0–0.187 | 0–0.1 | 77% | 100% |
| Heading level skips | 13 | 0 | 0–1 | 0–0 | 77% | 100% |
| Acronyms never expanded | 13 | 2 | 0–10 | 0–4 | 77% | 100% |
| Text follows the browser's font size | 13 | 1 | 0–1 | 1–1 | 77% | 77% |
| Space between paragraphs | 9 | 0.69 | 0.43–5.57 | 0.5–1.4 | 78% | 89% |
| Transition words | 11 | 0.229 | 0.021–0.333 | 0.18–0.65 | 82% | 91% |
| Vocabulary diversity | 11 | 0.703 | 0.488–0.739 | 0.55–0.85 | 82% | 100% |
| Distinct type sizes | 12 | 6 | 2–9 | 2–8 | 83% | 100% |
| Body text size (mobile) | 13 | 16 | 14–20 | 16–20 | 85% | 100% |
| Images with alt text | 13 | 1 | 0.55–1 | 1–1 | 85% | 92% |
| Uninformative link text | 13 | 0 | 0–1 | 0–0 | 85% | 100% |
| Sentence length variation | 11 | 0.5 | 0.45–0.91 | 0.45–1.1 | 91% | 100% |
| Filler and marketing words | 11 | 0.005 | 0.002–0.008 | 0–0.01 | 91% | 100% |
| Paragraphs over 120 words | 13 | 0 | 0–0.029 | 0–0.1 | 92% | 100% |
| Nominalisations | 11 | 0.019 | 0.006–0.04 | 0–0.05 | 100% | 100% |
| Vocabulary rarity | 11 | 4.35 | 3.61–4.58 | 3.6–5.5 | 100% | 100% |
| Body text contrast (WCAG) | 13 | 16.13 | 9.96–21 | 7–21 | 100% | 100% |
| Perceptual contrast (APCA Lc) | 13 | 103.1 | 93.1–106 | 75–108 | 100% | 100% |
| Justified text without hyphenation | 13 | 0 | 0–0 | 0–0.02 | 100% | 100% |
| Text set in capitals | 13 | 0 | 0–0.007 | 0–0.03 | 100% | 100% |

## The other half of the evidence

This file asks whether the bands match careful practice. `DIFFICULTY.md` asks whether the
difficulty metrics measure difficulty at all, against 107 labelled easy/hard article pairs
in English and French. That is where the passive-voice metric lost half its weight.

## Limits of this evidence

Thirteen pages, mostly English, mostly technical publishing and documentation. It is a
reference set, not a sample: it says what deliberate typography looks like, not what the
web looks like. A band that the reference set clears at 100% could still be too lax for a
population it never contained. Two French pages is not French coverage. Growing this set,
and adding pages with known reading-difficulty labels rather than assumed quality, is the
next real improvement — and until it exists, every number above should be read as
"consistent with careful practice", not "validated".
