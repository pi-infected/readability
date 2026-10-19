# Difficulty validation

`calibration/README.md` asks whether the target bands match careful practice. This asks a
harder question: **do the difficulty metrics measure difficulty at all?**

## Ground truth

Simple English Wikipedia and Vikidia are the same encyclopaedias written for a younger
reader. An article pair on one topic is therefore two texts about exactly the same thing at
two known difficulty levels — labelled data, free, in English *and* French.

```
python tools/validate_difficulty.py --out calibration/difficulty.json --limit 60
```

The test is **ordinal only**: for each pair, does the metric put the harder text on the
harder side? No absolute calibration is claimed or needed. Significance is a two-sided sign
test against the null that the metric is a coin flip.

Both sides of a pair are always measured on the same unit — lead against lead, or full
article against full article, never one against the other. 107 pairs
survived (57 English,
50 French);
13 were skipped and the reason for each is recorded in the JSON.

## Results — English (57 pairs)

| metric | n | ranks correctly | median delta | p |
|---|---|---|---|---|
| flesch | 57 | 100% | 25.2 | 0.0000 |
| gunning_fog | 57 | 100% | 5.5 | 0.0000 |
| lix | 57 | 98% | 17.1 | 0.0000 |
| flesch_kincaid | 57 | 98% | 5.4 | 0.0000 |
| coleman_liau | 57 | 98% | 3.9 | 0.0000 |
| ari | 57 | 98% | 6 | 0.0000 |
| rix | 57 | 98% | 3.59 | 0.0000 |
| pct_polysyllabic | 57 | 98% | 0.0723 | 0.0000 |
| pct_long_words | 57 | 98% | 0.0893 | 0.0000 |
| avg_sentence_len | 57 | 93% | 7.6271 | 0.0000 |
| pct_long_sentences | 57 | 93% | 0.2 | 0.0000 |
| word_rarity_zipf | 57 | 91% | 0.26 | 0.0000 |
| lexical_density | 57 | 91% | 0.0677 | 0.0000 |
| nominalization | 57 | 86% | 0.0138 | 0.0000 |
| pct_rare_words | 57 | 84% | 0.0206 | 0.0000 |
| vocab_diversity | 57 | 70% | 0.0331 | 0.0032 |
| passive_ratio | 55 | 62% | 0.0458 | **0.1048** |

## Results — French (50 pairs)

| metric | n | ranks correctly | median delta | p |
|---|---|---|---|---|
| flesch | 50 | 96% | 15.85 | 0.0000 |
| flesch_kincaid | 50 | 96% | 3.45 | 0.0000 |
| gunning_fog | 50 | 96% | 4.05 | 0.0000 |
| coleman_liau | 49 | 96% | 2.3 | 0.0000 |
| ari | 48 | 96% | 4.05 | 0.0000 |
| word_rarity_zipf | 48 | 96% | 0.265 | 0.0000 |
| nominalization | 50 | 94% | 0.0186 | 0.0000 |
| lix | 50 | 92% | 10.7 | 0.0000 |
| rix | 50 | 92% | 2.865 | 0.0000 |
| pct_polysyllabic | 50 | 92% | 0.0457 | 0.0000 |
| pct_rare_words | 50 | 92% | 0.0198 | 0.0000 |
| pct_long_words | 50 | 88% | 0.0432 | 0.0000 |
| pct_long_sentences | 50 | 82% | 0.1217 | 0.0000 |
| avg_sentence_len | 50 | 78% | 4.4376 | 0.0001 |
| lexical_density | 50 | 78% | 0.0318 | 0.0001 |
| vocab_diversity | 49 | 73% | 0.017 | 0.0014 |
| passive_ratio | 49 | 59% | 0.0417 | **0.2529** |

## Results — pooled (107 pairs)

| metric | n | ranks correctly | median delta | p |
|---|---|---|---|---|
| flesch | 107 | 98% | 20.3 | 0.0000 |
| gunning_fog | 107 | 98% | 4.8 | 0.0000 |
| flesch_kincaid | 107 | 97% | 4.8 | 0.0000 |
| coleman_liau | 106 | 97% | 3 | 0.0000 |
| ari | 105 | 97% | 5.3 | 0.0000 |
| lix | 107 | 95% | 13.3 | 0.0000 |
| rix | 107 | 95% | 3.15 | 0.0000 |
| pct_polysyllabic | 107 | 95% | 0.0566 | 0.0000 |
| pct_long_words | 107 | 93% | 0.0674 | 0.0000 |
| word_rarity_zipf | 105 | 93% | 0.26 | 0.0000 |
| nominalization | 107 | 90% | 0.0168 | 0.0000 |
| pct_long_sentences | 107 | 88% | 0.1667 | 0.0000 |
| pct_rare_words | 107 | 88% | 0.0199 | 0.0000 |
| avg_sentence_len | 107 | 86% | 6.7788 | 0.0000 |
| lexical_density | 107 | 85% | 0.0412 | 0.0000 |
| vocab_diversity | 106 | 72% | 0.0291 | 0.0000 |
| passive_ratio | 104 | 61% | 0.0429 | 0.0390 |

## What this changed

**Passive voice lost half its weight.** It ranks the harder text correctly 61% of the time
overall, and not significantly in either language on its own (English p=0.10, French
p=0.25). On this evidence it is a plain-language *style* concern, not a difficulty
predictor — so its weight went 1.0 → 0.5 and the report now says as much in the metric's
own explanation rather than implying it measures difficulty.

Everything else earns its place: the classic formulas rank 95–98% of pairs correctly with
p < 0.0001, in both languages, and so do the word-level measures the formulas are built on.

## The near miss worth recording

An earlier run had 12 French pairs. On those twelve, French sentence-length metrics looked
dead: average sentence length ranked 58% of pairs correctly (p=0.77) and "sentences over
the cap" ranked exactly 50% (p=1.00, a coin flip). The reading was tidy and plausible —
Vikidia simplifies vocabulary, not sentence structure — and the next step was going to be
rebalancing the French clarity weights away from sentence length.

At 50 French pairs both recovered: 78% (p=0.0001) and 82% (p<0.0001). The finding was
sampling noise wearing the costume of a discovery. Nothing was changed on twelve pairs, and
nothing should be. The passive-voice result is acted on because it is stable in *both*
languages independently and across both sample sizes.

## Kept honest on every commit

`tests/test_difficulty_ordering.py` freezes nine of these pairs into
`tests/fixtures/difficulty_pairs.json` and re-checks the ordinal property offline, so a
change that quietly breaks a metric's direction fails the test suite instead of shipping.

## Limits

Wikipedia-family prose is one register. A metric that ranks encyclopaedia pairs correctly
has not been shown to rank marketing copy, legal text or documentation correctly. Vikidia
targets 8–13 year olds and Simple English targets learners, which are different audiences
in the same direction. And ordinal accuracy says the ranking is right; it says nothing
about whether a LIX of 45 is the right threshold for anybody.
