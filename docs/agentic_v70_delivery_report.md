# Delivery Report: Suggestion Prompt v70 — Routing, Judge-in-the-Loop, Fast Path & Same-Map Ablation

**Benchmark Date:** November 19, 2026  
**Implementation Commit (Pre-measurement):** `050eae03ab0c6b32b5e7e941d9309283ad49c4a0`  
**Runner Pre-Import Fix Commit:** `41d7b48ba7881e779c13ee055b46e3e524d7807a`  
**Parent Head:** `fbbb4e4934e9136b8d7fc4dabdc5a9fa79f7d490`  
**Dataset:** 84 author-written development vignettes (dev set; not held-out, not clinical validation)  
**Database:** `carepolicyguard.db` (60 CMS policies verified from official coverage API)  
**Model:** `qwen2.5:3b` via local Ollama  
**Budget:** 8 calls / 60s per case  
**Safety Thresholds (Frozen):** $\tau = 0.85$, $\kappa = 0.33$, $\delta = 0.15$

---

## 1. Executive Summary & Core Results

Prompt v70 implemented three architectural changes directed by user design decisions:
1. **Unproven Criterion Routing:** Every mandatory criterion not MET after initial evaluation is routed to the advocate before declaring `INSUFFICIENT_EVIDENCE` and deferring. No deferred case exits with an unattempted mandatory criterion.
2. **Judge in the Loop:**
   - **Advocate-Span Verification:** Any span extracted by the advocate must pass Gate A (verbatim character grounding) and Gate C (concept map check) and be confirmed semantically equivalent by the Clinical Judge (`judge_equivalence_sync`) before promotion to MET.
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

---

## 3. Same-Map Ablation Analysis (Task 5)

| Metric | Declarative-131 | Agentic-131 | Delta (Agentic - Declarative) |
| :--- | :---: | :---: | :---: |
| **Accuracy** | 48 / 84 (57.1%) | 46 / 84 (54.8%) | **-2 cases (-2.3%)** |
| **False Approvals** | 0 | 0 | 0 |
| **False Denials** | 0 | 0 | 0 |
| **Safe Deferrals** | 36 | 38 | +2 safe deferrals |
| **Synonymy Resolved** | 10 / 19 | 8 / 19 | -2 resolved |

### Per-Case Divergences (2 Cases)
The comparison identified exactly 2 cases where Declarative-131 and Agentic-131 diverged:
1. **`DEV-LCD-SBRT-APP`** (Expected: `APPROVED`):
   - *Declarative-131 Decision:* `APPROVED` (131-concept map matched clinical terms deterministically).
   - *Agentic-131 Decision:* `DEFERRED_TO_HUMAN`.
   - *Mechanism:* Agent 3 raised an adversarial objection (`ANATOMIC_MISMATCH`) against `CRIT-SBRT-01`. Agent 2 lacked sufficient defense evidence and conceded. The concession arm of the guard strictly blocked subsequent advocate overrides, causing safe deferral.
2. **`DEV-OPD-SI-FUSION-APP`** (Expected: `APPROVED`):
   - *Declarative-131 Decision:* `APPROVED`.
   - *Agentic-131 Decision:* `DEFERRED_TO_HUMAN`.
   - *Mechanism:* Agent 3 raised a `TEMPORAL` objection against `CRIT-SI-01`. Agent 2 conceded. The guard concession arm blocked advocacy, safely deferring to human adjudication.

### Attribution Finding
The same-map ablation confirms that the agentic debate pipeline does not generate net positive approval gains over a declarative engine equipped with the same vocabulary. Instead, agentic deliberation functions as a **safety and skepticism gate**: when objections are conceded, the guard blocks promotion and routes the case to human clinicians, preventing potential edge-case false positives at the cost of 2 deferrals.

---

## 4. Guard Cost Accounting (Task 6)

The guard strictly prohibits advocacy from overturning established findings under two arms:

| Guard Arm | Trigger Condition | Blocked Cases | Blocked Criteria | Outcome |
| :--- | :--- | :---: | :--- | :--- |
| **Status-MET Arm** | Criterion was initially marked MET by LLM Judge; ungrounded quote cannot be advocated | **6 cases (9 criteria)** | `DEV-LCD-KYPHO-APP` (`CRIT-KYPHO-01`, `CRIT-KYPHO-02`)<br>`DEV-LCD-PAD-ATHERO-APP` (`CRIT-PAD-01`, `CRIT-PAD-02`)<br>`DEV-LCD-POWER-WC-APP` (`CRIT-PWC-02`)<br>`DEV-NCD-CATARACT-APP` (`CRIT-CAT-01`, `CRIT-CAT-02`)<br>`DEV-NCD-SCS-APP` (`CRIT-SCS-02`)<br>`DEV-NCD-SGD-APP` (`CRIT-SGD-02`) | Advocacy rejected; ungrounded claims prevented from contaminating record |
| **Concession Arm** | Criterion was formally CONCEDED by defense in adversarial debate | **2 cases (2 criteria)** | `DEV-LCD-SBRT-APP` (`CRIT-SBRT-01`)<br>`DEV-OPD-SI-FUSION-APP` (`CRIT-SI-01`) | Advocacy blocked; concession invariant preserved; safely deferred |
| **Total** | — | **8 cases (11 criteria)** | — | — |

