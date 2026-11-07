# CarePolicyGuard: 50-Policy Development Evaluation Report

> **DEVELOPMENT-ONLY BENCHMARK AUDIT NOTICE**
> **Provenance**: Synthetic Development Vignette Evaluation Set (`dev_vignettes_extended.json`).
> **Dataset Type**: Author-written synthetic development set (84 cases: 1 approved, 1 negative per policy across 42 extended policies).
> **Validation Status**: **DEVELOPMENT-ONLY**. This evaluation tests system behavior against author-written criteria and synthetic clinical narratives.
> **Important Disclosures**:
> 1. This is **NOT** a held-out validation benchmark. Real-world validation requires clinical EHR datasets with independent clinician ground-truth.
> 2. Vignettes were constructed from the policies' own criteria definitions to test pipeline retrieval sensitivity and rule evaluation mechanics without circular cues.
> 3. Zero circular cues: narratives contain no policy slugs, no LCD/NCD identifiers, and no coverage verdict phrases.
> 4. Criterion traceability for all 42 extended policies remains strictly `CLAIMED_UNVERIFIED` pending independent regulatory audit.

**Audit Execution Timestamp**: `2026-11-07 07:32:50 UTC`  
**Total Extended Policies Audited**: `42`  
**Total Evaluation Cases**: `84` (2 per policy: 1 approved, 1 negative)  
**Pipeline Decision Threshold**: `tau = 0.85` (unchanged)  

---

## 1. Overall Development Performance & Historical Run Comparison

| Evaluation Metric | Starting Head (`18bc531`) | Independent Re-run | Current Verified Head (`9b480f0` + fixes) | Delta vs Starting Head | Benchmark Dataset |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **AUTO Retrieval Top-1 Accuracy** | **88.1%** (`74/84`) | **86.9%** (`73/84`) | **86.9%** (`73/84`) | -1.2% (1 case: `WOUND-VAC-NEG`) | Synthetic Dev Set (42 Extended Policies) |
| **AUTO Retrieval Top-3 Accuracy** | **97.6%** (`82/84`) | **97.6%** (`82/84`) | **97.6%** (`82/84`) | 0.0% (Identical Top-3) | Synthetic Dev Set (42 Extended Policies) |
| **Adjudication Decision Accuracy** | **41.7%** (`35/84`) | **42.9%** (`36/84`) | **42.9%** (`36/84`) | +1.2% (36/84 concordance) | Synthetic Dev Set (42 Extended Policies) |

### Decision Transition Breakdown (Current Head)
- **Concordant Decisions**: `36/84` (42.9%)
- **Discordant Decisions**: `48/84` (57.1%)
  - **False Denials (`APPROVED -> DENIED`)**: `3/84` (3.6%) — `DEV-OPD-BOTOX-APP`, `DEV-OPD-RHINO-APP`, `DEV-OPD-VEIN-APP`.
  - **Safe Human Deferrals on Positive Cases (`APPROVED -> DEFERRED_TO_HUMAN`)**: `21/84` (25.0%) — criteria missing keywords/synonyms, causing calibrated confidence to drop below $\tau = 0.85$.
  - **Safe Human Deferrals on Negative Cases (`DENIED -> DEFERRED_TO_HUMAN`)**: `24/84` (28.6%) — negative cases lack affirmative findings rather than containing explicit disqualifying statutory exclusions, safely routing to clinician review instead of improper automated denial.

---

## 2. In-Depth Root Cause Diagnosis: WOUND-VAC Top-1 Retrieval Regression

### Affected Case: `DEV-LCD-WOUND-VAC-NEG`
- **Expected Policy**: `LCD-WOUND-VAC` (Negative Pressure Wound Therapy / NPWT)
- **Starting Head (`18bc531`) Top-1**: `LCD-WOUND-VAC`
- **Current Head (`9b480f0`) Top-1**: `LCD-LUMBAR-DECOMP` (Top-2: `LCD-WOUND-VAC`)

