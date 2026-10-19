"""Ordinal validation against labelled ground truth, offline.

Simple English Wikipedia and Vikidia are the same encyclopaedias written for a younger
reader, so an article pair on one topic is two texts about the same thing at two known
difficulty levels. `tools/validate_difficulty.py` runs this over 107 live pairs; the
fixture here freezes nine of them so the property is checked on every commit.

The claim under test is ordinal only: the harder text must land on the harder side. No
absolute calibration is asserted.
"""
import json
from pathlib import Path

import pytest

from readability_audit.lang import pack
from readability_audit.metrics import lexical, syntax
from readability_audit.metrics.formulas import compute, count
from readability_audit.text import sentences

PAIRS = json.loads((Path(__file__).parent / "fixtures" / "difficulty_pairs.json")
                   .read_text(encoding="utf8"))

# metric -> (extractor, +1 when a higher value means harder)
METRICS = {
    "lix": (lambda f, s, l: f["lix"].value, +1),
    "flesch": (lambda f, s, l: f["flesch_reading_ease"].value, -1),
    "flesch_kincaid": (lambda f, s, l: f["flesch_kincaid_grade"].value, +1),
    "gunning_fog": (lambda f, s, l: f["gunning_fog"].value, +1),
    "coleman_liau": (lambda f, s, l: f["coleman_liau"].value, +1),
    "rix": (lambda f, s, l: f["rix"].value, +1),
    "pct_polysyllabic": (lambda f, s, l: l.pct_polysyllabic, +1),
    "pct_long_words": (lambda f, s, l: l.pct_long_words, +1),
    "word_rarity_zipf": (lambda f, s, l: l.mean_zipf, -1),
    "avg_sentence_len": (lambda f, s, l: s.mean_len, +1),
}


def measure(text: str, code: str):
    lp = pack(code)
    sents = [s for p in text.split("\n") if len(p.strip()) > 30 for s in sentences(p, lp)]
    f = compute(count(sents, lp), lp, text)
    return f, syntax.analyse(sents, lp), lexical.analyse(text, lp)


@pytest.fixture(scope="module")
def measured():
    return [(p["lang"], p["topic"], measure(p["easy"], p["lang"]), measure(p["hard"], p["lang"]))
            for p in PAIRS]


def test_fixture_is_present_and_bilingual():
    langs = {p["lang"] for p in PAIRS}
    assert len(PAIRS) >= 8 and {"en", "fr"} <= langs


@pytest.mark.parametrize("key", list(METRICS))
def test_metric_ranks_the_harder_text_higher(measured, key):
    get, direction = METRICS[key]
    hits = total = 0
    misses = []
    for lang, topic, easy, hard in measured:
        try:
            e, h = get(*easy), get(*hard)
        except KeyError:
            continue
        if e is None or h is None or e == h:
            continue
        total += 1
        if (h - e) * direction > 0:
            hits += 1
        else:
            misses.append(f"{lang}/{topic} ({e:.2f} -> {h:.2f})")
    assert total >= 6, f"{key}: only {total} usable pairs"
    # The live run over 107 pairs puts every metric here at 86-98%. On nine pairs one
    # miss is 11%, so the floor is set to allow one and catch a real regression.
    assert hits / total >= 0.77, f"{key}: {hits}/{total} correct. Missed: {misses}"


def test_the_whole_battery_agrees_on_most_pairs(measured):
    """Per pair, most metrics should agree — a single metric can slip, a pair should not."""
    for lang, topic, easy, hard in measured:
        agree = 0
        for key, (get, direction) in METRICS.items():
            try:
                e, h = get(*easy), get(*hard)
            except KeyError:
                continue
            if e is not None and h is not None and (h - e) * direction > 0:
                agree += 1
        assert agree >= len(METRICS) * 0.6, f"{lang}/{topic}: only {agree}/{len(METRICS)}"
