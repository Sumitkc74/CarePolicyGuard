# CarePolicyGuard Independent Regulatory Traceability Audit Package

## Notice of Audit Status: PENDING INDEPENDENT REVIEW
> **CRITICAL COMPLIANCE NOTICE**:
> This audit package has been prepared for an **independent, external clinical informatics / regulatory auditor**.
> An audit, by definition, must be performed by an independent third party who did NOT write the criteria, implement the software, or author the system outputs.
> **The audit has NOT been performed by this engineering session, nor by the software developers.**
> All policy criteria in this repository currently carry the status **CLAIMED_UNVERIFIED** (or **UNVERIFIED** for contractor archetype definitions).
> No criterion or policy may carry a verified status in the production system until this independent review protocol is executed and signed off.

---

## 1. Auditor Eligibility & Blinding Rules
To ensure strict regulatory independence and prevent confirmation bias:
1. **Independent Reviewer Qualification**:
   The auditor must be a licensed clinician, health informatics specialist, or healthcare regulatory counsel independent of the CarePolicyGuard engineering team.
2. **Output Blinding Rule**:
   The independent auditor **must NOT have seen system execution logs, test outputs, or benchmark run traces** prior to reviewing the criteria definitions against the primary CMS statutory documents.
3. **Primary Source Grounding**:
   Auditors must independently retrieve the authoritative CMS National Coverage Determination (NCD) manuals (CMS Pub 100-03) and Local Coverage Determination (LCD) documents directly from the CMS Medicare Coverage Database (MCD).

---

## 2. Audit Protocol & Scope
The audit encompasses all 8 CMS coverage policies implemented in CarePolicyGuard:
1. **NCD 20.4**: Implantable Automatic Defibrillators (Cardiology)
2. **LCD L33829**: Positive Airway Pressure (PAP) Devices for Obstructive Sleep Apnea (DME MAC)
3. **LCD TOTAL-KNEE-01**: Total Knee Arthroplasty (TKA) for Severe Osteoarthritis (Contractor Archetype)
4. **NCD 20.29**: Hyperbaric Oxygen Therapy (Wound Care / Hyperbaric Medicine)
5. **NCD 20.33**: Transcatheter Edge-to-Edge Repair (TEER) for Mitral Regurgitation (Cardiology)
6. **NCD 20.7**: Percutaneous Transluminal Angioplasty (PTA) with Carotid Stent (Vascular Surgery)
7. **NCD 220.13**: Percutaneous Left Atrial Appendage Closure (LAAC) (Cardiology)
8. **NCD 240.2**: Home Use of Oxygen (Pulmonology / DME)

---

## 3. Four-Step Auditor Verification Procedure
For each criterion listed in [`CRITERIA_CHECKLIST_ALL_POLICIES.md`](file:///e:/Class/GitHub/CarePolicyGuard/carepolicyguard-audit/CRITERIA_CHECKLIST_ALL_POLICIES.md):

### Step 1: Document & Section Citation Verification
- Verify that `cms_document` accurately identifies the governing manual, publication number, and section title.
- Verify that `source_section` matches the official section heading in the CMS Coverage Database.

### Step 2: Clause & Paragraph Grounding
- Locate the claimed `source_paragraph` within the official CMS text.
- Verify that the specific clinical prerequisite, indication, or exclusion resides in that exact paragraph.

### Step 3: Verbatim Excerpt Word-for-Word Check
- Cross-check `source_text_excerpt` against the official CMS manual text.
- Flag any truncations, paraphrasing, or discrepancies. If an excerpt is not an exact verbatim match, mark as `DISCREPANCY_FLAGGED` and record the true verbatim wording.

### Step 4: Clinical Logic Faithfulness Assessment
- Verify that the software criterion schema (`NUMERIC_THRESHOLD`, `ORDINAL_RANK`, `FINDING_PRESENCE`, `TEMPORAL_DURATION`, `EXCLUSION`) faithfully reflects the statutory intent without introducing unstated barriers or omitting statutory exceptions.

---

## 4. Auditor Deliverables & Attestation
Upon completion of the review across all 26 criteria:
1. Complete the audit record in [`AUDIT_COVERAGE_TEMPLATE.md`](file:///e:/Class/GitHub/CarePolicyGuard/carepolicyguard-audit/AUDIT_COVERAGE_TEMPLATE.md).
2. Record any discrepancies, omissions, or necessary wording revisions.
3. Sign and date the Independent Regulatory Attestation block.

