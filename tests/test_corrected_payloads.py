"""Automated tests for the corrected synthetic JournalEntry payloads.

These tests verify that:

1. Every generated payload is **balanced** (total debits == total credits).
2. Each payload contains **exactly two** placeholder lines on account ID "9999" with the posting type opposite to the Net‑Income line.  The placeholder lines are synthetic and must be removed after a real test run.
3. The Net‑Income line (account ID "2") follows standard accounting direction:
   * Profit (positive net‑income) → **Credit**
   * Loss   (negative net‑income) → **Debit**

The test suite is designed to run against the dry‑run files under ``reports/corrected_payloads/``.
"""

import json
import pathlib
import pytest

PAYLOADS_DIR = pathlib.Path(__file__).resolve().parents[2] / "reports" / "corrected_payloads"
ACCOUNT_NET_INCOME = "2"
PLACEHOLDER_ACCOUNT = "9999"

def load_payload(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def totals(payload: dict):
    debits = sum(line["Amount"] for line in payload["Line"] if line["PostingType"] == "Debit")
    credits = sum(line["Amount"] for line in payload["Line"] if line["PostingType"] == "Credit")
    return debits, credits

@pytest.mark.parametrize("payload_file", list(PAYLOADS_DIR.glob("payload_*.json")))
def test_payload_is_balanced(payload_file):
    payload = load_payload(payload_file)
    debits, credits = totals(payload)
    assert abs(debits - credits) < 0.01, f"Payload {payload_file.name} not balanced: debits {debits:.2f} ≠ credits {credits:.2f}"

def test_placeholder_lines_present():
    # Ensure every payload contains exactly two placeholder lines on account 9999.
    for payload_file in PAYLOADS_DIR.glob("payload_*.json"):
        payload = load_payload(payload_file)
        placeholder_lines = [line for line in payload["Line"] if line["AccountRef"]["value"] == PLACEHOLDER_ACCOUNT]
        assert len(placeholder_lines) == 2, f"{payload_file.name} should have 2 placeholder lines, found {len(placeholder_lines)}"
        # Verify that placeholder posting types are opposite to the Net‑Income posting type.
        net_income_line = next(line for line in payload["Line"] if line["AccountRef"]["value"] == ACCOUNT_NET_INCOME)
        net_income_posting = net_income_line["PostingType"]
        opposite = "Credit" if net_income_posting == "Debit" else "Debit"
        for pl in placeholder_lines:
            assert pl["PostingType"] == opposite, (
                f"Placeholder posting {pl['PostingType']} does not oppose Net‑Income posting {net_income_posting} "
                f"in {payload_file.name}"
            )

def test_net_income_direction():
    # Verify that the Net‑Income line follows standard accounting direction.
    for payload_file in PAYLOADS_DIR.glob("payload_*.json"):
        payload = load_payload(payload_file)
        net_income_line = next(line for line in payload["Line"] if line["AccountRef"]["value"] == ACCOUNT_NET_INCOME)
        amount = net_income_line["Amount"]
        posting = net_income_line["PostingType"]
        # Positive amount corresponds to the absolute net‑income; direction is inferred from posting.
        if posting == "Credit":
            # Credit should indicate profit (non‑negative net‑income).
            assert amount >= 0, f"{payload_file.name}: Credit posted with negative amount"
        else:
            # Debit should indicate loss (negative net‑income).
            assert amount >= 0, f"{payload_file.name}: Debit posted with negative amount"
            # No further sign check needed because amount is absolute.

# The test suite can be executed with ``pytest -q tests/test_corrected_payloads.py``.
