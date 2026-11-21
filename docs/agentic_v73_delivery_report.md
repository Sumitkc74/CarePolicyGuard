# CarePolicyGuard Agentic Benchmark Delivery Report (v73)

- **Date:** November 21, 2026
- **Pre-Measurement Git Commit (Code & Tests):** `fd93806b15ab18d967eeab38ed982410bbf125a0` (short: `fd93806`)
- **Parent Git Commit (v72 Acceptance):** `41350ecc75ca107ec34c49ead069c45f532b6b42` (short: `41350ec`)
- **Parent Chain Verified via Git:**
  - `fd93806` Implement v73 narrowed pre-deferral review, measurement-script wins, tests, and v72 report corrections
  - `41350ec` Record v72 three-mode benchmark run, same-map ablation, and delivery report
  - `e3b4bc6` Implement Gate C provisional-equivalence path, guard grounding check, dynamic git provenance, and v72 tests
  - `75193cb` Correct v70 delivery report, benchmark metadata, test assertions, and ruff lint error
  - `546b713` Record v70 three-mode benchmark run, same-map ablation, and delivery report

---

## 1. Executive Summary & Acceptance Bar Verification

Suggestion Prompt v73 executed two major objectives:
1. **Part A (Report Corrections):** Corrected all 6 factual and accounting defects in `docs/agentic_v72_delivery_report.md` (no behavior change).
2. **Part B (Safe Optimizations) & Part C (Re-Measurement):** Implemented safe, proven optimizations to eliminate wasted LLM judge calls and reduce measurement friction, subject to the strict acceptance bar: **zero negative decision flips vs v72, zero new false approvals, and zero new false denials.**

### Acceptance Bar Results: PASSED (100% Concordance Preservation, Zero Degradation)
- **Per-Case Decision Diffs vs v72:** Exactly **0** diffs across all 84 development vignettes.
- **Accuracy Preserved:** Exactly **48/84 (57.1%)** concordant decisions (identical to v72).
- **Safety Profile Preserved:** Exactly **0 False Approvals**, **0 False Denials**, and **36 Safe Deferrals**.
- **Synonymy Resolved:** Exactly **9/19 (47.4%)** (identical to v72).
- **Efficiency Wins Achieved:**
  - **Judge Calls:** Reduced from **114** in v72 down to **89** in v73 (**-25 calls, -21.9% reduction**).
  - **Pre-Deferral Reviews:** Dropped from **36** (24 completed, 12 budget-exhausted) down to **10** (10 completed, 26 safely skipped by narrowing, 0 budget-exhausted).
  - **Wall-Time Latency:** Reduced from **2391.87s** down to **2237.59s** (**154.28s faster**).
  - **Over-60s Wall-Time Cases:** Reduced from **29** in v72 down to **17** in v73 (**-12 cases, -41.4% reduction**).

---

## 2. Part A: Corrections to the v72 Delivery Report

All 6 identified defects in `docs/agentic_v72_delivery_report.md` have been corrected and verified:

1. **Over-60s Wall-Time Baseline:**
   - *Previous Record:* Incorrectly claimed v70 had 32 cases exceeding 60s and claimed v72 (29) was an improvement.
   - *Correction:* The true v70 baseline was **26** cases exceeding 60s. v72 (29 cases) was a wall-time regression (+3 cases) due to unblocking advocacy attempts.
2. **Agentic Synonymy Resolution Baseline:**
   - *Previous Record:* Stated v70 resolved 7/19 synonymy cases and claimed v72 resolved +2.
   - *Correction:* The true v70 baseline was **8/19** (`IMRT`, `KNEE-ORTHOSIS`, `LUMBAR-DECOMP`, `PROTON`, `RAD-NIV`, `CARDIAC-REHAB`, `MPI-PET`, `PUMP`). v72 resolved **9/19**, which was a **+1 case improvement** (`DEV-LCD-POWER-WC-APP`).
