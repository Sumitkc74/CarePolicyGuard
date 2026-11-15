# v54 — Delivery Report

**Session Scope**: MEASUREMENT session only (Zero production code changes)  
**Parent Head at Start**: `c06ee6b41ad415eaacb89635990f2bd56ba48be1`  
**Database Used**: `carepolicyguard.db` (50 active CMS policies, path: `E:\Class\GitHub\CarePolicyGuard\carepolicyguard.db`)  
**Judge Model**: Local Ollama runtime with `qwen2.5:3b` (cloud egress default-off)  
**Committed Artifacts**:
- Runner: `scripts/run_agentic_v54_three_mode_measurement.py`
- Raw Results JSON: `app/data/benchmarks/agentic_v54_three_mode_run.json`
- Report: `docs/agentic_v54_measurement_report.md`

---

## 1. Per-Mode Four-Number Safety Comparison

All reported numbers recompute directly from the committed master JSON artifact `app/data/benchmarks/agentic_v54_three_mode_run.json`.

| Mode | Concepts / Map | Concordant / Total (Accuracy) | False Approvals (FA) | False Denials (FD) | Safe Deferrals | Synonymy Resolved | Delta vs v52 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Deterministic** | 12 concepts (Committed) | **37 / 84 (44.0%)** | 0 | 2 (PANNI, RHINO) | 45 | 0 / 19 | Identical (0 change) |
| **Declarative** | 12 concepts (Committed) | **39 / 84 (46.4%)** | 0 | 0 | 45 | 0 / 19 | Identical (0 change) |
| **Agentic** | 131 concepts (Merged) | **46 / 84 (54.8%)** | 0 | 0 | 38 | 8 / 19 | Identical (0 change) |

### Key Findings on Headline Metrics:
1. **Deterministic & Declarative Stability**: Zero regression across all 84 dev vignettes. The deterministic and declarative arms produced identical outcomes to v52 (37/84 and 39/84), confirming that v53 build changes were strictly isolated to the agentic mode.
2. **Agentic Concordance Unmoved**: Agentic headline accuracy remains at **46 / 84 (54.8%)**. Although the Agent 3 advocate successfully rescued criterion `CRIT-KYPHO-01` on `DEV-LCD-KYPHO-APP`, the overall case remains safely deferred because `CRIT-KYPHO-02` (conservative therapy documentation) was not met in the note.
3. **Synonymy Resolution**: 8 of 19 synonymy cases resolved (IMRT, KNEE-ORTHOSIS, LUMBAR-DECOMP, PROTON, RAD-NIV, CARDIAC-REHAB, MPI-PET, PUMP), exactly matching v52.

---

## 2. 9-Case Synonymy Table & SBRT / SI-FUSION Regression Rows

### The 9 Unresolved Synonymy Cases
None of the 9 unresolved synonymy cases flipped to APPROVED, though several engaged the new advocacy and debate mechanisms:

| Vignette ID | Expected | Actual | Concordant | Case Wall (s) | Adv. Attempts | Def. Calls | Debated Outcomes / Notes |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `DEV-LCD-KYPHO-APP` | APPROVED | DEFERRED | No | 52.48 s | 1 (1 Rescued) | 0 | `CRIT-KYPHO-01` rescued to MET; deferred on `CRIT-KYPHO-02` |
| `DEV-LCD-MRI-BRAIN-APP` | APPROVED | DEFERRED | No | 28.58 s | 1 (0 Rescued) | 0 | Advocate returned empty quote; deferred |
| `DEV-LCD-MRI-LUMBAR-APP`| APPROVED | DEFERRED | No | 29.49 s | 1 (0 Rescued) | 0 | Advocate returned empty quote; deferred |
| `DEV-LCD-PAD-ATHERO-APP`| APPROVED | DEFERRED | No | 51.40 s | 1 (0 Rescued) | 0 | Advocate quote rejected by `GATE_C_MAP_CHECK` |
| `DEV-LCD-POWER-WC-APP`  | APPROVED | DEFERRED | No | 31.23 s | 1 (0 Rescued) | 0 | Advocate quote rejected by `GATE_C_MAP_CHECK` |
| `DEV-NCD-CCTA-APP`      | APPROVED | DEFERRED | No | 30.12 s | 1 (0 Rescued) | 0 | Advocate returned empty quote; deferred |
| `DEV-NCD-PACEMAKER-APP` | APPROVED | DEFERRED | No | 30.03 s | 1 (0 Rescued) | 0 | Advocate returned empty quote; deferred |
| `DEV-NCD-PET-ONC-APP`   | APPROVED | DEFERRED | No | 0.09 s | 0 | 0 | Not routed to judge (deterministic abstention) |
| `DEV-NCD-SGD-APP`       | APPROVED | DEFERRED | No | 30.75 s | 1 (0 Rescued) | 0 | Advocate quote rejected by `GATE_C_MAP_CHECK` |

### SBRT and SI-FUSION Regression Rows

