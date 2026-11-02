# Route B Independent Second Annotator Instructions: Prior Authorization Validation

This document contains standard operating instructions for the independent second annotator performing blind dual annotation under **Route B (Independent Dual-Annotation Protocol)** for CarePolicyGuard held-out test sets.

---

## 1. Mandatory Regulatory Labelling Standard

> [!IMPORTANT]
> **Strict Labelling Rule**:
> Evaluations conducted under this protocol must be formally and consistently described in all scientific reports, benchmark tables, and regulatory submissions as:
> **"Independently dual-annotated, non-clinician validated"**
>
> They must **NEVER** be cited, described, or labelled as *"clinician-validated"*. Clinician validation is strictly reserved for Route A (certification by an independent board-certified physician [MD/DO] or credentialed senior clinical coder [CPC/CDIP/CCS]).

---

## 2. Independence and Blinding Requirements

To ensure zero cognitive bias and audit validity:
1. **Double Blinding**: The annotator must **never** be provided with CarePolicyGuard system predictions, baseline model decisions, agent extraction traces, or existing primary gold labels.
2. **Materials Provided**: The annotator receives ONLY:
   - The unannotated clinical case text (de-identified clinical progress note).
   - The verbatim CMS Medicare coverage policy text (National Coverage Determination [NCD] or Local Coverage Determination [LCD]).
   - The structured criteria checklist for the target policy.
3. **No Collaboration**: Annotators must evaluate all cases independently without discussing case details, interpretations, or borderline presentations with other annotators prior to formal adjudication.

---

## 3. Adjudication Guidelines

For each case, the annotator must record:

### A. Case Determination (`decision`)
- `APPROVED`: The clinical documentation meets ALL mandatory inclusion criteria, satisfies all statutory waiting periods/conservative therapy durations, and contains NO disqualifying exclusions.
- `DENIED`: The clinical documentation explicitly establishes that an exclusion condition is present (e.g. active infection, cardiogenic shock, life expectancy < 1 year) OR a mandatory inclusion threshold is definitively failed (e.g. LVEF > 35%, AHI < 5 events/hr with no symptoms).
- `DEFERRED_TO_HUMAN`: The clinical documentation is missing required quantitative measurements (e.g. qualitative aortic stenosis without AVA or gradient, missing treatment duration), documentation is ambiguous/conflicting, or vital clinical records are absent from the note.

### B. Per-Criterion Assessment (`per_criterion_assessments`)
For every criterion defined in the governing policy:
- `MET`: Documentation confirms the requirement is satisfied.
- `NOT_MET`: Documentation confirms the requirement is explicitly not met or negated.
- `INSUFFICIENT_EVIDENCE`: The note does not contain information to verify or refute this criterion.

### C. Supporting Evidence Spans (`supporting_evidence_spans`)
- Every positive or negative determination must cite an exact verbatim text quote copied directly from the clinical note.
- If a criterion is marked `INSUFFICIENT_EVIDENCE`, record `"None documented"`.

---

## 4. Submission & Quality Control Workflow

1. Record decisions in the provided [BLANK_ANNOTATION_SHEET.csv](file:///e:/Class/GitHub/CarePolicyGuard/carepolicyguard-heldout/validation_package/BLANK_ANNOTATION_SHEET.csv).
2. Execute the verification script:
   ```bash
   python compute_cohen_kappa.py --annotator1 primary_gold.json --annotator2 annotator2_submission.json
   ```
3. Target Inter-Rater Reliability:
   - **Cohen's Kappa Target**: $\kappa \ge 0.85$ (near-perfect agreement).
   - If $\kappa < 0.85$, all discrepant cases must be formally reviewed under [ADJUDICATION_LOG_TEMPLATE.md](file:///e:/Class/GitHub/CarePolicyGuard/carepolicyguard-heldout/validation_package/ADJUDICATION_LOG_TEMPLATE.md) by a third independent adjudicator against verbatim CMS statutory text.
   - Any case where disagreement cannot be reconciled with clear statutory evidence must remain recorded as `"disputed"` and excluded from automated authorization benchmarks.

