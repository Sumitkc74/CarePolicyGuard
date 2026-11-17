# Delivery Report: v60 Margins, Advocacy & Gate C Diagnosis, and Record Corrections

**Parent Commit**: `9a766b0` (v59, Nov 16, 2026)  
**Execution Timestamp**: 2026-11-16T16:05:00Z  
**Target Commit Title**: `(v60) Record re-rank margins, diagnose empty-quote advocacy and Gate C failures, and restore smoke records`

---

## 1. Executive Summary

The v60 BUILD + DIAGNOSIS session accomplishes three objectives:
1. **Task 1 (Build Fix)**: Populates `pre_margin` and `post_margin` (pre- and post-rerank margins) across all shortlist candidate records, flips evidence, and pipeline selections in the measurement JSON. Empirically verified: null candidate margin count dropped from 391 to 0; `DEV-LCD-PAD-ATHERO-APP` reads `post_margin = 0.0088` (`0.8588 - 0.8500`).
2. **Task 2 (Diagnosis)**: Investigates all 11 empty-quote advocacy rejections and all 6 Gate C rejections in positive development cases directly against the clinical notes, criterion definitions, and concept map without circular LLM evaluation:
   - **Empty-Quote Advocacy (11 criteria)**: **7 Judge-Extraction Failures** (verbatim clinical evidence present in the synthetic note, but advocate returned empty quote due to budget exhaustion or semantic extraction failure) vs **4 Genuine Clinical Evidence Omissions** (evidence legitimately absent from the note narrative; safe deferral to human review).
   - **Gate C Verification (6 criteria)**: **6 Map Gaps** (clinical synonymy present in note, but rejected due to unmapped concepts or cross-domain token collision) vs **0 Correct Rejections** (none of the 6 were genuinely disjoint). DRAFT concept definitions authored and documented (non-active).
   - Deliverable committed to [app/data/benchmarks/v60_advocacy_failure_diagnosis.json](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/v60_advocacy_failure_diagnosis.json).
