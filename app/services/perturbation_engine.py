import re
from typing import Dict, Any, List, Tuple

class LinguisticPerturbationEngine:
    """
    Empirical Stress-Testing Engine for Prior-Authorization Clinical NLP.
    Generates controlled programmatic perturbations across four clinical dimensions:
    1. Synonym Substitution across Cardiology, Pulmonology, Electrophysiology, and Wound Care
    2. Syntactic Negation Displacement (pre-negation vs. post-negation vs. ConText inversion)
    3. Semi-Structured Shorthand & Formatting Noise (bulleted lab/diagnostic notes)
    4. Controlled Evidence Omission (adversarial stress testing of abstention gate)
    """

    # Comprehensive clinical synonym mapping dictionary across all 5 CMS policies
    SYNONYM_REPLACEMENTS = [
        # Cardiology / NCD 20.4
        (r"(?i)\bleft ventricular ejection fraction\b", "LVEF"),
        (r"(?i)\blvef\b", "Left Ventricular Ejection Fraction"),
        (r"(?i)\bejection fraction\b", "LVEF"),
        (r"(?i)\bnyha class ii\b", "New York Heart Association Functional Class 2"),
        (r"(?i)\bnyha class iii\b", "New York Heart Association Functional Class 3"),
        (r"(?i)\bguideline-directed medical therapy\b", "GDMT"),
        (r"(?i)\bgdmt\b", "guideline-directed medical therapy"),
        (r"(?i)\bcoronary artery bypass graft(?:ing)?\b", "CABG"),
        (r"(?i)\bcabg\b", "coronary artery bypass grafting"),
        (r"(?i)\bst-elevation myocardial infarction\b", "STEMI"),
        (r"(?i)\bstemi\b", "ST-elevation myocardial infarction"),

        # Pulmonology / LCD L33829
        (r"(?i)\bapnea-hypopnea index\b", "AHI"),
        (r"(?i)\bahi\b", "Apnea-Hypopnea Index"),
        (r"(?i)\bpolysomnography\b", "overnight sleep study"),
        (r"(?i)\bcpap\b", "continuous positive airway pressure"),

        # Interventional Cardiology / NCD 20.33 (TAVR)
        (r"(?i)\baortic valve area\b", "AVA"),
        (r"(?i)\bava\b", "aortic valve area"),
        (r"(?i)\baortic stenosis\b", "severe AS"),
        (r"(?i)\btranscatheter aortic valve replacement\b", "TAVR"),

        # Electrophysiology / NCD 220.13 (LAAC)
        (r"(?i)\batrial fibrillation\b", "AFib"),
        (r"(?i)\bleft atrial appendage closure\b", "LAAC"),
        (r"(?i)\bcha2ds2-vasc\b", "CHADS-VASc"),

        # Wound Care / NCD 20.29 (HBOT)
        (r"(?i)\bdiabetic foot ulcer(?:ation)?\b", "DFU"),
        (r"(?i)\bhyperbaric oxygen therapy\b", "HBOT"),
        (r"(?i)\bwagner grade 3\b", "Wagner Classification Stage III")
    ]

    NEGATION_DISPLACEMENTS = [
        # Invert pre-negation to post-negation across clinical domains
        (r"(?i)\bno\s+(?:acute\s+)?cardiogenic shock\b", "cardiogenic shock is absent and ruled out"),
        (r"(?i)\bno active ischemia\b", "active cardiac ischemia has been evaluated and ruled out"),
        (r"(?i)\bdenies snoring\b", "snoring: negative"),
        (r"(?i)\bdenies excessive daytime sleepiness\b", "excessive daytime sleepiness: negative on ROS"),
        (r"(?i)\bno hypertension\b", "hypertension: negative"),
        (r"(?i)\bno stroke\b", "history of stroke: negative"),
        (r"(?i)\bno osteomyelitis\b", "osteomyelitis: ruled out on diagnostic imaging"),
        (r"(?i)\bwithout signs of hypoperfusion\b", "hypoperfusion signs are not present"),
        (r"(?i)\bno active infection\b", "systemic infection: absent and ruled out")
    ]

    @classmethod
    def apply_synonym_substitution(cls, text: str) -> str:
        """Applies global synonym swaps across the entire clinical narrative."""
        perturbed = text
        for pat, repl in cls.SYNONYM_REPLACEMENTS:
            # count=0 replaces all occurrences across the document
            perturbed = re.sub(pat, repl, perturbed, count=0)
        return perturbed

    @classmethod
    def apply_negation_displacement(cls, text: str) -> str:
        """Re-arranges syntactic position of negation markers across the document."""
        perturbed = text
        for pat, repl in cls.NEGATION_DISPLACEMENTS:
            perturbed = re.sub(pat, repl, perturbed, count=0)
        return perturbed

    @classmethod
    def apply_formatting_noise(cls, text: str) -> str:
        """Converts prose narrative into bulleted shorthand notation."""
        noisy = text
        # Convert "Echocardiogram: LVEF 28%" to "- ECHO: [EF=28%]"
        noisy = re.sub(r"(?i)echocardiogram[^\n\.]*?lvef\s*(\d{1,2})%", r"DIAGNOSTICS:\n- ECHO: [EF=\1%]", noisy)
        # Convert "AHI: 28.4 events per hour" to "- PSG: AHI=\1/hr"
        noisy = re.sub(r"(?i)apnea-hypopnea index[^\d]*?(\d{1,2}(?:\.\d+)?)", r"STUDIES:\n- PSG: AHI=\1/hr", noisy)
        # Convert "Aortic valve area: 0.68 cm2" to "- ECHO: AVA=0.68 cm2"
        noisy = re.sub(r"(?i)aortic valve area[^\d]*?(\d(?:\.\d+)?)\s*cm2", r"VALVE STUDY:\n- AVA: \1 cm2", noisy)
        return noisy

    @classmethod
    def apply_evidence_omission(cls, text: str, entity_keyword: str) -> str:
        """Adversarially removes lines containing the target entity keyword(s)."""
        lines = text.splitlines()
        keywords = [k.strip().lower() for k in entity_keyword.split("|") if k.strip()]
        filtered = [l for l in lines if not any(k in l.lower() for k in keywords)]
        return "\n".join(filtered)
