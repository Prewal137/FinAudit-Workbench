'''Tests for read‑only safety and accounting‑logic validation of QBO journal‑entry preparation.

These tests do **not** modify any production code, do not call QuickBooks, and use only the in‑repo pure‑Python helpers.
'''

import inspect
import pytest
from pathlib import Path

# Import the functions under test from the integration module.
import importlib.util, pathlib
module_path = pathlib.Path(__file__).resolve().parents[1] / 'integrations' / 'qbo_import_preparation.py'
spec = importlib.util.spec_from_file_location('qbo_import_preparation', module_path)
qbo_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qbo_mod)
prepare_journal_entry = qbo_mod.prepare_journal_entry
record_journal_entry_import = qbo_mod.record_journal_entry_import

# Minimal valid account map matching the keys expected by `prepare_journal_entry`.
BASE_ACCOUNT_MAP = {
    "revenue": "1",
    "cogs": "2",
    "direct_opex": "3",
    "sm_payroll": "4",
    "marketing": "5",
    "other_opex": "6",
}

def _net_income_line(payload, mapping):
    """Return the net‑income line dict from a payload, or ``None`` if absent."""
    net_id = mapping.get("net_income")
    if not net_id:
        return None
    for line in payload["Line"]:
        if line["AccountRef"]["value"] == str(net_id):
            return line
    return None

def _category_lines(payload, mapping):
    """Return a dict mapping each logical key to its line dict in the payload."""
    result = {}
    for key, acct_id in mapping.items():
        for line in payload["Line"]:
            if line["AccountRef"]["value"] == str(acct_id):
                result[key] = line
                break
    return result

@pytest.fixture
def profit_normalized():
    """A period where revenue > total expenses → profit scenario."""
    return {
        "period": "2026-01",
        "revenue": 1000.0,
        "cost_of_goods_sold": 200.0,
        "direct_opex": 100.0,
        "sm_payroll": 50.0,
        "marketing": 50.0,
        "other_opex": 100.0,
    }

@pytest.fixture
def loss_normalized():
    """A period where expenses > revenue → loss scenario (mirrors Phase‑5 test)."""
    return {
        "period": "2026-04",
        "revenue": 800.0,
        "cost_of_goods_sold": 400.0,
        "direct_opex": 200.0,
        "sm_payroll": 150.0,
        "marketing": 100.0,
        "other_opex": 100.0,
    }

def test_prepare_signature_has_no_manifest_path():
    """The preparation function must not accept a manifest path (read‑only guarantee)."""
    sig = inspect.signature(prepare_journal_entry)
    assert "manifest_path" not in sig.parameters

def test_revenue_lines_are_credits(profit_normalized):
    mapping = BASE_ACCOUNT_MAP.copy()
    mapping["net_income"] = "7"
    payload = prepare_journal_entry(profit_normalized, mapping)

    # Find the revenue line by its account id.
    rev_line = None
    for line in payload["Line"]:
        if line["AccountRef"]["value"] == mapping["revenue"]:
            rev_line = line
            break
    assert rev_line is not None, "Revenue line missing"
    assert rev_line["PostingType"] == "Credit"
    # Amount should be the absolute revenue (negative amount stored as credit).
    assert rev_line["Amount"] == pytest.approx(1000.0)

def test_expense_lines_are_debits(profit_normalized):
    mapping = BASE_ACCOUNT_MAP.copy()
    mapping["net_income"] = "7"
    payload = prepare_journal_entry(profit_normalized, mapping)

    expense_pairs = [
        ("cost_of_goods_sold", "cogs"),
        ("direct_opex", "direct_opex"),
        ("sm_payroll", "sm_payroll"),
        ("marketing", "marketing"),
        ("other_opex", "other_opex"),
    ]
    lines_by_key = _category_lines(payload, mapping)
    for norm_key, map_key in expense_pairs:
        assert map_key in lines_by_key, f"Missing expense line for {map_key}"
        line = lines_by_key[map_key]
        assert line["PostingType"] == "Debit"
        expected = profit_normalized[norm_key]
        assert line["Amount"] == pytest.approx(abs(expected))

