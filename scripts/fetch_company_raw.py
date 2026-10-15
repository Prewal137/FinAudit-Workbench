import os
import json
from pathlib import Path
import httpx
from dotenv import load_dotenv

# Resolve the project root (repo root) relative to this script location
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

CLIENT_ID = os.getenv("QUICKBOOKS_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("QUICKBOOKS_CLIENT_SECRET", "").strip()
REALM_ID = os.getenv("QUICKBOOKS_REALM_ID", "").strip()
REFRESH_TOKEN = os.getenv("QUICKBOOKS_REFRESH_TOKEN", "").strip()

TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
API_BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"

def refresh_access_token():
    if not all([CLIENT_ID, CLIENT_SECRET, REALM_ID, REFRESH_TOKEN]):
        raise RuntimeError("Missing QuickBooks credentials. Check .env.")
    response = httpx.post(
        TOKEN_URL,
        auth=(CLIENT_ID, CLIENT_SECRET),
        headers={"Accept": "application/json"},
        data={"grant_type": "refresh_token", "refresh_token": REFRESH_TOKEN},
        timeout=30,
    )
    response.raise_for_status()
    tokens = response.json()
    return tokens["access_token"]

def main():
    access_token = refresh_access_token()
    resp = httpx.get(
        f"{API_BASE}/{REALM_ID}/companyinfo/{REALM_ID}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        params={"minorversion": "75"},
        timeout=30,
    )
    resp.raise_for_status()
    # Print the full JSON response (beautified)
    print(json.dumps(resp.json(), indent=2))

if __name__ == "__main__":
    main()
