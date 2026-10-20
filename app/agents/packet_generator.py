import uuid
from datetime import datetime, timezone
from typing import List, Optional
from app.schemas.contracts import (
    FinalAdjudication,
    CMSCoveragePacket,
    FilledCriterionSection,
    DeterminationStatus
)

class CoveragePacketGenerator:
    """
    Generates an official CMS / Medicare Prior Authorization Coverage Determination Packet
    pre-filled with clinical evidence, diagnostic codes (ICD-10), procedure codes (CPT/HCPCS),
    and physician attestations derived from the evaluated medical note.
    """

    @staticmethod
    def get_codes_for_policy(policy_id: str) -> tuple[List[str], List[str]]:
        if policy_id == "NCD-20.4":
            return (
                ["I50.22 (Chronic systolic heart failure)", "I25.10 (Atherosclerotic heart disease)", "I25.2 (Old myocardial infarction)"],
                ["33249 (Insertion of implantable defibrillator system)", "93641 (Electrophysiologic evaluation at time of ICD insertion)"]
            )
        elif policy_id == "LCD-L33829":
            return (
                ["G47.33 (Obstructive sleep apnea (adult))", "I10 (Essential hypertension)"],
                ["E0601 (Continuous positive airway pressure (CPAP) device)", "A7034 (Nasal interface mask)"]
            )
        elif policy_id == "NCD-20.29":
            return (
                ["E11.621 (Type 2 diabetes with foot ulcer)", "L97.411 (Non-pressure ulcer of foot, bone involved)", "M86.171 (Osteomyelitis)"],
                ["99183 (Physician attendance in hyperbaric oxygen chamber)", "G0277 (Hyperbaric oxygen therapy, per 30 minutes)"]
            )
        elif policy_id == "NCD-240.2":
            return (
                ["J44.9 (Chronic obstructive pulmonary disease)", "J96.11 (Chronic respiratory failure with hypoxia)"],
                ["E1390 (Oxygen concentrator, stationary)", "E0431 (Portable gaseous oxygen system)"]
            )
        else:
            return (
                ["Z00.00 (General adult medical examination)"],
                ["99214 (Office/outpatient visit, moderate complexity)"]
            )

    @classmethod
    def generate_packet(
        cls,
        adjudication: FinalAdjudication,
        physician_name: Optional[str] = "Dr. Attending Physician, MD"
    ) -> CMSCoveragePacket:
        now = datetime.now(timezone.utc)
        packet_id = f"CMS-PAC-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        icd_codes, cpt_codes = cls.get_codes_for_policy(adjudication.policy_id)
        if adjudication.billing_validation and adjudication.billing_validation.detected_cpt_codes:
            covered_cpts = [f"{c.code} ({c.description})" for c in adjudication.billing_validation.detected_cpt_codes if c.status == "COVERED"]
            if covered_cpts:
                cpt_codes = covered_cpts
        if adjudication.billing_validation and adjudication.billing_validation.detected_icd10_codes:
            covered_icds = [f"{i.code} ({i.description})" for i in adjudication.billing_validation.detected_icd10_codes if i.status == "COVERED"]
            if covered_icds:
                icd_codes = covered_icds

        # Build filled criteria sections
        filled_sections: List[FilledCriterionSection] = []
        for crit in adjudication.criterion_assessments:
            evidence_quote = "No explicit citation extracted."
            if crit.verified_spans:
                evidence_quote = " | ".join([f'"{s.source_text}" (Section: {s.clinical_section})' for s in crit.verified_spans])

            if crit.status == DeterminationStatus.MET:
                attestation = f"I certify that documentation confirms {crit.name} requirement ({crit.required_temporal_window})."
            elif crit.status == DeterminationStatus.NOT_MET:
                attestation = f"Note indicates patient does not meet {crit.name} criterion."
            else:
                attestation = f"Supplementary clinical records requested for {crit.name} verification."

            filled_sections.append(FilledCriterionSection(
                criterion_code=crit.criterion_code,
                name=crit.name,
                status=crit.status.value,
                required_temporal_window=crit.required_temporal_window,
                extracted_evidence_quote=evidence_quote,
                clinical_rationale=crit.clinical_rationale,
                physician_attestation=attestation
            ))

        # Clinical Summary formulation
        summary = (
            f"Pre-authorization review for {adjudication.policy_title} ({adjudication.policy_id}). "
            f"Adjudication outcome: {adjudication.adjudication_decision.value} "
            f"with {adjudication.calibrated_aggregate_confidence * 100:.1f}% calibrated evidence confidence. "
        )
        if adjudication.abstention_status:
            summary += f"Gate Abstention active: {adjudication.abstention_reason}."

        # Determine CMS statutory validity period & Shared Decision Making (SDM) Attestation
        validity_period = "180 calendar days from date of determination"
        sdm_attestation = None

        if adjudication.policy_id == "NCD-20.4":
            validity_period = "180 Calendar Days (Elective ICD Device Implantation)"
            sdm_attestation = (
                "CMS NCD 20.4 Section B.3 Statutory Compliance: A formal shared decision-making encounter "
                "between the patient and an independent clinical practitioner occurred using an evidence-based decision tool "
                "addressing sudden cardiac death risks, ICD shock therapy, replacement timelines, and patient values."
            )
        elif adjudication.policy_id in ["LCD-L33829", "NCD-240.4"]:
            validity_period = "90 Calendar Days Initial Dispensing (followed by 12-week adherence trial)"
            sdm_attestation = (
                "CMS LCD L33718 / NCD 240.4 Compliance: Documented face-to-face clinical evaluation with patient "
                "education regarding proper positive airway pressure interface fit, acclimatization, and 12-week compliance trial."
            )
        elif adjudication.policy_id == "NCD-20.33":
            validity_period = "180 Calendar Days (TAVR Procedure)"
            sdm_attestation = (
                "CMS NCD 20.33 Section B.2 Compliance: Multi-disciplinary Heart Team consultation completed by "
                "interventional cardiologist and cardiac surgeon documenting surgical mortality risk, frailty, and patient goals."
            )
        elif adjudication.policy_id == "NCD-220.13":
            validity_period = "180 Calendar Days (LAAC Procedure)"
            sdm_attestation = (
                "CMS NCD 220.13 Compliance: Independent physician consultation documented concurring with non-pharmacologic "
                "stroke prevention rationale due to high bleeding risk on oral anticoagulation."
            )
        elif adjudication.policy_id == "NCD-20.29":
            validity_period = "30 Calendar Days (Hyperbaric Oxygen Therapy - 30 Session Course)"
            sdm_attestation = (
                "CMS NCD 20.29 Compliance: Hyperbaric medicine specialist evaluation confirming patient clearance "
                "and protocol adherence plan for diabetic foot ulcer management."
            )

        return CMSCoveragePacket(
            packet_id=packet_id,
            case_id=adjudication.case_id,
            patient_id_masked=adjudication.patient_id_masked,
            policy_id=adjudication.policy_id,
            policy_title=adjudication.policy_title,
            jurisdiction="Medicare Part B / CMS Regional MAC",
            date_of_service=now.strftime("%Y-%m-%d"),
            icd10_codes=icd_codes,
            cpt_hcpcs_codes=cpt_codes,
            clinical_summary=summary,
            criteria_sections=filled_sections,
            adjudication_decision=adjudication.adjudication_decision.value,
            abstention_status=adjudication.abstention_status,
            calibrated_confidence=adjudication.calibrated_aggregate_confidence,
            audit_hash=adjudication.audit_hash,
            submission_status="PENDING_CLINICIAN_REVIEW",
            clinician_action_notes=adjudication.required_clinician_action_notes,
            authorization_validity_period=validity_period,
            shared_decision_making_attestation=sdm_attestation
        )

