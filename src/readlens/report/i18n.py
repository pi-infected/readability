"""Report copy in English and French."""

EN = {
    "title": "Readability audit", "report_kind": "Readability & reading-comfort audit",
    "generated": "Generated", "pages": "pages",
    "coverage": "Coverage", "cov_analysed": "pages analysed", "cov_scored": "scored",
    "cov_rendered": "measured in a browser", "cov_detailed": "detailed below",
    "cov_unscorable": "with no readable content", "cov_failed": "unreachable",
    "desktop": "Desktop, 1440px", "mobile": "Mobile, 390px", "words": "words", "audience": "Audience",
    "grade": "Grade", "page": "Page",
    "score_explainer": "Site score: 70% mean page score, 20% worst page, 10% consistency. A reader lands on one page, not on the average.",
    "mean": "mean", "worst": "worst", "best": "best", "consistency": "consistency",
    "reading_time": " total reading time", "critical_issues": " critical issues",
    "high_issues": " high-severity issues", "rendered_pages": " pages measured in a browser",
    "fix_first": "What to fix first", "no_findings": "Nothing above the reporting threshold.",
    "affects": "Affects", "of": "of", "fix": "Fix",
    "pages_table": "Pages", "page_col": "Page", "type": "Type", "score": "Score",
    "profile": "Profile", "font": "Font", "contrast": "Contrast", "measure": "Chars/line",
    "table_legend": "Font = median body size in px (desktop). Contrast = median WCAG ratio of body text. "
                    "Chars/line = measured line length, target 50-80.",
    "consistency_h": "Consistency across the site",
    "consistency_intro": "A reader moving between pages should not have to re-adjust. "
                         "These scores measure how much the pages agree with each other.",
    "body_sizes": "Body text sizes", "line_heights": "Line heights", "measure_range": "Line length",
    "chars": "chars", "reading_level": "Reading level", "fonts_used": "Type families in use:",
    "dupe_titles": "Duplicate page titles:", "lang_declared": "Declared languages:",
    "lang_measured": "Measured languages:",
    "lang": "language", "lang_mismatch": "declared", "lang_after_render": "corrected after hydration to",
    "formulas": "Readability formulas", "metric": "Metric", "value": "Value",
    "interpretation": "Interpretation", "measured": "Measured against targets",
    "target": "Target", "page_findings": "Findings on this page",
    "hardest": "Hardest paragraphs", "asl": "avg sentence",
    "hints": "Sentences to rewrite",
    "methodology": "Methodology", "pillar_col": "Pillar", "why": "Why it is measured",
    "method_intro": "Every metric below is measured on the page itself: the text is extracted from "
                    "the main content, the typography is read from the rendered page in a real browser "
                    "at 1440px and 390px. A metric scores 100 inside its target band, 60 at the edge of "
                    "the tolerable range, and 0 one span beyond. Pillars are weighted means, minus a "
                    "penalty for each concrete defect found.",
    "limits": "Limits",
    "limits_text": "Readability formulas were calibrated on print prose and school grades; they measure "
                   "sentence and word length, not whether an argument is clear. Passive-voice and "
                   "nominalisation detection is rule-based and will miss some cases and over-report "
                   "others. Contrast is measured on the resolved computed colours, so text over images "
                   "or gradients is reported separately rather than scored. Treat the score as a "
                   "prioritised list of things to look at, not as a verdict.",
    "sev": {"critical": "critical", "high": "high", "medium": "medium", "low": "low",
            "info": "info", "ok": "ok", "A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F"},
    "pillar": {"clarity": "Clarity", "structure": "Structure", "comfort": "Comfort",
               "access": "Accessibility"},
}

