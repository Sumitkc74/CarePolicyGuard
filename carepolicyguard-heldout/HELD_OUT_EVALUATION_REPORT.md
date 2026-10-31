# CarePolicyGuard Held-Out Evaluation Report

**Dataset**: CarePolicyGuard Held-Out Vignette Set v1  
**Execution Timestamp**: 2026-10-31T23:40:58.169266+00:00  
**Total Vignettes**: 15 (Gold: {'APPROVED': 7, 'DEFERRED_TO_HUMAN': 4, 'DENIED': 4, 'total': 15})  
**Status**: UNSEALED - Evaluated once across deterministic, state_machine, and declarative modes  

## 1. Summary Performance by Execution Mode

| Execution Mode | Accuracy | Correct / Total | False Approvals | False Approval Rate | Abstentions | Mean Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `deterministic` | **73.3%** | 11 / 15 | **0** | **0.0%** | 6 (40.0%) | 25.32 ms |
| `state_machine` | **66.7%** | 10 / 15 | **0** | **0.0%** | 3 (20.0%) | 55.39 ms |
| `declarative` | **80.0%** | 12 / 15 | **0** | **0.0%** | 7 (46.7%) | 23.23 ms |

## 2. Granular Vignette Results Across Modes

| ID | Policy ID | Case Type | Gold Decision | Deterministic | State Machine | Declarative |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| HOLD-01 | NCD-20.4 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-02 | NCD-20.4 | exclusion-deny | `DENIED` | `DENIED` | `DENIED` | `DENIED` |
| HOLD-03 | NCD-20.4 | omission-defer | `DEFERRED_TO_HUMAN` | **`DENIED` (FAIL)** | **`DENIED` (FAIL)** | `DEFERRED_TO_HUMAN` |
| HOLD-04 | LCD-L33829 | borderline-approve | `APPROVED` | `APPROVED` | **`DEFERRED_TO_HUMAN` (FAIL)** | **`DEFERRED_TO_HUMAN` (FAIL)** |
| HOLD-05 | LCD-L33829 | threshold-deny | `DENIED` | **`DEFERRED_TO_HUMAN` (FAIL)** | **`DEFERRED_TO_HUMAN` (FAIL)** | **`DEFERRED_TO_HUMAN` (FAIL)** |
| HOLD-06 | LCD-L33829 | omission-defer | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` |
| HOLD-07 | NCD-20.33 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-08 | NCD-20.33 | omission-defer | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **`DENIED` (FAIL)** | `DEFERRED_TO_HUMAN` |
| HOLD-09 | NCD-220.13 | clear-approve | `APPROVED` | **`DEFERRED_TO_HUMAN` (FAIL)** | `APPROVED` | `APPROVED` |
| HOLD-10 | NCD-220.13 | safety-deny | `DENIED` | **`DEFERRED_TO_HUMAN` (FAIL)** | `DENIED` | **`DEFERRED_TO_HUMAN` (FAIL)** |
| HOLD-11 | NCD-20.29 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-12 | NCD-20.29 | omission-defer | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **`DENIED` (FAIL)** | `DEFERRED_TO_HUMAN` |
| HOLD-13 | NCD-20.7 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-14 | NCD-240.2 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-15 | LCD-TOTAL-KNEE-01 | exclusion-deny | `DENIED` | `DENIED` | `DENIED` | `DENIED` |

## 3. False Approvals and Mismatch Analysis

### Mode: `deterministic`
Total Mismatches: 4 | False Approvals: 0

- **HOLD-03** (NCD-20.4 - `omission-defer`): Gold = `DEFERRED_TO_HUMAN`, Predicted = `DENIED`
  - Rationale: CRIT-ICD-01: Documented LVEF is 33% confirmed by Echocardiography, meeting the mandatory primary prevention threshold of ≤35% (HFrEF).; CRIT-ICD-02: Patient classified as NYHA Class II heart failure symptoms.; CRIT-ICD-03: Medications identified, but duration of therapy (≥90 days prerequisite) is not substantiated in note.; CRIT-ICD-04: Event timeline documented: myocardial infarction; satisfies CMS mandatory post-event waiting periods.; CRIT-ICD-EXCL-01: Documented absence of disqualifying exclusion: No cardiogenic shock.
- **HOLD-05** (LCD-L33829 - `threshold-deny`): Gold = `DENIED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Potential unverified negative omission detected in [CRIT-CPAP-01]: EHR mentions clinical criteria terms but marked non-qualifying. | Calibrated aggregate confidence (0.667) falls below safety threshold tau (0.85).
- **HOLD-09** (NCD-220.13 - `clear-approve`): Gold = `APPROVED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Calibrated aggregate confidence (0.833) falls below safety threshold tau (0.85).
- **HOLD-10** (NCD-220.13 - `safety-deny`): Gold = `DENIED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Calibrated aggregate confidence (0.800) falls below safety threshold tau (0.85).

