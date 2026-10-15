import json
import pathlib
import importlib.util

# Load MCP server module to access query_journal_entries
repo_root = pathlib.Path(__file__).resolve().parents[1]
module_path = repo_root / 'integrations' / 'qbo_mcp_server.py'
spec = importlib.util.spec_from_file_location('qbo_mcp_server', str(module_path))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Query for Jan 2025 entries
entries = mod.query_journal_entries('2025-01-01', '2025-01-01')
print('January 2025 entries found:', len(entries))
for entry in entries:
    entry_id = entry.get('Id') or entry.get('id') or entry.get('JournalEntryId')
    print('Entry ID:', entry_id)
