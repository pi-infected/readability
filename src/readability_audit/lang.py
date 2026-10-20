"""Per-language linguistic resources. Full support: en, fr. Partial: es, de, it, pt, nl."""
from __future__ import annotations

from dataclasses import dataclass, field

# --- stopword profiles used for language identification ---------------------
PROFILE = {
    "en": "the of and to a in is it you that he was for on are with as i his they be at one have this from or had by hot but some what there we can out other were all your when up use word how said an each she which do their time if will way about many then them would write like so these her long make thing see him two has look more day could go come did number sound no most people my over know than call first who may down side been now find any new work part take get place made live where after back little only round man year came show every good me give our under name very through just form much great think say help low line before turn cause same mean differ move right boy old too does tell sentence set three want air well also play small end put home read hand port large spell add even land here must big high such follow act why ask men change went light kind off need house picture try us again animal point mother world near build self earth father",
    "fr": "de la le et les des en un une du dans est que pour qui sur au ne pas plus par avec se son sont ce il elle nous vous ils on aux ou mais comme tout ses leur cette a été être avec cela sans deux entre aussi si peut faire fait très bien encore lui même sous depuis avant après quand donc alors dont chaque autre autres toujours jamais dire dit peu tous celui ceux là où vers chez pendant beaucoup moins ainsi",
    "es": "de la que el en y a los se del las un por con no una su para es al lo como más pero sus le ha o este sí porque esta entre cuando muy sin sobre también me hasta hay donde quien desde todo nos durante todos uno les ni contra otros ese eso ante ellos e esto mí antes algunos qué unos yo otro otras otra él tanto esa estos mucho quienes nada muchos cual poco ella estar",
    "de": "der die und in den von zu das mit sich des auf für ist im dem nicht ein eine als auch es an werden aus er hat dass sie nach wird bei einer um am sind noch wie einem über einen so zum war haben nur oder aber vor zur bis mehr durch man sein wurde sei in prozent hatte kann gegen vom können schon wenn habe seine mark ihre dann unter wir soll ich",
    "it": "di che e il la per un in una non sono con si mi ma da come le ho più ci se al ti lo hai cosa questo del i sei alla della me quando ha tutto lui io anche solo perché prima o mio ora c'è dei sua fare tuo qui essere",
    "pt": "de a o que e do da em um para é com não uma os no se na por mais as dos como mas foi ao ele das tem à seu sua ou ser quando muito há nos já está eu também só pelo pela até isso ela entre era depois sem mesmo aos ter seus quem nas me esse eles",
    "nl": "de en van ik te dat die in een hij het niet zijn is was op aan met als voor had er maar om hem dan zou of wat mijn men dit zo door over ze zich bij ook tot je mij uit der daar haar naar heb hoe heeft hebben deze u want nog zal me zij nu ge geen omdat iets worden toch al waren veel meer doen",
}
STOPSETS = {k: set(v.split()) for k, v in PROFILE.items()}

PYPHEN_LOCALE = {"en": "en_US", "fr": "fr_FR", "es": "es_ES", "de": "de_DE",
                 "it": "it_IT", "pt": "pt_PT", "nl": "nl_NL"}

# Flesch Reading Ease coefficients: score = a - b*ASL - c*ASW
FLESCH_COEFF = {
    "en": (206.835, 1.015, 84.6, "Flesch Reading Ease"),
    "fr": (207.0, 1.015, 73.6, "Kandel-Moles (Flesch FR)"),
    "es": (206.84, 1.02, 60.0, "Fernandez-Huerta (ES)"),
    "de": (180.0, 1.0, 58.5, "Amstad (DE)"),
    "it": (217.0, 1.3, 60.0, "Flesch-Vacca (IT)"),
    "nl": (206.835, 0.93, 77.0, "Douma (NL)"),
    "pt": (248.835, 1.015, 84.6, "Flesch PT (Martins)"),
}

ABBREV = {
    "en": {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e",
           "fig", "inc", "ltd", "co", "corp", "dept", "est", "approx", "no", "vol", "al", "ca", "cf",
           "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sept", "sep", "oct", "nov", "dec",
           "mon", "tue", "wed", "thu", "fri", "sat", "sun", "u.s", "u.k", "ph.d", "min", "max"},
    "fr": {"m", "mme", "mlle", "dr", "pr", "st", "ste", "av", "bd", "etc", "cf", "ex",
           "p", "pp", "vol", "art", "env", "réf", "tél", "n°", "fig", "éd", "trad", "janv", "févr",
           "avr", "juil", "sept", "oct", "nov", "déc", "min", "max", "cad", "env", "chap"},
}

