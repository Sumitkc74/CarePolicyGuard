# CarePolicyGuard Extended Catalog Development Evaluation Report

> [!IMPORTANT]
> **DEVELOPMENT NUMBERS ONLY — NOT A HELD-OUT VALIDATION SET**
> **Evaluation Run Date**: 2026-11-05 18:17:18 UTC
> **Catalog Scope**: 42 Extended Policies (Slugs `LCD-ACDF` through `OPD-VEIN`)
> **Dataset Provenance**: `app/data/policies_extended/dev_vignettes_extended.json` (84 synthetic vignettes: 1 clean APPROVED, 1 NEGATIVE per policy)
> **Execution Harness**: `scripts/evaluate_extended_policies.py` (Zero clinical records, zero patient identities, zero held-out v2 evaluation)

## 1. Executive Summary (Development-Only Metrics)

| Evaluation Metric | Development Metric | Total Cases | Target / Status |
| :--- | :--- | :--- | :--- |
| **AUTO Retrieval Top-1 Accuracy** | **100.0%** (84/84) | 84 | Evaluated across 42 clinical domains |
| **AUTO Retrieval Top-3 Accuracy** | **100.0%** (84/84) | 84 | Evaluated across 42 clinical domains |
| **Adjudication Decision Accuracy** | **100.0%** (84/84) | 84 | Evaluated against statutory criteria |

## 2. Per-Policy Performance Breakdown

| Policy ID | Evaluated Cases | Top-1 Retrieval | Top-3 Retrieval | Decision Match | Remaining Discrepancies / Notes |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `LCD-ACDF` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-ACI` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-CT-CHEST` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-ESI` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-EVAR` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-FACET` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-HALLUX` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-HIP-ARTHRO` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-HIP-SCOOP` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-IMRT` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-KNEE-ARTHRO` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-KNEE-ORTHOSIS` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-KYPHO` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-LUMBAR-DECOMP` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-LUMBAR-FUSION` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-MRI-BRAIN` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-MRI-LUMBAR` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-PAD-ATHERO` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-PCI` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-POWER-WC` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-PROTON` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-RAD-NIV` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-ROTATOR-CUFF` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-SBRT` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-SHOULDER-ARTHRO` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `LCD-WOUND-VAC` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `NCD-CARDIAC-REHAB` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `NCD-CATARACT` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `NCD-CCTA` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `NCD-MPI-PET` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `NCD-PACEMAKER` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `NCD-PET-ONC` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `NCD-PUMP` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `NCD-SCS` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `NCD-SGD` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `OPD-BLEPH` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `OPD-BOTOX` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `OPD-CERV-DISC` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `OPD-PANNI` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `OPD-RHINO` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `OPD-SI-FUSION` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |
| `OPD-VEIN` | 2 | 2/2 | 2/2 | 2/2 | None (100% agreement) |

## 3. Retrieval Confusion Matrix (Top-1 Predictions)

The following matrix displays intended target policies versus the actual Top-1 retrieved policy during AUTO discovery.

