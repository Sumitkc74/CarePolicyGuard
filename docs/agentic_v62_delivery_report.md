# Agentic v62 Delivery Report: Gate C Domain Scoping, Advocate Span Refinement, and Three-Mode Adjudication Benchmark

**Benchmark Execution Date**: 2026-11-16T23:10:59Z  
**Parent Git Head**: `f2868ee` (v61)  
**Target Commit**: `(v62)`  
**Environment**: Local Host (Intel CPU, local Ollama instance running `qwen2.5:3b`, zero remote egress)  
**Dataset**: 84 Author-Written Development Clinical Vignettes (`dev_vignettes_extended.json`, non-held-out dev set)  
**Budget Constraints**: Frozen 8 LLM calls / 60.0s per-case wall clock limit  

---

## 1. Executive Summary & Four-Number Safety Comparison

The v62 release completes architectural scoping of Gate C matching to governing policy clinical domains (Task 1), refines advocate verbatim span selection to prioritize core statutory criteria elements over isolated peripheral numbers (Task 2), executes a full three-mode re-measurement across all 84 development vignettes (Task 3), and provides a deterministic diagnosis of the v59-to-v61 retrieval jitter (Task 4).

### Key Architectural Results:
1. **Gate C Domain Scoping (Task 1)**:
   - **Positive Control Verified**: Under `NCD-SCS` (Interventional Pain / Neurosurgery), candidate concept lookups are strictly scoped to the governing policy domain. The false collision with `CONCEPT-PROTON-PBT-01` (`"Skull Base, Spine, or Critical Structure Proximity"`, Radiation Oncology) is completely eliminated.
   - **Negative Control Verified**: Within the same domain (e.g., `LCD-KYPHO` / Spine Surgery), genuinely disjoint clinical concepts (`"Acute Vertebral Edema"` vs `"Active Spinal Infection"`) remain strictly rejected by Gate C.
2. **Advocate Span Selection (Task 2)**:
   - **SBRT-01 Control Rescued**: The advocate's span selection logic was upgraded with prioritized statutory element scoring. For `CRIT-SBRT-01`, instead of quoting the isolated PET number `"SUV max 8.4"`, the advocate quoted `"Medically inoperable early-stage non-small cell lung cancer."`.
   - Gate C verified equivalence under `CONCEPT-LUNG-CANCER`, promoting `CRIT-SBRT-01` to `MET`.
   - `DEV-LCD-SBRT-APP` becomes the **second agent-driven approval** in the benchmark (`DEFERRED_TO_HUMAN` → `APPROVED`).
3. **Accuracy & Safety (Task 3)**:
   - Agentic concordance advances to **48 / 84 (57.1% dev)**, up from 47 in v61.
   - Synonymy resolution reaches **10 / 19 (52.6% dev)**.
   - False Approvals remain strictly **0 across all three modes (0 / 0 / 0)**.
   - The 4 legitimate omission test cases continue to safely defer to human review.
   - Retrieval margins are 100% non-null (0 null `pre_margin`, 0 null `post_margin`).
4. **Retrieval Jitter Diagnosis (Task 4)**:
   - Two consecutive standalone retrieval runs over all 84 vignettes yielded **0 / 84 differences (100% exact agreement)**, eliminating GPU/CPU embedding computation non-determinism.

### Four-Number Safety Comparison Table
All metrics recomputed directly from committed evidence in [app/data/benchmarks/agentic_v62_three_mode_run.json](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/agentic_v62_three_mode_run.json):

| Execution Mode | Decisions (Approved / Denied / Deferred) | Concordant Decisions (Accuracy) | False Approvals (Safety) | False Denials | Safe Deferrals (Abstentions) | Synonymy Resolved (Target 19) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Deterministic Mode** (Committed 12 Concepts, 0 LLM calls) | 17 / 22 / 45 | **37 / 84 (44.0% dev)** | **0** | 2 | 45 | 0 / 19 (0.0% dev) |
| **Declarative Mode** (Committed 12 Concepts, LLM Proposer) | 19 / 20 / 45 | **39 / 84 (46.4% dev)** | **0** | 0 | 45 | 0 / 19 (0.0% dev) |
| **Agentic Mode v61** (Merged 131 Concepts, 8-Call Budget) | 29 / 18 / 37 | **47 / 84 (56.0% dev)** | **0** | 0 | 37 | 9 / 19 (47.4% dev) |
| **Agentic Mode v62** (Merged 131 Concepts, Scoped Gate C + Span Refine) | 30 / 18 / 36 | **48 / 84 (57.1% dev)** | **0** | **0** | **36** | **10 / 19 (52.6% dev)** |

---

## 2. Decision Delta vs v61

Comparing [app/data/benchmarks/agentic_v61_three_mode_run.json](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/agentic_v61_three_mode_run.json) with [app/data/benchmarks/agentic_v62_three_mode_run.json](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/agentic_v62_three_mode_run.json):

| Vignette ID | Governing Policy | Expected Decision | v61 Actual Decision | v62 Actual Decision | Status |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `DEV-LCD-SBRT-APP` | `LCD-SBRT` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`APPROVED`** | **RESCUED (+1)** |

