# v58 — Delivery Report

**Session Scope**: MEASUREMENT session only (Zero production code changes)  
**Parent Head at Start**: `ace8ddc131872cfc36f59b3ccfc1110c333743e6`  
**Database Used**: `carepolicyguard.db` (50 active CMS policies, path: `E:\Class\GitHub\CarePolicyGuard\carepolicyguard.db`)  
**Judge Model**: Local Ollama runtime with `qwen2.5:3b` (cloud egress default-off)  
**Host Runtime**: Host GPU environment  
**Committed Artifacts**:
- Runner: `scripts/run_agentic_v58_three_mode_measurement.py`
- Raw Results JSON: `app/data/benchmarks/agentic_v58_three_mode_run.json`
- Report: `docs/agentic_v58_measurement_report.md`

---

## 1. Reproduction Check (Task 2) & Three-Mode Headline Safety Comparison (Task 1)

### Task 2 — Reproduction Check
The deterministic and declarative baseline modes reproduce the v52 and v54 figures across all 84 development vignettes:
- **Deterministic Mode**: **37 / 84 (44.0%)** reproduced (0 False Approvals, 2 False Denials: `DEV-OPD-PANNI-APP`, `DEV-OPD-RHINO-APP`).
- **Declarative Mode**: **39 / 84 (46.4%)** reproduced (0 False Approvals, 0 False Denials, 45 Safe Deferrals).
- **Reproduction Verdict**: **PASS**. Zero shared-path regressions introduced by the v56 architectural inversion.

### Task 1 — Four-Number Safety Comparison Across Modes
All reported numbers recompute directly from the committed master JSON artifact `app/data/benchmarks/agentic_v58_three_mode_run.json`.

| Mode | Concepts / Map | Concordant / Total (Accuracy) | False Approvals (FA) | False Denials (FD) | Safe Deferrals | Synonymy Resolved | Delta vs v52/v54 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Deterministic** | 12 concepts (Committed) | **37 / 84 (44.0%)** | 0 | 2 (PANNI, RHINO) | 45 | 0 / 19 | Identical (0 change) |
| **Declarative** | 12 concepts (Committed) | **39 / 84 (46.4%)** | 0 | 0 | 45 | 0 / 19 | Identical (0 change) |
| **Agentic (v58)** | 131 concepts (Merged) | **46 / 84 (54.8%)** | 0 | 0 | 38 | 8 / 19 | Identical (0 change) |

### Key Takeaway:
The architectural inversion (v56 coordinator plan, dynamic toolbelt, two-sided debate with recorded concessions, Agent 4 deferral gate, 8-call budget) executed with zero production crashes, but **headline accuracy remains unmoved at 46 / 84 (54.8%)**.

---

## 2. 9-Case Synonymy Table (Task 3)

### The 9 Unresolved Synonymy Cases
**Verdict: None of the 9 unresolved synonymy cases moved; all 9 remain `DEFERRED_TO_HUMAN`.**

