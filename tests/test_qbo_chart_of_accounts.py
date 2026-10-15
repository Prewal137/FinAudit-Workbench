import pytest

import integrations.qbo_mcp_server as qbo


def _mock_response(status_code: int = 200, json_data: dict = None, method: str = "GET", url: str = "http://test.local"):
    """Utility to create an httpx.Response with a minimal ``Request`` attached.

    ``json_data`` may be ``None`` – the response will have an empty body.
    """
    if json_data is None:
        json_data = {}
    request = qbo.httpx.Request(method, url)
    return qbo.httpx.Response(status_code, json=json_data, request=request)


def test_list_chart_of_accounts_success(monkeypatch):
    """Simulate a successful single‑page response.

    The function should return the accounts present in the response.
    """
    # Mock token refresh to avoid real network calls.
    token_payload = {"access_token": "dummy_access", "refresh_token": "new_refresh"}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))

    response_data = {
        "QueryResponse": {
            "Account": [
                {"Id": "1", "Name": "Cash", "AccountType": "Bank", "AccountSubType": "Checking"},
                {"Id": "2", "Name": "Accounts Receivable", "AccountType": "AccountsReceivable"},
                {"Id": "3", "Name": "Revenue", "AccountType": "Income"},
            ],
            "startPosition": 1,
            "maxResults": 3,
        }
    }

    # Track the request parameters to confirm pagination logic is exercised.
    calls = []
    def _mock_get(*args, **kwargs):
        calls.append(kwargs.get("params", {}))
        return _mock_response(200, response_data)

    monkeypatch.setattr(qbo.httpx, "get", _mock_get)

    accounts = qbo.list_chart_of_accounts()

    assert isinstance(accounts, list)
    assert len(accounts) == 3
    ids = {acct["id"] for acct in accounts}
    assert ids == {"1", "2", "3"}
    # Verify the query includes startposition 1 (case‑insensitive)
    query_param = calls[0].get("query", "").lower()
    assert "startposition 1" in query_param



def test_list_chart_of_accounts_empty(monkeypatch):
    """When QuickBooks returns no accounts, the function should return an empty list."""
    # Mock token refresh to avoid real network calls.
    token_payload = {"access_token": "dummy_access", "refresh_token": "new_refresh"}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))

    empty_response = {"QueryResponse": {"Account": []}}
    monkeypatch.setattr(qbo.httpx, "get", lambda *a, **kw: _mock_response(200, empty_response))
    accounts = qbo.list_chart_of_accounts()
    assert accounts == []




def test_list_chart_of_accounts_http_error(monkeypatch):
    """HTTP errors should propagate as ``httpx.HTTPStatusError``."""
    error_response = _mock_response(401, {"Fault": {"Error": [{"Message": "Unauthorized"}]}})
    monkeypatch.setattr(qbo.httpx, "get", lambda *a, **kw: error_response)
    with pytest.raises(qbo.httpx.HTTPStatusError):
        qbo.list_chart_of_accounts()


def test_list_chart_of_accounts_multi_page(monkeypatch):
    """Simulate a two‑page response and verify pagination works correctly.

    QuickBooks returns a ``maxResults`` larger than the hard‑coded ``max_results`` (1000).
    The function should make a second request with ``startposition`` = 1001 and
    combine the results.
    """
    # Mock token refresh.
    token_payload = {"access_token": "dummy_access", "refresh_token": "new_refresh"}
    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))

    # First page: two accounts, maxResults = 1000, startPosition = 1.
    page1 = {
        "QueryResponse": {
            "Account": [
                {"Id": "1", "Name": "Cash", "AccountType": "Bank", "AccountSubType": "Checking"},
                {"Id": "2", "Name": "Accounts Receivable", "AccountType": "AccountsReceivable"},
            ],
            "startPosition": 1,
            "maxResults": 1000,
        }
    }
    # Second page: one additional account, no maxResults field – loop will stop after this page.
    page2 = {
        "QueryResponse": {
            "Account": [
                {"Id": "3", "Name": "Revenue", "AccountType": "Income"},
            ],
            "startPosition": 1001,
        }
    }

    calls = []
    def _mock_get(*args, **kwargs):
        params = kwargs.get("params", {})
        calls.append(params)
        query = params.get("query", "").lower()
        if "startposition 1001" in query:
            return _mock_response(200, page2)
        elif "startposition 1" in query:
            return _mock_response(200, page1)
        else:
            return _mock_response(200, {"QueryResponse": {"Account": []}})

    monkeypatch.setattr(qbo.httpx, "get", _mock_get)

    accounts = qbo.list_chart_of_accounts()

    # Verify we received all three accounts.
    assert isinstance(accounts, list)
    assert len(accounts) == 3
    ids = {a["id"] for a in accounts}
    assert ids == {"1", "2", "3"}

    # Verify pagination parameters (query strings contain the expected startpositions).
    query_params = [c.get("query", "").lower() for c in calls]
    assert any("startposition 1" in qp for qp in query_params)
    assert any("startposition 1001" in qp for qp in query_params)


