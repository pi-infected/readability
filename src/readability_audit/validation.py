"""What backs the numbers this tool prints, frozen so the JSON can carry its own provenance.

These figures are produced by `tools/calibrate.py` and `tools/validate_difficulty.py` and
recorded in `calibration/`. They describe the tool, not the site being audited.
"""

PROVENANCE = {
    "bands": {
        "method": "Target bands measured against a reference set of pages whose typography "
                  "is deliberate (typography authorities, plain-language public services, "
                  "publications whose reading experience is their product).",
        "reference_pages": 13,
        "rule": "A band moves when it encodes a convention the reference set contradicts. "
                "A band holds when it encodes a standard worth holding even where the web "
                "fails it (contrast, alt text, heading order).",
        "moved_on_evidence": [
            {"band": "connectives", "from": [0.25, 0.60], "to": [0.18, 0.65],
             "evidence": "reference median 23%: Yoast's 30% floor rejects most well-written prose"},
            {"band": "passive", "from": [0, 0.10], "to": [0, 0.14],
             "evidence": "reference median 11%"},
            {"band": "long_sentences", "from": [0, 0.15], "to": [0, 0.18],
             "evidence": "reference median sat on the old ceiling"},
            {"band": "unbroken_run", "from": [0, 300], "to": [0, 400],
             "evidence": "reference median 324 words"},
            {"band": "occlusion", "from": [0, 0.18], "to": [0, 0.25],
             "evidence": "reference median 20%"},
            {"band": "meta_description", "from": [110, 165], "to": [70, 200],
             "evidence": "15% of the reference set met the SEO convention; spread 0-398"},
        ],
        "artifact": "calibration/reference.json",
        "doc": "calibration/README.md",
    },
    "difficulty": {
        "method": "Ordinal test against labelled ground truth: Simple English Wikipedia and "
                  "Vikidia are the same encyclopaedias written for a younger reader, so an "
                  "article pair is two texts on one topic at two known levels. Two-sided "
                  "sign test against the null that the metric is a coin flip.",
        "pairs": {"total": 107, "en": 57, "fr": 50},
        "ranks_the_harder_text_correctly": {
            "flesch": 0.98, "gunning_fog": 0.98, "flesch_kincaid": 0.97,
            "coleman_liau": 0.97, "ari": 0.97, "lix": 0.95, "rix": 0.95,
            "pct_polysyllabic": 0.95, "pct_long_words": 0.93, "word_rarity_zipf": 0.93,
            "nominalization": 0.90, "avg_sentence_len": 0.86, "lexical_density": 0.85,
            "vocab_diversity": 0.72, "passive_ratio": 0.61,
        },
        "acted_on": "Passive voice ranks correctly only 61% of the time and not "
                    "significantly in either language alone (en p=0.10, fr p=0.25). Its "
                    "weight was halved and it is reported as a style signal, not a "
                    "difficulty one.",
        "artifact": "calibration/difficulty.json",
        "doc": "calibration/DIFFICULTY.md",
    },
    "implementation": {
        "method": "Every formula is cross-checked against textstat, an independent "
                  "implementation, on texts of increasing difficulty.",
        "exact_agreement": ["lix", "rix", "gunning_fog", "dale_chall"],
        "documented_divergence": {
            "flesch, flesch_kincaid, smog":
                "syllables come from CMUdict via syllapy; textstat uses a letter heuristic",
            "coleman_liau, ari":
                "letters are counted inside word tokens; textstat counts non-space characters",
        },
        "test": "tests/test_crossvalidation.py",
    },
}