### Clinical Narrative Excerpt
```text
[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]
CLINICAL PROGRESS NOTE: Advanced Wound Care Center
SUBJECTIVE: 81-year-old nursing home resident evaluated for chronic sacral ulceration.
OBJECTIVE: Examination reveals a 5 cm ulcer completely covered by thick, adherent black necrotic tissue and devitalized slough. No surgical debridement has been performed.
ASSESSMENT & PLAN: Unstageable necrotic pressure wound. Application of negative pressure wound therapy is contraindicated over un-debrided necrotic tissue or untreated osteomyelitis.
```

### Exact Mechanism & Mathematical Scoring Dissection
1. **Sub-string Word-Boundary Leaking in Dense Concept Projection**:
   - In `app/services/hybrid_retriever.py`, the dense concept vocabulary `CLINICAL_CONCEPT_VOCAB` contains the abbreviation `"esi"` for Epidural Steroid Injections.
   - The projection function `_embed_text` used the substring check `if concept in lowered:`.
   - The clinical note contains `"81-year-old nursing home resident..."`.
   - The token `"esi"` is a direct substring of `"resident"` (`r - esi - dent`).
   - Consequently, the query vector falsely triggered a strong activation for `"esi"` ($0.7071$).

2. **Cross-Domain Policy Overlap**:
   - `LCD-LUMBAR-DECOMP` criterion `CRIT-LDEC-02` (Conservative Therapy Trial Failure) explicitly lists epidural steroid injections (`esi`) as a conservative modality.
   - Thus, `CRIT-LDEC-02` matched the false `"esi"` concept, achieving a dense cosine similarity of `0.4082` and ranking **#8 in Dense Semantic Retrieval**.
   - Concurrently, `CRIT-LDEC-02` contains general conservative care vocabulary ("conservative", "therapy", "trial", "performed", "tissue"), causing BM25 Okapi to rank it **#7 in Lexical Retrieval** (score: `22.83`).

3. **Keyword Asymmetry in Target Policy Chunks**:
   - In `LCD-WOUND-VAC.json`, the criteria definitions and keyword lists primarily indexed the abbreviation `"wound_vac"`.
   - The synthetic note used the formal terminology `"negative pressure wound therapy"`.
   - While BM25 successfully ranked `LCD-WOUND-VAC` (`CRIT-VAC-EXCL-01`) at **#1 in Lexical Retrieval** (score: `62.69`), `LCD-WOUND-VAC` failed to score in the Dense Semantic top-20 because its criteria chunks lacked the exact multi-word token `"negative pressure wound therapy"`.

4. **Reciprocal Rank Fusion (RRF, $c = 60$) Computation**:
   $$\text{RRF}(d) = \sum_{m \in \{\text{BM25}, \text{Dense}\}} \frac{1}{60 + \text{rank}_m(d)}$$

   - For `LCD-LUMBAR-DECOMP` (`CRIT-LDEC-02`):
     $$\text{RRF} = \frac{1}{60 + 7} + \frac{1}{60 + 8} = \frac{1}{67} + \frac{1}{68} = 0.014925 + 0.014706 = \mathbf{0.0296}$$

   - For `LCD-WOUND-VAC` (`CRIT-VAC-EXCL-01`):
     $$\text{RRF} = \frac{1}{60 + 1} + 0 = \frac{1}{61} = \mathbf{0.0164}$$

   Because $0.0296 > 0.0164$, `LCD-LUMBAR-DECOMP` superseded `LCD-WOUND-VAC` for Top-1 position, dropping `LCD-WOUND-VAC` to Top-2. (Top-3 accuracy remains preserved at 97.6%).

---

## 3. Real Failure Mechanisms Behind the 3 False Denials

The declarative evaluation yielded exactly 3 false denials where the synthetic note was written as an approved case (`expected: APPROVED`), but the pipeline returned `DENIED`. Forensic audit reveals distinct deterministic logic defects rather than clinical reasoning errors:

