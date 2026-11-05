import json
import logging
import urllib.parse
import urllib.request
from typing import Any

from app.core.security import validate_npi_luhn

logger = logging.getLogger("app.services.nppes")

NPPES_API_BASE = "https://npiregistry.cms.hhs.gov/api/"


def clean_name_tokens(name_str: str) -> set[str]:
    """
    Normalizes a provider name into clean alphanumeric lowercase tokens,
    stripping titles, honorifics, and punctuation.
    """
    if not name_str:
        return set()
    cleaned = name_str.lower().replace(",", " ").replace(".", " ").replace("-", " ")
    ignored_tokens = {
        "dr", "dr.", "md", "do", "np", "pa", "pac", "pa-c", "mbbs", "crna",
        "pharmd", "facc", "faha", "facp", "phd", "ms", "rn", "bsn"
    }
    tokens = {t.strip() for t in cleaned.split() if t.strip() and t.strip() not in ignored_tokens}
    return tokens


def verify_npi_with_nppes(npi: str, account_holder_name: str) -> dict[str, Any]:
    """
    Primary-source verification against CMS NPPES National Provider Identifier Registry.
    Primary-source check requirements:
    1. Looks the submitted 10-digit NPI up in the public NPPES NPI Registry API.
    2. Requires an authentic name match against the account holder.
    3. Fails closed (is_verified=False) on network timeout, HTTP error, empty results, or name mismatch.
    4. Never stores or persists the full registry payload (privacy & storage minimization).
    """
    reasons: list[str] = []
    clean_npi = (npi or "").strip()

    # 1. Structural Luhn format validation
    if not clean_npi or len(clean_npi) != 10 or not clean_npi.isdigit():
        return {
            "is_verified": False,
            "registry_reference": None,
            "matched_name": None,
            "reasons": ["NPI must be a 10-digit numeric identifier."]
        }

    if not validate_npi_luhn(clean_npi):
        return {
            "is_verified": False,
            "registry_reference": None,
            "matched_name": None,
            "reasons": ["NPI failed CMS standard Luhn MOD-10 checksum validation."]
        }

    # 2. Query CMS NPPES API
    query_params = urllib.parse.urlencode({
        "number": clean_npi,
        "version": "2.1"
    })
    url = f"{NPPES_API_BASE}?{query_params}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "CarePolicyGuard-Credentialing/1.0",
                "Accept": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                logger.warning(f"NPPES API returned status {resp.status} for NPI {clean_npi}.")
                return {
                    "is_verified": False,
                    "registry_reference": None,
                    "matched_name": None,
                    "reasons": [f"CMS NPPES registry returned HTTP {resp.status}. Verification failed closed."]
                }
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning(f"Network failure reaching CMS NPPES registry: {e}. Verification fails closed.")
        return {
            "is_verified": False,
            "registry_reference": None,
            "matched_name": None,
            "reasons": [f"CMS NPPES Registry unreachable: {str(e)}. Primary source verification fails closed."]
        }

    result_count = payload.get("result_count", 0)
    results = payload.get("results", [])
    if result_count == 0 or not results:
        return {
            "is_verified": False,
            "registry_reference": None,
            "matched_name": None,
            "reasons": [f"NPI '{clean_npi}' was not found in CMS NPPES public provider registry."]
        }

    # 3. Provider Identity & Name Matching
    provider_record = results[0]
    basic_info = provider_record.get("basic", {})

    first_name = basic_info.get("first_name", "")
    last_name = basic_info.get("last_name", "")
    reg_full_name = f"{first_name} {last_name}".strip()

    # Match tokens
    account_tokens = clean_name_tokens(account_holder_name)
    registry_tokens = clean_name_tokens(reg_full_name)

    # Check last name match
    clean_last = last_name.lower().strip()
    clean_first = first_name.lower().strip()

    has_last_name_match = any(clean_last in t or t in clean_last for t in account_tokens) if clean_last else False
    has_first_name_match = any(clean_first in t or t in clean_first for t in account_tokens) if clean_first else False

    # Also check token intersection
    intersection = account_tokens.intersection(registry_tokens)

    # Requirement: Account name must match provider registered name
    if not (has_last_name_match or len(intersection) >= 1):
        reasons.append(
            f"Provider name mismatch: Account holder name '{account_holder_name}' does not match "
            f"NPPES registered provider name '{reg_full_name}'."
        )
        return {
            "is_verified": False,
            "registry_reference": f"NPPES-REGISTRY-{clean_npi}",
            "matched_name": reg_full_name,
            "reasons": reasons
        }

    # Success: Primary source verified
    return {
        "is_verified": True,
        "registry_reference": f"NPPES-REGISTRY-{clean_npi}",
        "matched_name": reg_full_name,
        "reasons": []
    }

