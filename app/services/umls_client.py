"""
UMLS / UTS REST API Client Service.

Provides terminology resolution (term -> CUI) and semantic equivalence verification
against the National Library of Medicine (NLM) Unified Medical Language System (UMLS)
Unified Terminology Services (UTS) REST API.

STRICT GOVERNANCE, PRIVACY, & LICENSING BOUNDARIES:
- NO NOTE EGRESS: Only individual medical terms (e.g. "prostate adenocarcinoma")
  are sent to the UTS REST API. Never a clinical note, never a note sentence,
  and never a patient narrative. Any multi-sentence or narrative input is
  strictly rejected prior to network egress.
- CREDENTIAL SAFETY: UMLS_API_KEY is read exclusively from the environment.
  It is never hardcoded, never logged, and never persisted to repository files.
- FAIL CLOSED: If UMLS_API_KEY is missing, empty, or unconfigured, the client
  fails closed gracefully by reporting unavailable and falling back to the
  committed concept map and clinical judge paths.
- METATHESAURUS CONTENT RESTRICTION: In adherence to the NLM UMLS Metathesaurus
  license agreement, no proprietary definitions, atom hierarchies, or concept trees
  are bundled, shipped, or cached. The local cache persists ONLY normalized term
  strings and their returned Concept Unique Identifiers (CUIs).
- VERSION PINNING: Pinned to release 2024AB (not "current") for auditable, reproducible
  clinical terminology evaluation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx

from app.core.config import settings

logger = logging.getLogger("carepolicyguard.umls_client")

# Pinned release version for reproducible mapping
UMLS_PINNED_VERSION: str = "2024AB"
UTS_BASE_URL: str = "https://uts-ws.nlm.nih.gov/rest"
DEFAULT_CACHE_PATH: Path = Path("app/data/umls_cui_cache.json")

# Term validation constants to enforce hard egress boundary:
# Rejects newlines/tabs, sentence punctuation followed by whitespace, or trailing sentence punctuation
MAX_TERM_LENGTH: int = 100
_SENTENCE_DELIMITERS = re.compile(r"[\n\r]|(?:\.\s+)|(?:\?\s+)|(?:\!\s+)|(?:\;\s+)|(?:[\.\?\!\;]$)")


class UMLSClient:
    """
    Client for NLM Unified Terminology Services (UTS) REST API.
    Provides term-to-CUI search and CUI-based clinical concept equivalence checks.
    """

    def __init__(
        self,
        api_key: str | None = None,
        version: str = UMLS_PINNED_VERSION,
        base_url: str = UTS_BASE_URL,
        timeout: float = 5.0,
        cache_path: Path | str | None = DEFAULT_CACHE_PATH,
        http_client: httpx.Client | None = None,
    ):
        # Read API key strictly from settings / environment; never hardcoded
        self.api_key: str = (
            api_key
            if api_key is not None
            else getattr(settings, "UMLS_API_KEY", os.getenv("UMLS_API_KEY", ""))
        ).strip()
        self.version: str = version
        self.base_url: str = base_url.rstrip("/")
        self.timeout: float = timeout
        self.cache_path: Path | None = Path(cache_path) if cache_path else None

        self._client: httpx.Client | None = http_client
        self._owns_client: bool = http_client is None

        # In-memory CUI cache: normalized_term -> Optional[CUI]
        self._memory_cache: dict[str, str | None] = {}
        self.telemetry: dict[str, int] = {
            "api_calls": 0,
            "cache_hits": 0,
            "lookups_attempted": 0,
            "lookups_resolved": 0,
            "equivalence_checks_evaluated": 0,
            "equivalence_confirmed_by_cui": 0,
        }

        self._load_cache()

    @property
    def is_configured(self) -> bool:
        """Returns True if a non-empty API key is available in the environment."""
        return bool(self.api_key)

    def _get_http_client(self) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=self.timeout)
            self._owns_client = True
        return self._client

    def close(self) -> None:
        """Closes the underlying HTTP client and persists cache to disk."""
        self._persist_cache()
        if self._owns_client and self._client and not self._client.is_closed:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def _load_cache(self) -> None:
        """Loads cached term->CUI mappings from local JSON cache if present."""
        if not self.cache_path or not self.cache_path.exists():
            return
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cached_version = data.get("version")
            if cached_version == self.version and "mappings" in data:
                self._memory_cache.update(data["mappings"])
                logger.debug(
                    f"Loaded {len(data['mappings'])} UMLS term mappings from local cache ({self.version})."
                )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.debug(f"Could not load local UMLS cache from {self.cache_path}: {exc}")

    def _persist_cache(self) -> None:
        """Persists in-memory term->CUI mappings to local JSON cache."""
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": self.version,
                "mappings": self._memory_cache,
            }
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
        except (OSError, TypeError, ValueError) as exc:
            logger.debug(f"Could not persist UMLS cache to {self.cache_path}: {exc}")

    def validate_term_egress_boundary(self, term: str) -> bool:
        """
        Enforces HIPAA and NLM safety boundaries:
        - Only individual medical terms are allowed.
        - Clinical progress notes, sentences, or multi-clause narratives are REJECTED.
        """
        if not term:
            return False
        clean = term.strip()
        if len(clean) > MAX_TERM_LENGTH:
            logger.warning(
                f"UMLS egress boundary violation: term exceeds max length ({len(clean)} > {MAX_TERM_LENGTH}). Query rejected."
            )
            return False
        if _SENTENCE_DELIMITERS.search(clean):
            logger.warning(
                "UMLS egress boundary violation: query contains sentence delimiters or linebreaks. Query rejected."
            )
            return False
        return True

    def get_cui(self, term: str) -> str | None:
        """
        Retrieves the Concept Unique Identifier (CUI) for a clinical term.
        Fails closed (returns None) if API key is unconfigured, term is invalid,
        or network error occurs.
        """
        self.telemetry["lookups_attempted"] += 1

        if not term:
            return None

        norm_term = term.strip().lower()

        # Hard boundary validation: reject patient notes or sentence fragments
        if not self.validate_term_egress_boundary(norm_term):
            return None

        # Check in-memory cache first
        if norm_term in self._memory_cache:
            self.telemetry["cache_hits"] += 1
            cached_cui = self._memory_cache[norm_term]
            if cached_cui:
                self.telemetry["lookups_resolved"] += 1
            return cached_cui

        # Fail closed immediately if no API key is configured
        if not self.is_configured:
            logger.debug("UMLS lookup skipped: UMLS_API_KEY is not configured in environment.")
            return None

        # Call UTS REST API search endpoint
        # HARD BOUNDARY: ONLY the normalized individual medical term is passed as the query string
        endpoint = f"{self.base_url}/search/{self.version}"
        params = {
            "string": norm_term,
            "searchType": "exact",
            "apiKey": self.api_key,
        }

        try:
            client = self._get_http_client()
            resp = client.get(endpoint, params=params)
            self.telemetry["api_calls"] += 1

            if resp.status_code == 200:
                data = resp.json()
                cui = self._extract_cui_from_response(data)
                self._memory_cache[norm_term] = cui
                if cui:
                    self.telemetry["lookups_resolved"] += 1
                    logger.debug(f"UMLS resolved '{norm_term}' -> CUI {cui}")
                else:
                    logger.debug(f"UMLS returned 0 exact matches for '{norm_term}'")
                return cui
            elif resp.status_code == 404:
                # Term not found in UMLS Metathesaurus
                self._memory_cache[norm_term] = None
                return None
            else:
                logger.debug(f"UTS search API returned HTTP {resp.status_code} for '{norm_term}'")
                return None

        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError, OSError, ValueError) as exc:
            logger.debug(f"UTS API lookup failed gracefully for '{norm_term}': {exc}")
            return None

    @staticmethod
    def _extract_cui_from_response(data: dict[str, Any]) -> str | None:
        """Extracts the first valid CUI from the UTS searchResults JSON structure."""
        # UTS search structure: {"result": {"results": [{"ui": "C0011860", "name": ...}]}}
        res_container = data.get("result", {})
        if isinstance(res_container, dict):
            items = res_container.get("results", [])
        elif isinstance(res_container, list):
            items = res_container
        else:
            items = data.get("searchResults", {}).get("results", data.get("results", []))

        if not items or not isinstance(items, list):
            return None

        first = items[0]
        if isinstance(first, dict):
            ui = first.get("ui")
            if ui and isinstance(ui, str) and ui.startswith("C"):
                return ui
        return None

    def are_equivalent(self, term_a: str, term_b: str) -> tuple[bool, str | None]:
        """
        Determines if two medical terms share the same UMLS Concept Unique Identifier (CUI).
        Returns:
            (True, cui) if both terms map authoritatively to the identical CUI.
            (False, None) if CUIs differ, either term is unmapped, or lookup fails.
        """
        self.telemetry["equivalence_checks_evaluated"] += 1

        norm_a = term_a.strip().lower()
        norm_b = term_b.strip().lower()

        if not norm_a or not norm_b:
            return False, None

        # Direct lexical identity fast-path
        if norm_a == norm_b:
            cui = self.get_cui(norm_a)
            if cui:
                self.telemetry["equivalence_confirmed_by_cui"] += 1
            return True, cui

        cui_a = self.get_cui(norm_a)
        if not cui_a:
            return False, None

        cui_b = self.get_cui(norm_b)
        if not cui_b:
            return False, None

        if cui_a == cui_b:
            self.telemetry["equivalence_confirmed_by_cui"] += 1
            logger.debug(f"UMLS equivalence confirmed: '{term_a}' == '{term_b}' via CUI {cui_a}")
            return True, cui_a

        return False, None


# Process-wide singleton instance
_GLOBAL_UMLS_CLIENT: UMLSClient | None = None


def get_umls_client() -> UMLSClient:
    """Returns the process-wide UMLSClient singleton."""
    global _GLOBAL_UMLS_CLIENT
    if _GLOBAL_UMLS_CLIENT is None:
        _GLOBAL_UMLS_CLIENT = UMLSClient()
    return _GLOBAL_UMLS_CLIENT
