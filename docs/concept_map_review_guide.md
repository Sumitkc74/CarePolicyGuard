# ConceptMap Candidate Entry Review Mechanism & Governance Guide

**Provenance**: CarePolicyGuard Medical Governance and Audit Infrastructure  
**Governing Rule**: Semantic equivalence is understanding, and the system must do it. Genuine ambiguity is a deferral, and the system must not guess it.  
**Auditable Queue File**: `app/data/concept_map/draft_concept_entries.json`  

---

## 1. Overview and Core Governance Separation

The `ConceptMap` serves as the deterministic verifier for LLM synonymy proposals under Gate C. In accordance with Medicare compliance and clinical safety mandates:
1. **Automated Agents Cannot Self-Approve**: Local LLMs (such as `qwen2.5:3b`) act exclusively as *curator's assistants* to draft candidate entries into `PENDING_HUMAN_REVIEW` status.
2. **Human Clinical Authority**: An entry can only transition from `PENDING_HUMAN_REVIEW` to `ACCEPTED` through an explicit, auditable decision recorded by a licensed medical director or authorized human clinical reviewer.
3. **Committed Map Isolation**: The production `ConceptMap` in `app/core/concept_map.py` remains immutable until human-reviewed entries are formally merged.

---

## 2. CLI Tool Usage (`scripts/review_concept_queue.py`)

A minimal, terminal-based review CLI allows clinicians to inspect pending entries, examine verbatim policy grounding, verify governing-rule determinations, and record binding review decisions.

### Listing Pending Entries
```bash
# List all pending entries across all extended policies
python scripts/review_concept_queue.py --list --status PENDING_HUMAN_REVIEW

# Filter by a specific policy (e.g. LCD-MRI-BRAIN or LCD-RAD-NIV)
python scripts/review_concept_queue.py --list --policy LCD-MRI-BRAIN

# Filter by governing-rule flag (e.g. view only flagged ambiguities)
python scripts/review_concept_queue.py --list --flag NEEDS_HUMAN_JUDGMENT
```

### Viewing Queue Summary Metrics
```bash
python scripts/review_concept_queue.py --summary
```

### Recording an Auditable Review Decision
Clinicians review the entry's `grounding_quote`, verify that accepted terms are true synonyms rather than coverage substitutions, and record their verdict:

```bash
# Accept an entry (e.g., verifying objective focal neurological signs)
python scripts/review_concept_queue.py --review DRAFT-CONCEPT-MRI-BRAIN-MRIB-01 --decision ACCEPT --reviewer "Dr. Sarah Chen, MD" --notes "Verified that cranial neuropathy, hemiparesis, and facial numbness represent objective focal neurological signs directly grounded in LCD criteria."

# Reject an entry (e.g., rejecting an ungrounded or ambiguous substitution)
python scripts/review_concept_queue.py --review DRAFT-CONCEPT-IMRT-IMRT-01 --decision REJECT --reviewer "Dr. Robert Evans, MD" --notes "Rejected: Rectal dose sparing cannot substitute for critical neural structure proximity under CRIT-IMRT-01; must be evaluated under dosimetric criteria CRIT-IMRT-02."
```

---

## 3. Mandatory Reviewer Guardrails

1. **Agent Self-Approval Lockout**:
   The review mechanism explicitly inspects the `--reviewer` identifier. If any automated agent, system process, or bot identifier is supplied (`agent`, `llm`, `antigravity`, `bot`, `assistant`, `system`), the CLI aborts with a security violation.
2. **Grounding Verification**:
   The reviewer must confirm that `grounding_quote` is a verbatim slice of the published Medicare policy. Entries lacking textual grounding must be rejected.
3. **Governing Rule Boundary**:
   - **Approve (Wording Equivalence)**: Synonyms, histological subtypes (e.g., adenocarcinoma for carcinoma), and standard medical abbreviations for the *same* clinical concept.
   - **Reject / Defer (Coverage Judgment)**: Attempting to substitute a different organ, a different diagnostic test, or a clinical trade-off (e.g., oxygen saturation for PaCO2, or anatomical stenosis for FFR).
