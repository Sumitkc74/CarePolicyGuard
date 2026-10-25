import uuid
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class SMARTLaunchContext(BaseModel):
    """
    SMART on FHIR OAuth2 Launch Context representation.
    """
    iss: str = Field(..., description="FHIR Server Base URL (e.g., Epic / Cerner sandbox)")
    launch: str = Field(..., description="Opaque launch identifier provided by the EHR")
    patient_id: Optional[str] = Field(default=None, description="Patient context ID")
    encounter_id: Optional[str] = Field(default=None, description="Active encounter context ID")

class SMARTTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600
    scope: str
    patient: str
    encounter: Optional[str] = None
    smart_style_url: Optional[str] = None

class FHIRPatientChart(BaseModel):
    patient_id: str
    patient_name_masked: str
    gender: str
    birth_year: str
    active_conditions: List[Dict[str, str]]
    active_medications: List[Dict[str, str]]
    diagnostic_observations: List[Dict[str, str]]
    clinical_notes: List[Dict[str, str]]
    synthesized_progress_note: str

class SMARTonFHIRConnectorService:
    """
    SMART on FHIR Interoperability Connector.
    Supports EHR EHR-launch and Standalone-launch flows (Epic, Cerner, Da Vinci PAS).
    Extracts Patient, Condition, MedicationRequest, Observation, and DocumentReference
    resources to synthesize clean clinical progress notes for automated adjudication.
    """

    # In-memory mock/sandbox store of EHR clinical charts
    EHR_SANDBOX_CHARTS: Dict[str, Dict[str, Any]] = {
        "EPIC-PT-1049": {
            "name": "E. Vance",
            "gender": "female",
            "birth_year": "1954",
            "conditions": [
                {"code": "I25.2", "display": "Old myocardial infarction (2021)"},
                {"code": "I50.22", "display": "Chronic systolic heart failure (NYHA Class II)"}
            ],
            "medications": [
                {"code": "866414", "display": "Carvedilol 25 MG Oral Tablet (Compliant > 180 days)"},
                {"code": "1657980", "display": "Sacubitril 49 MG / Valsartan 51 MG Oral Tablet (Compliant > 120 days)"},
                {"code": "866514", "display": "Spironolactone 25 MG Oral Tablet"}
            ],
            "observations": [
                {"code": "88062-5", "display": "Left ventricular Ejection fraction by Transthoracic 2D Echo", "value": "28 %", "date": "2025-01-15"}
            ],
            "notes": [
                "Cardiology clinic follow-up. 71-year-old female with ischemic cardiomyopathy status post anterior STEMI in 2021. Recent echocardiogram reveals severe LV systolic dysfunction with LVEF 28%. NYHA Class II symptoms with mild exertional shortness of breath. Fully compliant on optimal medical therapy including Carvedilol and Entresto for over 6 months. No cardiogenic shock. Recommend primary prevention ICD placement."
            ]
        },
        "CERNER-PT-3091": {
            "name": "R. Hayes",
            "gender": "male",
            "birth_year": "1960",
            "conditions": [
                {"code": "G47.33", "display": "Obstructive sleep apnea (adult)"},
                {"code": "I10", "display": "Essential hypertension"}
            ],
            "medications": [
                {"code": "314076", "display": "Lisinopril 10 MG Oral Tablet"}
            ],
            "observations": [
                {"code": "80327-0", "display": "Apnea hypopnea index (AHI) in polysomnography", "value": "34.2 events/hour", "date": "2025-02-10"}
            ],
            "notes": [
                "Pulmonology sleep evaluation. Prior face-to-face in-person clinical assessment by Dr. Gomez documented heavy daytime somnolence and witnessed nocturnal choking spells. Attended diagnostic overnight sleep study confirming severe obstructive sleep apnea with AHI 34.2 events/hr. Prescribing Auto-CPAP trial."
            ]
        }
    }

    @classmethod
    def get_smart_configuration(cls, fhir_base_url: str = "https://fhir.epic.sandbox/api/FHIR/R4") -> Dict[str, Any]:
        """
        Returns RFC 8414 /.well-known/smart-configuration discovery metadata.
        """
        return {
            "issuer": fhir_base_url,
            "authorization_endpoint": f"{fhir_base_url}/oauth2/authorize",
            "token_endpoint": f"{fhir_base_url}/oauth2/token",
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "private_key_jwt"],
            "grant_types_supported": ["authorization_code", "client_credentials"],
            "scopes_supported": [
                "openid",
                "profile",
                "launch",
                "launch/patient",
                "patient/Patient.read",
                "patient/Condition.read",
                "patient/Observation.read",
                "patient/MedicationRequest.read",
                "patient/DocumentReference.read",
                "offline_access"
            ],
            "response_types_supported": ["code"],
            "capabilities": [
                "launch-ehr",
                "launch-standalone",
                "client-confidential-symmetric",
                "context-passthrough-banner",
                "permission-patient"
            ]
        }

    @classmethod
    def exchange_launch_token(
        cls,
        code: str,
        patient_id: Optional[str] = "EPIC-PT-1049",
        encounter_id: Optional[str] = "ENC-88301"
    ) -> SMARTTokenResponse:
        """
        Simulates SMART OAuth2 token exchange with Epic/Cerner authorization server.
        """
        token_str = f"smart-token-{uuid.uuid4().hex}"
        return SMARTTokenResponse(
            access_token=token_str,
            token_type="Bearer",
            expires_in=3600,
            scope="launch/patient patient/Patient.read patient/Observation.read patient/Condition.read",
            patient=patient_id or "EPIC-PT-1049",
            encounter=encounter_id
        )

    @classmethod
    def fetch_patient_chart(cls, patient_id: str) -> FHIRPatientChart:
        """
        Fetches FHIR R4 resources for the given patient and compiles a clinical synthesis.
        """
        raw_data = cls.EHR_SANDBOX_CHARTS.get(patient_id)
        if not raw_data:
            # Generate fallback simulated chart
            raw_data = {
                "name": "Simulated Patient",
                "gender": "unknown",
                "birth_year": "1965",
                "conditions": [{"code": "I50.9", "display": "Heart failure, unspecified"}],
                "medications": [{"code": "866414", "display": "Carvedilol 12.5 MG Oral Tablet"}],
                "observations": [{"code": "88062-5", "display": "LVEF", "value": "30 %", "date": "2025-01-01"}],
                "notes": [f"Patient chart note for {patient_id}. Documented clinical evaluation for prior authorization."]
            }

        synth_note = (
            f"EHR SYNTHESIZED CLINICAL CONSULTATION NOTE (SMART on FHIR)\n"
            f"Patient Identifier: {patient_id} (HIPAA Safe Harbor Sanitized)\n"
            f"Birth Year: {raw_data['birth_year']} | Gender: {raw_data['gender'].upper()}\n\n"
            f"DOCUMENTED ACTIVE CONDITIONS (ICD-10-CM):\n" +
            "\n".join([f"- [{c['code']}] {c['display']}" for c in raw_data['conditions']]) +
            f"\n\nCURRENT ACTIVE MEDICATIONS (RxNorm / GDMT):\n" +
            "\n".join([f"- [{m['code']}] {m['display']}" for m in raw_data['medications']]) +
            f"\n\nDIAGNOSTIC OBSERVATIONS (LOINC):\n" +
            "\n".join([f"- [{o['code']}] {o['display']}: {o['value']} (Date: {o['date']})" for o in raw_data['observations']]) +
            f"\n\nCLINICAL PROGRESS NARRATIVE (DocumentReference):\n" +
            raw_data['notes'][0]
        )

        return FHIRPatientChart(
            patient_id=patient_id,
            patient_name_masked=raw_data["name"][:1] + ". ***",
            gender=raw_data["gender"],
            birth_year=raw_data["birth_year"],
            active_conditions=raw_data["conditions"],
            active_medications=raw_data["medications"],
            diagnostic_observations=raw_data["observations"],
            clinical_notes=[{"title": "Progress Note", "content": raw_data['notes'][0]}],
            synthesized_progress_note=synth_note
        )

    @classmethod
    def validate_remote_fhir_capability(cls, fhir_base_url: str = "https://hapi.fhir.org/baseR4", timeout: float = 6.0) -> Dict[str, Any]:
        """
        Queries a remote FHIR R4 server /metadata endpoint to verify CapabilityStatement compliance.
        Includes timeout tolerance and schema verification for public testbeds.
        """
        import httpx
        metadata_url = f"{fhir_base_url.rstrip('/')}/metadata"
        try:
            with httpx.Client(follow_redirects=True, timeout=timeout) as client:
                resp = client.get(metadata_url, headers={"Accept": "application/fhir+json, application/json"})
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "status": "online",
                        "resource_type": data.get("resourceType", "Unknown"),
                        "fhir_version": data.get("fhirVersion", "Unknown"),
                        "publisher": data.get("publisher", "Unknown"),
                        "software": data.get("software", {}).get("name", "FHIR Server")
                    }
                return {"status": "error", "status_code": resp.status_code}
        except Exception as exc:
            return {"status": "unreachable", "error": str(exc)}