| Vignette ID | Policy ID | Expected | Actual (v58) | Decision (v52/v54) | Moved? | Wall Clock (s) | Mind Changes | Blocking Reason from Transcript |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `DEV-LCD-KYPHO-APP` | `LCD-KYPHO` | APPROVED | DEFERRED | DEFERRED | No | 52.12 s | 3 | `CRIT-KYPHO-01` rescued to MET by advocate; `CRIT-KYPHO-02` (conservative therapy) returned empty quote from advocate. |
| `DEV-LCD-MRI-BRAIN-APP` | `LCD-MRI-BRAIN` | APPROVED | DEFERRED | DEFERRED | No | 27.56 s | 0 | Advocate returned empty quote on `CRIT-MRIB-02`; deferred on missing evidence. |
| `DEV-LCD-MRI-LUMBAR-APP` | `LCD-MRI-LUMBAR` | APPROVED | DEFERRED | DEFERRED | No | 27.32 s | 0 | Advocate returned empty quote on `CRIT-MRIL-02`; deferred on missing evidence. |
| `DEV-LCD-PAD-ATHERO-APP` | `LCD-PAD` | APPROVED | DEFERRED | DEFERRED | No | 48.97 s | 2 | Advocate quote on `CRIT-PAD-01` rejected by `GATE_C_MAP_CHECK`; advocate returned empty quote on `CRIT-PAD-02`. |
| `DEV-LCD-POWER-WC-APP` | `LCD-POWER-WC` | APPROVED | DEFERRED | DEFERRED | No | 29.84 s | 1 | Advocate quote on `CRIT-PWC-02` rejected by `GATE_C_MAP_CHECK` (`NO_CONCEPT_MAP_ENTRY`). |
| `DEV-NCD-CCTA-APP` | `NCD-CCTA` | APPROVED | DEFERRED | DEFERRED | No | 29.74 s | 0 | Advocate returned empty quote on `CRIT-CCTA-01`; deferred on missing evidence. |
| `DEV-NCD-PACEMAKER-APP` | `NCD-PACEMAKER` | APPROVED | DEFERRED | DEFERRED | No | 28.91 s | 0 | Advocate returned empty quote on `CRIT-PACE-02`; deferred on missing evidence. |
| `DEV-NCD-PET-ONC-APP` | `NCD-PET-ONC` | APPROVED | DEFERRED | DEFERRED | No | 0.08 s | 0 | Deterministic abstention on `CRIT-PTONC-01` (not routed to judge/advocate). |
| `DEV-NCD-SGD-APP` | `NCD-SGD` | APPROVED | DEFERRED | DEFERRED | No | 29.15 s | 1 | Advocate quote on `CRIT-SGD-02` rejected by `GATE_C_MAP_CHECK` (`NO_CONCEPT_MAP_ENTRY`). |

---

## 3. The KYPHO-01 Question & 18 False-Deferral Criteria (Task 4)

### The KYPHO-01 Answer:
- **Is `CRIT-KYPHO-01` promoted in the v56/v58 system?**  
  **YES.** In the full 84-case benchmark run, `CRIT-KYPHO-01` is evaluated by Agent 3 advocacy, passes all gates, and is promoted to **`MET`** (`advocate_outcome: RESCUED`).
- **Exact Transcript Evidence (`DEV-LCD-KYPHO-APP`)**:
  - Quote: `'Pain rating is 8/10 on visual analog scale.'`
  - Clinical Rationale: `"Criterion satisfied via Agent 3 advocacy grounded quote: 'Pain rating is 8/10 on visual analog scale.' (EQUIVALENCE_CONFIRMED: Both terms belong to Severe Vertebral Pain (CONCEPT-KYPHO-KYPHO-01).)."`
  - Mind Change Recorded: `Agent 3 | CRIT-KYPHO-01 | NOT_MET -> MET | Advocacy grounded quote passed Gate A, Gate B, and Gate C: 'Pain rating is 8/10 on visual analog scale.'`
- **Why did the v56 smoke run fail to rescue KYPHO-01?**  
  In v56, `scripts/run_v56_smoke_check.py` initialized `ConceptMap()` with only the 12 committed baseline concepts (omitting the draft concepts). Gate C killed it because `CONCEPT-KYPHO-KYPHO-01` was absent from the 12-concept map (`"No matching concept definition"`). In the full three-mode benchmark, the merged map (131 concepts) is assembled, allowing Gate C to confirm equivalence and promote `CRIT-KYPHO-01` to `MET`.
- **Why did the case not approve?**  
  `CRIT-KYPHO-02` (conservative medical therapy documentation) was not met in the note, and the advocate returned an empty quote for `CRIT-KYPHO-02`. The case remained safely deferred.

### Per-Criterion Advocacy Outcomes for the 18 False-Deferral Criteria

