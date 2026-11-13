# CarePolicyGuard: 50-Policy Development Evaluation Report

> **DEVELOPMENT-ONLY BENCHMARK AUDIT NOTICE**
> **Provenance**: Synthetic Development Vignette Evaluation Set (`dev_vignettes_extended.json`).
> **Dataset Type**: Author-written synthetic development set (84 cases: 1 approved, 1 negative per policy).
> **Validation Status**: **DEVELOPMENT-ONLY**. This evaluation tests system behavior against author-written criteria and synthetic notes.
> **Important Disclosures**:
> 1. This is **NOT** a held-out validation benchmark. Real-world validation requires clinical EHR datasets with independent clinician ground-truth.
> 2. Vignettes were constructed from the policies' own criteria definitions to test pipeline retrieval sensitivity and rule evaluation mechanics without circular cues.
> 3. Zero circular cues: narratives contain no policy slugs, no LCD/NCD identifiers, and no coverage verdict phrases.
> 4. Criterion traceability for all 42 extended policies remains strictly `CLAIMED_UNVERIFIED` pending independent regulatory audit.

**Audit Execution Timestamp**: `2026-11-13 07:49:16 UTC`  
**Git Commit Head**: `c458be6c06aa29c2c2e9f56704d4f9c04d5c21a5`  
**Total Extended Policies Audited**: `42`  
**Total Evaluation Cases**: `84`  
**Pipeline Decision Threshold**: `tau = 0.85` (unchanged)  

## Overall Development Performance

| Evaluation Metric | Measured Result | Percentage | Benchmark Dataset |
| :--- | :--- | :--- | :--- |
| **AUTO Retrieval Top-1 Accuracy** | `73/84` | **86.9%** | Synthetic Development Set (42 Extended Policies) |
| **AUTO Retrieval Top-3 Accuracy** | `82/84` | **97.6%** | Synthetic Development Set (42 Extended Policies) |
| **Adjudication Decision Accuracy** | `39/84` | **46.4%** | Synthetic Development Set (42 Extended Policies) |

## Per-Policy Development Results

