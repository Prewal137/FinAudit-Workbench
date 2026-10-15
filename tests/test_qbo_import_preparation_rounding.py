import pytest

# Load the module under test dynamically (same as in other tests)
import importlib.util, pathlib

module_path = pathlib.Path(__file__).resolve().parents[1] / 'integrations' / 'qbo_import_preparation.py'
spec = importlib.util.spec_from_file_location('qbo_import_preparation', module_path)
qbo_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qbo_module)
prepare_journal_entry = qbo_module.prepare_journal_entry

BASE_ACCOUNT_MAP = {
    "revenue": "1",
    "cogs": "2",
    "direct_opex": "3",
    "sm_payroll": "4",
    "marketing": "5",
    "other_opex": "6",
}

def test_rounding_of_amounts():
    """Amounts should be rounded to two decimal places in the payload."""
    normalized = {
        "period": "2026-08",
        # Revenue set to sum of rounded expense amounts (44.11) to achieve a balanced entry.
        "revenue": 44.1109,
        "cost_of_goods_sold": 23.1234,
        "direct_opex": 10.9876,
        "sm_payroll": 5.5555,
        "marketing": 3.3333,
        "other_opex": 1.1111,
    }
    # This creates a balanced entry without net_income mapping.
    payload = prepare_journal_entry(normalized, BASE_ACCOUNT_MAP)
    # Verify each amount is rounded to 2 decimals.
    for line in payload["Line"]:
        # All amounts should have at most two decimal places.
        assert round(line["Amount"], 2) == line["Amount"], "Amount not rounded to 2 decimals"
