import json
import pathlib
import importlib.util

# Load the MCP server module (contains is_duplicate_journal_entry)
repo_root = pathlib.Path(__file__).resolve().parents[1]
module_path = repo_root / 'integrations' / 'qbo_mcp_server.py'
spec = importlib.util.spec_from_file_location('qbo_mcp_server', str(module_path))
qbo_mcp_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qbo_mcp_server)

# Load the January payload (generated earlier)
payload_path = repo_root / 'reports' / 'balanced_payloads' / 'payload_2025-01.json'
payload = json.loads(payload_path.read_text(encoding='utf-8'))

# Mock query_journal_entries to return an empty list (no duplicates in sandbox)
qbo_mcp_server.query_journal_entries = lambda start, end: []

# Perform duplicate check
duplicate = qbo_mcp_server.is_duplicate_journal_entry(payload, '2025-01')
print(f'Duplicate detection result for 2025-01: {duplicate}')
