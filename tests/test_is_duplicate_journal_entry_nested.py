import copy
import pytest
import importlib.util, pathlib

# Load the MCP server module.
module_path = pathlib.Path(__file__).resolve().parents[1] / 'integrations' / 'qbo_mcp_server.py'
spec = importlib.util.spec_from_file_location('qbo_mcp_server', module_path)
qbo_mcp_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qbo_mcp_server)


def make_nested_payload():
    """Payload using the new nested JournalEntryLineDetail structure."""
    return {
        "TxnDate": "2025-01-01",
        "Line": [
            {
                "Amount": 100.0,
                "DetailType": "JournalEntryLineDetail",
                "JournalEntryLineDetail": {
                    "PostingType": "Credit",
                    "AccountRef": {"value": "1"}
                }
            },
            {
                "Amount": 100.0,
                "DetailType": "JournalEntryLineDetail",
                "JournalEntryLineDetail": {
                    "PostingType": "Debit",
                    "AccountRef": {"value": "2"}
                }
            },
        ],
    }


def test_nested_duplicate(monkeypatch):
    payload = make_nested_payload()
    # Create a duplicate entry with lines reversed but same nested structure.
    entry = copy.deepcopy(payload)
    entry["Line"] = list(reversed(entry["Line"]))
    monkeypatch.setattr(qbo_mcp_server, "query_journal_entries", lambda s, e: [entry])
    assert qbo_mcp_server.is_duplicate_journal_entry(payload, "2025-01") is True


def test_legacy_vs_nested(monkeypatch):
    # Legacy payload (top‑level) and entry nested – should be considered duplicate.
    legacy = {
        "TxnDate": "2025-01-01",
        "Line": [
            {"Amount": 100.0, "PostingType": "Credit", "AccountRef": {"value": "1"}},
            {"Amount": 100.0, "PostingType": "Debit", "AccountRef": {"value": "2"}},
        ],
    }
    nested = make_nested_payload()
    monkeypatch.setattr(qbo_mcp_server, "query_journal_entries", lambda s, e: [nested])
    assert qbo_mcp_server.is_duplicate_journal_entry(legacy, "2025-01") is True
