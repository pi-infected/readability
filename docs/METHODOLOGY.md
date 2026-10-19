# How readlens measures

The reasoning behind every number: which document is measured, where the targets come from, how a band becomes a score, and when the tool refuses to give one.

## What it measures

**Clarity** — the effort the sentences and vocabulary demand.
LIX (language-independent), Flesch reading ease with per-language coefficients
(Kandel–Moles for French, Fernández-Huerta for Spanish, Amstad for German, Flesch-Vacca
for Italian, Douma for Dutch), Flesch-Kincaid, Gunning Fog, SMOG, Coleman-Liau, ARI, RIX,
Dale-Chall, Wiener Sachtextformel. Beyond the formulas: sentence-length distribution and
rhythm, passive voice, nominalisation, transition words, adverb load, vocabulary rarity by
corpus frequency (Zipf), moving-average type-token ratio, hedging and marketing filler.

**Structure** — whether the page can be navigated and skimmed.
Heading tree and level skips, words per section, longest stretch with no heading,
paragraph-length distribution, list and table use, link-text quality, boilerplate share,
title and meta description, a composite scannability score.

**Comfort** — what the eye actually meets, read from the rendered page.
Body size, line height, measured line length (real line boxes, not an estimate), paragraph
spacing, justification (forgiven when hyphenation is on), capitals, type-scale consistency,
WCAG 2.2 contrast **and** APCA Lc contrast resolved through the real background stack,
layout shift, mobile overflow, dark-scheme support, web fonts that hide text while they
load, and how much of the first screen is eaten by sticky headers, cookie walls and chat
bubbles.

It also names the sentences to rewrite: the longest ones with the natural break point
marked, the passive constructions, the abstract nouns that want to be verbs.

**Accessibility** — whether everyone can read it.
`lang` declared vs language actually detected, alt-text coverage and quality, heading
order, uninformative link text, unexpanded acronyms, tables without headers, and whether
the text scales when a reader raises their browser's default font size.

## Which document gets measured

A page has two versions: the HTML the server sent, and the DOM after scripts have run. They
are not the same document, and measuring the text of one while measuring the typography of
the other produces a report that is confidently wrong. Before this was handled, a
client-rendered page audited as **"0 words"** while the comfort pillar happily reported the
line height and contrast of four paragraphs it claimed did not exist.

The served HTML wins when it actually carries the content — it is the cleaner document.
The rendered DOM is used only when the page builds its text in the browser. And the
question asked is not "is there more text after JavaScript", because a decorative animation
adds plenty: it is whether the article's own **opening paragraphs appear in the served
HTML** at all. Only then does the report say the content needs JavaScript.

Alongside that, machine output is not scored as writing. A terminal demo on a marketing
page put 10 KB of tool-call JSON and build logs into the prose metrics of the test site.
Blocks are classified by stopword and punctuation density — prose sits at 0.39–0.49
stopwords and ~0.00 punctuation, machine output at 0.17 and 0.13 — and the excluded blocks
are reported rather than silently dropped.

## Where the targets come from

Every band started as an assertion from the literature. `calibration/` is the attempt to
make them accountable: `tools/calibrate.py` measures a reference set of pages whose
typography is deliberate — Butterick, MDN, NN/g, Le Monde, service-public.fr, A List Apart
— and reports what share of them each band accepts.

A band moves when it encodes a **convention** the reference set contradicts (Yoast's 30%
transition words rejects most well-written prose; only 15% of the set met the 110–165
character meta-description rule). A band holds when it encodes a **standard worth holding**
even where the web fails it — contrast, alt text, heading order. Those score 77–100% on the
reference set anyway, so holding the line costs no false alarms.

`calibration/README.md` records what moved, what deliberately did not, and the limits of
the evidence — thirteen pages is a reference set, not a sample.

The bands are one half. The other is whether the difficulty metrics measure difficulty at
all, and that is testable against labelled data: Simple English Wikipedia and Vikidia are
the same encyclopaedias written for a younger reader, so an article pair is two texts about
the same thing at two known levels. Over **107 pairs in English and French**
(`tools/validate_difficulty.py`, results in `calibration/DIFFICULTY.md`) the classic
formulas rank the harder text correctly 95–98% of the time, p < 0.0001.

One metric failed: **passive voice ranks correctly only 61% of the time**, and not
significantly in either language alone. It carries half the weight it used to, and the
report now presents it as a style signal rather than a difficulty one. Nine of those pairs
are frozen into the test suite, so the ordinal property is re-checked offline on every
commit.

## Scoring

Every metric declares a target band, a tolerable band, a weight and the advice to give
when it misses. A metric scores 100 inside its target, 60 at the edge of tolerable, and 0
one span beyond. Pillars are weighted means minus a penalty for each concrete defect; a
page with an unfixed critical defect cannot be graded above 79.