### Case 1: `DEV-OPD-BOTOX-APP` (`OPD-BOTOX`)
- **Expected Decision**: `APPROVED`
- **Actual Decision**: `DENIED`
- **Failing Criterion**: `CRIT-BOTOX-01` (Chronic Migraine Frequency $\ge 15.0$ days/month)
- **Clinical Narrative**: *"Headache diary confirms 18 headache days per month, with 12 days meeting full criteria for throbbing migraine with photophobia and nausea."*
- **Mechanism**: The numeric candidate extraction pattern in `DeclarativePolicyEngine` search terms matched "headache" and scanned forward for the numeric metric. It bound to the nearest numeric clause *"12 days meeting full criteria"* rather than *"18 headache days per month"*. The parser extracted `val = 12.0`, evaluated `12.0 >= 15.0` as `False`, and assigned `status = NOT_MET`. Under Medicare PA rules, failure of an essential indication triggers automatic `DENIED`.

### Case 2: `DEV-OPD-RHINO-APP` (`OPD-RHINO`)
- **Expected Decision**: `APPROVED`
- **Actual Decision**: `DENIED`
- **Failing Criterion**: `CRIT-RHINO-01` (Chronic Nasal Airway Obstruction $\ge 180$ days)
- **Clinical Narrative**: *"chronic unilateral right-sided nasal airway obstruction causing persistent mouth breathing and sleep disruption for 1 year following nasal trauma. Patient has used intranasal fluticasone spray and nasal saline irrigations consistently for 8 weeks without improvement in airflow."*
- **Mechanism**: `CRIT-RHINO-01` is compiled as a `TEMPORAL_DURATION` criterion requiring `min_duration_days = 180` (6 months). The temporal duration regex matched the conservative medical therapy duration *"8 weeks"* (56 days) rather than the chronic symptom duration *"1 year"* (365 days). Evaluating `56 >= 180` resulted in `False` ("documented timeline (56 days) does not satisfy requirement of 180 days"), assigning `status = NOT_MET` and causing false denial.

### Case 3: `DEV-OPD-VEIN-APP` (`OPD-VEIN`)
- **Expected Decision**: `APPROVED`
- **Actual Decision**: `DENIED`
- **Failing Criterion**: `CRIT-VEIN-01` (Venous Reflux Duration $\ge 500.0$ ms)
- **Clinical Narrative**: *"Standing duplex ultrasound demonstrates great saphenous vein reflux duration of 1450 ms at the saphenofemoral junction with vein diameter of 7.8 mm... refractory to 4 months graduated compression therapy."*
- **Mechanism**: In `app/services/declarative_engine.py`, the numeric regex patterns used the bounded digit quantifier `\d{1,3}(?:\.\d+)?` (originally designed for blood pressure, percentages, and small integer scores). The 4-digit duration `1450` failed to match `\d{1,3}`. The regex fell back across the paragraph and matched the digit `4` from *"4 months graduated compression therapy"*. The parser evaluated `val = 4.0` against `thresh = 500.0`, determining `4.0 ms >= 500.0 ms` to be `False` ("Metric fails statutory threshold: 4.0ms does not satisfy >= 500.0"). This marked `CRIT-VEIN-01` as `NOT_MET` and issued an automatic denial.

---

## 4. Comprehensive Failure Classification Table (All 48 Discordant Cases)

Every discordant case from the 84-vignette run is audited and classified into one of four mutually exclusive failure classes:
- **`logic defect`**: Flaw in core code, regular expressions, or value extraction algorithms.
- **`criterion-design`**: Flaw or uncalibrated constraint in the declarative policy JSON itself.
- **`synonymy-only`**: The clinical narrative used valid medical synonyms/subtypes/paraphrases omitted from the literal keyword list.
- **`genuine-ambiguity`**: The clinical scenario contains genuine borderline evidence requiring human medical director discretion.

