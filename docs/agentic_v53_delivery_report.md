# v53 — Delivery Report

**Session Scope**: BUILD session  
**Parent Head at Start**: `b9a639d90576bdcc48b83e1c6dbbc0e5da6c22f9`  
**Host**: Local Ollama runtime with `qwen2.5:3b`  
**Test Baseline**: 406 passed, 1 warning in 176.40s (100% green, 0 regressions)

---

## 1. Executive Summary

The v52 measurement session surfaced two major architectural bottlenecks in the agentic adjudication path:
1. **One-sided Debate**: When the clinical judge returned `NOT_MET` or `INSUFFICIENT_EVIDENCE`, the agentic debate had no mechanism for advocating for satisfaction. The system fell back to unprompted span iterations (59 redundant calls in v52) rather than purposeful clinical advocacy.
2. **Premature Budget Halts**: With judge calls averaging ~11.6s on CPU/local execution, 2 calls consumed ~23s, hitting the 30s per-case budget ceiling and causing Agent 2 to concede on `BudgetExhaustionHalt` before defense arguments could even be evaluated (as observed in `DEV-LCD-SBRT-APP` and `DEV-OPD-SI-FUSION-APP`).

Session **v53** resolves both root causes:
- **Agent 3 Advocacy**: Agent 3 is given an active advocacy role when an unsettled criterion receives `NOT_MET` or `INSUFFICIENT_EVIDENCE`. It scans the clinical narrative for overlooked evidence, extracting an exact grounded quote and clinical rationale. The quote is strictly checked against Gate A (verbatim grounding with whitespace/punctuation repair) and Gates B & C (`evaluate_gate_chain`). Upon passing, Agent 2 posts `DEFENSE` promoting the criterion to `MET`. If ungrounded or contradictory, it is recorded as a challenge and stays deferred.
- **Capped Fallback**: Fallback span iteration is completely skipped on clean, completed `NOT_MET` or `INSUFFICIENT_EVIDENCE` determinations (`status_code == "COMPLETED"`). It is preserved strictly for recovery from genuine judge errors or timeouts (`status_code != "COMPLETED"`), where it is capped at at most 1 fallback span call per criterion.
- **Agentic Time Budget Expanded (30s → 60s)**: The per-case time budget for agentic mode was adjusted from 30.0s to 60.0s based on empirical latency data from v52. This allows complete adversarial exchange (initial judgment + counter-reading + defense/advocacy) within bounds.

---

## 2. Task-by-Task Implementation Details

### Task 1: Agent 3 Advocate for `NOT_MET` / `INSUFFICIENT_EVIDENCE`
- **Model & Architecture**:
  - Added `AdvocacyResult(advocacy_quote: str, rationale: str, status_code: str, elapsed_ms: float)` to `app/core/llm_judge.py`.
  - Added `BoardMessageType.ADVOCACY = "ADVOCACY"` to `app/schemas/message_board.py`.
  - Implemented `ClinicalEquivalenceJudge.generate_advocacy_sync(criterion, note_text, deterministic_assessment)` prompting the LLM to locate unaddressed narrative text that satisfies the clinical criterion.
- **Pipeline Integration (`app/agents/pipeline.py`)**:
  - Routed only to criteria that need judgment (`ccode in needs_judge_codes`), are not already promoted, and have not halted on budget.
  - Posts `BoardMessageType.ADVOCACY` to the message board with the proposed quote and rationale.
  - Subjected immediately to:
    1. **Gate A**: Verbatim grounding via `LLMProposalAgent.locate_claimed_span(sanitized_ehr, adv_quote, allow_repair=True)`.
    2. **Gates B & C**: Concept map consistency and negation/family history checks via `evaluate_gate_chain`.
  - **Outcome**: If the advocacy quote passes all gates, Agent 2 posts `DEFENSE` (`advocacy_promoted=True`) and promotes the criterion assessment to `DeterminationStatus.MET`. If Gate A or Gate B/C fails, or if no quote is found, Agent 3 posts `CHALLENGE` (`advocacy_rejected=True`) and the criterion remains deferred.

### Task 2: Cap the Fallback
- Replaced unbounded span loops with targeted fallback logic in `app/agents/pipeline.py`:
  ```python
  should_run_fallback = (
      not promoted
      and not budget_halt
      and getattr(crit_judgment, "status_code", "COMPLETED") != "COMPLETED"
  )
  ```
- **Clean Determinations**: Skips fallback entirely if the judge completed with `NOT_MET` or `INSUFFICIENT_EVIDENCE`.
- **Error Recovery**: If the judge encountered a network/timeout error, at most 1 candidate span (`cand_spans[0]`) is attempted as fallback, subject to remaining call budget.

### Task 3: Parameter Change — Agentic Time Budget (30s → 60s)
- **Change**: `max_time_per_case_seconds` updated from 30.0s to 60.0s in:
  - `app/core/llm_judge.py` (`ClinicalEquivalenceJudge.__init__`)
  - `app/core/agentic_guardrails.py` (`AgenticGuardrails.MAX_LLM_TIME_PER_CASE_SECONDS`)
  - `app/agents/pipeline.py` (instantiation of `ClinicalEquivalenceJudge`)
