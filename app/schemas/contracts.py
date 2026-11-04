from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeterminationStatus(str, Enum):
    MET = "MET"
    NOT_MET = "NOT_MET"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

class AdjudicationDecision(str, Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    DEFERRED_TO_HUMAN = "DEFERRED_TO_HUMAN"

class ClinicalEvidenceSpan(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_text: str = Field(..., description="Exact clinical text extracted from patient note")
    start_char: int = Field(..., description="Exact 0-indexed start character offset in original note")
    end_char: int = Field(..., description="Exact 0-indexed end character offset in original note")
    clinical_section: str = Field(default="Clinical Note", description="EHR section where evidence was found")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence in this span")
    semantic_support_passed: bool = Field(default=True, description="True if semantic validation (subject, timing, modality, negation, range) passes")
    subject_valid: bool = Field(default=True, description="True if experiencer is the patient, not family history or other party")
    timing_valid: bool = Field(default=True, description="True if event is actual/current, not future planned or resolved historical")
    modality_valid: bool = Field(default=True, description="True if modality is confirmed, not hypothetical or conditional")
    negation_valid: bool = Field(default=True, description="True if unnegated in active clinical clause")
    value_in_range: bool = Field(default=True, description="True if numeric measurement falls within statutory threshold")
    semantic_invalidation_reasons: list[str] = Field(default_factory=list, description="Specific semantic failure reasons if disqualified")

class CriterionAssessment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    criterion_id: int | str = Field(..., description="Unique criterion identifier")
    criterion_code: str = Field(..., description="Short code, e.g. CRIT-ICD-01")
    name: str = Field(default="", description="Criterion display name")
    description: str = Field(..., description="Full text description of policy criterion")
    is_exclusion: bool = Field(default=False, description="True if meeting this criterion excludes coverage")
    required_temporal_window: str = Field(default="Not specified", description="Required temporal preconditions")
    status: DeterminationStatus = Field(..., description="Evaluation status (MET, NOT_MET, INSUFFICIENT_EVIDENCE)")
    verified_spans: list[ClinicalEvidenceSpan] = Field(default_factory=list, description="Verified character-anchored clinical citations")
    clinical_rationale: str = Field(..., description="Reasoning mapping clinical facts to policy requirement")
    raw_confidence: float = Field(..., ge=0.0, le=1.0, description="Uncalibrated model confidence score")
    temporal_window_met: bool | None = Field(default=None, description="Whether temporal prerequisite was satisfied")

class VerificationAuditResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    criterion_code: str = Field(..., description="Code of audited criterion")
    grounding_status: bool = Field(..., description="True if evidence spans match character-for-character against source text")
    hallucination_flag: bool = Field(..., description="True if claimed evidence does not exist in EHR note")
    unverified_omission_flag: bool = Field(..., description="True if criterion was marked NOT_MET but salient clinical terms exist in note without citation")
    offset_drift_detected: bool = Field(..., description="True if text exists but start/end offsets drift from slice")
    discordance_flag: bool = Field(default=False, description="True if conflicting diagnostic measurements or internal contradictions exist across sections")
    healed_offset_drift: bool = Field(default=False, description="True if offset drift was autonomously healed by feedback loop")
    semantic_support_passed: bool = Field(default=True, description="True if all supporting evidence spans pass semantic integrity checks")
    semantic_audit_notes: str | None = Field(default=None, description="Detailed semantic breakdown (subject, timing, modality, negation, range)")
    discordance_details: str | None = Field(default=None, description="Specific details of conflicting clinical values or dates")
    audit_notes: str = Field(..., description="Detailed adversarial verification audit findings")
    calibrated_confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Confidence recalibrated after adversarial penalization (null if uncalibrated)")
    sufficiency_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Heuristic sufficiency score for this criterion")

class CodingMatch(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    description: str
    status: str  # "COVERED", "NON_COVERED", "UNSPECIFIED"
    rationale: str

class BillingValidationResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    policy_id: str
    is_billing_compliant: bool
    is_cpt_covered: bool
    is_icd10_covered: bool
    detected_cpt_codes: list[CodingMatch] = Field(default_factory=list)
    detected_icd10_codes: list[CodingMatch] = Field(default_factory=list)
    carc_codes: list[dict[str, str]] = Field(default_factory=list)
    rarc_codes: list[dict[str, str]] = Field(default_factory=list)
    billing_advisory: str

class TimelineMilestone(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    event_label: str
    event_date: str
    evaluation_date: str
    elapsed_days: int
    required_days: int
    deficit_days: int
    status: str  # "SATISFIED", "WAITING_PERIOD_UNMET", "NOT_SPECIFIED"
    citation: str
    advisory: str

class TimelineAnalysisResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    policy_id: str
    all_waiting_periods_satisfied: bool
    milestones: list[TimelineMilestone] = Field(default_factory=list)
    overall_timeline_advisory: str

class FinalAdjudication(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: str = Field(..., description="Unique deterministic case adjudication identifier")
    patient_id_masked: str = Field(..., description="Sanitized/masked patient identifier")
    policy_id: str = Field(..., description="Governing Medicare policy ID (e.g., NCD-20.4)")
    policy_title: str = Field(..., description="Full official Medicare policy title")
    adjudication_decision: AdjudicationDecision = Field(..., description="Final decision: APPROVED, DENIED, or DEFERRED_TO_HUMAN")
    abstention_status: bool = Field(..., description="True if autonomous decision was withheld and deferred to human review")
    raw_aggregate_confidence: float = Field(..., ge=0.0, le=1.0, description="Average uncalibrated extraction confidence")
    calibrated_aggregate_confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Empirical post-hoc calibrated confidence (only populated when fitted on held-out validation data; null otherwise)")
    calibrated_confidence_explanation: str | None = Field(default="No empirical calibration model fitted on held-out validation data; reporting heuristic sufficiency score", description="Explanation of calibration provenance or why calibrated_aggregate_confidence is null")
    abstention_threshold: float = Field(default=0.85, description="Operating sufficiency threshold tau below which system abstains")
    abstention_reason: str | None = Field(default=None, description="Detailed trigger rationale if abstention was activated")
    criterion_assessments: list[CriterionAssessment] = Field(default_factory=list, description="Criterion-by-criterion evaluation breakdown")
    verification_audits: list[VerificationAuditResult] = Field(default_factory=list, description="Adversarial verification results per criterion")
    audit_hash: str = Field(..., description="Cryptographic SHA-256 chain-of-custody seal over adjudication bundle")
    required_clinician_action_notes: str | None = Field(default=None, description="Actionable checklist items for clinical auditor")
    execution_time_ms: float = Field(default=0.0, description="Total pipeline latency in milliseconds")
    sanitized_ehr_text: str = Field(..., description="PHI-sanitized patient EHR note used in evaluation")
    timestamp: datetime = Field(..., description="Adjudication execution timestamp")
    billing_validation: BillingValidationResult | None = None
    timeline_analysis: TimelineAnalysisResult | None = None
    carc_codes: list[dict[str, str]] = Field(default_factory=list)
    rarc_codes: list[dict[str, str]] = Field(default_factory=list)
    execution_mode: str = Field(default="deterministic", description="Adjudication engine utilized: deterministic or state_machine")
    state_transitions: list[dict[str, Any]] | None = Field(default=None, description="State machine audit transitions if executed under state_machine mode")
    retrieval_insights: dict[str, Any] | None = Field(default=None, description="Hybrid retrieval candidate ranking if policy was auto-discovered")

    # Honest Scope & Sign-off Gate Architecture (Task 1 & Task 6)
    determination_stage: str = Field(
        default="PROVISIONAL",
        description="Determination release lifecycle stage: 'PROVISIONAL' (system output, non-releasable pre-check) or 'FINAL' (released only after recorded human sign-off)"
    )
    is_releasable: bool = Field(
        default=False,
        description="True only if human sign-off has occurred; provisional determinations cannot be released or exported as final"
    )
    determination_scope: str = Field(
        default="Checked: curated CMS statutory criteria. Not checked: plan-specific rules, member eligibility, network status. Requires human clinical review and sign-off before official transmission.",
        description="Explicit scope of checked CMS criteria vs unchecked plan/eligibility rules"
    )
    human_sign_off_status: str = Field(
        default="PENDING_CLINICAL_SIGN_OFF",
        description="Human sign-off status: PENDING_CLINICAL_SIGN_OFF, SIGNED_OFF, or OVERRIDDEN"
    )
    signed_off_by: str | None = Field(default=None, description="Name or identifier of licensed clinician who reviewed and signed off")
    signed_off_at: str | None = Field(default=None, description="Timestamp of clinical sign-off")
    audit_hash_type: str = Field(
        default="tamper_evident_integrity_seal",
        description="Tamper-evident record hash certifying post-creation integrity and reproducibility, not medical correctness"
    )
    plain_language_disclaimer: str = Field(
        default=(
            "Notice: This coverage determination pre-check is based solely on curated CMS coverage criteria. "
            "Plan-specific coverage rules and real-time patient eligibility were not evaluated. "
            "This output requires review and sign-off by a licensed clinical professional before any authorization or claim submission."
        ),
        description="Mandatory plain-language clinical disclaimer"
    )

    # Heuristic Sufficiency Reporting (Task 2)
    score_type: str = Field(
        default="sufficiency_score",
        description="Explicit classification of confidence score: sufficiency_score (heuristic criteria weight) rather than calibrated probability"
    )
    sufficiency_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Heuristic sufficiency score based on verified criteria")
    sufficiency_formula: str = Field(
        default="criteria_sufficiency_weighted_sum / total_applicable_criteria",
        description="Documented formula for sufficiency score computation"
    )
    criteria_met_count: int = Field(default=0, description="Count of criteria meeting statutory requirements")
    criteria_total_count: int = Field(default=0, description="Total criteria evaluated")
    missing_criteria: list[str] = Field(default_factory=list, description="Codes of missing criteria required for coverage")
    insufficient_criteria: list[str] = Field(default_factory=list, description="Codes of criteria with insufficient documentation")
    deferral_reason: str | None = Field(default=None, description="Clinical reason for deferral if deferred to human")

    # Multi-Agent Coordination & Disagreement Tracking (Task 4)
    critic_findings: dict[str, Any] | None = Field(default=None, description="Critic agent counter-evidence and falsification audit findings")
    agent_disagreements: list[dict[str, Any]] = Field(default_factory=list, description="Recorded agent disagreements resolved by deterministic veto")
    action_required_questions: list[str] = Field(default_factory=list, description="Targeted clinical questions formulated by MissingEvidenceAgent for human reviewer")
    human_override: dict[str, Any] | None = Field(default=None, description="Recorded human override preserving original system determination")
    original_system_output_json: str | None = Field(default=None, description="Byte-identical JSON serialization of original system determination prior to human override")

# Request / Response DTOs
class PolicyMatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    policy_id: str
    policy_title: str
    category: str
    decision: AdjudicationDecision
    calibrated_confidence: float | None = None
    score_type: str = "sufficiency_score"
    sufficiency_score: float = 0.0
    sufficiency_formula: str = "criteria_sufficiency_weighted_sum / total_applicable_criteria"
    relevance_score: float = 0.0
    total_criteria: int
    met_criteria: int
    unmet_criteria: int
    is_best_match: bool = False
    clinical_rationale: str
    adjudication: FinalAdjudication

class MultiPolicyScanRequest(BaseModel):
    patient_id: str = Field(default="PT-10829", description="Patient or record identifier")
    ehr_narrative: str = Field(..., min_length=20, description="Raw clinical EHR documentation / progress note")
    options: dict[str, Any] | None = Field(default_factory=dict, description="Pipeline configuration overrides (e.g. tau, debug)")

class MultiPolicyScanResponse(BaseModel):
    patient_id_masked: str
    total_policies_scanned: int
    approved_count: int
    denied_count: int
    deferred_count: int
    best_match_policy_id: str | None = None
    best_match_title: str | None = None
    all_matches: list[PolicyMatchSummary]
    multi_morbidity_insights: list[str] = Field(default_factory=list)
    execution_time_ms: float
    timestamp: datetime

class AdjudicationRequest(BaseModel):
    patient_id: str = Field(default="PT-10829", description="Patient or record identifier")
    policy_id: str | None = Field(default="AUTO", description="Selected Medicare LCD or NCD policy ID (e.g., NCD-20.4), or 'AUTO' for hybrid retrieval auto-discovery")
    ehr_narrative: str = Field(default="", description="Raw clinical EHR documentation / progress note")
    cpt_codes: list[str] | None = Field(default=None, description="Optional procedure codes to validate")
    icd10_codes: list[str] | None = Field(default=None, description="Optional diagnosis codes to validate")
    execution_mode: str | None = Field(
        default="deterministic",
        description="Adjudication engine: 'deterministic' (production rule pipeline), 'declarative' (production declarative schema engine), or 'state_machine' [EXPERIMENTAL] (multi-pass extractor with explicit state transitions). Note: state_machine mode is labeled EXPERIMENTAL due to lower precision and safety vulnerability on unconstrained clinical phrasing."
    )
    options: dict[str, Any] | None = Field(default_factory=dict, description="Pipeline configuration overrides (e.g. tau, debug)")

class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: str | None = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    expires_in_seconds: int
    full_name: str | None = None
    npi_number: str | None = None
    credential_title: str | None = None
    specialty: str | None = None
    organization: str | None = None

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "Clinician"
    # Medical Professional Verification Fields
    full_name: str | None = None
    npi_number: str | None = None
    credential_title: str | None = None  # MD, DO, NP, PA-C, MBBS, CRNA, PharmD
    medical_license: str | None = None
    license_state: str | None = None
    specialty: str | None = None
    organization: str | None = None

class MedicalVerificationRequest(BaseModel):
    npi_number: str
    email: str
    credential_title: str
    medical_license: str
    license_state: str
    organization: str | None = None

class MedicalVerificationResponse(BaseModel):
    is_verified: bool
    npi_valid: bool
    email_valid: bool
    credentials_valid: bool
    state_license_valid: bool
    organization_valid: bool
    message: str
    reasons: list[str] = []

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: str
    is_active: bool
    full_name: str | None = None
    npi_number: str | None = None
    credential_title: str | None = None
    license_state: str | None = None
    specialty: str | None = None
    organization: str | None = None
    is_verified_medical_pro: bool = False
    created_at: datetime

class CriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    criterion_code: str
    name: str
    description: str
    clinical_intent: str
    is_exclusion: bool
    required_temporal_window: str
    keywords: str
    min_score: float

class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    policy_id: str
    title: str
    jurisdiction: str
    effective_date: str
    description: str
    category: str
    criteria: list[CriterionOut]

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: str
    patient_id_masked: str
    policy_id: str
    decision: str
    abstention_status: bool
    abstention_reason: str | None
    calibrated_confidence: float | None = None
    sufficiency_score: float | None = None
    raw_confidence: float
    criterion_evaluations_json: str
    evidence_spans_json: str
    adversarial_audits_json: str
    required_clinician_action_notes: str | None
    audit_hash: str
    sanitized_ehr_preview: str
    execution_time_ms: float
    submission_status: str | None = "PENDING_REVIEW"
    signed_by: str | None = None
    signed_at: datetime | None = None
    payer_transaction_id: str | None = None
    created_at: datetime

class BenchmarkConfigMetrics(BaseModel):
    config_name: str
    label: str
    description: str
    accuracy: float
    evidence_faithfulness: float
    expected_calibration_error: float
    abstention_rate: float
    latency_ms: float
    clinical_safety_score: float

class VignetteEvaluationResult(BaseModel):
    vignette_id: str
    policy_id: str
    name: str
    clinical_domain: str
    gold_decision: str
    config_a_decision: str
    config_b_decision: str
    config_c_decision: str
    config_d_decision: str
    config_d_confidence: float
    config_d_grounded: bool
    config_d_abstain: bool
    status_match: bool

class BenchmarkResponse(BaseModel):
    dataset_size: int
    total_evaluations: int
    abstention_threshold: float
    configs: list[BenchmarkConfigMetrics]
    vignette_results: list[VignetteEvaluationResult] = Field(default_factory=list)
    comparative_analysis: str

# Document Prior Authorization & Insurance Submission Models
class FilledCriterionSection(BaseModel):
    criterion_code: str
    name: str
    status: str
    required_temporal_window: str
    extracted_evidence_quote: str
    clinical_rationale: str
    physician_attestation: str

class CMSCoveragePacket(BaseModel):
    packet_id: str
    case_id: str
    patient_id_masked: str
    policy_id: str
    policy_title: str
    jurisdiction: str
    date_of_service: str
    icd10_codes: list[str]
    cpt_hcpcs_codes: list[str]
    clinical_summary: str
    criteria_sections: list[FilledCriterionSection]
    adjudication_decision: str
    abstention_status: bool
    calibrated_confidence: float | None = None
    calibrated_confidence_explanation: str | None = "No empirical calibration model fitted on held-out validation data; reporting heuristic sufficiency score"
    score_type: str = "sufficiency_score"
    sufficiency_score: float = 0.0
    sufficiency_formula: str = "criteria_sufficiency_weighted_sum / total_applicable_criteria"
    determination_stage: str = Field(default="PROVISIONAL", description="Determination release lifecycle stage: 'PROVISIONAL' or 'FINAL'")
    is_releasable: bool = Field(default=False, description="True only after recorded human sign-off")
    human_sign_off_status: str = Field(default="PENDING_CLINICAL_SIGN_OFF", description="Sign-off status")
    audit_hash: str
    submission_status: str  # PENDING_CLINICIAN_REVIEW, SUBMITTED_TO_PAYER
    signed_by: str | None = None
    signed_at: str | None = None
    payer_transaction_id: str | None = None
    clinician_action_notes: str | None = None
    authorization_validity_period: str | None = "180 calendar days from date of determination"
    shared_decision_making_attestation: str | None = None

class SignOffRequest(BaseModel):
    signed_by: str | None = Field(default=None, description="Optional clinician name; verified user profile identity is authoritatively used")
    clinician_npi: str | None = Field(default=None, description="Clinician NPI")
    clinician_credentials: str | None = Field(default=None, description="Clinician title e.g. MD, DO, FACC")
    attestation_notes: str | None = Field(default=None, description="Clinical attestation or sign-off notes")

class SignOffResponse(BaseModel):
    case_id: str
    determination_stage: str = "FINAL"
    human_sign_off_status: str = "SIGNED_OFF"
    is_releasable: bool = True
    signed_off_by: str
    signed_off_at: str
    message: str

class SubmitPacketRequest(BaseModel):
    case_id: str
    signed_by: str
    clinician_notes: str | None = None
    payer_name: str | None = "CMS Medicare MAC Gateway"

class SubmissionReceipt(BaseModel):
    case_id: str
    packet_id: str
    payer_transaction_id: str
    submission_status: str
    signed_by: str
    signed_at: str
    payer_name: str
    audit_hash: str
    message: str

class PeerToPeerAppealRequest(BaseModel):
    case_id: str
    physician_name: str | None = None
    physician_npi: str | None = None
    physician_specialty: str | None = None
    reconsideration_notes: str | None = None

class PeerToPeerAppealLetter(BaseModel):
    appeal_id: str
    case_id: str
    patient_id_masked: str
    policy_id: str
    policy_title: str
    physician_name: str
    physician_npi: str
    date_of_service: str
    appeal_date: str
    denial_rationale: str
    statutory_legal_basis: str
    clinical_guideline_citations: list[str]
    peer_to_peer_talking_points: list[str]
    full_letter_text: str
    audit_hash: str

class EHRPushRequest(BaseModel):
    case_id: str
    ehr_system: str | None = "Epic Systems FHIR R4 / Da Vinci PAS"
    encounter_id: str | None = None

class EHRPushReceipt(BaseModel):
    status: str
    ehr_system: str
    ehr_document_id: str
    case_id: str
    patient_id_masked: str
    fhir_resource_type: str = "Bundle"
    transmitted_at: str
    audit_hash: str
    message: str

class ClinicalAddendumRequest(BaseModel):
    criterion_code: str | None = Field(default=None, description="Criterion code being addressed, e.g. CRIT-ICD-04")
    addendum_text: str = Field(..., min_length=10, description="Clinician's attested addendum narrative")
    clinician_name: str | None = Field(default="Attending Physician", description="Name of signing clinician")
    clinician_npi: str | None = Field(default="1043256787", description="10-digit NPI of signing clinician")

class ClinicalAddendumResponse(BaseModel):
    case_id: str
    status: str
    addendum_id: str
    criterion_addressed: str | None
    appended_at: str
    signed_by: str
    signed_npi: str
    prior_decision: str
    updated_decision: str
    updated_confidence: float | None = None
    updated_sufficiency_score: float | None = None
    audit_hash: str
    updated_adjudication: FinalAdjudication
    message: str

class AuditTrailEvent(BaseModel):
    event_id: str
    timestamp: str
    event_type: str  # ADJUDICATION, AMENDMENT, AUTHENTICATION, SUBMISSION, EHR_PUSH, ERASURE
    case_id: str | None
    patient_id_masked: str | None
    actor: str
    actor_role: str
    action_details: str
    audit_hash: str
    audit_seal_certifies: str = Field(
        default="tamper_evident_integrity_and_reproducibility",
        description="Certifies post-creation record immutability and deterministic reproducibility, not clinical correctness"
    )

class AuditTrailResponse(BaseModel):
    total_events: int
    system_mode: str
    events: list[AuditTrailEvent]

class BatchAdjudicationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    patient_id: str | None = Field(default=None, description="Patient identifier (will be masked under HIPAA Safe Harbor)")
    policy_id: str = Field(..., description="Target policy ID, e.g. NCD-20.4 or LCD-L33829")
    clinical_narrative: str = Field(..., min_length=15, description="De-identified or raw clinical progress note")
    requested_procedure_code: str | None = Field(default=None, description="CPT/HCPCS code, e.g. 33249")
    metadata: dict[str, Any] | None = Field(default_factory=dict, description="Custom metadata or roster tags")

class BatchAdjudicationRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    batch_name: str | None = Field(default="Clinical Roster Batch", description="Label for this multi-patient cohort")
    items: list[BatchAdjudicationItem] = Field(..., min_length=1, max_length=50, description="List of patient notes to adjudicate")
    webhook_url: str | None = Field(default=None, description="Optional outbound HTTPS webhook URL for notification upon batch completion")
    webhook_secret: str | None = Field(default=None, description="Shared secret for signing webhook payload with HMAC-SHA256")

class BatchAdjudicationItemResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    index: int
    patient_id_masked: str
    policy_id: str
    decision: AdjudicationDecision
    score_type: str = "sufficiency_score"
    sufficiency_score: float | None = None
    calibrated_confidence: float | None = None
    raw_confidence: float
    abstention_status: bool
    adjudication: FinalAdjudication

class BatchAdjudicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    batch_id: str
    batch_name: str
    total_patients: int
    approved_count: int
    denied_count: int
    deferred_count: int
    processing_time_ms: float
    timestamp: str
    webhook_delivered: bool | None = Field(default=None, description="Whether the outbound completion webhook was successfully dispatched")
    results: list[BatchAdjudicationItemResult]