# Transition / connective words (Yoast-style). Signals argumentative flow.
CONNECTIVES = {
    "en": {"also", "although", "as a result", "because", "besides", "but", "consequently",
           "conversely", "despite", "even so", "finally", "first", "for example", "for instance",
           "furthermore", "hence", "however", "in addition", "in contrast", "in fact", "indeed",
           "instead", "later", "likewise", "meanwhile", "moreover", "nevertheless", "next",
           "nonetheless", "on the contrary", "otherwise", "second", "similarly", "since", "so",
           "still", "that is", "then", "therefore", "though", "thus", "unless", "until", "whereas",
           "while", "yet", "in other words", "in short", "of course", "rather", "actually"},
    "fr": {"ainsi", "alors", "au contraire", "aussi", "autrement dit", "bien que", "car",
           "cependant", "c'est-à-dire", "d'abord", "d'ailleurs", "de plus", "donc", "en effet",
           "en outre", "en revanche", "en fait", "ensuite", "enfin", "malgré", "mais", "néanmoins",
           "or", "par ailleurs", "par conséquent", "par exemple", "pourtant", "puis", "puisque",
           "quand même", "tandis que", "toutefois", "à savoir", "de fait", "bref", "certes",
           "notamment", "surtout", "parce que", "tout d'abord", "finalement",
           "ainsi que", "de même", "en somme", "au final", "du coup", "voire", "sinon",
           "par contre", "en conclusion", "grâce à", "à cause de", "afin de", "pour que",
           "si bien que", "alors que", "dès lors", "en réalité", "en pratique",
           "concrètement", "plutôt que", "contrairement à", "au lieu de", "non seulement",
           "mais aussi", "d'une part", "d'autre part", "premièrement", "deuxièmement",
           "de sorte que", "lorsque", "tant que", "même si", "sauf si", "à condition que",
           "entre-temps", "désormais", "en effet", "en général", "par exemple", "en particulier",
           "au contraire", "en résumé", "à l'inverse", "de plus", "par ailleurs", "puis"},
}

# Hedging / vague filler that dilutes prose.
HEDGES = {
    "en": {"very", "really", "quite", "somewhat", "rather", "fairly", "basically", "simply",
           "just", "actually", "literally", "essentially", "arguably", "perhaps", "maybe",
           "possibly", "probably", "seems", "appears", "kind of", "sort of", "a bit", "various",
           "several", "numerous", "leverage", "utilize", "robust", "seamless", "cutting-edge",
           "state-of-the-art", "world-class", "best-in-class", "game-changing", "revolutionary",
           "innovative", "synergy", "holistic", "paradigm", "unlock", "empower", "supercharge"},
    "fr": {"très", "vraiment", "assez", "plutôt", "un peu", "quelque peu", "simplement",
           "littéralement", "essentiellement", "peut-être", "sans doute", "probablement",
           "semble", "paraît", "divers", "plusieurs", "nombreux", "innovant", "révolutionnaire",
           "incontournable", "unique", "puissant", "clé en main", "sur-mesure", "à la pointe",
           "leader", "solution globale", "synergie", "optimiser", "booster"},
}

NOMINAL_SUFFIX = {
    "en": ("tion", "sion", "ment", "ness", "ity", "ance", "ence", "ization", "isation", "ability"),
    "fr": ("tion", "sion", "ment", "ité", "ance", "ence", "isation", "ification", "abilité"),
    "es": ("ción", "sión", "miento", "idad", "ancia", "encia"),
    "de": ("ung", "heit", "keit", "schaft", "tion"),
}

ADVERB_SUFFIX = {"en": ("ly",), "fr": ("ment",), "es": ("mente",), "it": ("mente",), "pt": ("mente",)}

# Passive voice
BE_FORMS = {"be", "am", "is", "are", "was", "were", "been", "being", "get", "gets", "got", "gotten"}
ETRE_FORMS = {"est", "sont", "était", "étaient", "sera", "seront", "été", "être", "suis", "es",
              "sommes", "êtes", "fut", "furent", "serait", "seraient", "soit", "soient"}
EN_IRREGULAR_PP = {
    "done", "made", "said", "seen", "gone", "taken", "given", "known", "found", "told", "become",
    "left", "put", "kept", "held", "brought", "written", "shown", "built", "sent", "understood",
    "set", "run", "paid", "met", "chosen", "driven", "spoken", "broken", "read", "lost", "won",
    "cut", "let", "begun", "drawn", "grown", "thrown", "caught", "taught", "bought", "sold",
}

WEAK_LINK_TEXT = {
    "en": {"click here", "here", "read more", "more", "link", "this", "this page", "learn more",
           "see more", "continue", "download", "go", "click", "info", "details", "see here"},
    "fr": {"cliquez ici", "ici", "en savoir plus", "plus", "lien", "ce lien", "voir plus",
           "lire la suite", "continuer", "télécharger", "détails", "voir ici", "cliquer ici"},
}


@dataclass
class LangPack:
    code: str
    stopwords: set = field(default_factory=set)
    connectives: set = field(default_factory=set)
    hedges: set = field(default_factory=set)
    abbrev: set = field(default_factory=set)
    nominal: tuple = ()
    adverb: tuple = ()
    weak_link: set = field(default_factory=set)
    pyphen: str | None = None
    flesch: tuple | None = None
    long_word_chars: int = 7   # LIX threshold is >6 chars

    @property
    def supported(self) -> bool:
        return self.code in ("en", "fr")