- **Evidence & Justification**:
  - In v52, mean LLM call latency on the local model was 11.6s. Two sequential calls (initial judge + counter-reading) averaged ~23.2s, routinely exceeding 30.0s before defense dispatch.
  - At 60.0s, a 3-turn debate (initial call ~12s, counter-reading ~12s, defense ~12s = ~36s) comfortably completes within budget.
  - Frozen budgets remain strictly respected: `MAX_LLM_CALLS_PER_CASE = 3` is untouched.

### Task 4: Smoke Check & Transcript Audit
- Executed on 16 unique target vignettes across the required subsets:
  1. 3-case smoke test (`DEV-LCD-IMRT-APP`, `DEV-LCD-KYPHO-APP`, `DEV-LCD-ACDF-APP`)
  2. 9 unresolved synonymy cases from v52
  3. SBRT & SI-FUSION regression cases (`DEV-LCD-SBRT-APP`, `DEV-OPD-SI-FUSION-APP`)
  4. 14 false-deferral vignettes from v52
- Results committed to: `app/data/benchmarks/agentic_smoke_transcripts_v53.json`.
- **Key Findings**:
  - **Advocate Rescue**: On `DEV-LCD-KYPHO-APP`, Agent 3 advocacy inspected `CRIT-KYPHO-01` (severe back pain refractory to medical therapy) and extracted:
    `"Pain rating is 8/10 on visual analog scale."`
    This quote passed Gate A verbatim grounding, passed Gate B & C, and was defended by Agent 2, promoting `CRIT-KYPHO-01` to `MET`.
  - **SBRT & SI-FUSION Under 60s Budget**:
    - `DEV-LCD-SBRT-APP`: In v52, counter-reading finished at ~35.9s, causing concession by budget exhaustion. In v53 under the 60s budget, the defense attempt was reached and executed live. Agent 2 evaluated the `ANATOMIC_MISMATCH` challenge and conceded on clinical grounds (no resolving uncontradicted quote) rather than timing out.
    - `DEV-OPD-SI-FUSION-APP`: Defense call was reached within budget; conceded cleanly on clinical merit (`TEMPORAL` objection: conservative therapy < 16 weeks) rather than budget timeout.
  - **Fallback Capping**: In all clean determinations, fallback iterations were 0, eliminating the 59 wasted calls observed in v52.

### Task 5: Fail-Before / Pass-After Tests
Implemented 5 dedicated tests in `tests/test_agentic_redesign_realness.py`:
1. `test_advocacy_with_grounded_quote_promotes_criterion`: Confirms that a grounded, valid advocacy quote promotes a deferred criterion to `MET`.
2. `test_advocacy_with_fabricated_quote_rejected_by_gate_a`: Confirms that hallucinated advocacy quotes fail Gate A and remain unpromoted.
3. `test_advocacy_never_attempted_for_settled_criterion`: Confirms advocacy is never dispatched for criteria already settled (`MET`).
4. `test_fallback_skipped_on_clean_not_met_and_capped_at_one_on_error`: Verifies fallback is 0 on completed `NOT_MET` and at most 1 on judge error.
5. `test_sixty_second_time_budget_honored`: Verifies defense is permitted at 35s under the 60s budget, and rejected when exceeding 60s.

All 14 tests in `tests/test_agentic_redesign_realness.py` pass.

---

## 3. Test Suite Verification

- **Full Pytest Suite**:
  ```
  406 passed, 1 warning in 176.40s
  ```
- **Agentic Realness & Guardrail Suite**:
  ```
  tests/test_agentic_guardrails.py: 10 passed
  tests/test_agentic_redesign_realness.py: 14 passed
  tests/test_benchmark.py: 10 passed
  tests/test_v1_heldout_regressions.py: 4 passed
  ```
- **Ruff Linter Cleanliness**:
  - `tests/test_agentic_redesign_realness.py`: All checks passed.
  - `tests/test_agentic_guardrails.py`: All checks passed.
  - `scripts/run_agentic_v53_smoke_check.py`: All checks passed.
  - `app/schemas/message_board.py`: All checks passed.
  - `app/core/llm_judge.py`: All checks passed.
  - `app/core/agentic_guardrails.py`: All checks passed.
  - `app/agents/pipeline.py`: Clean on all modified lines.

---

## 4. Standing Rules Compliance

- **No Remote Egress**: Egress remains default-off; local Ollama with `qwen2.5:3b` was used exclusively.
- **Held-Out v2 Intact**: `carepolicyguard-heldout-v2/heldout_vignettes_v2.json` was never opened, read, or modified.
- **Deterministic & Declarative Unchanged**: Deterministic baseline and declarative engine paths remain identical with zero regressions.
- **No Self-Grading**: The 84-case benchmark was not run, and no headline accuracy or resolved-synonymy counts are reported. That measurement is strictly reserved for session v54.
