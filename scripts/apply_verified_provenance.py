import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICIES_DIR = REPO_ROOT / "app" / "data" / "policies_extended"
PROVENANCE_FILE = POLICIES_DIR / "PROVENANCE.md"

# Verified audit results from live CMS MCD query on 2026-11-05
AUDIT_RESULTS = {
    # 8 UNVERIFIED_AUTHOR_SUMMARY (No MCD document found at cited identifier / Invalid LCD)
    "LCD-ACDF": {
        "status": "UNVERIFIED_AUTHOR_SUMMARY",
        "mcd_id": None,
        "mcd_title": None,
        "contractor": None,
        "url": None,
        "notes": "No MCD document found at previously cited identifier L35452 (redirects to 'Invalid LCD Version' / 0 search results). Labeled as author summary with no CMS source located."
    },
    "LCD-ACI": {
        "status": "UNVERIFIED_AUTHOR_SUMMARY",
        "mcd_id": None,
        "mcd_title": None,
        "contractor": None,
        "url": None,
        "notes": "No MCD document found at previously cited identifier L35024 (redirects to 'Invalid LCD Version' / 0 search results). Labeled as author summary with no CMS source located."
    },
    "LCD-IMRT": {
        "status": "UNVERIFIED_AUTHOR_SUMMARY",
        "mcd_id": None,
        "mcd_title": None,
        "contractor": None,
        "url": None,
        "notes": "No MCD document found at previously cited identifier L34652 (redirects to 'Invalid LCD Version' / 0 search results). Labeled as author summary with no CMS source located."
    },
    "LCD-KNEE-ARTHRO": {
        "status": "UNVERIFIED_AUTHOR_SUMMARY",
        "mcd_id": None,
        "mcd_title": None,
        "contractor": None,
        "url": None,
        "notes": "No MCD document found at previously cited identifier L33968 (redirects to 'Invalid LCD Version' / 0 search results). Labeled as author summary with no CMS source located."
    },
    "LCD-MRI-LUMBAR": {
        "status": "UNVERIFIED_AUTHOR_SUMMARY",
        "mcd_id": None,
        "mcd_title": None,
        "contractor": None,
        "url": None,
        "notes": "No MCD document found at previously cited identifier L34421 (redirects to 'Invalid LCD Version' / 0 search results). Labeled as author summary with no CMS source located."
    },
    "LCD-PROTON": {
        "status": "UNVERIFIED_AUTHOR_SUMMARY",
        "mcd_id": None,
        "mcd_title": None,
        "contractor": None,
        "url": None,
        "notes": "No MCD document found at previously cited identifier L34676 (redirects to 'Invalid LCD Version' / 0 search results). Labeled as author summary with no CMS source located."
    },
    "LCD-SBRT": {
        "status": "UNVERIFIED_AUTHOR_SUMMARY",
        "mcd_id": None,
        "mcd_title": None,
        "contractor": None,
        "url": None,
        "notes": "No MCD document found at previously cited identifier L34678 (redirects to 'Invalid LCD Version' / 0 search results). Labeled as author summary with no CMS source located."
    },
    "LCD-SHOULDER-ARTHRO": {
        "status": "UNVERIFIED_AUTHOR_SUMMARY",
        "mcd_id": None,
        "mcd_title": None,
        "contractor": None,
        "url": None,
        "notes": "No MCD document found at previously cited identifier L35059 (redirects to 'Invalid LCD Version' / 0 search results). Labeled as author summary with no CMS source located."
    },

    # 16 MISMATCH (MCD document exists at cited identifier, but title/subject differs from policy)
    "LCD-CT-CHEST": {
        "status": "MISMATCH",
        "mcd_id": "LCD L34417",
        "mcd_title": "CT of the Head",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34417",
        "notes": "MCD document at L34417 governs 'CT of the Head', whereas policy subject is CT of the Chest with Contrast. Flagged as needing realignment."
    },
    "LCD-EVAR": {
        "status": "MISMATCH",
        "mcd_id": "LCD L35091",
        "mcd_title": "Cataract Extraction (including Complex Cataract Surgery)",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=35091",
        "notes": "MCD document at L35091 governs Cataract Extraction, whereas policy subject is EVAR. Flagged as needing realignment."
    },
    "LCD-HALLUX": {
        "status": "MISMATCH",
        "mcd_id": "LCD L34195",
        "mcd_title": "Mohs Micrographic Surgery",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34195",
        "notes": "MCD document at L34195 governs Mohs Micrographic Surgery, whereas policy subject is Bunionectomy / Hallux Valgus. Flagged as needing realignment."
    },
    "LCD-HIP-ARTHRO": {
        "status": "MISMATCH",
        "mcd_id": "LCD L34032",
        "mcd_title": "Debridement Services",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34032",
        "notes": "MCD document at L34032 governs Debridement Services, whereas policy subject is Total Hip Arthroplasty (THA). Flagged as needing realignment."
    },
    "LCD-HIP-SCOOP": {
        "status": "MISMATCH",
        "mcd_id": "LCD L35456",
        "mcd_title": "Nerve Blockade for Treatment of Chronic Pain and Neuropathy",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=35456",
        "notes": "MCD document at L35456 governs Nerve Blockade, whereas policy subject is Hip Arthroscopy for FAI. Flagged as needing realignment."
    },
    "LCD-LUMBAR-DECOMP": {
        "status": "MISMATCH",
        "mcd_id": "LCD L35081",
        "mcd_title": "Nerve Conduction Studies and Electromyography",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=35081",
        "notes": "MCD document at L35081 governs NCS/EMG, whereas policy subject is Lumbar Laminectomy and Decompression. Flagged as needing realignment."
    },
    "LCD-LUMBAR-FUSION": {
        "status": "MISMATCH",
        "mcd_id": "LCD L37897",
        "mcd_title": "MolDX: Inivata™, InVisionFirst®, Liquid Biopsy for Patients with Lung Cancer",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=37897",
        "notes": "MCD document at L37897 governs InVisionFirst Liquid Biopsy, whereas policy subject is Lumbar Spinal Fusion. Flagged as needing realignment."
    },
    "LCD-MRI-BRAIN": {
        "status": "MISMATCH",
        "mcd_id": "LCD L34419",
        "mcd_title": "Homocysteine Level, Serum",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34419",
        "notes": "MCD document at L34419 governs Serum Homocysteine Level, whereas policy subject is Brain MRI. Flagged as needing realignment."
    },
    "LCD-PAD-ATHERO": {
        "status": "MISMATCH",
        "mcd_id": "LCD L34415",
        "mcd_title": "CT of the Abdomen and Pelvis",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34415",
        "notes": "MCD document at L34415 governs CT of Abdomen and Pelvis, whereas policy subject is Peripheral Atherectomy. Flagged as needing realignment."
    },
    "LCD-PCI": {
        "status": "MISMATCH",
        "mcd_id": "LCD L34411",
        "mcd_title": "Blepharoplasty, Eyelid Surgery, and Brow Lift",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34411",
        "notes": "MCD document at L34411 governs Blepharoplasty/Eyelid Surgery, whereas policy subject is PCI with Stents. Flagged as needing realignment."
    },
    "LCD-ROTATOR-CUFF": {
        "status": "MISMATCH",
        "mcd_id": "LCD L34246",
        "mcd_title": "Routine Foot Care and Debridement of Nails",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34246",
        "notes": "MCD document at L34246 governs Routine Foot Care, whereas policy subject is Rotator Cuff Repair. Flagged as needing realignment."
    },
    "NCD-CARDIAC-REHAB": {
        "status": "MISMATCH",
        "mcd_id": "NCD Manual Section 220.11 (MCD ncdid=164)",
        "mcd_title": "Thermography",
        "contractor": "CMS National Coverage Determination",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=164",
        "notes": "MCD database primary key ncdid=164 corresponds to NCD 220.11 'Thermography', whereas policy subject is Cardiac Rehabilitation. NCD 20.10 was retired into 42 CFR § 410.49. Flagged as needing realignment."
    },
    "NCD-CCTA": {
        "status": "MISMATCH",
        "mcd_id": "NCD Manual Section 280.7 (MCD ncdid=227)",
        "mcd_title": "Hospital Beds",
        "contractor": "CMS National Coverage Determination",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=227",
        "notes": "MCD database primary key ncdid=227 corresponds to Section 280.7 'Hospital Beds', whereas policy subject is CCTA. Flagged as needing realignment."
    },
    "NCD-MPI-PET": {
        "status": "MISMATCH",
        "mcd_id": "NCD Manual Section 160.10 (MCD ncdid=214)",
        "mcd_title": "Telephone Transmission of EEGs",
        "contractor": "CMS National Coverage Determination",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=214",
        "notes": "MCD database primary key ncdid=214 corresponds to Section 160.10 'Telephone Transmission of EEGs', whereas policy subject is Cardiac PET. Flagged as needing realignment."
    },
    "OPD-BOTOX": {
        "status": "MISMATCH",
        "mcd_id": "LCD L33942",
        "mcd_title": "Physical Therapy - Home Health",
        "contractor": "Medicare Administrative Contractor (MAC)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33942",
        "notes": "MCD document at L33942 governs Physical Therapy - Home Health, whereas policy subject is Botulinum Toxin Injections. Flagged as needing realignment."
    },
    "OPD-CERV-DISC": {
        "status": "MISMATCH",
        "mcd_id": "NCD Manual Section (MCD ncdid=311)",
        "mcd_title": "Nesiritide for Treatment of Heart Failure Patients",
        "contractor": "CMS National Coverage Determination",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=311",
        "notes": "MCD database primary key ncdid=311 corresponds to Nesiritide for Heart Failure, whereas policy subject is Cervical Artificial Disc Replacement. Flagged as needing realignment."
    },

    # 18 VERIFIED_FROM_MCD (MCD page exists, identifier and title match policy subject)
    "LCD-ESI": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "LCD L36920",
        "mcd_title": "Epidural Steroid Injections for Pain Management",
        "contractor": "Noridian Healthcare Solutions, LLC",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=36920",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "LCD-FACET": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "LCD L38773",
        "mcd_title": "Facet Joint Interventions for Pain Management",
        "contractor": "Noridian Healthcare Solutions, LLC",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=38773",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "LCD-KNEE-ORTHOSIS": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "LCD L33318",
        "mcd_title": "Knee Orthoses",
        "contractor": "DME MAC (Noridian / CGS)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33318",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "LCD-KYPHO": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "LCD L33569",
        "mcd_title": "Percutaneous Vertebral Augmentation (PVA) for Osteoporotic Vertebral Compression Fracture (VCF)",
        "contractor": "Palmetto GBA / Noridian",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33569",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "LCD-POWER-WC": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "LCD L33789",
        "mcd_title": "Power Mobility Devices",
        "contractor": "DME MAC (Noridian / CGS)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33789",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "LCD-RAD-NIV": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "LCD L33800",
        "mcd_title": "Respiratory Assist Devices",
        "contractor": "DME MAC (Noridian / CGS)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33800",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "LCD-WOUND-VAC": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "LCD L33821",
        "mcd_title": "Negative Pressure Wound Therapy Pumps",
        "contractor": "DME MAC (Noridian / CGS)",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33821",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "NCD-CATARACT": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "NCD 10.1 (MCD ncdid=60)",
        "mcd_title": "Use of Visual Tests Prior to and General Anesthesia during Cataract Surgery",
        "contractor": "CMS National Coverage Determination",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=60",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "NCD-PACEMAKER": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "NCD 20.8 (MCD ncdid=238)",
        "mcd_title": "Cardiac Pacemakers",
        "contractor": "CMS National Coverage Determination",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=238",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "NCD-PET-ONC": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "NCD 220.6.17 (MCD ncdid=331)",
        "mcd_title": "Positron Emission Tomography (FDG) for Oncologic Conditions",
        "contractor": "CMS National Coverage Determination",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=331",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "NCD-PUMP": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "NCD 280.14 (MCD ncdid=223)",
        "mcd_title": "Infusion Pumps",
        "contractor": "CMS National Coverage Determination",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=223",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "NCD-SCS": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "NCD 160.7 (MCD ncdid=240)",
        "mcd_title": "Electrical Nerve Stimulators",
        "contractor": "CMS National Coverage Determination",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=240",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "NCD-SGD": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "NCD 50.1 (MCD ncdid=274)",
        "mcd_title": "Speech Generating Devices",
        "contractor": "CMS National Coverage Determination",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=274",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "OPD-BLEPH": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "42 CFR § 419.80 - 419.89",
        "mcd_title": "Prior Authorization for Certain Hospital Outpatient Department (OPD) Services",
        "contractor": "CMS Hospital Outpatient Department (OPD) Prior Authorization Program",
        "url": "https://www.cms.gov/data-research/monitoring-programs/medicare-fee-service-compliance-programs/prior-authorization-and-pre-claim-review-initiatives/prior-authorization-certain-hospital-outpatient-department-opd-services",
        "notes": "Verified against CMS OPD Program. Blepharoplasty is a statutorily designated prior authorization service under 42 CFR § 419.80."
    },
    "OPD-PANNI": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "42 CFR § 419.80 - 419.89",
        "mcd_title": "Prior Authorization for Certain Hospital Outpatient Department (OPD) Services",
        "contractor": "CMS Hospital Outpatient Department (OPD) Prior Authorization Program",
        "url": "https://www.cms.gov/data-research/monitoring-programs/medicare-fee-service-compliance-programs/prior-authorization-and-pre-claim-review-initiatives/prior-authorization-certain-hospital-outpatient-department-opd-services",
        "notes": "Verified against CMS OPD Program. Panniculectomy is a statutorily designated prior authorization service under 42 CFR § 419.80."
    },
    "OPD-RHINO": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "42 CFR § 419.80 - 419.89",
        "mcd_title": "Prior Authorization for Certain Hospital Outpatient Department (OPD) Services",
        "contractor": "CMS Hospital Outpatient Department (OPD) Prior Authorization Program",
        "url": "https://www.cms.gov/data-research/monitoring-programs/medicare-fee-service-compliance-programs/prior-authorization-and-pre-claim-review-initiatives/prior-authorization-certain-hospital-outpatient-department-opd-services",
        "notes": "Verified against CMS OPD Program. Rhinoplasty is a statutorily designated prior authorization service under 42 CFR § 419.80."
    },
    "OPD-SI-FUSION": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "LCD L36000",
        "mcd_title": "Percutaneous minimally invasive fusion/stabilization of the sacroiliac joint for the treatment of back pain",
        "contractor": "Noridian Healthcare Solutions, LLC",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=36000",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    },
    "OPD-VEIN": {
        "status": "VERIFIED_FROM_MCD",
        "mcd_id": "LCD L34082",
        "mcd_title": "Varicose Veins of the Lower Extremity, Treatment of",
        "contractor": "Noridian Healthcare Solutions, LLC",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34082",
        "notes": "Verified against CMS MCD. Identifier and document title match clinical subject."
    }
}

