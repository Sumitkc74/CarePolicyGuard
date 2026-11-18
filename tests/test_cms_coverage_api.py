"""
Unit tests for the official CMS Coverage API client (app.services.cms_coverage_api).
"""

from unittest.mock import MagicMock

import httpx
import pytest

from app.services.cms_coverage_api import CMSCoverageApiClient, CMSCoverageAPIError


@pytest.fixture
def mock_httpx_client():
    client = MagicMock(spec=httpx.Client)
    return client


def test_cms_coverage_api_token_fetch(mock_httpx_client):
    """Verifies runtime license token acquisition from /v1/metadata/license-agreement."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "meta": {"status": "success"},
        "data": [{"Token": "mock-token-abc-123"}]
    }
    mock_httpx_client.get.return_value = mock_response

    api = CMSCoverageApiClient(http_client=mock_httpx_client)
    token = api.get_license_token()

    assert token == "mock-token-abc-123"
    mock_httpx_client.get.assert_called_once_with(
        "https://api.coverage.cms.gov/v1/metadata/license-agreement"
    )

    # Subsequent call within window must return cached token without HTTP GET
    token2 = api.get_license_token()
    assert token2 == "mock-token-abc-123"
    assert mock_httpx_client.get.call_count == 1


def test_cms_coverage_api_token_forced_refresh(mock_httpx_client):
    """Verifies that force_refresh bypasses cache and gets a new token."""
    mock_response1 = MagicMock(spec=httpx.Response)
    mock_response1.json.return_value = {"data": [{"Token": "token-1"}]}
    mock_response2 = MagicMock(spec=httpx.Response)
    mock_response2.json.return_value = {"data": [{"Token": "token-2"}]}

    mock_httpx_client.get.side_effect = [mock_response1, mock_response2]

    api = CMSCoverageApiClient(http_client=mock_httpx_client)
    assert api.get_license_token() == "token-1"
    assert api.get_license_token(force_refresh=True) == "token-2"
    assert mock_httpx_client.get.call_count == 2


def test_cms_coverage_api_auth_headers(mock_httpx_client):
    """Verifies proper Bearer token attachment in headers."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.json.return_value = {"data": [{"Token": "valid-bearer-token"}]}
    mock_httpx_client.get.return_value = mock_response

    api = CMSCoverageApiClient(http_client=mock_httpx_client)
    headers = api.get_auth_headers()
    assert headers["Authorization"] == "Bearer valid-bearer-token"
    assert headers["Accept"] == "application/json"


def test_cms_coverage_api_fetch_ncd(mock_httpx_client):
    """Verifies NCD document fetch with document_id parameter."""
    token_resp = MagicMock(spec=httpx.Response)
    token_resp.json.return_value = {"data": [{"Token": "tok"}]}

    ncd_resp = MagicMock(spec=httpx.Response)
    ncd_resp.json.return_value = {
        "meta": {"status": "ok"},
        "data": [{
            "document_id": 110,
            "document_display_id": "20.4",
            "title": "Implantable Cardioverter Defibrillators (ICDs)",
            "indications_limitations": "Patients with prior MI and LVEF <= 35%"
        }]
    }

    mock_httpx_client.get.side_effect = [token_resp, ncd_resp]

    api = CMSCoverageApiClient(http_client=mock_httpx_client)
    doc = api.fetch_ncd_document(110)

    assert doc["document_id"] == 110
    assert doc["document_display_id"] == "20.4"
    assert "ICDs" in doc["title"]


def test_cms_coverage_api_fetch_lcd(mock_httpx_client):
    """Verifies LCD document fetch with lcdid parameter."""
    token_resp = MagicMock(spec=httpx.Response)
    token_resp.json.return_value = {"data": [{"Token": "tok"}]}

    lcd_resp = MagicMock(spec=httpx.Response)
    lcd_resp.json.return_value = {
        "meta": {"status": "ok"},
        "data": [{
            "lcd_id": 36575,
            "display_id": "L36575",
            "title": "Total Knee Arthroplasty",
            "indication": "Coverage indications for end-stage osteoarthritis"
        }]
    }

    mock_httpx_client.get.side_effect = [token_resp, lcd_resp]

    api = CMSCoverageApiClient(http_client=mock_httpx_client)
    doc = api.fetch_lcd_document(36575)

    assert doc["lcd_id"] == 36575
    assert doc["display_id"] == "L36575"
    assert doc["title"] == "Total Knee Arthroplasty"


def test_cms_coverage_api_search_ncd(mock_httpx_client):
    """Verifies NCD catalog search by display code and title."""
    token_resp = MagicMock(spec=httpx.Response)
    token_resp.json.return_value = {"data": [{"Token": "tok"}]}

    catalog_resp = MagicMock(spec=httpx.Response)
    catalog_resp.json.return_value = {
        "data": [
            {"document_id": 110, "document_display_id": "20.4", "title": "Implantable Cardioverter Defibrillators"},
            {"document_id": 12, "document_display_id": "20.29", "title": "Hyperbaric Oxygen Therapy"}
        ]
    }

    mock_httpx_client.get.side_effect = [token_resp, catalog_resp]

    api = CMSCoverageApiClient(http_client=mock_httpx_client)
    results = api.search_ncds(display_id="20.4")
    assert len(results) == 1
    assert results[0]["document_id"] == 110

    results2 = api.search_ncds(title_query="oxygen")
    assert len(results2) == 1
    assert results2[0]["document_id"] == 12


def test_cms_coverage_api_error_handling(mock_httpx_client):
    """Verifies proper exception raising on HTTP errors."""
    mock_httpx_client.get.side_effect = httpx.ConnectError("Connection refused")

    api = CMSCoverageApiClient(http_client=mock_httpx_client)
    with pytest.raises(CMSCoverageAPIError, match="Failed to acquire license agreement token"):
        api.get_license_token()