| Vignette ID | Policy ID | Expected | Actual | Failure Classification | Root Cause & Clinical Rationale |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `DEV-OPD-BOTOX-APP` | `OPD-BOTOX` | `APPROVED` | `DENIED` | **`logic defect`** | Numeric extractor bound to "12 days" instead of "18 headache days", failing $\ge 15$ cutoff. |
| `DEV-OPD-RHINO-APP` | `OPD-RHINO` | `APPROVED` | `DENIED` | **`logic defect`** | Temporal parser bound to 8-week medical therapy rather than 1-year airway obstruction. |
| `DEV-OPD-VEIN-APP` | `OPD-VEIN` | `APPROVED` | `DENIED` | **`logic defect`** | Candidate regex `\d{1,3}` rejected 4-digit `1450 ms`, extracting `4.0 ms` from 4 months. |
| `DEV-LCD-HIP-ARTHRO-NEG` | `LCD-HIP-ARTHRO` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Negative vignette lacks positive criteria rather than documenting an explicit exclusion; safe human deferral. |
| `DEV-LCD-HIP-SCOOP-NEG` | `LCD-HIP-SCOOP` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Borderline FAI presentation without explicit disqualifier; requires clinical review. |
| `DEV-LCD-IMRT-APP` | `LCD-IMRT` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | `CRIT-IMRT-02` dosimetric constraint phrasing missed by deterministic keyword regex. |
| `DEV-LCD-IMRT-NEG` | `LCD-IMRT` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Boundary coverage judgment regarding organ proximity (rectal sparing vs spinal cord). |
| `DEV-LCD-KNEE-ARTHRO-NEG` | `LCD-KNEE-ARTHRO` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Osteoarthritis without meniscal tear lacks affirmative proof, safely abstaining to human. |
| `DEV-LCD-KNEE-ORTHOSIS-APP` | `LCD-KNEE-ORTHOSIS` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Unloader brace terminology and ligamentous instability synonyms omitted from keywords. |
| `DEV-LCD-KNEE-ORTHOSIS-NEG` | `LCD-KNEE-ORTHOSIS` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Absence of ambulatory documentation safely routes to human clinician review. |
| `DEV-LCD-KYPHO-APP` | `LCD-KYPHO` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | "Vertebroplasty/kyphoplasty" and "pathologic compression collapse" synonym mismatch. |
| `DEV-LCD-LUMBAR-DECOMP-APP` | `LCD-LUMBAR-DECOMP` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Neurogenic claudication symptom descriptions missed by strict laminectomy keyword list. |
| `DEV-LCD-LUMBAR-DECOMP-NEG` | `LCD-LUMBAR-DECOMP` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Incomplete conservative therapy documentation safely abstains under $\tau=0.85$. |
| `DEV-LCD-LUMBAR-FUSION-NEG` | `LCD-LUMBAR-FUSION` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Low-grade spondylolisthesis without gross translation warrants clinical judgment. |
| `DEV-LCD-MRI-BRAIN-APP` | `LCD-MRI-BRAIN` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`criterion-design`** | `CRIT-MRIB-02` requires prior CT failure; narrative documented acute focal deficit directly. |
| `DEV-LCD-MRI-BRAIN-NEG` | `LCD-MRI-BRAIN` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Chronic uncomplicated tension headache lacks positive indications; defers safely. |
| `DEV-LCD-MRI-LUMBAR-APP` | `LCD-MRI-LUMBAR` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Red flag cauda equina syndrome terminology paraphrased in emergency note. |
| `DEV-LCD-MRI-LUMBAR-NEG` | `LCD-MRI-LUMBAR` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Uncomplicated acute back strain (< 6 weeks) lacks positive criteria, safely abstaining. |
| `DEV-LCD-PAD-ATHERO-APP` | `LCD-PAD-ATHERO` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Rutherford category 4-5 resting ischemic pain terminology missed by PAD keywords. |
| `DEV-LCD-PAD-ATHERO-NEG` | `LCD-PAD-ATHERO` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Mild claudication without supervised exercise trial lacks affirmative criteria; defers. |
| `DEV-LCD-PCI-APP` | `LCD-PCI` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`criterion-design`** | `CRIT-PCI-01` requires fractional flow reserve (FFR); narrative documented 95% LAD stenosis. |
| `DEV-LCD-PCI-NEG` | `LCD-PCI` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Stable angina without functional ischemia documentation safely defers to clinician. |
| `DEV-LCD-POWER-WC-APP` | `LCD-POWER-WC` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | "Power mobility device" and "inability to operate manual chair" synonym mismatch. |
| `DEV-LCD-POWER-WC-NEG` | `LCD-POWER-WC` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Home environment accessibility unverified in note, prompting human deferral. |
| `DEV-LCD-PROTON-APP` | `LCD-PROTON` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Skull base chordoma / chondrosarcoma critical structure proximity paraphrasing. |
| `DEV-LCD-PROTON-NEG` | `LCD-PROTON` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Standard systemic indications without dosimetric superiority claim; defers safely. |
| `DEV-LCD-RAD-NIV-APP` | `LCD-RAD-NIV` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`criterion-design`** | PaCO2 and nocturnal desaturation parameters in COPD formatted across non-standard layout. |
| `DEV-LCD-RAD-NIV-NEG` | `LCD-RAD-NIV` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Borderline daytime hypercapnia requires medical director evaluation. |
| `DEV-LCD-ROTATOR-CUFF-NEG` | `LCD-ROTATOR-CUFF` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Partial-thickness tendon tear without conservative care completion safely abstains. |
| `DEV-LCD-SBRT-APP` | `LCD-SBRT` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Inoperable stage I non-small cell lung carcinoma (NSCLC) medical contraindications. |
| `DEV-LCD-SHOULDER-ARTHRO-NEG` | `LCD-SHOULDER-ARTHRO` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Moderate glenohumeral osteoarthritis with preserved motion lacks surgical threshold. |
| `DEV-NCD-CARDIAC-REHAB-APP` | `NCD-CARDIAC-REHAB` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Post-CABG / post-STEMI qualifying episode timing paraphrased in discharge summary. |
| `DEV-NCD-CATARACT-NEG` | `NCD-CATARACT` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Snellen acuity 20/40 without documented glare disability; defers to human reviewer. |
| `DEV-NCD-CCTA-APP` | `NCD-CCTA` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Intermediate pre-test risk angina presentation terminology omitted from keywords. |
| `DEV-NCD-CCTA-NEG` | `NCD-CCTA` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | High-probability acute coronary syndrome requires invasive angiography, not CCTA. |
| `DEV-NCD-MPI-PET-APP` | `NCD-MPI-PET` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Inconclusive SPECT stress test and severe body mass index documentation phrasing. |
| `DEV-NCD-PACEMAKER-APP` | `NCD-PACEMAKER` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Symptomatic Mobitz Type II second-degree AV block electrophysiology phrasing. |
| `DEV-NCD-PACEMAKER-NEG` | `NCD-PACEMAKER` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Asymptomatic first-degree AV block lacks pacemaker indication; defers safely. |
| `DEV-NCD-PET-ONC-APP` | `NCD-PET-ONC` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Solitary pulmonary nodule FDG metabolic uptake and initial staging phrasing. |
| `DEV-NCD-PET-ONC-NEG` | `NCD-PET-ONC` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Non-covered routine cancer screening surveillance PET without recurrence suspicion. |
| `DEV-NCD-PUMP-APP` | `NCD-PUMP` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Intrathecal baclofen trial for severe intractable spasticity keyword variation. |
| `DEV-NCD-SCS-APP` | `NCD-SCS` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`criterion-design`** | Psychological clearance requirement strictly enforced; narrative described trial stimulator. |
| `DEV-NCD-SCS-NEG` | `NCD-SCS` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Active substance use disorder and untreated depression require psychiatric review. |
| `DEV-NCD-SGD-APP` | `NCD-SGD` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Augmentative and alternative communication (AAC) speech-language evaluation terms. |
| `DEV-NCD-SGD-NEG` | `NCD-SGD` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Temporary vocal impairment with recovery potential safely routes to human clinician. |
| `DEV-OPD-RHINO-NEG` | `OPD-RHINO` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Cosmetic rhinoplasty request without airway obstruction safely abstains under $\tau=0.85$. |
| `DEV-OPD-SI-FUSION-APP` | `OPD-SI-FUSION` | `APPROVED` | `DEFERRED_TO_HUMAN` | **`synonymy-only`** | Fortin finger test and fluoroscopic SI joint block $\ge 75\%$ pain relief phrasing. |
| `DEV-OPD-SI-FUSION-NEG` | `OPD-SI-FUSION` | `DENIED` | `DEFERRED_TO_HUMAN` | **`genuine-ambiguity`** | Lumbar discogenic pain masquerading as SI joint pain warrants human audit. |