The site score is 70% mean page score, 20% worst page score and 10% consistency — a reader
lands on one page, not on the average, and pays for every re-adjustment between pages.

Targets adapt to the page: a link index, a landing page, documentation, a legal page and
an article are held to different standards (`--audience general|technical|academic|children`
shifts them further). Pages with less than 150 words of running prose are not scored for
language at all, and say so.

## Output

One crawl produces one set of artifacts. `--out DIR` writes `readlens.json`,
`readlens.csv`, and an HTML and PDF report **per report language**, all rendered from the
same measurement pass — two languages can never describe two different crawls. Every page
gets a detail section by default (`--detail N` limits it), and the report opens with its
own coverage line: pages analysed, scored, measured in a browser, detailed below, plus any
that had no readable content or were unreachable.
`--json`, `--html`, `--pdf`, `--csv` write to explicit paths. `--report-lang fr` produces
the whole report in French — labels, advice, findings, units and formula interpretations,
not just the headings. `--screenshots` embeds a desktop screenshot per page.
`--fail-under 70` exits 2 when the site score is below the threshold, for CI.
`readlens diff before.json after.json` reports the score delta, which findings were resolved,
which are new, and which pages moved — that is the loop for getting better over time.

The JSON is the single source and is self-describing. Besides every measured value, the
band it was judged against, the score it earned and the evidence behind each finding, it
carries:

- `coverage` — what was discovered, analysed, scored, rendered, and what was not
- `scoring` — the pillars, their weights, and how a band becomes a score
- `methodology` — every metric documented **once**, with its bands per page type, rather
  than repeated inside all 23 pages
- `validation` — what backs the numbers: the reference-set calibration, the 107 labelled
  difficulty pairs and the per-metric accuracy, the cross-check against textstat, and
  which band moved on which evidence
- `artifacts` — every file the run wrote, including itself

The reports are a rendering of that file, not a separate truth.

## Speed and memory

The browser pass dominates the run, so pages render concurrently in one browser — N tabs,
not N browsers. Playwright's sync objects are bound to the thread that created them, so
thread-parallelism would mean a Chromium process per worker; the async API keeps one.

Measured on this repo (8 pages of tokenade.net, PSS so shared mappings are not
double-counted):

| `--concurrency` | wall | peak browser memory |
|---|---|---|
| 1 | 31.3 s | 309 MB |
| 4 | 14.5 s | 579 MB |
| 8 | 11.4 s | 723 MB |

Memory is base plus marginal — about 300 MB for the browser and ~90 MB per extra
concurrent page — so `--concurrency` is clamped to what `MemAvailable` actually allows,
keeping 800 MB free, and it is reduced automatically rather than swapping the machine. If
memory tightens mid-run the pool waits instead of opening another tab. The run prints the
concurrency it settled on and why. Past 4 the gain flattens: the crawl becomes
network-bound, not CPU-bound.

## When it declines to score

The tool may refuse to give a number. It must never invent one.

- **A page with no readable text** — an image-only page, a `<frameset>`, a shell whose
  script never ran — scores `n/a` rather than a middling number, is named in the report,
  and is left out of the site average instead of being averaged in as a zero.
- **A script the measures cannot read** — Arabic, Cyrillic, Chinese, Japanese — is measured
  for structure, comfort and accessibility, and the clarity pillar is absent with a finding
  that says why. Word- and syllable-based formulas need word boundaries and a syllable
  model; asserting a LIX for Chinese would be a number, not a measurement.
- **A document that will not parse** returns an error naming the cause. An empty body says
  so rather than reporting the status code, which would send someone hunting a server
  error that did not happen.

`tests/test_robustness.py` holds one case per failure that was found this way. Each of them
either crashed or produced a confident wrong number before it was fixed — including a
stopword-based filter that deleted every word of Arabic prose because Arabic contains no
English stopwords.

One known limit stays: libxml2 drops content nested deeper than about 256 elements. No real
page reaches that, and the tool reports "no readable content" rather than a score when it
happens.

## Limits, stated plainly

Readability formulas were calibrated on print prose and school grades. They measure
sentence and word length; they do not know whether an argument is clear. Passive-voice and
nominalisation detection is rule-based: it misses cases and over-reports others. Contrast
is computed on resolved colours, so text over an image or a gradient is reported
separately rather than scored. Syllable counting uses CMUdict for English (`syllapy`) and a
silent-e-aware heuristic for French, validated against a gold list in the test suite;
both are 90%+ accurate, not perfect.

Treat the score as a prioritised list of things to look at, not as a verdict.
