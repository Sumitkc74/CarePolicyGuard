# Delivery Report: v59 Architecture Build & Routing Hole Fix

**Parent Commit**: `c04665a` (v58, Nov 16, 2026)  
**Execution Timestamp**: 2026-11-16T08:56:58Z  
**Target Commit Title**: `(v59) Close routing hole on deterministic abstentions, record retrieval re-rank evidence, and disambiguate budget halts`

---

## 1. Executive Summary & Four-Number Safety Comparison

The v59 build successfully closes the routing hole that allowed cases with deterministic abstentions (`INSUFFICIENT_EVIDENCE` or verifier omission flags) to bypass the LLM Judge and Advocate before reaching an Agent 4 human review deferral. It records comprehensive retrieval re-rank evidence into candidates and audit trails, clears the v56 ruff regressions across modified production files back to parent baselines, and disambiguates operational halts from clinical abstention halts.

### Three-Mode Safety and Accuracy Comparison

| Metric | Mode 1: Deterministic | Mode 2: Declarative | Mode 3: Agentic | Target / Benchmark |
| :--- | :---: | :---: | :---: | :---: |
| **Concept Map Used** | Committed (12 concepts) | Committed (12 concepts) | Merged (131 concepts) | 12 vs 131 |
| **LLM Calls** | 0 calls | 1 call / case (proposer) | Up to 8 calls / case (judge/advocate) | Local `qwen2.5:3b` |
| **Concordant Decisions** | **37 / 84 (44.0%)** | **39 / 84 (46.4%)** | **46 / 84 (54.8%)** | 37 & 39 reproduce exactly |
| **False Approvals** | **0** | **0** | **0** | **0 (Safety Invariant)** |
| **False Denials** | 2 | 0 | 0 | 0 |
| **Safe Deferrals** | 45 | 45 | 38 | Safety gate |
| **Synonymy Resolved** | 0 / 19 | 0 / 19 | 8 / 19 | Expansion gain |
| **Reproduction Check** | **PASSED** (37/84) | **PASSED** (39/84) | N/A | **Both Passed** |

---

## 2. Task-by-Task Implementation Details

