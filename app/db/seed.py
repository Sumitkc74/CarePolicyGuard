from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import get_password_hash, UserRole
from app.db.models import User, MedicarePolicy, PolicyCriterion

def seed_database(db: Session):
    """
    Seeds initial users and CMS Medicare National and Local Coverage Determinations (NCDs and LCDs).
    """
    # 1. Seed Users
    default_users = [
        {
            "username": "admin@carepolicyguard.med",
            "email": "admin@carepolicyguard.med",
            "password": settings.DEFAULT_ADMIN_PASS,
            "role": UserRole.ADMIN.value,
            "mfa_enabled": True,
            "mfa_method": "email_otp"
        },
        {
            "username": "auditor@medicare.cms.gov",
            "email": "auditor@medicare.cms.gov",
            "password": settings.DEFAULT_AUDITOR_PASS,
            "role": UserRole.AUDITOR.value,
            "mfa_enabled": True,
            "mfa_method": "email_otp"
        },
        {
            "username": "clinician@hospital.org",
            "email": "clinician@hospital.org",
            "password": settings.DEFAULT_CLINICIAN_PASS,
            "role": UserRole.CLINICIAN.value,
            "npi_number": "1043256787",
            "medical_license": "C194820",
            "license_state": "CA",
            "credential_title": "MD",
            "specialty": "Cardiology & Electrophysiology",
            "organization": "Pacific Heart & Vascular Institute",
            "is_verified_medical_pro": True,
            "verification_method": "NPPES_API_VERIFIED",
            "mfa_enabled": True,
            "mfa_method": "email_otp"
        },
        {
            "username": "doctor@hospital.org",
            "email": "doctor@hospital.org",
            "password": "password123",
            "role": UserRole.CLINICIAN.value,
            "npi_number": "1043256787",
            "medical_license": "C12345",
            "license_state": "CA",
            "credential_title": "MD",
            "specialty": "Cardiology",
            "organization": "General Hospital",
            "is_verified_medical_pro": True,
            "verification_method": "NPPES_API_VERIFIED",
            "mfa_enabled": True,
            "mfa_method": "email_otp",
            "mfa_enabled_methods": "email_otp,totp_app",
            "totp_secret": "JBSWY3DPEHPK3PXP"
        }
    ]

    for u_data in default_users:
        existing = db.query(User).filter(User.username == u_data["username"]).first()
        if not existing:
            user = User(
                username=u_data["username"],
                email=u_data["email"],
                hashed_password=get_password_hash(u_data["password"]),
                role=u_data["role"],
                npi_number=u_data.get("npi_number"),
                medical_license=u_data.get("medical_license"),
                license_state=u_data.get("license_state"),
                credential_title=u_data.get("credential_title"),
                specialty=u_data.get("specialty"),
                organization=u_data.get("organization"),
                is_verified_medical_pro=u_data.get("is_verified_medical_pro", False),
                verification_method=u_data.get("verification_method"),
                mfa_enabled=u_data.get("mfa_enabled", False),
                mfa_method=u_data.get("mfa_method"),
                is_active=True
            )
            db.add(user)
        else:
            if u_data.get("npi_number") and not existing.npi_number:
                existing.npi_number = u_data.get("npi_number")
                existing.medical_license = u_data.get("medical_license")
                existing.license_state = u_data.get("license_state")
                existing.credential_title = u_data.get("credential_title")
                existing.specialty = u_data.get("specialty")
                existing.organization = u_data.get("organization")
                existing.is_verified_medical_pro = u_data.get("is_verified_medical_pro", False)
                existing.verification_method = u_data.get("verification_method")
            if "mfa_enabled" in u_data:
                existing.mfa_enabled = u_data["mfa_enabled"]
                existing.mfa_method = u_data["mfa_method"]
                existing.mfa_enabled_methods = u_data.get("mfa_enabled_methods", "email_otp")
                if u_data.get("totp_secret"):
                    existing.totp_secret = u_data["totp_secret"]

    db.commit()

    # 2. Seed Medicare Policies & Criteria
    from app.services.declarative_engine import DeclarativePolicyEngine
    declarative_policies = DeclarativePolicyEngine.get_all_policies()

    for p in declarative_policies:
        pol = db.query(MedicarePolicy).filter(MedicarePolicy.policy_id == p.policy_id).first()
        if not pol:
            pol = MedicarePolicy(
                policy_id=p.policy_id,
                title=p.title,
                jurisdiction=p.jurisdiction,
                effective_date=p.effective_date,
                category=p.category,
                description=p.description
            )
            db.add(pol)
            db.commit()
            db.refresh(pol)
        else:
            pol.title = p.title
            pol.jurisdiction = p.jurisdiction
            pol.effective_date = p.effective_date
            pol.category = p.category
            pol.description = p.description
            db.commit()

        # Synchronize criteria from canonical declarative JSON schemas
        existing_criteria_map = {c.criterion_code: c for c in pol.criteria}
        active_codes = set()
        for c in p.criteria:
            active_codes.add(c.criterion_code)
            kw_str = ", ".join(c.entity_names)
            if c.criterion_code in existing_criteria_map:
                crit = existing_criteria_map[c.criterion_code]
                crit.name = c.name
                crit.description = c.description
                crit.clinical_intent = c.clinical_intent
                crit.is_exclusion = c.is_exclusion
                crit.required_temporal_window = c.required_temporal_window
                crit.keywords = kw_str
                crit.min_score = c.min_score
            else:
                crit = PolicyCriterion(
                    policy_id=pol.id,
                    criterion_code=c.criterion_code,
                    name=c.name,
                    description=c.description,
                    clinical_intent=c.clinical_intent,
                    is_exclusion=c.is_exclusion,
                    required_temporal_window=c.required_temporal_window,
                    keywords=kw_str,
                    min_score=c.min_score
                )
                db.add(crit)

        # Remove deprecated criteria no longer present in canonical schema
        for code, crit in list(existing_criteria_map.items()):
            if code not in active_codes:
                db.delete(crit)

        db.commit()
