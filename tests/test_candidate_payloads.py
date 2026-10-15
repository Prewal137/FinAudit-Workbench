import json
import pathlib
import pytest

CANDIDATE_DIR = pathlib.Path(__file__).resolve().parents[2] / "reports" / "candidate_payloads"
ACCOUNT_NET_INCOME = "2"
PLACEHOLDER_ACCOUNT = "9999"

def load_payload(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def totals(payload: dict):
    debits = sum(l["Amount"] for l in payload["Line"] if l["PostingType"] == "Debit")
    credits = sum(l["Amount"] for l in payload["Line"] if l["PostingType"] == "Credit")
    return debits, credits

@pytest.mark.parametrize("payload_file", list(CANDIDATE_DIR.glob("payload_*.json")))
def test_candidate_payload_balanced(payload_file):
    payload = load_payload(payload_file)
    debits, credits = totals(payload)
    assert abs(debits - credits) < 0.01, f"{payload_file.name} not balanced: debits {debits:.2f} != credits {credits:.2f}"

def test_placeholder_and_equity_effect():
    for payload_file in CANDIDATE_DIR.glob("payload_*.json"):
        payload = load_payload(payload_file)
        # net_income line
        net_income_lines = [l for l in payload["Line"] if l["AccountRef"]["value"] == ACCOUNT_NET_INCOME]
        assert len(net_income_lines) == 1, f"{payload_file.name}: expected 1 net_income line"
        net_line = net_income_lines[0]
        net_amount = net_line["Amount"]
        net_posting = net_line["PostingType"]
        # placeholder lines
        placeholder_lines = [l for l in payload["Line"] if l["AccountRef"]["value"] == PLACEHOLDER_ACCOUNT]
        assert len(placeholder_lines) == 2, f"{payload_file.name}: expected 2 placeholder lines"
        # each placeholder line amount must equal net_income amount
        for pl in placeholder_lines:
            assert pl["Amount"] == net_amount, f"{payload_file.name}: placeholder amount {pl['Amount']} != net_income amount {net_amount}"
            # posting must be opposite to net_income posting
            expected = "Credit" if net_posting == "Debit" else "Debit"
            assert pl["PostingType"] == expected, f"{payload_file.name}: placeholder posting {pl['PostingType']} not opposite of net_income {net_posting}"

