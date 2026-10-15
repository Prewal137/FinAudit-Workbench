"""Test that generated payload lines follow the QuickBooks JournalEntry schema.

The QuickBooks API expects each line to include a nested ``JournalEntryLineDetail`` object.
"""

import importlib.util
import pathlib
import sys
import pytest

SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "generate_balanced_payloads.py"

def load_module():
    spec = importlib.util.spec_from_file_location("gen_balanced", str(SCRIPT_PATH))
    mod = importlib.util.module_from_spec(spec)
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.append(str(repo_root))
    spec.loader.exec_module(mod)
    return mod

ACCOUNT_MAP = {
    "revenue": "1",
    "cogs": "80",
    "direct_opex": "7",
    "sm_payroll": "57",
    "marketing": "16",
    "other_opex": "14",
    "net_income": "2",
}

def assert_line_schema(line):
    # Top‑level keys
    assert line["DetailType"] == "JournalEntryLineDetail"
    assert "JournalEntryLineDetail" in line
    # No stray top‑level PostingType / AccountRef
    assert "PostingType" not in line
    assert "AccountRef" not in line
    inner = line["JournalEntryLineDetail"]
    assert isinstance(inner, dict)
    assert "PostingType" in inner
    assert "AccountRef" in inner
    assert isinstance(inner["AccountRef"], dict)
    assert "value" in inner["AccountRef"]

def test_payload_line_schema_profit():
    mod = load_module()
    payload = mod.build_balanced_payload({
        "period": "2025-01",
        "revenue": 1000.0,
        "cost_of_goods_sold": 200.0,
        "direct_opex": 150.0,
        "sm_payroll": 130.0,
        "marketing": 90.0,
        "other_opex": 80.0,
        "net_income": 250.0,  # profit → Credit
    }, ACCOUNT_MAP)
    for line in payload["Line"]:
        assert_line_schema(line)

def test_payload_line_schema_loss():
    mod = load_module()
    payload = mod.build_balanced_payload({
        "period": "2025-02",
        "revenue": 800.0,
        "cost_of_goods_sold": 300.0,
        "direct_opex": 120.0,
        "sm_payroll": 110.0,
        "marketing": 70.0,
        "other_opex": 60.0,
        "net_income": -150.0,  # loss → Debit
    }, ACCOUNT_MAP)
    for line in payload["Line"]:
        assert_line_schema(line)