### Task 1: Close the Routing Hole on Deterministic Abstentions
- **Implementation**:
  - In [app/agents/pipeline.py](file:///e:/Class/GitHub/CarePolicyGuard/app/agents/pipeline.py#L463-L540): Identified `is_abstention_bound`. When no statutory exclusion is `MET` deterministically and any mandatory criterion has `INSUFFICIENT_EVIDENCE` or verifier negative omission flags (`has_omiss`), the coordinator now explicitly adds those criteria to `needs_judge_codes` even when `CandidateSpanExtractor` extracted 0 keyword spans from the note.
  - In [app/agents/pipeline.py](file:///e:/Class/GitHub/CarePolicyGuard/app/agents/pipeline.py#L612-L695): For exclusions with omission flags, allowed criteria to reach the LLM judge instead of immediately skipping to `NOT_MET`. For inclusions, eliminated `if not candidate_spans: continue` bypass when `ccode in needs_judge_codes`.
  - In [app/agents/pipeline.py](file:///e:/Class/GitHub/CarePolicyGuard/app/agents/pipeline.py#L980-L1005): Evaluated LLM judgments on exclusions (if `MET` -> short-circuit denial; if `NOT_MET` -> confirmed ruled out and cleared omission flag).
- **Synthetic Regression Test**:
  - Implemented [tests/test_abstention_routing_hole.py](file:///e:/Class/GitHub/CarePolicyGuard/tests/test_abstention_routing_hole.py):
    1. `test_abstention_routing_hole_calls_judge_and_advocate`: Synthetic fixture asserting `judge_calls > 0`, advocacy attempted, and `CRIT-PTONC-01` routed to `needs_judge`.
    2. `test_omission_bound_criterion_routes_to_judge`: Synthetic exclusion case asserting omission-bound criteria route to judge and short-circuit denial upon `MET`.
  - Pytest result: `2 passed in 1.52s`.
- **Target Cases Empirical Verification**:
  | Vignette ID | Policy | Expected | Actual | Judge Calls (v58) | Judge Calls (v59) | Routing Hole Closed |
  | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
  | `DEV-NCD-PET-ONC-APP` | `NCD-PET-ONC` | APPROVED | DEFERRED_TO_HUMAN | 0 | **1** | **YES** |
  | `DEV-LCD-RAD-NIV-NEG` | `LCD-RAD-NIV` | DENIED | DEFERRED_TO_HUMAN | 0 | **1** | **YES** |
  | `DEV-NCD-CCTA-NEG` | `NCD-CCTA` | DENIED | DEFERRED_TO_HUMAN | 0 | **2** | **YES** |

### Task 2: Record Retrieval Re-Rank Evidence
- **Implementation**:
  - In [app/services/policy_shortlist_service.py](file:///e:/Class/GitHub/CarePolicyGuard/app/services/policy_shortlist_service.py): Computed and persisted `pre_rerank_top1_policy_id`, `pre_rerank_top2_policy_id`, `pre_margin`, `post_rerank_top1_policy_id`, `post_rerank_top2_policy_id`, `post_margin`, and `rerank_flipped_top1`.
  - Retained `unified_score`, `coverage_ratio`, and `reranked_score` across all candidates.
  - In [app/agents/pipeline.py](file:///e:/Class/GitHub/CarePolicyGuard/app/agents/pipeline.py): Passed retrieval re-rank evidence into `agentic_audit_trail["agent_1_retrieval"]`.
- **Dev Benchmark Flip Analysis (across 84 vignettes)**:
  - Total flips caused by coverage re-rank: **9**
  - Flipped to gold policy: **2** (`DEV-LCD-HIP-ARTHRO-APP`, `DEV-LCD-SHOULDER-ARTHRO-APP`)
  - Flipped to non-gold policy: **7** (`DEV-LCD-FACET-NEG`, `DEV-LCD-LUMBAR-FUSION-NEG`, `DEV-LCD-MRI-LUMBAR-APP`, `DEV-LCD-PAD-ATHERO-APP`, `DEV-LCD-PAD-ATHERO-NEG`, `DEV-LCD-ROTATOR-CUFF-NEG`, `DEV-NCD-SCS-APP`)

### Task 3: Cleared v56 Ruff Regression
- Error counts restored to parent `5f2dc5e` levels without removing production logic:
  - `app/agents/pipeline.py`: **47** (reduced from 54; target $\le 47$)
  - `app/agents/policy_retriever.py`: **12** (reduced from 14; target $\le 12$)
  - `app/api/pas_routes.py`: **35** (reduced from 36; target $\le 35$)
  - New test file `tests/test_abstention_routing_hole.py`: **0** errors.
  - New benchmark runner `scripts/run_agentic_v59_three_mode_measurement.py`: **0** errors.

### Task 4: Disambiguate Budget-Halt Naming
- In [app/agents/pipeline.py](file:///e:/Class/GitHub/CarePolicyGuard/app/agents/pipeline.py) and [scripts/run_agentic_v59_three_mode_measurement.py](file:///e:/Class/GitHub/CarePolicyGuard/scripts/run_agentic_v59_three_mode_measurement.py):
  - Split halt metrics into:
    - **Operational budget halts**: 0 across all 84 cases (no wall-clock > 60s or call limit 8 exhaustion).
    - **Abstention gate halts**: 38 across 84 cases (36 insufficient evidence for mandatory criteria, 2 calibrated confidence below $\tau=0.85$).

### Task 5: Smoke Check & Full Three-Mode Benchmark
- Ran 12-case smoke check in [scripts/run_v56_smoke_check.py](file:///e:/Class/GitHub/CarePolicyGuard/scripts/run_v56_smoke_check.py): confirmed KYPHO-01 rescue reproduced and PET-ONC executed through judge.
- Ran full 84-case benchmark in [scripts/run_agentic_v59_three_mode_measurement.py](file:///e:/Class/GitHub/CarePolicyGuard/scripts/run_agentic_v59_three_mode_measurement.py):
  - Deterministic 37/84 reproduced exactly.
  - Declarative 39/84 reproduced exactly.
  - Agentic mode achieved 46/84 with 0 false approvals.

---

## 3. Verification Outputs

### Verbatim Pytest Output
```text
================= 421 passed, 2 warnings in 336.46s (0:05:36) =================
```

### Verbatim Ruff Counts
```text
app/agents/pipeline.py: 47 errors (baseline: 47)
app/agents/policy_retriever.py: 12 errors (baseline: 12)
app/api/pas_routes.py: 35 errors (baseline: 35)
tests/test_abstention_routing_hole.py: 0 errors
scripts/run_agentic_v59_three_mode_measurement.py: 0 errors
```

---

## 4. Statement of Anything That Did Not Work

1. **Routing Fix Did Not Convert Target Deferrals into Approvals**: While routing the 3 target cases (`DEV-NCD-PET-ONC-APP`, `DEV-LCD-RAD-NIV-NEG`, and `DEV-NCD-CCTA-NEG`) to the LLM Judge successfully triggered LLM deliberation (`judge_calls = 1-2`), the local `qwen2.5:3b` model evaluated the criteria as `INSUFFICIENT_EVIDENCE` or failed verbatim grounding Gate A, resulting in safe deferrals to human review (`DEFERRED_TO_HUMAN`). This is clinically correct according to the governing rule (genuine ambiguity or absence of documented clinical details defers safely rather than guessing), preserving 0 false approvals.
2. **Coverage Re-Ranking Accuracy**: Coverage re-ranking flipped 9 cases; while 2 cases were rescued to gold (`LCD-HIP-ARTHRO` and `LCD-SHOULDER-ARTHRO`), 7 cases flipped to non-gold adjacent procedures due to overlapping clinical keywords. The coverage formula and 0.08 margin threshold were kept strictly frozen per prompt instructions.
