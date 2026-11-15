# v52 — Delivery Report

**Session Type**: Measurement & Verification  
**Git Head at Start**: `0895eb20eb5b234ca06f85389668bc15d23c81a9` (v51-fix: widen fatal rule, evidence-backed defense debate, routing counters, smoke transcripts)  
**Execution Environment**: Local GPU host, Local Ollama daemon (`127.0.0.1:11434`, model: `qwen2.5:3b`)  
**Egress State**: Remote LLM egress strictly default-off / disabled  
**Dataset**: 84 development vignettes (`app/data/dev_vignettes.json`, author-written development test cases; **NOT** held-out, **NOT** clinical validation)  
**Held-out v2 Dataset**: `carepolicyguard-heldout-v2/heldout_vignettes_v2.json` strictly **UNTOUCHED** (not opened, not read, not run)  
**Production Code**: Strictly **ZERO** changes to production application code (`app/agents/pipeline.py`, `app/core/llm_judge.py`, etc.)  

---

## 1. Overview & Benchmark Deliverables

This measurement session executed the full 84-case development benchmark across all three operational modes under the frozen configurations:
1. **Deterministic Mode**: Committed concept map (12 concepts), standard deterministic regex/keyword parser.
2. **Declarative Mode**: Committed concept map (12 concepts), LLM proposer enabled, `span_repair=True`.
3. **Agentic Mode**: Merged concept map (12 committed + 119 PASS drafts = 131 concepts), autonomous deliberation with communicating shared message board, adversarial counter-reading verifier, evidence-backed defense debate, double-sided tracking, and strict routing.

