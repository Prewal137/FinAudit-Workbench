import json
import textwrap
from pathlib import Path

# Helper to create a minimal balanced payload JSON for testing.
def make_payload(period: str, revenue: float, expenses: list[float], net_income: float, account_map: dict) -> dict:
    """Return a payload dict.

    * ``period`` is "YYYY-MM" (used for TxnDate "YYYY-MM-01").
    * ``revenue`` is the credit amount.
    * ``expenses`` is a list of debit amounts.
    * ``net_income`` is the net income amount (positive = profit, negative = loss).
    * ``account_map`` maps logical keys to QuickBooks IDs; must contain
      ``revenue``, ``cogs``, ``direct_opex``, ``sm_payroll``, ``marketing``, ``other_opex``, ``net_income``.
    """
    lines = []
    # Revenue (credit)
    lines.append({
        "Amount": round(abs(revenue), 2),
        "DetailType": "JournalEntryLineDetail",
        "PostingType": "Credit",
        "AccountRef": {"value": str(account_map["revenue"])},
    })
    # Expenses (debits) – map them to the first five expense accounts.
    expense_keys = ["cogs", "direct_opex", "sm_payroll", "marketing", "other_opex"]
    for amt, key in zip(expenses, expense_keys):
        lines.append({
            "Amount": round(abs(amt), 2),
            "DetailType": "JournalEntryLineDetail",
            "PostingType": "Debit",
            "AccountRef": {"value": str(account_map[key])},
        })
    # Net‑income balancing line if present.
    if net_income != 0:
        posting = "Debit" if net_income > 0 else "Credit"
        amount = abs(net_income)
        lines.append({
            "Amount": round(amount, 2),
            "DetailType": "JournalEntryLineDetail",
            "PostingType": posting,
            "AccountRef": {"value": str(account_map["net_income"])},
        })
    return {"TxnDate": f"{period}-01", "Line": lines}

# Example account map (matches the repository's config).
example_account_map = {
    "revenue": "1",
    "cogs": "80",
    "direct_opex": "7",
    "sm_payroll": "57",
    "marketing": "16",
    "other_opex": "14",
    "net_income": "2",
}

# Create a balanced payload for period 2025-01.
# Revenue credit 800, expenses debit 600 and 400, net_income loss -200 (credit).
period = "2025-01"
payload = make_payload(
    period=period,
    revenue=800.0,
    expenses=[600.0, 400.0],
    net_income=-200.0,
    account_map=example_account_map,
)

# Write the payload to the expected dry‑run directory.
reports_dir = Path(__file__).resolve().parents[2] / "reports"
payload_dir = reports_dir / "dry_run_payloads"
payload_dir.mkdir(parents=True, exist_ok=True)
payload_path = payload_dir / f"{period}.json"
payload_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

print(f"Created test payload at {payload_path}")
