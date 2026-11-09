import json
import re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICIES_DIR = REPO_ROOT / "app" / "data" / "policies_extended"
DEV_VIGNETTES_FILE = POLICIES_DIR / "dev_vignettes_extended.json"
REPORT_FILE = POLICIES_DIR / "DEVELOPMENT_EVALUATION_REPORT.md"

FORBIDDEN_PHRASES = [
    # 1. 42 Extended policy slugs & base 8 policy slugs
    "LCD-ACDF", "LCD-ACI", "LCD-CT-CHEST", "LCD-ESI", "LCD-EVAR", "LCD-FACET",
    "LCD-HALLUX", "LCD-HIP-ARTHRO", "LCD-HIP-SCOOP", "LCD-IMRT", "LCD-KNEE-ARTHRO",
    "LCD-KNEE-ORTHOSIS", "LCD-KYPHO", "LCD-LUMBAR-DECOMP", "LCD-LUMBAR-FUSION",
    "LCD-MRI-BRAIN", "LCD-MRI-LUMBAR", "LCD-PAD-ATHERO", "LCD-PCI", "LCD-POWER-WC",
    "LCD-PROTON", "LCD-RAD-NIV", "LCD-ROTATOR-CUFF", "LCD-SBRT", "LCD-SHOULDER-ARTHRO",
    "LCD-WOUND-VAC", "NCD-CARDIAC-REHAB", "NCD-CATARACT", "NCD-CCTA", "NCD-MPI-PET",
    "NCD-PACEMAKER", "NCD-PET-ONC", "NCD-PUMP", "NCD-SCS", "NCD-SGD", "OPD-BLEPH",
    "OPD-BOTOX", "OPD-CERV-DISC", "OPD-PANNI", "OPD-RHINO", "OPD-SI-FUSION", "OPD-VEIN",
    "NCD-20.7", "NCD-20.4", "NCD-220.13", "LCD-L33587", "LCD-L33777", "LCD-L33778",
    "NCD-50.3", "NCD-160.18",

    # 2. Statutory document identifiers
    "42 CFR", "L35452", "L35024", "L36920", "L38773", "L33318", "L33569", "L33789",
    "L33800", "L33821", "NCD 10.1", "NCD 20.8", "NCD 220.6.17", "NCD 280.14", "NCD 160.7",
    "NCD 50.1", "LCD ", "NCD ",

    # 3. Verdict and coverage decision phrases
    "satisfies all clinical coverage indications",
    "coverage indications",
    "denied under",
    "contraindicated and denied",
    "meets coverage criteria",
    "coverage criteria met",
    "coverage approved",
    "coverage denied",
    "prior authorization approved",
    "prior authorization denied",
    "expected decision",
    "decision: approved",
    "decision: denied"
]

def test_vignettes_narratives_contain_zero_cues_or_verdict_phrases():
    """Asserts that no narrative in dev_vignettes_extended.json contains any forbidden cues."""
    assert DEV_VIGNETTES_FILE.exists(), f"Vignette file {DEV_VIGNETTES_FILE} does not exist"

    with open(DEV_VIGNETTES_FILE, "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    assert len(vignettes) == 84, f"Expected 84 vignettes, got {len(vignettes)}"

    violations = []
    for vig in vignettes:
        vid = vig.get("vignette_id", "UNKNOWN")
        narrative = vig.get("ehr_narrative", "")
        narrative_lower = narrative.lower()

        for phrase in FORBIDDEN_PHRASES:
            if phrase.lower() in narrative_lower:
                violations.append((vid, phrase))

    assert len(violations) == 0, f"Found {len(violations)} cue violations in vignettes: {violations[:5]}"

def test_evaluation_report_numbers_match_evaluation_harness_output():
    """Asserts that the committed DEVELOPMENT_EVALUATION_REPORT.md accurately reflects harness metrics and guards against staleness."""
    assert REPORT_FILE.exists(), "DEVELOPMENT_EVALUATION_REPORT.md must exist"
    report_text = REPORT_FILE.read_text(encoding="utf-8")

    assert "DEVELOPMENT-ONLY" in report_text
    assert "## Confusion Matrix (AUTO Retrieval Top-1)" in report_text
    assert "## Per-Policy Development Results" in report_text

    # Extract headline numbers from report table
    top1_match = re.search(r"\|\s*\*\*AUTO Retrieval Top-1 Accuracy\*\*\s*\|\s*`(\d+)/(\d+)`\s*\|\s*\*\*([\d\.]+)%\*\*", report_text)
    top3_match = re.search(r"\|\s*\*\*AUTO Retrieval Top-3 Accuracy\*\*\s*\|\s*`(\d+)/(\d+)`\s*\|\s*\*\*([\d\.]+)%\*\*", report_text)
    dec_match = re.search(r"\|\s*\*\*Adjudication Decision Accuracy\*\*\s*\|\s*`(\d+)/(\d+)`\s*\|\s*\*\*([\d\.]+)%\*\*", report_text)

    assert top1_match, "Failed to parse AUTO Retrieval Top-1 Accuracy from report"
    assert top3_match, "Failed to parse AUTO Retrieval Top-3 Accuracy from report"
    assert dec_match, "Failed to parse Adjudication Decision Accuracy from report"

    report_top1 = int(top1_match.group(1))
    report_top3 = int(top3_match.group(1))
    report_dec = int(dec_match.group(1))
    report_total = int(dec_match.group(2))

    # Fast deterministic fresh evaluation (runs in seconds, no Ollama required)
    from scripts.evaluate_extended_policies import run_evaluation
    fresh = run_evaluation(write_report=False)

    assert report_total == fresh["total"] == 84, f"Total vignettes mismatch: report={report_total}, fresh={fresh['total']}"
    assert report_top1 == fresh["top1_correct"] == 73, f"Top-1 accuracy mismatch: report={report_top1}, fresh={fresh['top1_correct']}"
    assert report_top3 == fresh["top3_correct"] == 82, f"Top-3 accuracy mismatch: report={report_top3}, fresh={fresh['top3_correct']}"
    assert report_dec == fresh["decision_correct"] == 39, f"Adjudication decision accuracy mismatch: report={report_dec}, fresh={fresh['decision_correct']}"