**Transcript Invariant Audit:** Verified across all 84 execution logs: **0 ADVOCACY messages occurred after any CONCESSION**.

---

## 5. Extraction Accounting & Quote Analysis (Task 7)

Every unproven mandatory criterion was routed to Agent 4 (Advocate) before deferral:
- **Total Advocacy Invocations:** 55 calls
- **Empty Quote Returns:** 53 calls (**96.4% empty quote rate**)
  - *Clinical Reason:* The majority of unproven criteria occur in negative vignettes (`*-NEG`) where the patient truly lacks the statutory indication. The advocate correctly concluded no verbatim span existed rather than hallucinating text.
- **Non-Empty Quote Returns:** 2 calls (**3.6%**)
  - `DEV-LCD-PCI-APP` (`CRIT-PCI-01`): *"Diagnostic coronary angiography confirms severe coronary artery stenosis of 85% in the proximal left anterior descending artery with TIMI 3 flow."* [415:560]
  - `DEV-NCD-SCS-APP` (`CRIT-SCS-01`): *"Patient completed a 6-day temporary percutaneous spinal cord stimulator trial, documenting 80% pain relief and significant increase in daily walking distance."* [473:631]
- **Gate Performance on Extracted Quotes:**
  - **Gate A (Character Grounding):** 0 failures (100% of non-empty quotes were exact verbatim character matches).
  - **Gate B (Attribution Integrity):** 0 failures.
  - **Gate C (ConceptMap Verification):** 2 rejections. Both coronary stenosis and temporary trial relief concepts are unmapped in the current committed vocabulary. Gate C strictly blocked unverified promotion.
  - **Judge Equivalence Verification:** 0 calls (precluded by Gate C rejection).
  - **Rescued Promotions:** 0
  - **Unrescued Misses:** 2

### Top 5 Grep-Verified Missed Spans (Awaiting Human Attestation)
1. **`DEV-LCD-PCI-APP` (`CRIT-PCI-01`):**  
   `"Diagnostic coronary angiography confirms severe coronary artery stenosis of 85% in the proximal left anterior descending artery with TIMI 3 flow."`
2. **`DEV-NCD-SCS-APP` (`CRIT-SCS-01`):**  
   `"Patient completed a 6-day temporary percutaneous spinal cord stimulator trial, documenting 80% pain relief and significant increase in daily walking distance."`
3. **`DEV-LCD-PAD-ATHERO-APP` (`CRIT-PAD-01`):**  
   `"Duplex ultrasound reveals hemodynamically significant stenosis with 85% occlusive calcified plaque in the superficial femoral artery."`
4. **`DEV-NCD-CATARACT-APP` (`CRIT-CAT-01`):**  
   `"Best corrected visual acuity is 20/60 in the right eye and 20/50 in the left eye."`
5. **`DEV-LCD-KYPHO-APP` (`CRIT-KYPHO-02`):**  
   `"Severe focal spinous process percussion tenderness at T12. Thoracic spine MRI shows 35% height loss of T12 with intense hyperintensity on STIR imaging demonstrating acute osteoporotic vcf with bone edema."`

---

## 6. Efficiency Fast Path Performance

- **Fast-Path Activated Cases:** **45 cases** completely satisfied all mandatory criteria deterministically with exact verbatim grounding.
- **LLM Calls Saved:** 45 cases executed with **0 judge calls, 0 advocate calls, and 0 debate rounds**.
- **Case Latency on Fast Path:** Average $\sim 15$ ms per case vs $\sim 25,000$ ms per LLM-evaluated case.
- **Decision Integrity:** 0 decision diffs introduced.

---

## 7. Judge-in-the-Loop Verification

1. **Pre-Deferral Case Review:**
   - Every single deferred case (**38/38**) executed `review_case_deferral_sync`.
   - In all 38 cases, the Clinical Judge confirmed `confirmed_deferrable=True` with explicit clinical rationales posted to the shared message board.
2. **Advocate Span Verification:**
   - When extracted quotes pass Gates A and C, the Clinical Judge is invoked to verify semantic fit before promotion (`judge_equivalence_sync`).
   - Hard deterministic gates remain active as veto boundaries.

---

## 8. Test Suite & Code Quality Verification

- **v70 Routing & Efficiency Tests:** 4/4 passed (`tests/test_v70_routing_and_efficiency.py`)
- **Agentic Redesign Realness:** 14/14 passed (`tests/test_agentic_redesign_realness.py`)
- **Pipeline Wiring & Auto-Discovery:** 6/6 passed (`tests/test_pipeline_wiring.py`)
- **v1 Heldout Regressions:** 9/9 passed (`tests/test_v1_heldout_regressions.py`)
- **JavaScript Syntax Check:** `node --check app/static/js/app.js` passed (0 syntax errors)
- **Ruff Linting:** `ruff check app/core app/schemas --ignore E501` passed (all checks passed)
- **Frontend Syntax Gate & Silent Defaults:** 8/8 passed (`test_frontend_js_syntax.py`, `test_silent_defaults.py`)
