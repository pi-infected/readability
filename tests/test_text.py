import pytest

from readlens.lang import detect, pack
from readlens.text import sentences, syllables, words

EN, FR = pack("en"), pack("fr")


@pytest.mark.parametrize("text,n", [
    ("Dr. Smith paid $1,250.50 on Jan. 3. He said e.g. this works! Yes... it does.", 3),
    ("One. Two. Three.", 3),
    ("No terminal punctuation", 1),
    ("Visit https://a.b/c. Then stop.", 2),
    ("Is it? Yes! Really...", 3),
])
def test_sentence_split_en(text, n):
    assert len(sentences(text, EN)) == n


@pytest.mark.parametrize("text,n", [
    ("M. Dupont a payé 1 250,50 € le 3 janv. Il dit p. ex. que ça marche.", 2),
    ("Vraiment ? Oui. Bien sûr !", 3),
])
def test_sentence_split_fr(text, n):
    assert len(sentences(text, FR)) == n


EN_GOLD = {"readability": 5, "orange": 2, "simple": 2, "people": 2, "computer": 3,
           "information": 4, "beautiful": 3, "through": 1, "science": 2, "every": 2,
           "different": 3, "available": 4, "question": 2, "important": 3, "the": 1,
           "cat": 1, "queue": 1, "chocolate": 3, "interesting": 4, "library": 3}

FR_GOLD = {"orange": 2, "parlent": 1, "également": 4, "souvent": 2, "comment": 2,
           "vraiment": 2, "chantent": 1, "lisibilité": 5, "gouvernement": 4, "moment": 2,
           "prennent": 1, "simple": 1, "beaucoup": 2, "aujourd'hui": 3, "ordinateur": 4,
           "information": 4, "oiseau": 2, "travailler": 3, "difficile": 3, "maison": 2}


def _accuracy(gold, lp):
    hits = sum(1 for w, g in gold.items() if syllables(w, lp) == g)
    return hits / len(gold)


def test_syllables_en():
    assert _accuracy(EN_GOLD, EN) >= 0.9


def test_syllables_fr():
    assert _accuracy(FR_GOLD, FR) >= 0.9


def test_words_keeps_internal_punctuation():
    assert words("aujourd'hui well-known") == ["aujourd'hui", "well-known"]


def test_detect():
    assert detect("Le renard brun saute par dessus le chien qui ne se demande pas pourquoi.")[0] == "fr"
    assert detect("The quick brown fox jumps over the lazy dog and it does not ask why.")[0] == "en"
    assert detect("hi")[1] == 0.0
