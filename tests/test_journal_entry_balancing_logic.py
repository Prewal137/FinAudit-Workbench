'''Tests for read‑only safety and accounting‑logic validation of QBO journal‑entry preparation after Phase 5 changes.

These tests verify that:
* Revenue lines are generated as Credit entries.
* Expense lines are generated as Debit entries.
* The function raises a ValueError for unbalanced entries (no automatic net_income balancing).
* The manifest handling functions behave as before.
'''

import inspect
import pytest
import importlib.util, pathlib

# Load the module under test.
module_path = pathlib.Path(__file__).resolve().parents[1] / 'integrations' / 'qbo_import_preparation.py'
spec = importlib.util.spec_from_file_location('qbo_import_preparation', module_path)
qbo_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qbo_mod)
prepare_journal_entry = qbo_mod.prepare_journal_entry
record_journal_entry_import = qbo_mod.record_journal_entry_import

# Minimal valid account map (no net_income mapping needed).
BASE_ACCOUNT_MAP = {
    "revenue": "1",
    "cogs": "2",
    "direct_opex": "3",
    "sm_payroll": "4",
    "marketing": "5",
    "other_opex": "6",
}

def _category_lines(payload, mapping):
    result = {}
    for key, acct_id in mapping.items():
        for line in payload["Line"]:
            if line["AccountRef"]["value"] == str(acct_id):
                result[key] = line
                break
    return result

def _make_balanced_normalized(period="2026-01", revenue=1000.0, expense=200.0):
    """Create a normalized dict where total expenses equal revenue.
    It distributes the expense equally among the five expense categories.
    """
    per_expense = expense / 5
    return {
        "period": period,
        "revenue": revenue,
        "cost_of_goods_sold": per_expense,
        "direct_opex": per_expense,
        "sm_payroll": per_expense,
        "marketing": per_expense,
        "other_opex": per_expense,
    }

def test_prepare_signature_has_no_manifest_path():
    """The preparation function must not accept a manifest path (read‑only guarantee)."""
    sig = inspect.signature(prepare_journal_entry)
    assert "manifest_path" not in sig.parameters

def test_revenue_line_is_credit():
    normalized = _make_balanced_normalized(revenue=500.0, expense=500.0)
    payload = prepare_journal_entry(normalized, BASE_ACCOUNT_MAP)
    rev_line = next(line for line in payload["Line"] if line["AccountRef"]["value"] == BASE_ACCOUNT_MAP["revenue"])
    assert rev_line["PostingType"] == "Credit"
    assert rev_line["Amount"] == pytest.approx(500.0)

def test_expense_lines_are_debits():
    normalized = _make_balanced_normalized(revenue=800.0, expense=800.0)
    payload = prepare_journal_entry(normalized, BASE_ACCOUNT_MAP)
    lines_by_key = _category_lines(payload, BASE_ACCOUNT_MAP)
    expense_keys = ["cogs", "direct_opex", "sm_payroll", "marketing", "other_opex"]
    for key in expense_keys:
        assert key in lines_by_key
        line = lines_by_key[key]
        assert line["PostingType"] == "Debit"
        # Amount should be the absolute expense value.
        expected = normalized[key] if key != "cogs" else normalized["cost_of_goods_sold"]
        assert line["Amount"] == pytest.approx(abs(expected))

def test_unbalanced_entry_raises_error():
    # Profit scenario (revenue > expenses)
    profit_norm = _make_balanced_normalized(revenue=1000.0, expense=800.0)
    with pytest.raises(ValueError, match="Unbalanced entry"):
        prepare_journal_entry(profit_norm, BASE_ACCOUNT_MAP)
    # Loss scenario (expenses > revenue)
    loss_norm = _make_balanced_normalized(revenue=600.0, expense=900.0)
    with pytest.raises(ValueError, match="Unbalanced entry"):
        prepare_journal_entry(loss_norm, BASE_ACCOUNT_MAP)

def test_record_journal_entry_import_behaviour(tmp_path):
    """Verify duplicate and conflicting import detection works unchanged."""
    # Use a balanced normalized period.
    normalized = _make_balanced_normalized(revenue=500.0, expense=500.0)
    payload = prepare_journal_entry(normalized, BASE_ACCOUNT_MAP)
    period = normalized["period"]
    manifest_path = tmp_path / "manifest.json"
    # First import succeeds.
    record_journal_entry_import(payload, period, manifest_path=str(manifest_path))
    # Duplicate payload raises duplicate error.
    with pytest.raises(ValueError) as exc_dup:
        record_journal_entry_import(payload, period, manifest_path=str(manifest_path))
    assert "Duplicate journal entry detected" in str(exc_dup.value)
    # Conflicting payload (modify revenue amount) raises conflict error.
    conflicting = payload.copy()
    conflicting["Line"] = [line.copy() for line in payload["Line"]]
    for line in conflicting["Line"]:
        if line["AccountRef"]["value"] == BASE_ACCOUNT_MAP["revenue"]:
            line["Amount"] = line["Amount"] + 1.0
            break
    with pytest.raises(ValueError) as exc_conf:
        record_journal_entry_import(conflicting, period, manifest_path=str(manifest_path))
    assert "Conflicting journal entry already recorded" in str(exc_conf.value)