| Expected Policy | Top-1 Predicted Policy | Occurrences | Match Status |
| :--- | :--- | :---: | :--- |
| `LCD-ACDF` | `LCD-ACDF` | 2 | Exact Match |
| `LCD-ACI` | `LCD-ACI` | 2 | Exact Match |
| `LCD-CT-CHEST` | `LCD-CT-CHEST` | 2 | Exact Match |
| `LCD-ESI` | `LCD-ESI` | 2 | Exact Match |
| `LCD-EVAR` | `LCD-EVAR` | 2 | Exact Match |
| `LCD-FACET` | `LCD-FACET` | 2 | Exact Match |
| `LCD-HALLUX` | `LCD-HALLUX` | 2 | Exact Match |
| `LCD-HIP-ARTHRO` | `LCD-HIP-ARTHRO` | 2 | Exact Match |
| `LCD-HIP-SCOOP` | `LCD-HIP-SCOOP` | 2 | Exact Match |
| `LCD-IMRT` | `LCD-IMRT` | 2 | Exact Match |
| `LCD-KNEE-ARTHRO` | `LCD-KNEE-ARTHRO` | 2 | Exact Match |
| `LCD-KNEE-ORTHOSIS` | `LCD-KNEE-ORTHOSIS` | 2 | Exact Match |
| `LCD-KYPHO` | `LCD-KYPHO` | 2 | Exact Match |
| `LCD-LUMBAR-DECOMP` | `LCD-LUMBAR-DECOMP` | 2 | Exact Match |
| `LCD-LUMBAR-FUSION` | `LCD-LUMBAR-FUSION` | 2 | Exact Match |
| `LCD-MRI-BRAIN` | `LCD-MRI-BRAIN` | 2 | Exact Match |
| `LCD-MRI-LUMBAR` | `LCD-MRI-LUMBAR` | 2 | Exact Match |
| `LCD-PAD-ATHERO` | `LCD-PAD-ATHERO` | 2 | Exact Match |
| `LCD-PCI` | `LCD-PCI` | 2 | Exact Match |
| `LCD-POWER-WC` | `LCD-POWER-WC` | 2 | Exact Match |
| `LCD-PROTON` | `LCD-PROTON` | 2 | Exact Match |
| `LCD-RAD-NIV` | `LCD-RAD-NIV` | 2 | Exact Match |
| `LCD-ROTATOR-CUFF` | `LCD-ROTATOR-CUFF` | 2 | Exact Match |
| `LCD-SBRT` | `LCD-SBRT` | 2 | Exact Match |
| `LCD-SHOULDER-ARTHRO` | `LCD-SHOULDER-ARTHRO` | 2 | Exact Match |
| `LCD-WOUND-VAC` | `LCD-WOUND-VAC` | 2 | Exact Match |
| `NCD-CARDIAC-REHAB` | `NCD-CARDIAC-REHAB` | 2 | Exact Match |
| `NCD-CATARACT` | `NCD-CATARACT` | 2 | Exact Match |
| `NCD-CCTA` | `NCD-CCTA` | 2 | Exact Match |
| `NCD-MPI-PET` | `NCD-MPI-PET` | 2 | Exact Match |
| `NCD-PACEMAKER` | `NCD-PACEMAKER` | 2 | Exact Match |
| `NCD-PET-ONC` | `NCD-PET-ONC` | 2 | Exact Match |
| `NCD-PUMP` | `NCD-PUMP` | 2 | Exact Match |
| `NCD-SCS` | `NCD-SCS` | 2 | Exact Match |
| `NCD-SGD` | `NCD-SGD` | 2 | Exact Match |
| `OPD-BLEPH` | `OPD-BLEPH` | 2 | Exact Match |
| `OPD-BOTOX` | `OPD-BOTOX` | 2 | Exact Match |
| `OPD-CERV-DISC` | `OPD-CERV-DISC` | 2 | Exact Match |
| `OPD-PANNI` | `OPD-PANNI` | 2 | Exact Match |
| `OPD-RHINO` | `OPD-RHINO` | 2 | Exact Match |
| `OPD-SI-FUSION` | `OPD-SI-FUSION` | 2 | Exact Match |
| `OPD-VEIN` | `OPD-VEIN` | 2 | Exact Match |

## 4. Policy Traceability and Audit Integrity

- **Criteria Provenance Status**: All 126 criteria across the 42 extended policies remain explicitly categorized as `CLAIMED_UNVERIFIED`.
- **Statutory References**: Machine-readable CMS manual sections, LCD numbers, and 42 CFR citations are cataloged in `app/data/policies_extended/PROVENANCE.md`.
- **Retriever Concept Coverage**: The dense semantic vocabulary covers all 42 extended clinical domains in `app/services/hybrid_retriever.py` with zero reliance on placeholder defaults.
- **Resilient Fallback**: Fallback chunks cover all 50 policies when the database is unseeded.
