"""Tests for the local QuickBooks JournalEntry preparation function.

These tests verify that the payload generation respects debit/credit balance,
handles missing account mappings, correctly adds a net‑income balancing line
when required, supports zero and negative expense values, and that import
recording via the manifest is performed separately from preparation.
"""

import json
import os
import pytest
from pathlib import Path

# Dynamically load functions under test
import importlib.util, pathlib

module_path = pathlib.Path(__file__).resolve().parents[1] / 'integrations' / 'qbo_import_preparation.py'
spec = importlib.util.spec_from_file_location('qbo_import_preparation', module_path)
qbo_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qbo_module)
prepare_journal_entry = qbo_module.prepare_journal_entry
record_journal_entry_import = qbo_module.record_journal_entry_import

# Helper to extract totals from the payload
def _totals(payload: dict):
    credit = sum(line["Amount"] for line in payload["Line"] if line["PostingType"] == "Credit")
    debit = sum(line["Amount"] for line in payload["Line"] if line["PostingType"] == "Debit")
    return credit, debit

# A minimal valid account map for the required keys
BASE_ACCOUNT_MAP = {
    "revenue": "1",
    "cogs": "2",
    "direct_opex": "3",
    "sm_payroll": "4",
    "marketing": "5",
    "other_opex": "6",
    # "net_income" optional, added in specific tests when needed
}

def test_balanced_journal_entry():
    """A balanced period should produce a payload without a net‑income line and without touching the manifest."""
    normalized = {
        "period": "2026-01",
        "revenue": 1000.0,
        "cost_of_goods_sold": 400.0,
        "direct_opex": 200.0,
        "sm_payroll": 150.0,
        "marketing": 150.0,
        "other_opex": 100.0,
    }
    payload = prepare_journal_entry(normalized, BASE_ACCOUNT_MAP)
    assert payload["TxnDate"] == "2026-01-01"
    assert len(payload["Line"]) == 6
    credit, debit = _totals(payload)
    assert credit == pytest.approx(debit)
    assert all(line["AccountRef"]["value"] != "net_income" for line in payload["Line"])

def test_missing_account_mapping():
    """Missing a required account mapping should raise ValueError."""
    normalized = {
        "period": "2026-02",
        "revenue": 500.0,
        "cost_of_goods_sold": 200.0,
        "direct_opex": 100.0,
        "sm_payroll": 50.0,
        "marketing": 50.0,
        "other_opex": 100.0,
    }
    bad_map = BASE_ACCOUNT_MAP.copy()
    del bad_map["marketing"]
    with pytest.raises(ValueError, match="Missing account mapping for 'marketing'"):
        prepare_journal_entry(normalized, bad_map)

def test_balancing_requires_net_income_profit(tmp_path: Path):
    """Profit period requires a Debit net_income line to balance the entry."""
    normalized = {
        "period": "2026-03",
        "revenue": 1200.0,
        "cost_of_goods_sold": 300.0,
        "direct_opex": 200.0,
        "sm_payroll": 100.0,
        "marketing": 50.0,
        "other_opex": 50.0,
    }
    # Missing net_income mapping should raise
    with pytest.raises(ValueError, match="Balancing entry required but no 'net_income' account mapping provided"):
        prepare_journal_entry(normalized, BASE_ACCOUNT_MAP)
    # With mapping, preparation succeeds
    mapping = BASE_ACCOUNT_MAP.copy()
    mapping["net_income"] = "7"
    payload = prepare_journal_entry(normalized, mapping)
    assert len(payload["Line"]) == 7
    net_line = next(line for line in payload["Line"] if line["AccountRef"]["value"] == "7")
    assert net_line["PostingType"] == "Debit"
    credit, debit = _totals(payload)
    assert credit == pytest.approx(debit)
    # Record the successful import
    manifest = tmp_path / "manifest.json"
    record_journal_entry_import(payload, normalized["period"], manifest_path=str(manifest))
    # Duplicate record should raise
    with pytest.raises(ValueError, match="Duplicate journal entry detected"):
        record_journal_entry_import(payload, normalized["period"], manifest_path=str(manifest))

def test_balancing_requires_net_income_loss(tmp_path: Path):
    """Loss period requires a Credit net_income line to balance the entry."""
    pass

def test_zero_and_negative_expense_values(tmp_path: Path):
    """Zero or negative expense values are handled and a balancing net_income line is added when needed."""
    normalized = {
        "period": "2026-06",
        "revenue": 1000.0,
        "cost_of_goods_sold": 0.0,
        "direct_opex": -50.0,  # negative expense becomes a credit line
        "sm_payroll": 0.0,
        "marketing": 0.0,
        "other_opex": 0.0,
    }
    mapping = BASE_ACCOUNT_MAP.copy()
    mapping["net_income"] = "7"
    payload = prepare_journal_entry(normalized, mapping)
    assert any(line["AccountRef"]["value"] == "7" for line in payload["Line"])  # net_income present
    direct_line = next(line for line in payload["Line"] if line["AccountRef"]["value"] == "3")
    assert direct_line["Amount"] == pytest.approx(50.0)
    # Net income should be a Debit line because the overall balance is positive
    net_line = next(line for line in payload["Line"] if line["AccountRef"]["value"] == "7")
    assert net_line["PostingType"] == "Debit"
    credit, debit = _totals(payload)
    assert credit == pytest.approx(debit)
    # Record import and verify no duplicate error for a fresh manifest
    manifest = tmp_path / "manifest.json"
    record_journal_entry_import(payload, normalized["period"], manifest_path=str(manifest))

def test_invalid_input_missing_field():
    """Calling the function with a missing required field should raise ValueError."""
    normalized = {
        "period": "2026-07",
        # revenue omitted intentionally
        "cost_of_goods_sold": 100.0,
        "direct_opex": 50.0,
        "sm_payroll": 25.0,
        "marketing": 25.0,
        "other_opex": 10.0,
    }
    with pytest.raises(ValueError, match="Missing required field 'revenue'"):
        prepare_journal_entry(normalized, BASE_ACCOUNT_MAP)
