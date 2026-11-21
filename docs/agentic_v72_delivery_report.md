# Agentic Adjudication Delivery Report (v72)
**Implementation & Measurement: Gate C Provisional-Equivalence Path, Guard Grounding Check, Dynamic Provenance & Re-Measurement**

- **Date:** November 21, 2026
- **Git Commit (Implementation & Tests):** `e3b4bc625537af22fee5b1840732edd09839dadc`
- **Parent Git Commit (v71 Acceptance):** `75193cb62c7a57c1dbd17f1b2925438866284b93`
- **Parent Chain Verified via Git:**
  - `e3b4bc6` Implement Gate C provisional-equivalence path, guard grounding check, dynamic git provenance, and v72 tests
  - `75193cb` Correct v70 delivery report, benchmark metadata, test assertions, and ruff lint error
  - `546b713` Record v70 three-mode benchmark run, same-map ablation, and delivery report
  - `41d7b48` Pre-import transformers and reorder retrieval sanity check first in measurement script
  - `050eae0` Implement v70 routing, judge-in-the-loop, efficiency fast path and same-map ablation
  - `c919d85` ci: cache and preload SapBERT model before pytest in CI runner
  - `fbbb4e4` Execute v67 three-mode and retrieval re-measurement, record runner and results JSON
  - `938fce1` Pin frontend JS syntax gate and handlers check in CI and pytest suite (v67 Task 4)
  - `447c2ba` Fix NCD-100.1 spurious shortlist match, add word-boundary guards, and rebuild vector store (v68)
  - `ea0bab6` Fix syntax error in app.js and update frontend script cache buster
- **Database:** `carepolicyguard.db` (60 official CMS policies)
- **Local Model:** `qwen2.5:3b` via local Ollama (`http://127.0.0.1:11434`)
- **Benchmark Run Artifact:** [`agentic_v72_three_mode_run.json`](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/agentic_v72_three_mode_run.json)

---

## 1. Executive Summary & Core Results

In Suggestion Prompt v70, 8 valid synonymy criteria with 100% verbatim quotes in the clinical narrative were erroneously killed by Gate C because their clinical terms were absent from the committed concept map (which remains strictly frozen at 12 concepts). The subsequent status-MET guard arm then blanket-blocked advocacy, mistaking concept-map absence for an ungrounded extraction failure.

Prompt v72 resolves this architectural gap while maintaining the governing rule: **Semantic equivalence must be understood, never deferred for that sole reason; genuine ambiguity must defer.**

### Key Findings of the v72 Delivery:
1. **Gate C Provisional-Equivalence Path (Task 1):** Zero of the 8 Gate C criteria were killed by Gate C in v72. When Gate A passes (exact verbatim quote in EHR note) and the Clinical Judge returns `MET` (or verifies advocate equivalence), but the concept is unmapped, Gate C passes provisionally. The concept is queued for human attestation (`needs_human_attestation: True`), posted to the message board, recorded in the audit trail, and the case proceeds. The committed map remains strictly frozen at 12 concepts.
2. **Guard Grounding Check (Task 2):** In `app/agents/pipeline.py`, the status-MET guard arm now blocks only when a quote is **genuinely ungrounded** (locating to `-1` in the text, Gate A failure). The 8 grounded quotes rejected by Gate C in v70 were unblocked. The concession arm remains 100% strictly enforced (`CRIT-SBRT-01` and `CRIT-SI-01` pattern).
3. **Agentic Accuracy Gain (+2 Cases, 48/84 = 57.1%):** Agentic mode increased from 46/84 (54.8%) in v70 to **48/84 (57.1%)** in v72.
   - `DEV-LCD-POWER-WC-APP` was approved (+1) after `CRIT-PWC-02` passed Gate C provisionally and successfully defended against counter-reading.
   - `DEV-LCD-PCI-APP` was approved (+1) via live advocate span verification: Agent 3 advocate found the LAD stenosis quote, and the Clinical Judge verified it as equivalent, promoting `CRIT-PCI-01`.
4. **Advocate Span Verification Proven in Production:** The live judge advocate-span verification mechanism (Task 2a from v70, previously 0 calls) recorded **2 live calls**:
   - `DEV-LCD-PCI-APP` (`CRIT-PCI-01`): Verified and promoted (rescued case to APPROVED).
   - `DEV-NCD-SCS-APP` (`CRIT-SCS-01`): Correctly rejected candidate quote due to semantic mismatch (80% pain relief vs >= 50% trial criterion mismatch).
