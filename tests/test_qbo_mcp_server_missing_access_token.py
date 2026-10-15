import pytest
import httpx
import integrations.qbo_mcp_server as qbo

def _mock_response(status_code: int = 200, json_data: dict = None, method: str = "GET", url: str = "http://test.local"):
    if json_data is None:
        json_data = {}
    request = httpx.Request(method, url)
    return httpx.Response(status_code, json=json_data, request=request)

def test_refresh_access_token_missing_access_token(monkeypatch, tmp_path):
    """If response lacks access_token field, function should raise RuntimeError and not persist refresh token."""
    token_payload = {"refresh_token": "real_new_refresh_token"}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))
    original_token = qbo.REFRESH_TOKEN
    original_env = qbo.ENV_FILE.read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="Intuit's response did not contain an access token"):
        qbo.refresh_access_token()
    # Ensure no changes persisted
    assert qbo.REFRESH_TOKEN == original_token
    assert qbo.ENV_FILE.read_text(encoding="utf-8") == original_env
