# Route B Discrepancy Adjudication Log Template

This document provides the standard adjudication template for resolving disagreements identified during Route B dual-annotation of held-out test sets.

> [!IMPORTANT]
> **Labelling Rule Reminder**:
> All results certified through Route B must be cited as:
> **"Independently dual-annotated, non-clinician validated"** (never *"clinician-validated"*).

---

## 1. Adjudication Protocol

1. **Third-Party Adjudicator**: A third independent reviewer with clinical coding or medical informatics expertise adjudicates every discrepancy where Annotator 1 and Annotator 2 disagree.
2. **Statutory Standard**: Adjudication must be grounded strictly in the **verbatim text of the applicable CMS NCD or LCD policy**, not personal clinical impression or unwritten hospital practice.
3. **Disputed Disposition**: If a case presents genuine statutory ambiguity that cannot be resolved definitively by verbatim CMS criteria, the case **MUST be marked as `DISPUTED`** and permanently excluded from automated benchmark scoring.

---

## 2. Adjudication Summary Sheet

| Case ID | Governing Policy | Annotator 1 Decision | Annotator 2 Decision | Final Adjudicated Label | Adjudication Status | Adjudicating Reviewer |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `CASE-DISC-01` | *[e.g. NCD-20.4]* | `DENIED` | `DEFERRED_TO_HUMAN` | `DEFERRED_TO_HUMAN` | **RESOLVED** | *Reviewer Name / ID* |
| `CASE-DISC-02` | *[e.g. LCD-L33829]* | `APPROVED` | `DENIED` | `DISPUTED` | **EXCLUDED (DISPUTED)** | *Reviewer Name / ID* |

---

## 3. Detailed Case Adjudication Records

### Case Record: `[CASE-ID-PLACEHOLDER]`
- **Governing Policy**: `[POLICY-ID-PLACEHOLDER]` (Verbatim Title)
- **Annotator 1 Decision**: `[APPROVED | DENIED | DEFERRED_TO_HUMAN]`
  - *Annotator 1 Rationale*: `[Summary of Annotator 1 rationale]`
- **Annotator 2 Decision**: `[APPROVED | DENIED | DEFERRED_TO_HUMAN]`
  - *Annotator 2 Rationale*: `[Summary of Annotator 2 rationale]`
- **Statutory Conflict Analysis**:
  - Relevant CMS policy section and verbatim criteria citation: `"[Insert verbatim policy criteria quote]"`
  - Clinical chart evidence: `"[Insert exact verbatim span from chart]"`
- **Final Determination**: `[APPROVED | DENIED | DEFERRED_TO_HUMAN | DISPUTED]`
- **Adjudication Rationale**:
  - Detailed explanation of how the verbatim policy criteria resolve the dispute between the annotators, or why the case is classified as permanently disputed.
- **Adjudicator Signature & Date**: `[Name / ID], [YYYY-MM-DD]`