3. **Task 3 (Record Corrections)**:
   - Corrected typo in [docs/agentic_v59_delivery_report.md](file:///e:/Class/GitHub/CarePolicyGuard/docs/agentic_v59_delivery_report.md#L69): $\tau = 0.80 \rightarrow \tau = 0.85$.
   - Restored original v56 smoke transcript record [app/data/benchmarks/v56_smoke_transcripts.json](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/v56_smoke_transcripts.json) from `c04665a` (timestamp `2026-11-16T04:15:24.260003+00:00`) and preserved the v59 smoke re-run in [app/data/benchmarks/v59_smoke_transcripts.json](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/v59_smoke_transcripts.json) (timestamp `2026-11-16T08:04:39.463925+00:00`).

---

## 2. Task 1: Re-Rank Margin Recording & Verification

In [app/services/policy_shortlist_service.py](file:///e:/Class/GitHub/CarePolicyGuard/app/services/policy_shortlist_service.py), [app/agents/pipeline.py](file:///e:/Class/GitHub/CarePolicyGuard/app/agents/pipeline.py), and [scripts/run_agentic_v59_three_mode_measurement.py](file:///e:/Class/GitHub/CarePolicyGuard/scripts/run_agentic_v59_three_mode_measurement.py), both `pre_margin` and `post_margin` are now explicitly propagated to every candidate in `shortlist`, `pipeline_selections`, `flips`, and the per-case outputs.

### Empirical Margin Verification
- **Target Case `DEV-LCD-PAD-ATHERO-APP`**:
  - `pre_rerank_top1`: `LCD-PAD-ATHERO` (score: `1.0000`, runner-up `NCD-20.29`: `0.8179`) $\rightarrow$ `pre_margin = 0.1821`
  - `post_rerank_top1`: `NCD-20.29` (score: `0.8588`, runner-up `LCD-PAD-ATHERO`: `0.8500`) $\rightarrow$ `post_margin = 0.0088`
- **Candidate Margins in Measurement JSON** ([app/data/benchmarks/agentic_v59_three_mode_run.json](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/agentic_v59_three_mode_run.json)):
  - Total candidates evaluated across 84 cases: **391**
  - Null `post_margin` count before fix: **391**
  - Null `post_margin` count after fix: **0**
  - Null `pre_margin` count before fix: **391**
  - Null `pre_margin` count after fix: **0**
  - Re-rank flips recorded: **9** (null margins: **0**)

---

## 3. Task 2: Empty-Quote & Gate C Failure Diagnosis

### Summary Diagnosis Counts

| Category | Total Criteria | Evidence Present / Map Gap | Evidence Absent / Correct Rejection |
| :--- | :---: | :---: | :---: |
| **Empty-Quote Advocacy Failures** | **11** | **7** (Judge-Extraction Failures) | **4** (Legitimate Clinical Omissions) |
| **Gate C Concept Map Rejections** | **6** | **6** (Map Gaps) | **0** (Correct Rejections) |

---

### Diagnosis of 11 Empty-Quote Advocacy Failures

| Vignette ID | Criterion Code | Verdict | Verbatim Note Span (or Missing Element) | Criterion Element Satisfied | Root Cause Mechanism |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `DEV-LCD-KYPHO-APP` | `CRIT-KYPHO-02` | **Evidence Present** | *"Thoracic spine MRI shows 35% height loss of T12 with intense hyperintensity on STIR imaging demonstrating acute osteoporotic vcf with bone edema."* | STIR hyperintensity / bone marrow edema confirming acute vertebral fracture. | Advocate call budget exhausted (3/3) on preceding criterion; automated empty-quote return. |
| `DEV-LCD-MRI-BRAIN-APP` | `CRIT-MRIB-02` | **Evidence Absent** | *Missing*: Progressive headache with red flags (nocturnal awakening, papilledema, Valsalva worsening). Note documents: *"No history of uncomplicated tension headache"*. | None (patient presented with focal motor deficits, not headache). | Clinical evidence genuinely absent from vignette narrative. Safe deferral to human review. |
| `DEV-LCD-MRI-LUMBAR-APP` | `CRIT-MRIL-02` | **Evidence Absent** | *Missing*: Preceding or concurrent plain radiographs (lumbar X-ray). Note documents 6-week PT failure and motor weakness, but zero lumbar radiographs. | None (radiograph evaluation omitted). | Plain X-ray requirement genuinely omitted in vignette text. Safe deferral to human review. |
| `DEV-LCD-PAD-ATHERO-APP` | `CRIT-PAD-02` | **Evidence Present** | *"Resting right ankle-brachial index is 0.48. Duplex ultrasound reveals hemodynamically significant stenosis with 85% occlusive calcified plaque in the superficial femoral artery."* | Objective vascular testing: ABI <= 0.90 (0.48) and duplex ultrasound confirming >= 50% stenosis (85%). | Advocate call budget exhausted (3/3) following debate on CRIT-PAD-01. |
| `DEV-LCD-SBRT-APP` | `CRIT-SBRT-01` | **Evidence Present** | *"76-year-old with severe baseline COPD (FEV1 32% predicted, home oxygen 2 L/min) evaluated for newly discovered right upper lobe solitary nodule. Thoracic surgery deemed patient medically inoperable due to high operative mortality risk... PET-CT confirms hypermetabolic 2.2 cm peripheral pulmonary lesion... cT1cN0M0"*. | Medically inoperable early-stage lung cancer (FEV1 < 40%, cT1cN0M0 2.2 cm solitary lesion). | Advocate budget exhausted following debate counter-reading on spine proximity. |
| `DEV-NCD-CATARACT-APP` | `CRIT-CAT-02` | **Evidence Present** | *"Patient is no longer able to read standard book print even with updated bifocal glasses, creating significant difficulty with daily activities... progressive blurring and severe glare while driving at night."* | Visual impairment interfering with essential ADLs (inability to read print, disabling glare driving at night). | Advocate budget exhausted following Gate C challenge on CRIT-CAT-01. |
| `DEV-NCD-CCTA-APP` | `CRIT-CCTA-01` | **Evidence Absent** | *Missing*: Documentation of sinus rhythm and achievable target resting heart rate < 65 bpm. Note documents 35% intermediate pre-test risk, but omits technical gating parameters. | None (technical gating parameters omitted). | Gating prerequisites genuinely absent in vignette narrative. Safe deferral to human review. |
| `DEV-NCD-PACEMAKER-APP` | `CRIT-PACE-02` | **Evidence Absent** | *Missing*: Documentation ruling out reversible drug toxicity (beta-blockers, digoxin) or transient ischemia. Note documents normal BMP (K 4.2) and thyroid, but omits toxicologic / medication review. | None (reversible medication toxicity not ruled out). | Documentation of medication-induced reversible etiology exclusion is genuinely absent. Safe deferral. |
| `DEV-NCD-PET-ONC-APP` | `CRIT-PTONC-01` | **Evidence Present** | *"Biopsy pathology confirms moderately differentiated invasive esophageal adenocarcinoma."* | Pathology report documenting biopsy-proven solid malignancy (invasive esophageal adenocarcinoma). | LLM Judge/Advocate extraction failure: model fixated on 'solitary pulmonary nodule' clause and overlooked esophageal adenocarcinoma as biopsy-proven malignancy. |
| `DEV-NCD-SCS-APP` | `CRIT-SCS-02` | **Evidence Present** | *"Pre-procedure psychological evaluation completed and cleared with no unresolved behavioral contraindications."* | Formal pre-implant psychological evaluation completed with documented behavioral clearance. | Advocate budget exhausted following Gate C rejection on CRIT-SCS-01. |
| `DEV-OPD-SI-FUSION-APP` | `CRIT-SI-01` | **Evidence Present** | *"Fluoroscopically guided diagnostic right sacroiliac joint block produced documented 85% relief of baseline pain during the anesthetic window."* | >= 75% pain relief on fluoroscopically guided diagnostic SI joint block (documented 85% relief). | Advocate budget exhausted following debate challenge on conservative duration. |

---

### Diagnosis of 6 Gate C Rejections & Proposed Draft Concept Definitions

| Vignette ID | Criterion Code | Verdict | Quoted Span Passed to Gate C | Concept Map Consulted | Proposed Non-Active DRAFT Concept |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `DEV-LCD-PAD-ATHERO-APP` | `CRIT-PAD-01` | **Map Gap** | *"Right lower extremity pulses absent at popliteal and pedal levels. Resting right ankle-brachial index is 0.48. Duplex ultrasound reveals hemodynamically significant stenosis with 85% occlusive calcified plaque in the superficial femoral artery."* | Committed (12 concepts) & Draft (`CONCEPT-RUTHERFORD-CAT-3`) | `DRAFT-CONCEPT-SEVERE-CLAUDICATION-AMBULATION`<br>• *Terms*: `severe lifestyle-limiting claudication occurring after walking less than 50 paces`, `severe intermittent claudication severely limiting ambulation`, `rutherford class 3`<br>• *Rationale*: Walking < 50 paces (Rutherford class 3) is clinically synonymous with severe claudication limiting ambulation. |
| `DEV-LCD-PCI-APP` | `CRIT-PCI-01` | **Map Gap** | *"Diagnostic coronary angiography confirms severe coronary artery stenosis of 85% in the proximal left anterior descending artery with TIMI 3 flow."* | Committed & Draft (neither contained angiographic coronary stenosis equivalence) | `DRAFT-CONCEPT-CORONARY-ANGIOGRAPHIC-STENOSIS`<br>• *Terms*: `coronary angiography confirms severe coronary artery stenosis of 85%`, `severe coronary artery stenosis`, `luminal diameter stenosis >= 70%`, `coronary stenosis`<br>• *Rationale*: Angiographic 85% proximal LAD stenosis satisfies >= 70% luminal diameter stenosis requirement in a major epicardial coronary artery. |
| `DEV-LCD-POWER-WC-APP` | `CRIT-PWC-02` | **Map Gap** | *"Severe progressive neurological condition with total inability to self-propel manual mobility devices. Plan: Group 3 complex rehabilitative power wheelchair with multi-function power seating."* | Committed & Draft (contains wheelchair propulsion, lacks PT/OT + ATP evaluation) | `DRAFT-CONCEPT-SEATED-MOBILITY-PT-ATP-EVAL`<br>• *Terms*: `comprehensive seated mobility evaluation completed by licensed physical therapist and certified atp`, `specialty seating evaluation`, `certified atp evaluation`, `pt/ot evaluation completed`<br>• *Rationale*: Comprehensive seated mobility evaluation completed by licensed PT and certified ATP is identical to mandated specialty evaluation. |
| `DEV-NCD-CATARACT-APP` | `CRIT-CAT-01` | **Map Gap** | *"Best corrected visual acuity is 20/60 in the right eye and 20/50 in the left eye."* | Committed & Draft (lacks visual acuity ratio / Snellen scale mappings) | `DRAFT-CONCEPT-BCVA-20-50-OR-WORSE`<br>• *Terms*: `best corrected visual acuity is 20/60 in the right eye`, `bcva 20/60`, `best corrected visual acuity 20/50 or worse`, `bcva 20/50`<br>• *Rationale*: BCVA 20/60 is numerically worse than 20/50 on standard Snellen acuity scale and satisfies threshold criterion. |
| `DEV-NCD-SCS-APP` | `CRIT-SCS-01` | **Map Gap** | *"Patient completed a 6-day temporary percutaneous spinal cord stimulator trial, documenting 80% pain relief and significant increase in daily walking distance."* | Draft (`CONCEPT-TEMPORARY-SCS-TRIAL-RELIEF` vs `CONCEPT-SKULL-BASE-SPINE-PROXIMITY`) | `DRAFT-CONCEPT-SCS-TRIAL-80-PERCENT-RELIEF`<br>• *Terms*: `temporary percutaneous spinal cord stimulator trial, documenting 80% pain relief`, `6-day temporary percutaneous spinal cord stimulator trial`, `scs trial relief >= 50%`<br>• *Rationale*: Documented 80% relief during 6-day trial satisfies >= 50% pain relief requirement during 3-7 day trial. Resolves cross-domain collision on keyword 'spine'. |
| `DEV-NCD-SGD-APP` | `CRIT-SGD-02` | **Map Gap** | *"Severe irreversible expressive communication deficit with successful formal SLP device trial. Plan: Dedicated synthesized speech-generating device with integrated eye-tracking access."* | Committed & Draft (lacks formal written SLP assessment and trial entries) | `DRAFT-CONCEPT-FORMAL-SLP-AAC-EVALUATION`<br>• *Terms*: `comprehensive assessment by licensed speech-language pathologist (slp)`, `slp completed formal device trial with dedicated eye-gaze speech-generating system`, `successful formal slp device trial`, `slp assessment completed`<br>• *Rationale*: Assessment by licensed SLP with completed eye-gaze AAC system trial is clinically synonymous with required formal assessment and trial. |

---

## 4. Task 3: Record Corrections

### 1. Delivery Report $\tau$ Value Typo Corrected
- In [docs/agentic_v59_delivery_report.md](file:///e:/Class/GitHub/CarePolicyGuard/docs/agentic_v59_delivery_report.md#L69):
  - **Before**: `2 calibrated confidence below $\tau=0.80$`
  - **After**: `2 calibrated confidence below $\tau=0.85$`
  - Confirmed: matches code definition `tau = settings.CONFIDENCE_THRESHOLD = 0.85`.

### 2. Original v56 Smoke Record Restored & v59 Preserved
- Checked out original [app/data/benchmarks/v56_smoke_transcripts.json](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/v56_smoke_transcripts.json) from parent `c04665a`:
  - `timestamp`: `2026-11-16T04:15:24.260003+00:00`
- Persisted v59 smoke check re-run to [app/data/benchmarks/v59_smoke_transcripts.json](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/v59_smoke_transcripts.json):
  - `timestamp`: `2026-11-16T08:04:39.463925+00:00`
- Both files are now tracked and present in the repository.

---

## 5. Verification Outputs

### Regression Test Suite Verification
```text
======================= 16 passed, 1 warning in 20.29s ========================
- tests/test_abstention_routing_hole.py: 2 passed
- tests/test_benchmark.py: 5 passed (10/10 clinical vignettes verified)
- tests/test_v1_heldout_regressions.py: 9 passed (15/15 held-out cases verified, 0 False Approvals, 0 False Denials)
```

### Verbatim Ruff Counts
```text
app/agents/pipeline.py: 47 errors (target: <= 47, clean against baseline)
app/agents/policy_retriever.py: 12 errors (target: <= 12, clean against baseline)
app/api/pas_routes.py: 35 errors (target: <= 35, clean against baseline)
app/services/policy_shortlist_service.py: 0 errors
scripts/run_agentic_v59_three_mode_measurement.py: 0 errors
tests/test_abstention_routing_hole.py: 0 errors
```

---

## 6. Plain Statement of Anything That Did Not Work

1. **Gate C Cross-Domain Keyword Collision**: In `DEV-NCD-SCS-APP`, the word `"spine"` in `"temporary percutaneous spinal cord stimulator trial"` matched an unrelated draft SBRT concept (`CONCEPT-SKULL-BASE-SPINE-PROXIMITY`), causing Gate C to reject the quote as belonging to disjoint concepts. Fixing cross-domain collisions requires scoped domain matching rather than global keyword token matching in Gate C.
2. **Advocacy Exhaustion Under Multi-Round Debates**: 6 of the 7 extraction failures were caused by the hard 3-call per-case advocate budget being consumed by earlier criteria or challenges, forcing Agent 3 to return an empty quote `(Quoted evidence: '')` on downstream criteria without examining the text.
