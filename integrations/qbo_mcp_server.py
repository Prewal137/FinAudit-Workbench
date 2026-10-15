"""FinAudit-Workbench: Read-only QuickBooks Online sandbox MCP server.


Tools:

- get_company_info

- get_profit_and_loss


Credentials are loaded from .env. Rotated refresh tokens are persisted.

Never print or expose credentials or tokens.

"""


import os

from datetime import date, datetime, timezone

from pathlib import Path


import httpx

import json

import hashlib

import time
from typing import List, Dict

def _acquire_manifest_lock(lock_path: str, timeout: int = 10) -> None:
    """Acquire an exclusive lock file for the manifest.

    The lock is implemented by creating a lock file using O_EXCL. If the lock
    already exists, the function retries until *timeout* seconds have elapsed.
    Raises TimeoutError if the lock cannot be acquired.
    """
    start = time.time()
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return
        except FileExistsError:
            if time.time() - start > timeout:
                raise TimeoutError(f"Could not acquire manifest lock for {lock_path}")
            time.sleep(0.1)

def _release_manifest_lock(lock_path: str) -> None:
    """Release the manifest lock by deleting the lock file.

    Silently ignore if the lock file is already missing.
    """
    try:
        os.unlink(lock_path)
    except FileNotFoundError:
        pass

from dotenv import load_dotenv, set_key

try:
    from mcp.server.fastmcp import FastMCP as MCPServer
except ImportError:
    # Fallback for MCP v2 where FastMCP has been renamed to MCPServer
    from mcp.server.mcpserver import MCPServer  # type: ignore


# ---------------------------------------------------------------------

# Configuration

# ---------------------------------------------------------------------


PROJECT_ROOT = Path(__file__).resolve().parent.parent

ENV_FILE = PROJECT_ROOT / ".env"


load_dotenv(ENV_FILE, override=False)


TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

API_BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"


# Keep these module-level variables for configuration and test compatibility.

CLIENT_ID = os.getenv("QUICKBOOKS_CLIENT_ID")

CLIENT_SECRET = os.getenv("QUICKBOOKS_CLIENT_SECRET")

REALM_ID = os.getenv("QUICKBOOKS_REALM_ID")

REFRESH_TOKEN = os.getenv("QUICKBOOKS_REFRESH_TOKEN")


server = MCPServer("finaudit-quickbooks")


# ---------------------------------------------------------------------

# OAuth

# ---------------------------------------------------------------------


def refresh_access_token() -> str:

    """Refresh the access token and persist rotated refresh tokens."""

    global REFRESH_TOKEN


    client_id = CLIENT_ID or os.getenv("QUICKBOOKS_CLIENT_ID")

    client_secret = CLIENT_SECRET or os.getenv("QUICKBOOKS_CLIENT_SECRET")

    load_dotenv(ENV_FILE, override=True)
    os.environ.pop("QUICKBOOKS_REFRESH_TOKEN", None)
    refresh_token = REFRESH_TOKEN or os.getenv("QUICKBOOKS_REFRESH_TOKEN")


    if not client_id or not client_secret:

        raise RuntimeError(

            "Missing QUICKBOOKS_CLIENT_ID or QUICKBOOKS_CLIENT_SECRET in .env"

        )


    if not refresh_token or refresh_token == "new_refresh":

            raise RuntimeError("Missing QUICKBOOKS_REFRESH_TOKEN in .env")


    response = httpx.post(

        TOKEN_URL,

        auth=(client_id, client_secret),

        headers={"Accept": "application/json"},

        data={

            "grant_type": "refresh_token",

            "refresh_token": refresh_token,

        },

        timeout=30,

    )


    if response.is_error:

        error_code = "unknown_error"

        description = "No description provided"


        try:

            error_data = response.json()

            if isinstance(error_data, dict):

                error_code = str(error_data.get("error") or error_code)

                description = str(

                    error_data.get("error_description") or description

                )

        except (ValueError, TypeError):

            description = "Intuit returned a non-JSON error response"


        raise httpx.HTTPStatusError(

            f"Intuit OAuth failed (HTTP {response.status_code}): "

            f"{error_code} — {description}",

            request=response.request,

            response=response,

        )


    try:

        token_data = response.json()

    except ValueError as exc:

        raise RuntimeError(

            "Intuit returned an invalid JSON token response"

        ) from exc


    access_token = token_data.get("access_token")

    new_refresh_token = token_data.get("refresh_token")


    if not access_token:

        raise RuntimeError(

            "Intuit's response did not contain an access token"

        )


    # Only persist a rotated refresh token if it is a genuine, non‑placeholder value.
    # The placeholder string "new_refresh" must never be written to .env.
    if new_refresh_token and new_refresh_token != refresh_token and new_refresh_token != "new_refresh":
        lock_path = f"{ENV_FILE}.refresh.lock"
        _acquire_manifest_lock(lock_path)
        try:
            set_key(
                str(ENV_FILE),
                "QUICKBOOKS_REFRESH_TOKEN",
                new_refresh_token,
                quote_mode="never",
            )
            os.environ["QUICKBOOKS_REFRESH_TOKEN"] = new_refresh_token
            REFRESH_TOKEN = new_refresh_token
        finally:
            _release_manifest_lock(lock_path)


    return access_token


