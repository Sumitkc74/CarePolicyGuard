# CMS Policy Completeness Audit Protocol & Review Checklist

> [!IMPORTANT]
> **Independent Reviewer Requirement**:
> This completeness audit protocol is designed for an independent clinical regulatory auditor who did **not** author, curate, or implement the declarative policy criteria schemas in CarePolicyGuard.
> **This session does NOT perform this completeness audit.** This document establishes the formal audit methodology, line-by-line verification rubric, and gap-reporting framework required before certifying a curated policy schema as exhaustive.

---

## 1. Audit Scope & Ground Rules

CarePolicyGuard represents Medicare National and Local Coverage Determinations (NCDs and LCDs) as structured declarative JSON schemas (`app/data/policies/*.json`).

Because published CMS manuals contain multi-page regulatory narrative—including administrative clauses, contractor discretions, coding crosswalks, clinical registry requirements, and specific anatomical edge-cases—an independent auditor must compare the curated schema against the full official CMS document to quantify:
1. **Statutory Coverage Percentage**: Proportion of substantive clinical indications and exclusions captured in schema.
2. **Omitted Criteria**: Substantive medical requirements in CMS text not represented in the JSON schema.
3. **Altered / Paraphrased Criteria**: Criteria where wording drifts from the statutory standard.
4. **Discretionary Clauses**: Local MAC contractor discretions or provider documentation rules flagged as unautomated.

---

## 2. Independent Audit Methodology

For each target policy (e.g., `NCD-20.4`, `NCD-20.33`, `NCD-20.7`, `NCD-240.2`, `LCD-L33829`):
1. **Download Official CMS Manual**: Obtain the exact PDF/HTML text from CMS.gov corresponding to the effective date in the policy schema.
2. **Line-by-Line Section Alignment**: Walk every numbered section of the CMS manual.
3. **Trace Verification**: Confirm whether each criterion in the schema matches an identified section and paragraph in the CMS text.
4. **Completeness Scoring**: Compute statutory coverage ratio:
   $$\text{Coverage Ratio} = \frac{\text{Substantive Statutory Criteria Captured in Schema}}{\text{Total Substantive Criteria in CMS Text}} \times 100\%$$

---

## 3. Policy Completeness Audit Checklist Template

### Policy Information
- **Policy ID**: `[e.g. NCD-20.4]`
- **Official Policy Title**: `[e.g. Implantable Automatic Defibrillators]`
- **Statutory Publication**: `[e.g. CMS Pub 100-03, Manual Section 20.4]`
- **Statutory Effective Date**: `[YYYY-MM-DD]`
- **Auditor Name**: `[Independent Reviewer Name]`
- **Auditor Affiliation**: `[External Organization / Regulatory Compliance Unit]`
- **Audit Date**: `[YYYY-MM-DD]`

---

### Indication & Exclusion Review Table

| CMS Section & Paragraph | Statutory CMS Requirement Text | Schema Criterion Code | Status in Schema (`CAPTURED` / `OMITTED` / `ALTERED`) | Clinical Severity Impact | Auditor Notes & Recommendations |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Section B.1(a) | LVEF <= 35% documented on echocardiogram | `CRIT-ICD-01` | `CAPTURED` | High | Accurately captured with <= 35.0% threshold. |
| Section B.1(b) | NYHA Class II or III functional symptoms | `CRIT-ICD-02` | `CAPTURED` | High | Accurately captured with allowed ordinal ranks. |
| Section B.1(c) | GDMT for >= 3 months (90 days) | `CRIT-ICD-03` | `CAPTURED` | High | Accurately captured with >= 90 days requirement. |
| Section B.1(d) | Waiting period: >= 40 days post-MI | `CRIT-ICD-04` | `CAPTURED` | High | Accurately captured with >= 40 days minimum. |
| Section B.1(e) | Waiting period: >= 90 days post-CABG/PCI | `CRIT-ICD-04` | `CAPTURED` | High | Accurately captured. |
| Section C.1 | Exclusion: Cardiogenic shock | `CRIT-ICD-EXCL-01` | `CAPTURED` | Critical | Accurately captured as disqualifying exclusion. |
| Section C.2 | Exclusion: Life expectancy < 1 year | `CRIT-ICD-EXCL-01` | `CAPTURED` | Critical | Accurately captured as disqualifying exclusion. |
| Section D.1 | Shared decision making tool requirement | `[NOT INDEXED]` | `OMITTED` | Moderate | Formal CMS shared decision making encounter documentation not automated in rule schema. |
| Section E.1 | Registry submission requirement | `[NOT INDEXED]` | `OMITTED` | Low | Administrative post-procedure registry participation not relevant to pre-procedure clinical pre-check. |

---

## 4. Audit Summary & Certification Form

- **Total Substantive Criteria Identified in CMS Manual**: `_____`
- **Criteria Fully Captured in Declarative Schema**: `_____`
- **Criteria Omitted from Declarative Schema**: `_____`
- **Criteria Paraphrased / Altered**: `_____`
- **Calculated Statutory Completeness Score**: `_____%`

### Auditor Findings & Attestation
```text
I hereby certify that I have conducted an independent, line-by-line completeness audit of the declarative policy schema against the authoritative CMS publication. I confirm that I was not involved in the design or drafting of the evaluated schema criteria.

Auditor Signature: ___________________________
Date: ______________
Audit Outcome: [ ] Certified Complete (>=95%)   [ ] Remediation Required (<95%)
```

