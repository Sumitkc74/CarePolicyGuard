from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict

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

class CriterionAssessment(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    criterion_id: Union[int, str] = Field(..., description="Unique criterion identifier")
    criterion_code: str = Field(..., description="Short code, e.g. CRIT-ICD-01")
    name: str = Field(default="", description="Criterion display name")
    description: str = Field(..., description="Full text description of policy criterion")
    is_exclusion: bool = Field(default=False, description="True if meeting this criterion excludes coverage")
    required_temporal_window: str = Field(default="Not specified", description="Required temporal preconditions")
    status: DeterminationStatus = Field(..., description="Evaluation status (MET, NOT_MET, INSUFFICIENT_EVIDENCE)")
    verified_spans: List[ClinicalEvidenceSpan] = Field(default_factory=list, description="Verified character-anchored clinical citations")
    clinical_rationale: str = Field(..., description="Reasoning mapping clinical facts to policy requirement")
    raw_confidence: float = Field(..., ge=0.0, le=1.0, description="Uncalibrated model confidence score")
    temporal_window_met: Optional[bool] = Field(default=None, description="Whether temporal prerequisite was satisfied")

class VerificationAuditResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    criterion_code: str = Field(..., description="Code of audited criterion")
    grounding_status: bool = Field(..., description="True if evidence spans match character-for-character against source text")
    hallucination_flag: bool = Field(..., description="True if claimed evidence does not exist in EHR note")
    unverified_omission_flag: bool = Field(..., description="True if criterion was marked NOT_MET but salient clinical terms exist in note without citation")
    offset_drift_detected: bool = Field(..., description="True if text exists but start/end offsets drift from slice")
    discordance_flag: bool = Field(default=False, description="True if conflicting diagnostic measurements or internal contradictions exist across sections")
    healed_offset_drift: bool = Field(default=False, description="True if offset drift was autonomously healed by feedback loop")
    audit_notes: str = Field(..., description="Detailed adversarial verification audit findings")
    calibrated_confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence recalibrated after adversarial penalization")

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
    detected_cpt_codes: List[CodingMatch] = Field(default_factory=list)
    detected_icd10_codes: List[CodingMatch] = Field(default_factory=list)
    carc_codes: List[Dict[str, str]] = Field(default_factory=list)
    rarc_codes: List[Dict[str, str]] = Field(default_factory=list)
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
    milestones: List[TimelineMilestone] = Field(default_factory=list)
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
    calibrated_aggregate_confidence: float = Field(..., ge=0.0, le=1.0, description="Aggregate calibrated confidence after adversarial audit")
    abstention_threshold: float = Field(default=0.85, description="Confidence threshold tau below which system must abstain")
    abstention_reason: Optional[str] = Field(default=None, description="Detailed trigger rationale if abstention was activated")
    criterion_assessments: List[CriterionAssessment] = Field(default_factory=list, description="Criterion-by-criterion evaluation breakdown")
    verification_audits: List[VerificationAuditResult] = Field(default_factory=list, description="Adversarial verification results per criterion")
    audit_hash: str = Field(..., description="Cryptographic SHA-256 chain-of-custody seal over adjudication bundle")
    required_clinician_action_notes: Optional[str] = Field(default=None, description="Actionable checklist items for clinical auditor")
    execution_time_ms: float = Field(default=0.0, description="Total pipeline latency in milliseconds")
    sanitized_ehr_text: str = Field(..., description="PHI-sanitized patient EHR note used in evaluation")
    timestamp: datetime = Field(..., description="Adjudication execution timestamp")
    billing_validation: Optional[BillingValidationResult] = None
    timeline_analysis: Optional[TimelineAnalysisResult] = None
    carc_codes: List[Dict[str, str]] = Field(default_factory=list)
    rarc_codes: List[Dict[str, str]] = Field(default_factory=list)

# Request / Response DTOs
class PolicyMatchSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    policy_id: str
    policy_title: str
    category: str
    decision: AdjudicationDecision
    calibrated_confidence: float
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
    options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Pipeline configuration overrides (e.g. tau, debug)")

class MultiPolicyScanResponse(BaseModel):
    patient_id_masked: str
    total_policies_scanned: int
    approved_count: int
    denied_count: int
    deferred_count: int
    best_match_policy_id: Optional[str] = None
    best_match_title: Optional[str] = None
    all_matches: List[PolicyMatchSummary]
    multi_morbidity_insights: List[str] = Field(default_factory=list)
    execution_time_ms: float
    timestamp: datetime

class AdjudicationRequest(BaseModel):
    patient_id: str = Field(default="PT-10829", description="Patient or record identifier")
    policy_id: str = Field(..., description="Selected Medicare LCD or NCD policy ID (e.g., NCD-20.4)")
    ehr_narrative: str = Field(..., min_length=20, description="Raw clinical EHR documentation / progress note")
    cpt_codes: Optional[List[str]] = Field(default=None, description="Optional procedure codes to validate")
    icd10_codes: Optional[List[str]] = Field(default=None, description="Optional diagnosis codes to validate")
    options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Pipeline configuration overrides (e.g. tau, debug)")

class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    expires_in_seconds: int

class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "Clinician"
    # Medical Professional Verification Fields
    full_name: Optional[str] = None
    npi_number: Optional[str] = None
    credential_title: Optional[str] = None  # MD, DO, NP, PA-C, MBBS, CRNA, PharmD
    medical_license: Optional[str] = None
    license_state: Optional[str] = None
    specialty: Optional[str] = None
    organization: Optional[str] = None

class MedicalVerificationRequest(BaseModel):
    npi_number: str
    email: str
    credential_title: str
    medical_license: str
    license_state: str
    organization: Optional[str] = None

class MedicalVerificationResponse(BaseModel):
    is_verified: bool
    npi_valid: bool
    email_valid: bool
    credentials_valid: bool
    state_license_valid: bool
    organization_valid: bool
    message: str
    reasons: List[str] = []

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: str
    is_active: bool
    npi_number: Optional[str] = None
    credential_title: Optional[str] = None
    license_state: Optional[str] = None
    organization: Optional[str] = None
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
    criteria: List[CriterionOut]

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    case_id: str
    patient_id_masked: str
    policy_id: str
    decision: str
    abstention_status: bool
    abstention_reason: Optional[str]
    calibrated_confidence: float
    raw_confidence: float
    criterion_evaluations_json: str
    evidence_spans_json: str
    adversarial_audits_json: str
    required_clinician_action_notes: Optional[str]
    audit_hash: str
    sanitized_ehr_preview: str
    execution_time_ms: float
    submission_status: Optional[str] = "PENDING_REVIEW"
    signed_by: Optional[str] = None
    signed_at: Optional[datetime] = None
    payer_transaction_id: Optional[str] = None
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
    configs: List[BenchmarkConfigMetrics]
    vignette_results: List[VignetteEvaluationResult] = Field(default_factory=list)
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
    icd10_codes: List[str]
    cpt_hcpcs_codes: List[str]
    clinical_summary: str
    criteria_sections: List[FilledCriterionSection]
    adjudication_decision: str
    abstention_status: bool
    calibrated_confidence: float
    audit_hash: str
    submission_status: str  # PENDING_CLINICIAN_REVIEW, SUBMITTED_TO_PAYER
    signed_by: Optional[str] = None
    signed_at: Optional[str] = None
    payer_transaction_id: Optional[str] = None
    clinician_action_notes: Optional[str] = None
    authorization_validity_period: Optional[str] = "180 calendar days from date of determination"
    shared_decision_making_attestation: Optional[str] = None

class SubmitPacketRequest(BaseModel):
    case_id: str
    signed_by: str
    clinician_notes: Optional[str] = None
    payer_name: Optional[str] = "CMS Medicare MAC Gateway"

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
    physician_name: Optional[str] = None
    physician_npi: Optional[str] = None
    physician_specialty: Optional[str] = None
    reconsideration_notes: Optional[str] = None

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
    clinical_guideline_citations: List[str]
    peer_to_peer_talking_points: List[str]
    full_letter_text: str
    audit_hash: str

class EHRPushRequest(BaseModel):
    case_id: str
    ehr_system: Optional[str] = "Epic Systems FHIR R4 / Da Vinci PAS"
    encounter_id: Optional[str] = None

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
    criterion_code: Optional[str] = Field(default=None, description="Criterion code being addressed, e.g. CRIT-ICD-04")
    addendum_text: str = Field(..., min_length=10, description="Clinician's attested addendum narrative")
    clinician_name: Optional[str] = Field(default="Attending Physician", description="Name of signing clinician")
    clinician_npi: Optional[str] = Field(default="1043256787", description="10-digit NPI of signing clinician")

class ClinicalAddendumResponse(BaseModel):
    case_id: str
    status: str
    addendum_id: str
    criterion_addressed: Optional[str]
    appended_at: str
    signed_by: str
    signed_npi: str
    prior_decision: str
    updated_decision: str
    updated_confidence: float
    audit_hash: str
    updated_adjudication: FinalAdjudication
    message: str

class AuditTrailEvent(BaseModel):
    event_id: str
    timestamp: str
    event_type: str  # ADJUDICATION, AMENDMENT, AUTHENTICATION, SUBMISSION, EHR_PUSH, ERASURE
    case_id: Optional[str]
    patient_id_masked: Optional[str]
    actor: str
    actor_role: str
    action_details: str
    audit_hash: str

class AuditTrailResponse(BaseModel):
    total_events: int
    system_mode: str
    events: List[AuditTrailEvent]

class BatchAdjudicationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    patient_id: Optional[str] = Field(default=None, description="Patient identifier (will be masked under HIPAA Safe Harbor)")
    policy_id: str = Field(..., description="Target policy ID, e.g. NCD-20.4 or LCD-L33829")
    clinical_narrative: str = Field(..., min_length=15, description="De-identified or raw clinical progress note")
    requested_procedure_code: Optional[str] = Field(default=None, description="CPT/HCPCS code, e.g. 33249")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom metadata or roster tags")

class BatchAdjudicationRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    batch_name: Optional[str] = Field(default="Clinical Roster Batch", description="Label for this multi-patient cohort")
    items: List[BatchAdjudicationItem] = Field(..., min_length=1, max_length=50, description="List of patient notes to adjudicate")
    webhook_url: Optional[str] = Field(default=None, description="Optional outbound HTTPS webhook URL for notification upon batch completion")
    webhook_secret: Optional[str] = Field(default=None, description="Shared secret for signing webhook payload with HMAC-SHA256")

class BatchAdjudicationItemResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    index: int
    patient_id_masked: str
    policy_id: str
    decision: AdjudicationDecision
    calibrated_confidence: float
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
    webhook_delivered: Optional[bool] = Field(default=None, description="Whether the outbound completion webhook was successfully dispatched")
    results: List[BatchAdjudicationItemResult]