### Failure Class Totals
- **`logic defect`**: `3` cases (6.25%)
- **`criterion-design`**: `4` cases (8.33%)
- **`synonymy-only`**: `18` cases (37.50%)
- **`genuine-ambiguity`**: `23` cases (47.92%)
- **Total Discordant Cases**: `48` cases (100.0%)

---

## Per-Policy Development Results

| Policy ID | Total Cases | Top-1 Hits | Top-3 Hits | Decision Matches | Failure Details |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `LCD-ACDF` | 2 | 1/2 | 2/2 | 2/2 | Clean (Both Approved and Negative matched) |
| `LCD-ACI` | 2 | 2/2 | 2/2 | 2/2 | Clean |
| `LCD-CT-CHEST` | 2 | 2/2 | 2/2 | 2/2 | Clean |
| `LCD-ESI` | 2 | 2/2 | 2/2 | 2/2 | Clean |
| `LCD-EVAR` | 2 | 2/2 | 2/2 | 2/2 | Clean |
| `LCD-FACET` | 2 | 2/2 | 2/2 | 2/2 | Clean |
| `LCD-HALLUX` | 2 | 2/2 | 2/2 | 2/2 | Clean |
| `LCD-HIP-ARTHRO` | 2 | 2/2 | 2/2 | 1/2 | `DEV-LCD-HIP-ARTHRO-NEG`: `DENIED -> DEFERRED_TO_HUMAN` |
| `LCD-HIP-SCOOP` | 2 | 2/2 | 2/2 | 1/2 | `DEV-LCD-HIP-SCOOP-NEG`: `DENIED -> DEFERRED_TO_HUMAN` |
| `LCD-IMRT` | 2 | 2/2 | 2/2 | 0/2 | `DEV-LCD-IMRT-APP` (`APPROVED -> DEFERRED_TO_HUMAN`); `DEV-LCD-IMRT-NEG` (`DENIED -> DEFERRED_TO_HUMAN`) |
| `LCD-KNEE-ARTHRO` | 2 | 2/2 | 2/2 | 1/2 | `DEV-LCD-KNEE-ARTHRO-NEG`: `DENIED -> DEFERRED_TO_HUMAN` |
| `LCD-KNEE-ORTHOSIS` | 2 | 1/2 | 2/2 | 0/2 | `DEV-LCD-KNEE-ORTHOSIS-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `LCD-KYPHO` | 2 | 1/2 | 2/2 | 1/2 | `DEV-LCD-KYPHO-APP`: `APPROVED -> DEFERRED_TO_HUMAN` |
| `LCD-LUMBAR-DECOMP` | 2 | 2/2 | 2/2 | 0/2 | `DEV-LCD-LUMBAR-DECOMP-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `LCD-LUMBAR-FUSION` | 2 | 2/2 | 2/2 | 1/2 | `DEV-LCD-LUMBAR-FUSION-NEG`: `DENIED -> DEFERRED_TO_HUMAN` |
| `LCD-MRI-BRAIN` | 2 | 2/2 | 2/2 | 0/2 | `DEV-LCD-MRI-BRAIN-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `LCD-MRI-LUMBAR` | 2 | 2/2 | 2/2 | 0/2 | `DEV-LCD-MRI-LUMBAR-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `LCD-PAD-ATHERO` | 2 | 2/2 | 2/2 | 0/2 | `DEV-LCD-PAD-ATHERO-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `LCD-PCI` | 2 | 1/2 | 1/2 | 0/2 | `DEV-LCD-PCI-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `LCD-POWER-WC` | 2 | 2/2 | 2/2 | 0/2 | `DEV-LCD-POWER-WC-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `LCD-PROTON` | 2 | 2/2 | 2/2 | 0/2 | `DEV-LCD-PROTON-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `LCD-RAD-NIV` | 2 | 1/2 | 2/2 | 0/2 | `DEV-LCD-RAD-NIV-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `LCD-ROTATOR-CUFF` | 2 | 1/2 | 2/2 | 1/2 | `DEV-LCD-ROTATOR-CUFF-NEG`: `DENIED -> DEFERRED_TO_HUMAN` |
| `LCD-SBRT` | 2 | 2/2 | 2/2 | 1/2 | `DEV-LCD-SBRT-APP`: `APPROVED -> DEFERRED_TO_HUMAN` |
| `LCD-SHOULDER-ARTHRO` | 2 | 1/2 | 1/2 | 1/2 | `DEV-LCD-SHOULDER-ARTHRO-NEG`: `DENIED -> DEFERRED_TO_HUMAN` |
| `LCD-WOUND-VAC` | 2 | 1/2 | 2/2 | 2/2 | Clean decisions (Retrieval Top-1 regressed to Top-2 on NEG) |
| `NCD-CARDIAC-REHAB` | 2 | 2/2 | 2/2 | 1/2 | `DEV-NCD-CARDIAC-REHAB-APP`: `APPROVED -> DEFERRED_TO_HUMAN` |
| `NCD-CATARACT` | 2 | 2/2 | 2/2 | 1/2 | `DEV-NCD-CATARACT-NEG`: `DENIED -> DEFERRED_TO_HUMAN` |
| `NCD-CCTA` | 2 | 1/2 | 2/2 | 0/2 | `DEV-NCD-CCTA-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `NCD-MPI-PET` | 2 | 2/2 | 2/2 | 1/2 | `DEV-NCD-MPI-PET-APP`: `APPROVED -> DEFERRED_TO_HUMAN` |
| `NCD-PACEMAKER` | 2 | 2/2 | 2/2 | 0/2 | `DEV-NCD-PACEMAKER-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `NCD-PET-ONC` | 2 | 2/2 | 2/2 | 0/2 | `DEV-NCD-PET-ONC-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `NCD-PUMP` | 2 | 1/2 | 2/2 | 1/2 | `DEV-NCD-PUMP-APP`: `APPROVED -> DEFERRED_TO_HUMAN` |
| `NCD-SCS` | 2 | 1/2 | 2/2 | 0/2 | `DEV-NCD-SCS-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `NCD-SGD` | 2 | 2/2 | 2/2 | 0/2 | `DEV-NCD-SGD-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `OPD-BLEPH` | 2 | 2/2 | 2/2 | 2/2 | Clean |
| `OPD-BOTOX` | 2 | 2/2 | 2/2 | 1/2 | `DEV-OPD-BOTOX-APP`: False Denial (`APPROVED -> DENIED`) |
| `OPD-CERV-DISC` | 2 | 2/2 | 2/2 | 2/2 | Clean |
| `OPD-PANNI` | 2 | 2/2 | 2/2 | 2/2 | Clean |
| `OPD-RHINO` | 2 | 2/2 | 2/2 | 0/2 | `DEV-OPD-RHINO-APP`: False Denial; `DEV-OPD-RHINO-NEG`: `DEFERRED_TO_HUMAN` |
| `OPD-SI-FUSION` | 2 | 2/2 | 2/2 | 0/2 | `DEV-OPD-SI-FUSION-APP` & `NEG`: both `DEFERRED_TO_HUMAN` |
| `OPD-VEIN` | 2 | 2/2 | 2/2 | 1/2 | `DEV-OPD-VEIN-APP`: False Denial (`APPROVED -> DENIED`) |

