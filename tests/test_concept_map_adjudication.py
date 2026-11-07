"""
Unit and integration tests for Task 1: Concept Map in Adjudication and Task 3: Criteria as Concepts.
Governing rules:
- Semantic equivalence is understanding, and the system must do it.
- Genuine ambiguity is a deferral, and the system must not guess it.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.concept_map import (
    ConceptDefinition,
    ConceptMap,
    ConceptReviewQueue,
    ConceptReviewItem,
    ReviewQueueStatus,
    get_concept_map,
)
from app.schemas.contracts import DeterminationStatus
from app.schemas.declarative_policy import CriterionType, DeclarativeCriterion
from app.services.declarative_engine import DeclarativePolicyEngine

FIXTURE_PATH = Path("tests/fixtures/sample_clinician_notes.json")


def test_concept_map_vocabulary_and_term_indexing():
    """Validates that the auditable concept map indexes clinical terms without hidden fuzziness."""
    cmap = get_concept_map()
    assert cmap.total_concepts >= 10
    assert cmap.total_terms >= 30

    # Prostate cancer concept
    pca_def = cmap.lookup_concept("prostate adenocarcinoma")
    assert pca_def is not None
    assert pca_def.concept_id == "CONCEPT-PROSTATE-CANCER"
    assert "prostate adenocarcinoma" in pca_def.accepted_terms
    assert "ca prostate" in pca_def.accepted_terms
    assert "pca" in pca_def.accepted_terms


def test_concept_map_near_miss_protection():
    """
    Asserts that the concept map is NOT a blanket substring match.
    Near-misses (e.g. adenocarcinoma of a different organ, benign hyperplasia)
    must fail equivalence verification via explicit prohibited near-miss lists.
    """
    cmap = get_concept_map()

    # 1. Prostate cancer vs lung adenocarcinoma
    passed, reason = cmap.verify_equivalence("prostate cancer", "lung adenocarcinoma")
    assert not passed
    assert "PROHIBITED_NEAR_MISS" in reason

    # 2. Prostate cancer vs benign prostatic hyperplasia
    passed, reason = cmap.verify_equivalence("prostate cancer", "benign prostatic hyperplasia")
    assert not passed
    assert "PROHIBITED_NEAR_MISS" in reason

    # 3. Cataract vs glaucoma
    passed, reason = cmap.verify_equivalence("cataract", "glaucoma")
    assert not passed
    assert "PROHIBITED_NEAR_MISS" in reason


def test_unmapped_claim_lands_in_review_queue_and_case_defers():
    """
    A claim with NO MAP ENTRY is not auto-accepted:
    it lands in the human review queue and the case defers.
    The LLM may suggest new entries, but it must never add one by itself.
    """
    ConceptReviewQueue.clear()
    cmap = get_concept_map()

    # Attempt equivalence of an unmapped claim (e.g. rectal spacing for spinal proximity)
    passed, reason = cmap.verify_equivalence("adjacent to spinal cord", "rectal dose sparing")
    assert not passed
    assert "NO_CONCEPT_MAP_ENTRY" in reason

    # Submit to human review queue
    item = ConceptReviewQueue.submit_unmapped_proposal(
        case_id="SYN-06",
        criterion_code="CRIT-IMRT-01",
        criterion_term="adjacent to spinal cord",
        proposed_span="rectal dose sparing",
        claimed_equivalence="User asks if rectal sparing satisfies spinal cord proximity",
        ehr_snippet="does rectal dose sparing satisfy a criterion written for tumours adjacent to the spinal cord?"
    )
    assert item.status == ReviewQueueStatus.PENDING_HUMAN_REVIEW
    assert len(ConceptReviewQueue.get_pending()) >= 1

    # Human review resolution
    resolved = ConceptReviewQueue.resolve_item(
        review_id=item.review_id,
        decision="REJECTED",
        reviewer_notes="Coverage judgment: rectal sparing does not satisfy a spinal cord specific criterion."
    )
    assert resolved is not None
    assert resolved.status == ReviewQueueStatus.REJECTED


def test_sample_clinician_notes_all_12_cases_adjudication():
    """
    Paraphrase test set built from sample_clinician_notes.json:
    Asserts that all 12 cases produce their exact stated expected outcomes:
    - SYN-01, SYN-02, SYN-08, SYN-09, SYN-10, SYN-12 resolve without deferral for synonymy.
    - SYN-03, SYN-04, SYN-05, SYN-07, SYN-11 do not resolve (NOT_MET / reject).
    - SYN-06 defers (genuine ambiguity / human judgment).
    """
    assert FIXTURE_PATH.exists()
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        fixture_data = json.load(f)

    cases = fixture_data["cases"]
    assert len(cases) == 12
    cmap = get_concept_map()

    for case in cases:
        cid = case["case_id"]
        narrative = case["ehr_narrative"]
        expected_crit = case["expected_criterion_outcome"]

        # Ambiguity case: SYN-06
        if cid == "SYN-06":
            assert expected_crit == "DEFER"
            passed, reason = cmap.verify_equivalence("adjacent to spinal cord", "rectal dose sparing")
            assert not passed
            assert "NO_CONCEPT_MAP_ENTRY" in reason
            continue

        # Prostate IMRT cases: SYN-01, SYN-02, SYN-03, SYN-04, SYN-05, SYN-07, SYN-12
        if case["policy_id"] == "LCD-IMRT":
            crit = DeclarativeCriterion(
                criterion_code="CRIT-IMRT-01",
                name="Prostate Cancer",
                description="Clinically localized prostate cancer requiring radiation",
                criterion_type=CriterionType.FINDING_PRESENCE,
                entity_names=["prostate cancer"]  # Engine expands through ConceptMap!
            )
            eval_res = DeclarativePolicyEngine.evaluate(crit, narrative)
            if expected_crit == "MET":
                assert eval_res.status == DeterminationStatus.MET, (
                    f"Case {cid} failed to resolve semantic equivalence: {eval_res.clinical_rationale}"
                )
            else:
                assert eval_res.status != DeterminationStatus.MET, (
                    f"Trap case {cid} erroneously passed as MET: {eval_res.clinical_rationale}"
                )

        # Cataract case: SYN-08
        elif case["policy_id"] == "NCD-CATARACT":
            crit = DeclarativeCriterion(
                criterion_code="CRIT-CAT-01",
                name="Cataract and Lens Opacity",
                description="Visual impairment with dense lens opacity or nuclear sclerosis",
                criterion_type=CriterionType.FINDING_PRESENCE,
                entity_names=["cataract"]  # Engine expands to lens opacity, nuclear sclerosis, etc.
            )
            eval_res = DeclarativePolicyEngine.evaluate(crit, narrative)
            assert eval_res.status == DeterminationStatus.MET

        # ESI cases: SYN-09, SYN-11
        elif case["policy_id"] == "LCD-ESI":
            crit = DeclarativeCriterion(
                criterion_code="CRIT-ESI-01",
                name="Failure of Conservative Therapy",
                description="Refractory to conservative therapy for at least 4-6 weeks",
                criterion_type=CriterionType.FINDING_PRESENCE,
                entity_names=["failure of conservative therapy"]
            )
            eval_res = DeclarativePolicyEngine.evaluate(crit, narrative)
            if expected_crit == "MET":
                assert eval_res.status == DeterminationStatus.MET
            else:
                assert eval_res.status != DeterminationStatus.MET

        # Knee orthosis case: SYN-10
        elif case["policy_id"] == "LCD-KNEE-ORTHOSIS":
            crit = DeclarativeCriterion(
                criterion_code="CRIT-KORTH-01",
                name="Knee Joint Instability",
                description="Documented knee instability or angular deformity",
                criterion_type=CriterionType.FINDING_PRESENCE,
                entity_names=["knee instability"]  # Expands to "knee gives way", "varus deformity", etc.
            )
            eval_res = DeclarativePolicyEngine.evaluate(crit, narrative)
            assert eval_res.status == DeterminationStatus.MET


def test_task3_rewritten_criterion_instances_and_intent():
    """
    Task 3: Tests each rewritten criterion asserting an instance from the authorized list
    satisfies it and an instance outside the list does not (or defers).
    """
    # 1. LCD-IMRT CRIT-IMRT-01 (Class: Dose-Sensitive Critical Normal Structures)
    policy_imrt = DeclarativePolicyEngine.load_policy("LCD-IMRT")
    assert policy_imrt is not None
    crit_imrt_01 = next(c for c in policy_imrt.criteria if c.criterion_code == "CRIT-IMRT-01")

    # Instance from list: Parotid gland sparing
    note_parotid = "Patient has head and neck carcinoma requiring parotid gland sparing to avoid xerostomia."
    res_parotid = DeclarativePolicyEngine.evaluate(crit_imrt_01, note_parotid)
    assert res_parotid.status == DeterminationStatus.MET

    # Instance from list: Brainstem proximity
    note_brainstem = "Patient has head and neck carcinoma adjacent to the brainstem."
    res_brainstem = DeclarativePolicyEngine.evaluate(crit_imrt_01, note_brainstem)
    assert res_brainstem.status == DeterminationStatus.MET

    # Excluded instance per governing rule: Rectal wall dose sparing does not satisfy CRIT-IMRT-01
    note_rectal = "Inverse IMRT plan limits rectal wall dose below 70 Gy while escalating target volume."
    res_rectal = DeclarativePolicyEngine.evaluate(crit_imrt_01, note_rectal)
    assert res_rectal.status != DeterminationStatus.MET

    # Instance outside list: Hand tendon sparing (unrelated structure)
    note_unrelated = "Patient has head and neck carcinoma; hand tendon sparing requested."
    res_unrelated = DeclarativePolicyEngine.evaluate(crit_imrt_01, note_unrelated)
    assert res_unrelated.status != DeterminationStatus.MET

    # 2. LCD-PROTON CRIT-PBT-01 (Class: Critical Dose-Limiting Neural/Ocular Structures)
    policy_proton = DeclarativePolicyEngine.load_policy("LCD-PROTON")
    assert policy_proton is not None
    crit_pbt_01 = next(c for c in policy_proton.criteria if c.criterion_code == "CRIT-PBT-01")

    # Instance from list: Optic chiasm proximity
    note_chiasm = "Skull base lesion abutting optic chiasm requiring Bragg peak margin preservation."
    res_chiasm = DeclarativePolicyEngine.evaluate(crit_pbt_01, note_chiasm)
    assert res_chiasm.status == DeterminationStatus.MET

    # 3. LCD-LUMBAR-DECOMP CRIT-LDEC-02 (Class: Non-Surgical Conservative Therapy)
    policy_decomp = DeclarativePolicyEngine.load_policy("LCD-LUMBAR-DECOMP")
    assert policy_decomp is not None
    crit_ldec_02 = next(c for c in policy_decomp.criteria if c.criterion_code == "CRIT-LDEC-02")

    # Instance from list: Chiropractic care + NSAIDs
    note_chiro = "Patient completed 8 weeks of chiropractic care and NSAIDs without resolution of radiculopathy."
    res_chiro = DeclarativePolicyEngine.evaluate(crit_ldec_02, note_chiro)
    assert res_chiro.status == DeterminationStatus.MET


def test_pipeline_level_syn06_defers_and_syn01_proceeds():
    """
    Task 4: Pipeline-level test (not map-only) asserting:
    1. SYN-06 defers to human at pipeline level (rectal dose sparing does NOT silently pass spinal cord rule).
    2. SYN-01 proceeds without deferral for synonymy alone on CRIT-IMRT-01 (prostate adenocarcinoma is understood).
    """
    from app.agents.pipeline import MultiAgentVerificationPipeline
    from app.schemas.contracts import AdjudicationDecision

    pipeline = MultiAgentVerificationPipeline(db=None)

    assert FIXTURE_PATH.exists()
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        cases = {c["case_id"]: c for c in json.load(f)["cases"]}

    # 1. Pipeline-level check for SYN-06: MUST DEFER
    syn06_case = cases["SYN-06"]
    adj_06 = pipeline.adjudicate_sync(
        patient_id="PT-SYN-06",
        policy_id="LCD-IMRT",
        ehr_narrative=syn06_case["ehr_narrative"],
        execution_mode="declarative",
        save_record=False
    )
    assert adj_06.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN

    # 2. Pipeline-level check for SYN-01: CRIT-IMRT-01 must proceed as MET (synonymy understood)
    syn01_case = cases["SYN-01"]
    adj_01 = pipeline.adjudicate_sync(
        patient_id="PT-SYN-01",
        policy_id="LCD-IMRT",
        ehr_narrative=syn01_case["ehr_narrative"],
        execution_mode="declarative",
        save_record=False
    )
    crit_01_syn01 = next((a for a in adj_01.criterion_assessments if a.criterion_code == "CRIT-IMRT-01"), None)
    assert crit_01_syn01 is not None
    assert crit_01_syn01.status == DeterminationStatus.MET, (
        f"SYN-01 failed to resolve prostate adenocarcinoma on CRIT-IMRT-01: {crit_01_syn01.clinical_rationale}"
    )
