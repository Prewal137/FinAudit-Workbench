"""Tests for is_duplicate_journal_entry helper.

These tests verify the canonical fingerprinting and fail‑closed behaviour.
"""

import copy
import pytest

import importlib.util, pathlib
module_path = pathlib.Path(__file__).resolve().parents[1] / 'integrations' / 'qbo_mcp_server.py'
spec = importlib.util.spec_from_file_location('qbo_mcp_server', module_path)
qbo_mcp_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qbo_mcp_server)


def make_payload():
    """Return a simple payload with two lines.
    Revenue (Credit) on account 1, expense (Debit) on account 2.
    """
    return {
        "TxnDate": "2025-01-01",
        "Line": [
            {"Amount": 100.0, "PostingType": "Credit", "AccountRef": {"value": "1"}},
            {"Amount": 100.0, "PostingType": "Debit", "AccountRef": {"value": "2"}},
        ],
    }


def test_duplicate_detected(monkeypatch):
    payload = make_payload()
    # Create an entry with lines in reverse order – should still be duplicate.
    entry = copy.deepcopy(payload)
    entry["Line"] = list(reversed(entry["Line"]))
    monkeypatch.setattr(qbo_mcp_server, "query_journal_entries", lambda s, e: [entry])
    assert qbo_mcp_server.is_duplicate_journal_entry(payload, "2025-01") is True


def test_no_duplicate(monkeypatch):
    payload = make_payload()
    monkeypatch.setattr(qbo_mcp_server, "query_journal_entries", lambda s, e: [])
    assert qbo_mcp_server.is_duplicate_journal_entry(payload, "2025-01") is False


def test_query_failure(monkeypatch):
    payload = make_payload()
    def raise_err(s, e):
        raise RuntimeError("API failure")
    monkeypatch.setattr(qbo_mcp_server, "query_journal_entries", raise_err)
    with pytest.raises(RuntimeError, match="API failure"):
        qbo_mcp_server.is_duplicate_journal_entry(payload, "2025-01")


def test_malformed_entry(monkeypatch):
    payload = make_payload()
    # Entry missing required fields (no AccountRef, PostingType)
    malformed = {"TxnDate": "2025-01-01", "Line": [{"Amount": 100.0}]}
    monkeypatch.setattr(qbo_mcp_server, "query_journal_entries", lambda s, e: [malformed])
    with pytest.raises(ValueError):
        qbo_mcp_server.is_duplicate_journal_entry(payload, "2025-01")


def test_equivalent_structure(monkeypatch):
    payload = make_payload()
    entry = copy.deepcopy(payload)
    # Add extra unrelated fields.
    entry["Id"] = "123"
    entry["Meta"] = {"source": "quickbooks"}
    monkeypatch.setattr(qbo_mcp_server, "query_journal_entries", lambda s, e: [entry])
    assert qbo_mcp_server.is_duplicate_journal_entry(payload, "2025-01") is True
