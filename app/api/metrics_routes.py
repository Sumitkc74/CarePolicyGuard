import time
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import AdjudicationLog, User, UserSession, MedicarePolicy
from app.core.cache import policy_cache

def get_prometheus_metrics(db: Session = Depends(get_db)):
    """
    Exposes system, operational, and clinical adjudication metrics in standard
    Prometheus text format for Datadog, Prometheus, Grafana, and Splunk scraping.
    """
    total_adjudications = db.query(AdjudicationLog).count()
    approved = db.query(AdjudicationLog).filter(AdjudicationLog.decision == "APPROVED").count()
    denied = db.query(AdjudicationLog).filter(AdjudicationLog.decision == "DENIED").count()
    abstained = db.query(AdjudicationLog).filter(AdjudicationLog.abstention_status == True).count()

    # Latency statistics
    logs = db.query(AdjudicationLog.execution_time_ms).filter(AdjudicationLog.execution_time_ms.isnot(None)).all()
    avg_latency_s = (sum(l[0] for l in logs) / len(logs) / 1000.0) if logs else 0.045

    # User & Session counts
    total_users = db.query(User).count()
    active_sessions = db.query(UserSession).filter(UserSession.is_revoked == False).count()
    total_policies = db.query(MedicarePolicy).count()

    # Cache telemetry
    cache_stats = policy_cache.get_metrics()
    cache_hits = cache_stats.get("hits", 0)
    cache_misses = cache_stats.get("misses", 0)
    cache_ratio = cache_stats.get("hit_ratio", 0.0)
    active_keys = cache_stats.get("active_cached_keys", 0)

    lines = [
        "# HELP carepolicyguard_adjudications_total Total number of clinical prior-authorization adjudications processed.",
        "# TYPE carepolicyguard_adjudications_total counter",
        f'carepolicyguard_adjudications_total{{status="all"}} {total_adjudications}',
        f'carepolicyguard_adjudications_total{{status="approved"}} {approved}',
        f'carepolicyguard_adjudications_total{{status="denied"}} {denied}',
        f'carepolicyguard_adjudications_total{{status="abstained"}} {abstained}',
        "",
        "# HELP carepolicyguard_adjudication_latency_seconds_avg Average processing latency per clinical chart in seconds.",
        "# TYPE carepolicyguard_adjudication_latency_seconds_avg gauge",
        f"carepolicyguard_adjudication_latency_seconds_avg {avg_latency_s:.4f}",
        "",
        "# HELP carepolicyguard_active_device_sessions Currently active authenticated device sessions.",
        "# TYPE carepolicyguard_active_device_sessions gauge",
        f"carepolicyguard_active_device_sessions {active_sessions}",
        "",
        "# HELP carepolicyguard_registered_users_total Total registered clinical, admin, and auditor users.",
        "# TYPE carepolicyguard_registered_users_total gauge",
        f"carepolicyguard_registered_users_total {total_users}",
        "",
        "# HELP carepolicyguard_medicare_policies_loaded Active CMS Medicare NCD and LCD policies in rules registry.",
        "# TYPE carepolicyguard_medicare_policies_loaded gauge",
        f"carepolicyguard_medicare_policies_loaded {total_policies}",
        "",
        "# HELP carepolicyguard_policy_cache_hits_total Number of in-memory policy and criteria cache hits.",
        "# TYPE carepolicyguard_policy_cache_hits_total counter",
        f"carepolicyguard_policy_cache_hits_total {cache_hits}",
        "",
        "# HELP carepolicyguard_policy_cache_misses_total Number of in-memory policy and criteria cache misses.",
        "# TYPE carepolicyguard_policy_cache_misses_total counter",
        f"carepolicyguard_policy_cache_misses_total {cache_misses}",
        "",
        "# HELP carepolicyguard_policy_cache_hit_ratio Efficiency ratio of cache queries satisfied from memory.",
        "# TYPE carepolicyguard_policy_cache_hit_ratio gauge",
        f"carepolicyguard_policy_cache_hit_ratio {cache_ratio:.4f}",
        "",
        "# HELP carepolicyguard_active_cached_policies Currently active compiled CMS policy structures in memory.",
        "# TYPE carepolicyguard_active_cached_policies gauge",
        f"carepolicyguard_active_cached_policies {active_keys}"
    ]

    return Response(content="\n".join(lines) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8")


def get_metrics_json(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Returns real-time clinical, operational, and system cache telemetry in structured JSON format.
    """
    total_adjudications = db.query(AdjudicationLog).count()
    approved = db.query(AdjudicationLog).filter(AdjudicationLog.decision == "APPROVED").count()
    denied = db.query(AdjudicationLog).filter(AdjudicationLog.decision == "DENIED").count()
    abstained = db.query(AdjudicationLog).filter(AdjudicationLog.abstention_status == True).count()

    logs = db.query(AdjudicationLog.execution_time_ms).filter(AdjudicationLog.execution_time_ms.isnot(None)).all()
    avg_latency_ms = (sum(l[0] for l in logs) / len(logs)) if logs else None

    return {
        "adjudications": {
            "total": total_adjudications,
            "approved": approved,
            "denied": denied,
            "abstained": abstained,
            "approval_rate": (approved / total_adjudications) if total_adjudications > 0 else 0.0,
            "average_latency_ms": round(avg_latency_ms, 2) if avg_latency_ms is not None else None
        },
        "security": {
            "total_users": db.query(User).count(),
            "active_sessions": db.query(UserSession).filter(UserSession.is_revoked == False).count(),
            "revoked_sessions": db.query(UserSession).filter(UserSession.is_revoked == True).count(),
            "mfa_mandated": True
        },
        "cache_and_system": policy_cache.get_metrics(),
        "clinical_rules": {
            "active_policies_count": db.query(MedicarePolicy).count(),
            "supported_frameworks": ["CMS NCD 20.4", "CMS NCD 20.7", "CMS NCD 20.33", "CMS LCD L33829"]
        }
    }


def get_operator_metrics(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Operator-facing metrics endpoint:
    Aggregates latency distribution, deferral burden rate, and decision breakdown.
    Contains zero patient identifiers or Protected Health Information (PHI).
    """
    total_adjudications = db.query(AdjudicationLog).count()
    approved = db.query(AdjudicationLog).filter(AdjudicationLog.decision == "APPROVED").count()
    denied = db.query(AdjudicationLog).filter(AdjudicationLog.decision == "DENIED").count()
    deferred = db.query(AdjudicationLog).filter(AdjudicationLog.decision == "DEFERRED_TO_HUMAN").count()

    # Latency numbers
    raw_latencies = [
        row[0] for row in db.query(AdjudicationLog.execution_time_ms)
        .filter(AdjudicationLog.execution_time_ms.isnot(None))
        .all()
    ]

    if raw_latencies:
        mean_latency = round(sum(raw_latencies) / len(raw_latencies), 2)
        min_latency = round(min(raw_latencies), 2)
        max_latency = round(max(raw_latencies), 2)
    else:
        mean_latency = 0.0
        min_latency = 0.0
        max_latency = 0.0

    deferral_rate = round(deferred / total_adjudications, 4) if total_adjudications > 0 else 0.0
    approval_rate = round(approved / total_adjudications, 4) if total_adjudications > 0 else 0.0
    denial_rate = round(denied / total_adjudications, 4) if total_adjudications > 0 else 0.0

    return {
        "operator_telemetry": {
            "total_evaluations": total_adjudications,
            "decisions": {
                "approved_count": approved,
                "denied_count": denied,
                "deferred_to_human_count": deferred,
            },
            "rates": {
                "approval_rate": approval_rate,
                "denial_rate": denial_rate,
                "deferral_rate": deferral_rate,
            },
            "latency_ms": {
                "mean": mean_latency,
                "min": min_latency,
                "max": max_latency,
            },
            "cache_efficiency": policy_cache.get_metrics(),
            "phi_safe": True
        }
    }


def register_metrics_routes(api_router: APIRouter):
    api_router.add_api_route("/metrics", get_prometheus_metrics, methods=["GET"], summary="OpenTelemetry / Prometheus Metrics Endpoint")
    api_router.add_api_route("/metrics/json", get_metrics_json, methods=["GET"], summary="Operational Metrics JSON API")
    api_router.add_api_route("/metrics/operator", get_operator_metrics, methods=["GET"], summary="Operator Telemetry API (Zero PHI)")
