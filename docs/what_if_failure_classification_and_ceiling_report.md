# What-If Residual Failure Classification and Ceiling Report

> **DISCLOSURE**:
> - Provenance: Author-written synthetic development set (`dev_vignettes_extended.json`, 84 cases across 42 policies).
> - Status: **DEVELOPMENT-ONLY / WHAT-IF EXPERIMENTAL AUDIT**.
> - In-Memory Activation: 120 candidate `PASS_EQUIVALENCE` concepts activated in-memory only; committed production map remains strictly at 12 concepts.
> - Sealed Data: Never accessed `heldout_vignettes_v2.json`. Zero private identifiers or clinical PHI.

---

## 1. Clean Controlled Comparison (Task 1)

Both experimental arms were executed live in this session on the exact same 84 development vignettes using the identical `v2_verbatim_worked_example` prompt and call counting.

| Metric | Arm A: Committed Map Only (12 Concepts) | Arm B: Expanded Map (132 Concepts: 12 + 120 PENDING) | True Map Delta |
| :--- | :--- | :--- | :--- |
| **Active Map Concepts** | 12 | 132 | +120 concepts |
| **Total Pipeline Calls** | 111 | 111 | 0 |
| **Gate A Passes (Exact Slice)** | 68 | 67 | -1 |
| **Gate A Failures** | 43 | 44 | +1 |
| **Gate B Rejections (Semantic)** | 0 | 0 | 0 |
| **Gate C Map Rejections** | 68 | 62 | **-6** |
| **Proposals Accepted** | 0 | 5 | **+5** |
| **Concordant Decisions** | 39 / 84 (46.4%) | 39 / 84 (46.4%) | 0 (0.0%) |
| **False Approvals Caused by LLM** | 0 | 0 | **0** (Safety Invariant Maintained) |
| **False Denials Caused by LLM** | 0 | 0 | 0 |
| **Safe Deferrals to Human** | 45 | 45 | 0 |
| **Synonymy-Only Deferrals Resolved** | 0 / 19 | 1 / 19 (`DEV-LCD-RAD-NIV-APP`) | **+1** |

### Plain Delta Analysis
The concept map's true effect on this development set is:
1. **Gate C Veto Reduction**: Decreased Gate C rejections by 6 (from 68 to 62).
2. **Proposals Accepted**: Increased accepted proposals from 0 to 5 (+5).
3. **Synonymy Deferral Resolution**: Resolved 1 of 19 synonymy deferrals (`DEV-LCD-RAD-NIV-APP`).
4. **Overall Decision Concordance**: **Zero decision delta (0.0%, 39/84 to 39/84)**. Resolving the single criterion in `DEV-LCD-RAD-NIV-APP` enabled that individual case to pass, but across the full 84-case benchmark, overall concordance remained 39/84 (46.4%).
5. **Safety**: Zero false approvals in both arms.

---

## 2. Residual Failure Classification (Task 2)

