import os
import json
import httpx
import pytest
from pathlib import Path

# Import the module under test after we have the ability to monkey‑patch globals.
import integrations.qbo_mcp_server as qbo


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch, tmp_path):
    """Prepare a temporary .env file and monkey‑patch the module globals.

    Each test gets a fresh .env containing a dummy refresh token so we can verify
    that refresh token rotation is persisted correctly.
    """
    # Create a temporary .env file with the required keys.
    env_content = "\n".join(
        [
            "QUICKBOOKS_CLIENT_ID=dummy_id",
            "QUICKBOOKS_CLIENT_SECRET=dummy_secret",
            "QUICKBOOKS_REALM_ID=1234567890",
            "QUICKBOOKS_REFRESH_TOKEN=old_refresh_token",
        ]
    )
    fake_env = tmp_path / ".env"
    fake_env.write_text(env_content + "\n", encoding="utf-8")

    # Monkey‑patch the path that the module uses for the .env file.
    monkeypatch.setattr(qbo, "ENV_FILE", fake_env)
    # Monkey‑patch the credential globals that were read at import time.
    monkeypatch.setattr(qbo, "CLIENT_ID", "dummy_id")
    monkeypatch.setattr(qbo, "CLIENT_SECRET", "dummy_secret")
    monkeypatch.setattr(qbo, "REALM_ID", "1234567890")
    monkeypatch.setattr(qbo, "REFRESH_TOKEN", "old_refresh_token")
    # Ensure the module sees the refreshed token variable when it is updated.
    # (refresh_access_token updates the global REFRESH_TOKEN in the module.)
    yield


def _mock_response(status_code: int = 200, json_data: dict = None, method: str = "GET", url: str = "http://test.local"):
    """Utility to create an httpx.Response with a minimal ``Request`` attached.
    ``json_data`` may be ``None`` – the response will have an empty body.
    ``method`` and ``url`` are used only to construct a dummy request so that
    ``Response.raise_for_status()`` works without raising ``RuntimeError``.
    """
    if json_data is None:
        json_data = {}
    request = httpx.Request(method, url)
    return httpx.Response(status_code, json=json_data, request=request)


def test_refresh_access_token_success_and_env_update(monkeypatch, tmp_path):
    """A successful token refresh should return the new access token and
    persist a rotated refresh token to the temporary ``.env`` file.
    """
    # Mock the POST request to return a new access token and a *different* refresh token.
    token_payload = {"access_token": "new_access_token", "refresh_token": "new_refresh_token"}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))

    access_token = qbo.refresh_access_token()
    assert access_token == "new_access_token"

    # The module should have updated the global REFRESH_TOKEN as well.
    assert qbo.REFRESH_TOKEN == "new_refresh_token"

    # Verify that the temporary .env file now contains the rotated token.
    env_text = qbo.ENV_FILE.read_text(encoding="utf-8")
    assert "QUICKBOOKS_REFRESH_TOKEN=new_refresh_token" in env_text


def test_refresh_access_token_no_rotation(monkeypatch, tmp_path):
    """If the refresh token returned by the endpoint is identical to the existing
    one, the ``.env`` file must remain unchanged.
    """
    token_payload = {"access_token": "same_access", "refresh_token": "old_refresh_token"}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))

    # Capture the original .env contents.
    original_env = qbo.ENV_FILE.read_text(encoding="utf-8")

    access_token = qbo.refresh_access_token()
    assert access_token == "same_access"
    # Global REFRESH_TOKEN should stay the same.
    assert qbo.REFRESH_TOKEN == "old_refresh_token"
    # File should be unchanged.
    assert qbo.ENV_FILE.read_text(encoding="utf-8") == original_env


def test_refresh_access_token_http_error(monkeypatch):
    """HTTP errors from the token endpoint should propagate as ``httpx.HTTPStatusError``.
    """
    # Return a 401 response – ``raise_for_status`` will raise the proper exception.
    error_response = _mock_response(401, {"error": "invalid_grant"})
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: error_response)

    with pytest.raises(httpx.HTTPStatusError):
        qbo.refresh_access_token()


def test_get_company_info_success(monkeypatch):
    """A successful call should return a dictionary with company details.
    The function internally calls ``refresh_access_token`` – we mock the token
    endpoint and the company‑info request.
    """
    # Mock token refresh first.
    token_payload = {"access_token": "company_access", "refresh_token": "new_refresh"}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))

    # Mock the GET request for company info.
    company_payload = {
        "CompanyInfo": {
            "CompanyName": "Acme Corp",
            "Country": "US",
            "CurrencyRef": {"value": "USD"},
        }
    }
    monkeypatch.setattr(qbo.httpx, "get", lambda *a, **kw: _mock_response(200, company_payload))

    info = qbo.get_company_info()
    expected = {
        "company_name": "Acme Corp",
        "country": "US",
        "currency": "USD",
        "environment": "sandbox",
        "status": "connected",
    }
    assert info == expected


def test_get_company_info_http_error(monkeypatch):
    """If the company‑info endpoint returns an error, the exception should bubble up.
    """
    # Mock token refresh to succeed.
    token_payload = {"access_token": "ok_access", "refresh_token": "new_refresh"}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))
    # Mock GET to return a 403 error.
    error_response = _mock_response(403, {"Fault": {"Error": [{"Message": "Forbidden"}]}})
    monkeypatch.setattr(qbo.httpx, "get", lambda *a, **kw: error_response)

    with pytest.raises(httpx.HTTPStatusError):
        qbo.get_company_info()