FR = {
    "title": "Audit de lisibilité", "report_kind": "Audit de lisibilité et de confort de lecture",
    "generated": "Généré le", "pages": "pages",
    "coverage": "Couverture", "cov_analysed": "pages analysées", "cov_scored": "notées",
    "cov_rendered": "mesurées dans un navigateur", "cov_detailed": "détaillées ci-dessous",
    "cov_unscorable": "sans contenu lisible", "cov_failed": "injoignables",
    "desktop": "Bureau, 1440px", "mobile": "Mobile, 390px", "words": "mots", "audience": "Public",
    "grade": "Note", "page": "Page",
    "score_explainer": "Score du site : 70% de la moyenne des pages, 20% de la pire page, "
                       "10% de cohérence. Un lecteur arrive sur une page, pas sur la moyenne.",
    "mean": "moyenne", "worst": "pire", "best": "meilleure", "consistency": "cohérence",
    "reading_time": " de lecture au total", "critical_issues": " problèmes critiques",
    "high_issues": " problèmes majeurs", "rendered_pages": " pages mesurées dans un navigateur",
    "fix_first": "À corriger en premier", "no_findings": "Rien au-dessus du seuil de signalement.",
    "affects": "Concerne", "of": "sur", "fix": "Correction",
    "pages_table": "Pages", "page_col": "Page", "type": "Type", "score": "Score",
    "profile": "Profil", "font": "Corps", "contrast": "Contraste", "measure": "Signes/ligne",
    "table_legend": "Corps = taille médiane du texte courant en px (bureau). Contraste = ratio WCAG médian. "
                    "Signes/ligne = longueur de ligne mesurée, cible 50-80.",
    "consistency_h": "Cohérence à l'échelle du site",
    "consistency_intro": "Un lecteur qui passe d'une page à l'autre ne devrait pas avoir à se réadapter. "
                         "Ces scores mesurent à quel point les pages sont d'accord entre elles.",
    "body_sizes": "Tailles de texte courant", "line_heights": "Interlignes",
    "measure_range": "Longueur de ligne", "chars": "signes", "reading_level": "Niveau de lecture",
    "fonts_used": "Familles typographiques utilisées :", "dupe_titles": "Titres de page en double :",
    "lang_declared": "Langues déclarées :", "lang_measured": "Langues mesurées :",
    "lang": "langue", "lang_mismatch": "déclarée", "lang_after_render": "corrigée après hydratation en",
    "formulas": "Formules de lisibilité", "metric": "Métrique", "value": "Valeur",
    "interpretation": "Interprétation", "measured": "Mesures par rapport aux cibles",
    "target": "Cible", "page_findings": "Constats sur cette page",
    "hardest": "Paragraphes les plus difficiles", "asl": "phrase moy.",
    "hints": "Phrases à reprendre",
    "methodology": "Méthodologie", "pillar_col": "Pilier", "why": "Pourquoi c'est mesuré",
    "method_intro": "Chaque métrique est mesurée sur la page elle-même : le texte est extrait du contenu "
                    "principal, la typographie est lue sur le rendu réel dans un navigateur à 1440px et "
                    "390px. Une métrique vaut 100 dans sa plage cible, 60 au bord de la plage tolérable, "
                    "0 une plage au-delà. Les piliers sont des moyennes pondérées, moins une pénalité "
                    "par défaut concret constaté.",
    "limits": "Limites",
    "limits_text": "Les formules de lisibilité ont été calibrées sur de la prose imprimée et des niveaux "
                   "scolaires ; elles mesurent la longueur des phrases et des mots, pas la clarté d'un "
                   "raisonnement. La détection du passif et des nominalisations est à base de règles : "
                   "elle rate des cas et en signale à tort. Le contraste est mesuré sur les couleurs "
                   "calculées, donc le texte posé sur une image ou un dégradé est signalé à part plutôt "
                   "que noté. Ce score est une liste de priorités, pas un verdict.",
    "sev": {"critical": "critique", "high": "majeur", "medium": "moyen", "low": "mineur",
            "info": "info", "ok": "ok", "A": "A", "B": "B", "C": "C", "D": "D", "E": "E", "F": "F"},
    "pillar": {"clarity": "Clarté", "structure": "Structure", "comfort": "Confort",
               "access": "Accessibilité"},
}

STRINGS = {"en": EN, "fr": FR}


def strings(lang: str) -> dict:
    return STRINGS.get((lang or "en").split("-")[0].lower(), EN)
