# CarePolicyGuard Held-Out Evaluation Report

**Dataset**: CarePolicyGuard Held-Out Vignette Set v1  
**Execution Timestamp**: 2026-10-31T23:09:42.977625+00:00  
**Total Vignettes**: 15 (Gold: {'APPROVED': 7, 'DEFERRED_TO_HUMAN': 4, 'DENIED': 4, 'total': 15})  
**Status**: UNSEALED - Evaluated once across deterministic, state_machine, and declarative modes  

## 1. Summary Performance by Execution Mode

| Execution Mode | Accuracy | Correct / Total | False Approvals | False Approval Rate | Abstentions | Mean Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `deterministic` | **53.3%** | 8 / 15 | **2** | **13.3%** | 5 (33.3%) | 31.7 ms |
| `state_machine` | **40.0%** | 6 / 15 | **6** | **40.0%** | 1 (6.7%) | 73.33 ms |
| `declarative` | **80.0%** | 12 / 15 | **0** | **0.0%** | 6 (40.0%) | 32.84 ms |

## 2. Granular Vignette Results Across Modes

| ID | Policy ID | Case Type | Gold Decision | Deterministic | State Machine | Declarative |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| HOLD-01 | NCD-20.4 | clear-approve | `APPROVED` | `APPROVED` | **`DENIED` (FAIL)** | `APPROVED` |
| HOLD-02 | NCD-20.4 | exclusion-deny | `DENIED` | **`APPROVED` (FAIL)** | **`APPROVED` (FAIL)** | `DENIED` |
| HOLD-03 | NCD-20.4 | omission-defer | `DEFERRED_TO_HUMAN` | **`DENIED` (FAIL)** | **`DENIED` (FAIL)** | `DEFERRED_TO_HUMAN` |
| HOLD-04 | LCD-L33829 | borderline-approve | `APPROVED` | `APPROVED` | `APPROVED` | **`DEFERRED_TO_HUMAN` (FAIL)** |
| HOLD-05 | LCD-L33829 | threshold-deny | `DENIED` | **`DEFERRED_TO_HUMAN` (FAIL)** | **`DEFERRED_TO_HUMAN` (FAIL)** | **`DEFERRED_TO_HUMAN` (FAIL)** |
| HOLD-06 | LCD-L33829 | omission-defer | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **`APPROVED` (FAIL)** | `DEFERRED_TO_HUMAN` |
| HOLD-07 | NCD-20.33 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-08 | NCD-20.33 | omission-defer | `DEFERRED_TO_HUMAN` | **`APPROVED` (FAIL)** | **`APPROVED` (FAIL)** | `DEFERRED_TO_HUMAN` |
| HOLD-09 | NCD-220.13 | clear-approve | `APPROVED` | **`DEFERRED_TO_HUMAN` (FAIL)** | `APPROVED` | **`DENIED` (FAIL)** |
| HOLD-10 | NCD-220.13 | safety-deny | `DENIED` | **`DEFERRED_TO_HUMAN` (FAIL)** | **`APPROVED` (FAIL)** | `DENIED` |
| HOLD-11 | NCD-20.29 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-12 | NCD-20.29 | omission-defer | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **`APPROVED` (FAIL)** | `DEFERRED_TO_HUMAN` |
| HOLD-13 | NCD-20.7 | clear-approve | `APPROVED` | **`DENIED` (FAIL)** | `APPROVED` | `APPROVED` |
| HOLD-14 | NCD-240.2 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-15 | LCD-TOTAL-KNEE-01 | exclusion-deny | `DENIED` | `DENIED` | **`APPROVED` (FAIL)** | `DENIED` |

## 3. False Approvals and Mismatch Analysis

### Mode: `deterministic`
Total Mismatches: 7 | False Approvals: 2

