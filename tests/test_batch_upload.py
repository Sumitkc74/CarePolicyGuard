import pytest
import io
import json
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_batch_upload_csv():
    csv_content = """patient_id,policy_id,requested_procedure_code,clinical_narrative
PT-CSV-101,NCD-20.4,33249,"Patient with severe ischemic cardiomyopathy. LVEF 28%. NYHA II. On GDMT >6 months."
PT-CSV-102,NCD-20.4,33249,"Patient with recent myocardial infarction 10 days ago. LVEF 30%."
"""
    files = [("files", ("roster.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv"))]
    res = client.post("/api/v1/adjudicate/batch/upload-parse", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["total_patients"] == 2
    assert data["items"][0]["patient_id"] == "PT-CSV-101"
    assert data["items"][0]["policy_id"] == "NCD-20.4"
    assert "LVEF 28%" in data["items"][0]["clinical_narrative"]
    assert data["items"][1]["patient_id"] == "PT-CSV-102"

def test_batch_upload_json():
    json_data = [
        {
            "patient_id": "PT-JSON-201",
            "policy_id": "LCD-L33829",
            "requested_procedure_code": "E0601",
            "clinical_narrative": "Patient with obstructive sleep apnea. Epworth 16. AHI 34.2 events/hr."
        }
    ]
    files = [("files", ("roster.json", io.BytesIO(json.dumps(json_data).encode("utf-8")), "application/json"))]
    res = client.post("/api/v1/adjudicate/batch/upload-parse", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["total_patients"] == 1
    assert data["items"][0]["patient_id"] == "PT-JSON-201"
    assert data["items"][0]["policy_id"] == "LCD-L33829"

def test_multipage_extract_text():
    file1 = ("files", ("page1.txt", io.BytesIO(b"Page 1: 68-year-old male with severe heart failure."), "text/plain"))
    file2 = ("files", ("page2.txt", io.BytesIO(b"Page 2: Echocardiogram confirms LVEF 27% and NYHA Class III."), "text/plain"))
    res = client.post("/api/v1/extract-text", files=[file1, file2])
    assert res.status_code == 200
    data = res.json()
    assert data["files_count"] == 2
    assert "Page 1:" in data["extracted_text"]
    assert "Page 2:" in data["extracted_text"]
    assert "NCD-20.4" in data["suggested_policy_id"]

