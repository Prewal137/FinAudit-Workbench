"""Balanced JournalEntry preparation utilities.

Provides a wrapper around the existing ``prepare_journal_entry`` that adds a
net‑income balancing line when the source data includes a ``net_income`` value
and the account mapping contains a ``"net_income"`` entry. This respects the
original design (which intentionally disables auto‑balancing) while offering a
safe, explicit way to produce a balanced payload for import into the QuickBooks
sandbox.
"""

from __future__ import annotations

from typing import Dict, Any

# Re‑use the existing implementation.
from integrations.qbo_import_preparation import prepare_journal_entry


def prepare_balanced_journal_entry(normalized_period: Dict[str, Any], account_map: Dict[str, str]):
    """Create a balanced JournalEntry payload for the given period.

    This mirrors the logic from ``scripts/generate_balanced_payloads.py`` and ensures
    the resulting payload is balanced by adding a net‑income line when appropriate.
    """
    period = normalized_period.get("period")
    # Helper to add a line.
    def _add_line(amount: float, posting_type: str, acct_key: str, lines_acc: list):
        lines_acc.append({
            "Amount": round(abs(amount), 2),
            "DetailType": "JournalEntryLineDetail",
            "PostingType": posting_type,
            "AccountRef": {"value": str(account_map[acct_key])},
        })
    lines: list = []
    # Revenue is a credit.
    _add_line(normalized_period["revenue"], "Credit", "revenue", lines)
    # Expenses – positive amounts are debits, negative become credits.
    expense_map = {
        "cost_of_goods_sold": "cogs",
        "direct_opex": "direct_opex",
        "sm_payroll": "sm_payroll",
        "marketing": "marketing",
        "other_opex": "other_opex",
    }
    for period_key, acct_key in expense_map.items():
        amount = normalized_period[period_key]
        if amount >= 0:
            _add_line(amount, "Debit", acct_key, lines)
        else:
            _add_line(-amount, "Credit", acct_key, lines)
    # Net‑income balancing line if present.
    if "net_income" in normalized_period and normalized_period["net_income"] is not None:
        net_income_amount = normalized_period["net_income"]
        if net_income_amount >= 0:
            posting = "Debit"
            amount = net_income_amount
        else:
            posting = "Credit"
            amount = -net_income_amount
        _add_line(amount, posting, "net_income", lines)
    # Verify totals.
    total_debits = sum(l["Amount"] for l in lines if l["PostingType"] == "Debit")
    total_credits = sum(l["Amount"] for l in lines if l["PostingType"] == "Credit")
    if abs(total_debits - total_credits) > 0.01:
        raise RuntimeError(f"Balanced payload generation failed for period {period}: debits {total_debits:.2f} != credits {total_credits:.2f}")
    return {"TxnDate": f"{period}-01", "Line": lines}

"""Utility script entry‑point (optional).

Running ``python -m integrations.qbo_import_balanced`` will load the default
workbook, prepare balanced payloads for each period, and write the JSON payloads
to ``reports/qbo_import_payloads/`` for review. No QuickBooks write is performed.
"""

if __name__ == "__main__":
    import argparse
    from pathlib import Path
    import json
    from src.ingestion import load_financial_workbook
    from src.metrics import calculate_financial_metrics

    parser = argparse.ArgumentParser(description="Prepare balanced JournalEntry payloads from the workbook without posting.")
    parser.add_argument("workbook", type=str, help="Path to the Excel workbook")
    parser.add_argument("--mapping", type=str, default=str(Path(__file__).parents[2] / "configs" / "account_map.json"), help="Account mapping JSON file")
    args = parser.parse_args()

    # Load workbook.
    is_stmt, bs_stmt = load_financial_workbook(args.workbook)
    metrics = calculate_financial_metrics(is_stmt, bs_stmt)
    periods = metrics.get_chronological_periods()

    # Load account mapping.
    import json
    with open(args.mapping, "r", encoding="utf-8") as f:
        account_map = json.load(f)

    out_dir = Path("reports") / "qbo_import_payloads"
    out_dir.mkdir(parents=True, exist_ok=True)

    for p in periods:
        mm = metrics.get_monthly(p)
        norm = {
            "period": p,
            "revenue": mm.revenue,
            "cost_of_goods_sold": mm.cogs,
            "direct_opex": mm.direct_opex,
            "sm_payroll": mm.sm_payroll,
            "marketing": mm.marketing,
            "other_opex": mm.other_opex,
        }
        if mm.net_income is not None:
            norm["net_income"] = mm.net_income
        try:
            payload = prepare_balanced_journal_entry(norm, account_map)
        except Exception as exc:
            print(f"Failed for period {p}: {exc}")
            continue
        # Write payload JSON for review.
        (out_dir / f"payload_{p}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Prepared balanced payload for period {p}")