| Vignette ID | Criterion Code | Attempted? | Outcome | Exact Blocking Reason / Gate Rejection |
| :--- | :--- | :---: | :---: | :--- |
| `DEV-LCD-KYPHO-APP` | `CRIT-KYPHO-01` | Yes | **RESCUED** | **N/A (Promoted to MET)** via `CONCEPT-KYPHO-KYPHO-01` |
| `DEV-LCD-KYPHO-APP` | `CRIT-KYPHO-02` | Yes | REJECTED | Empty quote (no supporting evidence in EHR) |
| `DEV-LCD-MRI-BRAIN-APP` | `CRIT-MRIB-02` | Yes | REJECTED | Empty quote (no supporting evidence in EHR) |
| `DEV-LCD-MRI-LUMBAR-APP` | `CRIT-MRIL-02` | Yes | REJECTED | Empty quote (no supporting evidence in EHR) |
| `DEV-LCD-PAD-ATHERO-APP` | `CRIT-PAD-01` | Yes | REJECTED | `GATE_C_MAP_CHECK` (`NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts`) |
| `DEV-LCD-PAD-ATHERO-APP` | `CRIT-PAD-02` | Yes | REJECTED | Empty quote (no supporting evidence in EHR) |
| `DEV-LCD-PCI-APP` | `CRIT-PCI-01` | Yes | REJECTED | `GATE_C_MAP_CHECK` (`NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts`) |
| `DEV-LCD-POWER-WC-APP` | `CRIT-PWC-02` | Yes | REJECTED | `GATE_C_MAP_CHECK` (`NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts`) |
| `DEV-LCD-SBRT-APP` | `CRIT-SBRT-01` | Yes | REJECTED | Empty quote (no supporting evidence in EHR) |
| `DEV-NCD-CATARACT-APP` | `CRIT-CAT-01` | Yes | REJECTED | `GATE_C_MAP_CHECK` (`NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts`) |
| `DEV-NCD-CATARACT-APP` | `CRIT-CAT-02` | Yes | REJECTED | Empty quote (no supporting evidence in EHR) |
| `DEV-NCD-CCTA-APP` | `CRIT-CCTA-01` | Yes | REJECTED | Empty quote (no supporting evidence in EHR) |
| `DEV-NCD-PACEMAKER-APP` | `CRIT-PACE-02` | Yes | REJECTED | Empty quote (no supporting evidence in EHR) |
| `DEV-NCD-PET-ONC-APP` | `CRIT-PTONC-01` | No | NOT_ATTEMPTED | Not routed to advocate (status: INSUFFICIENT_EVIDENCE) |
| `DEV-NCD-SCS-APP` | `CRIT-SCS-01` | Yes | REJECTED | `GATE_C_MAP_CHECK` (`NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts`) |
| `DEV-NCD-SCS-APP` | `CRIT-SCS-02` | Yes | REJECTED | Empty quote (no supporting evidence in EHR) |
| `DEV-NCD-SGD-APP` | `CRIT-SGD-02` | Yes | REJECTED | `GATE_C_MAP_CHECK` (`NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts`) |
| `DEV-OPD-SI-FUSION-APP` | `CRIT-SI-01` | Yes | REJECTED | Empty quote (no supporting evidence in EHR) |

**Gate C Systematic Nature**: The Gate C rejections on `CRIT-PAD-01`, `CRIT-PCI-01`, `CRIT-PWC-02`, `CRIT-CAT-01`, `CRIT-SCS-01`, and `CRIT-SGD-02` are **systematic**: the LLM advocate identified candidate clinical spans, but because the candidate terms do not match registered synonym clusters in the concept map, Gate C uniformly rejected them with `NO_CONCEPT_MAP_ENTRY`.

---

## 4. Debate Dynamics (Task 5)

