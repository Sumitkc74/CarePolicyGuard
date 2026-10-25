import time
import pytest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

from main import app
from app.core.cache import policy_cache
from app.core.idempotency import idempotency_engine
from app.services.webhook_service import WebhookService

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_state():
    policy_cache.clear()
    idempotency_engine.clear()
    yield
    policy_cache.clear()
    idempotency_engine.clear()


def test_concurrent_adjudication_stress():
    """
    Stress test verifying thread safety, low latency, and zero race conditions
    under concurrent multi-threaded adjudication requests.
    """
    payload = {
        "patient_id": "PT-STRESS-CONC",
        "policy_id": "NCD-20.4",
        "ehr_narrative": (
            "Patient is 72 years old with severe ischemic heart disease. "
            "Echocardiogram demonstrates LVEF 24%. "
            "NYHA Class III heart failure persists on guideline-directed medical therapy. "
            "Prior MI occurred 9 months ago. No acute coronary events in preceding 40 days."
        ),
        "options": {"save_record": False}
    }

    # Initial warm-up to populate policy criteria cache
    warmup_res = client.post("/api/v1/adjudicate", json=payload)
    assert warmup_res.status_code == 200

    concurrency = 10
    results = []

    def run_single_adjudication(worker_id):
        headers = {
            "Idempotency-Key": f"stress-worker-key-{worker_id}",
            "X-Test-Bypass-Rate-Limit": "true"
        }
        start = time.perf_counter()
        resp = client.post("/api/v1/adjudicate", json=payload, headers=headers)
        dur = round((time.perf_counter() - start) * 1000, 2)
        return resp.status_code, dur, resp.json()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(run_single_adjudication, i) for i in range(concurrency)]
        for f in futures:
            status_code, duration_ms, data = f.result()
            results.append((status_code, duration_ms, data))

    # All concurrent requests must return HTTP 200
    for code, dur, data in results:
        assert code == 200
        assert data["adjudication_decision"] == "APPROVED"
        assert dur < 2500  # under 2.5s even under concurrency

    # Policy cache should have served concurrent requests with high hit ratio
    metrics = policy_cache.get_metrics()
    assert metrics["hits"] >= concurrency
    assert metrics["hit_ratio"] > 0.8


def test_batch_adjudication_with_webhook():
    """
    Tests batch adjudication RCM workflow with outbound HMAC-SHA256 webhook delivery.
    """
    batch_req = {
        "batch_name": "Cardiology Inpatient Roster",
        "webhook_url": "https://hospital-ehr.internal/webhooks/prior-auth",
        "webhook_secret": "secure_hmac_secret_994821",
        "items": [
            {
                "patient_id": "PT-BATCH-WH-01",
                "policy_id": "NCD-20.4",
                "requested_procedure_code": "33249",
                "clinical_narrative": (
                    "70-year-old male with ischemic cardiomyopathy, documented LVEF 22% on echo, "
                    "NYHA Class III dyspnea on GDMT. Remote MI 12 months ago."
                )
            },
            {
                "patient_id": "PT-BATCH-WH-02",
                "policy_id": "NCD-20.4",
                "requested_procedure_code": "33249",
                "clinical_narrative": (
                    "64-year-old female with LVEF 45%, NYHA Class I. Inconclusive findings."
                )
            },
            {
                "patient_id": "PT-BATCH-WH-03",
                "policy_id": "NCD-20.4",
                "requested_procedure_code": "33249",
                "clinical_narrative": (
                    "Patient suffered an acute myocardial infarction STEMI 12 days ago. "
                    "LVEF is 28%."
                )
            }
        ]
    }

    # Mock the outbound HTTP dispatch to simulate EHR webhook receiver
    with patch.object(WebhookService, "dispatch_webhook", return_value=True) as mock_dispatch:
        resp = client.post(
            "/api/v1/adjudicate/batch",
            json=batch_req,
            headers={"X-Test-Bypass-Rate-Limit": "true"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_patients"] == 3
        assert data["approved_count"] == 1
        assert data["deferred_count"] == 1
        assert data["denied_count"] == 1
        assert data["webhook_delivered"] is True

        mock_dispatch.assert_called_once()
        _, kwargs = mock_dispatch.call_args
        assert kwargs["webhook_url"] == "https://hospital-ehr.internal/webhooks/prior-auth"
        assert kwargs["secret"] == "secure_hmac_secret_994821"
        assert kwargs["payload"]["event"] == "batch_adjudication.completed"
        assert kwargs["payload"]["total_patients"] == 3


def test_webhook_service_hmac_signature():
    """
    Validates HMAC-SHA256 cryptographic signature computation for webhooks.
    """
    payload_bytes = b'{"event":"test","status":"success"}'
    secret = "test_hospital_shared_secret"

    sig = WebhookService.compute_signature(payload_bytes, secret)
    assert len(sig) == 64  # SHA-256 hex string length
    # Deterministic test
    sig2 = WebhookService.compute_signature(payload_bytes, secret)
    assert sig == sig2


def test_ui_endpoints_exist_and_healthy():
    """
    Verifies that all operational telemetry, Prometheus, and UI routes are responding correctly.
    """
    # Root Prometheus endpoint
    prom_res = client.get("/metrics")
    assert prom_res.status_code == 200
    assert "carepolicyguard_policy_cache_hits_total" in prom_res.text

    # Root JSON metrics endpoint
    json_res = client.get("/metrics/json")
    assert json_res.status_code == 200
    telemetry = json_res.json()
    assert "cache_and_system" in telemetry
    assert "adjudications" in telemetry
    assert "security" in telemetry

    # Index HTML with new PDF download buttons
    index_res = client.get("/")
    assert index_res.status_code == 200
    assert "downloadPacketPdf()" in index_res.text
    assert "downloadAppealLetterPdf()" in index_res.text
    assert "telemetry-cache-ratio" in index_res.text