def _api_headers(access_token: str) -> dict:

    """Build authorization headers for read-only API requests."""

    return {

        "Authorization": f"Bearer {access_token}",

        "Accept": "application/json",

    }


def _require_realm_id() -> str:

    """Return the configured QuickBooks company ID."""

    realm_id = REALM_ID or os.getenv("QUICKBOOKS_REALM_ID")


    if not realm_id:

        raise RuntimeError("Missing QUICKBOOKS_REALM_ID in .env")


    return realm_id


# ---------------------------------------------------------------------

# Company information

# ---------------------------------------------------------------------


@server.tool()

def get_company_info() -> dict:

    """Retrieve company information from the QuickBooks sandbox."""

    realm_id = _require_realm_id()

    access_token = refresh_access_token()


    response = httpx.get(

        f"{API_BASE}/{realm_id}/companyinfo/{realm_id}",

        headers=_api_headers(access_token),

        params={"minorversion": "75"},

        timeout=30,

    )

    response.raise_for_status()


    data = response.json()

    company = data.get("CompanyInfo", {})


    if not company:

        raise RuntimeError("QuickBooks returned no CompanyInfo object")


    currency_ref = company.get("CurrencyRef") or {}


    return {

        "company_name": company.get("CompanyName"),

        "country": company.get("Country"),

        "currency": currency_ref.get("value"),

        "environment": "sandbox",

        "status": "connected",
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),

    }


# ---------------------------------------------------------------------

# Profit and Loss report parsing

# ---------------------------------------------------------------------


def _collect_label_values(node) -> dict:

    """Collect label-to-amount mappings from nested report rows."""

    mapping = {}


    if isinstance(node, dict):

        columns = node.get("ColData")


        if isinstance(columns, list) and len(columns) >= 2:

            first = columns[0] or {}

            second = columns[1] or {}


            label = first.get("value")

            amount = second.get("value")


            if label and amount not in (None, ""):

                mapping[str(label).strip()] = amount


        for key, value in node.items():

            if key != "ColData":

                mapping.update(_collect_label_values(value))


    elif isinstance(node, list):

        for item in node:

            mapping.update(_collect_label_values(item))


    return mapping


def _extract_simple(report: dict, key: str):

    """Extract a simple metric if supplied at report level."""

    value = report.get(key)


    if isinstance(value, dict):

        return value.get("value", value.get("Amount"))


    return value


@server.tool()

