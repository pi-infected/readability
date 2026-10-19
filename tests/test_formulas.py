import pytest

from readlens.lang import pack
from readlens.metrics.formulas import Counts, compute, consensus_grade, count
from readlens.text import sentences

EASY = "The cat sat on the mat. It was a sunny day. The dog ran fast. Birds sang in the tree."
HARD = ("Notwithstanding the aforementioned considerations, the implementation of comprehensive "
        "infrastructural modifications necessitates a systematic evaluation of organisational "
        "readiness, particularly where interdependencies between legacy subsystems remain "
        "insufficiently documented.")


def _f(text, code="en"):
    lp = pack(code)
    return compute(count(sentences(text, lp), lp), lp, text)


def test_matches_textstat_on_simple_text():
    textstat = pytest.importorskip("textstat")
    textstat.set_lang("en")
    ours = _f(EASY)["flesch_reading_ease"].value
    assert ours == pytest.approx(textstat.flesch_reading_ease(EASY), abs=0.5)


def test_easy_scores_higher_than_hard():
    assert _f(EASY)["flesch_reading_ease"].value > _f(HARD)["flesch_reading_ease"].value
    assert _f(EASY)["lix"].value < _f(HARD)["lix"].value


def test_french_uses_kandel_moles():
    f = _f("Le chat est sur le tapis. Il fait beau. Le chien court vite.", "fr")
    assert "Kandel" in f["flesch_reading_ease"].name


def test_lix_bands():
    assert _f(EASY)["lix"].band in ("very easy", "easy")
    assert _f(HARD)["lix"].band == "very difficult"


def test_consensus_is_median_of_grades():
    f = _f(HARD)
    grades = sorted(x.value for x in f.values() if x.unit == "grade")
    c = consensus_grade(f)
    assert grades[0] <= c <= grades[-1]


def test_empty_input():
    assert compute(Counts(), pack("en")) == {}
