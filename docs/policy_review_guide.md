# Policy Criteria Human Review Guide (Agent 5 Verification Workflow)

## 1. Overview & Purpose
This guide establishes the mandatory protocol for human clinical and policy reviewers evaluating Medicare Local Coverage Determination (LCD) and National Coverage Determination (NCD) policy criteria in CarePolicyGuard.

The policy verification workflow enforces strict separation of responsibilities:
- **Agent 5 (Policy Onboarding Agent)**: Performs automated mechanical extraction from official CMS Coverage API documents, runs verbatim whitespace-normalized excerpt matching, flags semantic ambiguities, and stages policies as `DRAFT` with all criteria set to `PENDING_HUMAN_REVIEW`.
- **Human Clinical / Policy Reviewer**: Conducts independent clinical judgment and provenance verification before any drafted criterion can become `ACCEPTED` or any policy can transition from `DRAFT` to `ACTIVE`.

---

## 2. Reviewer Verification Standards
When reviewing a candidate criterion via `python scripts/review_policy_queue.py --show <CRITERION_CODE>`, the human reviewer must evaluate:

1. **Statutory Fidelity**:
   - Does the criterion's `description` faithfully and accurately represent what the cited LCD or NCD document actually mandates?
   - Does the criterion distort, invert, over-generalize, or invent requirements not present in the statutory coverage document?
2. **Verbatim Excerpt Grounding**:
   - Is the `source_text_excerpt` an exact, verbatim quotation from the official CMS document text?
   - The CLI tool strictly prohibits `APPROVE` / `ACCEPT` decisions if the automated verbatim check is `FAIL` or `NO_DOCUMENT`.
3. **Ambiguity Assessment**:
   - Are terms clearly defined (e.g., specific quantitative thresholds, defined clinical timelines, recognized anatomical landmarks)?
   - If an indication requires subjective interpretation, has it been flagged for human adjudication?

---

## 3. Decision Definitions
The reviewer records an explicit decision using `python scripts/review_policy_queue.py --record <CRITERION_CODE> --decision <APPROVE|REJECT> --reviewer <NAME> --notes <RATIONALE>`:

- **`APPROVE` (or `ACCEPT`)**:
  - The criterion accurately reflects statutory CMS coverage policy.
  - The excerpt is verified verbatim (`PASS`).
  - Required non-empty reviewer notes document the clinical justification and confirming citation.
- **`REJECT`**:
  - The criterion description misinterprets policy requirements, cites mismatched or ungrounded evidence, or conflicts with medical consensus.
  - Required notes must articulate the specific defect or statutory divergence.

---

## 4. Strict Security & Anti-Sycophancy Governance
1. **Agent Self-Approval Prohibited**:
   - Automated agents, LLMs, and internal bots are strictly blocked from approving policy criteria.
   - The CLI tool screens the `--reviewer` identifier against forbidden keywords (`agent`, `llm`, `antigravity`, `bot`, `assistant`, `system`, `auto`) and terminates immediately upon detection.
2. **Audit Immutability**:
   - Every recorded decision permanently records the reviewer's identity, timestamp in UTC ISO format, and clinical rationale.
   - Overwriting an existing decision requires an explicit `--overwrite` flag accompanied by a comprehensive explanatory justification.
3. **Policy Activation Gate**:
   - A newly onboarded policy cannot be activated (`--activate-policy <POLICY_ID>`) until **100% of its criteria** (including all exclusions) have achieved `ACCEPTED` status in the verification queue.
   - Existing catalog policies (60 policies, 182 criteria) remain in grandfathered `ACTIVE` status to preserve baseline stability, while their provenance records remain transparently auditable in `app/data/policy_verification_records.json`.