5. **Zero Safety Regressions:** Zero false approvals (0 FA) and zero false denials (0 FD) across all 84 dev vignettes.

---

## 2. Four-Number Safety Comparison Table (Task 5)

Across all 84 author-written development vignettes evaluated against `carepolicyguard.db`:

| Mode | Committed Map Size | Accuracy (Concordant) | False Approvals (FA) | False Denials (FD) | Safe Deferrals | Synonymy Resolved |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Deterministic Mode** | 12 concepts | 37/84 (44.0%) | 0 | 2 | 45 | 0/19 |
| **Declarative Mode** | 12 concepts | 39/84 (46.4%) | 0 | 0 | 45 | 0/19 |
| **Agentic Mode (v70 Baseline)** | 131 concepts | 46/84 (54.8%) | 0 | 0 | 38 | 7/19 |
| **Agentic Mode (v72 Delivery)** | 131 concepts (provisional path) | **48/84 (57.1%)** | **0** | **0** | **36** | **9/19** |

*Reproduction Check: Deterministic 37/84 and Declarative 39/84 reproduced exactly (passed).*

---

## 3. Same-Map Ablation (Task 5)

Comparison between Declarative Mode with 131 concepts and Agentic Mode with 131 concepts on identical inputs:

| Metric | Declarative Mode (131 Concepts) | Agentic Mode (131 Concepts - v72) | Net Difference |
| :--- | :---: | :---: | :---: |
| **Overall Accuracy** | 48/84 (57.1%) | 48/84 (57.1%) | 0 net (4 per-case diffs) |
| **False Approvals** | 0 | 0 | 0 |
| **False Denials** | 0 | 0 | 0 |
| **Safe Deferrals** | 36 | 36 | 0 |
| **Synonymy Resolved** | 10/19 | 9/19 | -1 net |

### Per-Case Divergences (4 cases):

| Vignette ID | Expected | Declarative (131) | Agentic (131) | Divergence Cause & Mechanism |
| :--- | :---: | :---: | :---: | :--- |
| **`DEV-LCD-PCI-APP`** | `APPROVED` | `DEFERRED_TO_HUMAN` (Discordant) | **`APPROVED`** (Concordant) | **Agentic Gain (+1):** Declarative extractor missed or failed to resolve the 85% LAD stenosis syntax. Agent 3 advocate searched the note, extracted the 145-char span, and the Clinical Judge verified semantic equivalence live. |
| **`DEV-LCD-POWER-WC-APP`** | `APPROVED` | `DEFERRED_TO_HUMAN` (Discordant) | **`APPROVED`** (Concordant) | **Agentic Gain (+1):** Declarative engine could not resolve posture/trunk stability phrasing. In Agentic mode, `CRIT-PWC-02` passed Gate C provisionally and Agent 2 successfully defended against an `ANATOMIC_MISMATCH` objection using verbatim clinical evidence. |
| **`DEV-LCD-SBRT-APP`** | `APPROVED` | `APPROVED` (Concordant) | `DEFERRED_TO_HUMAN` (Discordant) | **Adversarial Safety Deferral:** Agent 3 raised an `ANATOMIC_MISMATCH` counter-reading (lesion measured 6.5 cm, exceeding 5 cm threshold). Agent 2 defense failed to locate counter-evidence and conceded. Invariant preserved: concession is final. |
| **`DEV-OPD-SI-FUSION-APP`** | `APPROVED` | `APPROVED` (Concordant) | `DEFERRED_TO_HUMAN` (Discordant) | **Adversarial Safety Deferral:** Agent 3 raised a `TEMPORAL` counter-reading regarding conservative therapy duration. Agent 2 conceded. Concession guard strictly blocked promotion. |

---

## 4. Status of the 8 Gate C Criteria (Tasks 1 & 2)

Detailed tracking of the 8 criteria blocked by Gate C in v70:

