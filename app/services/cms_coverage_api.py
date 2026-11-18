"""
CMS Coverage API Client (api.coverage.cms.gov).

Connects to the official Centers for Medicare & Medicaid Services (CMS)
Medicare Coverage Database (MCD) Coverage API to retrieve:
- License Agreement tokens (1-hour validity, fetched at runtime)
- National Coverage Determination (NCD) reports & documents
- Local Coverage Determination (LCD) reports & documents
- Coverage Articles and Medicare Coverage Documents

STRICT GOVERNANCE & SECURITY RULES:
- License tokens are acquired dynamically at runtime only.
- Never commit, hardcode, or log authentication tokens or secrets.
- Read-only queries against official CMS endpoints.
"""

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("carepolicyguard.cms_coverage_api")

CMS_API_BASE_URL = "https://api.coverage.cms.gov"
TOKEN_VALIDITY_SECONDS = 3000  # Token valid for 3600s (1 hr); refresh after 50 minutes (3000s)


class CMSCoverageAPIError(Exception):
    """Base exception for CMS Coverage API errors."""


class CMSCoverageApiClient:
    """
    Official CMS Coverage API client for Medicare Coverage Database (MCD).
    Handles dynamic token acquisition and document retrieval.
    """

    def __init__(
        self,
        base_url: str = CMS_API_BASE_URL,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = http_client or httpx.Client(timeout=timeout)
        self._owns_client = http_client is None
        self._token: str | None = None
        self._token_fetched_at: float = 0.0
        self._ncd_catalog_cache: list[dict[str, Any]] | None = None
        self._lcd_catalog_cache: list[dict[str, Any]] | None = None

    def close(self):
        """Closes the underlying HTTP client if owned."""
        if self._owns_client and self._client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_license_token(self, force_refresh: bool = False) -> str:
        """
        Retrieves or refreshes the CMS Coverage API license agreement token.
        Endpoint: GET /v1/metadata/license-agreement
        Response format: {"meta": {...}, "data": [{"Token": "<bearer_token>"}]}
        """
        now = time.time()
        if (
            not force_refresh
            and self._token
            and (now - self._token_fetched_at) < TOKEN_VALIDITY_SECONDS
        ):
            return self._token

        url = f"{self.base_url}/v1/metadata/license-agreement"
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            token_list = data.get("data", [])
            if not token_list or not isinstance(token_list, list) or "Token" not in token_list[0]:
                raise CMSCoverageAPIError(f"Unexpected license agreement response structure: {data}")

            self._token = token_list[0]["Token"]
            self._token_fetched_at = now
            logger.info("Successfully fetched new CMS Coverage API license agreement token.")
            return self._token
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch CMS Coverage API license token: {e}")
            raise CMSCoverageAPIError(f"Failed to acquire license agreement token: {e}") from e

    def get_auth_headers(self) -> dict[str, str]:
        """Returns standard authorization headers with Bearer token."""
        token = self.get_license_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

    def get_ncd_report(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """
        Fetches the complete national coverage determination (NCD) catalog.
        Endpoint: GET /v1/reports/national-coverage-ncd/
        """
        if self._ncd_catalog_cache and not force_refresh:
            return self._ncd_catalog_cache

        url = f"{self.base_url}/v1/reports/national-coverage-ncd/"
        headers = self.get_auth_headers()
        try:
            resp = self._client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            self._ncd_catalog_cache = data
            return data
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch NCD catalog report: {e}")
            raise CMSCoverageAPIError(f"Failed to fetch NCD catalog report: {e}") from e

    def get_lcd_report(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """
        Fetches the complete local coverage determination (LCD) final catalog.
        Endpoint: GET /v1/reports/local-coverage-final-lcds/
        """
        if self._lcd_catalog_cache and not force_refresh:
            return self._lcd_catalog_cache

        url = f"{self.base_url}/v1/reports/local-coverage-final-lcds/"
        headers = self.get_auth_headers()
        try:
            resp = self._client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            self._lcd_catalog_cache = data
            return data
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch LCD catalog report: {e}")
            raise CMSCoverageAPIError(f"Failed to fetch LCD catalog report: {e}") from e

    def search_ncds(
        self,
        display_id: str | None = None,
        title_query: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Searches NCDs by display code (e.g. '20.4') and/or title keywords.
        """
        catalog = self.get_ncd_report()
        results = []
        disp_clean = display_id.strip() if display_id else None
        title_clean = title_query.strip().lower() if title_query else None

        for item in catalog:
            item_disp = str(item.get("document_display_id", "")).strip()
            item_title = str(item.get("title", "")).lower()

            if disp_clean and item_disp == disp_clean:
                results.append(item)
                continue

            if title_clean and title_clean in item_title:
                results.append(item)

        return results

    def search_lcds(
        self,
        display_id: str | None = None,
        title_query: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Searches LCDs by display ID (e.g. 'L38284') and/or title keywords.
        """
        catalog = self.get_lcd_report()
        results = []
        disp_clean = display_id.strip().upper() if display_id else None
        title_clean = title_query.strip().lower() if title_query else None

        for item in catalog:
            item_disp = str(item.get("document_display_id", "")).strip().upper()
            item_title = str(item.get("title", "")).lower()

            if disp_clean and item_disp == disp_clean:
                results.append(item)
                continue

            if title_clean and title_clean in item_title:
                results.append(item)

        return results

    def fetch_ncd_document(self, ncdid: int) -> dict[str, Any]:
        """
        Fetches full NCD document text by document_id (ncdid).
        Endpoint: GET /v1/data/ncd?ncdid={ncdid}
        """
        url = f"{self.base_url}/v1/data/ncd"
        params = {"ncdid": ncdid}
        headers = self.get_auth_headers()
        try:
            resp = self._client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data or not isinstance(data, list):
                raise CMSCoverageAPIError(f"No NCD document returned for ncdid={ncdid}")
            return data[0]
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch NCD document {ncdid}: {e}")
            raise CMSCoverageAPIError(f"Failed to fetch NCD document {ncdid}: {e}") from e

    def fetch_lcd_document(self, lcdid: int) -> dict[str, Any]:
        """
        Fetches full LCD document text by document_id (lcdid).
        Endpoint: GET /v1/data/lcd?lcdid={lcdid}
        """
        url = f"{self.base_url}/v1/data/lcd"
        params = {"lcdid": lcdid}
        headers = self.get_auth_headers()
        try:
            resp = self._client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data or not isinstance(data, list):
                raise CMSCoverageAPIError(f"No LCD document returned for lcdid={lcdid}")
            return data[0]
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch LCD document {lcdid}: {e}")
            raise CMSCoverageAPIError(f"Failed to fetch LCD document {lcdid}: {e}") from e

    def fetch_article_document(self, articleid: int) -> dict[str, Any]:
        """
        Fetches full Article document text by articleid.
        Endpoint: GET /v1/data/article?articleid={articleid}
        """
        url = f"{self.base_url}/v1/data/article"
        params = {"articleid": articleid}
        headers = self.get_auth_headers()
        try:
            resp = self._client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data or not isinstance(data, list):
                raise CMSCoverageAPIError(f"No Article document returned for articleid={articleid}")
            return data[0]
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch Article document {articleid}: {e}")
            raise CMSCoverageAPIError(f"Failed to fetch Article document {articleid}: {e}") from e

    def fetch_medicare_coverage_document(self, mcdid: int) -> dict[str, Any]:
        """
        Fetches full Medicare Coverage Document by mcdid.
        Endpoint: GET /v1/data/medicare-coverage-document?mcdid={mcdid}
        """
        url = f"{self.base_url}/v1/data/medicare-coverage-document"
        params = {"mcdid": mcdid}
        headers = self.get_auth_headers()
        try:
            resp = self._client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data or not isinstance(data, list):
                raise CMSCoverageAPIError(f"No Medicare Coverage Document returned for mcdid={mcdid}")
            return data[0]
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch Medicare Coverage Document {mcdid}: {e}")
            raise CMSCoverageAPIError(f"Failed to fetch Medicare Coverage Document {mcdid}: {e}") from e