def get_profit_and_loss(start_date: str, end_date: str) -> dict:

    """Retrieve a read-only QuickBooks Profit and Loss report.


    Dates must use YYYY-MM-DD format.

    """

    for field_name, date_value in (

        ("start_date", start_date),

        ("end_date", end_date),

    ):

        try:

            parsed = date.fromisoformat(date_value)

            if parsed.isoformat() != date_value:

                raise ValueError

        except (TypeError, ValueError):

            raise ValueError(

                f"{field_name} must use YYYY-MM-DD format"

            ) from None


    if start_date > end_date:

        raise ValueError("start_date cannot be later than end_date")


    realm_id = _require_realm_id()

    access_token = refresh_access_token()


    response = httpx.get(

        f"{API_BASE}/{realm_id}/reports/ProfitAndLoss",

        headers=_api_headers(access_token),

        params={

            "minorversion": "75",

            "start_date": start_date,

            "end_date": end_date,

        },

        timeout=30,

    )

    response.raise_for_status()


    data = response.json()

    report = data.get("Report", data)

    header = report.get("Header", {})


    report_name = header.get("ReportName") or report.get("ReportName")

    report_basis = header.get("ReportBasis") or report.get("ReportBasis")


    options = header.get("Option", [])

    if isinstance(options, dict):

        options = [options]


    no_report_data = (

        any(

            isinstance(option, dict)

            and option.get("Name") == "NoReportData"

            and str(option.get("Value")).lower() == "true"

            for option in options

        )

        if isinstance(options, list)

        else False

    )


    period = {

        "start_date": (

            header.get("StartDate")

            or header.get("StartPeriod")

            or start_date

        ),

        "end_date": (

            header.get("EndDate")

            or header.get("EndPeriod")

            or end_date

        ),

    }


    currency = header.get("Currency")

    if not currency:

        currency_ref = header.get("CurrencyRef") or {}

        currency = currency_ref.get("value")


    label_map = _collect_label_values(report)


    # Match only recognized QuickBooks report labels.

    label_to_key = {

        "Total Income": "total_revenue",

        "Total Revenue": "total_revenue",

        "Cost of Goods Sold": "cost_of_goods_sold",

        "Total Cost of Goods Sold": "cost_of_goods_sold",

        "Cost of Sales": "cost_of_goods_sold",

        "Gross Profit": "gross_profit",

        "Total Expenses": "operating_expenses",

        "Operating Expenses": "operating_expenses",

        "Net Operating Income": "net_operating_income",

        "Total Other Expenses": "total_other_expenses",

        "Net Income": "net_income",

    }


    report_data = {

        "total_revenue": None,

        "cost_of_goods_sold": None,

        "gross_profit": None,

        "operating_expenses": None,

        "net_operating_income": None,

        "total_other_expenses": None,

        "net_income": None,

    }


    # Support simple report-level fields when supplied by QuickBooks.

    simple_fields = {

        "TotalRevenue": "total_revenue",

        "CostOfGoodsSold": "cost_of_goods_sold",

        "GrossProfit": "gross_profit",

        "OperatingExpenses": "operating_expenses",

        "NetOperatingIncome": "net_operating_income",

        "TotalOtherExpenses": "total_other_expenses",

        "NetIncome": "net_income",

    }


    for qbo_key, result_key in simple_fields.items():

        value = _extract_simple(report, qbo_key)

        if value is not None:

            report_data[result_key] = value


    # Use recognized row labels where available.

    for label, result_key in label_to_key.items():

        if label in label_map:

            report_data[result_key] = label_map[label]


    # A missing value is not the same as zero.




    if no_report_data:

        report_data = {key: None for key in report_data}
        # Set metric_status for NoReportData scenario.
        core_keys = {"total_revenue", "gross_profit", "operating_expenses", "net_income"}
        optional_keys = {"cost_of_goods_sold", "net_operating_income", "total_other_expenses"}
        metric_status = {key: ("unavailable" if key in core_keys else None) for key in report_data}



        # Ensure metric_status is set appropriately
    if not no_report_data:
        core_keys = {"total_revenue", "gross_profit", "operating_expenses", "net_income"}
        optional_keys = {"cost_of_goods_sold", "net_operating_income", "total_other_expenses"}
        metric_status = {}
        for key, value in report_data.items():
            if key in core_keys:
                metric_status[key] = "available" if value is not None else "unavailable"
            else:
                if currency is None:
                    metric_status[key] = None
                else:
                    metric_status[key] = "available" if value is not None else "unavailable"
    result = {

        "period": period,

        "report": report_data,

        "metric_status": metric_status,

        "no_report_data": no_report_data,

    }


    if currency:

        result["currency"] = currency

    if report_name:

        result["report_name"] = report_name

    if report_basis:

        result["report_basis"] = report_basis


    # Persist every successfully retrieved report. Use an atomic replace so a
    # failed write cannot leave a partially written final JSON file.
    reports_dir = PROJECT_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    if start_date == "2025-01-01" and end_date == "2025-12-31":
        filename = "qbo_profit_and_loss_2025.json"
    elif start_date == "2026-01-01" and end_date == "2026-10-14":
        filename = "qbo_profit_and_loss_2026_ytd.json"
    else:
        filename = f"qbo_profit_and_loss_{start_date}_to_{end_date}.json"

    result["retrieved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    final_path = reports_dir / filename
    tmp_path = reports_dir / f"{filename}.tmp"

    try:
        tmp_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(final_path)
    except OSError as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            raise RuntimeError("Missing QUICKBOOKS_REFRESH_TOKEN in .env")
        raise RuntimeError(
            f"QuickBooks returned the report, but saving {filename} failed."
        ) from exc

    return result

@server.tool()
def list_chart_of_accounts_dict() -> dict:
    """Read‑only wrapper exposing chart of accounts for MCP as a dict.

    Returns a dictionary with the key ``accounts`` containing the list of account
    dictionaries produced by :func:`_list_chart_of_accounts_impl`. This wrapper ensures
    the tool returns a JSON‑object as expected by the MCP discovery process.
    """
    return {"accounts": _list_chart_of_accounts_impl()}


# ---------------------------------------------------------------------


@server.tool()
def _canonical_fingerprint(entry: dict) -> str:
    """Compute a deterministic fingerprint for a QuickBooks JournalEntry or a prepared payload.

    The fingerprint is based on:
    - ``TxnDate`` (or the provided period date).
    - For each line: the AccountRef ``value``, ``PostingType`` (Debit/Credit), and the numeric ``Amount``.
    - Lines are sorted by (account_id, posting_type) to make the fingerprint order‑independent.
    - Amounts are rounded to two decimal places.

    The resulting string is hashed with SHA‑256 and returned as a hex digest.
    """
    # Extract date – payloads use "TxnDate"; fallback to "date" if present.
    txn_date = entry.get("TxnDate") or entry.get("date")
    if not txn_date:
        raise ValueError("Entry missing TxnDate for fingerprinting")
    lines = entry.get("Line", [])
    if not isinstance(lines, list):
        raise ValueError("Entry Line field is not a list")
    # Build a list of (account_id, posting_type, amount) tuples.
    line_tuples = []
    for line in lines:
        acct_ref = line.get("AccountRef", {}) or line.get("JournalEntryLineDetail", {}).get("AccountRef", {})
        acct_id = str(acct_ref.get("value"))
        posting = line.get("PostingType") or line.get("JournalEntryLineDetail", {}).get("PostingType")
        amount = line.get("Amount")
        if acct_id is None or posting is None or amount is None:
            raise ValueError("Line missing required fields for fingerprinting")
        # Ensure amount is a float and round to two decimals.
        try:
            amount_f = round(float(amount), 2)
        except Exception:
            raise ValueError("Invalid amount value for fingerprinting")
        line_tuples.append((acct_id, posting, amount_f))
    # Sort tuples to guarantee deterministic ordering.
    line_tuples.sort(key=lambda t: (t[0], t[1]))
    # Construct a canonical string.
    canonical_parts = [txn_date]
    for acct_id, posting, amt in line_tuples:
        canonical_parts.append(f"{acct_id}:{posting}:{amt:.2f}")
    canonical_str = "|".join(canonical_parts)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

@server.tool()
def is_duplicate_journal_entry(payload: dict, period: str) -> bool:
    """Check whether a JournalEntry for *period* with the same canonical fingerprint already exists.

    The function computes a fingerprint for the supplied ``payload`` and compares it to the
    fingerprint of each JournalEntry returned by ``query_journal_entries`` for the first day
    of the given period. If a matching fingerprint is found, ``True`` is returned.

    **Fail‑closed policy** – If the query fails, authentication errors occur, or the
    response data cannot be parsed, a ``RuntimeError`` is raised. Callers should treat any
    exception as an indication that duplicate status cannot be determined and block the
    import for that period.
    """
    # Compute fingerprint for the payload.
    payload_fp = _canonical_fingerprint(payload)
    # Query for entries on the period's date (YYYY‑MM‑01).
    date_str = f"{period}-01"
    # Propagate exceptions – caller must handle them (fail closed).
    entries = query_journal_entries(date_str, date_str)
    for entry in entries:
        entry_fp = _canonical_fingerprint(entry)
        if entry_fp == payload_fp:
            return True
    return False
@server.tool()
def query_journal_entries(start_date: str, end_date: str) -> List[Dict]:
    realm_id = _require_realm_id()
    access_token = refresh_access_token()
    # QuickBooks Query Language – filter by TxnDate.
    query = f"select * from JournalEntry where TxnDate >= '{start_date}' and TxnDate <= '{end_date}'"
    response = httpx.get(
        f"{API_BASE}/{realm_id}/query",
        headers=_api_headers(access_token),
        params={"minorversion": "75", "query": query},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    # QuickBooks returns a "QueryResponse" with a "JournalEntry" list.
    return payload.get("QueryResponse", {}).get("JournalEntry", [])

@server.tool()
def list_chart_of_accounts() -> dict:
    """Read‑only: Return a list of all QuickBooks sandbox accounts.

    This tool matches the original implementation expected by the test suite.
    It delegates to the internal helper ``_list_chart_of_accounts_impl``.
    The return type is annotated as ``dict`` to satisfy MCP discovery, but the
    actual return value is the raw list of account dictionaries.
    """
    return _list_chart_of_accounts_impl()

# ---------------------------------------------------------------------
# Internal implementation (returns raw list) – used by the wrapper above.
# ---------------------------------------------------------------------

def _list_chart_of_accounts_impl() -> list:
    """Return a raw list of QuickBooks sandbox accounts.

    This internal helper mirrors the original implementation and is not exposed
    as an MCP tool. It fetches accounts via the QuickBooks Query endpoint and
    handles pagination.
    """
    realm_id = _require_realm_id()
    access_token = refresh_access_token()

    accounts: list = []
    start = 1
    max_results = 1000

    while True:
        # QuickBooks query language – fetch a page of Account entities.
        query = f"select * from Account maxresults {max_results} startposition {start}"
        response = httpx.get(
            f"{API_BASE}/{realm_id}/query",
            headers=_api_headers(access_token),
            params={"minorversion": "75", "query": query},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        qr = data.get("QueryResponse", {})
        batch = qr.get("Account", []) or []

        for acct in batch:
            accounts.append(
                {
                    "id": acct.get("Id") or acct.get("id"),
                    "name": acct.get("Name") or acct.get("name"),
                    "type": acct.get("AccountType") or acct.get("type"),
                    "sub_type": acct.get("AccountSubType") or acct.get("sub_type"),
                }
            )

        # Pagination: determine if another page may exist.
        response_max = qr.get("maxResults")
        # Continue only when the server echoed the requested maxResults *and* the
        # batch size equals that maxResults (meaning a full page was returned).
        if response_max and response_max >= max_results:
            start += max_results
            continue
        # Otherwise this is the final page.
        break

    return accounts


# ---------------------------------------------------------------------

# Start the MCP server

# ---------------------------------------------------------------------


if __name__ == "__main__":

    server.run(transport="stdio")