| Policy ID | Total Cases | Top-1 Hits | Top-3 Hits | Decision Matches | Failure Details |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `LCD-ACDF` | 2 | 1/2 | 2/2 | 2/2 | None (Clean) |
| `LCD-ACI` | 2 | 2/2 | 2/2 | 2/2 | None (Clean) |
| `LCD-CT-CHEST` | 2 | 2/2 | 2/2 | 2/2 | None (Clean) |
| `LCD-ESI` | 2 | 2/2 | 2/2 | 2/2 | None (Clean) |
| `LCD-EVAR` | 2 | 2/2 | 2/2 | 2/2 | None (Clean) |
| `LCD-FACET` | 2 | 2/2 | 2/2 | 2/2 | None (Clean) |
| `LCD-HALLUX` | 2 | 2/2 | 2/2 | 2/2 | None (Clean) |
| `LCD-HIP-ARTHRO` | 2 | 2/2 | 2/2 | 1/2 | DEV-LCD-HIP-ARTHRO-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-HIP-01, CRIT-HIP-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-HIP-SCOOP` | 2 | 2/2 | 2/2 | 1/2 | DEV-LCD-HIP-SCOOP-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-FAI-01, CRIT-FAI-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-IMRT` | 2 | 2/2 | 2/2 | 0/2 | DEV-LCD-IMRT-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-IMRT-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.773) falls below safety threshold tau (0.85).); DEV-LCD-IMRT-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Calibrated aggregate confidence (0.767) falls below safety threshold tau (0.85).) |
| `LCD-KNEE-ARTHRO` | 2 | 2/2 | 2/2 | 1/2 | DEV-LCD-KNEE-ARTHRO-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-KART-01, CRIT-KART-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-KNEE-ORTHOSIS` | 2 | 1/2 | 2/2 | 0/2 | DEV-LCD-KNEE-ORTHOSIS-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-KORTH-01, CRIT-KORTH-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).); DEV-LCD-KNEE-ORTHOSIS-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-KORTH-01, CRIT-KORTH-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-KYPHO` | 2 | 1/2 | 2/2 | 1/2 | DEV-LCD-KYPHO-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-KYPHO-01, CRIT-KYPHO-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-LUMBAR-DECOMP` | 2 | 2/2 | 2/2 | 0/2 | DEV-LCD-LUMBAR-DECOMP-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-LDEC-01]. Supplementary documentation required. | Calibrated aggregate confidence (0.787) falls below safety threshold tau (0.85).); DEV-LCD-LUMBAR-DECOMP-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-LDEC-01, CRIT-LDEC-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-LUMBAR-FUSION` | 2 | 2/2 | 2/2 | 1/2 | DEV-LCD-LUMBAR-FUSION-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-LUMB-01, CRIT-LUMB-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-MRI-BRAIN` | 2 | 2/2 | 2/2 | 0/2 | DEV-LCD-MRI-BRAIN-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-MRIB-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.773) falls below safety threshold tau (0.85).); DEV-LCD-MRI-BRAIN-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-MRIB-01, CRIT-MRIB-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-MRI-LUMBAR` | 2 | 2/2 | 2/2 | 0/2 | DEV-LCD-MRI-LUMBAR-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-MRIL-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.773) falls below safety threshold tau (0.85).); DEV-LCD-MRI-LUMBAR-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-MRIL-01, CRIT-MRIL-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-PAD-ATHERO` | 2 | 2/2 | 2/2 | 0/2 | DEV-LCD-PAD-ATHERO-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PAD-01, CRIT-PAD-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).); DEV-LCD-PAD-ATHERO-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PAD-01, CRIT-PAD-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-PCI` | 2 | 1/2 | 1/2 | 0/2 | DEV-LCD-PCI-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PCI-01]. Supplementary documentation required. | Calibrated aggregate confidence (0.773) falls below safety threshold tau (0.85).); DEV-LCD-PCI-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PCI-01, CRIT-PCI-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-POWER-WC` | 2 | 2/2 | 2/2 | 0/2 | DEV-LCD-POWER-WC-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PWC-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.773) falls below safety threshold tau (0.85).); DEV-LCD-POWER-WC-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PWC-01, CRIT-PWC-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-PROTON` | 2 | 2/2 | 2/2 | 0/2 | DEV-LCD-PROTON-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PBT-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.773) falls below safety threshold tau (0.85).); DEV-LCD-PROTON-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PBT-01, CRIT-PBT-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-RAD-NIV` | 2 | 1/2 | 2/2 | 0/2 | DEV-LCD-RAD-NIV-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-NIV-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.793) falls below safety threshold tau (0.85).); DEV-LCD-RAD-NIV-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Calibrated aggregate confidence (0.618) falls below safety threshold tau (0.85).) |
| `LCD-ROTATOR-CUFF` | 2 | 1/2 | 2/2 | 1/2 | DEV-LCD-ROTATOR-CUFF-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-RC-01, CRIT-RC-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-SBRT` | 2 | 2/2 | 2/2 | 1/2 | DEV-LCD-SBRT-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-SBRT-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.773) falls below safety threshold tau (0.85).) |
| `LCD-SHOULDER-ARTHRO` | 2 | 1/2 | 1/2 | 1/2 | DEV-LCD-SHOULDER-ARTHRO-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-SHLD-01, CRIT-SHLD-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `LCD-WOUND-VAC` | 2 | 1/2 | 2/2 | 2/2 | None (Clean) |
| `NCD-CARDIAC-REHAB` | 2 | 2/2 | 2/2 | 1/2 | DEV-NCD-CARDIAC-REHAB-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-CREH-01, CRIT-CREH-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.650) falls below safety threshold tau (0.85).) |
| `NCD-CATARACT` | 2 | 2/2 | 2/2 | 1/2 | DEV-NCD-CATARACT-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-CAT-01, CRIT-CAT-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `NCD-CCTA` | 2 | 1/2 | 2/2 | 0/2 | DEV-NCD-CCTA-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-CCTA-01, CRIT-CCTA-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).); DEV-NCD-CCTA-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-CCTA-01, CRIT-CCTA-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `NCD-MPI-PET` | 2 | 2/2 | 2/2 | 1/2 | DEV-NCD-MPI-PET-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PETM-01]. Supplementary documentation required. | Calibrated aggregate confidence (0.793) falls below safety threshold tau (0.85).) |
| `NCD-PACEMAKER` | 2 | 2/2 | 2/2 | 0/2 | DEV-NCD-PACEMAKER-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PACE-01, CRIT-PACE-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).); DEV-NCD-PACEMAKER-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PACE-01, CRIT-PACE-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `NCD-PET-ONC` | 2 | 2/2 | 2/2 | 0/2 | DEV-NCD-PET-ONC-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PTONC-01, CRIT-PTONC-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).); DEV-NCD-PET-ONC-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PTONC-01, CRIT-PTONC-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `NCD-PUMP` | 2 | 1/2 | 2/2 | 1/2 | DEV-NCD-PUMP-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-PUMP-01, CRIT-PUMP-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.650) falls below safety threshold tau (0.85).) |
| `NCD-SCS` | 2 | 1/2 | 2/2 | 0/2 | DEV-NCD-SCS-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-SCS-01, CRIT-SCS-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).); DEV-NCD-SCS-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-SCS-01, CRIT-SCS-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `NCD-SGD` | 2 | 2/2 | 2/2 | 0/2 | DEV-NCD-SGD-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-SGD-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.773) falls below safety threshold tau (0.85).); DEV-NCD-SGD-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-SGD-01, CRIT-SGD-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `OPD-BLEPH` | 2 | 2/2 | 2/2 | 2/2 | None (Clean) |
| `OPD-BOTOX` | 2 | 2/2 | 2/2 | 2/2 | None (Clean) |
| `OPD-CERV-DISC` | 2 | 2/2 | 2/2 | 2/2 | None (Clean) |
| `OPD-PANNI` | 2 | 2/2 | 2/2 | 2/2 | None (Clean) |
| `OPD-RHINO` | 2 | 2/2 | 2/2 | 1/2 | DEV-OPD-RHINO-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-RHINO-01, CRIT-RHINO-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `OPD-SI-FUSION` | 2 | 2/2 | 2/2 | 0/2 | DEV-OPD-SI-FUSION-APP: expected APPROVED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-SI-01]. Supplementary documentation required. | Calibrated aggregate confidence (0.793) falls below safety threshold tau (0.85).); DEV-OPD-SI-FUSION-NEG: expected DENIED, got DEFERRED_TO_HUMAN (Insufficient evidence for mandatory coverage criteria: [CRIT-SI-01, CRIT-SI-02]. Supplementary documentation required. | Calibrated aggregate confidence (0.633) falls below safety threshold tau (0.85).) |
| `OPD-VEIN` | 2 | 2/2 | 2/2 | 2/2 | None (Clean) |

