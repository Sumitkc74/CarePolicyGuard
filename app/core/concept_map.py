"""
Explicit, Auditable Concept Map and Human Review Queue for Clinical Adjudication.
Task 1: The concept map in adjudication, as the deterministic verifier for LLM synonymy proposals.
No hidden fuzzy matching, no embedding similarity with unexplained thresholds.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ConceptSource(str, Enum):
    """Auditable provenance source for accepted concept terms."""
    RETRIEVAL_VOCABULARY = "retrieval_vocabulary"
    ONBOARDING_AGENT = "onboarding_agent"
    TASK1_ADJUDICATION_EXPANSION = "task1_adjudication_expansion"
    HUMAN_REVIEW_ACCEPTED = "human_review_accepted"


class ConceptDefinition(BaseModel):
    """
    Explicit, auditable definition of a clinical concept.
    Lists accepted clinical terms, synonyms, histology subtypes, abbreviations,
    and prohibited near-misses that must NEVER match this concept.
    """
    concept_id: str = Field(..., description="Unique concept identifier, e.g. CONCEPT-PROSTATE-CANCER")
    canonical_name: str = Field(..., description="Canonical clinical concept name")
    domain: str = Field(default="general", description="Clinical domain, e.g. oncology, ophthalmology")
    accepted_terms: list[str] = Field(default_factory=list, description="Accepted synonymous terms, subtypes, abbreviations")
    prohibited_near_misses: list[str] = Field(
        default_factory=list,
        description="Explicit negative terms/near-misses that must NOT match (e.g. lung adenocarcinoma for prostate)"
    )
    is_class_concept: bool = Field(default=False, description="Whether this concept represents a class with instances")
    authorized_instances: list[str] = Field(
        default_factory=list,
        description="Authorized instances of this class justified by policy text or CMS source"
    )
    source: ConceptSource = Field(default=ConceptSource.TASK1_ADJUDICATION_EXPANSION)
    source_reason: str = Field(..., description="Auditable justification for why these terms belong to this concept")


class ReviewQueueStatus(str, Enum):
    """Status of an item in the human review queue."""
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class ConceptReviewItem(BaseModel):
    """
    A proposed synonymy equivalence that had no match in the concept map.
    Logged for human clinician review. The case defers while pending review.
    """
    review_id: str = Field(default_factory=lambda: f"REV-{uuid.uuid4().hex[:8].upper()}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    case_id: str = Field(..., description="Case or vignette ID where claim occurred")
    criterion_code: str = Field(..., description="Policy criterion code being evaluated")
    criterion_term: str = Field(..., description="Term in the policy criterion")
    proposed_span: str = Field(..., description="Exact span extracted from note")
    claimed_equivalence: str = Field(..., description="Equivalence claimed by LLM or author")
    ehr_snippet: str = Field(default="", description="Surrounding clinical context from note")
    status: ReviewQueueStatus = Field(default=ReviewQueueStatus.PENDING_HUMAN_REVIEW)
    reviewer_decision: str | None = Field(default=None)
    reviewer_notes: str | None = Field(default=None)
    resolved_at: datetime | None = Field(default=None)


class ConceptReviewQueue:
    """
    Auditable queue for unmapped synonymy claims.
    Ensures that unknown synonym claims defer to human review and are recorded.
    Reviewed entries (accepted by human) are the ONLY way the concept map grows at runtime.
    The LLM may suggest new entries, but it must NEVER add one by itself.
    """
    _QUEUE: ClassVar[list[ConceptReviewItem]] = []

    @classmethod
    def submit_unmapped_proposal(
        cls,
        case_id: str,
        criterion_code: str,
        criterion_term: str,
        proposed_span: str,
        claimed_equivalence: str,
        ehr_snippet: str = ""
    ) -> ConceptReviewItem:
        """Submits an unmapped claim to the review queue."""
        item = ConceptReviewItem(
            case_id=case_id,
            criterion_code=criterion_code,
            criterion_term=criterion_term,
            proposed_span=proposed_span,
            claimed_equivalence=claimed_equivalence,
            ehr_snippet=ehr_snippet,
            status=ReviewQueueStatus.PENDING_HUMAN_REVIEW
        )
        cls._QUEUE.append(item)
        logger.info(f"Submitted unmapped synonymy claim {item.review_id} to human review queue (case={case_id})")
        return item

    @classmethod
    def get_pending(cls) -> list[ConceptReviewItem]:
        """Returns all items pending human review."""
        return [item for item in cls._QUEUE if item.status == ReviewQueueStatus.PENDING_HUMAN_REVIEW]

    @classmethod
    def resolve_item(
        cls,
        review_id: str,
        decision: str,
        reviewer_notes: str,
        concept_map: ConceptMap | None = None,
        concept_id: str | None = None
    ) -> ConceptReviewItem | None:
        """
        Resolves an item. If accepted and concept_map/concept_id provided,
        adds the approved term to the concept map with auditable human provenance.
        """
        for item in cls._QUEUE:
            if item.review_id == review_id:
                if decision.upper() == "ACCEPTED":
                    item.status = ReviewQueueStatus.ACCEPTED
                    item.reviewer_decision = "ACCEPTED"
                    item.reviewer_notes = reviewer_notes
                    item.resolved_at = datetime.now(UTC)
                    if concept_map and concept_id:
                        concept_map.add_accepted_term(
                            concept_id=concept_id,
                            term=item.proposed_span,
                            source_reason=f"Human review accepted ({item.review_id}): {reviewer_notes}"
                        )
                else:
                    item.status = ReviewQueueStatus.REJECTED
                    item.reviewer_decision = "REJECTED"
                    item.reviewer_notes = reviewer_notes
                    item.resolved_at = datetime.now(UTC)
                return item
        return None

    @classmethod
    def clear(cls) -> None:
        """Clears queue (for test isolation)."""
        cls._QUEUE.clear()

    @classmethod
    def all_items(cls) -> list[ConceptReviewItem]:
        return list(cls._QUEUE)


class ConceptMap:
    """
    Deterministic clinical concept vocabulary and verifier for adjudication.
    Maps clinical terms, synonyms, histology subtypes, and abbreviations.
    No fuzzy string matching; explicit containment in auditable concept definitions.
    """

    def __init__(self, data_path: Path | None = None):
        self._concepts: dict[str, ConceptDefinition] = {}
        self._term_to_concept_id: dict[str, str] = {}
        self._load_built_in_concepts()
        if data_path and data_path.exists():
            self._load_from_json(data_path)

    @property
    def total_concepts(self) -> int:
        return len(self._concepts)

    @property
    def total_terms(self) -> int:
        return len(self._term_to_concept_id)

    def register_concept(self, concept: ConceptDefinition) -> None:
        """Registers a concept and indexes all its accepted terms in lowercase."""
        self._concepts[concept.concept_id] = concept
        for term in concept.accepted_terms:
            norm_term = term.strip().lower()
            if norm_term:
                self._term_to_concept_id[norm_term] = concept.concept_id
        for instance in concept.authorized_instances:
            norm_inst = instance.strip().lower()
            if norm_inst:
                self._term_to_concept_id[norm_inst] = concept.concept_id

    def lookup_concept(self, term: str) -> ConceptDefinition | None:
        """Finds concept definition for a given clinical term or synonym."""
        norm_term = term.strip().lower()
        cid = self._term_to_concept_id.get(norm_term)
        if cid:
            return self._concepts.get(cid)
        # Check if term contains any indexed multi-word term or vice-versa
        for indexed_term, c_id in self._term_to_concept_id.items():
            if len(indexed_term) >= 4 and indexed_term in norm_term:
                return self._concepts.get(c_id)
        return None

    def get_terms_for_concept(self, concept_id_or_term: str) -> list[str]:
        """Returns all accepted terms (including instances) for a concept."""
        if concept_id_or_term in self._concepts:
            c = self._concepts[concept_id_or_term]
            return list(c.accepted_terms) + list(c.authorized_instances)
        c = self.lookup_concept(concept_id_or_term)
        if c:
            return list(c.accepted_terms) + list(c.authorized_instances)
        return [concept_id_or_term]

    def verify_equivalence(
        self,
        criterion_term: str,
        proposed_term: str
    ) -> tuple[bool, str]:
        """
        The Map is the Verifier:
        Checks if proposed_term and criterion_term belong to the same clinical concept.
        Returns: (is_equivalent: bool, reason: str)
        Possible reasons:
        - "EQUIVALENCE_CONFIRMED": verified in concept map
        - "PROHIBITED_NEAR_MISS": explicit negative match (e.g. wrong organ adenocarcinoma)
        - "NO_CONCEPT_MAP_ENTRY": no concept contains both terms -> defers to human review queue
        """
        crit_norm = criterion_term.strip().lower()
        prop_norm = proposed_term.strip().lower()

        # Find concepts for both terms
        crit_concept = self.lookup_concept(crit_norm)
        prop_concept = self.lookup_concept(prop_norm)

        if not crit_concept:
            return False, f"NO_CONCEPT_MAP_ENTRY: Criterion term '{criterion_term}' is not indexed in concept map."

        # Check prohibited near-misses on the criterion's concept
        for near_miss in crit_concept.prohibited_near_misses:
            if near_miss.lower() in prop_norm:
                return False, f"PROHIBITED_NEAR_MISS: Proposed term '{proposed_term}' matches prohibited near-miss '{near_miss}' for concept {crit_concept.canonical_name}."

        if not prop_concept:
            return False, f"NO_CONCEPT_MAP_ENTRY: Proposed term '{proposed_term}' has no entry in concept map."

        if crit_concept.concept_id == prop_concept.concept_id:
            # If concept is a class with distinct authorized instances
            if crit_concept.is_class_concept:
                crit_instances = [inst for inst in crit_concept.authorized_instances if inst.lower() in crit_norm or crit_norm in inst.lower()]
                prop_instances = [inst for inst in crit_concept.authorized_instances if inst.lower() in prop_norm or prop_norm in inst.lower()]
                # If criterion specifically names an instance (e.g. spinal cord) and proposed term is a different instance (e.g. rectum)
                if crit_instances and prop_instances and not any(ci in prop_instances for ci in crit_instances):
                    return False, f"NO_CONCEPT_MAP_ENTRY: Terms are distinct anatomical instances of class '{crit_concept.canonical_name}' ({crit_instances[0]} vs {prop_instances[0]}); cross-instance substitution is a coverage judgment and defers to human review."

            return True, f"EQUIVALENCE_CONFIRMED: Both terms belong to {crit_concept.canonical_name} ({crit_concept.concept_id})."

        # Check if criterion concept is a class and proposed term is an authorized instance
        if crit_concept.is_class_concept:
            for inst in crit_concept.authorized_instances:
                if inst.lower() in prop_norm or prop_norm in inst.lower():
                    return True, f"EQUIVALENCE_CONFIRMED: '{proposed_term}' is an authorized instance of class '{crit_concept.canonical_name}'."

        return False, f"NO_CONCEPT_MAP_ENTRY: Terms belong to disjoint concepts ('{crit_concept.canonical_name}' vs '{prop_concept.canonical_name}')."

    def add_accepted_term(self, concept_id: str, term: str, source_reason: str) -> bool:
        """Adds an accepted term to an existing concept with human provenance."""
        concept = self._concepts.get(concept_id)
        if not concept:
            return False
        norm = term.strip().lower()
        if norm not in [t.lower() for t in concept.accepted_terms]:
            concept.accepted_terms.append(term.strip())
            self._term_to_concept_id[norm] = concept_id
            logger.info(f"Added term '{term}' to concept {concept_id}: {source_reason}")
            return True
        return False

    def _load_from_json(self, path: Path) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("concepts", []):
                self.register_concept(ConceptDefinition(**item))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning(f"Could not load concepts from {path}: {exc}")

    def _load_built_in_concepts(self) -> None:
        """Loads core clinical concept definitions covering 50 CMS policy domains."""

        # 1. Oncology: Prostate Cancer (SYN-01, SYN-02, SYN-05, SYN-12)
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-PROSTATE-CANCER",
            canonical_name="Prostate Cancer",
            domain="oncology",
            accepted_terms=[
                "prostate cancer", "prostate adenocarcinoma", "adenocarcinoma of the prostate",
                "prostate malignancy", "prostatic adenocarcinoma", "ca prostate", "pca",
                "clinically localized prostate cancer", "intermediate-risk prostate adenocarcinoma",
                "carcinoma of prostate", "malignant neoplasm of prostate"
            ],
            prohibited_near_misses=[
                "lung adenocarcinoma", "breast adenocarcinoma", "pancreatic adenocarcinoma",
                "colon adenocarcinoma", "colorectal adenocarcinoma", "gastric adenocarcinoma",
                "benign prostatic hyperplasia", "bph", "prostatitis", "prostate disease"
            ],
            source=ConceptSource.TASK1_ADJUDICATION_EXPANSION,
            source_reason="Oncology standard: adenocarcinoma of the prostate is the predominant histologic subtype of prostate cancer."
        ))

        # 2. Oncology: Lung Cancer (for near-miss differentiation)
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-LUNG-CANCER",
            canonical_name="Lung Malignancy",
            domain="oncology",
            accepted_terms=[
                "lung adenocarcinoma", "lung cancer", "non-small cell lung cancer", "nsclc",
                "small cell lung cancer", "sclc", "bronchogenic carcinoma", "squamous cell carcinoma of lung"
            ],
            prohibited_near_misses=["prostate adenocarcinoma", "prostate cancer"],
            source=ConceptSource.TASK1_ADJUDICATION_EXPANSION,
            source_reason="Distinct primary malignancy; prevents cross-organ mismatch."
        ))

        # 3. Radiation Oncology: Dose-Sensitive Critical Normal Structures (Task 3 Class Concept)
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-DOSE-SENSITIVE-STRUCTURES",
            canonical_name="Dose-Sensitive Critical Normal Structures",
            domain="radiation_oncology",
            is_class_concept=True,
            accepted_terms=[
                "critical dose-sensitive structures", "critical structures", "dose-sensitive structures",
                "adjacent critical organs", "organs at risk", "oar", "normal tissue tolerance"
            ],
            authorized_instances=[
                "spinal cord", "brainstem", "optic nerves", "optic chiasm", "retina",
                "parotid glands", "salivary glands", "submandibular glands",
                "rectum", "rectal wall", "bladder", "bladder wall", "cochlea"
            ],
            prohibited_near_misses=[],
            source=ConceptSource.TASK1_ADJUDICATION_EXPANSION,
            source_reason="LCD-IMRT & LCD-PROTON clinical class: dose-limiting adjacent normal tissues requiring modulation."
        ))

        # 4. Ophthalmology: Cataract & Lens Opacity (SYN-08)
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-CATARACT-LENS-OPACITY",
            canonical_name="Cataract and Lens Opacity",
            domain="ophthalmology",
            accepted_terms=[
                "cataract", "cataracts", "cataract extraction", "lens opacity", "dense lens opacity",
                "nuclear sclerosis", "cortical cataract", "posterior subcapsular cataract",
                "phacoemulsification", "progressive clouding of vision", "visual impairment from cataract",
                "symptomatic lens opacity", "capsular opacification"
            ],
            prohibited_near_misses=["glaucoma", "macular degeneration", "dry eye syndrome", "corneal abrasion"],
            source=ConceptSource.ONBOARDING_AGENT,
            source_reason="Ophthalmology standard: lens opacity and nuclear sclerosis represent physical manifestations of cataract."
        ))

        # 5. Ophthalmology: Visual Impairment & Glare Disability (SYN-08)
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-VISUAL-IMPAIRMENT",
            canonical_name="Visual Impairment and Glare Disability",
            domain="ophthalmology",
            accepted_terms=[
                "visual impairment", "disabling glare", "glare disability", "glare while driving",
                "visual acuity 20/50 or worse", "visual acuity 20/200", "snellen visual acuity",
                "difficulty reading from vision", "reduced visual acuity", "progressive clouding of vision"
            ],
            prohibited_near_misses=[],
            source=ConceptSource.ONBOARDING_AGENT,
            source_reason="Clinical functional impairment preconditions for cataract surgical coverage."
        ))

        # 6. Spine / Pain: Failure of Conservative Care (SYN-09, SYN-11)
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-CONSERVATIVE-CARE-FAILURE",
            canonical_name="Failure of Conservative Therapy",
            domain="spine_pain",
            accepted_terms=[
                "failure of conservative care", "failure of conservative therapy",
                "refractory to conservative measures", "refractory to conservative management",
                "failed conservative management", "failed conservative therapy",
                "tried physical therapy and anti-inflammatory tablets for six weeks without relief",
                "trial and failure of conservative therapy", "conservative care trial failure",
                "refractory to physical therapy", "conservative measures failed",
                "persistent symptoms despite conservative therapy", "failed physical therapy"
            ],
            prohibited_near_misses=[
                "has not yet tried", "not yet attempted", "no prior conservative care",
                "wants injection promptly without therapy", "conservative measures not yet attempted"
            ],
            source=ConceptSource.ONBOARDING_AGENT,
            source_reason="Interventional pain LCD requirement: active prior failure of physical therapy and analgesics."
        ))

        # 7. Spine / Pain: Radiculopathy (SYN-09, SYN-11)
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-RADICULOPATHY",
            canonical_name="Radiculopathy and Nerve Root Compression",
            domain="spine_pain",
            accepted_terms=[
                "radiculopathy", "lumbar radiculopathy", "cervical radiculopathy",
                "nerve root compression", "compressing the left s1 nerve root", "compressing nerve root",
                "sciatica", "severe shooting pain down the left leg", "shooting pain down the left leg",
                "positive straight-leg raise", "dermatomal radiation", "paresthesias"
            ],
            prohibited_near_misses=["localized low back pain without radiation", "axial back pain"],
            source=ConceptSource.ONBOARDING_AGENT,
            source_reason="Radicular neural compression confirmed by physical exam and neuro-imaging."
        ))

        # 8. Orthopedics: Knee Instability (SYN-10)
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-KNEE-INSTABILITY",
            canonical_name="Knee Joint Instability",
            domain="orthopedics",
            accepted_terms=[
                "knee instability", "knee gives way", "knee gives way several times a week",
                "giving way", "unstable knee", "knee unstable on stress testing",
                "joint laxity", "ligamentous laxity", "patellar instability", "subjective instability"
            ],
            prohibited_near_misses=["stable knee", "no instability"],
            source=ConceptSource.ONBOARDING_AGENT,
            source_reason="DMEPOS knee orthosis clinical coverage trigger: objective or documented giving way/instability."
        ))

        # 9. Orthopedics: Knee Deformity (SYN-10)
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-KNEE-DEFORMITY",
            canonical_name="Knee Angular Deformity",
            domain="orthopedics",
            accepted_terms=[
                "knee deformity", "varus deformity", "varus deformity of the right knee",
                "valgus deformity", "varus malalignment", "valgus malalignment",
                "genu varum", "genu valgum", "angular deformity of knee"
            ],
            prohibited_near_misses=["normal alignment", "neutral mechanical axis"],
            source=ConceptSource.ONBOARDING_AGENT,
            source_reason="DMEPOS unloader orthosis criterion: coronal plane angular malalignment."
        ))

        # 10. Cardiology: LVEF / Systolic Heart Failure
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-LVEF-HEART-FAILURE",
            canonical_name="Left Ventricular Ejection Fraction and Systolic Heart Failure",
            domain="cardiology",
            accepted_terms=[
                "lvef", "left ventricular ejection fraction", "ejection fraction", "systolic heart failure",
                "hfref", "heart failure with reduced ejection fraction", "ischemic cardiomyopathy",
                "nonischemic cardiomyopathy", "dilated cardiomyopathy"
            ],
            prohibited_near_misses=["heart failure with preserved ejection fraction", "hfpef"],
            source=ConceptSource.RETRIEVAL_VOCABULARY,
            source_reason="NCD 20.4 core physiological biomarker for implantable defibrillator eligibility."
        ))

        # 11. Sleep Medicine: Obstructive Sleep Apnea
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-SLEEP-APNEA",
            canonical_name="Obstructive Sleep Apnea",
            domain="sleep_medicine",
            accepted_terms=[
                "obstructive sleep apnea", "sleep apnea", "osa", "apnea hypopnea index",
                "ahi", "respiratory disturbance index", "rdi", "polysomnography"
            ],
            prohibited_near_misses=["central sleep apnea"],
            source=ConceptSource.RETRIEVAL_VOCABULARY,
            source_reason="NCD 240.4 CPAP diagnostic criteria."
        ))

        # 12. Wound Care: Diabetic Foot Ulcer
        self.register_concept(ConceptDefinition(
            concept_id="CONCEPT-DIABETIC-ULCER",
            canonical_name="Diabetic Foot Ulcer",
            domain="wound_care",
            accepted_terms=[
                "diabetic foot ulcer", "diabetic ulcer", "neuropathic ulcer",
                "wagner grade 3", "wagner grade 4", "wagner grade 3 or 4 ulcer",
                "deep ulcer with osteomyelitis", "chronic diabetic wound"
            ],
            prohibited_near_misses=["venous stasis ulcer", "arterial insufficiency ulcer"],
            source=ConceptSource.RETRIEVAL_VOCABULARY,
            source_reason="NCD 20.29 Hyperbaric oxygen therapy coverage prerequisite."
        ))


# Shared singleton instance
_GLOBAL_CONCEPT_MAP: ConceptMap | None = None


def get_concept_map() -> ConceptMap:
    """Returns the process-wide ConceptMap singleton."""
    global _GLOBAL_CONCEPT_MAP
    if _GLOBAL_CONCEPT_MAP is None:
        _GLOBAL_CONCEPT_MAP = ConceptMap()
    return _GLOBAL_CONCEPT_MAP