In v52, both `DEV-LCD-SBRT-APP` and `DEV-OPD-SI-FUSION-APP` ran up against the old 30.0s time budget ceiling (~35.9s elapsed) and conceded due to operational budget exhaustion without ever executing the defense call (`defenses_attempted = 0`).

In v54 (under v53's 60.0s budget):
- **`DEV-LCD-SBRT-APP`**:
  - Wall Time: **56.38 s** (safely under the 60.0s budget ceiling).
  - Counter-reading: Raised on `ANATOMIC_MISMATCH` (brain MRI vs primary spinal tumor).
  - Defense Call: **1 call attempted live** to `generate_defense_sync`.
  - Outcome: Agent 2 defense could not provide an uncontradicted quote resolving the mismatch; Agent 2 **conceded cleanly on clinical merit** (`CRIT-SBRT-01: CONCEDED`).
  - Budget-refused defenses: **0**.
- **`DEV-OPD-SI-FUSION-APP`**:
  - Wall Time: **49.89 s** (safely under the 60.0s budget ceiling).
  - Counter-reading: Raised on `TEMPORAL` objection (conservative therapy duration < 16 weeks).
  - Defense Call: **1 call attempted live** to `generate_defense_sync`.
  - Outcome: Note lacked explicit documentation of 16 weeks duration; Agent 2 **conceded cleanly on clinical merit** (`CRIT-SI-01: CONCEDED`).
  - Budget-refused defenses: **0**.

Both cases now complete proper adversarial debate cycles and concede on clinical evidence rather than artificial timeouts.

---

## 3. Debate Dynamics & Agent 3 Advocacy Table

### Debate Dynamics Summary
- **Counter-Readings Raised**: 2
  - `ANATOMIC_MISMATCH`: 1 (`DEV-LCD-SBRT-APP`)
  - `TEMPORAL`: 1 (`DEV-OPD-SI-FUSION-APP`)
- **Defense Calls Attempted** (calls to `generate_defense_sync`): **2**
- **Defense Outcomes**:
  - Defended: 0
  - Conceded on Clinical Evidence: 2
  - Budget-Refused Defenses: **0** (eliminated from v52)
- **Concessions on Gate Failure**: 9
- **Unresolved Disagreements**: **0** (down from 2 in v52)
- **Decisions Changed by Debate**: 0

### Agent 3 Advocacy Accounting
- **Total Advocacy Calls Attempted**: 33
- **Advocacy Promotions (`DEFENSE` with `advocacy_promoted=True`)**: **1**
- **Advocacy Rejections (`CHALLENGE` with `advocacy_rejected=True`)**: **32**
  - Rejected by Gate A (Verbatim grounding): 0
  - Rejected by Gate B or Gate C (Concept map check / scope): 6
  - Rejected on Empty Quote (Model found no supporting evidence): 26

### The 18 False Deferrals Advocate Breakdown
The table below documents every criterion among the 18 false deferrals from v52, recording its advocate outcome and exact blocking step:

| # | Vignette ID | Criterion Code | Advocate Attempted | Advocate Outcome | Blocking Step | Quoted Evidence / Notes |
| :-: | :--- | :--- | :-: | :---: | :--- | :--- |
| 1 | `DEV-LCD-KYPHO-APP` | `CRIT-KYPHO-01` | **Yes** | **RESCUED** | **N/A (Promoted to MET)** | `"Pain rating is 8/10 on visual analog scale."` (Passed Gate A, B, C) |
| 2 | `DEV-LCD-KYPHO-APP` | `CRIT-KYPHO-02` | No | BUDGET_HALT | Budget halt before advocacy | Missing conservative therapy evidence in chart |
| 3 | `DEV-LCD-MRI-BRAIN-APP` | `CRIT-MRIB-02` | Yes | REJECTED | Empty quote (no supporting text) | Model could not locate qualifying documentation |
| 4 | `DEV-LCD-MRI-LUMBAR-APP` | `CRIT-MRIL-02` | Yes | REJECTED | Empty quote (no supporting text) | Model could not locate qualifying documentation |
| 5 | `DEV-LCD-PAD-ATHERO-APP` | `CRIT-PAD-01` | Yes | REJECTED | `GATE_C_MAP_CHECK` | Quote found but failed concept map accepted terms |
| 6 | `DEV-LCD-PAD-ATHERO-APP` | `CRIT-PAD-02` | No | BUDGET_HALT | Budget halt before advocacy | Halts due to unsatisfied criteria in prior checks |
| 7 | `DEV-LCD-PCI-APP` | `CRIT-PCI-01` | Yes | REJECTED | `GATE_C_MAP_CHECK` | Quote found but failed concept map accepted terms |
| 8 | `DEV-LCD-POWER-WC-APP` | `CRIT-PWC-02` | Yes | REJECTED | `GATE_C_MAP_CHECK` | Quote found but failed concept map accepted terms |
| 9 | `DEV-LCD-SBRT-APP` | `CRIT-SBRT-01` | No | BUDGET_HALT | Budget halt after debate | Conceded during counter-reading debate on anatomic grounds |
| 10 | `DEV-NCD-CATARACT-APP` | `CRIT-CAT-01` | Yes | REJECTED | `GATE_C_MAP_CHECK` | Quote found but failed concept map accepted terms |
| 11 | `DEV-NCD-CATARACT-APP` | `CRIT-CAT-02` | No | BUDGET_HALT | Budget halt before advocacy | Halts due to prior unsatisfied criteria |
| 12 | `DEV-NCD-CCTA-APP` | `CRIT-CCTA-01` | Yes | REJECTED | Empty quote (no supporting text) | Model could not locate qualifying documentation |
| 13 | `DEV-NCD-PACEMAKER-APP` | `CRIT-PACE-02` | Yes | REJECTED | Empty quote (no supporting text) | Model could not locate qualifying documentation |
| 14 | `DEV-NCD-PET-ONC-APP` | `CRIT-PTONC-01` | No | BUDGET_HALT | Deterministic abstention | Case halted before entering LLM judge |
| 15 | `DEV-NCD-SCS-APP` | `CRIT-SCS-01` | Yes | REJECTED | `GATE_C_MAP_CHECK` | Quote found but failed concept map accepted terms |
| 16 | `DEV-NCD-SCS-APP` | `CRIT-SCS-02` | No | BUDGET_HALT | Budget halt before advocacy | Halts due to prior unsatisfied criteria |
| 17 | `DEV-NCD-SGD-APP` | `CRIT-SGD-02` | Yes | REJECTED | `GATE_C_MAP_CHECK` | Quote found but failed concept map accepted terms |
| 18 | `DEV-OPD-SI-FUSION-APP` | `CRIT-SI-01` | No | BUDGET_HALT | Budget halt after debate | Conceded during counter-reading debate on temporal grounds |

---

## 4. Fallback, Routing, Budget & Latency Numbers

### Fallback Elimination (Capped Fallback in v53)
| Metric | v52 Measurement | v54 Measurement | Delta |
| :--- | :---: | :---: | :---: |
| Cases Entering Fallback | 35 | **0** | **-35** |
| Fallback Calls Burned | 59 | **0** | **-59 (100% eliminated)** |
| Fallback Promotions | 0 | **0** | 0 |
| `fallback_calls` Per-Case Field | Null / missing | **Populated Integer on all 84 cases** | Fixed |

### Routing Counters
- Total Initial Judge Calls: **49**
- Judge Calls Otherwise Deferring: **49** (100%)
- Judge Calls Already Settled: **0** (0% routing violation)
- Advocacy Calls on Settled Criteria: **0**

### Budget & Latency Performance
- Cases Exceeding Wall Budget: **0** (was 26 in v52 under 30s ceiling)
- Max Case Wall Time: **56.38 s** (safely bounded under the 60.0s budget)
- Mean Case Wall Time: **14.97 s** (Min: 0.03 s, Max: 56.38 s)
- Judge Call Latency: Mean **14.39 s** (14,387.95 ms), Max **18.86 s** (18,864.02 ms)
- Total Budget Halts: **38**
  - Insufficient evidence for mandatory coverage criteria: 36
  - Calibrated aggregate confidence below safety threshold ($\tau = 0.85$): 1
  - Potential unverified negative omission detected: 1
  - Operational time/call exhaustion halts: **0**

---

## 5. Explicit Disclosures & Compliance

1. **Zero Production Code Changes**:
   - `git diff HEAD app/` is completely empty.
   - The only committed files in this session are the measurement runner (`scripts/run_agentic_v54_three_mode_measurement.py`), master output JSON (`app/data/benchmarks/agentic_v54_three_mode_run.json`), and this delivery report (`docs/agentic_v54_measurement_report.md`).
2. **Held-Out v2 Dataset Untouched**:
   - `carepolicyguard-heldout-v2/heldout_vignettes_v2.json` was never opened, read, or evaluated.
3. **Remote LLM Egress Default-Off**:
   - All LLM inference ran locally via Ollama with `qwen2.5:3b`. Zero external network calls were made.
4. **Frozen Thresholds Honored**:
   - Shortlist thresholds (0.08 / 0.33 / 0.15), RRF weights, coverage formula, 3-calls-per-case bound, and 60.0s time budget remained untouched.
5. **Full Pytest Suite Result**:
   - Verified live before report generation:
     ```
     ================= 406 passed, 1 warning in 197.67s (0:03:17) =================
     ```
     *(406 passed / 0 skipped / 1 warning on live host with Ollama active; in environments where Ollama is absent, `test_live_ollama_model_smoke_test` cleanly skips resulting in 405 passed / 1 skipped / 1 warning).*
6. **Ruff Linter Cleanliness**:
   - `ruff check scripts/run_agentic_v54_three_mode_measurement.py`: **0 errors**.