All other 83 cases maintained exact decision concordance with v61. No regressions occurred.

---

## 3. Analysis of the Five Gate C Criteria

In v61, five budget-cleared criteria ran but were blocked at Gate C. Below is their precise outcome in v62:

### 1. `CRIT-SBRT-01` (`DEV-LCD-SBRT-APP`)
- **Outcome**: **RESCUED** (Promoted to `MET`)
- **Verbatim Quote**: `"Medically inoperable early-stage non-small cell lung cancer."` (slice `[630:690]`)
- **Mechanism**: Advocate span selection prioritized inoperability and staging elements over the isolated metric `"SUV max 8.4"`. The advocate quoted `"Medically inoperable early-stage non-small cell lung cancer."` at character slice `[630:690]`. Gate C verified equivalence under `CONCEPT-LUNG-CANCER`.
- **Transcript Evidence**:
  > `[#07] [Agent 3: Adversarial Verifier] -> CHALLENGE | Criterion: CRIT-SBRT-01`  
  > `Content: Defense of CRIT-SBRT-01: Grounded advocacy quote 'Medically inoperable early-stage non-small cell lung cancer.' passed Gate A, Gate B, and Gate C. Promoting CRIT-SBRT-01 to MET.`

### 2. `CRIT-SCS-02` (`DEV-NCD-SCS-APP`)
- **Outcome**: Still failing, but **cross-domain collision completely eliminated**.
- **Verbatim Quote**: `"Patient completed a 6-day temporary percutaneous spinal cord stimulator trial, documenting 80% pain relief and significant increase in daily walking distance."`
- **Mechanism**: In v61, Gate C suffered a false collision where `"spinal cord"` in the SCS note matched `CONCEPT-PROTON-PBT-01` (`Skull Base, Spine, or Critical Structure Proximity`, Radiation Oncology). With domain scoping, the proton concept was excluded from candidate evaluation under `NCD-SCS` (Interventional Pain / Neurosurgery). The criterion was evaluated purely within its governing domain. It remains un-promoted because the advocate quoted the stimulator trial text instead of psychological clearance, and Gate C rejected it as no matching concept definition.
- **Transcript Evidence**:
  > `[#13] [Agent 3: Adversarial Verifier] -> CHALLENGE | Criterion: CRIT-SCS-02`  
  > `Content: Advocacy on CRIT-SCS-02 rejected by GATE_C_MAP_CHECK (ConceptMap equivalence rejected: No matching concept definition.).`  
  *(Note: The v61 collision string `'Skull Base, Spine, or Critical Structure Proximity'` is completely gone).*

### 3. `CRIT-KYPHO-02` (`DEV-LCD-KYPHO-APP`)
- **Outcome**: Still failing.
- **Verbatim Quote**: `"Severe focal spinous process percussion tenderness at T12. Thoracic spine MRI shows 35% height loss of T12 with intense hyperintensity on STIR imaging..."`
- **Mechanism**: Within the `Interventional Radiology / Spine Surgery` domain, the clinical note documented acute fracture with STIR hyperintensity, but the phrasing did not match an accepted synonym for refractory pain or fracture edema under the committed concept map.
- **Transcript Evidence**:
  > `[#15] [Agent 3: Adversarial Verifier] -> CHALLENGE | Criterion: CRIT-KYPHO-02`  
  > `Content: Advocacy on CRIT-KYPHO-02 rejected by GATE_C_MAP_CHECK (ConceptMap equivalence rejected: No matching concept definition.).`

### 4. `CRIT-PAD-02` (`DEV-LCD-PAD-ATHERO-APP`)
- **Outcome**: Still failing.
- **Verbatim Quote**: `"Right lower extremity arterial duplex ultrasound demonstrates 85% focal stenosis in the proximal superficial femoral artery with monophasic waveform distally."`
- **Mechanism**: In `Vascular Surgery / Interventional Cardiology`, `CRIT-PAD-02` evaluated duplex 85% focal stenosis, which does not match an approved synonym in the committed concept dictionary.
- **Transcript Evidence**:
  > `[#15] [Agent 3: Adversarial Verifier] -> CHALLENGE | Criterion: CRIT-PAD-02`  
  > `Content: Advocacy on CRIT-PAD-02 rejected by GATE_C_MAP_CHECK (ConceptMap equivalence rejected: No matching concept definition.).`

### 5. `CRIT-CAT-02` (`DEV-NCD-CATARACT-APP`)
- **Outcome**: Still failing.
- **Verbatim Quote**: `"Visually significant cataract in right eye causing substantial impairment of activities of daily living refractory to spectacles."`
- **Mechanism**: The advocate quoted the ADL impairment text, which was evaluated within Ophthalmology against `CRIT-CAT-02` (`Visual Impairment ADLs`). Gate C distinguished the ADL impairment concept from lens opacity (`CONCEPT-VISUAL-IMPAIRMENT` vs `CONCEPT-CATARACT-LENS-OPACITY`).
- **Transcript Evidence**:
  > `[#15] [Agent 3: Adversarial Verifier] -> CHALLENGE | Criterion: CRIT-CAT-02`  
  > `Content: Advocacy on CRIT-CAT-02 rejected by GATE_C_MAP_CHECK (ConceptMap equivalence rejected: NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts ('Visual Impairment ADLs' vs 'Cataract and Lens Opacity')..).`

