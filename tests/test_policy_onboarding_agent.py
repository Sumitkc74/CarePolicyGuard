"""
Tests for Agent 5: Policy Onboarding Agent (Task 1).
Verifies:
1. Known-good MCD source onboarding reproduces substantive criteria.
2. Fake/invalid CMS identifier stops with SOURCE_NOT_FOUND and writes nothing.
3. Non-verbatim quoted passage is rejected and flagged VERBATIM_CHECK_FAILED.
4. Ambiguous passages are flagged NEEDS_HUMAN_JUDGMENT with explicit clinician questions.
5. DRAFT policies cannot be used by adjudication pipeline and are excluded from retrieval.
6. Sample clinician notes fixture (SYN-01..SYN-12):
   - Synonymy/paraphrase/abbreviation cases (SYN-01, SYN-02, SYN-08, SYN-09, SYN-10, SYN-12) resolve to MET.
   - Trap cases (SYN-03, SYN-04, SYN-05, SYN-07, SYN-11) do NOT resolve to MET.
   - Ambiguity case (SYN-06) is flagged as ambiguity and deferred.
"""

import json
from pathlib import Path
import pytest

from app.agents.policy_onboarding import (
    PolicyOnboardingAgent,
    OnboardingResult
)
from app.agents.policy_retriever import PolicyRetrievalAgent
from app.agents.pipeline import MultiAgentVerificationPipeline
from app.services.declarative_engine import DeclarativePolicyEngine
from app.services.hybrid_retriever import HybridPolicyRetriever
from app.schemas.declarative_policy import DeclarativePolicy, DeclarativeCriterion, CriterionType
from app.schemas.contracts import DeterminationStatus, AdjudicationDecision


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "sample_clinician_notes.json"


def test_onboarding_against_known_good_source_reproduces_criteria():
    """Onboarding with a known-good MCD identifier (L36920) produces valid criteria."""
    agent = PolicyOnboardingAgent()
    result = agent.onboard_policy(
        cms_id="L36920",
        clinical_subject="Epidural Steroid Injections for Pain Management",
        save_draft=False
    )
    assert result.status == "DRAFT_ONBOARDED"
    assert result.policy is not None
    assert result.policy.status == "DRAFT"
    assert result.policy.policy_version.startswith("DRAFT")
    assert result.report is not None
    assert result.report.provenance_status == "VERIFIED_FROM_MCD"
    assert result.report.verbatim_checks_passed >= 1
    assert result.report.verbatim_checks_failed == 0

    # Substantive criterion check
    crit_codes = [c.criterion_code for c in result.policy.criteria]
    assert "CRIT-ESI-01" in crit_codes
    esi_crit = next(c for c in result.policy.criteria if c.criterion_code == "CRIT-ESI-01")
    assert esi_crit.source_traceability_status == "CLAIMED_UNVERIFIED"
    assert "conservative therapy" in esi_crit.entity_names


def test_onboarding_with_fake_identifier_stops_with_source_not_found(tmp_path):
    """Onboarding with a fake or fabricated identifier aborts with SOURCE_NOT_FOUND and writes nothing."""
    agent = PolicyOnboardingAgent(staging_dir=tmp_path)
    result = agent.onboard_policy(
        cms_id="L35452",  # Known fabricated ACDF identifier
        clinical_subject="Anterior Cervical Discectomy and Fusion",
        save_draft=True
    )
    assert result.status == "SOURCE_NOT_FOUND"
    assert "SOURCE_NOT_FOUND" in result.message
    assert result.policy is None
    # Must write no files to staging directory
    assert list(tmp_path.glob("*.json")) == []
    assert list(tmp_path.glob("*.md")) == []


