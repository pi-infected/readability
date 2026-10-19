<p align="center">
  <img src="docs/assets/hero.svg" alt="readlens — a lens sweeps a web page and flags thin contrast (APCA Lc 66, needs 92.5), small text and line length, while the terminal prints the same findings." width="900" />
</p>

<h1 align="center">readlens</h1>

<p align="center">
  <b>Audit how readable — and how comfortable to read — a website really is.<br/>
  Contrast, typography, line length, clarity, structure, accessibility. Measured in a real browser.</b>
</p>

<p align="center">
  <a href="#license"><img src="https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue" alt="license" /></a>
  <img src="https://img.shields.io/badge/python-%E2%89%A53.10-3776ab?logo=python&logoColor=white" alt="python ≥ 3.10" />
  <a href="https://github.com/pi-infected/readability/actions"><img src="https://github.com/pi-infected/readability/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <img src="https://img.shields.io/badge/WCAG%202.2%20%2B%20APCA-contrast-ffd103" alt="WCAG 2.2 + APCA" />
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#measure-only-what-you-need">Recipes</a> ·
  <a href="#commands">Commands</a> ·
  <a href="#for-ai-agents">For AI agents</a> ·
  <a href="docs/METHODOLOGY.md">Methodology</a>
</p>

Most readability tools stop at a Flesch score. A Flesch score cannot see that the body
text is 12px, that the contrast is 2.6:1, that a line runs to 140 characters, or that the
page declares `lang="en"` while the prose is French.

**readlens** opens your pages in headless Chromium at desktop and mobile widths, reads the
real computed styles, pulls the actual content out of each page, and tells you **what to
fix first** — with the offending text, its colours and the target it missed.

```text
$ readlens page https://tokenade.net/fr --only contrast

  96.0/100 A  landing · fr · 356 words · 1.7 min

  100.0 Body text contrast (WCAG)                   15.05:1  target 7-21 ratio
  100.0 Perceptual contrast (APCA Lc)               Lc 91.7  target 75-108 Lc

  medium   3 text blocks are perceptually thin
           They pass WCAG 2 but fall short of the APCA level for their size and weight.
           → Raise the contrast or the font size for these blocks.
           · "Une installation, zéro config. Tokenade compacte les sorties…"
             color rgb(107, 100, 87) · background rgb(238, 232, 220) · ratio 4.8 · apca_abs 66.0 · apca_required 92.5 · font_px 15.5
```

## Why readlens

- **Measured, not guessed.** Font size, line height and characters per line come from real
  line boxes in a real browser. Contrast is resolved through the actual background stack,
  in **WCAG 2.2** ratio *and* **APCA Lc** (the WCAG 3 draft), per size and weight.
- **Language-aware.** LIX, Flesch with per-language coefficients (Kandel–Moles for French,
  Fernández-Huerta for Spanish, Amstad for German…), Gunning Fog, SMOG, Coleman-Liau, plus
  passive voice, nominalisations, filler words, vocabulary rarity.
- **Pick exactly what you measure.** `--only contrast`, `--skip mobile`,
  `--only clarity,structure`… A selection that needs no browser skips it: a text-only audit
  of 8 pages runs in about **4 seconds**.
- **Honest.** A page with no readable text scores `n/a`, not a made-up number. Terminal
  demos and JSON blobs are not scored as prose. Targets are calibrated against a reference
  set of well-typeset sites and validated on 107 labelled difficulty pairs
  ([methodology](docs/METHODOLOGY.md)).
- **Agent-ready.** Every command has `--format json`, stable exit codes, and the JSON carries
  the evidence, the target and the fix. A ready-made [agent skill](skills/readlens/SKILL.md)
  is included.

## Install

```sh
git clone https://github.com/pi-infected/readability
cd readability
pip install -e .                 # or: uv pip install -e .
pip install playwright && playwright install chromium   # once, for the rendered pass
readlens metrics                 # check it works: lists everything you can measure
```

Without Playwright, readlens still runs every text, structure and accessibility metric —
only the rendered *comfort* metrics (contrast, typography, layout) need the browser.

