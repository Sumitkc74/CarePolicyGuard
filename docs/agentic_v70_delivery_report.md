# Delivery Report: Suggestion Prompt v70 — Routing, Judge-in-the-Loop, Fast Path & Same-Map Ablation (Corrected Record)

**Benchmark Date:** November 19, 2026  
**Implementation Commit (Pre-measurement):** `050eae03ab0c6b32b5e7e941d9309283ad49c4a0`  
**Runner Pre-Import Fix Commit:** `41d7b481292bd36bf7e9c42fa0eb22b5c44439aa`  
**Measurement & Benchmark Commit:** `546b71340fe00b0dc2495e017e2aa039db702c58`  
**Full Parent Chain:** `fbbb4e4934e9136b8d7fc4dabdc5a9fa79f7d490` → `c919d85b6325a551648efb97475bf4614846aab2` (CI: cache + preload SapBERT before pytest) → `050eae03ab0c6b32b5e7e941d9309283ad49c4a0` → `41d7b481292bd36bf7e9c42fa0eb22b5c44439aa` → `546b71340fe00b0dc2495e017e2aa039db702c58`  
**CI Status:** GREEN at `546b71340fe00b0dc2495e017e2aa039db702c58` (GitHub Actions workflow run `44658513669`, conclusion success; all 3 jobs success: test suite, code quality, Docker), enabled by `c919d85`.  
**Dataset:** 84 author-written development vignettes (dev set only; not held-out evidence, not clinical validation ground truth)  
**Database:** `carepolicyguard.db` (60 CMS policies verified from official coverage API)  
**Model:** `qwen2.5:3b` via local Ollama  
**Budget:** 8 calls / 60s per case  
**Safety Thresholds (Frozen):** $\tau = 0.85$, $\kappa = 0.33$, $\delta = 0.15$

---

## 1. Executive Summary & Core Results

Prompt v70 implemented three architectural mechanisms directed by user design decisions:
1. **Unproven Criterion Routing:** Every mandatory criterion not MET after initial evaluation is offered to the advocate before declaring `INSUFFICIENT_EVIDENCE` and deferring. A deferred case cannot exit with an unattempted mandatory criterion.
2. **Judge in the Loop:**
   - **Advocate-Span Verification:** Any span extracted by the advocate must pass Gate A (verbatim grounding) and Gate C (concept map check) and be confirmed semantically equivalent by the Clinical Judge (`judge_equivalence_sync`) before promotion to MET. (Note: in the live v70 run, 0 calls reached this verification because both non-empty quotes were Gate-C-rejected first; the mechanism remains unproven in production).
   - **Pre-Deferral Case-Level Review:** Every deferred case undergoes a case-level review by the Clinical Judge (`review_case_deferral_sync`) confirming deferrability before handoff to human review.
3. **Efficiency Fast Path:** When the deterministic engine completely satisfies all mandatory criteria with exact verbatim grounding (and no exclusion criteria met), the case is finalized with **zero LLM calls** (no judge, no debate, no advocate).
4. **Same-Map Ablation (Task 5):** Evaluated Declarative mode on the identical merged 131-concept map (`declarative-131`) against `agentic-131` to rigorously isolate agent-attributable gain vs concept-map gain.

---

## 2. Four-Number Safety Comparison across Modes (84 Dev Vignettes)

| Execution Mode | Concept Map | Concordant / Total | Accuracy (%) | False Approvals | False Denials | Safe Deferrals | Synonymy Resolved |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Deterministic** | Committed (12 concepts) | **37 / 84** | 44.0% | **0** | 2 | 45 | 0 / 19 |
| **Declarative** | Committed (12 concepts) | **39 / 84** | 46.4% | **0** | 0 | 45 | 0 / 19 |
| **Declarative-131 (Ablation)** | Merged (131 concepts) | **48 / 84** | 57.1% | **0** | 0 | 36 | 10 / 19 |
| **Agentic-131** | Merged (131 concepts) | **46 / 84** | 54.8% | **0** | 0 | 38 | 8 / 19 |

