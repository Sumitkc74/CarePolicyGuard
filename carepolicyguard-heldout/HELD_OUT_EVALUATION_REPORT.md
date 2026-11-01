# CarePolicyGuard Development-Set (v1) Diagnostic Evaluation Report

> [!IMPORTANT]
> **Development-Set Status**: This set (v1) is an unsealed development dataset used for regression testing and failure diagnosis.
> Diagnostic numbers reported here are internal benchmarks and must not be cited as held-out generalization claims.
> Held-out evaluation is strictly reserved for the sealed v2 dataset pending clinician sign-off.

**Dataset**: CarePolicyGuard Held-Out Vignette Set v1 (Development Diagnostic Set)  
**Execution Timestamp**: 2026-11-01T23:24:52.128019+00:00  
**Total Vignettes**: 15 (Gold: {'APPROVED': 7, 'DEFERRED_TO_HUMAN': 4, 'DENIED': 4, 'total': 15})  
**Status**: UNSEALED DEVELOPMENT SET  

## 1. Summary Performance by Execution Mode

| Execution Mode | Accuracy | Correct / Total | False Approvals | False Approval Rate | Abstentions | Mean Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `deterministic` | **100.0%** | 15 / 15 | **0** | **0.0%** | 4 (26.7%) | 27.15 ms |
| `state_machine` | **100.0%** | 15 / 15 | **0** | **0.0%** | 4 (26.7%) | 62.13 ms |
| `declarative` | **100.0%** | 15 / 15 | **0** | **0.0%** | 4 (26.7%) | 24.38 ms |

## 2. Granular Vignette Results Across Modes

| ID | Policy ID | Case Type | Gold Decision | Deterministic | State Machine | Declarative |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| HOLD-01 | NCD-20.4 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-02 | NCD-20.4 | exclusion-deny | `DENIED` | `DENIED` | `DENIED` | `DENIED` |
| HOLD-03 | NCD-20.4 | omission-defer | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` |
| HOLD-04 | LCD-L33829 | borderline-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-05 | LCD-L33829 | threshold-deny | `DENIED` | `DENIED` | `DENIED` | `DENIED` |
| HOLD-06 | LCD-L33829 | omission-defer | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` |
| HOLD-07 | NCD-20.33 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-08 | NCD-20.33 | omission-defer | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` |
| HOLD-09 | NCD-220.13 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-10 | NCD-220.13 | safety-deny | `DENIED` | `DENIED` | `DENIED` | `DENIED` |
| HOLD-11 | NCD-20.29 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-12 | NCD-20.29 | omission-defer | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` |
| HOLD-13 | NCD-20.7 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-14 | NCD-240.2 | clear-approve | `APPROVED` | `APPROVED` | `APPROVED` | `APPROVED` |
| HOLD-15 | LCD-TOTAL-KNEE-01 | exclusion-deny | `DENIED` | `DENIED` | `DENIED` | `DENIED` |

## 3. False Approvals and Mismatch Analysis

### Mode: `deterministic`
No mismatches observed. 100% concordance with gold labels.

### Mode: `state_machine`
No mismatches observed. 100% concordance with gold labels.

### Mode: `declarative`
No mismatches observed. 100% concordance with gold labels.