- **HOLD-02** (NCD-20.4 - `exclusion-deny`): Gold = `DENIED`, Predicted = `APPROVED` **[CRITICAL PATIENT SAFETY FAILURE: FALSE APPROVAL]**
  - Rationale: CRIT-ICD-01: Documented LVEF is 29% confirmed by Echocardiography, meeting the mandatory primary prevention threshold of ≤35% (HFrEF).; CRIT-ICD-02: Patient classified as NYHA Class II heart failure symptoms.; CRIT-ICD-03: Documented guideline-directed medical therapy sustained for 6 months (meets >=90 day / 3 month CMS threshold).; CRIT-ICD-04: Event timeline documented: myocardial infarction 6 months ago; satisfies CMS mandatory post-event waiting periods.; CRIT-ICD-EXCL-01: Documented absence of disqualifying exclusion: No cardiogenic shock.
- **HOLD-03** (NCD-20.4 - `omission-defer`): Gold = `DEFERRED_TO_HUMAN`, Predicted = `DENIED`
  - Rationale: CRIT-ICD-01: Documented LVEF is 33% confirmed by Echocardiography, meeting the mandatory primary prevention threshold of ≤35% (HFrEF).; CRIT-ICD-02: Patient classified as NYHA Class II heart failure symptoms.; CRIT-ICD-03: Medications identified, but duration of therapy (≥90 days prerequisite) is not substantiated in note.; CRIT-ICD-04: Event timeline documented: myocardial infarction; satisfies CMS mandatory post-event waiting periods.; CRIT-ICD-EXCL-01: Documented absence of disqualifying exclusion: No cardiogenic shock.
- **HOLD-05** (LCD-L33829 - `threshold-deny`): Gold = `DENIED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Potential unverified negative omission detected in [CRIT-CPAP-01]: EHR mentions clinical criteria terms but marked non-qualifying. | Calibrated aggregate confidence (0.667) falls below safety threshold tau (0.85).
- **HOLD-08** (NCD-20.33 - `omission-defer`): Gold = `DEFERRED_TO_HUMAN`, Predicted = `APPROVED` **[CRITICAL PATIENT SAFETY FAILURE: FALSE APPROVAL]**
  - Rationale: CRIT-TAVR-01: Documented severe aortic stenosis: 'severe aortic stenosis', satisfying NCD 20.33 AVA/gradient requirements.; CRIT-TAVR-02: Documented multidisciplinary evaluation: 'multidisciplinary Heart Team', confirming high/prohibitive surgical risk consensus.
- **HOLD-09** (NCD-220.13 - `clear-approve`): Gold = `APPROVED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Calibrated aggregate confidence (0.833) falls below safety threshold tau (0.85).
- **HOLD-10** (NCD-220.13 - `safety-deny`): Gold = `DENIED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Calibrated aggregate confidence (0.800) falls below safety threshold tau (0.85).
- **HOLD-13** (NCD-20.7 - `clear-approve`): Gold = `APPROVED`, Predicted = `DENIED`
  - Rationale: CRIT-CAS-01: Documented 85% carotid stenosis in symptomatic patient with neurological history (meets CMS NCD 20.7 threshold >=70%).; CRIT-CAS-02: Documented consensus between a cardiothoracic surgeon and interventional cardiologist confirming prohibitive surgical risk is missing.; CRIT-CAS-03: Documented utilization of mandatory CMS embolic protection system: 'embolic protection device'.

### Mode: `state_machine`
Total Mismatches: 9 | False Approvals: 6

- **HOLD-01** (NCD-20.4 - `clear-approve`): Gold = `APPROVED`, Predicted = `DENIED`
  - Rationale: CRIT-ICD-01: Extracted via clinical pattern matching.; CRIT-ICD-02: Extracted via clinical pattern matching.; CRIT-ICD-03: Extracted via clinical pattern matching.; CRIT-ICD-04: Extracted via clinical pattern matching.; CRIT-ICD-EXCL-01: Extracted via clinical pattern matching.
- **HOLD-02** (NCD-20.4 - `exclusion-deny`): Gold = `DENIED`, Predicted = `APPROVED` **[CRITICAL PATIENT SAFETY FAILURE: FALSE APPROVAL]**
  - Rationale: CRIT-ICD-01: Extracted via clinical pattern matching.; CRIT-ICD-02: Extracted via clinical pattern matching.; CRIT-ICD-03: Extracted via clinical pattern matching.; CRIT-ICD-04: Extracted via clinical pattern matching.; CRIT-ICD-EXCL-01: Extracted via clinical pattern matching.
- **HOLD-03** (NCD-20.4 - `omission-defer`): Gold = `DEFERRED_TO_HUMAN`, Predicted = `DENIED`
  - Rationale: CRIT-ICD-01: Extracted via clinical pattern matching.; CRIT-ICD-02: Extracted via clinical pattern matching.; CRIT-ICD-03: Extracted via clinical pattern matching.; CRIT-ICD-04: Extracted via clinical pattern matching.; CRIT-ICD-EXCL-01: Extracted via clinical pattern matching.
- **HOLD-05** (LCD-L33829 - `threshold-deny`): Gold = `DENIED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Potential unverified negative omission detected in [CRIT-CPAP-01]: EHR mentions clinical criteria terms but marked non-qualifying. | Calibrated aggregate confidence (0.720) falls below safety threshold tau (0.85).
- **HOLD-06** (LCD-L33829 - `omission-defer`): Gold = `DEFERRED_TO_HUMAN`, Predicted = `APPROVED` **[CRITICAL PATIENT SAFETY FAILURE: FALSE APPROVAL]**
  - Rationale: CRIT-CPAP-01: Extracted via clinical pattern matching.; CRIT-CPAP-02: Extracted via clinical pattern matching.