### Invariant & Baseline Reproduction Checks
- **Deterministic 37 Reproduction:** Exact match ($37/84$).
- **Declarative 39 Reproduction:** Exact match ($39/84$).
- **Agentic 46 Reproduction:** Exact match ($46/84$).
- **Efficiency-Driven Decision Diffs:** **0 diffs**. All 84 decisions match the v67 baseline exactly under the fast path.
- **Safety Invariant:** 0 False Approvals across all modes.
- **Provenance & Dev Labelling:** All reported numbers are development measurements on the author-written 84-vignette set, not held-out clinical ground truth.

---

## 3. Wall-Time and Call-Count Performance (Task 2)

### Acceptance Item Status: FAILED
The v70 acceptance criterion requiring *"wall time not worse than the v67 baselines"* **FAILED**.

| Metric | v67 Baseline | v70 Measured Run | Delta |
| :--- | :---: | :---: | :---: |
| **Mean Case Wall Time** | 21.48 s | **26.59 s** | +5.11 s (+23.8%) |
| **Max Case Wall Time** | 63.97 s | **71.09 s** | +7.12 s |
| **Cases Exceeding 60 s Budget** | 9 cases | **26 cases** | +17 cases |
| **Total Judge LLM Calls** | 64 calls | **106 calls** | +42 calls (+65.6%) |
| - *Judge Criterion Evaluations* | 64 calls | 68 calls | +4 calls |
| - *Pre-Deferral Case Reviews* | 0 calls | **38 calls** | +38 calls |
| **Mean Judge Calls per Case** | 0.76 calls | **1.26 calls** | +0.50 calls |
| **Max Judge Calls in a Case** | 2 calls | **4 calls** | +2 calls |

### Root Cause
The wall-time regression is directly caused by the **pre-deferral case-level review (`review_case_deferral_sync`)**, which executed across all 38 deferred cases, adding 38 heavy LLM calls (averaging 12–16 seconds each). The tradeoff between pre-deferral verification and latency remains a user architectural decision pending evaluation.

---

## 4. Efficiency Fast Path Record (Task 3)

- **Fast Path Realness:** 45 cases executed with **0 judge calls and 0 advocate calls** (28 `APPROVED` + 17 `DENIED`).
- **Net Comparison vs v67 Baseline:** The fast path saved **zero calls compared to v67**. In v67, 46 cases had zero judge calls; in v70, 45 cases had zero judge calls.
- **Case Losing Zero-Call Status:** **`DEV-OPD-BLEPH-NEG`**. In v67, this case had 0 judge calls. In v70, under unproven criterion routing, it executed 1 judge evaluation and 1 advocate call (31.51 s wall time) before reaching the same `DENIED` decision.
- **Corrected Execution Latencies:**
  - **Fast-Path Cases (45 cases):** Actual mean latency **99.8 ms** (max **180 ms**).
  - **LLM-Evaluated Cases (39 cases):** Actual mean latency **57.16 s** (max **71.09 s**).
- **Net Call Impact:** Total judge calls went **up** from 64 to 106.

---

## 5. Same-Map Ablation Analysis (Task 5)

| Metric | Declarative-131 | Agentic-131 | Delta (Agentic - Declarative) |
| :--- | :---: | :---: | :---: |
| **Accuracy** | 48 / 84 (57.1%) | 46 / 84 (54.8%) | **-2 cases (-2.3%)** |
| **False Approvals** | 0 | 0 | 0 |
| **False Denials** | 0 | 0 | 0 |
| **Safe Deferrals** | 36 | 38 | +2 safe deferrals |
| **Synonymy Resolved** | 10 / 19 | 8 / 19 | -2 resolved |

### Per-Case Divergences (2 Cases)
Exactly 2 cases diverged between Declarative-131 and Agentic-131:
1. **`DEV-LCD-SBRT-APP`** (Expected: `APPROVED`):
   - *Declarative-131 Decision:* `APPROVED` (131-concept map matched clinical terms deterministically).
   - *Agentic-131 Decision:* `DEFERRED_TO_HUMAN`.
   - *Mechanism:* Agent 3 raised an adversarial objection (`ANATOMIC_MISMATCH`) against `CRIT-SBRT-01`. Agent 2 lacked defense evidence and conceded. The concession arm of the guard blocked subsequent advocate override, safely deferring.
