# Empirical Trace and Decision Blocker Classification for 19 Synonymy Cases

## 1. Executive Summary & Measured Puzzle Resolution

In v28/v29 benchmarks, intermediate proposer telemetry showed clear improvements (span repair enabled 77 Gate A passes and 8 accepted proposals), yet end-to-end decisions remained strictly unchanged at **39/84 (46.4%)**, with only **1 of 19 synonymy cases resolving (`DEV-LCD-RAD-NIV-APP`)**.

This v30 diagnostic traced all 19 cases through the execution pipeline to isolate the exact blocking mechanism for every single case.

### Decision Blocker Breakdown Across the 18 Unresolved Cases

| Bucket | Count | Mechanism & Clinical Explanation |
| :--- | :---: | :--- |
| **(a) Multi-criterion block** | **1** | `DEV-LCD-SBRT-APP`: Proposal for `CRIT-SBRT-01` was accepted, but `CRIT-SBRT-02` (motion management) was unmet. Multiple criteria are required by policy. |
| **(b) Evidence not applied (wiring defect)** | **0 primary (1 compound)** | Found in `app/agents/pipeline.py`: accepted verified spans set `status=MET` but left `raw_confidence=0.50`, triggering weakest-link floor. **Fixed in v30 with regression test.** |
| **(c) Confidence block** | **0** | No case had all criteria MET with confidence lingering below $\tau=0.85$. |
| **(d) Other: Gate A Quote Mismatch** | **7** | LLM produced summarized phrases or altered acronyms/words ('PT/OT', 'in the absence of') resulting in `[0:0]` hallucinated offsets. |
| **(d) Other: Gate C Disjoint ConceptMap Entries** | **9** | v27 draft entries and v29 attested entries were registered as separate concept records with distinct canonical names, causing `verify_equivalence` to reject with `Terms belong to disjoint concepts`. |
| **(d) Other: Gate C Governing Rule Judgment** | **1** | `DEV-LCD-MRI-BRAIN-APP`: Focal motor deficit proposed for headache red flags flagged `NEEDS_HUMAN_JUDGMENT`. Correctly deferred. |

---

## 2. Detailed Case-by-Case Trace (All 19 Synonymy Cases)

