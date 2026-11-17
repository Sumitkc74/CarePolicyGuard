"""
v62 Regression Tests: Gate C Domain Scoping and Advocate Span Selection.

Task 1: Scope Gate C matching by policy domain.
- Positive Control: Under NCD-SCS (Interventional Pain / Neurosurgery), an advocacy quote
  referencing 'spinal cord' does NOT match or collide with CONCEPT-PROTON-PBT-01
  ('Skull Base, Spine, or Critical Structure Proximity', Radiation Oncology).
- Negative Control: Within the same domain (e.g. LCD-KYPHO / Spine Surgery),
  genuinely disjoint concepts (e.g. 'Acute Vertebral Edema' vs 'Active Spinal Infection')
  are still rejected by Gate C.

Task 2: Fix advocate span selection.
- SBRT-01 Control: ClinicalEquivalenceJudge.select_most_relevant_span prioritizes the
  span establishing inoperability and early-stage disease rather than secondary readings
  like 'SUV max 8.4'.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.core.agentic_guardrails import AgenticGuardrails
from app.core.concept_map import ConceptDefinition, ConceptMap, ConceptSource
from app.core.llm_judge import ClinicalEquivalenceJudge
from app.schemas.contracts import ClinicalEvidenceSpan


@pytest.fixture
def v62_test_concept_map() -> ConceptMap:
    """Assembles a merged concept map containing built-ins and draft concepts."""
    cmap = ConceptMap()
    draft_file = Path("app/data/concept_map/draft_concept_entries.json")
    if draft_file.exists():
        with open(draft_file, "r", encoding="utf-8") as f:
            drafts = json.load(f)
        for d in drafts:
            if d.get("governing_rule_check") == "PASS_EQUIVALENCE":
                cmap.register_concept(
                    ConceptDefinition(
                        concept_id=d["concept_id"],
                        canonical_name=d["canonical_name"],
                        domain=d["domain"],
                        accepted_terms=d["accepted_terms"],
                        prohibited_near_misses=d.get("prohibited_near_misses", []),
                        source=ConceptSource.TASK1_ADJUDICATION_EXPANSION,
                        source_reason=d.get("governing_rule_rationale", ""),
                    )
                )
    return cmap


def test_task1_positive_control_scs_proton_collision_prevented(v62_test_concept_map: ConceptMap) -> None:
    """
    Task 1 Positive Control:
    Under NCD-SCS (Interventional Pain / Neurosurgery), the quote:
    'Patient completed a 6-day temporary percutaneous spinal cord stimulator trial, documenting 80% pain relief'
    contains 'spinal cord', which in v61 collided with CONCEPT-PROTON-PBT-01 (Radiation Oncology).
    With domain scoping, the proton concept must NOT be a candidate match, eliminating the
    false cross-domain collision.
    """
    quote = (
        "Patient completed a 6-day temporary percutaneous spinal cord stimulator trial, "
        "documenting 80% pain relief and significant increase in daily walking distance."
    )
    ehr = f"OBJECTIVE: {quote}"
    s = ehr.index(quote)
    e = s + len(quote)

    span = ClinicalEvidenceSpan(
        source_text=quote,
        start_char=s,
        end_char=e,
        confidence=0.92,
    )

    criterion: dict[str, Any] = {
        "criterion_code": "CRIT-SCS-02",
        "name": "Pre-Implant Psychological Evaluation",
        "description": "Documented formal pre-implant psychological evaluation by a licensed mental health professional.",
        "entity_names": ["psychological evaluation for scs", "mental health clearance"],
        "keywords": ["psychological evaluation for scs", "mental health clearance"],
        "policy_id": "NCD-SCS",
        "category": "Interventional Pain / Neurosurgery",
        "domain": "Interventional Pain / Neurosurgery",
    }

    # Evaluate gate chain with domain scoping
    res = AgenticGuardrails.evaluate_gate_chain(
        candidate_span=span,
        criterion=criterion,
        ehr_narrative=ehr,
        concept_map=v62_test_concept_map,
        policy_domain="Interventional Pain / Neurosurgery",
        policy_id="NCD-SCS",
    )

    # The failure reason must NOT mention CONCEPT-PROTON-PBT-01 or Skull Base, Spine, or Critical Structure Proximity
    assert "Skull Base, Spine, or Critical Structure Proximity" not in res["reason"]
    assert "CONCEPT-PROTON" not in res["reason"]


def test_task1_negative_control_genuinely_disjoint_terms_in_same_domain_rejected(
    v62_test_concept_map: ConceptMap,
) -> None:
    """
    Task 1 Mandatory Negative Control:
    Within the same clinical domain (Spine Surgery / Interventional Radiology),
    a quote about Active Systemic Infection evaluated against a criterion about
    Acute Vertebral Edema must STILL be rejected by Gate C as disjoint concepts.
    Domain scoping must never weaken Gate C into a rubber stamp.
    """
    quote = "Patient exhibits active systemic infection with high fevers and bacteremia."
    ehr = f"OBJECTIVE: {quote}"
    s = ehr.index(quote)
    e = s + len(quote)

    span = ClinicalEvidenceSpan(
        source_text=quote,
        start_char=s,
        end_char=e,
        confidence=0.92,
    )

    criterion: dict[str, Any] = {
        "criterion_code": "CRIT-KYPHO-02",
        "name": "Acute Vertebral Fracture Edema",
        "description": "Documentation of acute or subacute vertebral compression fracture with bone marrow edema.",
        "entity_names": ["acute vertebral edema", "marrow edema on mri", "hyperintensity on stir"],
        "keywords": ["acute vertebral edema", "bone marrow edema"],
        "policy_id": "LCD-KYPHO",
        "category": "Interventional Radiology / Spine Surgery",
        "domain": "Interventional Radiology / Spine Surgery",
    }

    res = AgenticGuardrails.evaluate_gate_chain(
        candidate_span=span,
        criterion=criterion,
        ehr_narrative=ehr,
        concept_map=v62_test_concept_map,
        policy_domain="Interventional Radiology / Spine Surgery",
        policy_id="LCD-KYPHO",
    )

    assert not res["passed"]
    assert res["failing_gate"] == "GATE_C_MAP_CHECK"
    # Must reject as disjoint concepts within domain or no matching concept definition
    assert "disjoint concepts" in res["reason"] or "NO_CONCEPT_MAP_ENTRY" in res["reason"]


def test_task2_advocate_span_selection_covers_inoperability() -> None:
    """
    Task 2 Regression Control:
    For CRIT-SBRT-01 on DEV-LCD-SBRT-APP note text, select_most_relevant_span must
    select the span containing inoperability and early-stage disease rather than
    secondary numbers such as 'SUV max 8.4'.
    """
    note = (
        "[SYNTHETIC TEST DATA - NOT A REAL PATIENT RECORD]\n"
        "CLINICAL PROGRESS NOTE: Radiation Oncology\n"
        "SUBJECTIVE: 76-year-old with severe baseline COPD (FEV1 32% predicted, home oxygen 2 L/min) "
        "evaluated for newly discovered right upper lobe solitary nodule. Thoracic surgery deemed "
        "patient medically inoperable due to high operative mortality risk.\n"
        "OBJECTIVE: PET-CT confirms hypermetabolic 2.2 cm peripheral pulmonary lesion (SUV max 8.4) "
        "with zero mediastinal or distant nodal uptake (cT1cN0M0). Brain MRI negative. "
        "Multidisciplinary thoracic tumor board reviewed case and recommended stereotactic ablative delivery.\n"
        "ASSESSMENT & PLAN: Medically inoperable early-stage non-small cell lung cancer. "
        "Plan: Stereotactic body radiation therapy (SBRT) delivering 50 Gy in 4 fractions with respiratory motion tracking."
    )

    criterion: dict[str, Any] = {
        "criterion_code": "CRIT-SBRT-01",
        "name": "Early-Stage NSCLC (T1-T2N0M0) or Oligometastases (<= 3 Lesions)",
        "description": "Biopsy-proven early stage lung cancer in medically inoperable patient (poor pulmonary reserve FEV1 < 40%), or oligometastatic disease with <= 3 discrete lesions.",
        "clinical_intent": "Establish tumor stage and volume qualifying for stereotactic hypofractionation",
        "entity_names": ["stage i nsclc", "medically inoperable lung cancer", "oligometastatic disease <= 3 lesions", "t1n0m0 lung cancer"],
        "keywords": ["stage i nsclc", "medically inoperable lung cancer", "oligometastatic disease <= 3 lesions", "t1n0m0 lung cancer"],
    }

    # Simulate advocate initially returning weak fragment 'SUV max 8.4'
    refined_span = ClinicalEquivalenceJudge.select_most_relevant_span(
        criterion=criterion,
        note_text=note,
        candidate_quote="SUV max 8.4",
    )

    assert refined_span in note
    assert "inoperab" in refined_span.lower(), f"Expected inoperability element in quote, got: {refined_span}"


def test_concept_map_domain_filtering_mechanism(v62_test_concept_map: ConceptMap) -> None:
    """Verifies that ConceptMap.lookup_concept strictly respects domain filters."""
    # Global lookup of 'spinal cord' finds radiation oncology concept
    c_global = v62_test_concept_map.lookup_concept("spinal cord")
    assert c_global is not None
    assert c_global.concept_id in ("CONCEPT-PROTON-PBT-01", "CONCEPT-DOSE-SENSITIVE-STRUCTURES")

    # Scoped lookup to Interventional Pain / Neurosurgery must NOT return the proton concept
    c_scoped = v62_test_concept_map.lookup_concept(
        "spinal cord",
        domain="Interventional Pain / Neurosurgery",
        policy_id="NCD-SCS",
    )
    assert c_scoped is None