| Criterion Code | Case ID | Gate C Status (v70) | Gate C Status (v72) | Debate / Resolution Outcome | Final Criterion Status |
| :--- | :--- | :---: | :---: | :--- | :---: |
| **`CRIT-KYPHO-02`** | `DEV-LCD-KYPHO-APP` | Rejected (Veto) | **Passed (Provisional)** | Challenged on `TEMPORAL` (2-week conservative therapy). Defense conceded. | `INSUFFICIENT_EVIDENCE` |
| **`CRIT-PAD-01`** | `DEV-LCD-PAD-ATHERO-APP` | Rejected (Veto) | **Passed (Provisional)** | Challenged on `TEMPORAL` (4-month duration). Defense conceded. | `INSUFFICIENT_EVIDENCE` |
| **`CRIT-PAD-02`** | `DEV-LCD-PAD-ATHERO-APP` | Rejected (Veto) | **Passed (Provisional)** | No fatal counter-reading. Defended and promoted. | **`MET`** (Provisional) |
| **`CRIT-PWC-02`** | `DEV-LCD-POWER-WC-APP` | Rejected (Veto) | **Passed (Provisional)** | Challenged on `ANATOMIC_MISMATCH`. Agent 2 defended with grounded quote. Case APPROVED. | **`MET`** (Defended) |
| **`CRIT-CAT-01`** | `DEV-NCD-CATARACT-APP` | Rejected (Veto) | **Passed (Provisional)** | Challenged on `NEGATION` (visual acuity 20/60). Defense conceded. | `INSUFFICIENT_EVIDENCE` |
| **`CRIT-CAT-02`** | `DEV-NCD-CATARACT-APP` | Rejected (Veto) | **Passed (Provisional)** | No fatal counter-reading. Defended and promoted. | **`MET`** (Provisional) |
| **`CRIT-SCS-02`** | `DEV-NCD-SCS-APP` | Rejected (Veto) | **Passed (Provisional)** | Challenged on `TEMPORAL`. Operational time budget exceeded (76s > 60s) during defense attempt. | `INSUFFICIENT_EVIDENCE` |
| **`CRIT-SGD-02`** | `DEV-NCD-SGD-APP` | Rejected (Veto) | **Passed (Provisional)** | Challenged on `NEGATION`. Defense conceded. | `INSUFFICIENT_EVIDENCE` |

### Complementary Target Criteria:
- **`CRIT-KYPHO-01` (`DEV-LCD-KYPHO-APP`):** Quote was disjoint / ungrounded in note text (Gate A failure). Status-MET guard arm **correctly blocked advocacy** (`genuinely_ungrounded=True`).
- **`CRIT-PCI-01` (`DEV-LCD-PCI-APP`):** Advocate found 145-char LAD stenosis quote. Passed Gate A. Passed Gate C provisionally. Clinical Judge verified equivalence live. Promoted to `MET` (Case APPROVED).
- **`CRIT-SBRT-01` & `CRIT-SI-01`:** Conceded during adversarial debate. Concession arm guard **strictly blocked advocacy**.

---

## 5. Guard Cost Audit & Telemetry Breakdown

### Guard Cost Audit Comparison (v70 vs v72):

| Guard Arm | Trigger Condition | v70 Blocks | v72 Blocks | Differential & Impact |
| :--- | :--- | :---: | :---: | :--- |
| **Status-MET Arm** | Initial judgment was `MET` | 9 blocks (6 cases) | **1 block (1 case)** | **-8 blocks.** 8 grounded quotes previously blocked due to missing concept definitions now pass Gate C provisionally. Only `CRIT-KYPHO-01` (genuinely ungrounded) is blocked. |
| **Concession Arm** | Formally conceded in debate | 2 blocks (2 cases) | **6 blocks (6 cases)** | **+4 blocks.** Reflects criteria that now reach counter-reading and are conceded on clinical grounds rather than killed prematurely by Gate C. |
| **Total Guard Blocks** | — | **11 blocks (8 cases)** | **7 blocks (7 cases)** | **-4 net blocks.** False guard rejections eliminated. |

### Execution Bounds & Latency Telemetry:
- **Total Runtime:** 2,391.87 seconds (~39.8 min) across 84 cases in all 3 modes.
- **Mean Case Wall Time:** 28.47s (min 0.05s via Fast Path, max 76.28s).
- **Cases Exceeding 60s:** 29 (down from 32 in v70).
- **Judge Calls:** 114 total across 84 cases (mean 1.36 calls/case, max 5).
- **Fast Path:** Activated on all deterministically verified cases (0 LLM calls, <0.1s latency).

