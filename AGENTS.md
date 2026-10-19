# readlens — notes for AI agents

## Using the tool
See [`skills/readlens/SKILL.md`](skills/readlens/SKILL.md): which command to pick, the JSON
shape, exit codes, and the measure → fix → re-measure loop. Copy that directory into your
agent's skills folder (Claude Code: `~/.claude/skills/`) to load it automatically.

Fast rules:
- Always pass `--format json` and the narrowest `--only` that answers the question.
- `readlens metrics --format json` lists every valid selector.
- Selections without `comfort` metrics never start a browser.
- `readlens urls SITE` before a big `audit`, to check the page list.

## Working on the code
- Python ≥ 3.10, sources in `src/readlens/`, tests in `tests/`.
- `pip install -e . pytest && python -m pytest -q` (`-m "not render"` without Chromium).
- Metrics are declared in `scoring.build_metrics`; their catalogue (pillar, label, whether
  they need the browser) lives in `select.METRICS` and a test keeps the two in sync.
- Browser probe: `src/readlens/probe.js` (runs in the page), driven by `render.py`.
- Targets are data: change a band only with evidence (`calibration/`, `tools/calibrate.py`).
