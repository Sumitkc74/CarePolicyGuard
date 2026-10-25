import time
import pytest
from fastapi.testclient import TestClient
from main import app
from app.core.cache import policy_cache, CacheSecurityException
from app.core.idempotency import idempotency_engine
from app.core.rate_limiter import limiter, SlidingWindowRateLimiter

client = TestClient(app)

@pytest.fixture(autouse=True)
def cleanup_system_caches():
    policy_cache.clear()
    idempotency_engine.clear()
    limiter.reset_all()
    yield
    policy_cache.clear()
    idempotency_engine.clear()
    limiter.reset_all()


def test_policy_cache_lifecycle_and_metrics():
    # Cache miss
    assert policy_cache.get("criteria:TEST-POL") is None
    metrics_initial = policy_cache.get_metrics()
    assert metrics_initial["misses"] == 1
    assert metrics_initial["hits"] == 0

    # Cache set and hit
    policy_cache.set("criteria:TEST-POL", [{"code": "CRIT-1", "score": 0.85}], ttl_seconds=60)
    cached_val = policy_cache.get("criteria:TEST-POL")
    assert cached_val is not None
    assert cached_val[0]["code"] == "CRIT-1"

    metrics_after_hit = policy_cache.get_metrics()
    assert metrics_after_hit["hits"] == 1
    assert metrics_after_hit["hit_ratio"] == 0.5

    # Invalidation
    assert policy_cache.invalidate("criteria:TEST-POL") is True
    assert policy_cache.get("criteria:TEST-POL") is None


def test_hipaa_phi_cache_prevention_guardrail():
    # Attempting to cache patient identifiers or raw EHR narratives must trigger a security exception
    forbidden_keys = [
        "patient:PT-12345",
        "pt-49821_diagnosis",
        "mrn:994821",
        "ssn:000-11-2222",
        "clinical_note:extract"
    ]

    for key in forbidden_keys:
        with pytest.raises(CacheSecurityException):
            policy_cache.set(key, "sensitive clinical text")

        with pytest.raises(CacheSecurityException):
            policy_cache.get(key)


def test_idempotency_engine_in_flight_concurrency():
    call_count = 0

    def expensive_action():
        nonlocal call_count
        call_count += 1
        time.sleep(0.01)
        return {"decision": "APPROVED", "token": "AUTH-123"}, 200, {"Custom-Header": "Val"}

    test_key = "claim-tx-9948"

    # First execution
    payload1, status1, headers1, is_replay1 = idempotency_engine.execute_idempotent(
        idempotency_key=test_key,
        action=expensive_action
    )
    assert not is_replay1
    assert payload1["decision"] == "APPROVED"
    assert call_count == 1

    # Replay execution
    payload2, status2, headers2, is_replay2 = idempotency_engine.execute_idempotent(
        idempotency_key=test_key,
        action=expensive_action
    )
    assert is_replay2
    assert payload2["decision"] == "APPROVED"
    assert payload2["token"] == "AUTH-123"
    # Action must NOT be executed a second time
    assert call_count == 1


def test_api_adjudicate_idempotency_key_replay():
    payload = {
        "patient_id": "PT-SYS-TEST-01",
        "policy_id": "NCD-20.4",
        "ehr_narrative": (
            "Patient is 68 years old with ischemic cardiomyopathy. "
            "Transthoracic echocardiogram confirms left ventricular ejection fraction LVEF 26%. "
            "NYHA Functional Class III symptoms persist despite optimal GDMT therapy. "
            "No acute MI in prior 40 days. Non-ischemic dilated cardiomyopathy excluded."
        ),
        "options": {"save_record": False}
    }

    idemp_header = {"Idempotency-Key": "idemp-adjudicate-req-401"}

    # Initial request
    resp1 = client.post("/api/v1/adjudicate", json=payload, headers=idemp_header)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "Idempotency-Replay" not in resp1.headers
    case_id_1 = data1["case_id"]

    # Replay request with identical Idempotency-Key
    resp2 = client.post("/api/v1/adjudicate", json=payload, headers=idemp_header)
    assert resp2.status_code == 200
    assert resp2.headers.get("Idempotency-Replay") == "true"
    data2 = resp2.json()
    # Must replay the identical case and outcome
    assert data2["case_id"] == case_id_1
    assert data2["adjudication_decision"] == data1["adjudication_decision"]


def test_da_vinci_pas_submit_idempotency():
    claim_payload = {
        "resourceType": "Claim",
        "use": "preauthorization",
        "patient": {"reference": "Patient/PT-IDEMP-02"},
        "provider": {"reference": "Practitioner/NPI-994821"},
        "item": [
            {
                "sequence": 1,
                "productOrService": {
                    "coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": "33249"}]
                }
            }
        ],
        "supportingInfo": [
            {
                "sequence": 1,
                "valueString": "Patient with NYHA Class III heart failure, documented LVEF 25% on GDMT."
            }
        ]
    }

    idemp_header = {"Idempotency-Key": "pas-claim-key-778"}

    # Submit 1
    resp1 = client.post("/api/v1/pas/submit", json=claim_payload, headers=idemp_header)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "Idempotency-Replay" not in resp1.headers
    resp_id_1 = data1["id"]

    # Submit 2 with same idempotency key
    resp2 = client.post("/api/v1/pas/submit", json=claim_payload, headers=idemp_header)
    assert resp2.status_code == 200
    assert resp2.headers.get("Idempotency-Replay") == "true"
    data2 = resp2.json()
    assert data2["id"] == resp_id_1
    assert data2["outcome"] == data1["outcome"]


def test_system_cache_telemetry_endpoint():
    resp = client.get("/api/v1/system/cache-metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert "hits" in data
    assert "misses" in data
    assert "hit_ratio" in data
    assert "active_cached_keys" in data
    assert "default_ttl_seconds" in data

