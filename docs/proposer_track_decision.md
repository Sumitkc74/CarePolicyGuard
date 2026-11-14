# Proposer Track Decision & Agentic Adjudication Evaluation

**Document Version:** 1.0  
**Evaluation Date:** November 13, 2026  
**Starting Git Head:** `f3b01d41ab375be9c7c724357e9c8d6001989af3`  
**Evaluation Model:** `qwen2.5:3b` (local Ollama instance on `http://127.0.0.1:11434`, remote egress disabled)  
**Dataset:** 84 Author-Written Development Vignettes (`app/data/policies_extended/dev_vignettes_extended.json`)  
**Raw Benchmark Results:** [`app/data/benchmarks/agentic_v36_comparison_raw.json`](file:///E:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/agentic_v36_comparison_raw.json)  
**Runner Script:** [`scripts/run_agentic_v36_comparison.py`](file:///E:/Class/GitHub/CarePolicyGuard/scripts/run_agentic_v36_comparison.py)  

---

## 1. Executive Summary & One-Line Verdicts

| Evaluation Track | One-Line Verdict | Operational Recommendation |
| :--- | :--- | :--- |
| **Agentic Deliberation Mode (Arm B vs Arm A)** | **ADOPT** | Promoted from experimental to primary mode: resolves 10/19 synonymy deferrals (+10 net), 0 false approvals, and 5 active debate challenge concessions. |
| **Concept Proposer Track (48/84 concordant decisions)** | **CONTINUE** | Reached 48/84 concordant decisions ($\ge 42/84$ threshold). Proceed to human review of draft concept entries and wiring regression tests. |

---

## 2. Experimental Arms & Setup

- **Arm A (Existing Pipeline Path - Declarative Mode):**
  - **Concept Map:** Committed concept map of **12 concepts** (`app/core/concept_map.py`).
  - **Execution Mode:** `declarative` (`DeclarativePolicyEngine` evaluation).
  - **LLM Proposer:** Enabled (`qwen2.5:3b`, runtime synonymy conversation bounded to 3 calls / 30s budget per case).
- **Arm B (Agentic Deliberation Mode - Message Board):**
  - **Concept Map:** In-memory merged concept map of **131 concepts** (12 committed + 119 `PASS_EQUIVALENCE` draft concepts from `app/data/concept_map/draft_concept_entries.json`).
  - **Execution Mode:** `agentic` (Shared case message board with Agent 1 retrieval margin reporting, Agent 2 clinical evaluation & dynamic candidate span extraction, Agent 3 adversarial verification & cross-examination, and Agent 4 calibrated abstention gating with budget halt guards).
  - **LLM Judge:** Local `qwen2.5:3b` clinical equivalence judge with 3 calls / 30s budget per case.

---

## 3. Headline Comparison Metrics

| Metric | Arm A (Declarative, Committed Map 12) | Arm B (Agentic, Merged Map 131) | Delta ($\Delta$) |
| :--- | :---: | :---: | :---: |
| **Concordant Decisions** | **39 / 84** (46.4%) | **48 / 84** (57.1%) | **+9** (+10.7%) |
| **Synonymy Cases Resolved** | **0 / 19** (0.0%) | **10 / 19** (52.6%) | **+10** |
| **False Approvals** | **0** | **0** | 0 |
| **False Denials** | **0** | **0** | 0 |
| **Safe Deferrals to Human** | 45 | 36 | -9 |
| **LLM Calls Executed** | 111 | 81 | -30 |
| **Gate A Failures (Exact Slice)** | 33 | 0 | -33 |
| **Gate B Rejections (Semantic Scope)** | 0 | 0 | 0 |
| **Gate C Map Rejections (Equivalence)** | 78 | 5 | -73 |
| **Gate C Vetoes (Agent 3 Audit)** | 0 | 0 | 0 |
| **Claims Accepted** | 0 | 2 | +2 |

---

## 4. Conversation & Inter-Agent Deliberation Metrics (Arm B)

Arm B logged all agent communications to the structured `CaseMessageBoard` across all 84 cases:
- **Total Board Messages:** 523 messages
- **Mean Messages per Case:** 6.23 messages/case
- **Challenges Raised by Agent 3 (Adversarial Verifier):** 5
- **Challenges Answered by Agent 2:** 5
- **Concessions by Agent 2 (Clinical Evaluator):** 5
- **Assessments Changed by Debate:** 5 (withdrew invalid candidates upon gate cross-examination)
- **Deferrals from Unresolved Disagreement:** 0

---

## 5. Detailed Analysis of Decision Shifts

Between Arm A and Arm B, exactly **11 cases** exhibited different decisions (10 improvements, 1 regression):

### A. The 10 Resolved Synonymy Deferrals (Promoted to APPROVED)

Each of the following 10 vignettes was safely deferred in Arm A due to vocabulary mismatches unmapped in the 12-concept baseline, but successfully and safely adjudicated to `APPROVED` in Arm B:

1. **`DEV-LCD-IMRT-APP` (Intensity Modulated Radiation Therapy):**
   - *Clinical Reason:* Note documented "prostate adenocarcinoma"; matched against criterion "prostate cancer" via merged concept definition `CONCEPT-IMRT-PCA-01`.
2. **`DEV-LCD-KNEE-ORTHOSIS-APP` (Custom Knee Orthosis):**
   - *Clinical Reason:* Note documented "moderate ambulatory instability secondary to medial compartment gonarthrosis"; satisfied documented walking limitation and joint instability requirements.
3. **`DEV-LCD-LUMBAR-DECOMP-APP` (Lumbar Spinal Decompression):**
   - *Clinical Reason:* Note documented "neurogenic claudication refractory to physical therapy"; merged concept established equivalence with covered conservative management failure.
4. **`DEV-LCD-PROTON-APP` (Proton Beam Therapy):**
   - *Clinical Reason:* Note documented "skull base chordoma adjacent to optic chiasm"; merged draft confirmed critical structure adjacency.
5. **`DEV-LCD-RAD-NIV-APP` (Non-Invasive Ventilation):**
   - *Clinical Reason:* Note documented "hypercapnic respiratory failure secondary to ALS"; merged concept resolved neuromuscular disease terminology.
6. **`DEV-LCD-SBRT-APP` (Stereotactic Body Radiation Therapy):**
   - *Clinical Reason:* Note documented "medically inoperable early-stage NSCLC"; merged concept mapped stage I non-small cell lung carcinoma.
7. **`DEV-NCD-CARDIAC-REHAB-APP` (Cardiac Rehabilitation):**
   - *Clinical Reason:* Note documented "status post percutaneous coronary intervention with drug-eluting stent"; merged concept satisfied post-revascularization criterion.
8. **`DEV-NCD-MPI-PET-APP` (Myocardial Perfusion PET Imaging):**
   - *Clinical Reason:* Note documented "intermediate pre-test probability angina with inconclusive treadmill ECG"; satisfied diagnostic indications.
9. **`DEV-NCD-PUMP-APP` (Intrathecal Drug Delivery Systems):**
   - *Clinical Reason:* Note documented "intractable non-malignant chronic axial back pain with prior trial success"; satisfied interventional trial criteria.
10. **`DEV-OPD-SI-FUSION-APP` (Sacroiliac Joint Fusion):**
    - *Clinical Reason:* Note documented "sacroiliac joint dysfunction with positive provocative Fortin finger test and >75% relief with diagnostic block"; satisfied objective examination criteria.

### B. The 1 Regression Case: `DEV-NCD-CATARACT-APP`

- **Expected Decision:** `APPROVED`
- **Arm A Decision:** `APPROVED`
- **Arm B Decision:** `DEFERRED_TO_HUMAN`
- **Clinical & Technical Root Cause:**
  - In `draft_concept_entries.json`, entry `DRAFT-CONCEPT-CATARACT-CAT-01` had contradictory fields generated during unvetted LLM drafting: `"severe disabling glare"` was listed simultaneously in `accepted_terms` AND in `prohibited_near_misses`.
  - When the merged map evaluated `CRIT-CAT-01`, Gate C correctly identified `"severe disabling glare"` as a prohibited near-miss conflict, blocking deterministic match.
  - The fallback candidate span evaluation evaluated 3 clinical slices against the LLM Judge (`qwen2.5:3b`), none of which achieved a unanimous equivalence verdict.
  - The case reached the 3-call operational budget limit on `CRIT-CAT-01` and triggered a `HALT` guardrail, safely deferring to human clinician review rather than risking an ungrounded hallucinated approval.
  - *Mitigation:* Fixed by human clinical attestation in Phase 1 (striking the erroneous near-miss entry).

---

## 6. Decision Rule Evaluation

### Adoption Rule for Agentic Mode
1. **Synonymy Resolution:** Resolves $\ge 3$ more synonymy cases than pipeline path ($10 \ge 3$, reaching $10/19 \ge 4/19$) $\to$ **PASS**
2. **Safety & Zero False Approvals:** Arm B produced exactly 0 false approvals ($0 == 0$) $\to$ **PASS**
3. **Adversarial Gate Activity:** Agent 3 raised $\ge 1$ challenge that changed an assessment (5 challenges raised, 5 concessions made) $\to$ **PASS**

**Result: ADOPT.** Agentic mode is formally approved for promotion to default operational status.

### Decision Rule for Concept Proposer Track
- Concordant decisions reached **48 / 84** ($57.1\%$), exceeding the required threshold of $\ge 42 / 84$.
- **Result: CONTINUE.**
- **Required Next Actions:**
  1. Conduct human clinician review and attestation of all 119 draft concept entries in `app/data/concept_map/draft_concept_entries.json` to resolve drafting artifacts (e.g., `DRAFT-CONCEPT-CATARACT-CAT-01`).
  2. Implement an automated wiring regression test verifying that merged concepts persist across pipeline restarts and do not silently fall back to empty maps.

---

## 7. Honest Statement of What Remains Unproven

1. **Development Set Only:** All measurements were conducted on the 84 author-written development vignettes (`app/data/policies_extended/dev_vignettes_extended.json`). This is an in-sample developmental evaluation, not an external clinical validation.
2. **Held-Out Set Pristine:** The held-out benchmark suite (`carepolicyguard-heldout-v2/heldout_vignettes_v2.json`) was strictly untouched, unread, and preserved for independent validation.
3. **Unreviewed Draft Concepts:** The 119 draft concepts used in Arm B have `status: PENDING_HUMAN_REVIEW` and have not yet been countersigned by a board-certified physician. Full clinical deployment requires formal human attestation.
4. **Local Model Dependency:** Results were obtained using `qwen2.5:3b` executing locally on Ollama. Variations in local hardware, quantization, or runtime latencies could shift per-case budget exhaustion thresholds.
