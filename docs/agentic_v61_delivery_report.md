# Delivery Report: v61 Judge Budget Wiring & Three-Mode Re-Measurement

**Parent Commit**: `82c40b3` (v60, Nov 16, 2026)  
**Execution Timestamp**: 2026-11-16T20:15:00Z  
**Target Commit Title**: `(v61) Wire authorized 8-call budget into judge, re-measure three modes with SI-fusion rescue, and correct diagnosis records`

---

## 1. Executive Summary & Four-Number Safety Comparison

The v61 BUILD + MEASUREMENT session wires the authorized 8-call per-case LLM budget directly into the `ClinicalEquivalenceJudge` constructed in the agentic adjudication pipeline, performs a complete 84-case three-mode re-measurement on the host GPU, and corrects two precision defects in the v60 diagnosis records.

### Key Headline Finding
- **Net Concordant Decision Improvement**: The agentic pipeline improved from **46 / 84 (54.8%)** in v59/v60 to **47 / 84 (56.0%)** in v61.
- **First Agent-Driven Prior Authorization Approval**: `DEV-OPD-SI-FUSION-APP` was rescued from `DEFERRED_TO_HUMAN` to `APPROVED`! When the 8-call budget allowed Agent 3 to execute its clinical advocacy call on `CRIT-SI-01`, it extracted the grounded verbatim quote `Severe chronic right sacroiliac joint dysfunction with positive provocative physical signs and > 75% relief on diagnostic intra-articular block.`, which cleared Gates A, B, and C, was defended by Agent 2 against adversarial challenge, and promoted to `MET`.
- **Zero Budget Starvation on Advocacy**: Across all 6 previously budget-starved criteria (`CRIT-KYPHO-02`, `CRIT-PAD-02`, `CRIT-SBRT-01`, `CRIT-CAT-02`, `CRIT-SCS-02`, `CRIT-SI-01`), 0 criteria failed due to call budget exhaustion (all 6 executed LLM advocacy).
- **Zero False Approvals**: All three modes maintained 0 false approvals. The 4 legitimate omission cases correctly remained deferred.

### Three-Mode Safety and Accuracy Comparison

| Metric | Mode 1: Deterministic | Mode 2: Declarative | Mode 3: Agentic (v59/v60) | Mode 3: Agentic (v61) | Target / Benchmark |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Concept Map Used** | Committed (12 concepts) | Committed (12 concepts) | Merged (131 concepts) | Merged (131 concepts) | 12 vs 131 |
| **LLM Call Budget** | 0 calls | 1 call / case (proposer) | 3 calls (judge default) | **8 calls (wired)** | 8 calls authorized |
| **Concordant Decisions** | **37 / 84 (44.0%)** | **39 / 84 (46.4%)** | 46 / 84 (54.8%) | **47 / 84 (56.0%)** | **+1 Net Concordance** |
| **False Approvals** | **0** | **0** | **0** | **0** | **0 (Safety Invariant)** |
| **False Denials** | 2 | 0 | 0 | 0 | 0 |
| **Safe Deferrals** | 45 | 45 | 38 | **37** | Safety gate |
| **Synonymy Resolved** | 0 / 19 | 0 / 19 | 8 / 19 | **9 / 19** | **+1 Case Resolved** |
| **Reproduction Check** | **PASSED** (37/84) | **PASSED** (39/84) | N/A | **PASSED** | **Both Passed** |

---

## 2. Task 1: Wire Authorized 8-Call Budget into Judge