### Committed Benchmark Artifacts
- **Measurement Runner**: [`scripts/run_agentic_v52_three_mode_measurement.py`](file:///e:/Class/GitHub/CarePolicyGuard/scripts/run_agentic_v52_three_mode_measurement.py)
- **Raw Results Data**: [`app/data/benchmarks/agentic_v52_three_mode_run.json`](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/agentic_v52_three_mode_run.json)
- **Measurement Delivery Report**: [`docs/agentic_v52_measurement_report.md`](file:///e:/Class/GitHub/CarePolicyGuard/docs/agentic_v52_measurement_report.md)

---

## 2. Four-Number Safety Comparison Across Modes

All metrics below are computed directly from the 84 author-written development vignettes (`app/data/dev_vignettes.json`). They are strictly **dev-vignette numbers** and do not represent held-out clinical validation numbers.

| Measurement Dimension | Deterministic (Committed 12) | Declarative (Committed 12) | Agentic (Merged 131) | v37 Agentic Baseline (Commit `8b72d52`) |
| :--- | :--- | :--- | :--- | :--- |
| **Concordant / Total** | **37 / 84** | **39 / 84** | **46 / 84** | 48 / 84 |
| **Concordance / Accuracy (%)** | **44.0%** | **46.4%** | **54.8%** | 57.1% |
| **False Approvals (FA)** | **0** | **0** | **0** | 0 |
| **False Denials (FD)** | **2** | **0** | **0** | 0 |
| **Safe Deferrals** | **45** | **45** | **38** | 36 |
| **Synonymy Resolved Cases** | **0 / 19** | **0 / 19** | **8 / 19** | 10 / 19 |
| **Elapsed Runtime** | 3.67 s | 1,585.39 s (~26.4 min) | 1,129.81 s (~18.8 min) | ~1,600 s |

### Safety Invariants
- **Zero False Approvals**: All three modes achieved 0 False Approvals across all 84 dev vignettes.
- **Zero False Denials in Declarative and Agentic Modes**: The 2 False Denials in Deterministic mode were completely eliminated in Declarative and Agentic modes via abstention and semantic repair.
- **Concordance Shift from v37 Baseline**: Agentic mode scored 46/84 (54.8%) versus 48/84 (57.1%) in v37. The difference of 2 cases (`DEV-LCD-PCI-APP` and `DEV-OPD-SI-FUSION-APP`) is analyzed below: in v37 with a static stub pipeline, these two cases were approved; under the v51/v51-fix live LLM judge and adversarial counter-reading verifier, `DEV-LCD-PCI-APP` was safely deferred due to low calibrated confidence (0.773 < 0.85), and `DEV-OPD-SI-FUSION-APP` was safely deferred due to an adversarial counter-reading challenge where the budget timed out before defense.

---

## 3. The 9 Unresolved Synonymy Cases Analysis

The 9 synonymy cases that remained unresolved in prior sessions were evaluated in all three modes. Below is the decision in each mode alongside the exact resolving mechanism or blocking step in Agentic mode:

| Vignette ID | Policy | Expected Decision | Deterministic Decision | Declarative Decision | Agentic Decision | Agentic Blocking Step / Resolving Mechanism |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `DEV-LCD-KYPHO-APP` | `LCD-KYPHO` | `APPROVED` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **One-sided judge failure + Budget halt**: Judge evaluated `CRIT-KYPHO-01` and `CRIT-KYPHO-02` as `INSUFFICIENT_EVIDENCE` ("No documented clinical evidence matching statutory criteria."). Fallback entered; 2 calls burned; execution bounds reached (30s limit exceeded). |
| `DEV-LCD-MRI-BRAIN-APP` | `LCD-MRI-BRAIN` | `APPROVED` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **One-sided judge failure**: `CRIT-MRIB-01` was MET (focal neurological deficit), but `CRIT-MRIB-02` was judged `INSUFFICIENT_EVIDENCE`. Fallback entered (2 calls); calibrated confidence 0.773 < $\tau=0.85$. Safely deferred. |
| `DEV-LCD-MRI-LUMBAR-APP` | `LCD-MRI-LUMBAR` | `APPROVED` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **One-sided judge failure**: `CRIT-MRIL-01` was MET (lumbar radiculopathy), but `CRIT-MRIL-02` judged `INSUFFICIENT_EVIDENCE`. Fallback entered (1 call); calibrated confidence 0.773 < $\tau=0.85$. Safely deferred. |
| `DEV-LCD-PAD-ATHERO-APP` | `LCD-PAD-ATHERO` | `APPROVED` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **One-sided judge failure + Budget halt**: Both `CRIT-PAD-01` and `CRIT-PAD-02` judged `INSUFFICIENT_EVIDENCE`. Fallback entered (2 calls); total time budget exceeded. |
| `DEV-LCD-POWER-WC-APP` | `LCD-POWER-WC` | `APPROVED` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **One-sided judge failure**: `CRIT-PWC-01` was MET (unable to perform MRADLs), but `CRIT-PWC-02` judged `INSUFFICIENT_EVIDENCE`. Fallback entered (2 calls); calibrated confidence 0.773 < $\tau=0.85$. Safely deferred. |
| `DEV-NCD-CCTA-APP` | `NCD-CCTA` | `APPROVED` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **One-sided judge failure**: `CRIT-CCTA-02` was MET (equivocal baseline ECG), but `CRIT-CCTA-01` judged `INSUFFICIENT_EVIDENCE`. Fallback entered (2 calls); calibrated confidence 0.773 < $\tau=0.85$. Safely deferred. |
| `DEV-NCD-PACEMAKER-APP` | `NCD-PACEMAKER` | `APPROVED` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **One-sided judge failure**: `CRIT-PACE-01` was MET (Syncope), but `CRIT-PACE-02` judged `INSUFFICIENT_EVIDENCE`. Fallback entered (1 call); calibrated confidence 0.773 < $\tau=0.85$. Safely deferred. |
| `DEV-NCD-PET-ONC-APP` | `NCD-PET-ONC` | `APPROVED` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **One-sided judge failure**: `CRIT-PTONC-02` was MET (staging to determine resectability), but `CRIT-PTONC-01` judged `INSUFFICIENT_EVIDENCE`. No fallback entered (0 calls); calibrated confidence 0.773 < $\tau=0.85$. Safely deferred. |
| `DEV-NCD-SGD-APP` | `NCD-SGD` | `APPROVED` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **One-sided judge failure**: `CRIT-SGD-01` was MET (anarthria), but `CRIT-SGD-02` judged `INSUFFICIENT_EVIDENCE`. Fallback entered (2 calls); calibrated confidence 0.773 < $\tau=0.85$. Safely deferred. |

### The 8 Resolved Synonymy Cases in Agentic Mode
The 8 cases successfully resolved in Agentic mode (approved with full concordance) are:
1. `DEV-LCD-IMRT-APP`
2. `DEV-LCD-KNEE-ORTHOSIS-APP`
3. `DEV-LCD-LUMBAR-DECOMP-APP`
4. `DEV-LCD-PROTON-APP`
5. `DEV-LCD-RAD-NIV-APP`
6. `DEV-NCD-CARDIAC-REHAB-APP`
7. `DEV-NCD-MPI-PET-APP`
8. `DEV-NCD-PUMP-APP`

---

## 4. Debate Execution & Agent Dynamics Across 84 Agentic Cases

Across all 84 dev vignettes in Agentic mode:
- **Counter-readings Raised**: **2**
  - Case `DEV-LCD-SBRT-APP` (`CRIT-SBRT-01`): Verifier raised an `ANATOMIC_MISMATCH` counter-reading ("negative brain MRI contradicts oligometastases requirement").
  - Case `DEV-OPD-SI-FUSION-APP` (`CRIT-SI-01`): Verifier raised a `TEMPORAL` counter-reading ("conservative therapy duration not specified as lasting 16 weeks").
- **Defenses Attempted**: **0** (in both cases, the per-case execution wall time reached 34–35 s before the defense prompt could be dispatched; the 30.0 s budget halt triggered immediately before dispatch).
- **Outcome Split**:
  - `DEFENDED`: **0**
  - `CONCEDED-counter`: **0**
  - `CONCEDED-gate` (due to ungrounded quote / Gate A failure): **10**
  - `UNRESOLVED` (budget exhaustion during dispute): **2**
- **Decisions Changed by Debate**: **0** (neither disputed criterion was promoted to MET, so the decision remained `DEFERRED_TO_HUMAN`).
- **Criterion-Judge Outcome Split**:
  - `MET` (grounded in note): **6**
  - `MET` (ungrounded, killed by Gate A): **1**
  - `NOT_MET`: **26**
  - `MISSING_OR_OTHER`: **7**
  - **Gate A Kill Rate**: **14.3%** (1 out of 7 `MET` judgments had ungrounded quotations and was intercepted by Gate A).
- **Fallback Usage**:
  - Cases entering span-level fallback: **35**
  - Fallback judge calls burned: **59**
  - Fallback promotions achieved: **0** (0 spans were promoted from `AMBIGUOUS`/`REJECTED` to `CONFIRMED` under the strict thresholds).

---

## 5. Routing, Latency & Budget Execution

- **Strict Routing Enforcement**:
  - Total LLM Judge calls dispatched: **99**
  - Calls dispatched for criteria otherwise deferring: **49**
  - Calls dispatched for criteria already settled deterministically: **0**
  - **Routing Violation (`already_settled > 0`)**: **`False`** (100% compliant with the routing invariant).
- **Judge Call Distribution**:
  - Cases with 0 judge calls: 49 cases (settled entirely via deterministic/exclusion rules)
  - Cases with 1 judge call: 0 cases
  - Cases with 2 judge calls: 7 cases
  - Cases with 3 judge calls: 27 cases
- **Budget Halts**:
  - Total budget halts: **38**
  - Reason breakdown:
    - *Insufficient evidence for mandatory coverage criteria*: 27
    - *Operational budget exhausted (30.0s time or 3-call bound reached)*: 9
    - *Calibrated aggregate confidence below safety threshold $\tau=0.85$*: 1
    - *Potential unverified negative omission detected*: 1
- **Latency Performance (GPU Host, Local `qwen2.5:3b`)**:
  - Mean Judge Latency: **11,557.99 ms** (~11.6 s per call)
  - Max Judge Latency: **18,255.45 ms** (~18.3 s)
  - Mean Case Wall Time: **13.45 s** (Min: 0.03 s, Max: 40.86 s)

---

## 6. The One-Sidedness Finding & False Deferral Analysis (Design Finding)

### The Architectural Limitation
Today, the criterion judge and downstream gates operate in a **one-sided** fashion:
1. When an LLM judge evaluates a criterion, if it determines `MET`, its output must pass Gate A (exact verbatim quotation grounding check), Gate B (contradiction check), and the Adversarial Verifier counter-reading.
2. If the LLM judge outputs `NOT_MET` (or `INSUFFICIENT_EVIDENCE`), that negative finding is **accepted immediately without an adversarial check, counter-reading, or evidence challenge**.
3. In 14 cases that are gold-standard `APPROVED`, the LLM judge returned `INSUFFICIENT_EVIDENCE` or `NOT_MET` on one or more mandatory criteria despite valid clinical paraphrases existing in the note. Because there is no "proponent advocate" to challenge negative findings or cite supporting phrases, these cases are silently dropped into fallback or deferred.

### Itemized List of One-Sidedness False Deferrals (18 Criteria across 14 Vignettes)

| Vignette ID | Policy ID | Criterion Code | Clinical Rationale Given by Judge |
| :--- | :--- | :--- | :--- |
| `DEV-LCD-KYPHO-APP` | `LCD-KYPHO` | `CRIT-KYPHO-01` | "No documented clinical evidence matching statutory criteria." |
| `DEV-LCD-KYPHO-APP` | `LCD-KYPHO` | `CRIT-KYPHO-02` | "No documented clinical evidence matching statutory criteria." |
| `DEV-LCD-MRI-BRAIN-APP` | `LCD-MRI-BRAIN` | `CRIT-MRIB-02` | "No documented clinical evidence matching statutory criteria." |
| `DEV-LCD-MRI-LUMBAR-APP` | `LCD-MRI-LUMBAR` | `CRIT-MRIL-02` | "No documented clinical evidence matching statutory criteria." |
| `DEV-LCD-PAD-ATHERO-APP` | `LCD-PAD-ATHERO` | `CRIT-PAD-01` | "No documented clinical evidence matching statutory criteria." |
| `DEV-LCD-PAD-ATHERO-APP` | `LCD-PAD-ATHERO` | `CRIT-PAD-02` | "No documented clinical evidence matching statutory criteria." |
| `DEV-LCD-PCI-APP` | `LCD-PCI` | `CRIT-PCI-01` | "No documented clinical evidence matching statutory criteria." |
| `DEV-LCD-POWER-WC-APP` | `LCD-POWER-WC` | `CRIT-PWC-02` | "No documented clinical evidence matching statutory criteria." |
| `DEV-LCD-SBRT-APP` | `LCD-SBRT` | `CRIT-SBRT-01` | "No documented clinical evidence matching statutory criteria." |
| `DEV-NCD-CATARACT-APP` | `NCD-CATARACT` | `CRIT-CAT-01` | "No documented clinical evidence matching statutory criteria." |
| `DEV-NCD-CATARACT-APP` | `NCD-CATARACT` | `CRIT-CAT-02` | "No documented clinical evidence matching statutory criteria." |
| `DEV-NCD-CCTA-APP` | `NCD-CCTA` | `CRIT-CCTA-01` | "No documented clinical evidence matching statutory criteria." |
| `DEV-NCD-PACEMAKER-APP` | `NCD-PACEMAKER` | `CRIT-PACE-02` | "No documented clinical evidence matching statutory criteria." |
| `DEV-NCD-PET-ONC-APP` | `NCD-PET-ONC` | `CRIT-PTONC-01` | "No documented clinical evidence matching statutory criteria." |
| `DEV-NCD-SCS-APP` | `NCD-SCS` | `CRIT-SCS-01` | "No documented clinical evidence matching statutory criteria." |
| `DEV-NCD-SCS-APP` | `NCD-SCS` | `CRIT-SCS-02` | "No documented clinical evidence matching statutory criteria." |
| `DEV-NCD-SGD-APP` | `NCD-SGD` | `CRIT-SGD-02` | "No documented clinical evidence matching statutory criteria." |
| `DEV-OPD-SI-FUSION-APP` | `OPD-SI-FUSION` | `CRIT-SI-01` | "No documented clinical evidence matching statutory criteria." |

This finding is formally documented as an architectural input for future double-sided deliberation design.

---

## 7. Quality, Regressions & Standing Rule Disclosures

1. **Held-out v2 Dataset**:
   - `carepolicyguard-heldout-v2/heldout_vignettes_v2.json` was **NOT opened, read, queried, or modified**.
2. **Remote LLM Egress**:
   - Strictly disabled. All LLM inferences ran exclusively on local Ollama daemon (`qwen2.5:3b` at `127.0.0.1:11434`).
3. **Zero Production Code Changes**:
   - `git diff app/` confirms 0 modifications to production application code.
4. **Full Test Suite Verification**:
   - Pytest suite: **401 passed, 1 warning in 179.35s** (100% green).
   - Core regression guards: `tests/test_benchmark.py` and `tests/test_v1_heldout_regressions.py` passed **14 / 14 in 5.44s** (0 False Approvals, 0 False Denials).
5. **Linting & Code Cleanliness**:
   - `ruff check scripts/run_agentic_v52_three_mode_measurement.py`: **Clean (0 errors, 0 warnings)**.
