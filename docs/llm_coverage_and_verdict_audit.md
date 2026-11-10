# Task 1(c) Coverage Audit & Forensic Verdict

## 1. Summary of LLM Telemetry (84 Dev Vignettes / 126 Calls)

- **Total LLM Calls**: `126`
- **Gate A Rejections (Verbatim Extraction Failure)**: `79` (62.7%)
- **Gate B Rejections (Negation / Family History)**: `2` (1.6%)
- **Gate C Rejections (Unmapped Concept Whitelist Veto)**: `43` (34.1%)
- **Proposals Accepted**: `2` (1.6%)
- **Decision Changes Produced**: `0`

## 2. Case-by-Case Coverage Analysis

### (a) The 43 Gate C Map Rejections
All 43 proposals passed Gate A (exact note quote) and Gate B (no negation), but proposed clinical concepts from extended policies outside the 12 curated concepts in `ConceptMap` (e.g., `LCD-IMRT`, `LCD-KYPHO`, `LCD-KNEE-ORTHOSIS`, `LCD-VARICOSE-VEINS`). Because Gate C enforces human-vetted concept mapping, unmapped concepts fail with `NO_CONCEPT_MAP_ENTRY` and safely route to human review. In none of these 43 cases did the system make an unauthorized coverage expansion.

### (b) The 2 Accepted Proposals
Both proposals mapped to `CONCEPT-CONSERVATIVE-CARE-FAILURE`. In both cases, the deterministic engine had already matched the criteria using literal policy keywords (`physical therapy`, `failed`), rendering the LLM proposals **100% redundant** with the deterministic engine.

## 3. One-Paragraph Forensic Verdict

> Across all 84 synthetic development vignettes (126 LLM calls, 3B parameter model), the gated LLM proposal step produced exactly 2 accepted proposals and 0 net adjudication decision changes (concordance remained 39/84, 46.4%). This outcome is explained by a combination of two structural factors: (1) Prompt & Model Size: small 3B models fail verbatim extraction on 33.3% to 51.9% of calls (Gate A rejections), though explicit verbatim instructions with worked examples improve extraction fidelity by +18.5% (Gate A pass rate rising from 48.1% to 66.7%), while larger 14B models exceed the statutory latency budget (122.06s vs 30.0s per case, a 306.9% overrun); and (2) Coverage & Closed-World Gate C: all 43 non-paraphrased proposals were vetoed by Gate C because the extended policies' specialized concepts were absent from the 12 curated concepts in ConceptMap (returning NO_CONCEPT_MAP_ENTRY), while the 2 accepted proposals mapped to CONCEPT-CONSERVATIVE-CARE-FAILURE where the deterministic engine had already matched the evidence via literal keywords. For the LLM to add genuine decision-improving value beyond its role as a redundant safety net, two prerequisites must be met: the human-curated ConceptMap whitelist must be expanded to cover the extended policies' distinct concept spaces, and faster quantized inference or prompt caching must bring higher-capacity models within the statutory 30-second budget.
