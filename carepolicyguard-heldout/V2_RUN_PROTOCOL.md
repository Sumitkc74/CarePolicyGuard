# CarePolicyGuard Held-Out Test Set v2: Run Protocol and Validation Standard

This protocol defines the strict governance, independent validation routes, and run-once execution procedures for the **v2 Held-Out Evaluation Set**.

---

## 1. Principles of Held-Out Evaluation

A valid held-out benchmark measures the real generalization of the autonomous clinical prior authorization system to unseen clinical notes, unmodeled stylistic variations, documentation noise, and novel clinical edge cases.

To preserve scientific and regulatory integrity:
1. **Sealed Status**: The v2 held-out set must remain strictly sealed and uninspected during all algorithm development, rule tuning, prompt engineering, and bug fixing.
2. **Zero Contamination**: No code, regex, deterministic rules, few-shot prompts, or fine-tuning datasets may be updated or modified based on inspection of v2 cases.
3. **Run-Once Standard**: The evaluation is executed exactly once across all target modes. Retries, parameter tuning, or code revisions after viewing v2 evaluation results invalidate the evaluation as a held-out test.
4. **Permanent Record**: All raw execution logs, individual case predictions, and confidence distributions must be committed immutably to version control.

---

## 2. Independent Gold Label Validation Routes

Before executing the v2 evaluation, gold determination labels (`APPROVED`, `DENIED`, `DEFERRED_TO_HUMAN`) and criterion-level ground truths must be independently certified under one of two validation routes.

### Route A: External Clinician Certification (Primary Standard)
- **Reviewer Profile**: Licensed medical doctor (MD/DO) board-certified in Internal Medicine, Cardiology, Pulmonology, Orthopedic Surgery, or a credentialed Senior Clinical Coding Specialist (CPC / CDIP / CCS).
- **Independence**: The clinician must have had zero involvement in the authoring of the CarePolicyGuard codebase, heuristics, or prompt templates.
- **Process**:
  1. The clinician receives the clinical vignette text, patient demographics, target procedure code, primary diagnosis code, and the verbatim CMS LCD/NCD policy text.
  2. The clinician independently records:
     - Policy Determination: `APPROVED`, `DENIED`, or `DEFERRED_TO_HUMAN`
     - Per-criterion assessment: `MET`, `NOT_MET`, or `INSUFFICIENT_EVIDENCE`
     - Primary rationale and specific excerpt/span supporting the determination
  3. Sign-off: The clinician signs and dates the validation sheet certifying that each gold label represents clinically defensible prior authorization practice under applicable CMS coverage policies.

### Route B: Blind Dual Annotation with Inter-Rater Reliability (Secondary Standard)
- **Reviewer Profile**: Two independent trained biomedical informatics annotators.
- **Process**:
  1. Both annotators receive identical blinded vignettes without access to system predictions, baseline runs, or each other's scoring.
  2. Each annotator independently labels determination (`APPROVED`, `DENIED`, `DEFERRED_TO_HUMAN`) and criterion states.
  3. **Inter-Rater Reliability**: Calculate Cohen's Kappa ($\kappa$) across both annotators:
     $$\kappa = \frac{p_o - p_e}{1 - p_e}$$
     - Target requirement: $\kappa \ge 0.85$ (near-perfect agreement).
     - If $\kappa < 0.85$, ambiguous cases must be flagged and re-reviewed against verbatim CMS criteria.
  4. Discrepancies between Annotator 1 and Annotator 2 must be adjudicated by a third independent adjudicator before sealing the dataset.

---

## 3. Run-Once Execution Procedure

When gold labels have been certified under Route A or Route B:

```
Step 1: Check Working Tree
Ensure git status is clean on the target release commit.
Record HEAD commit SHA in evaluation metadata.

Step 2: Clear Volatile Caches
Clear in-memory and disk caches to guarantee fresh evaluation:
app.core.cache.policy_cache.clear()

Step 3: Execute Single-Pass Evaluation
Execute evaluation harness across all candidate configurations:
- Config A: Local LLM Baseline (Ollama frozen model id)
- Config B: Deterministic Symbolic Engine
- Config C: Explicit State Machine Engine
- Config D: Declarative Policy-as-Data Engine

Step 4: Generate Sealed Run Artifacts
Write timestamped raw outputs:
- carepolicyguard-heldout/v2_results_raw.json (unaltered model outputs)
- carepolicyguard-heldout/V2_EVALUATION_REPORT.md (rendered report)

Step 5: Immediate Immutable Commit
Commit raw run artifacts directly to git without code changes.
```

---

## 4. Reporting Template and Required Safety Metrics

Every held-out evaluation report must compute and report the four mandatory safety numbers alongside calibration and latency statistics:

### Mandatory Four-Metric Safety Summary

| Configuration / Mode | False Approvals (FA) | False Denials (FD) | Deferral Rate | Diagnostic Accuracy | Sample Size ($n$) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Config A: Local LLM Baseline** | *[count / %]* | *[count / %]* | *[count / %]* | *[count / %]* | $n = \dots$ |
| **Config B: Deterministic Mode** | *[count / %]* | *[count / %]* | *[count / %]* | *[count / %]* | $n = \dots$ |
| **Config C: State Machine Mode** | *[count / %]* | *[count / %]* | *[count / %]* | *[count / %]* | $n = \dots$ |
| **Config D: Declarative Mode** | *[count / %]* | *[count / %]* | *[count / %]* | *[count / %]* | $n = \dots$ |

### Metric Definitions
- **False Approval (FA)**: System predicted `APPROVED` when gold is `DENIED` or `DEFERRED_TO_HUMAN`. **Safety Invariant: Must strictly be 0 (0.0%).**
- **False Denial (FD)**: System predicted `DENIED` when gold is `APPROVED` or `DEFERRED_TO_HUMAN`. Evaluates unwarranted autonomous denials where clinical documentation was missing or qualifying.
- **Deferral Rate**: Percentage of cases routed to human clinical reviewer (`DEFERRED_TO_HUMAN`). Reflects operational burden vs autonomous throughput.
- **Diagnostic Accuracy**: Overall exact match against certified gold determinations across all three classes.

### Additional Empirical Measurements
- **Expected Calibration Error (ECE)**:
  $$\text{ECE} = \sum_{m=1}^M \frac{|B_m|}{N} \left| \text{acc}(B_m) - \text{conf}(B_m) \right|$$
  *Must explicitly report covered subset sample size $n$*.
- **Faithfulness Rate**: Percentage of citations verified via exact character-slice matching against the raw EHR string.
- **Latency**: Mean and p95 end-to-end latency in milliseconds.