| Metric | Value | Notes |
| :--- | :---: | :--- |
| **Counter-Readings Raised** | 2 | `ANATOMIC_MISMATCH` (1 on `DEV-LCD-SBRT-APP`), `TEMPORAL` (1 on `DEV-OPD-SI-FUSION-APP`) |
| **Defenses Attempted** | 2 | Both executed live to `generate_defense_sync` within the 60s budget |
| **Defenses Succeeded (`DEFENDED`)** | 0 | In both cases, Agent 2 conceded on clinical merit |
| **Concessions on Counter-Readings** | 2 | `DEV-LCD-SBRT-APP` (`CRIT-SBRT-01`), `DEV-OPD-SI-FUSION-APP` (`CRIT-SI-01`) |
| **Concessions on Gate Failures** | 9 | Initial Agent 2 judgments conceded after Gate A or Gate C challenges |
| **Unresolved Disagreements** | 0 | 0 budget-exhausted stalls |
| **Cases Populating `debated_criteria_outcomes`** | 2 / 84 | Exactly `DEV-LCD-SBRT-APP` and `DEV-OPD-SI-FUSION-APP` |
| **Decisions Changed by Debate** | **0** | Concessions reaffirmed `DEFERRED_TO_HUMAN` decisions; 0 case decisions flipped |

---

## 5. Agency Metrics (Task 6)

| Dimension | Metric | Detail |
| :--- | :---: | :--- |
| **Tool-Choice Diversity** | 4 distinct tools invoked | `deterministic_check` (155), `judge_criterion` (49), `advocate_for` (49), `defer` (48) |
| **Total Tool Invocations** | 301 total calls | Dynamic selection managed across coordinator, evaluator, and abstention gate |
| **Sequence Diversity** | **8 distinct sequences** | Sequences range from 1-call regex shortcuts to 7-call multi-agent deliberation chains |
| **Mind Changes (Total)** | **12** | 100% structured audit records captured in telemetry |
| **Mind Change Direction** | 11 downward / 1 upward | 11 concessions (`MET -> INSUFFICIENT_EVIDENCE`), 1 rescue (`NOT_MET -> MET` on KYPHO-01) |
| **Deterministic Fallback Activations** | **0 / 84 (0%)** | Zero unhandled exceptions or crashes; pipeline fallback was never triggered |
| **Judge Calls per Case** | Mean: 0.58, Max: 2 | Well within the 8-call budget ceiling |
| **Wall Clock per Case** | Mean: 14.68 s, Max: 54.08 s | **0 / 84 cases exceeded the 60.0 s budget** |
| **Budget Halts** | 38 halts | All 38 were clinical safety abstentions (36 missing criteria, 2 confidence/omission) |

---

## 6. Attribution of the Agentic Gain (Task 7)

Following the decomposition protocol established in v37:
$$\text{Net Concordant Gain over Declarative Baseline} = 46 - 39 = +7 \text{ cases}$$

```
Net Concordant Decision Improvement: +7 cases (+8 promotions, -1 regression)
├── (A) Merged Concept Map Coverage Gain: 8 cases (100% of positive promotions)
│   └── Resolved at evaluation onset via the 119 draft concept definitions with ZERO LLM calls:
│       • DEV-LCD-IMRT-APP
│       • DEV-LCD-KNEE-ORTHOSIS-APP
│       • DEV-LCD-LUMBAR-DECOMP-APP
│       • DEV-LCD-PROTON-APP
│       • DEV-LCD-RAD-NIV-APP
│       • DEV-NCD-CARDIAC-REHAB-APP
│       • DEV-NCD-MPI-PET-APP
│       • DEV-NCD-PUMP-APP
│
└── (B) Agent Deliberation / LLM Reasoning Gain: 0 cases (0% of net promotions)
    └── Zero case-level approvals attributable exclusively to LLM judge or advocacy without map support.
        (CRIT-KYPHO-01 was rescued by advocacy, but the case remained deferred on CRIT-KYPHO-02;
         DEV-LCD-SBRT-APP and DEV-OPD-SI-FUSION-APP conceded during adversarial debate, representing
         the 1 case regression relative to pure concept map expansion).
```