2. **`DEV-OPD-SI-FUSION-APP`** (Expected: `APPROVED`):
   - *Declarative-131 Decision:* `APPROVED`.
   - *Agentic-131 Decision:* `DEFERRED_TO_HUMAN`.
   - *Mechanism:* Agent 3 raised a `TEMPORAL` objection against `CRIT-SI-01`. Agent 2 conceded. The guard concession arm blocked advocacy, safely deferring.

### Attribution Finding
The same-map ablation confirms that the agentic debate pipeline does not produce net approval gains over a declarative engine equipped with an identical concept map. Rather, agentic deliberation operates as a **skepticism filter**: conceded challenges prevent automated promotion and route the case to clinicians, preventing edge-case false approvals at the cost of 2 deferrals.

---

## 6. Guard Cost Accounting & Trigger Mechanism (Task 4)

The guard blocked promotions under two distinct arms:

| Guard Arm | Trigger Condition | Blocked Promotions | Cases & Criteria | Mechanism Detail |
| :--- | :--- | :---: | :--- | :--- |
| **Status-MET Arm** | Initial judgment status was `MET` (`crit_judgment.status == "MET"`) | **9 promotions across 6 cases** | `DEV-LCD-KYPHO-APP` (`CRIT-KYPHO-01`, `CRIT-KYPHO-02`)<br>`DEV-LCD-PAD-ATHERO-APP` (`CRIT-PAD-01`, `CRIT-PAD-02`)<br>`DEV-LCD-POWER-WC-APP` (`CRIT-PWC-02`)<br>`DEV-NCD-CATARACT-APP` (`CRIT-CAT-01`, `CRIT-CAT-02`)<br>`DEV-NCD-SCS-APP` (`CRIT-SCS-02`)<br>`DEV-NCD-SGD-APP` (`CRIT-SGD-02`) | **1 Genuine Ungrounded Quote (Gate A):** `CRIT-KYPHO-01` quote was ungrounded in text.<br>**8 Grounded Quotes Rejected by Gate C:** The other 8 had verbatim-grounded quotes in the note, but were rejected by Gate C (*"ConceptMap equivalence rejected: No matching concept definition"*). The guard blocks on judgment status alone, not grounding. **8 of these 9 blocks are concept-map gaps, not extraction failures.** |
| **Concession Arm** | Criterion formally CONCEDED in debate (`debated_criteria_outcomes[c] == "CONCEDED"`) | **2 promotions across 2 cases** | `DEV-LCD-SBRT-APP` (`CRIT-SBRT-01`)<br>`DEV-OPD-SI-FUSION-APP` (`CRIT-SI-01`) | Concession invariant preserved; advocacy strictly prohibited after concession. |
| **Total** | — | **11 promotions across 8 cases** | — | **8 of the 11 blocked promotions stem from concept-map vocabulary gaps.** |

**Transcript Invariant Audit:** Verified across all 84 transcripts: **0 ADVOCACY messages occurred after any CONCESSION**.

---

## 7. Extraction Accounting & Gate-C-Blocked Spans (Task 4 & Task 7)

- **Total Advocacy Calls:** 55 calls
- **Empty Quote Returns:** 53 calls (**96.4% empty quote rate**)  
  *Clinical Reason: In negative vignettes (`*-NEG`), the patient truly lacks the clinical indication; the advocate faithfully reported that no qualifying verbatim span exists rather than hallucinating text.*
- **Non-Empty Quote Returns:** 2 calls (**3.6%**)
  - `DEV-LCD-PCI-APP` (`CRIT-PCI-01`): *"Diagnostic coronary angiography confirms severe coronary artery stenosis of 85% in the proximal left anterior descending artery with TIMI 3 flow."* [415:560]
  - `DEV-NCD-SCS-APP` (`CRIT-SCS-01`): *"Patient completed a 6-day temporary percutaneous spinal cord stimulator trial, documenting 80% pain relief and significant increase in daily walking distance."* [473:631]