3. **`CRIT-SCS-02` Outcome Recording:**
   - *Previous Record:* Listed `CRIT-SCS-02` as "conceded".
   - *Correction:* Recorded as `UNRESOLVED_DISAGREEMENT`. In `DEV-NCD-SCS-APP`, the defense was cut off by the 60s per-case budget limit at wall time 76.28s, with the case safely deferring without concession.
4. **Pre-Deferral Review Split in v72:**
   - *Previous Record:* Grouped all 36 deferred cases as receiving a pre-deferral review.
   - *Correction:* Exactly **24 COMPLETED** review calls, while **12 SKIPPED_BUDGET_EXHAUSTED** because the 60s / 8-call budget was reached before the review stage.
5. **Ruff Error Remediation & Per-File Reporting:**
   - *Previous Record:* Left 2 new errors unaddressed (`pipeline.py` I001 unsorted import; `llm_proposer.py` UP045 `Optional[str]`).
   - *Correction:* Fixed I001 in `pipeline.py` and UP045 in `llm_proposer.py`. Reported exact per-file counts confirming zero net-new errors.
6. **Gain Attribution Accounting (Cataract Regression):**
   - *Previous Record:* Claimed 8 map + 2 agent = 10 net gain over declarative (39).
   - *Correction:* Accounted for `DEV-NCD-CATARACT-APP` draft-concept contradiction regression (47 declarative 131 vs 48 agentic): Map 8 + agent 2 - 1 (`CATARACT-APP`) = **9 net gain**.

---

## 3. Part B: Implementation of Safe Optimizations

### Task 2: Narrowed Pre-Deferral Review
- **The Rule:** In `app/agents/pipeline.py`, pre-deferral case-level review runs **ONLY** when a deferred case has at least one mandatory (non-exclusion) criterion with final status `MET` (`criteria_met_count > 0`). When `criteria_met_count == 0`, the review is safely skipped.
- **Clinical & System Rationality:** When a case has 0 mandatory criteria met, it is a straightforward deferral with no approval evidence to weigh or confirm; consulting the judge wastes an LLM call (~15s) and risks operational budget exhaustion. When >= 1 criterion is MET, the judge's case-level review confirms whether the remaining unproven criteria genuinely justify deferral over human clinician escalation.
- **Traceability & Audit:** When skipped, an `INFORM` message is posted to the shared message board with `metadata={"pre_deferral_review": True, "pre_deferral_review_skipped": True, "narrowing_rule_applied": True, "reason": "No mandatory criteria met; pre-deferral review narrowed to cases with >= 1 criterion MET"}`. Both `pre_deferral_review_completed` and `pre_deferral_review_skipped_by_narrowing` flags are recorded in `agentic_audit_trail["judge_routing"]`.
- **Pre-Deferral Review Distribution:**
  - **Reviewed (10 Cases):**
    1. `DEV-LCD-MRI-BRAIN-APP`
    2. `DEV-LCD-MRI-LUMBAR-APP`
    3. `DEV-LCD-PAD-ATHERO-APP`
    4. `DEV-LCD-SBRT-APP`
    5. `DEV-NCD-CATARACT-APP`
    6. `DEV-NCD-CCTA-APP`
    7. `DEV-NCD-PACEMAKER-APP`
    8. `DEV-NCD-PET-ONC-APP`
    9. `DEV-NCD-SGD-APP`
    10. `DEV-OPD-SI-FUSION-APP`
  - **Skipped by Narrowing (26 Cases):** All cases with 0 criteria MET (e.g. `DEV-LCD-ACDF-NEG`, `DEV-LCD-FACET-APP`, etc.).
  - **Budget-Exhausted Halts at Review:** **0** (eliminated all 12 budget-exhausted stalls).