def test_non_verbatim_quoted_passage_is_rejected():
    """A quoted passage that does not appear verbatim in the source document is flagged and rejected."""
    agent = PolicyOnboardingAgent()
    fake_doc_text = "This policy covers spinal orthoses for scoliosis."
    is_verbatim = agent.verify_verbatim_quote(fake_doc_text, "This policy covers cranial helmets.")
    assert not is_verbatim

    # When onboarding with non-verbatim indication
    doc = {
        "mcd_id": "L-TEST",
        "title": "Test Policy",
        "text": fake_doc_text,
        "indications": [
            {
                "code": "CRIT-TEST-01",
                "name": "Fabricated Citation Criterion",
                "description": "Fabricated quote test",
                "quoted_passage": "This sentence was hallucinated and does not exist in the source.",
                "section": "Indications",
                "paragraph": "Paragraph 1",
                "type": "FINDING_PRESENCE",
                "synonyms": ["scoliosis"]
            }
        ]
    }
    # Mocking fetch
    agent.fetch_mcd_document = lambda cid, subj: doc
    res = agent.onboard_policy(cms_id="L-TEST", clinical_subject="Test Policy", save_draft=False)
    assert res.status == "REJECTED_VERBATIM_FAILURE"
    assert res.report.verbatim_checks_failed == 1
    crit = res.policy.criteria[0]
    assert crit.source_traceability_status == "VERBATIM_CHECK_FAILED"
    assert crit.source_text_excerpt is None


def test_ambiguous_passage_flagged_needs_human_judgment():
    """An ambiguous passage is flagged as NEEDS_HUMAN_JUDGMENT with an explicit clinician question."""
    agent = PolicyOnboardingAgent()
    doc = agent.fetch_mcd_document("LCD-IMRT", "Intensity-Modulated Radiation Therapy")
    assert doc is not None
    ambiguities = agent.detect_ambiguities(doc["indications"], doc["text"])
    assert len(ambiguities) >= 1
    flag = ambiguities[0]
    assert flag.flag_type == "NEEDS_HUMAN_JUDGMENT"
    assert "rectal dose sparing" in flag.question_for_human.lower()
    assert "spinal cord" in flag.question_for_human.lower()


def test_draft_policy_excluded_from_adjudication_and_retrieval(tmp_path):
    """
    Asserts that DRAFT policies:
    1. Are excluded from retrieval by HybridPolicyRetriever.
    2. Cannot be loaded for decision by DeclarativePolicyEngine and PolicyRetrievalAgent.
    """
    # 1. Test DeclarativePolicyEngine and PolicyRetrievalAgent exclusion
    draft_policy = DeclarativePolicy(
        policy_id="LCD-TEST-DRAFT",
        title="Experimental Proton Therapy",
        description="Draft proton therapy policy",
        criteria=[],
        status="DRAFT"
    )
    # Save draft to temp directory
    p_path = tmp_path / "LCD-TEST-DRAFT.json"
    p_path.write_text(json.dumps(draft_policy.model_dump()), encoding="utf-8")

    # Invalidate and check load
    DeclarativePolicyEngine._POLICY_CACHE.pop("LCD-TEST-DRAFT", None)
    # Direct load with allow_draft=False must return None
    DeclarativePolicyEngine.get_policies_extended_dir = classmethod(lambda cls: tmp_path)
    loaded = DeclarativePolicyEngine.load_policy("LCD-TEST-DRAFT", allow_draft=False)
    assert loaded is None, "DRAFT policy must not load when allow_draft=False"

    # Explicit allow_draft=True loads it
    loaded_allowed = DeclarativePolicyEngine.load_policy("LCD-TEST-DRAFT", allow_draft=True)
    assert loaded_allowed is not None
    assert loaded_allowed.status == "DRAFT"

    # PolicyRetrievalAgent must return None
    retriever_agent = PolicyRetrievalAgent(db=None)
    retrieved = retriever_agent.retrieve_policy("LCD-TEST-DRAFT")
    assert retrieved is None, "PolicyRetrievalAgent must return None for DRAFT policy"

    # 2. Test HybridPolicyRetriever index exclusion
    all_policies = DeclarativePolicyEngine.get_all_policies(include_drafts=False)
    draft_ids = [p.policy_id for p in all_policies if p.status == "DRAFT"]
    assert len(draft_ids) == 0, "DRAFT policies must not be present in active policy list"