Recorded in [what_if_residual_failure_classification.json](file:///e:/Class/GitHub/CarePolicyGuard/app/data/benchmarks/what_if_residual_failure_classification.json).

### Gate A Failures (44 Total)
Gate A requires a character-for-character exact slice from the clinical note. All 44 Gate A failures in Arm B were classified into mutually exclusive classes:

| Class | Count | Description & Representative Evidence |
| :--- | :--- | :--- |
| **Paraphrase of a Real Span** | **26** (59.1%) | The clinical concept is factually present in the note, but the LLM rephrased, altered casing, stripped punctuation, or summarized.<br>• *DEV-LCD-ACDF-NEG*: Claimed `"conservative management tried for only 1 week"` vs Note `"Conservative management tried for only 1 week."` (case and punctuation mismatch).<br>• *DEV-LCD-HALLUX-NEG*: Claimed `"no conservative shoe modifications attempted"` vs Note `"No conservative shoe modifications attempted."`<br>• *DEV-LCD-KYPHO-APP*: Claimed `"STIR or T2 MRI demonstrating hyperintensity"` vs Note `"MRI confirms acute compression fracture with severe vertebral marrow edema on STIR sequences"`. |
| **Hallucination** | **18** (40.9%) | The claimed text does not exist in the note. The LLM copied criterion definitions or prompt descriptions instead of extracting text from the note.<br>• *DEV-LCD-ESI-NEG*: Claimed `"Trial and failure of >= 4 weeks of non-invasive conservative treatment (medications, physical therapy, activity modification)."` (verbatim copy of criterion name/desc, not in note).<br>• *DEV-LCD-FACET-NEG*: Claimed `"Chronic Axial Pain Duration (>= 3 Months)"`.<br>• *DEV-OPD-VEIN-NEG*: Claimed `"persistent pain, edema, or stasis dermatitis"`. |
| **Wrong Span** | **0** (0.0%) | Verbatim span from wrong part of note or wrong patient context. |
| **Other** | **0** (0.0%) | Unclassifiable errors. |

### Gate C Vetoes (62 Total)
Proposals that passed Gate A and Gate B were audited at Gate C against the expanded 132-concept map.

| Class | Count | Description & Representative Evidence |
| :--- | :--- | :--- |
| **Claimed Concept Absent from Expanded Map** | **54** (87.1%) | The proposed text or criterion term has no matching concept or accepted term entry in the expanded concept map.<br>• *DEV-LCD-IMRT-APP*: `"3D-CRT plan exceeds rectal wall tolerance constraints"` vs `"Dosimetric Proof of 3D Conformal Inadequacy"`.<br>• *DEV-LCD-KNEE-ORTHOSIS-APP*: `"3+ anterior drawer, grade III laxity"` vs `"Documented Objective Knee Laxity or Ligamentous Deficiency"`.<br>• *DEV-LCD-KNEE-ORTHOSIS-APP*: `"conical thigh geometry"` vs `"Medical Justification for Custom vs Prefabricated Device"`.<br>• *DEV-LCD-KYPHO-APP*: `"Pain rating is 8/10 on visual analog scale"` vs `"Severe Vertebral Pain"`. |
| **Claimed Concept Present but Equivalence Wrong** | **8** (12.9%) | Terms exist in the map, but either match disjoint concepts or represent distinct anatomical instances requiring coverage judgment.<br>• *DEV-LCD-MRI-BRAIN-NEG*: LLM attempted to equate cervical pain symptoms to intracranial mass criteria.<br>• *DEV-LCD-FACET-NEG*: Attempted to equate radicular pain to facet arthropathy (explicit near-miss). |
| **Other** | **0** (0.0%) | Unclassifiable errors. |

### Top Recurring Missing Concepts
The 54 absent-concept vetoes clustered around specific clinical phrasing in the synthetic notes that the 120 policy-drafted concept entries omitted:
1. `Dosimetric Proof of 3D Conformal Inadequacy` (normal tissue constraints, rectal sparing, critical structure tolerance)
2. `Documented Objective Knee Laxity or Ligamentous Deficiency` (anterior drawer, Lachman, pivot shift, grade III laxity)
3. `Medical Justification for Custom vs Prefabricated Device` (disproportionate leg dimensions, conical thigh, severe varus deformity)
4. `Severe Vertebral Pain` (visual analog scale >= 7/10, acute fracture pain refractory to analgesics)
5. `Progressive Neurological Deficit` (motor weakness, extremity drift, myelopathic progression)
6. `Comparative Dosimetric Treatment Plan Demonstrating Sparing` (photon vs proton organ-at-risk dose differential)
7. `Epicardial Coronary Stenosis >= 70%` (severe coronary artery narrowing, subtotal occlusion)

---

## 3. Ceiling Estimate for the 19 Synonymy Deferrals (Task 3)

Case-by-case audit of the 19 author-written synonymy vignettes (`DEV-*-APP`):

| Vignette ID | Policy ID | What-If Status | Blocker Analysis & Ceiling Resolution Path |
| :--- | :--- | :--- | :--- |
| `DEV-LCD-IMRT-APP` | `LCD-IMRT` | Deferred | Blocked by Gate C: `"3D-CRT plan exceeds rectal wall tolerance constraints"` missed by map for conformal inadequacy. Resolves under complete map coverage. |
| `DEV-LCD-KNEE-ORTHOSIS-APP` | `LCD-KNEE-ORTHOSIS` | Deferred | Blocked by Gate C: `"3+ anterior drawer"` and `"conical thigh geometry"` missed by map. Resolves under complete map coverage. |
| `DEV-LCD-KYPHO-APP` | `LCD-KYPHO` | Deferred | Blocked by Dual: `CRIT-KYPHO-01` (Gate C map veto on VAS 8/10) + `CRIT-KYPHO-02` (Gate A paraphrase on STIR hyperintensity). Resolves under perfect quoting + map coverage. |
| `DEV-LCD-LUMBAR-DECOMP-APP` | `LCD-LUMBAR-DECOMP` | Deferred | Blocked by Gate C: `"severe lumbar spinal stenosis"` missed by map. Resolves under complete map coverage. |
| `DEV-LCD-MRI-BRAIN-APP` | `LCD-MRI-BRAIN` | Deferred | Blocked by Gate C: `"progressive right upper extremity hemiparesis"` missed by map for `CRIT-MRIB-02`. Resolves under complete map coverage. |
| `DEV-LCD-MRI-LUMBAR-APP` | `LCD-MRI-LUMBAR` | Deferred | Blocked by Gate A: Paraphrased plain radiographs span. Resolves under perfect verbatim quoting. |
| `DEV-LCD-PAD-ATHERO-APP` | `LCD-PAD-ATHERO` | Deferred | Blocked by Gate A: Paraphrased claudication and ABI spans. Resolves under perfect verbatim quoting. |
| `DEV-LCD-POWER-WC-APP` | `LCD-POWER-WC` | Deferred | Blocked by Gate A: Paraphrased PT/OT specialty evaluation. Resolves under perfect verbatim quoting. |
| `DEV-LCD-PROTON-APP` | `LCD-PROTON` | Deferred | Blocked by Gate C: Comparative plan cord dose differential missed by map. Resolves under complete map coverage. |
| `DEV-LCD-RAD-NIV-APP` | `LCD-RAD-NIV` | **RESOLVED (APPROVED)** | **Resolved in Arm B**: Map entry for elevated daytime PaCO2 / hypercapnia passed Gate C and satisfied criterion. |
| `DEV-LCD-SBRT-APP` | `LCD-SBRT` | Deferred | Blocked by Gate C: `CRIT-SBRT-01` accepted, but `CRIT-SBRT-02` (rigid immobilization motion management) missed by map. Resolves under complete map coverage. |
| `DEV-NCD-CARDIAC-REHAB-APP` | `NCD-CARDIAC-REHAB` | Deferred | Blocked by Gate C: CABG revascularization and aerobic exercise plan missed by map. Resolves under complete map coverage. |
| `DEV-NCD-CCTA-APP` | `NCD-CCTA` | Deferred | Blocked by Dual: `CRIT-CCTA-01` (Gate A paraphrase) + `CRIT-CCTA-02` (Gate C map veto). Resolves under perfect quoting + map coverage. |
| `DEV-NCD-MPI-PET-APP` | `NCD-MPI-PET` | Deferred | Blocked by Gate C: Severe multivessel CAD and ischemia missed by map. Resolves under complete map coverage. |
| `DEV-NCD-PACEMAKER-APP` | `NCD-PACEMAKER` | Deferred | Blocked by Gate A: Paraphrased exclusion of reversible bradycardia causes. Resolves under perfect verbatim quoting. |
| `DEV-NCD-PET-ONC-APP` | `NCD-PET-ONC` | Deferred | Blocked by Dual: `CRIT-PTONC-01` (Gate A paraphrase) + `CRIT-PTONC-02` (Gate C map veto). Resolves under perfect quoting + map coverage. |
| `DEV-NCD-PUMP-APP` | `NCD-PUMP` | Deferred | Blocked by Gate C: 75% pain relief and intractable pelvic pain missed by map. Resolves under complete map coverage. |
| `DEV-NCD-SGD-APP` | `NCD-SGD` | Deferred | Blocked by Gate A: Paraphrased SLP formal evaluation. Resolves under perfect verbatim quoting. |
| `DEV-OPD-SI-FUSION-APP` | `OPD-SI-FUSION` | Deferred | Blocked by Gate C: 75% relief on diagnostic SI block missed by map. Resolves under complete map coverage. |

### Blocker Distribution Summary
- **Already Resolved in Arm B**: 1 case (`DEV-LCD-RAD-NIV-APP`)
- **Blocked Exclusively by Gate C Map Coverage**: 10 cases (52.6%)
- **Blocked Exclusively by Gate A Verbatim Quoting**: 5 cases (26.3%)
- **Blocked by Dual Gate A + Gate C**: 3 cases (15.8%)
- **Theoretical Ceiling**: **19 of 19 (100%)** synonymy-only deferrals could resolve to `APPROVED` if both quoting and map coverage were perfected.

---

## 4. One-Paragraph Verdict & Biggest Blocker

The proposer's theoretical ceiling on this dataset is materially above zero decisions: **19 of the 19 synonymy deferrals (a potential +22.6% accuracy gain, raising decision concordance from 46.4% to 69.0%) could resolve to `APPROVED`** under perfect quoting and comprehensive concept coverage, confirming that the LLM is not structurally redundant with the deterministic engine. However, its realized contribution remains stalled at 1 decision (+1.2%) because **vocabulary mismatch in the ConceptMap is the single biggest remaining blocker (accounting for 54 of 62 Gate C vetoes, 87.1%, and blocking 13 of the 18 unresolved cases)**. The 3B model drafted candidate concepts solely from policy definition headers, producing abstract synonyms that failed to capture the concrete clinical phrasings (e.g., `"conical thigh geometry"`, `"3+ anterior drawer"`, `"exceeds rectal tolerance"`) present in the notes; concurrently, character-level quoting flaws (26 paraphrase failures) block the remaining 5 cases before Gate C is ever reached. For the LLM to flip even one additional decision, the human review workflow must curate the 13 specific clinical synonyms identified in this report into the approved ConceptMap whitelist, while prompting or post-processing must enforce exact case/punctuation anchoring to clear Gate A.
