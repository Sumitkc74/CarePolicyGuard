from typing import Optional
from fastapi import APIRouter, Query, HTTPException, status
from app.services.smart_fhir_connector import (
    SMARTonFHIRConnectorService,
    SMARTTokenResponse,
    FHIRPatientChart
)

def register_smart_fhir_routes(api_router: APIRouter):
    @api_router.get("/fhir/.well-known/smart-configuration", summary="SMART on FHIR Discovery Metadata")
    def get_smart_discovery():
        """
        RFC 8414 /.well-known/smart-configuration endpoint for EHR App Launch handshake.
        """
        return SMARTonFHIRConnectorService.get_smart_configuration()

    @api_router.post("/fhir/auth/token", response_model=SMARTTokenResponse, summary="SMART OAuth2 Token Exchange")
    def smart_token_exchange(
        code: str = Query("mock_code_123", description="Authorization code from EHR launch"),
        patient: Optional[str] = Query("EPIC-PT-1049", description="Patient ID in EHR context"),
        encounter: Optional[str] = Query("ENC-88301", description="Encounter ID in EHR context")
    ):
        """
        Simulates SMART on FHIR OAuth2 token exchange with Epic or Cerner sandbox.
        """
        return SMARTonFHIRConnectorService.exchange_launch_token(
            code=code,
            patient_id=patient,
            encounter_id=encounter
        )

    @api_router.get("/fhir/patients/{patient_id}/chart", response_model=FHIRPatientChart, summary="Fetch EHR Clinical Chart via FHIR R4")
    def fetch_ehr_patient_chart(patient_id: str):
        """
        Pulls structured FHIR resources (Conditions, Observations, Medications, Notes) from the EHR
        and returns a synthesized progress note ready for multi-agent prior-authorization adjudication.
        """
        return SMARTonFHIRConnectorService.fetch_patient_chart(patient_id)

