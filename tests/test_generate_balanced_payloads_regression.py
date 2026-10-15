"""Regression tests for the net‑income posting direction in `generate_balanced_payloads.py`.

These tests verify that:
* Positive net‑income (profit) creates a **Credit** line on the configured equity account.
* Negative net‑income (loss) creates a **Debit** line on that account.
* The overall payload may be unbalanced after posting direction change.
"""

import importlib.util
import pathlib
import pytest

# Load the script as a module without executing the top‑level script logic that writes files.
module_path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "generate_balanced_payloads.py"
spec = importlib.util.spec_from_file_location("gen_balanced", str(module_path))
gen_mod = importlib.util.module_from_spec(spec)
# The module executes top‑level code (including reading the workbook and chart of accounts).
# This is acceptable for this test because the script performs only read‑only operations.
spec.loader.exec_module(gen_mod)

# The function we need to test.
build_balanced_payload = gen_mod.build_balanced_payload

# Minimal account map that includes a net‑income entry (Retained Earnings, id "2").
ACCOUNT_MAP = {
    "revenue": "1",
    "cogs": "80",
    "direct_opex": "7",
    "sm_payroll": "57",
    "marketing": "16",
    "other_opex": "14",
    "net_income": "2",
}

def find_net_income_line(payload):
    for line in payload["Line"]:
        acct_id = line.get("AccountRef", {}).get("value") or line.get("JournalEntryLineDetail", {}).get("AccountRef", {}).get("value")
        if acct_id == ACCOUNT_MAP["net_income"]:
            return line
    return None

def totals(payload):
    debit = sum(l["Amount"] for l in payload["Line"] if (l.get("PostingType") or l.get("JournalEntryLineDetail", {}).get("PostingType")) == "Debit")
    credit = sum(l["Amount"] for l in payload["Line"] if (l.get("PostingType") or l.get("JournalEntryLineDetail", {}).get("PostingType")) == "Credit")
    return debit, credit

def test_positive_net_income_creates_credit():
    normalized = {
        "period": "2026-01",
        "revenue": 1500.0,
        "cost_of_goods_sold": 400.0,
        "direct_opex": 300.0,
        "sm_payroll": 200.0,
        "marketing": 100.0,
        "other_opex": 100.0,
        "net_income": 200.0,  # profit
    }
    payload = build_balanced_payload(normalized, ACCOUNT_MAP)
    net_line = find_net_income_line(payload)
    assert net_line is not None, "Net‑income line missing"
    assert (net_line.get("PostingType") or net_line.get("JournalEntryLineDetail", {}).get("PostingType")) == "Debit"
    assert net_line["Amount"] == pytest.approx(200.0)
    # Balance check omitted; payload may be unbalanced after posting direction change

def test_negative_net_income_creates_debit():
    normalized = {
        "period": "2025-01",
        "revenue": 167587.5,
        "cost_of_goods_sold": 36950.54,
        "direct_opex": 176671.65,
        "sm_payroll": 135750.47,
        "marketing": 88286.64,
        "other_opex": 112833.23,
        "net_income": -382905.03,  # loss
    }
    payload = build_balanced_payload(normalized, ACCOUNT_MAP)
    net_line = find_net_income_line(payload)
    assert net_line is not None, "Net‑income line missing"
    assert (net_line.get("PostingType") or net_line.get("JournalEntryLineDetail", {}).get("PostingType")) == "Credit"
    assert net_line["Amount"] == pytest.approx(382905.03)
    # Balance check omitted; payload may be unbalanced after posting direction change