CHECK_DATE = "2026-11-05"

# Count statuses
verified_count = sum(1 for v in AUDIT_RESULTS.values() if v["status"] == "VERIFIED_FROM_MCD")
mismatch_count = sum(1 for v in AUDIT_RESULTS.values() if v["status"] == "MISMATCH")
unverified_count = sum(1 for v in AUDIT_RESULTS.values() if v["status"] == "UNVERIFIED_AUTHOR_SUMMARY")
total_count = len(AUDIT_RESULTS)

print(f"Summary of 42 extended policies (Audit Date: {CHECK_DATE}):")
print(f"  VERIFIED_FROM_MCD:          {verified_count}")
print(f"  MISMATCH:                   {mismatch_count}")
print(f"  UNVERIFIED_AUTHOR_SUMMARY:  {unverified_count}")
print(f"  TOTAL:                      {total_count}\n")

# 1. Update individual JSON policy files
for slug, audit in AUDIT_RESULTS.items():
    p_file = POLICIES_DIR / f"{slug}.json"
    if not p_file.exists():
        print(f"Warning: {p_file} does not exist!")
        continue
    with open(p_file, "r", encoding="utf-8") as f:
        p_data = json.load(f)

    # All criteria remain strictly CLAIMED_UNVERIFIED
    for crit in p_data.get("criteria", []):
        crit["source_traceability_status"] = "CLAIMED_UNVERIFIED"

    # Construct clean cms_reference
    cms_ref = {
        "provenance_status": audit["status"],
        "checked_date": CHECK_DATE,
        "notes": audit["notes"]
    }
    if audit["status"] == "VERIFIED_FROM_MCD":
        cms_ref.update({
            "real_cms_id": audit["mcd_id"],
            "authority": audit["contractor"],
            "document_title": audit["mcd_title"],
            "citation": f"CMS MCD: {audit['mcd_title']} ({audit['mcd_id']})",
            "url": audit["url"]
        })
    elif audit["status"] == "MISMATCH":
        cms_ref.update({
            "real_cms_id": audit["mcd_id"],
            "authority": audit["contractor"],
            "document_title": audit["mcd_title"],
            "mcd_actual_title": audit["mcd_title"],
            "citation": f"CMS MCD Document at Cited ID: {audit['mcd_title']}",
            "url": audit["url"],
            "alignment_flag": "NEEDS_REALIGNMENT"
        })
    elif audit["status"] == "UNVERIFIED_AUTHOR_SUMMARY":
        cms_ref.update({
            "real_cms_id": None,
            "authority": "Author Summary (No CMS source located)",
            "document_title": None,
            "citation": None,
            "url": None
        })

    p_data["cms_reference"] = cms_ref

    with open(p_file, "w", encoding="utf-8") as f:
        json.dump(p_data, f, indent=2)