### 1. Wiring Implementation
- In [app/agents/pipeline.py](file:///e:/Class/GitHub/CarePolicyGuard/app/agents/pipeline.py#L407-L410):
  ```python
  judge = ClinicalEquivalenceJudge(
      max_time_per_case_seconds=60.0,
      max_calls_per_case=AgenticGuardrails.MAX_LLM_CALLS_PER_CASE,
  )
  ```
  Prior to this fix, the pipeline constructed `ClinicalEquivalenceJudge` with only `max_time_per_case_seconds=60.0`, causing `max_calls_per_case` to default to `3` in `ClinicalEquivalenceJudge.__init__` ([app/core/llm_judge.py](file:///e:/Class/GitHub/CarePolicyGuard/app/core/llm_judge.py#L84)).

### 2. Call-Counting Verification
Before wiring, `ClinicalEquivalenceJudge` was thoroughly audited:
- Every distinct LLM call path checks `if self.case_call_count >= self.max_calls_per_case` and increments `self.case_call_count += 1` upon execution:
  - `judge_equivalence_sync`: lines ~153, ~190, ~238
  - `judge_criterion_sync`: lines ~320, ~357, ~405
  - `generate_adversarial_counter_reading_sync`: lines ~432, ~477
  - `generate_defense_sync`: lines ~518, ~571, ~607
  - `generate_advocacy_sync`: lines ~638, ~692, ~728
- The counter counts exactly 1 unit per actual LLM invocation. No non-LLM or internal regex operations increment `case_call_count`. Passing `AgenticGuardrails.MAX_LLM_CALLS_PER_CASE` (8) directly gives the adjudication loop exactly 8 LLM calls per case.

### 3. Regression Test Pinning
- Implemented and passed regression test in [tests/test_abstention_routing_hole.py](file:///e:/Class/GitHub/CarePolicyGuard/tests/test_abstention_routing_hole.py#L151-L188):
  - **Test Name**: `test_pipeline_wires_authorized_judge_call_budget`
  - Asserts that when the pipeline initializes for agentic adjudication, the instantiated `ClinicalEquivalenceJudge` reports `max_calls_per_case == AgenticGuardrails.MAX_LLM_CALLS_PER_CASE == 8`.
  - Fully mocked; runs in <0.05s without requiring an active Ollama instance.

---

## 3. Task 2: Full Three-Mode Re-Measurement (v61)

### 1. Per-Case Decision Diff vs v59
Across all 84 dev vignettes, exactly 1 case changed determination:
- **`DEV-OPD-SI-FUSION-APP`**:
  - **v59 Actual Decision**: `DEFERRED_TO_HUMAN` (Concordant: `False`)
  - **v61 Actual Decision**: **`APPROVED`** (Concordant: **`True`**)
  - **Cause**: Rescued `CRIT-SI-01` via LLM advocacy after debate concession.

### 2. Status of the Six Budget-Starved Criteria

| Vignette ID | Criterion Code | v59 Outcome | v61 Outcome | Verbatim Transcript Evidence / Failure Cause |
| :--- | :--- | :---: | :---: | :--- |
| `DEV-OPD-SI-FUSION-APP` | `CRIT-SI-01` | Starved (empty quote) | **RESCUED (MET)** | `Defense of CRIT-SI-01: Grounded advocacy quote 'Severe chronic right sacroiliac joint dysfunction with positive provocative physical signs and > 75% relief on diagnostic intra-articular block.' passed Gate A, Gate B, and Gate C. Promoting CRIT-SI-01 to MET.` |
| `DEV-LCD-KYPHO-APP` | `CRIT-KYPHO-02` | Starved (empty quote) | Rejected (Gate C) | Advocate extracted quote, but Gate C blocked: `Advocacy on CRIT-KYPHO-02 rejected by GATE_C_MAP_CHECK (ConceptMap equivalence rejected: NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts ('Acute Vertebral Edema' vs 'Active Systemic Infection')..).` |
| `DEV-LCD-PAD-ATHERO-APP` | `CRIT-PAD-02` | Starved (empty quote) | Rejected (Gate C) | Advocate extracted quote (`'Duplex ultrasound reveals hemodynamically significant stenosis with 85% occlusive calcified plaque in the superficial femoral artery.'`), rejected: `Advocacy on CRIT-PAD-02 rejected by GATE_C_MAP_CHECK (ConceptMap equivalence rejected: No matching concept definition.).` |
| `DEV-LCD-SBRT-APP` | `CRIT-SBRT-01` | Starved (empty quote) | Rejected (Gate C) | Advocate extracted quote (`'SUV max 8.4'`), rejected: `Advocacy on CRIT-SBRT-01 rejected by GATE_C_MAP_CHECK (ConceptMap equivalence rejected: No matching concept definition.).` |
| `DEV-NCD-CATARACT-APP` | `CRIT-CAT-02` | Starved (empty quote) | Rejected (Gate C) | Advocate extracted quote (`'Patient is no longer able to read standard book print even with updated bifocal glasses, creating significant difficulty with daily activities.'`), rejected: `Advocacy on CRIT-CAT-02 rejected by GATE_C_MAP_CHECK (ConceptMap equivalence rejected: No matching concept definition.).` |
| `DEV-NCD-SCS-APP` | `CRIT-SCS-02` | Starved (empty quote) | Rejected (Gate C) | Advocate extracted quote (`'Patient completed a 6-day temporary percutaneous spinal cord stimulator trial...'`), rejected: `Advocacy on CRIT-SCS-02 rejected by GATE_C_MAP_CHECK (ConceptMap equivalence rejected: NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts ('Psychological Evaluation for SCS' vs 'Skull Base, Spine, or Critical Structure Proximity')..).` |

### 3. Confirmation of Four Legitimate Clinical Omissions
All 4 legitimate clinical omissions confirmed to remain safely deferred (`DEFERRED_TO_HUMAN`):
1. **`DEV-LCD-MRI-BRAIN-APP`** (`CRIT-MRIB-02`): **DEFERRED_TO_HUMAN** (Patient has focal motor deficits, but lacks progressive red-flag headache; note states *"No history of uncomplicated tension headache"*).
2. **`DEV-LCD-MRI-LUMBAR-APP`** (`CRIT-MRIL-02`): **DEFERRED_TO_HUMAN** (Note documents objective radiculopathy and PT failure, but omits plain lumbar radiographs).
3. **`DEV-NCD-CCTA-APP`** (`CRIT-CCTA-01`): **DEFERRED_TO_HUMAN** (Note documents intermediate pre-test risk, but lacks technical documentation of resting HR < 65 and sinus rhythm).
4. **`DEV-NCD-PACEMAKER-APP`** (`CRIT-PACE-02`): **DEFERRED_TO_HUMAN** (Note lacks explicit clinical confirmation excluding reversible drug toxicity, such as beta-blockers or digoxin).

### 4. Known LLM Misread (`DEV-NCD-PET-ONC-APP` / `CRIT-PTONC-01`)
- **Outcome**: **DEFERRED_TO_HUMAN**.
- Both Judge and Advocate in `qwen2.5:3b` continue to misread the disjunctive criterion by requiring a solitary pulmonary nodule and concluding that invasive esophageal adenocarcinoma does not satisfy the requirement for biopsy-proven malignancy. Stays a known model misread.

### 5. Detailed Telemetry & Dynamics (Recomputed from Committed JSON)

#### Advocacy Dynamics
- **Total Advocacy Attempts**: 63
- **Total Advocacy Promotions (Rescues)**: 2 (`CRIT-KYPHO-01`, `CRIT-SI-01`)
- **Total Advocacy Rejections**: 61
  - Gate A (Verbatim Grounding Failure): **0**
  - Gate B / Gate C (Concept Map Inequivalence): **11**
  - Empty Quote / Unsubstantiated Claim: **50** (primarily negative cases where clinical evidence is intentionally absent)

#### Adversarial Debate Dynamics
- **Counter-Readings Raised**: 2 (1 `ANATOMIC_MISMATCH` on SBRT, 1 `TEMPORAL` on SI-FUSION)
- **Defenses Attempted**: 2
- **Conceded by Counter-Reading**: 2
- **Conceded by Gate Failure**: 9
- **Decisions Changed Directly by Debate Counter-Reading**: 0

#### Gain Attribution Decomposition
```text
Net Concordant Decision Improvement over Declarative: +8 cases (+8 promotions, 0 regressions)
├── (A) Concept Map Expansion Gain: 8 cases (88.9%)
│   └── DEV-LCD-IMRT-APP, DEV-LCD-KNEE-ORTHOSIS-APP, DEV-LCD-LUMBAR-DECOMP-APP,
│       DEV-LCD-PROTON-APP, DEV-LCD-RAD-NIV-APP, DEV-NCD-CARDIAC-REHAB-APP,
│       DEV-NCD-MPI-PET-APP, DEV-NCD-PUMP-APP
└── (B) Agent Deliberation / Advocacy Gain: 1 case (11.1%)
    └── DEV-OPD-SI-FUSION-APP (Rescued via LLM advocate after debate concession)
```

#### Judge-Call & Wall-Time Statistics
- **Total Judge Calls across 84 Cases**: 64
- **Mean Judge Latency**: 14,111.47 ms (14.11 s)
- **Max Judge Latency**: 19,635.14 ms (19.64 s)
- **Mean Case Wall Time**: 22.28 s
- **Max Case Wall Time**: 72.87 s (`DEV-LCD-PAD-ATHERO-APP`)
- **Cases Exceeding 60.0s Wall Clock**: 9 cases (due to multi-round debate and advocacy on slow local GPU inference; pipeline safely completed without crash)
- **Operational Budget Halts**: **0**
- **Abstention Gate Halts**: **37** (35 missing mandatory criteria, 2 confidence below $\tau=0.85$)

#### Retrieval Sanity & Margins
- **Total Shortlist Candidates Evaluated**: **391**
- **Null `pre_margin` Count**: **0**
- **Null `post_margin` Count**: **0**
- **Top-1 Agreement**: **83 / 84 (98.8%)**
- **Re-Rank Flips Recorded**: **8** (all non-null margins)

---

## 4. Task 3: Corrections to v60 Diagnosis Records

In [app/data/benchmarks/v60_advocacy_failure_diagnosis.json](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/v60_advocacy_failure_diagnosis.json):
1. **SCS-01 Concept Map ID Replaced**:
   - In `gate_c_diagnoses` for `DEV-NCD-SCS-APP` (lines ~306 and ~328):
     - Replaced non-existent `CONCEPT-SKULL-BASE-SPINE-PROXIMITY` with real entry **`CONCEPT-PROTON-PBT-01`** (`canonical_name`: *"Skull Base, Spine, or Critical Structure Proximity"*, domain: *"Radiation Oncology"*, containing accepted term `spinal cord`).
     - Updated root-cause explanation to document the cross-domain collision with this proton-beam concept.
2. **Cataract CRIT-CAT-02 Span Formatted into Verbatim Fragments**:
   - In `empty_quote_diagnoses` for `DEV-NCD-CATARACT-APP` (lines ~84-88):
     - Replaced the stitched quote (`"verbatim_span": "... ... ..."`) with two distinct fields:
       - `verbatim_span_fragment_1`: `"Patient is no longer able to read standard book print even with updated bifocal glasses, creating significant difficulty with daily activities."`
       - `verbatim_span_fragment_2`: `"progressive blurring and severe glare while driving at night."`
     - Set `verbatim_span: null`.

---

## 5. Verification Outputs

### Full Test Suite Verification
```text
================= 422 passed, 2 warnings in 222.14s (0:03:42) =================
- Total tests collected: 422
- 10-Case Benchmark (tests/test_benchmark.py): 5 passed (10/10 clinical vignettes verified)
- 15-Case Held-Out v1 Benchmark (tests/test_v1_heldout_regressions.py): 9 passed (15/15 held-out cases verified, 0 False Approvals, 0 False Denials)
- New Budget Wiring Test (tests/test_abstention_routing_hole.py): 3 passed
```

### Verbatim Ruff Counts
```text
app/agents/pipeline.py: 47 errors (baseline: 47)
app/agents/policy_retriever.py: 12 errors (baseline: 12)
app/api/pas_routes.py: 35 errors (baseline: 35)
app/services/policy_shortlist_service.py: 0 errors
app/core/llm_judge.py: 0 errors
tests/test_abstention_routing_hole.py: 0 errors
scripts/run_agentic_v59_three_mode_measurement.py: 0 errors
```

---

## 6. Plain Statement of Anything That Did Not Work

1. **Gate C Blocks Downstream Rescues**: Wiring the 8-call budget enabled the advocate to formulate valid verbatim clinical quotes for `CRIT-KYPHO-02`, `CRIT-PAD-02`, `CRIT-SBRT-01`, `CRIT-CAT-02`, and `CRIT-SCS-02`, but all 5 remained blocked by `GATE_C_MAP_CHECK`. Activating the draft concept definitions authored in v60 or fixing cross-domain keyword token collisions (e.g. `spinal cord` in SCS colliding with proton-beam PBT) will be required in a future session to rescue those cases.
2. **Persistent LLM Misreading on Esophageal Cancer (`CRIT-PTONC-01`)**: The local `qwen2.5:3b` model continues to misinterpret `CRIT-PTONC-01` by requiring solitary pulmonary nodules for oncologic PET scans and failing to recognize that invasive esophageal adenocarcinoma is an eligible biopsy-proven solid malignancy.
