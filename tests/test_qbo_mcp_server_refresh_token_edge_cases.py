import pytest
import httpx
import integrations.qbo_mcp_server as qbo

# Reuse the _mock_response helper from existing test module by importing it.
# Since we cannot import from that test directly, we replicate a minimal version here.

def _mock_response(status_code: int = 200, json_data: dict = None, method: str = "GET", url: str = "http://test.local"):
    if json_data is None:
        json_data = {}
    request = httpx.Request(method, url)
    return httpx.Response(status_code, json=json_data, request=request)

def test_refresh_access_token_placeholder_ignored(monkeypatch, tmp_path):
    """If the refresh token is the placeholder 'new_refresh', it should not be persisted."""
    token_payload = {"access_token": "new_access_token", "refresh_token": "new_refresh"}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))
    original_token = qbo.REFRESH_TOKEN
    original_env = qbo.ENV_FILE.read_text(encoding="utf-8")
    access_token = qbo.refresh_access_token()
    assert access_token == "new_access_token"
    assert qbo.REFRESH_TOKEN == original_token
    assert qbo.ENV_FILE.read_text(encoding="utf-8") == original_env

def test_refresh_access_token_missing_refresh_field(monkeypatch, tmp_path):
    """When the response lacks a refresh_token field, no rotation occurs."""
    token_payload = {"access_token": "new_access_token"}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))
    original_token = qbo.REFRESH_TOKEN
    original_env = qbo.ENV_FILE.read_text(encoding="utf-8")
    access_token = qbo.refresh_access_token()
    assert access_token == "new_access_token"
    assert qbo.REFRESH_TOKEN == original_token
    assert qbo.ENV_FILE.read_text(encoding="utf-8") == original_env

def test_refresh_access_token_empty_refresh_token(monkeypatch, tmp_path):
    """An empty string refresh token should be ignored and not persisted."""
    token_payload = {"access_token": "new_access_token", "refresh_token": ""}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))
    original_token = qbo.REFRESH_TOKEN
    original_env = qbo.ENV_FILE.read_text(encoding="utf-8")
    access_token = qbo.refresh_access_token()
    assert access_token == "new_access_token"
    assert qbo.REFRESH_TOKEN == original_token
    assert qbo.ENV_FILE.read_text(encoding="utf-8") == original_env

def test_refresh_access_token_missing_refresh_token_variable(monkeypatch, tmp_path):
    """If .env does not contain QUICKBOOKS_REFRESH_TOKEN, refresh should raise RuntimeError."""
    # Create a .env without the refresh token.
    env_content = "\n".join([
        "QUICKBOOKS_CLIENT_ID=dummy_id",
        "QUICKBOOKS_CLIENT_SECRET=dummy_secret",
        "QUICKBOOKS_REALM_ID=1234567890",
    ])
    fake_env = tmp_path / ".env"
    fake_env.write_text(env_content + "\n", encoding="utf-8")
    monkeypatch.setattr(qbo, "ENV_FILE", fake_env)
    monkeypatch.setattr(qbo, "REFRESH_TOKEN", None)
    token_payload = {"access_token": "new_access_token", "refresh_token": "some_token"}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))
    with pytest.raises(RuntimeError, match="Missing QUICKBOOKS_REFRESH_TOKEN"):
        qbo.refresh_access_token()

def test_refresh_access_token_concurrent_calls(monkeypatch, tmp_path):
    """Simulate two successive calls to verify lock acquisition and release each time.
    Uses a temporary .env file so writes stay isolated.
    """
    # Create a temporary .env file with required keys and an initial refresh token.
    env_content = "\n".join([
        "QUICKBOOKS_CLIENT_ID=dummy_id",
        "QUICKBOOKS_CLIENT_SECRET=dummy_secret",
        "QUICKBOOKS_REALM_ID=1234567890",
        "QUICKBOOKS_REFRESH_TOKEN=old_refresh_token",
    ])
    fake_env = tmp_path / ".env"
    fake_env.write_text(env_content + "\n", encoding="utf-8")
    # Monkey‑patch the module to use the temporary env and token.
    monkeypatch.setattr(qbo, "ENV_FILE", fake_env)
    monkeypatch.setattr(qbo, "REFRESH_TOKEN", "old_refresh_token")

    payloads = [
        {"access_token": "access1", "refresh_token": "token1"},
        {"access_token": "access2", "refresh_token": "token2"},
    ]
    def post_mock(*a, **kw):
        data = payloads.pop(0)
        return _mock_response(200, data)
    monkeypatch.setattr(qbo.httpx, "post", post_mock)
    lock_calls = []
    def acquire_mock(path):
        lock_calls.append(("acquire", path))
    def release_mock(path):
        lock_calls.append(("release", path))
    monkeypatch.setattr(qbo, "_acquire_manifest_lock", acquire_mock)
    monkeypatch.setattr(qbo, "_release_manifest_lock", release_mock)
    token1 = qbo.refresh_access_token()
    token2 = qbo.refresh_access_token()
    assert token1 == "access1"
    assert token2 == "access2"
    # Ensure the temporary .env was updated with the last token.
    env_text = qbo.ENV_FILE.read_text(encoding="utf-8")
    assert "QUICKBOOKS_REFRESH_TOKEN=token2" in env_text
    # Should have two acquires and two releases.
    acquires = [c for c in lock_calls if c[0] == "acquire"]
    releases = [c for c in lock_calls if c[0] == "release"]
    assert len(acquires) == 2
    assert len(releases) == 2
    expected_path = f"{qbo.ENV_FILE}.refresh.lock"
    for _, path in acquires + releases:
        assert path == expected_path