def pack(code: str | None) -> LangPack:
    c = (code or "en").split("-")[0].lower()
    if c not in STOPSETS:
        c = "en"
    return LangPack(
        code=c,
        stopwords=STOPSETS.get(c, set()),
        connectives=CONNECTIVES.get(c, CONNECTIVES["en"]),
        hedges=HEDGES.get(c, HEDGES["en"]),
        abbrev=ABBREV.get(c, ABBREV["en"]),
        nominal=NOMINAL_SUFFIX.get(c, NOMINAL_SUFFIX["en"]),
        adverb=ADVERB_SUFFIX.get(c, ()),
        weak_link=WEAK_LINK_TEXT.get(c, WEAK_LINK_TEXT["en"]),
        pyphen=PYPHEN_LOCALE.get(c),
        flesch=FLESCH_COEFF.get(c),
    )


SCRIPT_RANGES = (
    ("latin", ((0x41, 0x5A), (0x61, 0x7A), (0xC0, 0x24F))),
    ("greek", ((0x370, 0x3FF),)),
    ("cyrillic", ((0x400, 0x4FF),)),
    ("hebrew", ((0x590, 0x5FF),)),
    ("arabic", ((0x600, 0x6FF), (0x750, 0x77F))),
    ("devanagari", ((0x900, 0x97F),)),
    ("thai", ((0xE00, 0xE7F),)),
    ("cjk", ((0x3040, 0x30FF), (0x4E00, 0x9FFF), (0xAC00, 0xD7AF))),
)


def dominant_script(text: str) -> tuple[str, float]:
    """Which writing system the text is in, and what share of its letters agree."""
    counts: dict[str, int] = {}
    total = 0
    for ch in text[:4000]:
        if not ch.isalpha():
            continue
        cp = ord(ch)
        for name, ranges in SCRIPT_RANGES:
            if any(lo <= cp <= hi for lo, hi in ranges):
                counts[name] = counts.get(name, 0) + 1
                total += 1
                break
        else:
            counts["other"] = counts.get("other", 0) + 1
            total += 1
    if not total:
        return "unknown", 0.0
    name, n = max(counts.items(), key=lambda kv: kv[1])
    return name, round(n / total, 3)


# Clarity metrics need syllables, stopwords and word boundaries. We have those for the
# languages below; elsewhere the tool reports structure, comfort and access and says
# plainly that it cannot judge the writing.
CLARITY_LANGUAGES = set(STOPSETS)


def clarity_supported(code: str | None, text: str) -> tuple[bool, str]:
    script, share = dominant_script(text)
    if script == "cjk":
        return False, ("this text is written in a script without word spacing, which the "
                       "word- and sentence-based measures cannot read")
    if script not in ("latin", "unknown") and share > 0.5:
        return False, f"the language metrics here are built for Latin-script text, not {script}"
    if code not in CLARITY_LANGUAGES:
        return False, f"no language profile for {code!r}"
    return True, ""


# Languages each non-Latin script is written in; the first is the guess when the page
# declares none of them.
SCRIPT_LANGS = {
    "greek": ("el",), "cyrillic": ("ru", "uk", "bg", "sr", "be", "mk", "kk"),
    "hebrew": ("he", "yi"), "arabic": ("ar", "fa", "ur", "ps"),
    "devanagari": ("hi", "mr", "ne", "sa"), "thai": ("th",),
}


def _cjk_lang(text: str) -> str:
    kana = sum(1 for ch in text[:4000] if 0x3040 <= ord(ch) <= 0x30FF)
    hangul = sum(1 for ch in text[:4000] if 0xAC00 <= ord(ch) <= 0xD7AF)
    han = sum(1 for ch in text[:4000] if 0x4E00 <= ord(ch) <= 0x9FFF)
    if hangul > max(kana, han):
        return "ko"
    return "ja" if kana > 0.1 * (kana + han) else "zh"


def detect(text: str, declared: str | None = None) -> tuple[str, float]:
    """Deterministic language id: the script first, then a stopword profile for
    Latin-script text. Returns (code, confidence 0-1). A declared language written in
    the detected script is kept: the script cannot tell Persian from Arabic."""
    import re
    script, share = dominant_script(text)
    if script not in ("latin", "unknown", "other") and share > 0.5:
        if script == "cjk":
            code = _cjk_lang(text)
            langs = ("zh", "ja", "ko") if code == "zh" else (code,)
        else:
            langs = SCRIPT_LANGS[script]
            code = langs[0]
        return (declared if declared in langs else code), 0.9
    words = re.findall(r"[^\W\d_]+", text.lower(), re.UNICODE)[:1500]
    if len(words) < 8:
        return "en", 0.0
    scores = {c: sum(1 for w in words if w in sw) / len(words) for c, sw in STOPSETS.items()}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top, second = ranked[0], ranked[1]
    if top[1] < 0.03:
        return "en", 0.0
    margin = (top[1] - second[1]) / max(top[1], 1e-6)
    conf = (margin * 1.6 + top[1] * 1.2) * min(1.0, len(words) / 40)
    return top[0], round(min(1.0, conf), 3)
