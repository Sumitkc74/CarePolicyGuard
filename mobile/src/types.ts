export interface ClinicalEvidenceSpan {
  source_text: string;
  start_char: number;
  end_char: number;
  clinical_section: string;
  confidence: number;
}

export interface CriterionAssessment {
  criterion_id: string | number;
  criterion_code: string;
  name: string;
  description: string;
  is_exclusion: boolean;
  required_temporal_window: string;
  status: "MET" | "NOT_MET" | "INSUFFICIENT_EVIDENCE";
  verified_spans: ClinicalEvidenceSpan[];
  clinical_rationale: string;
  raw_confidence: number;
}

export interface FinalAdjudication {
  case_id: string;
  patient_id_masked: string;
  policy_id: string;
  policy_title: string;
  adjudication_decision: "APPROVED" | "DENIED" | "DEFERRED_TO_HUMAN";
  abstention_status: boolean;
  raw_aggregate_confidence: number;
  calibrated_aggregate_confidence: number;
  abstention_threshold: number;
  abstention_reason?: string;
  criterion_assessments: CriterionAssessment[];
  audit_hash: string;
  execution_time_ms: number;
  sanitized_ehr_text: string;
  timestamp: string;
}

export interface PeerToPeerAppealLetter {
  appeal_id: string;
  case_id: string;
  patient_id_masked: string;
  policy_id: string;
  policy_title: string;
  physician_name: string;
  physician_npi: string;
  date_of_service: string;
  appeal_date: string;
  denial_rationale: string;
  statutory_legal_basis: string;
  clinical_guideline_citations: string[];
  peer_to_peer_talking_points: string[];
  full_letter_text: string;
  audit_hash: string;
}

export interface MedicarePolicy {
  policy_id: string;
  title: string;
  category: string;
  description: string;
}