### Mode: `state_machine`
Total Mismatches: 5 | False Approvals: 0

- **HOLD-03** (NCD-20.4 - `omission-defer`): Gold = `DEFERRED_TO_HUMAN`, Predicted = `DENIED`
  - Rationale: CRIT-ICD-01: Statutory metric verified: 33.0% satisfies <= 35.0 threshold.; CRIT-ICD-02: Qualifying functional/severity stage confirmed: II in ['II', 'III', '2', '3', 'CLASS II', 'CLASS III'].; CRIT-ICD-03: No documented clinical evidence matching statutory criteria.; CRIT-ICD-04: No documented clinical evidence matching statutory criteria.; CRIT-ICD-EXCL-01: Statutory exclusion condition ruled out: documented as absent or resolved (no).
- **HOLD-04** (LCD-L33829 - `borderline-approve`): Gold = `APPROVED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Potential unverified negative omission detected in [CRIT-CPAP-01]: EHR mentions clinical criteria terms but marked non-qualifying. | Calibrated aggregate confidence (0.720) falls below safety threshold tau (0.85).
- **HOLD-05** (LCD-L33829 - `threshold-deny`): Gold = `DENIED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Potential unverified negative omission detected in [CRIT-CPAP-01]: EHR mentions clinical criteria terms but marked non-qualifying. | Calibrated aggregate confidence (0.720) falls below safety threshold tau (0.85).
- **HOLD-08** (NCD-20.33 - `omission-defer`): Gold = `DEFERRED_TO_HUMAN`, Predicted = `DENIED`
  - Rationale: CRIT-TAVR-01: No documented clinical evidence matching statutory criteria.; CRIT-TAVR-02: Documented finding was explicitly negated (no).
- **HOLD-12** (NCD-20.29 - `omission-defer`): Gold = `DEFERRED_TO_HUMAN`, Predicted = `DENIED`
  - Rationale: CRIT-HBOT-01: Qualifying functional/severity stage confirmed: 3 in ['3', '4', '5', 'III', 'IV', 'V', 'STAGE III', 'STAGE IV'].; CRIT-HBOT-02: No documented clinical evidence matching statutory criteria.; CRIT-HBOT-03: Documented finding was explicitly negated (no).

### Mode: `declarative`
Total Mismatches: 3 | False Approvals: 0

- **HOLD-04** (LCD-L33829 - `borderline-approve`): Gold = `APPROVED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Potential unverified negative omission detected in [CRIT-CPAP-01]: EHR mentions clinical criteria terms but marked non-qualifying. | Calibrated aggregate confidence (0.674) falls below safety threshold tau (0.85).
- **HOLD-05** (LCD-L33829 - `threshold-deny`): Gold = `DENIED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Potential unverified negative omission detected in [CRIT-CPAP-01]: EHR mentions clinical criteria terms but marked non-qualifying. | Calibrated aggregate confidence (0.674) falls below safety threshold tau (0.85).
- **HOLD-10** (NCD-220.13 - `safety-deny`): Gold = `DENIED`, Predicted = `DEFERRED_TO_HUMAN`
  - Rationale: Calibrated aggregate confidence (0.820) falls below safety threshold tau (0.85).