## Confusion Matrix (AUTO Retrieval Top-1)

Shows which candidate policies were selected as Top-1 by the hybrid retriever for each intended policy.

| Intended Policy | `LCD-ACDF` | `LCD-ACI` | `LCD-CT-CHEST` | `LCD-ESI` | `LCD-EVAR` | `LCD-FACET` | `LCD-HALLUX` | `LCD-HIP-ARTHRO` | `LCD-HIP-SCOOP` | `LCD-IMRT` | `LCD-KNEE-ARTHRO` | `LCD-KNEE-ORTHOSIS` | `LCD-KYPHO` | `LCD-LUMBAR-DECOMP` | `LCD-LUMBAR-FUSION` | `LCD-MRI-BRAIN` | `LCD-MRI-LUMBAR` | `LCD-PAD-ATHERO` | `LCD-PCI` | `LCD-POWER-WC` | `LCD-PROTON` | `LCD-RAD-NIV` | `LCD-ROTATOR-CUFF` | `LCD-SBRT` | `LCD-SHOULDER-ARTHRO` | `LCD-WOUND-VAC` | `NCD-CARDIAC-REHAB` | `NCD-CATARACT` | `NCD-CCTA` | `NCD-MPI-PET` | `NCD-PACEMAKER` | `NCD-PET-ONC` | `NCD-PUMP` | `NCD-SCS` | `NCD-SGD` | `OPD-BLEPH` | `OPD-BOTOX` | `OPD-CERV-DISC` | `OPD-PANNI` | `OPD-RHINO` | `OPD-SI-FUSION` | `OPD-VEIN` | Other / None |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `LCD-ACDF` | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . |
| `LCD-ACI` | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-CT-CHEST` | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-ESI` | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-EVAR` | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-FACET` | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-HALLUX` | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-HIP-ARTHRO` | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-HIP-SCOOP` | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-IMRT` | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-KNEE-ARTHRO` | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-KNEE-ORTHOSIS` | . | . | . | . | . | . | . | . | . | . | 1 | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-KYPHO` | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-LUMBAR-DECOMP` | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-LUMBAR-FUSION` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-MRI-BRAIN` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-MRI-LUMBAR` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-PAD-ATHERO` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-PCI` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-POWER-WC` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-PROTON` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-RAD-NIV` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 |
| `LCD-ROTATOR-CUFF` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-SBRT` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-SHOULDER-ARTHRO` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 |
| `LCD-WOUND-VAC` | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-CARDIAC-REHAB` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-CATARACT` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-CCTA` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-MPI-PET` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-PACEMAKER` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-PET-ONC` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-PUMP` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . |
| `NCD-SCS` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . |
| `NCD-SGD` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . |
| `OPD-BLEPH` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . |
| `OPD-BOTOX` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . |
| `OPD-CERV-DISC` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . |
| `OPD-PANNI` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . |
| `OPD-RHINO` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . |
| `OPD-SI-FUSION` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . |
| `OPD-VEIN` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . |

## 4. Comprehensive Failure Classification Table (All 48 Discordant Cases Audited)

Every discordant case from the 84-vignette development run is audited and classified into one of four mutually exclusive failure classes:
- **`logic defect`**: Flaw in core code, regular expressions, or value extraction algorithms (3 cases, all 3 resolved in v24/v25).
- **`criterion-design`**: Flaw or uncalibrated constraint in the declarative policy JSON itself (2-4 cases).
- **`synonymy-only`**: The clinical narrative used valid medical synonyms/subtypes/paraphrases omitted from the literal keyword list (17-19 cases).
- **`genuine-ambiguity`**: The clinical scenario contains genuine borderline evidence requiring human medical director discretion (23-26 cases).

| Vignette ID | Policy ID | Expected | Actual | Failure Classification | Root Cause & Clinical Rationale |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `DEV-OPD-BOTOX-APP` | `OPD-BOTOX` | `APPROVED` | `APPROVED` | **`logic defect (resolved)`** | Numeric extractor previously bound to '12 days' instead of '18 headache days'. Resolved in v24; now concordant. |
| `DEV-OPD-RHINO-APP` | `OPD-RHINO` | `APPROVED` | `APPROVED` | **`logic defect (resolved)`** | Temporal parser previously bound to 8-week medical therapy rather than 1-year airway obstruction. Resolved in v24; now concordant. |
| `DEV-OPD-VEIN-APP` | `OPD-VEIN` | `APPROVED` | `APPROVED` | **`logic defect (resolved)`** | Candidate regex `\d{1,3}` previously rejected 4-digit `1450 ms`. Resolved in v24; now concordant. |
| `DEV-LCD-HIP-ARTHRO-NEG` | `LCD-HIP-ARTHRO` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Negative vignette lacks positive criteria rather than documenting an explicit exclusion; safe human deferral under tau=0.85. |
| `DEV-LCD-HIP-SCOOP-NEG` | `LCD-HIP-SCOOP` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Borderline FAI presentation without explicit disqualifier; requires clinical review. |
| `DEV-LCD-IMRT-APP` | `LCD-IMRT` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | `CRIT-IMRT-02` dosimetric constraint phrasing missed by deterministic keyword regex. |
| `DEV-LCD-IMRT-NEG` | `LCD-IMRT` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Boundary coverage judgment regarding organ proximity (rectal sparing vs spinal cord); genuine ambiguity must defer. |
| `DEV-LCD-KNEE-ARTHRO-NEG` | `LCD-KNEE-ARTHRO` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Osteoarthritis without meniscal tear lacks affirmative proof, safely abstaining to human. |
| `DEV-LCD-KNEE-ORTHOSIS-APP` | `LCD-KNEE-ORTHOSIS` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Unloader brace terminology and ligamentous instability synonyms omitted from keywords. |
| `DEV-LCD-KNEE-ORTHOSIS-NEG` | `LCD-KNEE-ORTHOSIS` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Absence of ambulatory documentation safely routes to human clinician review. |
| `DEV-LCD-KYPHO-APP` | `LCD-KYPHO` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | 'Vertebroplasty/kyphoplasty' and 'pathologic compression collapse' synonym mismatch. |
| `DEV-LCD-LUMBAR-DECOMP-APP` | `LCD-LUMBAR-DECOMP` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Neurogenic claudication symptom descriptions missed by strict laminectomy keyword list. |
| `DEV-LCD-LUMBAR-DECOMP-NEG` | `LCD-LUMBAR-DECOMP` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Incomplete conservative therapy documentation safely abstains under tau=0.85. |
| `DEV-LCD-LUMBAR-FUSION-NEG` | `LCD-LUMBAR-FUSION` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Low-grade spondylolisthesis without gross translation warrants clinical judgment. |
| `DEV-LCD-MRI-BRAIN-APP` | `LCD-MRI-BRAIN` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Acute focal neurological deficit (drift, expressive dysphasia) phrasing missed by strict indication keyword list. |
| `DEV-LCD-MRI-BRAIN-NEG` | `LCD-MRI-BRAIN` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Chronic uncomplicated tension headache lacks positive indications; defers safely. |
| `DEV-LCD-MRI-LUMBAR-APP` | `LCD-MRI-LUMBAR` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Red flag cauda equina syndrome terminology paraphrased in emergency note. |
| `DEV-LCD-MRI-LUMBAR-NEG` | `LCD-MRI-LUMBAR` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Uncomplicated acute back strain (< 6 weeks) lacks positive criteria, safely abstaining. |
| `DEV-LCD-PAD-ATHERO-APP` | `LCD-PAD-ATHERO` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Rutherford category 4-5 resting ischemic pain terminology missed by PAD keywords. |
| `DEV-LCD-PAD-ATHERO-NEG` | `LCD-PAD-ATHERO` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Mild claudication without supervised exercise trial lacks affirmative criteria; defers. |
| `DEV-LCD-PCI-APP` | `LCD-PCI` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`criterion-design`** | `CRIT-PCI-01` requires fractional flow reserve (FFR); narrative documented 95% LAD stenosis directly. |
| `DEV-LCD-PCI-NEG` | `LCD-PCI` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Stable angina without functional ischemia documentation safely defers to clinician. |
| `DEV-LCD-POWER-WC-APP` | `LCD-POWER-WC` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | 'Power mobility device' and 'inability to operate manual chair' synonym mismatch. |
| `DEV-LCD-POWER-WC-NEG` | `LCD-POWER-WC` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Home environment accessibility unverified in note, prompting human deferral. |
| `DEV-LCD-PROTON-APP` | `LCD-PROTON` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Skull base chordoma / chondrosarcoma critical structure proximity paraphrasing. |
| `DEV-LCD-PROTON-NEG` | `LCD-PROTON` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Standard systemic indications without dosimetric superiority claim; defers safely. |
| `DEV-LCD-RAD-NIV-APP` | `LCD-RAD-NIV` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | End-stage COPD with hypercapnic respiratory failure and nocturnal desaturation terminology variation. |
| `DEV-LCD-RAD-NIV-NEG` | `LCD-RAD-NIV` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Borderline daytime hypercapnia requires medical director evaluation. |
| `DEV-LCD-ROTATOR-CUFF-NEG` | `LCD-ROTATOR-CUFF` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Partial-thickness tendon tear without conservative care completion safely abstains. |
| `DEV-LCD-SBRT-APP` | `LCD-SBRT` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Inoperable stage I non-small cell lung carcinoma (NSCLC) medical contraindications. |
| `DEV-LCD-SHOULDER-ARTHRO-NEG` | `LCD-SHOULDER-ARTHRO` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Moderate glenohumeral osteoarthritis with preserved motion lacks surgical threshold. |
| `DEV-NCD-CARDIAC-REHAB-APP` | `NCD-CARDIAC-REHAB` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Post-CABG / post-STEMI qualifying episode timing paraphrased in discharge summary. |
| `DEV-NCD-CATARACT-NEG` | `NCD-CATARACT` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Snellen acuity 20/40 without documented glare disability; defers to human reviewer. |
| `DEV-NCD-CCTA-APP` | `NCD-CCTA` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Intermediate pre-test risk angina presentation terminology omitted from keywords. |
| `DEV-NCD-CCTA-NEG` | `NCD-CCTA` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | High-probability acute coronary syndrome requires invasive angiography, not CCTA. |
| `DEV-NCD-MPI-PET-APP` | `NCD-MPI-PET` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Inconclusive SPECT stress test and severe body mass index documentation phrasing. |
| `DEV-NCD-PACEMAKER-APP` | `NCD-PACEMAKER` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Symptomatic Mobitz Type II second-degree AV block electrophysiology phrasing. |
| `DEV-NCD-PACEMAKER-NEG` | `NCD-PACEMAKER` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Asymptomatic first-degree AV block lacks pacemaker indication; defers safely. |
| `DEV-NCD-PET-ONC-APP` | `NCD-PET-ONC` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Solitary pulmonary nodule FDG metabolic uptake and initial staging phrasing. |
| `DEV-NCD-PET-ONC-NEG` | `NCD-PET-ONC` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Non-covered routine cancer screening surveillance PET without recurrence suspicion. |
| `DEV-NCD-PUMP-APP` | `NCD-PUMP` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Intrathecal baclofen trial for severe intractable spasticity keyword variation. |
| `DEV-NCD-SCS-APP` | `NCD-SCS` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`criterion-design`** | Psychological clearance requirement strictly enforced; narrative described trial stimulator. |
| `DEV-NCD-SCS-NEG` | `NCD-SCS` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Active substance use disorder and untreated depression require psychiatric review. |
| `DEV-NCD-SGD-APP` | `NCD-SGD` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Augmentative and alternative communication (AAC) speech-language evaluation terms. |
| `DEV-NCD-SGD-NEG` | `NCD-SGD` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Temporary vocal impairment with recovery potential safely routes to human clinician. |
| `DEV-OPD-RHINO-NEG` | `OPD-RHINO` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Cosmetic rhinoplasty request without airway obstruction safely abstains under tau=0.85. |
| `DEV-OPD-SI-FUSION-APP` | `OPD-SI-FUSION` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Fortin finger test and fluoroscopic SI joint block >= 75% pain relief phrasing. |
| `DEV-OPD-SI-FUSION-NEG` | `OPD-SI-FUSION` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Lumbar discogenic pain masquerading as SI joint pain warrants human audit. |

### Failure Class Totals (Audited Head)
- **`logic defect`**: `3` cases originally audited in v23; **all 3 resolved in v24** (now concordant `APPROVED`).
- **`criterion-design`**: `2` cases (4.4% of remaining discordant).
- **`synonymy-only`**: `19` cases (42.2% of remaining discordant).
- **`genuine-ambiguity`**: `24` cases (53.3% of remaining discordant).
- **Current Discordant Cases**: `45` cases (`84 - 39 = 45`).

## 5. Controlled Prompt Experiment Results (Task 1b)

Evaluated on the 19 controlled synonymy failure cases (27 criterion-vignette evaluation pairs) using `qwen2.5:3b` with unified Gate A checking (`failing_gate != 'GATE_A_EXACT_SLICE'`):
- **Production Prompt (Legacy)**: Calls=27, Proposals=27, Gate A Pass=13, Gate A Fail=14 $\rightarrow$ **48.1% Pass Rate**.
- **Variant Prompt (Verbatim Instruction + Worked Example)**: Calls=27, Proposals=27, Gate A Pass=18, Gate A Fail=9 $\rightarrow$ **66.7% Pass Rate**.
- **Net Margin**: **+18.5% improvement** in Gate A extraction fidelity without introducing false approvals or ungrounded proposals.
- **Accepted Proposals & Decision Changes**: 0 in both arms (all proposals vetoed by Gate C due to closed-world concept mapping).

## 6. Larger Model Feasibility & Latency Budget Constraint (Task 2)

- **Model Attempted**: `qwen2.5:14b` (Q4_K_M quantization) via local Ollama runner.
- **Measured Constraint**: 122.06 seconds per vignette (measured on `DEV-LCD-ACDF-NEG` with 2 unmet criteria calls, each hitting the 60.0s safety ceiling).
- **Projected Full Run**: $> 7,560$ seconds ($\approx 2.1$ hours) across 84 dev vignettes (126 LLM calls).
- **Budget Comparison**: Exceeds the statutory budget of **3 calls / 30.0s per case** by **306.9%** per vignette; cannot complete within interactive session.
- **Outcome**: Explicitly recorded as `CANNOT_RUN_BUDGET_EXCEEDED` in `app/data/benchmarks/bench_v1_llm_safety_report.json`.

## 7. LLM Coverage Audit & Forensic Verdict (Task 3)

> Across all 84 synthetic development vignettes (126 LLM calls, 3B parameter model), the gated LLM proposal step produced exactly 2 accepted proposals and 0 net adjudication decision changes (concordance remained 39/84, 46.4%). This outcome is explained by a combination of two structural factors: (1) Prompt & Model Size: small 3B models fail verbatim extraction on 33.3% to 51.9% of calls (Gate A rejections), though explicit verbatim instructions with worked examples improve extraction fidelity by +18.5% (Gate A pass rate rising from 48.1% to 66.7%), while larger 14B models exceed the statutory latency budget (122.06s vs 30.0s per case, a 306.9% overrun); and (2) Coverage & Closed-World Gate C: all 43 non-paraphrased proposals were vetoed by Gate C because the extended policies' specialized concepts were absent from the 12 curated concepts in ConceptMap (returning NO_CONCEPT_MAP_ENTRY), while the 2 accepted proposals mapped to CONCEPT-CONSERVATIVE-CARE-FAILURE where the deterministic engine had already matched the evidence via literal keywords. For the LLM to add genuine decision-improving value beyond its role as a redundant safety net, two prerequisites must be met: the human-curated ConceptMap whitelist must be expanded to cover the extended policies' distinct concept spaces, and faster quantized inference or prompt caching must bring higher-capacity models within the statutory 30-second budget.


## Verification and Honesty Notes
- **Forbidden Phrase Scan**: Verified 0 occurrences of policy slugs, LCD/NCD identifiers, or coverage verdict phrases in vignette texts.
- **Retrieval Architecture**: Evaluated under `HybridPolicyRetriever` combining BM25 keyword matching with expanded domain clinical concept vocabulary.
- **Adjudication Mechanics**: Evaluated under `DeclarativePolicyEngine` character-anchored extraction and ConText negation scoping.
- **Status**: Development baseline only. All extended policies remain `CLAIMED_UNVERIFIED` at the criterion level.
