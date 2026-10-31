import re
from typing import Dict, Any, List, Tuple

class LinguisticPerturbationEngine:
    """
    Empirical Stress-Testing Engine for Prior-Authorization Clinical NLP.
    Generates controlled programmatic perturbations across three clinical dimensions:
    1. Synonym Substitution (e.g., LVEF vs. Left Ventricular Ejection Fraction vs. EF)
    2. Syntactic Negation Displacement (e.g., pre-negation vs. post-negation vs. ConText inversion)
    3. Semi-Structured Shorthand & Formatting Noise (e.g., bulleted lab notes vs. narrative text)
    4. Controlled Evidence Omission (adversarial stress test for abstention gate)
    """

    # Comprehensive clinical synonym mapping dictionary
    SYNONYM_REPLACEMENTS = [
        (r"(?i)\bleft ventricular ejection fraction\b", "LVEF"),
        (r"(?i)\blvef\b", "Left Ventricular Ejection Fraction"),
        (r"(?i)\bejection fraction\b", "LVEF"),
        (r"(?i)\bnyha class ii\b", "New York Heart Association Functional Class 2"),
        (r"(?i)\bnyha class iii\b", "New York Heart Association Functional Class 3"),
        (r"(?i)\bapnea-hypopnea index\b", "AHI"),
        (r"(?i)\bahi\b", "Apnea-Hypopnea Index"),
        (r"(?i)\bguideline-directed medical therapy\b", "GDMT"),
        (r"(?i)\bgdmt\b", "guideline-directed medical therapy"),
        (r"(?i)\bcoronary artery bypass graft(?:ing)?\b", "CABG"),
        (r"(?i)\bcabg\b", "coronary artery bypass grafting"),
        (r"(?i)\bst-elevation myocardial infarction\b", "STEMI"),
        (r"(?i)\bstemi\b", "ST-elevation myocardial infarction"),
    ]

    NEGATION_DISPLACEMENTS = [
        # Invert pre-negation to post-negation
        (r"(?i)\bno\s+(?:acute\s+)?cardiogenic shock\b", "cardiogenic shock is absent and ruled out"),
        (r"(?i)\bno active ischemia\b", "active cardiac ischemia has been evaluated and ruled out"),
        (r"(?i)\bdenies snoring\b", "snoring: negative"),
        (r"(?i)\bwithout signs of hypoperfusion\b", "hypoperfusion signs are not present"),
    ]

    @classmethod
    def apply_synonym_substitution(cls, text: str) -> str:
        """Applies synonym swaps across clinical narrative."""
        perturbed = text
        for pat, repl in cls.SYNONYM_REPLACEMENTS:
            perturbed = re.sub(pat, repl, perturbed, count=1)
        return perturbed

    @classmethod
    def apply_negation_displacement(cls, text: str) -> str:
        """Re-arranges syntactic position of negation markers (pre- to post-negation)."""
        perturbed = text
        for pat, repl in cls.NEGATION_DISPLACEMENTS:
            perturbed = re.sub(pat, repl, perturbed, count=1)
        return perturbed

    @classmethod
    def apply_formatting_noise(cls, text: str) -> str:
        """Converts prose narrative into bulleted shorthand notation."""
        noisy = text
        # Convert "Echocardiogram: LVEF 28%" to "- ECHO: [EF=28%]"
        noisy = re.sub(r"(?i)echocardiogram[^\n\.]*?lvef\s*(\d{1,2})%", r"DIAGNOSTICS:\n- ECHO: [EF=\1%]", noisy)
        # Convert "AHI: 28.4 events per hour" to "- PSG: AHI=\1/hr"
        noisy = re.sub(r"(?i)apnea-hypopnea index[^\d]*?(\d{1,2}(?:\.\d+)?)", r"STUDIES:\n- PSG: AHI=\1/hr", noisy)
        return noisy

    @classmethod
    def apply_evidence_omission(cls, text: str, entity_keyword: str) -> str:
        """Adversarially removes a clinical sentence containing the target entity keyword."""
        lines = text.splitlines()
        filtered = [l for l in lines if entity_keyword.lower() not in l.lower()]
        return "\n".join(filtered)
