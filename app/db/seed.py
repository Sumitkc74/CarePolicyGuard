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
    policies_data = [
        {
            "policy_id": "NCD-20.4",
            "title": "Implantable Automatic Defibrillators (ICDs)",
            "jurisdiction": "National Coverage Determination (CMS)",
            "effective_date": "2018-02-15",
            "category": "Cardiology",
            "description": "CMS coverage policy for primary and secondary prevention implantable cardioverter defibrillators. Mandates documented severe systolic dysfunction (LVEF <= 35%), NYHA Class II/III, at least 90 days of guideline-directed medical therapy (GDMT), post-event waiting periods, and absence of cardiogenic shock.",
            "criteria": [
                {
                    "criterion_code": "CRIT-ICD-01",
                    "name": "Severe LV Systolic Dysfunction (LVEF <= 35%)",
                    "description": "Documented Left Ventricular Ejection Fraction (LVEF) <= 35% on diagnostic echocardiography, cardiac MRI, or radionucleotide ventriculography.",
                    "clinical_intent": "Mandatory primary prevention hemodynamic threshold",
                    "is_exclusion": False,
                    "required_temporal_window": "Within past 12 months",
                    "keywords": "lvef, ejection fraction, systolic dysfunction, echo, 35%",
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-ICD-02",
                    "name": "Heart Failure Functional Classification (NYHA II/III)",
                    "description": "Patient classified as New York Heart Association (NYHA) Class II or Class III functional heart failure symptoms.",
                    "clinical_intent": "Verify symptomatic heart failure burden",
                    "is_exclusion": False,
                    "required_temporal_window": "Documented at clinical evaluation",
                    "keywords": "nyha, functional class, class ii, class iii, dyspnea, heart failure",
                    "min_score": 0.80
                },
                {
                    "criterion_code": "CRIT-ICD-03",
                    "name": "Guideline-Directed Medical Therapy Duration (>=90 Days)",
                    "description": "Patient has received optimal guideline-directed medical therapy (GDMT) including beta-blocker, ACEi/ARB/ARNI, and MRA for at least 90 days (3 months).",
                    "clinical_intent": "Ensure medical optimization trial before device implantation",
                    "is_exclusion": False,
                    "required_temporal_window": ">= 90 days / 3 months duration",
                    "keywords": "gdmt, carvedilol, metoprolol, lisinopril, entresto, spironolactone, 90 days, 3 months",
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-ICD-04",
                    "name": "Post-Myocardial Infarction & Revascularization Waiting Period",
                    "description": "At least 40 days must have elapsed post-myocardial infarction (MI) and at least 90 days elapsed post-CABG or post-PCI revascularization.",
                    "clinical_intent": "Allow myocardial recovery window to prevent premature implantation",
                    "is_exclusion": False,
                    "required_temporal_window": ">= 40 days post-MI or >= 90 days post-CABG/PCI",
                    "keywords": "mi, myocardial infarction, revascularization, cabg, pci, 40 days, 90 days",
                    "min_score": 0.80
                },
                {
                    "criterion_code": "CRIT-ICD-EXCL-01",
                    "name": "Cardiogenic Shock or Non-Cardiac Terminal Illness Exclusion",
                    "description": "Exclusion: Patient has active cardiogenic shock or non-cardiac disease with life expectancy less than 1 year (e.g., metastatic cancer, hospice).",
                    "clinical_intent": "Exclude non-beneficial device placement under futile conditions",
                    "is_exclusion": True,
                    "required_temporal_window": "Current clinical encounter",
                    "keywords": "shock, cardiogenic shock, terminal, hospice, life expectancy < 1 year",
                    "min_score": 0.90
                }
            ]
        },
        {
            "policy_id": "LCD-L33829",
            "title": "Positive Airway Pressure (PAP) Devices for Obstructive Sleep Apnea",
            "jurisdiction": "Noridian Healthcare Solutions (JE/JF)",
            "effective_date": "2020-01-01",
            "category": "Pulmonology",
            "description": "Medicare local coverage determination for CPAP/APAP therapy in adult obstructive sleep apnea (OSA). Requires diagnostic polysomnography with AHI/RDI >= 15, or AHI 5-14 with documented comorbid symptoms, and prior face-to-face clinical evaluation.",
            "criteria": [
                {
                    "criterion_code": "CRIT-CPAP-01",
                    "name": "Diagnostic Polysomnography (AHI/RDI >= 15 or 5-14 with Comorbidity)",
                    "description": "Apnea-Hypopnea Index (AHI) or Respiratory Disturbance Index (RDI) >= 15 events/hr, or AHI 5-14 accompanied by documented hypertension, excessive daytime sleepiness, or ischemic heart disease.",
                    "clinical_intent": "Confirm objective diagnostic severity of sleep-disordered breathing",
                    "is_exclusion": False,
                    "required_temporal_window": "Diagnostic sleep study",
                    "keywords": "ahi, rdi, polysomnography, sleep study, apnea, hypopnea, hypertension, sleepiness",
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-CPAP-02",
                    "name": "Prerequisite Face-to-Face Clinical Evaluation",
                    "description": "A face-to-face clinical evaluation conducted by the prescribing physician prior to the sleep study documenting sleep-disordered breathing signs and symptoms.",
                    "clinical_intent": "Mandatory in-person physician clinical assessment prior to testing",
                    "is_exclusion": False,
                    "required_temporal_window": "Prior to diagnostic sleep study",
                    "keywords": "face-to-face, in-person, clinical evaluation, sleep evaluation",
                    "min_score": 0.80
                }
            ]
        },
        {
            "policy_id": "NCD-20.29",
            "title": "Hyperbaric Oxygen Therapy for Diabetic Wounds of Lower Extremities",
            "jurisdiction": "National Coverage Determination (CMS)",
            "effective_date": "2017-04-03",
            "category": "Wound Care",
            "description": "CMS coverage for systemic hyperbaric oxygen therapy (HBOT) in patients with diabetic wounds of the lower extremities. Requires Wagner Grade 3 or higher, failure of at least 30 days of standard conservative wound therapy, and vascular evaluation.",
            "criteria": [
                {
                    "criterion_code": "CRIT-HBOT-01",
                    "name": "Severe Diabetic Wound Wagner Grade 3 or Higher",
                    "description": "Documented deep diabetic foot ulceration with involvement of tendon, capsule, or bone (Wagner Grade 3: deep ulcer with abscess or osteomyelitis; Grade 4: gangrene of forefoot).",
                    "clinical_intent": "Establish severe deep tissue infection or bone involvement",
                    "is_exclusion": False,
                    "required_temporal_window": "At current wound evaluation",
                    "keywords": "wagner, grade 3, grade 4, osteomyelitis, gangrene, deep ulcer",
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-HBOT-02",
                    "name": "Failure of >= 30 Days Standard Conservative Wound Therapy",
                    "description": "Patient must have completed at least 30 continuous days of standard wound care (including sharp debridement, moist dressings, and offloading) without measurable signs of healing.",
                    "clinical_intent": "Verify exhaustion of standard wound care prior to high-cost HBOT",
                    "is_exclusion": False,
                    "required_temporal_window": ">= 30 days prior to HBOT initiation",
                    "keywords": "standard wound care, debridement, offloading, 30 days, failed",
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-HBOT-03",
                    "name": "Lower Extremity Vascular Assessment",
                    "description": "Documentation of peripheral perfusion assessment (palpable dorsalis pedis / posterior tibial pulses, or ABI >= 0.7) to rule out untreatable ischemic non-viability.",
                    "clinical_intent": "Confirm sufficient vascular perfusion for tissue viability",
                    "is_exclusion": False,
                    "required_temporal_window": "Within past 60 days",
                    "keywords": "vascular, pulses, palpable, abi, perfusion",
                    "min_score": 0.75
                }
            ]
        },
        {
            "policy_id": "NCD-240.2",
            "title": "Home Use of Oxygen",
            "jurisdiction": "National Coverage Determination (CMS)",
            "effective_date": "2021-09-27",
            "category": "Pulmonology",
            "description": "CMS coverage for long-term home oxygen therapy in chronic respiratory disease. Requires documented arterial blood gas PaO2 <= 55 mmHg or SaO2/SpO2 <= 88% at rest on room air.",
            "criteria": [
                {
                    "criterion_code": "CRIT-O2-01",
                    "name": "Resting Hypoxemia (PaO2 <= 55 mmHg or SpO2 <= 88%)",
                    "description": "Arterial blood gas PaO2 <= 55 mmHg or pulse oximetry oxygen saturation (SpO2) <= 88% measured at rest on room air in a stable state.",
                    "clinical_intent": "Objective demonstration of severe chronic resting hypoxemia",
                    "is_exclusion": False,
                    "required_temporal_window": "Within 30 days of order",
                    "keywords": "pao2, spo2, oxygen saturation, hypoxemia, room air, 88%",
                    "min_score": 0.85
                }
            ]
        },
        {
            "policy_id": "NCD-20.33",
            "title": "Transcatheter Edge-to-Edge Repair (TEER) for Mitral Regurgitation",
            "jurisdiction": "National Coverage Determination (CMS)",
            "effective_date": "2024-07-01",
            "category": "Cardiology",
            "description": "CMS coverage for Transcatheter Edge-to-Edge Repair (TEER / MitraClip) for treatment of significant symptomatic severe mitral regurgitation in high surgical risk patients. Requires documented multidisciplinary Heart Team consensus evaluation.",
            "criteria": [
                {
                    "criterion_code": "CRIT-TEER-01",
                    "name": "Severe Valvular Disease (Severe Mitral Regurgitation or Severe Aortic Stenosis)",
                    "description": "Documented severe valvular disease: severe mitral regurgitation (Grade 3+ to 4+) or severe aortic stenosis (AVA <= 1.0 cm2, mean gradient >= 40 mmHg, or peak velocity >= 4.0 m/s).",
                    "clinical_intent": "Establish severe structural valvular disease threshold for percutaneous repair/replacement",
                    "is_exclusion": False,
                    "required_temporal_window": "Within past 6 months",
                    "keywords": "mitral regurgitation, mr, grade 3+, grade 4+, severe mr, aortic stenosis, ava, mean gradient, aortic jet, tavr, echo",
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-TEER-02",
                    "name": "Multidisciplinary Heart Team Consensus",
                    "description": "Independent evaluation by a cardiac surgeon and an interventional cardiologist confirming prohibited or high surgical risk (STS score >= 8% or documented prohibitive risk factors).",
                    "clinical_intent": "Ensure multi-specialty surgical risk consensus per CMS mandate",
                    "is_exclusion": False,
                    "required_temporal_window": "Prior to procedure scheduling",
                    "keywords": "heart team, cardiothoracic surgeon, high risk, sts score, prohibitive risk",
                    "min_score": 0.80
                }
            ]
        },
        {
            "policy_id": "NCD-20.7",
            "title": "Percutaneous Transluminal Angioplasty (PTA) with Carotid Artery Stenting (CAS)",
            "jurisdiction": "National Coverage Determination (CMS)",
            "effective_date": "2023-10-11",
            "category": "Interventional Neurology & Cardiology",
            "description": "CMS coverage for Percutaneous Transluminal Angioplasty (PTA) with Carotid Artery Stenting (CAS) for patients with symptomatic or asymptomatic severe carotid stenosis at high risk for carotid endarterectomy (CEA). Mandatory deployment of FDA-approved embolic protection systems.",
            "criteria": [
                {
                    "criterion_code": "CRIT-CAS-01",
                    "name": "Severe Carotid Stenosis (>= 70% Symptomatic or >= 80% Asymptomatic)",
                    "description": "Documented carotid artery stenosis >= 70% in symptomatic patients or >= 80% in asymptomatic patients verified by carotid duplex ultrasound, CTA, MRA, or angiography.",
                    "clinical_intent": "Establish severe anatomical carotid narrowing threshold",
                    "is_exclusion": False,
                    "required_temporal_window": "Within past 6 months",
                    "keywords": "carotid stenosis, 70%, 80%, carotid duplex, cta, mra, angiography, ica",
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-CAS-02",
                    "name": "Documented High Surgical Risk for Carotid Endarterectomy (CEA)",
                    "description": "Patient has documented clinical or anatomical features placing them at high risk for open CEA (e.g., hostile neck, prior radiation, tracheostomy, severe COPD, STS score >= 8%).",
                    "clinical_intent": "Justify percutaneous stenting over surgical endarterectomy",
                    "is_exclusion": False,
                    "required_temporal_window": "Current pre-procedure evaluation",
                    "keywords": "high risk for cea, hostile neck, radiation, tracheostomy, severe copd, high risk",
                    "min_score": 0.80
                },
                {
                    "criterion_code": "CRIT-CAS-03",
                    "name": "Mandatory FDA-Approved Embolic Protection Device (EPD)",
                    "description": "Procedure plan includes deployment of an FDA-approved distal embolic protection device (filter or flow reversal system) during stent deployment.",
                    "clinical_intent": "Prevent distal embolic stroke during stenting",
                    "is_exclusion": False,
                    "required_temporal_window": "Procedure plan and equipment verification",
                    "keywords": "embolic protection device, epd, distal filter, embolic protection, stent",
                    "min_score": 0.85
                }
            ]
        },
        {
            "policy_id": "NCD-220.13",
            "title": "Percutaneous Left Atrial Appendage Closure (LAAC / Watchman)",
            "jurisdiction": "National Coverage Determination (CMS)",
            "effective_date": "2024-01-01",
            "category": "Electrophysiology & Interventional Cardiology",
            "description": "CMS coverage for Percutaneous Left Atrial Appendage Closure (LAAC) for patients with non-valvular atrial fibrillation at high stroke risk who are unsuitable for long-term oral anticoagulation.",
            "criteria": [
                {
                    "criterion_code": "CRIT-LAAC-01",
                    "name": "Non-Valvular Atrial Fibrillation with High Stroke Risk (CHA2DS2-VASc >= 3)",
                    "description": "Documented non-valvular atrial fibrillation with high thromboembolic stroke risk (CHA2DS2-VASc score >= 2 for men or >= 3 for women).",
                    "clinical_intent": "Confirm clinical indication for stroke risk reduction in non-valvular AF",
                    "is_exclusion": False,
                    "required_temporal_window": "Documented in clinical record",
                    "keywords": "atrial fibrillation, afib, cha2ds2-vasc, stroke risk, chads",
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-LAAC-02",
                    "name": "Contraindication to Long-Term Oral Anticoagulation (HAS-BLED >= 3)",
                    "description": "Documented formal contraindication or clinical rationale demonstrating patient is unsuitable for long-term oral anticoagulation (e.g. major recurrent bleed, HAS-BLED >= 3).",
                    "clinical_intent": "Establish necessity of device-based closure over medical anticoagulation",
                    "is_exclusion": False,
                    "required_temporal_window": "Documented medical history",
                    "keywords": "has-bled, bleeding risk, hemorrhage, contraindication, anticoagulation, eliquis, bleed",
                    "min_score": 0.85
                },
                {
                    "criterion_code": "CRIT-LAAC-03",
                    "name": "Pre-Procedural Imaging Verifying Absence of LA Thrombus",
                    "description": "TEE or CTA within 48 hours of procedure confirming absence of intracardiac or left atrial appendage thrombus and appropriate ostial anatomy.",
                    "clinical_intent": "Ensure safety of percutaneous transseptal puncture and closure deployment",
                    "is_exclusion": False,
                    "required_temporal_window": "Within pre-procedure timeframe",
                    "keywords": "tee, transesophageal, thrombus, left atrial, watchman, ostium, anatomy",
                    "min_score": 0.80
                }
            ]
        }
    ]

    for p_info in policies_data:
        pol = db.query(MedicarePolicy).filter(MedicarePolicy.policy_id == p_info["policy_id"]).first()
        if not pol:
            pol = MedicarePolicy(
                policy_id=p_info["policy_id"],
                title=p_info["title"],
                jurisdiction=p_info["jurisdiction"],
                effective_date=p_info["effective_date"],
                category=p_info["category"],
                description=p_info["description"]
            )
            db.add(pol)
            db.commit()
            db.refresh(pol)

            for c_info in p_info["criteria"]:
                crit = PolicyCriterion(
                    policy_id=pol.id,
                    criterion_code=c_info["criterion_code"],
                    name=c_info["name"],
                    description=c_info["description"],
                    clinical_intent=c_info["clinical_intent"],
                    is_exclusion=c_info["is_exclusion"],
                    required_temporal_window=c_info["required_temporal_window"],
                    keywords=c_info["keywords"],
                    min_score=c_info["min_score"]
                )
                db.add(crit)
            db.commit()
        else:
            existing_codes = {c.criterion_code for c in pol.criteria}
            for c_info in p_info["criteria"]:
                if c_info["criterion_code"] not in existing_codes:
                    crit = PolicyCriterion(
                        policy_id=pol.id,
                        criterion_code=c_info["criterion_code"],
                        name=c_info["name"],
                        description=c_info["description"],
                        clinical_intent=c_info["clinical_intent"],
                        is_exclusion=c_info["is_exclusion"],
                        required_temporal_window=c_info["required_temporal_window"],
                        keywords=c_info["keywords"],
                        min_score=c_info["min_score"]
                    )
                    db.add(crit)
            db.commit()

