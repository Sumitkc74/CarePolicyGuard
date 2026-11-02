"""
Policy Cache and Invalidation Tests.
Verifies:
1. Cache hit behavior on repeated policy retrieval.
2. Explicit cache invalidation via invalidate_policy and clear_cache.
3. Automatic disk-change invalidation based on file modification timestamps.
4. PolicyCacheManager TTL expiration and HIPAA Safe Harbor key protections.
"""

import time
import json
import tempfile
from pathlib import Path
import pytest

from app.core.cache import PolicyCacheManager, CacheSecurityException, policy_cache
from app.services.declarative_engine import DeclarativePolicyEngine


def test_declarative_policy_cache_hit_and_explicit_invalidation():
    """
    Verify DeclarativePolicyEngine caches loaded policies and explicitly invalidates them.
    """
    DeclarativePolicyEngine.clear_cache()

    # Initial load
    p1 = DeclarativePolicyEngine.load_policy("NCD-20.4")
    assert p1 is not None
    assert "NCD-20.4" in DeclarativePolicyEngine._POLICY_CACHE

    # Repeated load returns identical cached object
    p2 = DeclarativePolicyEngine.load_policy("NCD-20.4")
    assert p1 is p2

    # Explicit invalidation
    assert DeclarativePolicyEngine.invalidate_policy("NCD-20.4") is True
    assert "NCD-20.4" not in DeclarativePolicyEngine._POLICY_CACHE

    # Reload fetches a fresh instance
    p3 = DeclarativePolicyEngine.load_policy("NCD-20.4")
    assert p3 is not None
    assert p3 is not p1


def test_declarative_policy_cache_mtime_invalidation(monkeypatch, tmp_path):
    """
    Verify DeclarativePolicyEngine automatically detects on-disk modification
    and refreshes cached policy.
    """
    # Create a temporary policy file
    policy_id = "TEST-MOCK-POLICY"
    mock_file = tmp_path / f"{policy_id}.json"
    
    initial_data = {
        "policy_id": policy_id,
        "title": "Version 1 Policy",
        "jurisdiction": "National",
        "effective_date": "2026-01-01",
        "category": "Test",
        "description": "Initial policy version",
        "criteria": []
    }
    with open(mock_file, "w", encoding="utf-8") as f:
        json.dump(initial_data, f)

    # Point policies dir to tmp_path
    monkeypatch.setattr(DeclarativePolicyEngine, "get_policies_dir", classmethod(lambda cls: tmp_path))
    DeclarativePolicyEngine.clear_cache()

    # Load version 1
    p_v1 = DeclarativePolicyEngine.load_policy(policy_id)
    assert p_v1 is not None
    assert p_v1.title == "Version 1 Policy"

    # Modify policy on disk with updated title
    time.sleep(0.05)  # Ensure distinct mtime
    updated_data = dict(initial_data)
    updated_data["title"] = "Version 2 Updated Policy"
    with open(mock_file, "w", encoding="utf-8") as f:
        json.dump(updated_data, f)

    # Next load should automatically invalidate cache due to updated mtime
    p_v2 = DeclarativePolicyEngine.load_policy(policy_id)
    assert p_v2 is not None
    assert p_v2.title == "Version 2 Updated Policy"
    assert p_v2 is not p_v1


def test_policy_cache_manager_ttl_and_phi_guard():
    """
    Verify PolicyCacheManager expires keys after TTL and blocks PHI keys.
    """
    manager = PolicyCacheManager(default_ttl_seconds=1)
    
    # Normal key caching
    manager.set("policy:NCD-20.4:criteria", {"count": 4}, ttl_seconds=1)
    assert manager.get("policy:NCD-20.4:criteria") == {"count": 4}

    # Expire
    time.sleep(1.05)
    assert manager.get("policy:NCD-20.4:criteria") is None

    # HIPAA Safe Harbor key protection
    with pytest.raises(CacheSecurityException):
        manager.set("patient_123_ehr_data", "unauthorized_phi")

    with pytest.raises(CacheSecurityException):
        manager.get("mrn_98765_record")