## Measure only what you need

A full audit renders every page twice (desktop + mobile) and runs ~40 metrics. Most of the
time you want one thing. Select it, and readlens does only the work that thing needs.

| You want | Command | Browser |
| --- | --- | --- |
| Contrast of one page (WCAG + APCA) | `readlens page URL --only contrast` | desktop only |
| Typography without the phone pass | `readlens page URL --only typography --skip mobile` | desktop only |
| Is my mobile layout readable? | `readlens page URL --only mobile` | both |
| How hard is my writing? | `readlens page URL --only clarity` | none |
| Just the classic formulas | `readlens text draft.md --only readability` | none |
| Whole blog, text only, fast | `readlens audit https://site.com --include '/blog/' --pages 100 --only clarity,structure` | none |
| Everything except SEO nits | `readlens audit https://site.com --skip seo` | both |
| Check a few exact pages | `readlens page URL1 URL2 URL3` | both |
| Accessibility, minus the browser | `readlens page URL --only access --skip rem_scaling` | none |

Selectors are **pillars**, **groups** or single **metrics**, comma-separated and repeatable.
`readlens metrics` prints them all.

- **Pillars:** `clarity` · `structure` · `comfort` · `access`
- **Groups:** `readability` · `style` · `contrast` · `typography` · `layout` · `mobile` ·
  `headings` · `links` · `seo` · `images`
- **Metrics:** `lix`, `flesch`, `asl`, `passive`, `font_size`, `line_height`, `measure`,
  `contrast`, `apca`, `occlusion`, `cls`, `alt_coverage`, `rem_scaling`… (40 in all)

### Choose which pages

```sh
readlens urls https://site.com --pages 200              # dry run: what would be audited
readlens audit https://site.com --pages 50 \
  --include '/en/' --exclude '/tag/' --exclude '/page/[0-9]+'   # repeatable regexes
readlens audit https://site.com --url-list https://site.com/a https://site.com/b
readlens audit https://site.com --no-sitemap --depth 1  # links from the home page only
```

Discovery reads `sitemap.xml` first, then crawls same-origin links. `robots.txt` is
respected, responses are cached on disk, duplicates (redirects, canonicals, identical
bodies) are analysed once.

## Commands

| Command | What it does |
| --- | --- |
| `readlens page URL…` | Analyse one or more pages, no crawl. Prints metrics, findings and evidence. |
| `readlens audit URL` | Crawl a site, score every page, write JSON / CSV / HTML / PDF reports. |
| `readlens text FILE` | Analyse a local Markdown, text or HTML file (`-` for stdin). JSON out. |
| `readlens urls URL` | List the pages an audit would visit, without analysing them. |
| `readlens metrics` | List every pillar, group and metric you can pass to `--only` / `--skip`. |
| `readlens diff A.json B.json` | What changed between two audits: score delta, resolved and new findings. |
| `readlens benchmark URL URL…` | Audit several sites the same way and rank them. |

### Options

```text
selection   --only SEL          measure only these pillars / groups / metrics
            --skip SEL          leave these out
            --no-render         never start the browser
pages       --pages N           page budget (audit 10, urls 50)
            --include RE        URL must match one of these   (repeatable)
            --exclude RE        URL must not match any        (repeatable)
            --url-list A B C    exactly these URLs, no crawl
            --depth N           link-crawl depth (default 2)
            --no-sitemap        crawl links only
            --delay S           politeness delay (default 0.4s)
            --ignore-robots     only for sites you own
targets     --audience A        general · technical · academic · children
            --lang fr           force the language of the linguistic metrics
            --config FILE       TOML/JSON: bands, weights, only/skip (see below)
output      --format json       machine-readable result on stdout
            --out DIR           readlens.{json,csv,html,pdf} in DIR
            --json/--csv/--html/--pdf PATH
            --report-lang en fr reports in one or more languages, one crawl
            --screenshots       desktop screenshot per page in the report
            --evidence N        evidence lines per finding (page, default 2)
            --fail-under N      exit 2 below this score (CI gate)
speed       --concurrency N     pages rendered at once, clamped to free RAM
            --no-cache          always refetch
```