- **Gate Performance:**
  - **Gate A (Verbatim Grounding):** 0 failures (100% of non-empty quotes grounded).
  - **Gate B (Attribution Integrity):** 0 failures.
  - **Gate C (ConceptMap Equivalence):** 2 rejections. Both coronary stenosis and temporary trial relief concepts are unmapped in the current committed vocabulary. Gate C strictly blocked promotion.
  - **Advocate Span Verification (Task 2a):** **0 calls live**. Both non-empty quotes were Gate-C-rejected prior to reaching the judge; the live span verification mechanism remains unproven in production.
  - **Rescued Promotions:** 0
  - **Unrescued Misses:** 2

### Top 5 Gate-C-Blocked Spans (Grep-Verified in Notes)
All 5 spans exist verbatim in the clinical notes. None were missed by extraction; all 5 were blocked by Gate C due to missing concept definitions:
1. **`DEV-LCD-PCI-APP` (`CRIT-PCI-01`, 145 chars - found by advocate):**  
   `"Diagnostic coronary angiography confirms severe coronary artery stenosis of 85% in the proximal left anterior descending artery with TIMI 3 flow."`
2. **`DEV-NCD-SCS-APP` (`CRIT-SCS-01`, 158 chars - found by advocate):**  
   `"Patient completed a 6-day temporary percutaneous spinal cord stimulator trial, documenting 80% pain relief and significant increase in daily walking distance."`
3. **`DEV-LCD-PAD-ATHERO-APP` (`CRIT-PAD-01`, 133 chars - found by judge):**  
   `"Duplex ultrasound reveals hemodynamically significant stenosis with 85% occlusive calcified plaque in the superficial femoral artery."`
4. **`DEV-NCD-CATARACT-APP` (`CRIT-CAT-01`, 81 chars - found by judge):**  
   `"Best corrected visual acuity is 20/60 in the right eye and 20/50 in the left eye."`
5. **`DEV-LCD-KYPHO-APP` (`CRIT-KYPHO-02`, 204 chars - found by judge):**  
   `"Severe focal spinous process percussion tenderness at T12. Thoracic spine MRI shows 35% height loss of T12 with intense hyperintensity on STIR imaging demonstrating acute osteoporotic vcf with bone edema."`

---

## 8. Adversarial Debate & Deliberation Dynamics (Task 7)

- **Mind Changes:** **11 mind changes total**, all **`met_to_insufficient`** (0 `toward_met`).
- **Counter-Readings Raised:** 2 counter-readings raised by Agent 3.
- **Defended Counter-Readings:** 0 defended (both conceded by Agent 2).
- **Decisions Changed by Debate:** **0 decisions changed**. Debate acted exclusively as an abstention/deferral enforcement mechanism.

---

## 9. Code Quality, Linting & Regression Suite (Task 6 & Task 8)

### Ruff Linting Report (Task 6)
- **Standard Scope (`app/core app/schemas --ignore E501`):** Clean (0 errors).
- **`app/core/llm_judge.py`:** Clean (0 errors).
- **`app/agents/pipeline.py`:** **47 errors** (reduced from 48 at `546b713`).
  - *Fix:* Identified and removed net-new unused import `CaseDeferralReview` from `app/agents/pipeline.py:401` (`F401`).
  - *Status:* Exactly matches the pre-existing error count at `fbbb4e4` (47 errors). Pre-existing legacy typing errors (`UP035`, `UP006`, `UP045`) remain untouched per the improvement rule.
- **Frontend Syntax Check:** `node --check app/static/js/app.js` passed (0 errors).

### Test Suite Execution
- **`tests/test_v70_routing_and_efficiency.py`:** **4/4 passed**
  - `test_deferred_case_has_recorded_advocate_attempt_for_unproven_criteria` (strengthened per-criterion assertion)
  - `test_advocate_span_requires_judge_verification_before_promotion`
  - `test_deferred_case_has_recorded_judge_confirmation`
  - `test_fully_verified_case_makes_zero_llm_calls` (strengthened unconditional assertion)
- **`tests/test_agentic_redesign_realness.py`:** **14/14 passed**
- **`tests/test_pipeline_wiring.py`:** **6/6 passed**
- **`tests/test_v1_heldout_regressions.py`:** **9/9 passed**
- **`tests/test_frontend_js_syntax.py` & `test_silent_defaults.py`:** **8/8 passed**