### Task 3: Measurement Script Wins
1. **Deterministic / Declarative Baseline Reuse (`--reuse-baselines`):**
   - Implemented `verify_baseline_reuse_validity()` in `scripts/run_agentic_v59_three_mode_measurement.py`.
   - Executes `git diff --name-only <prev_head> HEAD` against critical files (`app/core/concept_map.py`, `app/services/declarative_engine.py`, `app/data/concept_map.json`, `app/data/policies_extended/`, `carepolicyguard.db`).
   - Verified 0 critical files modified since `41350ec`; safely reused baseline runs, eliminating ~400s of redundant re-execution.
2. **Ollama Keep-Alive Pinning (`warmup_ollama`):**
   - Issues a pre-run API call to `http://127.0.0.1:11434/api/generate` with `keep_alive="60m"` and model `qwen2.5:3b`.
   - Prevents model unloads between batches or idle turn pauses, stabilizing per-call inference latency.
3. **Bench-Only Execution Flag (`--bench-only`):**
   - Added `--bench-only` flag to allow fast verification runs against the 10 standard `BENCH-01..10` benchmark vignettes.

---

## 4. Benchmark Measurement & Same-Map Ablation (v73)

### Four-Number Safety Comparison across 84 Dev Vignettes

| Evaluation Arm | Accuracy / Concordance | False Approvals | False Denials | Safe Deferrals | Synonymy Resolved |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Arm 1: Deterministic Engine** (12 committed concepts) | 37/84 (44.0%) | 0 (0.0%) | 2 (2.4%) | 45 (53.6%) | 0/19 (0.0%) |
| **Arm 2: Declarative LLM Engine** (12 committed concepts) | 39/84 (46.4%) | 0 (0.0%) | 0 (0.0%) | 45 (53.6%) | 0/19 (0.0%) |
| **Ablation: Declarative Engine** (131 merged concepts) | 48/84 (57.1%) | 0 (0.0%) | 0 (0.0%) | 36 (42.9%) | 10/19 (52.6%) |
| **Arm 3: Agentic Pipeline** (131 merged concepts, v73) | **48/84 (57.1%)** | **0 (0.0%)** | **0 (0.0%)** | **36 (42.9%)** | **9/19 (47.4%)** |

### Same-Map Ablation Analysis (Declarative 131 vs Agentic 131)
When both Declarative and Agentic pipelines run on the identical 131-concept merged map:
- **Declarative (131 concepts):** 48/84 (57.1%), 0 FA, 0 FD, 36 Deferrals, 10/19 synonymy.
- **Agentic (131 concepts, v73):** 48/84 (57.1%), 0 FA, 0 FD, 36 Deferrals, 9/19 synonymy.
- **Agent-Attributable Net Gain:** **0** (48 vs 48).
- **Per-Case Diffs (4 cases total):**
  - `DEV-LCD-PCI-APP`: Agentic **APPROVED** (Concordant), Declarative **DEFERRED** (+1 Agentic rescue).
  - `DEV-LCD-POWER-WC-APP`: Agentic **APPROVED** (Concordant), Declarative **DEFERRED** (+1 Agentic rescue).
  - `DEV-LCD-SBRT-APP`: Declarative **APPROVED** (Concordant), Agentic **DEFERRED** (-1 Agentic debate regression via concession).
  - `DEV-OPD-SI-FUSION-APP`: Declarative **APPROVED** (Concordant), Agentic **DEFERRED** (-1 Agentic debate regression via concession).

---

## 5. Judge-Call Volume, Efficiency & Wall-Time Latency