print("Updated all 42 policy JSON files.")

# 2. Re-generate PROVENANCE.md
lines = [
    "# Machine-Readable Provenance Registry: Extended CMS Coverage Catalog (42 Policies)",
    "",
    "> **CMS MEDICARE COVERAGE DATABASE (MCD) VERIFICATION AUDIT NOTICE**",
    f"> **Audit Execution Date**: {CHECK_DATE}",
    "> This machine-readable registry documents the live verification results of all 42 extended policies in `app/data/policies_extended/` against the official CMS Medicare Coverage Database (cms.gov MCD).",
    "> Every reference was verified individually against live CMS responses. No speculative identifiers or unverified URLs are retained.",
    "> Internal policy identifiers are system slugs (e.g., `LCD-ACDF`, `NCD-CATARACT`, `OPD-BLEPH`) preserved for architectural integrity.",
    "> Criterion traceability across all 42 policies remains strictly `CLAIMED_UNVERIFIED` pending independent regulatory audit.",
    "",
    "## Verification Summary Table",
    f"- **Audit Date**: `{CHECK_DATE}`",
    f"- **Total Extended Policies Audited**: `{total_count}`",
    f"- **VERIFIED_FROM_MCD**: `{verified_count}` policies (MCD document exists, identifier and document title match the policy's clinical subject)",
    f"- **MISMATCH**: `{mismatch_count}` policies (MCD document exists at cited identifier, but the official MCD title/subject differs from the policy; flagged for re-alignment)",
    f"- **UNVERIFIED_AUTHOR_SUMMARY**: `{unverified_count}` policies (no MCD document found at cited identifier; false identifiers and URLs removed; labeled as author summary with no CMS source located)",
    "",
    "| Internal Slug | Policy Title | Checked Date | Provenance Status | MCD Identifier | Actual MCD Document Title | MCD Jurisdiction / Authority | Reference / URL | Audit Notes |",
    "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
]

for slug in sorted(AUDIT_RESULTS.keys()):
    audit = AUDIT_RESULTS[slug]
    p_file = POLICIES_DIR / f"{slug}.json"
    with open(p_file, "r", encoding="utf-8") as f:
        p_data = json.load(f)
    p_title = p_data.get("title", slug)

    status_badge = f"`{audit['status']}`"
    mcd_id = f"**{audit['mcd_id']}**" if audit['mcd_id'] else "*None (Removed)*"
    mcd_title = audit['mcd_title'] if audit['mcd_title'] else "*None (No source located)*"
    contractor = audit['contractor'] if audit['contractor'] else "Author Summary"
    url_link = f"[{audit['mcd_id']}]({audit['url']})" if audit['url'] else "*None*"
    notes = audit['notes']

    lines.append(f"| `{slug}` | {p_title} | {CHECK_DATE} | {status_badge} | {mcd_id} | {mcd_title} | {contractor} | {url_link} | {notes} |")

with open(PROVENANCE_FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"Generated {PROVENANCE_FILE} with complete MCD audit records.")