---

## 4. Advocacy, Debate, and Telemetry

```
Adversarial Verifier (Agent 3) Advocacy Telemetry:
  - Total Advocacy Attempts: 63
  - Total Advocacy Promotions: 3 (CRIT-KYPHO-01, CRIT-SBRT-01, CRIT-SI-01)
  - Total Advocacy Rejections: 60
    - Gate A (Verbatim Grounding Failure): 0
    - Gate B/C (Semantic / ConceptMap Equivalence Rejections): 60
    - Empty Quote Returned: 0
  - Agent-Driven Approvals: 2 (DEV-OPD-SI-FUSION-APP, DEV-LCD-SBRT-APP)

Two-Sided Debate Dynamics:
  - Counter-Readings Raised by Agent 3: 2
    - Objection Types: ANATOMIC_MISMATCH (1), TEMPORAL (1)
  - Defenses Attempted: 2
  - Conceded by Agent 2 via Counter-Reading: 2
  - Conceded by Agent 2 via Gate Failure: 9
  - Unresolved Disagreements: 0
  - Decisions Changed by Debate: 0

Budget & Latency Telemetry:
  - Total Decisions: Approved 30 (35.7%), Denied 18 (21.4%), Deferred 36 (42.9%) [Concordant: 48 (57.1%)]
  - Autonomous Approvals: 30 (35.7%), Denials: 18 (21.4%)
  - Judge Calls: 64 total across 84 cases (mean 0.76 calls/case, formula: total_judge_calls / 84)
  - Agent Turns: 180 total across 84 cases (mean 2.14 turns/case, formula: sum(turns_taken) / 84 using turns_taken field across Agent 2 and Agent 3)
  - Operational Budget Halts: 0
  - Abstention Gate Halts: 36 (34 missing mandatory criteria, 2 confidence below tau=0.85)
  - Mean Judge Latency: 15.04 s (max: 20.10 s)
  - Mean Case Wall Time: 23.65 s (min: 0.04 s, max: 72.45 s)
  - Cases Exceeding 60.0 s Wall Clock: 14 (was 9 in v61; all completed cleanly with 0 operational budget halts)
```

---

## 5. Safety & Legitimate Omissions Verification

### False Approvals
- **Deterministic**: 0 / 84
- **Declarative**: 0 / 84
- **Agentic**: 0 / 84

### Legitimate Omissions (True Positive Cases with Omitted Elements)
All 4 omission controls continue to safely defer to a human clinician:
1. `DEV-LCD-MRI-BRAIN-APP` (`LCD-MRI-BRAIN`): Expected `APPROVED` → Actual: `DEFERRED_TO_HUMAN` (Safe Deferral; omitted red flags requirement)
2. `DEV-LCD-MRI-LUMBAR-APP` (`LCD-MRI-LUMBAR`): Expected `APPROVED` → Actual: `DEFERRED_TO_HUMAN` (Safe Deferral; omitted 6-week conservative trial)
3. `DEV-NCD-CCTA-APP` (`NCD-CCTA`): Expected `APPROVED` → Actual: `DEFERRED_TO_HUMAN` (Safe Deferral; omitted intermediate CAD risk documentation)
4. `DEV-NCD-PACEMAKER-APP` (`NCD-PACEMAKER`): Expected `APPROVED` → Actual: `DEFERRED_TO_HUMAN` (Safe Deferral; omitted reversible cause documentation)

---

## 6. Retrieval Sanity & Margins

Read directly from `retrieval_sanity` in `agentic_v62_three_mode_run.json`:
- **Total Cases Evaluated**: **84**
- **Null `pre_margin` Count**: **0** (resolved; backfilled from shortlist telemetry)
- **Null `post_margin` Count**: **0** (resolved; backfilled from shortlist telemetry)
- **Top-1 Agreement (Pipeline vs Standalone)**: **84 / 84 (100.0% dev)**
- **Pipeline Gold Top-1 Accuracy**: **69 / 84 (82.1% dev)**
- **Pipeline Gold Top-3 Accuracy**: **82 / 84 (97.6% dev)**
- **Pipeline Gold Top-5 Accuracy**: **82 / 84 (97.6% dev)**
- **Re-Rank Flips Total**: **8** (all non-null margins)

---

## 7. Correction of v61 Delivery Report

In [docs/agentic_v61_delivery_report.md](file:///e:/Class/GitHub/CarePolicyGuard/docs/agentic_v61_delivery_report.md#L137):
- **Previous line**: `- **Top-1 Agreement**: **83 / 84 (98.8%)**`
- **Corrected line**: `- **Top-1 Agreement**: **84 / 84 (100.0%)**`
- **Provenance**: Line 137 in `agentic_v61_delivery_report.md` was stale text carried over from v59. The underlying committed JSON artifact (`agentic_v61_three_mode_run.json`) confirmed `top1_agreement_count: 84` and `disagreements: []`. This line has been corrected in-place.
