"""Cross-validation against textstat, an independent implementation.

Where a formula is fully specified by counts we both derive the same way (words,
sentences, long words, the Dale-Chall list), we must agree to the decimal. Where the
formula depends on a definition each library is free to choose — how a syllable is
counted, whether "characters" includes punctuation — we allow a documented gap and say
which choice is ours.
"""
import pytest

from readability_audit.lang import pack
from readability_audit.metrics.formulas import compute, count
from readability_audit.text import sentences

textstat = pytest.importorskip("textstat")

EASY = "The cat sat on the mat. It was a sunny day. The dog ran fast. Birds sang in the tree."
MID = ("Readability is not one thing. A sentence can be short and still be hard, because the "
       "words in it are rare. A sentence can be long and still be easy, because it is built "
       "from words a reader meets every day. Most formulas measure only length, which is why "
       "they agree with each other and disagree with readers.")
HARD = ("Notwithstanding the aforementioned considerations, the implementation of comprehensive "
        "infrastructural modifications necessitates a systematic evaluation of organisational "
        "readiness, particularly where interdependencies between legacy subsystems remain "
        "insufficiently documented and the attendant remediation costs are indeterminate.")
TEXTS = [EASY, MID, HARD]

# key, textstat function name, tolerance, why the tolerance is not zero
CASES = [
    ("lix", "lix", 0.1, "same definition, same counts"),
    ("rix", "rix", 0.1, "same definition, same counts"),
    ("gunning_fog", "gunning_fog", 0.2, "complex-word rule matches"),
    ("dale_chall", "dale_chall_readability_score", 0.1, "same 3000-word list"),
    ("flesch_reading_ease", "flesch_reading_ease", 8.0,
     "syllables: we use CMUdict via syllapy, textstat uses a letter heuristic"),
    ("flesch_kincaid_grade", "flesch_kincaid_grade", 1.5, "same syllable difference"),
    ("smog", "smog_index", 1.0, "same syllable difference, via the polysyllable count"),
    ("coleman_liau", "coleman_liau_index", 1.0,
     "letters: we count letters inside word tokens, textstat counts non-space characters"),
    ("ari", "automated_readability_index", 1.5, "same character-definition difference"),
]


@pytest.mark.parametrize("text", TEXTS, ids=["easy", "mid", "hard"])
@pytest.mark.parametrize("key,fn_name,tol,why", CASES,
                         ids=[c[0] for c in CASES])
def test_agrees_with_textstat(text, key, fn_name, tol, why):
    lp = pack("en")
    textstat.set_lang("en")
    ours = compute(count(sentences(text, lp), lp), lp, text)
    if key not in ours:
        pytest.skip(f"{key} not produced for this text")
    ref = getattr(textstat, fn_name)(text)
    assert ours[key].value == pytest.approx(ref, abs=tol), why


def test_french_flesch_matches_textstat_fr():
    lp = pack("fr")
    textstat.set_lang("fr")
    t = ("Le chat est sur le tapis. Il fait beau. Le chien court vite dans le jardin. "
         "Les oiseaux chantent dans l'arbre et personne ne se demande pourquoi.")
    ours = compute(count(sentences(t, lp), lp), lp, t)["flesch_reading_ease"]
    assert ours.value == pytest.approx(textstat.flesch_reading_ease(t), abs=8.0)
    assert "Kandel" in ours.name


def test_ordering_is_preserved_across_all_formulas():
    """Whatever the absolute calibration, harder text must score harder. Every time."""
    lp = pack("en")
    f = [compute(count(sentences(t, lp), lp), lp, t) for t in TEXTS]
    for key in ("lix", "rix", "gunning_fog", "flesch_kincaid_grade", "coleman_liau", "ari"):
        vals = [x[key].value for x in f if key in x]
        assert vals == sorted(vals), f"{key} does not increase with difficulty: {vals}"
    ease = [x["flesch_reading_ease"].value for x in f]
    assert ease == sorted(ease, reverse=True), f"reading ease does not fall: {ease}"
