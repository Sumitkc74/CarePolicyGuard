from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, Text, DateTime, ForeignKey
)
from sqlalchemy.orm import relationship
from app.db.session import Base

def utcnow():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="Clinician")  # Auditor, Clinician, Admin
    is_active = Column(Boolean, default=True, nullable=False)

    # Medical Professional Credential & Licensure Verification
    npi_number = Column(String(20), nullable=True, index=True)
    medical_license = Column(String(50), nullable=True)
    license_state = Column(String(10), nullable=True)
    credential_title = Column(String(50), nullable=True)  # MD, DO, NP, PA-C, MBBS, CRNA, PharmD
    specialty = Column(String(100), nullable=True)
    organization = Column(String(150), nullable=True)
    is_verified_medical_pro = Column(Boolean, default=False, nullable=False)
    verification_method = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    adjudication_logs = relationship("AdjudicationLog", back_populates="user")


class MedicarePolicy(Base):
    __tablename__ = "medicare_policies"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    policy_id = Column(String(50), unique=True, index=True, nullable=False)  # e.g., 'NCD-20.4', 'LCD-L33829'
    title = Column(String(255), nullable=False)
    jurisdiction = Column(String(100), nullable=False, default="National")
    effective_date = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(100), nullable=False, default="Cardiology")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    criteria = relationship("PolicyCriterion", back_populates="policy", cascade="all, delete-orphan", order_by="PolicyCriterion.id")


class PolicyCriterion(Base):
    __tablename__ = "policy_criteria"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    policy_id = Column(Integer, ForeignKey("medicare_policies.id", ondelete="CASCADE"), nullable=False, index=True)
    criterion_code = Column(String(50), nullable=False, index=True)  # e.g., 'CRIT-1', 'CRIT-EXCL-1'
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    clinical_intent = Column(Text, nullable=False)
    is_exclusion = Column(Boolean, default=False, nullable=False)
    required_temporal_window = Column(String(150), nullable=False, default="Not specified")
    keywords = Column(Text, nullable=False, default="")  # comma-separated clinical tokens
    min_score = Column(Float, default=0.75, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    policy = relationship("MedicarePolicy", back_populates="criteria")


class AdjudicationLog(Base):
    __tablename__ = "adjudication_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    case_id = Column(String(100), unique=True, index=True, nullable=False)
    patient_id_masked = Column(String(100), index=True, nullable=False)
    policy_id = Column(String(50), index=True, nullable=False)
    decision = Column(String(50), nullable=False)  # APPROVED, DENIED, DEFERRED_TO_HUMAN
    abstention_status = Column(Boolean, default=False, nullable=False)
    abstention_reason = Column(Text, nullable=True)
    calibrated_confidence = Column(Float, nullable=False)
    raw_confidence = Column(Float, nullable=False)
    criterion_evaluations_json = Column(Text, nullable=False)
    evidence_spans_json = Column(Text, nullable=False)
    adversarial_audits_json = Column(Text, nullable=False)
    required_clinician_action_notes = Column(Text, nullable=True)
    audit_hash = Column(String(64), index=True, nullable=False)  # SHA-256
    sanitized_ehr_preview = Column(Text, nullable=False)
    execution_time_ms = Column(Float, default=0.0, nullable=False)
    submission_status = Column(String(50), default="PENDING_REVIEW", nullable=False)
    signed_by = Column(String(100), nullable=True)
    signed_at = Column(DateTime(timezone=True), nullable=True)
    payer_transaction_id = Column(String(100), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="adjudication_logs")