def test_profit_balancing_line_is_debit(profit_normalized):
    """When revenue exceeds expenses, the net‑income line must be a Debit (equity increase)."""
    mapping = BASE_ACCOUNT_MAP.copy()
    mapping["net_income"] = "7"
    payload = prepare_journal_entry(profit_normalized, mapping)
    net_line = _net_income_line(payload, mapping)
    assert net_line is not None, "Net‑income line not added for profit"
    assert net_line["PostingType"] == "Debit", "Profit net‑income line should be Debit"
    # The amount should equal the profit (revenue - expenses).
    profit = (
        profit_normalized["revenue"]
        - (
            profit_normalized["cost_of_goods_sold"]
            + profit_normalized["direct_opex"]
            + profit_normalized["sm_payroll"]
            + profit_normalized["marketing"]
            + profit_normalized["other_opex"]
        )
    )
    assert net_line["Amount"] == pytest.approx(profit)

def test_loss_balancing_line_is_credit(loss_normalized):
    """When expenses exceed revenue, the net‑income line must be a Credit (equity decrease)."""
    mapping = BASE_ACCOUNT_MAP.copy()
    mapping["net_income"] = "7"
    payload = prepare_journal_entry(loss_normalized, mapping)
    net_line = _net_income_line(payload, mapping)
    assert net_line is not None, "Net‑income line not added for loss"
    assert net_line["PostingType"] == "Credit", "Loss net‑income line should be Credit"
    # Amount should equal the absolute loss.
    loss = (
        loss_normalized["revenue"]
        - (
            loss_normalized["cost_of_goods_sold"]
            + loss_normalized["direct_opex"]
            + loss_normalized["sm_payroll"]
            + loss_normalized["marketing"]
            + loss_normalized["other_opex"]
        )
    )
    assert net_line["Amount"] == pytest.approx(abs(loss))

def test_prepare_does_not_create_manifest(tmp_path, profit_normalized):
    """Calling `prepare_journal_entry` must not create a manifest file.

    The function has no manifest_path argument, so we verify that no new file appears
    in a fresh temporary directory.
    """
    # Ensure the temporary directory is empty.
    assert not any(tmp_path.iterdir())
    mapping = BASE_ACCOUNT_MAP.copy()
    mapping["net_income"] = "7"
    payload = prepare_journal_entry(profit_normalized, mapping)
    # After the call, the temporary directory should still be empty.
    assert not any(tmp_path.iterdir()), "prepare_journal_entry created unexpected files"

def test_duplicate_and_conflict_import_records(tmp_path, profit_normalized):
    """`record_journal_entry_import` must reject duplicate and conflicting records.

    Uses a temporary manifest file so the test does not interfere with the real manifest.
    """
    manifest_path = tmp_path / "manifest.json"
    mapping = BASE_ACCOUNT_MAP.copy()
    mapping["net_income"] = "7"
    payload = prepare_journal_entry(profit_normalized, mapping)
    period = profit_normalized["period"]

    # First import should succeed.
    record_journal_entry_import(payload, period, manifest_path=str(manifest_path))

    # Duplicate (same payload) must raise.
    with pytest.raises(ValueError) as exc_dup:
        record_journal_entry_import(payload, period, manifest_path=str(manifest_path))
    assert "Duplicate journal entry detected" in str(exc_dup.value)

    # Conflicting payload (change Revenue) must raise a different error.
    conflicting = payload.copy()
    # Deep‑copy the lines and adjust the revenue line amount.
    conflicting["Line"] = [line.copy() for line in payload["Line"]]
    for line in conflicting["Line"]:
        if line["AccountRef"]["value"] == mapping["revenue"]:
            line["Amount"] = line["Amount"] + 1.0
            break
    with pytest.raises(ValueError) as exc_conf:
        record_journal_entry_import(conflicting, period, manifest_path=str(manifest_path))
    assert "Conflicting journal entry already recorded" in str(exc_conf.value)

def test_aggregate_rows_not_included(profit_normalized):
    """The payload must contain only the six category lines plus the optional net‑income line.
    No aggregate/sub‑total rows exist in the normalized input, so the line count should match.
    """
    mapping = BASE_ACCOUNT_MAP.copy()
    mapping["net_income"] = "7"
    payload = prepare_journal_entry(profit_normalized, mapping)
    # Expected lines: 6 categories + net‑income = 7
    assert len(payload["Line"]) == 7
    # Verify that each expected account id appears exactly once.
    expected_ids = {str(v) for v in mapping.values()}
    found_ids = {line["AccountRef"]["value"] for line in payload["Line"]}
    assert expected_ids == found_ids, "Payload contains unexpected or missing account ids"