| Metric | v70 Baseline | v72 Baseline | v73 (Safe Optimizations) | Delta (v73 vs v72) |
| :--- | :--- | :--- | :--- | :--- |
| **Total LLM Judge Calls** | 109 | 114 | **89** | **-25 calls (-21.9%)** |
| **Pre-Deferral Review Calls** | 36 | 36 (24 ran / 12 timeout) | **10** (10 ran / 26 skipped) | **-26 calls skipped** |
| **Advocate Span Verifications** | 0 | 2 | **3** | +1 call |
| **Advocate Span Rejections** | 0 | 1 | **2** | +1 rejection |
| **Total Agentic Wall Time** | 2244.60s | 2391.87s | **2237.59s** | **-154.28s faster** |
| **Cases Exceeding 60s Wall Time**| 26 | 29 | **17** | **-12 cases (-41.4%)** |
| **Operational Budget Halts** | 12 | 12 | **0 at Review Stage** | **-12 halts eliminated** |

---

## 6. Verification, Tests & Quality Gates (Tasks 3, 4, 6)

### Pytest Regression Suite: 16/16 PASSED in 33.84s
- **`tests/test_v73_safe_optimizations.py`:** 4/4 PASSED.
  1. `test_pre_deferral_review_runs_when_mandatory_criterion_met`: PASSED.
  2. `test_pre_deferral_review_skipped_when_no_mandatory_criterion_met`: PASSED.
  3. `test_judge_core_work_unchanged`: PASSED.
  4. `test_baseline_reuse_validation_mechanism`: PASSED.
- **`tests/test_v72_provisional_equivalence.py`:** 5/5 PASSED.
  1. `test_grounded_judge_verified_met_with_unmapped_concept_not_killed_by_gate_c`: PASSED.
  2. `test_guard_does_not_block_grounded_met`: PASSED.
  3. `test_genuinely_ungrounded_met_still_blocked_by_guard`: PASSED.
  4. `test_conceded_criterion_still_blocked_by_guard`: PASSED.
  5. `test_committed_concept_map_unchanged_at_12_concepts`: PASSED.
- **`tests/test_v70_routing_and_efficiency.py`:** 4/4 PASSED.
  1. `test_deferred_case_has_recorded_advocate_attempt_for_unproven_criteria`: PASSED.
  2. `test_advocate_span_requires_judge_verification_before_promotion`: PASSED.
  3. `test_deferred_case_has_recorded_judge_confirmation`: PASSED.
  4. `test_fully_verified_case_makes_zero_llm_calls`: PASSED.
- **`tests/test_frontend_js_syntax.py`:** 3/3 PASSED.
  1. `test_app_js_syntax_validity`: PASSED.
  2. `test_app_js_syntax_gate_catches_broken_syntax`: PASSED.
  3. `test_frontend_auth_handlers_present_and_wired`: PASSED.

### Ruff Linting & Quality Verification:
- `app/agents/pipeline.py`: 340 errors (reduced from 351 on `41350ec`; **0 net-new errors**).
- `app/agents/llm_proposer.py`: 370 errors (reduced from 378 on `41350ec`; **0 net-new errors**).
- `app/schemas/message_board.py`: **0 errors (Clean)**.
- `scripts/run_agentic_v59_three_mode_measurement.py`: 22 errors (unchanged from 22 on `41350ec`; **0 net-new errors**).
- `tests/test_v73_safe_optimizations.py`: **0 errors (Clean)**.

---

## 7. Mandatory Disclosures & Unproven Items

In accordance with strict reporting standards:
1. **Agentic vs Declarative Parity:** The agentic architecture with 131 concepts achieves **48/84 (57.1%)**, matching Declarative on the same 131-concept map (**48/84**). While the agentic mode successfully rescues 2 cases through LLM reasoning and advocacy (`DEV-LCD-PCI-APP` and `DEV-LCD-POWER-WC-APP`), these are offset by 2 debate regressions (`DEV-LCD-SBRT-APP` and `DEV-OPD-SI-FUSION-APP`).
2. **Synthetic Dataset Notice:** The 84 development vignettes are author-written synthetic calibration vignettes, not clinical validation or real-world patient records.
3. **Local Hardware Constraints:** All tests and benchmark measurements executed locally using `qwen2.5:3b` under Ollama on Windows.