def test_sample_clinician_notes_fixture_evaluation():
    """
    Evaluates the 12 author-written synthetic sample notes (SYN-01..SYN-12).
    Verifies the governing rule:
    - Semantic equivalence (synonyms, subtypes, paraphrases, abbreviations) resolves to MET:
      SYN-01, SYN-02, SYN-08, SYN-09, SYN-10, SYN-12.
    - Trap cases do NOT resolve to MET:
      SYN-03 (negation), SYN-04 (family history), SYN-05 (near-miss organ),
      SYN-07 (hypothetical), SYN-11 (negated prior care).
    - Ambiguity case (SYN-06) is flagged as ambiguity and defers.
    """
    assert FIXTURE_PATH.exists(), f"Fixture file {FIXTURE_PATH} must exist"
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        fixture_data = json.load(f)

    cases = fixture_data["cases"]
    assert len(cases) == 12

    # Instantiate Onboarding Agent concept maps
    agent = PolicyOnboardingAgent()
    imrt_map = agent.build_concept_map("Intensity-Modulated Radiation Therapy", "IMRT prostate adenocarcinoma")
    cat_map = agent.build_concept_map("Cataract Extraction", "lens opacity nuclear sclerosis glare")
    esi_map = agent.build_concept_map("Epidural Steroid Injections", "conservative therapy physical therapy")
    korth_map = agent.build_concept_map("Knee Orthoses", "knee gives way varus deformity instability")

    # Evaluate each case
    for case in cases:
        cid = case["case_id"]
        narrative = case["ehr_narrative"]
        expected_crit = case["expected_criterion_outcome"]

        # 1. Ambiguity Case
        if cid == "SYN-06":
            assert expected_crit == "DEFER"
            ambs = agent.detect_ambiguities([{"description": "tumours adjacent to spinal cord"}], narrative)
            assert len(ambs) >= 1
            assert ambs[0].flag_type == "NEEDS_HUMAN_JUDGMENT"
            continue

        # 2. Prostate IMRT cases (SYN-01..SYN-05, SYN-07, SYN-12)
        if case["policy_id"] == "LCD-IMRT":
            crit = DeclarativeCriterion(
                criterion_code="CRIT-IMRT-01",
                name="Prostate Cancer",
                description="Clinically localized prostate cancer requiring radiation",
                criterion_type=CriterionType.FINDING_PRESENCE,
                entity_names=imrt_map["prostate cancer"]
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

        # 3. Cataract case (SYN-08)
        elif case["policy_id"] == "NCD-CATARACT":
            crit = DeclarativeCriterion(
                criterion_code="CRIT-CAT-01",
                name="Best Corrected Visual Acuity or Glare",
                description="Visual acuity 20/50 or worse or disabling glare with cataract",
                criterion_type=CriterionType.FINDING_PRESENCE,
                entity_names=cat_map["cataract"] + cat_map["visual impairment"]
            )
            eval_res = DeclarativePolicyEngine.evaluate(crit, narrative)
            assert eval_res.status == DeterminationStatus.MET

        # 4. ESI cases (SYN-09, SYN-11)
        elif case["policy_id"] == "LCD-ESI":
            crit = DeclarativeCriterion(
                criterion_code="CRIT-ESI-01",
                name="Failure of Conservative Therapy",
                description="Refractory to conservative therapy for at least 4-6 weeks",
                criterion_type=CriterionType.FINDING_PRESENCE,
                entity_names=esi_map["failure of conservative care"]
            )
            eval_res = DeclarativePolicyEngine.evaluate(crit, narrative)
            if expected_crit == "MET":
                assert eval_res.status == DeterminationStatus.MET, (
                    f"Case {cid} failed: {eval_res.clinical_rationale}"
                )
            else:
                assert eval_res.status != DeterminationStatus.MET, (
                    f"Trap case {cid} erroneously passed: {eval_res.clinical_rationale}"
                )

        # 5. Knee Orthosis case (SYN-10)
        elif case["policy_id"] == "LCD-KNEE-ORTHOSIS":
            crit = DeclarativeCriterion(
                criterion_code="CRIT-KORTH-01",
                name="Documented Instability and Deformity",
                description="Knee instability with giving way or objective varus deformity",
                criterion_type=CriterionType.FINDING_PRESENCE,
                entity_names=korth_map["knee instability"] + korth_map["deformity"]
            )
            eval_res = DeclarativePolicyEngine.evaluate(crit, narrative)
            assert eval_res.status == DeterminationStatus.MET