| Vignette ID | Policy ID | Unmet Criteria | Primary Blocker | Detailed Findings |
| :--- | :--- | :--- | :--- | :--- |
| `DEV-LCD-IMRT-APP` | `LCD-IMRT` | `CRIT-IMRT-02` | `other_gate_c_disjoint_concepts` | ConceptMap check failed with NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts. Criterion term was registered in v27 draft while attested note phrase was registered in separate v29 entry without unified concept definition, causing verify_equivalence to fail. |
| `DEV-LCD-KNEE-ORTHOSIS-APP` | `LCD-KNEE-ORTHOSIS` | `CRIT-KORTH-01, CRIT-KORTH-02` | `other_gate_c_disjoint_concepts` | ConceptMap check failed with NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts. Criterion term was registered in v27 draft while attested note phrase was registered in separate v29 entry without unified concept definition, causing verify_equivalence to fail. |
| `DEV-LCD-KYPHO-APP` | `LCD-KYPHO` | `CRIT-KYPHO-01, CRIT-KYPHO-02` | `other_gate_a_quote_mismatch` | LLM produced paraphrased text, acronym variation, or summarized policy wording that could not be mapped to exact character offsets in EHR narrative ([0:0] offsets). Gate A exact slice check rejected proposal. |
| `DEV-LCD-LUMBAR-DECOMP-APP` | `LCD-LUMBAR-DECOMP` | `CRIT-LDEC-01` | `other_gate_c_disjoint_concepts` | ConceptMap check failed with NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts. Criterion term was registered in v27 draft while attested note phrase was registered in separate v29 entry without unified concept definition, causing verify_equivalence to fail. |
| `DEV-LCD-MRI-BRAIN-APP` | `LCD-MRI-BRAIN` | `CRIT-MRIB-02` | `other_gate_c_coverage_judgment` | Governing Rule enforcement: CRIT-MRIB-02 requires headache red flags. Proposed phrase 'progressive right upper extremity clumsiness...' is a focal motor symptom, not a headache synonym. Pre-audit flag 'NEEDS_HUMAN_JUDGMENT' correctly prevents automated approval of clinical substitution. |
| `DEV-LCD-MRI-LUMBAR-APP` | `LCD-MRI-LUMBAR` | `CRIT-MRIL-02` | `other_gate_a_quote_mismatch` | LLM produced paraphrased text, acronym variation, or summarized policy wording that could not be mapped to exact character offsets in EHR narrative ([0:0] offsets). Gate A exact slice check rejected proposal. |
| `DEV-LCD-PAD-ATHERO-APP` | `LCD-PAD-ATHERO` | `CRIT-PAD-01, CRIT-PAD-02` | `other_gate_a_quote_mismatch` | LLM produced paraphrased text, acronym variation, or summarized policy wording that could not be mapped to exact character offsets in EHR narrative ([0:0] offsets). Gate A exact slice check rejected proposal. |
| `DEV-LCD-POWER-WC-APP` | `LCD-POWER-WC` | `CRIT-PWC-02` | `other_gate_a_quote_mismatch` | LLM produced paraphrased text, acronym variation, or summarized policy wording that could not be mapped to exact character offsets in EHR narrative ([0:0] offsets). Gate A exact slice check rejected proposal. |
| `DEV-LCD-PROTON-APP` | `LCD-PROTON` | `CRIT-PBT-02` | `other_gate_c_disjoint_concepts` | ConceptMap check failed with NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts. Criterion term was registered in v27 draft while attested note phrase was registered in separate v29 entry without unified concept definition, causing verify_equivalence to fail. |
| `DEV-LCD-RAD-NIV-APP` | `LCD-RAD-NIV` | `None (All Met)` | `resolved_deterministic_expanded_map` | Both criteria (CRIT-NIV-01 and CRIT-NIV-02) satisfied deterministically by in-sample expanded ConceptMap. Adjudication succeeded with decision APPROVED. |
| `DEV-LCD-SBRT-APP` | `LCD-SBRT` | `CRIT-SBRT-01, CRIT-SBRT-02` | `multi_criterion_block_with_wiring_defect` | CRIT-SBRT-01 proposal was accepted by Gates A, B, C and cross-examination. However, CRIT-SBRT-02 was unmet (failed Gate C due to disjoint concept entry in map). In addition, criterion assessment raw_confidence wiring defect left CRIT-SBRT-01 at 0.50, triggering weakest-link floor. Even with confidence wiring fixed, CRIT-SBRT-02 remains unmet. |
| `DEV-NCD-CARDIAC-REHAB-APP` | `NCD-CARDIAC-REHAB` | `CRIT-CREH-01, CRIT-CREH-02` | `other_gate_c_disjoint_concepts` | ConceptMap check failed with NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts. Criterion term was registered in v27 draft while attested note phrase was registered in separate v29 entry without unified concept definition, causing verify_equivalence to fail. |
| `DEV-NCD-CCTA-APP` | `NCD-CCTA` | `CRIT-CCTA-01, CRIT-CCTA-02` | `other_gate_a_quote_mismatch` | LLM produced paraphrased text, acronym variation, or summarized policy wording that could not be mapped to exact character offsets in EHR narrative ([0:0] offsets). Gate A exact slice check rejected proposal. |
| `DEV-NCD-MPI-PET-APP` | `NCD-MPI-PET` | `CRIT-PETM-01` | `other_gate_c_disjoint_concepts` | ConceptMap check failed with NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts. Criterion term was registered in v27 draft while attested note phrase was registered in separate v29 entry without unified concept definition, causing verify_equivalence to fail. |
| `DEV-NCD-PACEMAKER-APP` | `NCD-PACEMAKER` | `CRIT-PACE-02` | `other_gate_c_disjoint_concepts` | ConceptMap check failed with NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts. Criterion term was registered in v27 draft while attested note phrase was registered in separate v29 entry without unified concept definition, causing verify_equivalence to fail. |
| `DEV-NCD-PET-ONC-APP` | `NCD-PET-ONC` | `CRIT-PTONC-01, CRIT-PTONC-02` | `other_gate_a_quote_mismatch` | LLM produced paraphrased text, acronym variation, or summarized policy wording that could not be mapped to exact character offsets in EHR narrative ([0:0] offsets). Gate A exact slice check rejected proposal. |
| `DEV-NCD-PUMP-APP` | `NCD-PUMP` | `CRIT-PUMP-01, CRIT-PUMP-02` | `other_gate_c_disjoint_concepts` | ConceptMap check failed with NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts. Criterion term was registered in v27 draft while attested note phrase was registered in separate v29 entry without unified concept definition, causing verify_equivalence to fail. |
| `DEV-NCD-SGD-APP` | `NCD-SGD` | `CRIT-SGD-02` | `other_gate_a_quote_mismatch` | LLM produced paraphrased text, acronym variation, or summarized policy wording that could not be mapped to exact character offsets in EHR narrative ([0:0] offsets). Gate A exact slice check rejected proposal. |
| `DEV-OPD-SI-FUSION-APP` | `OPD-SI-FUSION` | `CRIT-SI-01` | `other_gate_c_disjoint_concepts` | ConceptMap check failed with NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts. Criterion term was registered in v27 draft while attested note phrase was registered in separate v29 entry without unified concept definition, causing verify_equivalence to fail. |

---

## 3. Proposal Accounting Audit (Closed Equation)

By reporting `gate_c_vetoes` (Agent 3 cross-examination vetoes) separately, proposal accounting closes exactly in both arms:

$$\text{Gate A Passes} - \text{Gate B Rejections} - \text{Gate C Map Rejections} - \text{Gate C Vetoes} = \text{Proposals Accepted}$$

- **Arm A (Committed Map Only, Span Repair OFF)**:
  $$70 - 0 - 70 - 0 = 0 \quad (\text{Closed})$$
- **Arm B (In-Sample Expanded Map, Span Repair ON)**:
  $$77 - 0 - 68 - 1 = 8 \quad (\text{Closed})$$

---

## 4. Wiring Defect Diagnosis & Remediation

- **Defect**: In `app/agents/pipeline.py` (lines 192-200), when `verified_span` was returned from `run_synonymy_conversation`, `assessment.status` was updated to `MET`, but `assessment.raw_confidence` remained at the initial unverified value of `0.50`.
- **Consequence**: In `CalibratedAbstentionGate`, `weakest_link_floor = 0.65` was triggered, aborting approval even if all criteria had been verified.
- **Fix Applied**: Line 194 now assigns `assessment.raw_confidence = verified_span.confidence or 0.95`.
- **Verification**: Automated regression test `tests/test_wiring_accepted_proposal_confidence.py` created and passing.
