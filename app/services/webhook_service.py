import json
import hmac
import hashlib
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

class WebhookService:
    """
    Enterprise Outbound Webhook Dispatcher.
    Delivers signed real-time completion notifications to hospital EHR / RCM systems
    following large asynchronous batch adjudications.
    """

    @classmethod
    def compute_signature(cls, payload_bytes: bytes, secret: str) -> str:
        """Computes HMAC-SHA256 cryptographic signature."""
        return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    @classmethod
    def dispatch_webhook(
        cls,
        webhook_url: str,
        payload: Dict[str, Any],
        secret: Optional[str] = None,
        timeout_seconds: float = 4.0
    ) -> bool:
        """
        Dispatches an HTTP POST webhook with HMAC-SHA256 header.
        Returns True if the destination returned 2xx, False otherwise.
        """
        if not webhook_url or not webhook_url.startswith(("http://", "https://")):
            return False

        payload_bytes = json.dumps(payload, default=str).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "CarePolicyGuard-Webhook-Dispatcher/2.0"
        }

        if secret:
            sig = cls.compute_signature(payload_bytes, secret)
            headers["X-CarePolicyGuard-Signature"] = f"sha256={sig}"

        req = urllib.request.Request(
            webhook_url,
            data=payload_bytes,
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                return 200 <= response.status < 300
        except Exception as e:
            print(f"[-] Webhook delivery notice ({webhook_url}): {e}")
            return False

