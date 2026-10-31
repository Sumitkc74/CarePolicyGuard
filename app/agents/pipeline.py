import time
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import compute_audit_hash, sanitize_phi
from app.schemas.contracts import (
    FinalAdjudication,
    AdjudicationDecision,
    DeterminationStatus,
    PolicyMatchSummary,
    MultiPolicyScanResponse
)
from app.agents.policy_retriever import PolicyRetrievalAgent
from app.agents.criteria_evaluator import CriteriaEvaluationAgent
from app.agents.adversarial_verifier import AdversarialVerificationAgent
from app.agents.abstention_gate import CalibratedAbstentionGate
from app.services.hybrid_retriever import HybridPolicyRetriever
from app.agents.state_machine import ClinicalAdjudicationStateMachine
from app.db.models import AdjudicationLog, MedicarePolicy
from app.services.billing_validator import BillingValidatorService
from app.services.timeline_analyzer import TimelineAnalyzerService

class MultiAgentVerificationPipeline:
    """
    CarePolicyGuard: Asynchronous Multi-Agent Clinical Evidence & Coverage Verification Engine
    Orchestrates:
    - Agent 1: Policy Retrieval
    - Agent 2: Criteria Evaluation
    - Agent 3: Adversarial Verification
    - Agent 4: Calibrated Abstention Gate
    Computes cryptographic chain-of-custody audit hashes and persists tamper-evident logs.
    """

    def __init__(self, db: Optional[Session] = None):
        self.db = db
        self.retrieval_agent = PolicyRetrievalAgent(db=db)
        self.hybrid_retriever = HybridPolicyRetriever(db=db)
        self.evaluator_agent = CriteriaEvaluationAgent()
        self.verifier_agent = AdversarialVerificationAgent()
        self.abstention_gate = CalibratedAbstentionGate(tau=settings.ABSTENTION_THRESHOLD)
        self.state_machine = ClinicalAdjudicationStateMachine(db=db, tau=settings.ABSTENTION_THRESHOLD)

    async def adjudicate(
        self,
        patient_id: str,
        policy_id: Optional[str],
        ehr_narrative: str,
        user_id: Optional[int] = None,
        custom_tau: Optional[float] = None,
        save_record: bool = True,
        cpt_codes: Optional[List[str]] = None,
        icd10_codes: Optional[List[str]] = None,
        execution_mode: str = "deterministic",
    ) -> FinalAdjudication:
        """Asynchronous wrapper executing the end-to-end multi-agent clinical verification workflow."""
        return self.adjudicate_sync(
            patient_id=patient_id,
            policy_id=policy_id,
            ehr_narrative=ehr_narrative,
            user_id=user_id,
            custom_tau=custom_tau,
            save_record=save_record,
            cpt_codes=cpt_codes,
            icd10_codes=icd10_codes,
            execution_mode=execution_mode,
        )

    def adjudicate_sync(
        self,
        patient_id: str,
        policy_id: Optional[str],
        ehr_narrative: str,
        user_id: Optional[int] = None,
        custom_tau: Optional[float] = None,
        save_record: bool = True,
        cpt_codes: Optional[List[str]] = None,
        icd10_codes: Optional[List[str]] = None,
        execution_mode: str = "deterministic",
    ) -> FinalAdjudication:
        """
        Executes the end-to-end multi-agent clinical verification workflow.
        """
        start_time = time.perf_counter()
        timestamp = datetime.now(timezone.utc)
        case_id = f"CASE-{uuid.uuid4().hex[:12].upper()}"

        # 1. Compliance Layer: PHI Sanitization
        sanitized_ehr = sanitize_phi(ehr_narrative) if settings.ENABLE_PHI_MASKING else ehr_narrative
        masked_patient_id = f"PT-***{patient_id[-4:]}" if len(patient_id) > 4 else f"PT-***"

        # 1b. Policy Auto-Discovery via Hybrid Policy Retrieval (BM25 + Dense RRF)
        retrieval_insights = None
        is_auto_policy = (not policy_id) or str(policy_id).strip().upper() in ("AUTO", "AUTOMATIC", "DETECT", "HYBRID", "NONE")
        if is_auto_policy:
            hybrid_results = self.hybrid_retriever.retrieve_hybrid(sanitized_ehr, top_k=3)
            if hybrid_results:
                policy_id = hybrid_results[0]["policy_id"]
                retrieval_insights = {
                    "auto_discovered": True,
                    "selected_policy_id": policy_id,
                    "selected_policy_title": hybrid_results[0].get("policy_title", ""),
                    "candidates": hybrid_results
                }
            else:
                policy_id = "NCD-20.4"
                retrieval_insights = {
                    "auto_discovered": True,
                    "selected_policy_id": policy_id,
                    "selected_policy_title": "Implantable Automatic Defibrillators",
                    "candidates": []
                }
        else:
            hybrid_results = self.hybrid_retriever.retrieve_hybrid(sanitized_ehr, top_k=3)
            retrieval_insights = {
                "auto_discovered": False,
                "selected_policy_id": policy_id,
                "candidates": hybrid_results
            }

        # 2. Agent 1: Policy Retrieval
        policy_obj = self.retrieval_agent.retrieve_policy(policy_id)
        if not policy_obj:
            # Fallback policy criteria if not in DB yet
            criteria_defs = self._get_fallback_criteria(policy_id)
            policy_title = f"Medicare Policy {policy_id}"
        else:
            policy_title = policy_obj.title
            criteria_defs = self.retrieval_agent.get_structured_criteria(policy_id)

        gate_tau = custom_tau or settings.ABSTENTION_THRESHOLD
        state_transitions = None

        if execution_mode == "state_machine":
            # State Machine Adjudication Mode:
            # Stages 0-6 with Structured Extractor, Critic Cross-Examination, Slice Check & Calibrated Gate
            sm_engine = ClinicalAdjudicationStateMachine(db=self.db, tau=gate_tau)
            sm_res = sm_engine.execute_state_machine(
                patient_id=masked_patient_id,
                policy_id=policy_id,
                policy_title=policy_title,
                criteria_list=criteria_defs,
                raw_ehr_text=sanitized_ehr
            )
            decision = AdjudicationDecision(sm_res["final_decision"])
            abstention_status = sm_res["abstention_status"]
            raw_aggregate_conf = sm_res["raw_confidence"]
            calibrated_aggregate_conf = sm_res["calibrated_confidence"]
            abstention_reason = sm_res.get("abstention_reason") or ("; ".join(sm_res.get("abstention_reasons", [])) if sm_res.get("abstention_reasons") else None)
            clinician_action_notes = sm_res.get("clinician_action_notes")
            state_transitions = [t.model_dump() for t in sm_engine.transitions]
            criteria_assessments = sm_res.get("criterion_assessments", [])
            verification_audits = sm_res.get("verification_audits", [])
        else:
            # 3. Agent 2: Criteria Evaluation
            criteria_assessments = []
            for crit in criteria_defs:
                assessment = self.evaluator_agent.evaluate_criterion(crit, sanitized_ehr)
                criteria_assessments.append(assessment)

            # 4. Agent 3: Adversarial Verification
            verification_audits = []
            for assessment, crit_def in zip(criteria_assessments, criteria_defs):
                audit_result = self.verifier_agent.audit_assessment(assessment, crit_def, sanitized_ehr)
                verification_audits.append(audit_result)

            # 4b. Autonomous Offset Drift Healing Feedback Loop
            for assessment, audit in zip(criteria_assessments, verification_audits):
                if audit.offset_drift_detected and not audit.hallucination_flag:
                    for span in assessment.verified_spans:
                        healed = self.verifier_agent.heal_offset_drift(span, sanitized_ehr)
                        if healed:
                            audit.offset_drift_detected = False
                            audit.healed_offset_drift = True
                            audit.grounding_status = True
                            audit.calibrated_confidence = assessment.raw_confidence
                            audit.audit_notes += " [AUTONOMOUSLY HEALED: Offset drift corrected to true text position.]"

            # 5. Agent 4: Calibrated Abstention Gate
            gate = CalibratedAbstentionGate(tau=gate_tau)
            (
                decision,
                abstention_status,
                raw_aggregate_conf,
                calibrated_aggregate_conf,
                abstention_reason,
                clinician_action_notes
            ) = gate.evaluate(criteria_assessments, verification_audits)

        # 5b. Clinical Timeline & Longitudinal Waiting Period Engine
        timeline_res = TimelineAnalyzerService.evaluate_timeline(
            policy_id=policy_id,
            ehr_narrative=sanitized_ehr
        )
        if not timeline_res.all_waiting_periods_satisfied:
            violation_details = [m.advisory for m in timeline_res.milestones if m.status == "WAITING_PERIOD_UNMET"]
            joined_violations = " | ".join(violation_details)
            if clinician_action_notes:
                clinician_action_notes += f" [STATUTORY TIMELINE DEFICIT]: {joined_violations}"
            else:
                clinician_action_notes = f"[STATUTORY TIMELINE DEFICIT]: {joined_violations}"

            # If clinical criteria passed but statutory waiting period failed (e.g., < 40 days post-MI)
            if decision == AdjudicationDecision.APPROVED:
                decision = AdjudicationDecision.DENIED
                abstention_reason = f"Statutory waiting period unmet: {violation_details[0]}"

        # 5c. CMS Billing & CPT / ICD-10 Dual-Coding Verification
        billing_res = BillingValidatorService.validate_billing(
            policy_id=policy_id,
            ehr_narrative=sanitized_ehr,
            requested_cpt_codes=cpt_codes,
            requested_icd10_codes=icd10_codes
        )
        carc_codes = billing_res.carc_codes
        rarc_codes = billing_res.rarc_codes

        # 6. Cryptographic Chain-of-Custody Seal (SHA-256)
        all_spans = []
        for ca in criteria_assessments:
            for sp in ca.verified_spans:
                all_spans.append(sp.model_dump())

        audit_hash = compute_audit_hash(
            patient_id_masked=masked_patient_id,
            policy_id=policy_id,
            decision=decision.value,
            calibrated_confidence=calibrated_aggregate_conf,
            criterion_assessments=[ca.model_dump() for ca in criteria_assessments],
            evidence_spans=all_spans,
            timestamp=timestamp
        )

        execution_time_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        final_result = FinalAdjudication(
            case_id=case_id,
            patient_id_masked=masked_patient_id,
            policy_id=policy_id,
            policy_title=policy_title,
            adjudication_decision=decision,
            abstention_status=abstention_status,
            raw_aggregate_confidence=raw_aggregate_conf,
            calibrated_aggregate_confidence=calibrated_aggregate_conf,
            abstention_threshold=gate_tau,
            abstention_reason=abstention_reason,
            criterion_assessments=criteria_assessments,
            verification_audits=verification_audits,
            audit_hash=audit_hash,
            required_clinician_action_notes=clinician_action_notes,
            execution_time_ms=execution_time_ms,
            sanitized_ehr_text=sanitized_ehr,
            timestamp=timestamp,
            billing_validation=billing_res,
            timeline_analysis=timeline_res,
            carc_codes=carc_codes,
            rarc_codes=rarc_codes,
            execution_mode=execution_mode,
            state_transitions=state_transitions,
            retrieval_insights=retrieval_insights
        )

        # 7. Persistence (Zero-Retention Medical Privacy Safe Harbor)
        if self.db and save_record:
            try:
                log_entry = AdjudicationLog(
                    case_id=case_id,
                    patient_id_masked=masked_patient_id,
                    policy_id=policy_id,
                    decision=decision.value,
                    abstention_status=abstention_status,
                    abstention_reason=abstention_reason,
                    calibrated_confidence=calibrated_aggregate_conf,
                    raw_confidence=raw_aggregate_conf,
                    criterion_evaluations_json=json.dumps([c.model_dump() for c in criteria_assessments]),
                    evidence_spans_json=json.dumps(all_spans),
                    adversarial_audits_json=json.dumps([v.model_dump() for v in verification_audits]),
                    required_clinician_action_notes=clinician_action_notes,
                    audit_hash=audit_hash,
                    sanitized_ehr_preview=sanitized_ehr[:300] + "...",
                    execution_time_ms=execution_time_ms,
                    user_id=user_id,
                    created_at=timestamp
                )
                self.db.add(log_entry)
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                print(f"Failed to persist adjudication log: {e}")

        return final_result

    async def adjudicate_all_policies(
        self,
        patient_id: str,
        ehr_narrative: str,
        user_id: Optional[int] = None,
        custom_tau: Optional[float] = None
    ) -> MultiPolicyScanResponse:
        """
        Scans an EHR clinical narrative across all active CMS policies in the database.
        Identifies all qualifying policies, detects multi-morbidity coverage, and ranks the best match.
        """
        start_time = time.perf_counter()
        timestamp = datetime.now(timezone.utc)
        masked_patient_id = f"PT-***{patient_id[-4:]}" if len(patient_id) > 4 else f"PT-***"

        # 1. Fetch active policies from DB or fallback
        policies = []
        if self.db:
            policies = self.db.query(MedicarePolicy).all()

        if not policies:
            class MockPolicy:
                def __init__(self, pid, title, cat):
                    self.policy_id = pid
                    self.title = title
                    self.category = cat
            policies = [
                MockPolicy("NCD-20.4", "Implantable Automatic Defibrillators", "Cardiology"),
                MockPolicy("LCD-L33829", "Continuous Positive Airway Pressure (CPAP)", "Durable Medical Equipment"),
                MockPolicy("NCD-20.29", "Hyperbaric Oxygen Therapy", "Wound Care / Hyperbaric Medicine"),
                MockPolicy("NCD-240.2", "Home Oxygen Therapy", "Pulmonology"),
                MockPolicy("NCD-20.33", "Transcatheter Edge-to-Edge Repair (TEER)", "Cardiology"),
            ]

        # 2. Compute narrative relevance scores
        relevance_map = {}
        if self.db:
            relevance_results = self.retrieval_agent.search_policies_by_narrative(ehr_narrative)
            for r in relevance_results:
                relevance_map[r["policy_id"]] = r.get("relevance_score", 0.0)

        # 3. Evaluate each policy through the multi-agent pipeline
        all_matches: List[PolicyMatchSummary] = []
        approved_matches: List[PolicyMatchSummary] = []

        for pol in policies:
            adjudication = await self.adjudicate(
                patient_id=patient_id,
                policy_id=pol.policy_id,
                ehr_narrative=ehr_narrative,
                user_id=user_id,
                custom_tau=custom_tau,
                save_record=False
            )

            total_crit = len(adjudication.criterion_assessments)
            met_crit = sum(
                1 for c in adjudication.criterion_assessments
                if (c.status == DeterminationStatus.MET and not getattr(c, "is_exclusion", False)) or
                   (c.status == DeterminationStatus.NOT_MET and getattr(c, "is_exclusion", False))
            )
            unmet_crit = total_crit - met_crit

            if adjudication.adjudication_decision == AdjudicationDecision.APPROVED:
                rationale = f"All {total_crit} clinical criteria verified with calibrated confidence {adjudication.calibrated_aggregate_confidence:.1%}."
            elif adjudication.adjudication_decision == AdjudicationDecision.DEFERRED_TO_HUMAN:
                rationale = f"Confidence ({adjudication.calibrated_aggregate_confidence:.1%}) below safety threshold or requires human auditor review."
            else:
                unmet_names = [
                    c.name or c.criterion_code for c in adjudication.criterion_assessments
                    if (c.status != DeterminationStatus.MET and not getattr(c, "is_exclusion", False)) or
                       (c.status == DeterminationStatus.MET and getattr(c, "is_exclusion", False))
                ]
                rationale = f"Missing mandatory criteria: {', '.join(unmet_names[:3])}."

            match_summary = PolicyMatchSummary(
                policy_id=pol.policy_id,
                policy_title=pol.title,
                category=getattr(pol, "category", "Medicare Coverage"),
                decision=adjudication.adjudication_decision,
                calibrated_confidence=adjudication.calibrated_aggregate_confidence,
                relevance_score=relevance_map.get(pol.policy_id, 0.0),
                total_criteria=total_crit,
                met_criteria=met_crit,
                unmet_criteria=unmet_crit,
                is_best_match=False,
                clinical_rationale=rationale,
                adjudication=adjudication
            )
            all_matches.append(match_summary)
            if adjudication.adjudication_decision == AdjudicationDecision.APPROVED:
                approved_matches.append(match_summary)

        # 4. Rank and determine Best Match
        all_matches.sort(
            key=lambda m: (
                1 if m.decision == AdjudicationDecision.APPROVED else (0.5 if m.decision == AdjudicationDecision.DEFERRED_TO_HUMAN else 0),
                m.calibrated_confidence,
                m.relevance_score
            ),
            reverse=True
        )

        best_match_policy_id = None
        best_match_title = None
        if all_matches:
            best_match = all_matches[0]
            if best_match.decision == AdjudicationDecision.APPROVED or best_match.relevance_score > 0.1:
                best_match.is_best_match = True
                best_match_policy_id = best_match.policy_id
                best_match_title = best_match.policy_title

        # 5. Multi-morbidity and co-occurrence insights
        multi_morbidity_insights = []
        approved_categories: Dict[str, List[str]] = {}
        for app in approved_matches:
            approved_categories.setdefault(app.category, []).append(app.policy_id)

        if len(approved_matches) > 1:
            cat_descriptions = [f"{cat} ({', '.join(pids)})" for cat, pids in approved_categories.items()]
            multi_morbidity_insights.append(
                f"Multi-Policy Coverage Detected: Patient satisfies criteria for {len(approved_matches)} distinct Medicare policies across {len(approved_categories)} domain(s): {'; '.join(cat_descriptions)}."
            )
            multi_morbidity_insights.append(
                "Billing Guidance: Submit separate prior authorization packets for each distinct billable procedure or device."
            )
        elif len(approved_matches) == 1:
            multi_morbidity_insights.append(
                f"Single Primary Coverage Match: Patient qualifies for {approved_matches[0].policy_id} - {approved_matches[0].policy_title}."
            )
        else:
            multi_morbidity_insights.append(
                "No policies fully approved autonomously. Clinical auditor review recommended to verify missing diagnostic evidence."
            )

        execution_time_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        return MultiPolicyScanResponse(
            patient_id_masked=masked_patient_id,
            total_policies_scanned=len(policies),
            approved_count=len(approved_matches),
            denied_count=sum(1 for m in all_matches if m.decision == AdjudicationDecision.DENIED),
            deferred_count=sum(1 for m in all_matches if m.decision == AdjudicationDecision.DEFERRED_TO_HUMAN),
            best_match_policy_id=best_match_policy_id,
            best_match_title=best_match_title,
            all_matches=all_matches,
            multi_morbidity_insights=multi_morbidity_insights,
            execution_time_ms=execution_time_ms,
            timestamp=timestamp
        )

    def _get_fallback_criteria(self, policy_id: str) -> list:
        """Fallback criteria definitions if DB query not initialized."""
        if policy_id == "NCD-20.4":
            return [
                {
                    "criterion_code": "CRIT-ICD-01",
                    "name": "Severe LV Systolic Dysfunction",
                    "description": "Documented Left Ventricular Ejection Fraction (LVEF) <= 35% on diagnostic echocardiography or cardiac MRI.",
                    "clinical_intent": "Mandatory primary prevention threshold",
                    "is_exclusion": False,
                    "required_temporal_window": "Within past 12 months",
                    "keywords": ["lvef", "ejection fraction", "systolic dysfunction"],
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-ICD-02",
                    "name": "Heart Failure Functional Classification",
                    "description": "Patient classified as New York Heart Association (NYHA) Class II or Class III functional symptoms.",
                    "clinical_intent": "Confirm clinical symptom burden",
                    "is_exclusion": False,
                    "required_temporal_window": "At current clinical evaluation",
                    "keywords": ["nyha", "functional class", "class ii", "class iii"],
                    "min_score": 0.80
                },
                {
                    "criterion_code": "CRIT-ICD-03",
                    "name": "Guideline-Directed Medical Therapy Duration",
                    "description": "Patient has received optimal guideline-directed medical therapy (GDMT) including beta-blocker and ACEi/ARB/ARNI for >= 90 days.",
                    "clinical_intent": "Ensure medical therapy trial before invasive device",
                    "is_exclusion": False,
                    "required_temporal_window": ">= 90 days / 3 months duration",
                    "keywords": ["gdmt", "carvedilol", "lisinopril", "metoprolol", "entresto", "medical therapy"],
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-ICD-04",
                    "name": "Post-Myocardial Infarction Waiting Period",
                    "description": "At least 40 days have elapsed following an acute myocardial infarction (MI) or >= 90 days post-coronary revascularization.",
                    "clinical_intent": "Prevent premature device placement during acute recovery",
                    "is_exclusion": False,
                    "required_temporal_window": ">= 40 days post-MI or >= 90 days post-CABG",
                    "keywords": ["mi", "myocardial infarction", "revascularization", "cabg", "pci"],
                    "min_score": 0.80
                },
                {
                    "criterion_code": "CRIT-ICD-EXCL-01",
                    "name": "Terminal Illness or Cardiogenic Shock Exclusion",
                    "description": "Exclusion: Non-cardiac disease with life expectancy < 1 year, or active cardiogenic shock.",
                    "clinical_intent": "Exclude non-beneficial device placement",
                    "is_exclusion": True,
                    "required_temporal_window": "At time of evaluation",
                    "keywords": ["shock", "cardiogenic shock", "terminal", "hospice", "life expectancy"],
                    "min_score": 0.90
                }
            ]
        elif policy_id == "LCD-L33829":
            return [
                {
                    "criterion_code": "CRIT-CPAP-01",
                    "name": "Diagnostic Polysomnography (AHI)",
                    "description": "Apnea-Hypopnea Index (AHI) or Respiratory Disturbance Index (RDI) >= 15 events/hr, or AHI 5-14 with documented comorbid symptoms (hypertension, excessive sleepiness, ischemic heart disease).",
                    "clinical_intent": "Confirm objective sleep-disordered breathing severity",
                    "is_exclusion": False,
                    "required_temporal_window": "Diagnostic sleep study",
                    "keywords": ["ahi", "apnea", "polysomnography", "rdi", "sleep study"],
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-CPAP-02",
                    "name": "Face-to-Face Clinical Evaluation",
                    "description": "Face-to-face clinical evaluation by prescribing physician prior to sleep study to assess sleep disordered breathing symptoms.",
                    "clinical_intent": "In-person evaluation requirement",
                    "is_exclusion": False,
                    "required_temporal_window": "Prior to diagnostic test",
                    "keywords": ["face-to-face", "in-person", "clinical evaluation"],
                    "min_score": 0.75
                }
            ]
        elif policy_id == "NCD-20.7":
            return [
                {
                    "criterion_code": "CRIT-CAS-01",
                    "name": "Severe Carotid Stenosis (>= 70% Symptomatic or >= 80% Asymptomatic)",
                    "description": "Documented carotid artery stenosis >= 70% in symptomatic patients or >= 80% in asymptomatic patients verified by carotid duplex ultrasound, CTA, MRA, or angiography.",
                    "clinical_intent": "Establish severe anatomical carotid narrowing threshold",
                    "is_exclusion": False,
                    "required_temporal_window": "Within past 6 months",
                    "keywords": ["carotid stenosis", "70%", "80%", "carotid duplex", "cta", "mra", "angiography", "ica"],
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-CAS-02",
                    "name": "Documented High Surgical Risk for Carotid Endarterectomy (CEA)",
                    "description": "Patient has documented clinical or anatomical features placing them at high risk for open CEA (e.g., hostile neck, prior radiation, tracheostomy, severe COPD, STS score >= 8%).",
                    "clinical_intent": "Justify percutaneous stenting over surgical endarterectomy",
                    "is_exclusion": False,
                    "required_temporal_window": "Current pre-procedure evaluation",
                    "keywords": ["high risk for cea", "hostile neck", "radiation", "tracheostomy", "severe copd", "high risk"],
                    "min_score": 0.80
                },
                {
                    "criterion_code": "CRIT-CAS-03",
                    "name": "Mandatory FDA-Approved Embolic Protection Device (EPD)",
                    "description": "Procedure plan includes deployment of an FDA-approved distal embolic protection device (filter or flow reversal system) during stent deployment.",
                    "clinical_intent": "Prevent distal embolic stroke during stenting",
                    "is_exclusion": False,
                    "required_temporal_window": "Procedure plan and equipment verification",
                    "keywords": ["embolic protection device", "epd", "distal filter", "embolic protection", "stent"],
                    "min_score": 0.85
                }
            ]
        elif policy_id == "NCD-220.13":
            return [
                {
                    "criterion_code": "CRIT-LAAC-01",
                    "name": "Non-Valvular Atrial Fibrillation with High Stroke Risk (CHA2DS2-VASc >= 3)",
                    "description": "Patient has documented non-valvular atrial fibrillation with high thromboembolic stroke risk (CHA2DS2-VASc score >= 2 for men, >= 3 for women).",
                    "clinical_intent": "Establish indication for non-pharmacologic stroke prevention",
                    "is_exclusion": False,
                    "required_temporal_window": "Documented in clinical record",
                    "keywords": ["atrial fibrillation", "afib", "cha2ds2-vasc", "stroke risk", "chads"],
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-LAAC-02",
                    "name": "Contraindication to Long-Term Oral Anticoagulation (HAS-BLED >= 3)",
                    "description": "Documented formal contraindication or clinical rationale demonstrating patient is unsuitable for long-term oral anticoagulation (e.g. major recurrent bleed, HAS-BLED >= 3).",
                    "clinical_intent": "Establish necessity of device-based closure over medical anticoagulation",
                    "is_exclusion": False,
                    "required_temporal_window": "Documented medical history",
                    "keywords": ["has-bled", "bleeding risk", "hemorrhage", "contraindication", "anticoagulation", "eliquis", "bleed"],
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-LAAC-03",
                    "name": "Pre-Procedural Imaging Verifying Absence of LA Thrombus",
                    "description": "TEE or CTA within 48 hours of procedure confirming absence of intracardiac or left atrial appendage thrombus and appropriate ostial anatomy.",
                    "clinical_intent": "Ensure safety of percutaneous transseptal puncture and closure deployment",
                    "is_exclusion": False,
                    "required_temporal_window": "Within pre-procedure timeframe",
                    "keywords": ["tee", "transesophageal", "thrombus", "left atrial", "watchman", "ostium", "anatomy"],
                    "min_score": 0.80
                }
            ]
        elif policy_id == "NCD-20.33":
            return [
                {
                    "criterion_code": "CRIT-TEER-01",
                    "name": "Severe Valvular Disease (Severe MR or Severe Symptomatic AS)",
                    "description": "Grade 3+ or Grade 4+ mitral regurgitation, or severe aortic stenosis (AVA <= 1.0 cm2, mean gradient >= 40 mmHg).",
                    "clinical_intent": "Establish hemodynamic severity for transcatheter valve intervention",
                    "is_exclusion": False,
                    "required_temporal_window": "Diagnostic echocardiography within 6 months",
                    "keywords": ["mitral regurgitation", "aortic stenosis", "ava", "mean gradient", "echocardiogram"],
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-TEER-02",
                    "name": "Multidisciplinary Heart Team Consensus on High Surgical Risk",
                    "description": "Evaluation by multidisciplinary Heart Team (cardiac surgeon and interventional cardiologist) establishing high or prohibitive surgical risk (STS PROM >= 8%).",
                    "clinical_intent": "Validate surgical risk consensus for transcatheter approach",
                    "is_exclusion": False,
                    "required_temporal_window": "Pre-procedure consultation",
                    "keywords": ["heart team", "multidisciplinary", "sts score", "high surgical risk", "prohibitive risk"],
                    "min_score": 0.85
                }
            ]
        elif policy_id == "NCD-20.29":
            return [
                {
                    "criterion_code": "CRIT-HBOT-01",
                    "name": "Severe Diabetic Foot Ulcer (Wagner Grade III or Higher)",
                    "description": "Deep diabetic lower extremity wound with bone involvement, osteomyelitis, or gangrene classified as Wagner Grade III, IV, or V.",
                    "clinical_intent": "Confirm anatomical severity warranting systemic hyperbaric therapy",
                    "is_exclusion": False,
                    "required_temporal_window": "Documented at clinical examination",
                    "keywords": ["wagner", "wagner grade 3", "osteomyelitis", "deep ulcer", "diabetic foot ulcer", "gangrene"],
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-HBOT-02",
                    "name": "Failure of Standard Conservative Wound Therapy (>= 30 Days)",
                    "description": "Documented lack of significant healing following at least 30 consecutive days of conventional wound therapy (debridement, offloading, moist dressing).",
                    "clinical_intent": "Ensure standard medical care exhausted prior to hyperbaric referral",
                    "is_exclusion": False,
                    "required_temporal_window": ">= 30 days conservative care",
                    "keywords": ["30 days", "conservative therapy", "offloading", "standard care", "debridement"],
                    "min_score": 0.80
                }
            ]
        else:
            return [
                {
                    "criterion_code": "CRIT-GEN-01",
                    "name": "Clinical Indication",
                    "description": "Evidence supporting coverage indication under CMS policy.",
                    "clinical_intent": "Coverage verification",
                    "is_exclusion": False,
                    "required_temporal_window": "Current",
                    "keywords": ["indication", "condition", "treatment"],
                    "min_score": 0.75
                }
            ]

