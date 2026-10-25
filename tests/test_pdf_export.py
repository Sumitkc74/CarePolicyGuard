import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_pdf_export_endpoints():
    # 1. Create a prior-auth case
    note = """
    70-year-old female with ischemic cardiomyopathy. Prior MI in 2020.
    Echo on 02/01/2025 demonstrates severe LV systolic dysfunction with LVEF 26%.
    Patient reports NYHA Class II dyspnea.
    Documented >120 days compliance on GDMT including Metoprolol succinate 100mg and Sacubitril/Valsartan 49/51mg.
    No cardiogenic shock.
    """

    res = client.post("/api/v1/adjudicate", json={
        "patient_id": "PT-PDF-TEST-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": note,
        "cpt_codes": ["33249"]
    })
    assert res.status_code == 200
    adj_data = res.json()
    case_id = adj_data["case_id"]

    # 2. Test Coverage Packet PDF export
    pdf_res = client.get(f"/api/v1/packet/{case_id}/pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-1.4")
    assert len(pdf_res.content) > 500

    # 3. Test Appeal Letter PDF export
    appeal_pdf_res = client.get(f"/api/v1/packet/{case_id}/appeal-letter/pdf")
    assert appeal_pdf_res.status_code == 200
    assert appeal_pdf_res.headers["content-type"] == "application/pdf"
    assert appeal_pdf_res.content.startswith(b"%PDF-1.4")
    assert len(appeal_pdf_res.content) > 500

