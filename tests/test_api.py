import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.config import settings

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == settings.PROJECT_NAME

def test_auth_login_valid_credentials():
    response = client.post("/api/v1/auth/login", json={
        "username": "auditor@medicare.cms.gov",
        "password": settings.DEFAULT_AUDITOR_PASS
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "Auditor"
    assert data["token_type"] == "bearer"

def test_auth_login_invalid_credentials():
    response = client.post("/api/v1/auth/login", json={
        "username": "auditor@medicare.cms.gov",
        "password": "WrongPassword123"
    })
    assert response.status_code == 401

def test_get_policies():
    response = client.get("/api/v1/policies")
    assert response.status_code == 200
    policies = response.json()
    assert len(policies) >= 3
    policy_ids = [p["policy_id"] for p in policies]
    assert "NCD-20.4" in policy_ids
    assert "LCD-L33829" in policy_ids

def test_get_presets():
    response = client.get("/api/v1/presets")
    assert response.status_code == 200
    data = response.json()
    assert "presets" in data
    assert len(data["presets"]) >= 4

def test_adjudicate_endpoint_qualifying_scenario():
    # Login to get token
    login_res = client.post("/api/v1/auth/login", json={
        "username": "auditor@medicare.cms.gov",
        "password": settings.DEFAULT_AUDITOR_PASS
    })
    token = login_res.json()["access_token"]

    ehr_text = """
    PROGRESS NOTE - CARDIOLOGY
    Patient with history of anterior STEMI 18 months ago.
    Echocardiogram: LVEF is 28%. NYHA Class II symptoms.
    On carvedilol and lisinopril for 6 months.
    No cardiogenic shock. Life expectancy > 1 year.
    """

    res = client.post(
        "/api/v1/adjudicate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "patient_id": "PT-TEST-8812",
            "policy_id": "NCD-20.4",
            "ehr_narrative": ehr_text
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["adjudication_decision"] == "APPROVED"
    assert data["abstention_status"] is False
    assert len(data["audit_hash"]) == 64
    assert len(data["criterion_assessments"]) >= 4
    assert len(data["verification_audits"]) >= 4

def test_benchmark_endpoint():
    res = client.post("/api/v1/benchmark/run")
    assert res.status_code == 200
    data = res.json()
    assert "configs" in data
    assert len(data["configs"]) == 4
    config_names = [c["config_name"] for c in data["configs"]]
    assert "Config A" in config_names
    assert "Config D" in config_names
    # Config D must have highest safety and faithfulness
    config_d = next(c for c in data["configs"] if c["config_name"] == "Config D")
    assert config_d["evidence_faithfulness"] == 1.0
    assert config_d["expected_calibration_error"] <= 0.08

def test_upload_note_and_submit_to_insurance():
    # 1. Doctor uploads clinical note
    clinical_note_content = b"""
    PULMONOLOGY CONSULTATION NOTE
    Patient with severe chronic snoring and witnessed apneas.
    Face-to-face clinical evaluation completed prior to diagnostic testing.
    Diagnostic overnight Polysomnography completed:
    Apnea-Hypopnea Index (AHI): 28.4 events/hr.
    Documented comorbid hypertension and daytime somnolence.
    Prescription for continuous positive airway pressure (auto-CPAP) initiated.
    """

    res = client.post(
        "/api/v1/upload-note",
        files={"file": ("dr_consult_note.txt", clinical_note_content, "text/plain")},
        data={"policy_id": "auto", "patient_id": "PT-DOC-4402", "tau": 0.85}
    )
    assert res.status_code == 200
    upload_data = res.json()
    assert upload_data["filename"] == "dr_consult_note.txt"
    assert upload_data["adjudication"]["policy_id"] == "LCD-L33829"  # Auto-matched OSA policy!
    assert upload_data["adjudication"]["adjudication_decision"] == "APPROVED"
    assert "packet" in upload_data
    case_id = upload_data["adjudication"]["case_id"]

    # 2. Retrieve filled coverage packet for clinician review
    packet_res = client.get(f"/api/v1/packet/{case_id}")
    assert packet_res.status_code == 200
    packet = packet_res.json()
    assert packet["case_id"] == case_id
    assert packet["policy_id"] == "LCD-L33829"
    assert len(packet["criteria_sections"]) >= 2
    assert "G47.33" in packet["icd10_codes"][0]

    # 3. Clinician signs & transmits packet to insurance
    submit_res = client.post(
        "/api/v1/packet/submit",
        json={
            "case_id": case_id,
            "signed_by": "Dr. Sarah Jenkins, MD, FCCP",
            "clinician_notes": "Patient thoroughly evaluated; meets all criteria under LCD L33829.",
            "payer_name": "CMS Medicare Part B / Noridian MAC"
        }
    )
    assert submit_res.status_code == 200
    receipt = submit_res.json()
    assert receipt["submission_status"] == "TRANSMITTED_ACCEPTED"
    assert receipt["signed_by"] == "Dr. Sarah Jenkins, MD, FCCP"
    assert receipt["payer_transaction_id"].startswith("CMS-EDI-837-")

def test_upload_image_note_and_adjudicate():
    """Verify that clinical note images (.png, .jpg) are accepted and OCR-extracted."""
    from PIL import Image, ImageDraw
    import io

    # Generate a synthetic PNG note
    img = Image.new("RGB", (800, 250), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "CONSULTATION: Severe Obstructive Sleep Apnea", fill=(0, 0, 0))
    draw.text((20, 60), "Diagnostic PSG shows AHI of 34 events/hr.", fill=(0, 0, 0))
    draw.text((20, 100), "Face-to-face physician evaluation completed prior to PSG.", fill=(0, 0, 0))
    draw.text((20, 140), "Prescribing continuous positive airway pressure (CPAP).", fill=(0, 0, 0))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    response = client.post(
        "/api/v1/upload-note",
        files={"file": ("clinical_sleep_study.png", img_bytes, "image/png")},
        data={"policy_id": "LCD-L33829", "patient_id": "PT-IMG-502"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "extracted_text" in data
    assert len(data["extracted_text"]) > 20
    assert data["adjudication"]["policy_id"] == "LCD-L33829"
    assert data["packet"] is not None

def test_cms_policy_sync_endpoint():
    """Verify that Method 2: Automated CMS Policy Sync runs and updates local database."""
    res = client.post("/api/v1/policies/sync-cms")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "summary" in data
    assert data["summary"]["policies_checked"] >= 4
    assert "details" in data
    assert len(data["details"]) >= 4

def test_cms_policy_sync_status_endpoint():
    res = client.get("/api/v1/policies/sync-status")
    assert res.status_code == 200
    data = res.json()
    assert "last_sync_timestamp" in data
    assert "policies_checked" in data

def test_scan_all_policies_multi_morbidity():
    """Verify that multi-policy scan detects both NCD-20.4 (ICD) and LCD-L33829 (CPAP)."""
    multi_morbidity_note = """
    CARDIOLOGY & PULMONOLOGY CLINICAL ENCOUNTER:
    Patient PT-8821 evaluated in outpatient clinic.
    History of ischemic cardiomyopathy with severe LV systolic dysfunction.
    Diagnostic transthoracic echocardiogram confirms Left Ventricular Ejection Fraction (LVEF) of 28%.
    Persistent NYHA Class III heart failure symptoms with dyspnea on minimal exertion.
    Patient maintained on guideline-directed medical therapy (GDMT) including sacubitril/valsartan,
    carvedilol, and spironolactone continuously for > 90 days (120 days total).
    No myocardial infarction within the past 40 days; no CABG or PCI within past 90 days.
    
    SLEEP MEDICINE EVALUATION:
    Face-to-face clinical evaluation conducted prior to sleep study for severe daytime somnolence.
    Overnight diagnostic polysomnography demonstrated an Apnea-Hypopnea Index (AHI) of 26 events/hr.
    Patient is indicated for Continuous Positive Airway Pressure (CPAP) therapy.
    """
    res = client.post(
        "/api/v1/adjudicate/scan-all",
        json={
            "patient_id": "PT-8821",
            "ehr_narrative": multi_morbidity_note
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total_policies_scanned"] >= 4
    assert data["approved_count"] >= 2  # Both NCD-20.4 and LCD-L33829 should be approved
    assert data["best_match_policy_id"] is not None
    assert len(data["multi_morbidity_insights"]) >= 2
    # Verify that approved matches contain NCD-20.4 and LCD-L33829
    approved_ids = [m["policy_id"] for m in data["all_matches"] if m["decision"] == "APPROVED"]
    assert "NCD-20.4" in approved_ids
    assert "LCD-L33829" in approved_ids

def test_generate_peer_to_peer_appeal_letter_endpoint():
    """Verify that peer-to-peer appeal letter is generated with talking points and statutory basis."""
    # 1. Adjudicate a case
    adj_res = client.post(
        "/api/v1/adjudicate",
        json={
            "patient_id": "PT-APL-TEST",
            "policy_id": "NCD-20.4",
            "ehr_narrative": "Patient has severe ischemic cardiomyopathy with LVEF 45% (fails <=35%)."
        }
    )
    assert adj_res.status_code == 200
    case_id = adj_res.json()["case_id"]

    # 2. Request Appeal Letter
    apl_res = client.post(
        f"/api/v1/packet/{case_id}/appeal-letter",
        json={
            "case_id": case_id,
            "physician_name": "Dr. Sarah Jenkins, MD, FACC",
            "physician_npi": "1043256787",
            "reconsideration_notes": "Clinical condition reflects progressive decompensation under exercise stress."
        }
    )
    assert apl_res.status_code == 200
    apl_data = apl_res.json()
    assert apl_data["appeal_id"].startswith("APL-")
    assert "peer_to_peer_talking_points" in apl_data
    assert len(apl_data["peer_to_peer_talking_points"]) >= 2
    assert "Section 1869 of the Social Security Act" in apl_data["statutory_legal_basis"]
    assert "EXPEDITED PEER-TO-PEER RECONSIDERATION REQUEST" in apl_data["full_letter_text"]
    assert "Dr. Sarah Jenkins, MD, FACC" in apl_data["full_letter_text"]

def test_fhir_bundle_export_and_ehr_push_endpoints():
    """Verify standard HL7 FHIR R4 Da Vinci PAS export and simulated direct EHR push."""
    # 1. Adjudicate a qualifying case
    adj_res = client.post(
        "/api/v1/adjudicate",
        json={
            "patient_id": "PT-FHIR-TEST",
            "policy_id": "LCD-L33829",
            "ehr_narrative": "Face-to-face evaluation conducted. Diagnostic polysomnogram shows AHI 22/hr."
        }
    )
    assert adj_res.status_code == 200
    case_id = adj_res.json()["case_id"]

    # 2. Export HL7 FHIR Bundle
    fhir_res = client.get(f"/api/v1/packet/{case_id}/fhir")
    assert fhir_res.status_code == 200
    bundle = fhir_res.json()
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "collection"
    assert len(bundle["entry"]) >= 4

    resource_types = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert "Patient" in resource_types
    assert "Practitioner" in resource_types
    assert "Claim" in resource_types
    assert "DocumentReference" in resource_types

    # 3. Direct EHR Push Simulation
    push_res = client.post(
        f"/api/v1/packet/{case_id}/ehr-push",
        json={
            "case_id": case_id,
            "ehr_system": "Epic Systems Hyperdrive / FHIR R4 Endpoint"
        }
    )
    assert push_res.status_code == 200
    push_data = push_res.json()
    assert push_data["status"] == "SUCCESS_TRANSMITTED"
    assert push_data["ehr_document_id"].startswith("EPIC-DOC-")
    assert push_data["case_id"] == case_id
    assert "Epic Systems Hyperdrive" in push_data["ehr_system"]

def test_billing_validator_cpt_icd10_and_carc_rarc_codes():
    """Verify CPT/HCPCS and ICD-10 cross-checking against CMS billing rules and CARC/RARC codes."""
    # 1. Valid compliant billing codes
    res_valid = client.post(
        "/api/v1/adjudicate",
        json={
            "patient_id": "PT-BILL-01",
            "policy_id": "NCD-20.4",
            "ehr_narrative": (
                "Patient with ischemic cardiomyopathy, NYHA Class III, LVEF 28%. "
                "Guideline-directed medical therapy for 6 months. No acute MI. "
                "Planned procedure: CPT 33249. Primary diagnosis: ICD-10 I42.0."
            ),
            "cpt_codes": ["33249"],
            "icd10_codes": ["I42.0"]
        }
    )
    assert res_valid.status_code == 200
    data_valid = res_valid.json()
    assert data_valid["billing_validation"]["is_billing_compliant"] is True
    assert data_valid["billing_validation"]["is_cpt_covered"] is True
    assert data_valid["billing_validation"]["is_icd10_covered"] is True
    carc_codes = [c["code"] for c in data_valid["carc_codes"]]
    assert "CARC 0" in carc_codes

    # 2. Incompatible / Non-covered diagnosis (e.g. R00.1 Bradycardia for ICD or invalid CPT)
    res_invalid = client.post(
        "/api/v1/adjudicate",
        json={
            "patient_id": "PT-BILL-02",
            "policy_id": "NCD-20.4",
            "ehr_narrative": "Patient evaluated for cardiac rhythm device.",
            "cpt_codes": ["99213"],
            "icd10_codes": ["R00.1"]
        }
    )
    assert res_invalid.status_code == 200
    data_invalid = res_invalid.json()
    assert data_invalid["billing_validation"]["is_billing_compliant"] is False
    carc_invalid = [c["code"] for c in data_invalid["carc_codes"]]
    assert "CARC 197" in carc_invalid or "CARC 50" in carc_invalid
    rarc_invalid = [r["code"] for r in data_invalid["rarc_codes"]]
    assert "RARC N54" in rarc_invalid or "RARC M62" in rarc_invalid

def test_clinical_timeline_waiting_period_reasoning():
    """Verify longitudinal clinical timeline calculation (e.g. 40 days post-MI under NCD 20.4)."""
    # 1. Premature scenario: MI occurred 14 days ago (violates >= 40-day mandate)
    res_premature = client.post(
        "/api/v1/adjudicate",
        json={
            "patient_id": "PT-TIMELINE-PREMATURE",
            "policy_id": "NCD-20.4",
            "ehr_narrative": (
                "Date of Evaluation: 2026-02-15.\n"
                "Patient had acute myocardial infarction on 2026-02-01. "
                "Echo shows LVEF 26%, NYHA Class III heart failure. On GDMT for > 90 days."
            )
        }
    )
    assert res_premature.status_code == 200
    premature_data = res_premature.json()
    assert premature_data["timeline_analysis"]["all_waiting_periods_satisfied"] is False
    milestones = premature_data["timeline_analysis"]["milestones"]
    assert len(milestones) >= 1
    mi_milestone = next(m for m in milestones if m["event_type"] == "POST_MYOCARDIAL_INFARCTION")
    assert mi_milestone["status"] == "WAITING_PERIOD_UNMET"
    assert mi_milestone["elapsed_days"] == 14
    assert mi_milestone["deficit_days"] == 26
    assert premature_data["adjudication_decision"] == "DENIED"

    # 2. Compliant scenario: MI occurred 120 days ago (satisfies >= 40-day mandate)
    res_compliant = client.post(
        "/api/v1/adjudicate",
        json={
            "patient_id": "PT-TIMELINE-COMPLIANT",
            "policy_id": "NCD-20.4",
            "ehr_narrative": (
                "Date of Evaluation: 2026-03-01.\n"
                "Patient with prior STEMI on 2025-10-15. "
                "Current echocardiogram demonstrates LVEF 28%, NYHA III symptoms. "
                "Guideline-directed medical therapy for > 90 days."
            )
        }
    )
    assert res_compliant.status_code == 200
    compliant_data = res_compliant.json()
    assert compliant_data["timeline_analysis"]["all_waiting_periods_satisfied"] is True
    mi_comp = next(m for m in compliant_data["timeline_analysis"]["milestones"] if m["event_type"] == "POST_MYOCARDIAL_INFARCTION")
    assert mi_comp["status"] == "SATISFIED"
    assert mi_comp["elapsed_days"] >= 40

def test_smart_addendum_deficiency_resolution_and_readjudication():
    """Verify one-click Smart Addendum generation to resolve missing clinical criteria."""
    # 1. Adjudicate note missing GDMT duration (LVEF and NYHA present, but GDMT absent)
    init_res = client.post(
        "/api/v1/adjudicate",
        json={
            "patient_id": "PT-ADDENDUM-TEST",
            "policy_id": "NCD-20.4",
            "ehr_narrative": (
                "Cardiology clinic note. Patient has dilated cardiomyopathy, NYHA Class III, "
                "recent echocardiogram reveals LVEF 29%. No prior acute MI."
            )
        }
    )
    assert init_res.status_code == 200
    case_id = init_res.json()["case_id"]
    init_decision = init_res.json()["adjudication_decision"]

    # 2. Append attested clinician addendum supplying GDMT compliance
    addendum_res = client.post(
        f"/api/v1/packet/{case_id}/addendum",
        json={
            "criterion_code": "CRIT-ICD-04",
            "addendum_text": "Patient has been compliant on optimal GDMT with Carvedilol 25mg BID and Entresto 49/51mg BID for > 120 days with good tolerance.",
            "clinician_name": "Dr. Eleanor Vance, MD",
            "clinician_npi": "1043256787"
        }
    )
    assert addendum_res.status_code == 200
    addendum_data = addendum_res.json()
    assert addendum_data["status"] == "ADDENDUM_APPLIED"
    assert addendum_data["addendum_id"].startswith("ADDENDUM-")
    assert addendum_data["signed_npi"] == "1043256787"
    assert addendum_data["updated_decision"] == "APPROVED"
    assert addendum_data["updated_confidence"] >= 0.85

def test_hipaa_audit_trail_inspection_and_csv_export():
    """Verify inspection and RFC 4180 CSV export of the tamper-evident audit ledger."""
    # 1. Inspect audit trail JSON
    trail_res = client.get("/api/v1/audit/trail")
    assert trail_res.status_code == 200
    trail_data = trail_res.json()
    assert "total_events" in trail_data
    assert "system_mode" in trail_data
    assert isinstance(trail_data["events"], list)

    # 2. Export audit trail CSV
    export_res = client.get("/api/v1/audit/trail/export")
    assert export_res.status_code == 200
    assert "text/csv" in export_res.headers["content-type"]
    assert 'attachment; filename="carepolicyguard_audit_trail.csv"' in export_res.headers["content-disposition"]
    csv_text = export_res.text
    assert "Event ID" in csv_text
    assert "Audit Hash (SHA-256)" in csv_text
    assert "Action Details" in csv_text