---

## 6. Implementation Anchors & Code Provenance (Tasks 1, 2, 4)

1. **`app/core/agentic_guardrails.py`:**
   - Lines 103–106: Added `judge_verified_met: bool = False`, `conceded: bool = False` to `evaluate_gate_chain`.
   - Lines 195–208: Added Step 3 Gate C provisional equivalence path. When Gate A passes, judge verified MET, and not conceded, unmapped concepts return `passed=True, is_provisional=True, needs_human_attestation=True, gate_c_rejected=True`.
2. **`app/agents/pipeline.py`:**
   - Lines 412–416: Initialized `provisional_equivalences: list[dict[str, Any]] = []`.
   - Lines 822–830: Passed `judge_verified_met=(crit_judgment.status == "MET")` and `conceded=(debated_criteria_outcomes.get(ccode) == "CONCEDED")` to `evaluate_gate_chain`.
   - Lines 858–905: Handled provisional pass: posted VERDICT to message board, queued concept via `ConceptReviewQueue.submit_unmapped_proposal`, recorded in `provisional_equivalences`.
   - Lines 1053–1062: Updated `assessment.clinical_rationale` to record provisional acceptance.
   - Lines 1082–1094: Guard grounding check in status-MET arm. Checks `locate_claimed_span(...) == -1` before blocking; ungrounded quotes blocked with specific reason, grounded quotes permitted to proceed.
   - Lines 1181–1248: Allowed advocate spans to be verified by Clinical Judge live (`judge_equivalence_sync`) and promoted provisionally if unmapped.
   - Lines 1820–1824: Recorded `provisional_equivalences` in `agentic_audit_trail` and `llm_proposal_metadata`.
3. **`app/agents/llm_proposer.py` & `app/agents/criteria_evaluator.py`:**
   - Added `is_provisional` and `needs_human_attestation` to `GateEvaluationResult`.
   - Updated proposal evaluation and criteria evaluator to accept provisional proposals without rejection.
4. **`scripts/run_agentic_v59_three_mode_measurement.py`:**
   - Lines 52–78: Added `get_git_provenance()` dynamically querying `git rev-parse HEAD`, `git rev-parse HEAD~1`, and `git log` at runtime.
   - Line 1256: Updated default output to `agentic_v72_three_mode_run.json`.
   - Lines 1394–1410: Populated metadata dynamically from git provenance.

---

## 7. Verification, Tests & Quality Gates (Tasks 3, 6)

### Pytest Regression Suite:
- **`tests/test_v72_provisional_equivalence.py`:** 5/5 PASSED.
  1. `test_grounded_judge_verified_met_with_unmapped_concept_not_killed_by_gate_c`: PASSED.
  2. `test_guard_does_not_block_grounded_met`: PASSED.
  3. `test_genuinely_ungrounded_met_still_blocked_by_guard`: PASSED.
  4. `test_conceded_criterion_still_blocked_by_guard`: PASSED.
  5. `test_committed_concept_map_unchanged_at_12_concepts`: PASSED.
- **`tests/test_v70_routing_and_efficiency.py`:** 4/4 PASSED.
- **Combined Test Run:** 9/9 PASSED in 12.86s.

### Ruff Linting & Frontend Checks:
- **Standard Scope (`app/core app/schemas --ignore E501`):** 0 errors (Clean).
- **`app/core/llm_judge.py`:** 0 errors (Clean).
- **`tests/test_v72_provisional_equivalence.py`:** 0 errors (Clean).
- **Frontend Syntax Gate (`node --check app/static/js/app.js`):** Clean.

---

## 8. Unproven Items & Limitations

In accordance with strict reporting standards:
1. **Clinical Validation:** The 84 development vignettes are author-written synthetic calibration vignettes, not clinical validation or real-world medical records.
2. **Human Review Queue Integration:** Concepts marked with `needs_human_attestation: True` are submitted to `ConceptReviewQueue` in SQLite; human clinician attestation UI and ingestion workflows remain separate from the automated verification pipeline.
3. **Wall Time Latency on Ollama:** Local 3B model execution on Ollama averages ~14.3s per LLM call. Cases with multiple debate and defense rounds can reach the 60s per-case budget boundary (e.g. `DEV-NCD-SCS-APP`), triggering safe deferral.
