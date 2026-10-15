"""Tests for account ID validation in ``prepare_journal_entry`` (A1)."""

import pytest
import importlib.util
import pathlib

# Load the module dynamically (as done in other tests)
module_path = pathlib.Path(__file__).resolve().parents[1] / "integrations" / "qbo_import_preparation.py"
spec = importlib.util.spec_from_file_location("qbo_import_preparation", module_path)
qbo_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qbo_mod)
prepare_journal_entry = qbo_mod.prepare_journal_entry

# Re‑use the BASE_ACCOUNT_MAP from existing test module via import
base_module_path = pathlib.Path(__file__).resolve().parents[1] / "tests" / "test_qbo_import_preparation.py"
spec2 = importlib.util.spec_from_file_location("test_qbo_import_preparation", base_module_path)
base_mod = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(base_mod)
BASE_ACCOUNT_MAP = base_mod.BASE_ACCOUNT_MAP

# Minimal valid normalized period (values can be arbitrary numbers)
VALID_NORMALIZED = {
    "period": "2026-01",
    "revenue": 1000.0,
    "cost_of_goods_sold": 400.0,
    "direct_opex": 200.0,
    "sm_payroll": 150.0,
    "marketing": 150.0,
    "other_opex": 100.0,
}

# Snapshot resembling the QuickBooks chart of accounts (list of dicts with "id")
VALID_SNAPSHOT = [
    {"id": "1", "name": "Revenue", "type": "Income"},
    {"id": "2", "name": "COGS", "type": "CostOfGoodsSold"},
    {"id": "3", "name": "Direct OPEX", "type": "Expense"},
    {"id": "4", "name": "SM Payroll", "type": "Expense"},
    {"id": "5", "name": "Marketing", "type": "Expense"},
    {"id": "6", "name": "Other OPEX", "type": "Expense"},
    {"id": "7", "name": "Net Income", "type": "Equity"},
]

def test_prepare_journal_entry_with_valid_snapshot():
    """When a valid chart‑of‑accounts snapshot is supplied, no validation error is raised."""
    payload = prepare_journal_entry(VALID_NORMALIZED, BASE_ACCOUNT_MAP, chart_of_accounts=VALID_SNAPSHOT)
    assert isinstance(payload, dict)
    assert "TxnDate" in payload and "Line" in payload

def test_prepare_journal_entry_missing_account_raises():
    """If the snapshot does not contain a required account ID, a ``ValueError`` is raised."""
    # Remove the "marketing" account (ID "5") from the snapshot.
    incomplete_snapshot = [acct for acct in VALID_SNAPSHOT if acct["id"] != "5"]
    with pytest.raises(ValueError, match="Account ID '5' for mapping key 'marketing' not found"):
        prepare_journal_entry(VALID_NORMALIZED, BASE_ACCOUNT_MAP, chart_of_accounts=incomplete_snapshot)