### Reports

```sh
readlens audit https://site.com --pages 30 --out report/ --report-lang en fr --screenshots
```

writes `readlens.json` (the single source of truth: every value, its target, its evidence,
the methodology and coverage), `readlens.csv` (one row per page), and an HTML + PDF report
per language — all from the same crawl. `readlens diff before.json after.json` closes the
loop when you ship a fix.

### Tune the targets

The bands are data, not code ([`examples/readlens.toml`](examples/readlens.toml)):

```toml
only = ["comfort", "access"]   # same selectors as --only / --skip
skip = ["seo"]
disable = ["meta_description"]

[bands.measure]                # our column is deliberately narrow
ideal = [45, 72]
tolerable = [35, 88]

[weights]
contrast = 2.5

[pillar_weights]
comfort = 0.35
```

## For AI agents

readlens is built to be driven by coding agents (Claude Code, Codex, Cursor, Copilot…):

- **`--format json`** on every command: result on **stdout**, progress on **stderr**.
- **Narrow first.** `--only` keeps the payload small and the run fast; `readlens metrics
  --format json` lists every valid selector.
- **Exit codes:** `0` ok · `1` (`page`) a URL could not be fetched or parsed · `2` below
  `--fail-under` · `64` bad selector.
- Every finding carries `key`, `severity`, `pillar`, `detail`, `fix` and `evidence`
  (the text, its colours, size, ratio, APCA level), so the agent can go straight to the
  CSS or the sentence.

```sh
readlens page https://site.com/pricing --only contrast,typography --format json \
  | jq '.findings[] | {key, severity, fix, evidence: .evidence[:2]}'
```

Install the skill so your agent knows when and how to use it:

```sh
mkdir -p ~/.claude/skills && cp -r skills/readlens ~/.claude/skills/   # Claude Code
```

Other agents: point them at [`AGENTS.md`](AGENTS.md).

## What it measures

**Clarity** — LIX, Flesch (per-language), Flesch-Kincaid, Gunning Fog, SMOG, Coleman-Liau,
ARI, RIX, Dale-Chall, Wiener Sachtextformel; sentence length and rhythm, passive voice,
nominalisations, transition words, long-word load, vocabulary rarity (Zipf), diversity,
filler and marketing words. It also names the sentences to rewrite.

**Structure** — heading density, longest stretch without a heading, paragraph length,
link density, scannability, boilerplate share, title and meta description.

**Comfort** (rendered) — body size on desktop and mobile, text below 16px, line height,
characters per line, paragraph spacing, justification, capitals, type-scale consistency,
WCAG 2.2 and APCA contrast, sticky chrome covering the first screen, layout shift,
horizontal overflow, dark-scheme support, web fonts that hide text while loading.

**Accessibility** — declared vs detected language, alt-text coverage and quality, heading
order, uninformative link text, unexpanded acronyms, tables without headers, and whether
text scales with the reader's default font size.

How each number is produced, calibrated and validated: [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Built on

[Playwright](https://playwright.dev) (rendering) · [trafilatura](https://github.com/adbar/trafilatura)
and [readability-lxml](https://github.com/buriy/python-readability) (content extraction) ·
[textstat](https://github.com/textstat/textstat) (cross-check) · [pyphen](https://github.com/Kozea/Pyphen)
and [syllapy](https://github.com/mholtzscher/syllapy) (syllables) · [WeasyPrint](https://weasyprint.org) (PDF) ·
WCAG 2.2 contrast and [APCA](https://github.com/Myndex/apca-w3) implemented from the specifications.

## Development

```sh
pip install -e . pytest && python -m pytest -q          # browser tests need Chromium
python -m pytest -q -m "not render"                     # offline subset
```

Issues and pull requests welcome.

## License

Licensed under either of [Apache License, Version 2.0](LICENSE-APACHE) or
[MIT license](LICENSE-MIT), at your option (`MIT OR Apache-2.0`).