- **HOLD-08** (NCD-20.33 - `omission-defer`): Gold = `DEFERRED_TO_HUMAN`, Predicted = `APPROVED` **[CRITICAL PATIENT SAFETY FAILURE: FALSE APPROVAL]**
  - Rationale: CRIT-TAVR-01: Extracted via clinical pattern matching.; CRIT-TAVR-02: Extracted via clinical pattern matching.
- **HOLD-10** (NCD-220.13 - `safety-deny`): Gold = `DENIED`, Predicted = `APPROVED` **[CRITICAL PATIENT SAFETY FAILURE: FALSE APPROVAL]**
  - Rationale: CRIT-LAAC-01: Extracted via clinical pattern matching.; CRIT-LAAC-02: Extracted via clinical pattern matching.; CRIT-LAAC-03: Extracted via clinical pattern matching.
- **HOLD-12** (NCD-20.29 - `omission-defer`): Gold = `DEFERRED_TO_HUMAN`, Predicted = `APPROVED` **[CRITICAL PATIENT SAFETY FAILURE: FALSE APPROVAL]**
  - Rationale: CRIT-HBOT-01: Extracted via clinical pattern matching.; CRIT-HBOT-02: Extracted via clinical pattern matching.; CRIT-HBOT-03: Extracted via clinical pattern matching.
- **HOLD-15** (LCD-TOTAL-KNEE-01 - `exclusion-deny`): Gold = `DENIED`, Predicted = `APPROVED` **[CRITICAL PATIENT SAFETY FAILURE: FALSE APPROVAL]**
  - Rationale: CRIT-TKA-01: Extracted via clinical pattern matching.; CRIT-TKA-02: Extracted via clinical pattern matching.; CRIT-TKA-EXCL-01: Extracted via clinical pattern matching.

### Mode: `declarative`
Total Mismatches: 3 | False Approvals: 0

- **HOLD-04** (LCD-L33829 - `borderline-approve`): Gold = `APPROVED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Potential unverified negative omission detected in [CRIT-CPAP-01]: EHR mentions clinical criteria terms but marked non-qualifying. | Calibrated aggregate confidence (0.674) falls below safety threshold tau (0.85).
- **HOLD-05** (LCD-L33829 - `threshold-deny`): Gold = `DENIED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Potential unverified negative omission detected in [CRIT-CPAP-01]: EHR mentions clinical criteria terms but marked non-qualifying. | Calibrated aggregate confidence (0.674) falls below safety threshold tau (0.85).
- **HOLD-09** (NCD-220.13 - `clear-approve`): Gold = `APPROVED`, Predicted = `DENIED`
  - Rationale: CRIT-LAAC-01: Metric fails statutory threshold: 2.0points does not satisfy >= 3.0.; CRIT-LAAC-02: Statutory metric verified: 4.0points satisfies >= 3.0 threshold.; CRIT-LAAC-03: Clinical finding documented: 'CTA'.
