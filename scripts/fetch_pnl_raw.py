
import os
import json
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

CLIENT_ID = os.getenv("QUICKBOOKS_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("QUICKBOOKS_CLIENT_SECRET", "").strip()
REALM_ID = os.getenv("QUICKBOOKS_REALM_ID", "").strip()
REFRESH_TOKEN = os.getenv("QUICKBOOKS_REFRESH_TOKEN", "").strip()

TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API_BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"

def main():
    if not all([CLIENT_ID, CLIENT_SECRET, REALM_ID, REFRESH_TOKEN]):
        raise RuntimeError("Missing QuickBooks credentials in .env")

    token_response = httpx.post(
        TOKEN_URL,
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": REFRESH_TOKEN,
        },
        timeout=30,
    )
    token_response.raise_for_status()
    access_token = token_response.json()["access_token"]

    response = httpx.get(
        f"{API_BASE}/{REALM_ID}/reports/ProfitAndLoss",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        params={
            "minorversion": "75",
            "start_date": "2026-01-01",
            "end_date": "2026-10-12",
        },
        timeout=30,
    )
    response.raise_for_status()
    report = response.json()

    # Print only the report JSON, never credentials or tokens.
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