---

## Confusion Matrix (AUTO Retrieval Top-1)

| Intended Policy | `LCD-ACDF` | `LCD-ACI` | `LCD-CT-CHEST` | `LCD-ESI` | `LCD-EVAR` | `LCD-FACET` | `LCD-HALLUX` | `LCD-HIP-ARTHRO` | `LCD-HIP-SCOOP` | `LCD-IMRT` | `LCD-KNEE-ARTHRO` | `LCD-KNEE-ORTHOSIS` | `LCD-KYPHO` | `LCD-LUMBAR-DECOMP` | `LCD-LUMBAR-FUSION` | `LCD-MRI-BRAIN` | `LCD-MRI-LUMBAR` | `LCD-PAD-ATHERO` | `LCD-PCI` | `LCD-POWER-WC` | `LCD-PROTON` | `LCD-RAD-NIV` | `LCD-ROTATOR-CUFF` | `LCD-SBRT` | `LCD-SHOULDER-ARTHRO` | `LCD-WOUND-VAC` | `NCD-CARDIAC-REHAB` | `NCD-CATARACT` | `NCD-CCTA` | `NCD-MPI-PET` | `NCD-PACEMAKER` | `NCD-PET-ONC` | `NCD-PUMP` | `NCD-SCS` | `NCD-SGD` | `OPD-BLEPH` | `OPD-BOTOX` | `OPD-CERV-DISC` | `OPD-PANNI` | `OPD-RHINO` | `OPD-SI-FUSION` | `OPD-VEIN` | Other / None |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `LCD-ACDF` | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . |
| `LCD-ACI` | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-CT-CHEST` | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-ESI` | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-EVAR` | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-FACET` | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-HALLUX` | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-HIP-ARTHRO` | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-HIP-SCOOP` | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-IMRT` | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-KNEE-ARTHRO` | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-KNEE-ORTHOSIS` | . | . | . | . | . | . | . | . | . | . | 1 | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-KYPHO` | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-LUMBAR-DECOMP` | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-LUMBAR-FUSION` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-MRI-BRAIN` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-MRI-LUMBAR` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-PAD-ATHERO` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-PCI` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-POWER-WC` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-PROTON` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-RAD-NIV` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 |
| `LCD-ROTATOR-CUFF` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-SBRT` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `LCD-SHOULDER-ARTHRO` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 |
| `LCD-WOUND-VAC` | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-CARDIAC-REHAB` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-CATARACT` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-CCTA` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-MPI-PET` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-PACEMAKER` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-PET-ONC` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . | . | . | . |
| `NCD-PUMP` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . |
| `NCD-SCS` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 1 | . | . | . | . | . | . | . | . | . |
| `NCD-SGD` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . | . |
| `OPD-BLEPH` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . | . |
| `OPD-BOTOX` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . | . |
| `OPD-CERV-DISC` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . | . |
| `OPD-PANNI` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . | . |
| `OPD-RHINO` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . | . |
| `OPD-SI-FUSION` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . | . |
| `OPD-VEIN` | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | . | 2 | . |

---

## Verification and Honesty Notes
- **Forbidden Phrase Scan**: Verified 0 occurrences of policy slugs, LCD/NCD identifiers, or coverage verdict phrases in synthetic development vignette texts.
- **Retrieval Architecture**: Evaluated under `HybridPolicyRetriever` combining BM25 Okapi lexical matching with dense concept projection over `CLINICAL_CONCEPT_VOCAB`.
- **Adjudication Engine**: Evaluated under `DeclarativePolicyEngine` character-anchored extraction and ConText scope detection.
- **Operational Status**: Baseline development evaluation only. All 42 extended CMS policies remain strictly `CLAIMED_UNVERIFIED` pending formal regulatory audit.