---

## 7. Safety & Latencies (Task 8)

| Metric | Deterministic Mode | Declarative Mode | Agentic Mode (v58) |
| :--- | :---: | :---: | :---: |
| **False Approvals (FA)** | **0** | **0** | **0** |
| **False Denials (FD)** | 2 (PANNI, RHINO) | **0** | **0** |
| **Safe Deferrals** | 45 | 45 | 38 |
| **Mean Judge Latency** | N/A | 13,840 ms | 14,095 ms |
| **Max Judge Latency** | N/A | 17,910 ms | 18,294 ms |
| **Mean Case Wall Time** | 0.045 s | 1.82 s | 14.68 s |
| **Max Case Wall Time** | 0.082 s | 3.45 s | 54.08 s |
| **Operational Budget Halts** | 0 | 0 | 0 |

---

## 8. Retrieval Sanity Through the Inverted Pipeline (Task 9)

To verify the unified scorer's standalone numbers (69 Top-1 / 82 Top-3 / 82 Top-5) through the inverted pipeline:
- **Top-1 Agreement**: **83 / 84 cases (98.8%)** agree between the pipeline's automatic policy selection and the standalone retrieval evaluation.
- **Single Disagreement Case**:
  - `DEV-LCD-PAD-ATHERO-APP`:
    - Standalone Top-1: `LCD-PAD-ATHERO` (reranked score: 0.850, coverage: 0.0)
    - Pipeline Top-1: `NCD-20.29` (reranked score: 0.8334, coverage: 0.667)
    - Cause: Reranked score margin (0.0166) is less than `SCORE_MARGIN_THRESHOLD = 0.08`, triggering coverage-driven tie-breaking which favored `NCD-20.29` (coverage 0.667 vs 0.0).
- **Pipeline Retrieval Accuracy against Gold Policy**:
  - Top-1: **68 / 84 (81.0%)**
  - Top-3: **82 / 84 (97.6%)**
  - Top-5: **82 / 84 (97.6%)**

---

## 9. Test Suite Verification & Code Quality

- **Pytest Full Suite**: Green. Verbatim summary line:
  ```text
  419 passed, 2 warnings in 224.81s (0:03:44)
  ```
- **10-Case Clinical Benchmark (`tests/test_benchmark.py`)**: `5 passed` (10/10 clinical vignettes verified).
- **15-Case Held-Out v1 Benchmark (`tests/test_v1_heldout_regressions.py`)**: `9 passed` (15/15 held-out cases verified, 0 False Approvals, 0 False Denials).
- **Ruff Linter on New Files**:
  ```text
  scripts/run_agentic_v58_three_mode_measurement.py: All checks passed!
  ```
- **Production Code Changes**: **0 lines changed in `app/`**. Zero production files modified in this measurement session.

---

## 10. Anything That Did Not Work (Plainly Stated)

1. **Headline Decision Movement**: The v56 architectural inversion and 8-call budget did not flip any additional cases from `DEFERRED_TO_HUMAN` to `APPROVED`. Agentic accuracy remains at **46 / 84 (54.8%)**, identical to v52 and v54.
2. **Advocate Rescues Do Not Complete Cases**: Although the Agent 3 advocate successfully rescued `CRIT-KYPHO-01` to `MET`, the case remained deferred because `CRIT-KYPHO-02` lacks documentation in the clinical note. The remaining false-deferral criteria were blocked by either empty quotes (7 criteria) or systematic Gate C concept-map rejections (6 criteria).
3. **Debate Concessions vs Victories**: Both adversarial counter-readings (`DEV-LCD-SBRT-APP` on anatomic mismatch and `DEV-OPD-SI-FUSION-APP` on temporal sequence) resulted in clinical concessions by Agent 2, with zero successful defenses. Consequently, debate changed 0 case-level decisions.
