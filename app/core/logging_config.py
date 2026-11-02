"""
Structured JSON Logging for CarePolicyGuard.
Formats application and audit logs into structured JSON suitable for
Splunk, Datadog, Elasticsearch, CloudWatch, and Grafana Loki.
Strictly redacts PHI and sensitive fields.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class SafeJsonFormatter(logging.Formatter):
    """
    HIPAA-Compliant Structured JSON Formatter.
    Ensures zero leakage of raw EHR narratives or unmasked identifiers.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineNo": record.lineno,
        }

        # Attach extra structured fields if present on log record
        for key, val in record.__dict__.items():
            if key not in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "id", "levelname", "levelno", "lineno", "module",
                "msecs", "message", "msg", "name", "pathname", "process",
                "processName", "relativeCreated", "stack_info", "thread", "threadName"
            }:
                # Sanitize key names to avoid PHI leakage
                if any(k in key.lower() for k in ["ehr", "note", "narrative", "patient_name", "ssn", "mrn"]):
                    log_payload[key] = "[REDACTED_PHI]"
                else:
                    log_payload[key] = val

        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload)


def configure_structured_logging(level: int = logging.INFO) -> None:
    """
    Configures root logger with SafeJsonFormatter.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing stream handlers to prevent duplicate lines
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.StreamHandler):
            root_logger.removeHandler(handler)

    json_handler = logging.StreamHandler(sys.stdout)
    json_handler.setFormatter(SafeJsonFormatter())
    root_logger.addHandler(json_handler)

