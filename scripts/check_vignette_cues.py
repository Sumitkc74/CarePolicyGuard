import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEV_VIGNETTES_FILE = REPO_ROOT / "app" / "data" / "policies_extended" / "dev_vignettes_extended.json"

FORBIDDEN_PHRASES = [
    # Policy slugs / IDs
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

    # Document identifiers
    "42 CFR", "L35452", "L35024", "L36920", "L38773", "L33318", "L33569", "L33789",
    "L33800", "L33821", "NCD 10.1", "NCD 20.8", "NCD 220.6.17", "NCD 280.14", "NCD 160.7",
    "NCD 50.1", "LCD ", "NCD ",

    # Verdict and coverage decision phrases
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

def scan_vignettes_for_cues():
    with open(DEV_VIGNETTES_FILE, "r", encoding="utf-8") as f:
        vignettes = json.load(f)

    violations = []
    for vig in vignettes:
        vid = vig["vignette_id"]
        narrative = vig["ehr_narrative"]
        narrative_lower = narrative.lower()

        for phrase in FORBIDDEN_PHRASES:
            # Check case-insensitive match
            if phrase.lower() in narrative_lower:
                violations.append((vid, phrase))

    return violations

if __name__ == "__main__":
    v = scan_vignettes_for_cues()
    if v:
        print(f"Found {len(v)} violations:")
        for vid, p in v:
            print(f"  [{vid}] Contains forbidden phrase: {p!r}")
    else:
        print("SUCCESS: Zero forbidden phrases or cues detected in all 84 vignettes!")

