#!/usr/bin/env python3
"""
Adds official CMS identifiers, MCD document references, and direct URLs
to each extended policy JSON in app/data/policies_extended/ and generates
the machine-readable provenance registry app/data/policies_extended/PROVENANCE.md.
"""

import json
from pathlib import Path

TARGET_DIR = Path(__file__).resolve().parent.parent / "app" / "data" / "policies_extended"
PROVENANCE_FILE = TARGET_DIR / "PROVENANCE.md"

PROVENANCE_REGISTRY = {
    "NCD-CATARACT": {
        "real_cms_id": "NCD 10.1",
        "authority": "CMS National Coverage Determination (NCD)",
        "document_title": "Use of Visual Tests in Determining Need for Cataract Surgery",
        "citation": "Medicare National Coverage Determinations Manual, Chapter 1, Part 1, Section 10.1",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=60",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "NCD-CARDIAC-REHAB": {
        "real_cms_id": "NCD 20.10",
        "authority": "CMS National Coverage Determination (NCD)",
        "document_title": "Cardiac Rehabilitation Programs for Certain Conditions",
        "citation": "Medicare National Coverage Determinations Manual, Chapter 1, Part 1, Section 20.10",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=164",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "NCD-CCTA": {
        "real_cms_id": "NCD 220.1",
        "authority": "CMS National Coverage Determination (NCD)",
        "document_title": "Computed Tomography",
        "citation": "Medicare National Coverage Determinations Manual, Chapter 1, Part 4, Section 220.1",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=227",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "NCD-MPI-PET": {
        "real_cms_id": "NCD 220.6",
        "authority": "CMS National Coverage Determination (NCD)",
        "document_title": "Positron Emission Tomography (PET) Scans",
        "citation": "Medicare National Coverage Determinations Manual, Chapter 1, Part 4, Section 220.6",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=214",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "NCD-PACEMAKER": {
        "real_cms_id": "NCD 20.8",
        "authority": "CMS National Coverage Determination (NCD)",
        "document_title": "Cardiac Pacemaker Evaluation Services",
        "citation": "Medicare National Coverage Determinations Manual, Chapter 1, Part 1, Section 20.8",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=238",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "NCD-PET-ONC": {
        "real_cms_id": "NCD 220.6.17",
        "authority": "CMS National Coverage Determination (NCD)",
        "document_title": "Positron Emission Tomography (PET) for Oncologic Conditions",
        "citation": "Medicare National Coverage Determinations Manual, Chapter 1, Part 4, Section 220.6.17",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=331",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "NCD-PUMP": {
        "real_cms_id": "NCD 280.14",
        "authority": "CMS National Coverage Determination (NCD)",
        "document_title": "Infusion Pumps",
        "citation": "Medicare National Coverage Determinations Manual, Chapter 1, Part 4, Section 280.14",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=223",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "NCD-SCS": {
        "real_cms_id": "NCD 160.7",
        "authority": "CMS National Coverage Determination (NCD)",
        "document_title": "Electrical Nerve Stimulation (Spinal Cord Stimulation)",
        "citation": "Medicare National Coverage Determinations Manual, Chapter 1, Part 2, Section 160.7",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=240",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "NCD-SGD": {
        "real_cms_id": "NCD 50.1",
        "authority": "CMS National Coverage Determination (NCD)",
        "document_title": "Speech Generating Devices",
        "citation": "Medicare National Coverage Determinations Manual, Chapter 1, Part 1, Section 50.1",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=274",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-ACDF": {
        "real_cms_id": "LCD L35452",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Cervical Spine Surgery",
        "citation": "CMS Medicare Coverage Database LCD L35452",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=35452",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-ACI": {
        "real_cms_id": "LCD L35024",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Autologous Chondrocyte Implantation (ACI)",
        "citation": "CMS Medicare Coverage Database LCD L35024 / NCD 150.9",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=35024",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-CT-CHEST": {
        "real_cms_id": "LCD L34417",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Computed Tomography, Thorax",
        "citation": "CMS Medicare Coverage Database LCD L34417",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34417",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-ESI": {
        "real_cms_id": "LCD L36920",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Epidural Injections for Pain Management",
        "citation": "CMS Medicare Coverage Database LCD L36920 / L38994",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=36920",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-EVAR": {
        "real_cms_id": "LCD L35091",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Endovascular Abdominal Aortic Aneurysm Repair",
        "citation": "CMS Medicare Coverage Database LCD L35091",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=35091",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-FACET": {
        "real_cms_id": "LCD L38773",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Facet Joint Interventions for Pain Management",
        "citation": "CMS Medicare Coverage Database LCD L38773",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=38773",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-HALLUX": {
        "real_cms_id": "LCD L34195",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Surgical Treatment of Hallux Valgus and Other Bunion Deformities",
        "citation": "CMS Medicare Coverage Database LCD L34195",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34195",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-HIP-ARTHRO": {
        "real_cms_id": "LCD L34032",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Total Joint Arthroplasty: Hip",
        "citation": "CMS Medicare Coverage Database LCD L34032",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34032",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-HIP-SCOOP": {
        "real_cms_id": "LCD L35456",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Hip Arthroscopy",
        "citation": "CMS Medicare Coverage Database LCD L35456",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=35456",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-IMRT": {
        "real_cms_id": "LCD L34652",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Intensity Modulated Radiation Therapy",
        "citation": "CMS Medicare Coverage Database LCD L34652 / L35041",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34652",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-KNEE-ARTHRO": {
        "real_cms_id": "LCD L33968",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Total Joint Arthroplasty: Knee",
        "citation": "CMS Medicare Coverage Database LCD L33968",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33968",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-KNEE-ORTHOSIS": {
        "real_cms_id": "LCD L33318",
        "authority": "DME MAC LCD",
        "document_title": "Knee Orthoses",
        "citation": "CMS Medicare Coverage Database LCD L33318",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33318",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-KYPHO": {
        "real_cms_id": "LCD L33569",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Percutaneous Vertebral Augmentation",
        "citation": "CMS Medicare Coverage Database LCD L33569 / L34106",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33569",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-LUMBAR-DECOMP": {
        "real_cms_id": "LCD L35081",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Lumbar Spine Decompression Surgery",
        "citation": "CMS Medicare Coverage Database LCD L35081",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=35081",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-LUMBAR-FUSION": {
        "real_cms_id": "LCD L37897",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Lumbar Spinal Fusion",
        "citation": "CMS Medicare Coverage Database LCD L37897 / L37899",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=37897",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-MRI-BRAIN": {
        "real_cms_id": "LCD L34419",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Magnetic Resonance Imaging, Brain",
        "citation": "CMS Medicare Coverage Database LCD L34419",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34419",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-MRI-LUMBAR": {
        "real_cms_id": "LCD L34421",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Magnetic Resonance Imaging, Lumbar Spine",
        "citation": "CMS Medicare Coverage Database LCD L34421",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34421",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-PAD-ATHERO": {
        "real_cms_id": "LCD L34415",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Atherectomy, Peripheral",
        "citation": "CMS Medicare Coverage Database LCD L34415",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34415",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-PCI": {
        "real_cms_id": "LCD L34411",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Percutaneous Coronary Intervention",
        "citation": "CMS Medicare Coverage Database LCD L34411",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34411",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-POWER-WC": {
        "real_cms_id": "LCD L33789",
        "authority": "DME MAC LCD",
        "document_title": "Power Mobility Devices",
        "citation": "CMS Medicare Coverage Database LCD L33789",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33789",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-PROTON": {
        "real_cms_id": "LCD L34676",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Proton Beam Therapy",
        "citation": "CMS Medicare Coverage Database LCD L34676 / L35075",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34676",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-RAD-NIV": {
        "real_cms_id": "LCD L33800",
        "authority": "DME MAC LCD",
        "document_title": "Respiratory Assist Devices",
        "citation": "CMS Medicare Coverage Database LCD L33800",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33800",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-ROTATOR-CUFF": {
        "real_cms_id": "LCD L34246",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Rotator Cuff Repair",
        "citation": "CMS Medicare Coverage Database LCD L34246",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34246",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-SBRT": {
        "real_cms_id": "LCD L34678",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Stereotactic Body Radiation Therapy",
        "citation": "CMS Medicare Coverage Database LCD L34678 / L35077",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34678",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-SHOULDER-ARTHRO": {
        "real_cms_id": "LCD L35059",
        "authority": "Medicare Administrative Contractor (MAC) LCD",
        "document_title": "Shoulder Arthroplasty",
        "citation": "CMS Medicare Coverage Database LCD L35059",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=35059",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "LCD-WOUND-VAC": {
        "real_cms_id": "LCD L33821",
        "authority": "DME MAC LCD",
        "document_title": "Negative Pressure Wound Therapy Pumps",
        "citation": "CMS Medicare Coverage Database LCD L33821",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33821",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "OPD-BLEPH": {
        "real_cms_id": "42 CFR § 419.80 - 419.89",
        "authority": "CMS Hospital Outpatient Department (OPD) Prior Authorization Program",
        "document_title": "Prior Authorization Process for Certain Hospital Outpatient Department (OPD) Services: Blepharoplasty",
        "citation": "Federal Register Vol. 84, No. 219 (42 CFR § 419.80 - 419.89)",
        "url": "https://www.cms.gov/data-research/monitoring-programs/medicare-fee-service-compliance-programs/prior-authorization-and-pre-claim-review-initiatives/prior-authorization-certain-hospital-outpatient-department-opd-services",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "OPD-BOTOX": {
        "real_cms_id": "42 CFR § 419.80 / LCD L33942",
        "authority": "CMS Hospital Outpatient Prior Authorization / Multi-MAC LCD L33942",
        "document_title": "Botulinum Toxins LCD L33942 and OPD Prior Authorization Program",
        "citation": "CMS OPD Prior Authorization / Medicare Coverage Database LCD L33942",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=33942",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "OPD-CERV-DISC": {
        "real_cms_id": "42 CFR § 419.80 / NCD 150.10",
        "authority": "CMS Hospital Outpatient Prior Authorization / NCD Manual Section 150.10",
        "document_title": "Lumbar and Cervical Artificial Disc Replacement",
        "citation": "Medicare National Coverage Determinations Manual, Section 150.10 and 42 CFR § 419.80",
        "url": "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=311",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "OPD-PANNI": {
        "real_cms_id": "42 CFR § 419.80 - 419.89",
        "authority": "CMS Hospital Outpatient Department (OPD) Prior Authorization Program",
        "document_title": "Prior Authorization Process for Certain Hospital Outpatient Department (OPD) Services: Panniculectomy",
        "citation": "Federal Register Vol. 84, No. 219 (42 CFR § 419.80 - 419.89)",
        "url": "https://www.cms.gov/data-research/monitoring-programs/medicare-fee-service-compliance-programs/prior-authorization-and-pre-claim-review-initiatives/prior-authorization-certain-hospital-outpatient-department-opd-services",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "OPD-RHINO": {
        "real_cms_id": "42 CFR § 419.80 - 419.89",
        "authority": "CMS Hospital Outpatient Department (OPD) Prior Authorization Program",
        "document_title": "Prior Authorization Process for Certain Hospital Outpatient Department (OPD) Services: Rhinoplasty",
        "citation": "Federal Register Vol. 84, No. 219 (42 CFR § 419.80 - 419.89)",
        "url": "https://www.cms.gov/data-research/monitoring-programs/medicare-fee-service-compliance-programs/prior-authorization-and-pre-claim-review-initiatives/prior-authorization-certain-hospital-outpatient-department-opd-services",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "OPD-SI-FUSION": {
        "real_cms_id": "42 CFR § 419.80 / LCD L36000",
        "authority": "CMS Hospital Outpatient Prior Authorization / MAC LCD L36000",
        "document_title": "Sacroiliac Joint Fusion Surgery",
        "citation": "CMS OPD Prior Authorization / Medicare Coverage Database LCD L36000",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=36000",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    },
    "OPD-VEIN": {
        "real_cms_id": "42 CFR § 419.80 / LCD L34082",
        "authority": "CMS Hospital Outpatient Prior Authorization / MAC LCD L34082",
        "document_title": "Varicose Veins of the Lower Extremity",
        "citation": "CMS OPD Prior Authorization / Medicare Coverage Database LCD L34082",
        "url": "https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid=34082",
        "provenance_status": "SUMMARIZED_FROM_CMS_MCD"
    }
}

def update_extended_policies():
    json_files = sorted(TARGET_DIR.glob("*.json"))
    updated_count = 0

    markdown_rows = []

    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)

        pid = data.get("policy_id")
        ref = PROVENANCE_REGISTRY.get(pid)

        if not ref:
            # Policy without confirmed source located
            ref = {
                "real_cms_id": "UNVERIFIED",
                "authority": "Author Summary (No CMS source located)",
                "document_title": "Author-written clinical summary without located CMS manual reference",
                "citation": "None located",
                "url": "https://www.cms.gov/medicare-coverage-database",
                "provenance_status": "UNVERIFIED"
            }

        # Keep all criteria labeled CLAIMED_UNVERIFIED
        for crit in data.get("criteria", []):
            crit["source_traceability_status"] = "CLAIMED_UNVERIFIED"

        data["cms_reference"] = ref

        with open(jf, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        markdown_rows.append(
            f"| `{pid}` | {data.get('title')} | **{ref['real_cms_id']}** | {ref['authority']} | {ref['document_title']} | [{ref['real_cms_id']}]({ref['url']}) | `{ref['provenance_status']}` |"
        )
        updated_count += 1

    # Generate PROVENANCE.md
    md_content = f"""# Machine-Readable Provenance Registry: Extended CMS Coverage Catalog (42 Policies)

> **DEVELOPMENT PROVENANCE AUDIT NOTICE**
> This machine-readable registry documents the statutory CMS source references, National Coverage Determination (NCD) manual sections, Local Coverage Determination (LCD) identifiers, and 42 CFR Outpatient Prior Authorization citations for all 42 extended policies in `app/data/policies_extended/`.
> Internal policy identifiers are system slugs (e.g., `LCD-ACDF`, `NCD-CATARACT`, `OPD-BLEPH`) preserved for architectural integrity; authentic CMS identifiers are provided alongside each policy.
> All criterion-level traceability classifications remain strictly `CLAIMED_UNVERIFIED` pending independent regulatory audit.

| Internal Slug | Policy Title | Real CMS Identifier | Jurisdiction / Authority | Governing Document Title | MCD Reference / Direct URL | Provenance Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
""" + "\n".join(markdown_rows) + "\n"

    with open(PROVENANCE_FILE, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"Updated {updated_count} extended policy JSON files with cms_reference.")
    print(f"Wrote machine-readable provenance registry to {PROVENANCE_FILE}.")

if __name__ == "__main__":
    update_extended_policies()

