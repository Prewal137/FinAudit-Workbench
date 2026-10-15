import os

import json

import httpx

import pytest

from pathlib import Path



# Import the module under test after we have the ability to monkey‑patch globals.

import integrations.qbo_mcp_server as qbo





@pytest.fixture(autouse=True)

def _clear_env(monkeypatch, tmp_path):
    # Ensure the MCP server writes reports into the temporary directory used by the test.
    # This prevents pollution of the real repository reports folder.
    monkeypatch.setattr(qbo, "PROJECT_ROOT", tmp_path)

    """Prepare a temporary .env file and monkey‑patch globals.



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





def _mock_response(status_code: int = 200, json_data: dict = None, method: str = "GET", url: str = "http\://test.local"):

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

    token_payload = {"access_token": "new_access_token", "refresh_token": "real_new_refresh_token"}

    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))



    access_token = qbo.refresh_access_token()

    assert access_token == "new_access_token"



    # The module should have updated the global REFRESH_TOKEN as well.

    assert qbo.REFRESH_TOKEN == "real_new_refresh_token"



    # Verify that the temporary .env file now contains the rotated token.

    env_text = qbo.ENV_FILE.read_text(encoding="utf-8")

    assert "QUICKBOOKS_REFRESH_TOKEN=real_new_refresh_token" in env_text





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

    # Verify timestamp and compare remaining fields
    assert "retrieved_at" in info
    expected_with_ts = expected.copy()
    expected_with_ts["retrieved_at"] = info["retrieved_at"]
    assert info == expected_with_ts





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





def test_get_profit_and_loss_success(monkeypatch):

    """A successful ProfitAndLoss report request returns the expected structured data.

    This test covers the legacy flat‑key response format.

    """

    # Mock token refresh.

    token_payload = {"access_token": "pl_access", "refresh_token": "new_refresh"}

    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))



    # Mock GET response for the ProfitAndLoss report.

    report_payload = {

        "Report": {

            "Header": {

                "StartDate": "2023-01-01",

                "EndDate": "2023-12-31",

                "CurrencyRef": {"value": "USD"},

            },

            "TotalRevenue": {"value": "1000"},

            "GrossProfit": {"value": "600"},

            "OperatingExpenses": {"value": "300"},

            "NetIncome": {"value": "300"},

        }

    }

    monkeypatch.setattr(qbo.httpx, "get", lambda *a, **kw: _mock_response(200, report_payload))



    info = qbo.get_profit_and_loss("2023-01-01", "2023-12-31")

    expected = {

        "period": {"start_date": "2023-01-01", "end_date": "2023-12-31"},

        "currency": "USD",

        "report": {

            "total_revenue": "1000",
            "cost_of_goods_sold": None,

            "gross_profit": "600",

            "operating_expenses": "300",
            "net_operating_income": None,
            "total_other_expenses": None,

            "net_income": "300",

        },

        "metric_status": {

            "total_revenue": "available",
            "cost_of_goods_sold": "unavailable",

            "gross_profit": "available",

            "operating_expenses": "available",
            "net_operating_income": "unavailable",
            "total_other_expenses": "unavailable",

            "net_income": "available",

        },

        "no_report_data": False,

    }

    # Verify timestamp and compare remaining fields
    assert "retrieved_at" in info
    expected_with_ts = expected.copy()
    expected_with_ts["retrieved_at"] = info["retrieved_at"]
    assert info == expected_with_ts





def test_get_profit_and_loss_http_error(monkeypatch):

    """If the ProfitAndLoss endpoint returns an error, the exception propagates.

    """

    token_payload = {"access_token": "pl_access_err", "refresh_token": "new_refresh"}

    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))

    error_response = _mock_response(403, {"Fault": {"Error": [{"Message": "Forbidden"}]}})

    monkeypatch.setattr(qbo.httpx, "get", lambda *a, **kw: error_response)

    with pytest.raises(httpx.HTTPStatusError):

        qbo.get_profit_and_loss("2023-01-01", "2023-12-31")





def test_get_profit_and_loss_missing_currency(monkeypatch):

    """When the API response lacks a CurrencyRef, the result omits the currency field.

    """

    token_payload = {"access_token": "pl_no_currency", "refresh_token": "new_refresh"}

    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))

    report_payload = {

        "Report": {

            "Header": {

                "StartDate": "2023-01-01",

                "EndDate": "2023-12-31",

                # No CurrencyRef key

            },

            "TotalRevenue": {"value": "2000"},

            "GrossProfit": {"value": "1200"},

            "OperatingExpenses": {"value": "500"},

            "NetIncome": {"value": "700"},

        }

    }

    monkeypatch.setattr(qbo.httpx, "get", lambda *a, **kw: _mock_response(200, report_payload))

    info = qbo.get_profit_and_loss("2023-01-01", "2023-12-31")

    # Currency should be omitted.

    assert "currency" not in info

    assert info["period"] == {"start_date": "2023-01-01", "end_date": "2023-12-31"}

    assert info["report"] == {

        "total_revenue": "2000",
            "cost_of_goods_sold": None,

        "gross_profit": "1200",

        "operating_expenses": "500",
            "net_operating_income": None,
            "total_other_expenses": None,

        "net_income": "700",

    }

    assert info["metric_status"] == {

        "total_revenue": "available",
            "cost_of_goods_sold": "unavailable",
            "cost_of_goods_sold": None,

        "gross_profit": "available",

        "operating_expenses": "available",
            "net_operating_income": "unavailable",
            "total_other_expenses": "unavailable",
            "net_operating_income": None,
            "total_other_expenses": None,

        "net_income": "available",

    }

    assert info["no_report_data"] is False



# ---------------------------------------------------------------------

# New tests covering the nested‑row format returned by the live QuickBooks sandbox.

# ---------------------------------------------------------------------



def test_get_profit_and_loss_nested_success(monkeypatch):

    """ProfitAndLoss reports with values nested inside ``Rows``/``ColData``

    should be correctly extracted.

    """

    token_payload = {"access_token": "nested_access", "refresh_token": "new_refresh"}

    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))



    nested_payload = {

        "Report": {

            "Header": {

                "StartDate": "2023-01-01",

                "EndDate": "2023-12-31",

                "Currency": "EUR",

            },

            "Rows": {

                "Row": [

                    {"Header": {"ColData": [{"value": "Income"}]}},

                    {

                        "Summary": {"ColData": [{"value": "Total Income"}]},

                        "ColData": [{"value": "Total Income"}, {"value": "2000"}],

                    },

                    {

                        "Summary": {"ColData": [{"value": "Gross Profit"}]},

                        "ColData": [{"value": "Gross Profit"}, {"value": "1200"}],

                    },

                    {

                        "Summary": {"ColData": [{"value": "Total Expenses"}]},

                        "ColData": [{"value": "Total Expenses"}, {"value": "500"}],

                    },

                    {

                        "Summary": {"ColData": [{"value": "Net Income"}]},

                        "ColData": [{"value": "Net Income"}, {"value": "700"}],

                    },

                ]

            },

        }

    }

    monkeypatch.setattr(qbo.httpx, "get", lambda *a, **kw: _mock_response(200, nested_payload))



    info = qbo.get_profit_and_loss("2023-01-01", "2023-12-31")

    expected = {

        "period": {"start_date": "2023-01-01", "end_date": "2023-12-31"},

        "currency": "EUR",

        "report": {

            "total_revenue": "2000",
            "cost_of_goods_sold": None,

            "gross_profit": "1200",

            "operating_expenses": "500",
            "net_operating_income": None,
            "total_other_expenses": None,

            "net_income": "700",

        },

        "metric_status": {

            "total_revenue": "available",
            "cost_of_goods_sold": "unavailable",

            "gross_profit": "available",

            "operating_expenses": "available",
            "net_operating_income": "unavailable",
            "total_other_expenses": "unavailable",

            "net_income": "available",

        },

        "no_report_data": False,

    }

    # Verify timestamp and compare remaining fields
    assert "retrieved_at" in info
    expected_with_ts = expected.copy()
    expected_with_ts["retrieved_at"] = info["retrieved_at"]
    assert info == expected_with_ts





def test_get_profit_and_loss_no_data(monkeypatch):

    """When QuickBooks indicates ``NoReportData`` the result should contain

    explicit ``null`` values for all metrics and flag the condition.

    """

    token_payload = {"access_token": "nodata_access", "refresh_token": "new_refresh"}

    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))



    nodata_payload = {

        "Header": {

            "Time": "2026-10-12T09:03:42-07:00",

            "ReportName": "ProfitAndLoss",

            "ReportBasis": "Accrual",

            "StartPeriod": "2026-01-01",

            "EndPeriod": "2026-01-31",

            "SummarizeColumnsBy": "Total",

            "Currency": "USD",

            "Option": [{"Name": "AccountingStandard", "Value": "GAAP"}, {"Name": "NoReportData", "Value": "true"}],

        },

        "Columns": {"Column": [{"ColTitle": "", "ColType": "Account", "MetaData": [{"Name": "ColKey", "Value": "account"}]}]},

        "Rows": {

            "Row": [

                {"Header": {"ColData": [{"value": "Income"}]}, "Summary": {"ColData": [{"value": "Total Income"}]}, "type": "Section", "group": "Income"},

                {"Summary": {"ColData": [{"value": "Gross Profit"}]}, "type": "Section", "group": "GrossProfit"},

                {"Header": {"ColData": [{"value": "Expenses"}]}, "Summary": {"ColData": [{"value": "Total Expenses"}]}, "type": "Section", "group": "Expenses"},

                {"Summary": {"ColData": [{"value": "Net Operating Income"}]}, "type": "Section", "group": "NetOperatingIncome"},

                {"Summary": {"ColData": [{"value": "Net Income"}]}, "type": "Section", "group": "NetIncome"},

            ]

        },

    }

    monkeypatch.setattr(qbo.httpx, "get", lambda *a, **kw: _mock_response(200, nodata_payload))



    info = qbo.get_profit_and_loss("2026-01-01", "2026-01-31")

    expected_report = {

        "total_revenue": None,
            "cost_of_goods_sold": None,

        "gross_profit": None,

        "operating_expenses": None,
            "net_operating_income": None,
            "total_other_expenses": None,

        "net_income": None,

    }

    assert info["period"] == {"start_date": "2026-01-01", "end_date": "2026-01-31"}

    assert info.get("currency") == "USD"

    assert info["report"] == expected_report

    assert info["metric_status"] == {

        "total_revenue": "unavailable",
            "cost_of_goods_sold": None,

        "gross_profit": "unavailable",

        "operating_expenses": "unavailable",
            "net_operating_income": None,
            "total_other_expenses": None,

        "net_income": "unavailable",

    }

    assert info["no_report_data"] is True

    # Report name and basis should be present when supplied.

    assert info.get("report_name") == "ProfitAndLoss"

    assert info.get("report_basis") == "Accrual"





def test_get_profit_and_loss_missing_metric(monkeypatch):

    """If a particular metric (e.g. Gross Profit) is absent from the rows, the

    corresponding result field should be ``null`` and marked unavailable.

    """

    token_payload = {"access_token": "partial_access", "refresh_token": "new_refresh"}

    monkeypatch.setattr(qbo.httpx, "post", lambda *a, **kw: _mock_response(200, token_payload))



    partial_payload = {

        "Report": {

            "Header": {

                "StartDate": "2023-01-01",

                "EndDate": "2023-12-31",

                "Currency": "GBP",

            },

            "Rows": {

                "Row": [

                    {

                        "Summary": {"ColData": [{"value": "Total Income"}]},

                        "ColData": [{"value": "Total Income"}, {"value": "1500"}],

                    },

                    # Gross Profit row deliberately omitted.

                    {

                        "Summary": {"ColData": [{"value": "Total Expenses"}]},

                        "ColData": [{"value": "Total Expenses"}, {"value": "800"}],

                    },

                    {

                        "Summary": {"ColData": [{"value": "Net Income"}]},

                        "ColData": [{"value": "Net Income"}, {"value": "700"}],

                    },

                ]

            },

        }

    }

    monkeypatch.setattr(qbo.httpx, "get", lambda *a, **kw: _mock_response(200, partial_payload))



    info = qbo.get_profit_and_loss("2023-01-01", "2023-12-31")

    expected = {

        "period": {"start_date": "2023-01-01", "end_date": "2023-12-31"},

        "currency": "GBP",

        "report": {

            "total_revenue": "1500",
            "cost_of_goods_sold": None,

            "gross_profit": None,  # Missing metric.

            "operating_expenses": "800",
            "net_operating_income": None,
            "total_other_expenses": None,

            "net_income": "700",

        },

        "metric_status": {

            "total_revenue": "available",
            "cost_of_goods_sold": "unavailable",

            "gross_profit": "unavailable",

            "operating_expenses": "available",
            "net_operating_income": "unavailable",
            "total_other_expenses": "unavailable",

            "net_income": "available",

        },

        "no_report_data": False,

    }

    # Verify timestamp and compare remaining fields
    assert "retrieved_at" in info
    expected_with_ts = expected.copy()
    expected_with_ts["retrieved_at"] = info["retrieved_at"]
    assert info == expected_with_ts


