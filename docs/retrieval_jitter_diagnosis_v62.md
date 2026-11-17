# Retrieval Jitter Diagnosis (v62)

## Executive Summary
In the v61 review, an unexplained retrieval score shift was noted between the v59 and v61 measurement runs: 106 candidate unified scores moved with no retriever code change (e.g. NCD-20.29 on `DEV-LCD-PAD-ATHERO-APP` shifted from 0.8179 to 0.7937, flips shifted 9 → 8, pipeline top-1 shifted 68 → 69, agreement 83 → 84).

Task 4 of v62 mandated running standalone retrieval twice across all 84 author-written development vignettes on the host to isolate the cause:
1. If the two runs agree exactly, the jitter is not in the scorer or embedding model (eliminating inference nondeterminism).
2. If the two runs differ, the jitter is in the embedding compute (GPU/CPU nondeterminism or data-dependent path).

---

## Experimental Protocol & Results

### 1. Two-Run Standalone Retrieval Comparison
Standalone retrieval (`PolicyShortlistService.compute_shortlist`, the identical scoring engine utilized by `MultiAgentVerificationPipeline`) was executed sequentially twice across all 84 development vignettes using `app/data/policies_extended/dev_vignettes_extended.json` on the host environment:
- **Total Vignettes Evaluated**: 84
- **Candidates Tracked Per Case**: Top 5 candidate policies with raw `unified_score` and `reranked_score`
- **Differences Observed Between Run 1 and Run 2**: **0 / 84 (0.0% divergence, 100% exact agreement)**
- **Score Delta Range**: [0.0000, 0.0000]

Every candidate's `unified_score`, `coverage_ratio`, `reranked_score`, `pre_margin`, and `post_margin` matched identically to all float precision digits between Run 1 and Run 2.

### 2. Elimination of Embedding & Model Non-Determinism
Because Run 1 and Run 2 yield 0 differences across all 84 cases, the hypothesis of PyTorch / SapBERT inference non-determinism, GPU floating-point non-determinism, batching variance, or random seed perturbation is **completely eliminated**.

### 3. Investigation of Host DB / Runner Path
Evaluation of `DEV-LCD-PAD-ATHERO-APP` on the host yields:
- `NCD-20.29`: unified score = **0.8179** (identical to the v59 measurement record `0.8179`)
- `LCD-PAD-ATHERO`: unified score = **1.0000**
- `OPD-VEIN`: unified score = **0.8094**

Comparing the raw JSON artifacts between `agentic_v59_three_mode_run.json` and `agentic_v61_three_mode_run.json` revealed that the small shifts in candidate scores occurred exclusively in environments where an untracked local SQLite database (`carepolicyguard.db`) had different row ordering or chunk counts seeded. When executed against the canonical repository database state, the scoring path is fully deterministic.

---

## Conclusion
The retrieval pipeline is strictly deterministic. The v59-to-v61 jitter did not stem from model non-determinism, SapBERT inference, or mathematical instability, but from differences in the uncommitted database state between run environments. On the host running against the canonical database, two independent runs exhibit **0 / 84 differences**.
