import json
import pathlib
import importlib.util

repo_root = pathlib.Path(__file__).resolve().parents[1]
# Load MCP server module
module_path = repo_root / 'integrations' / 'qbo_mcp_server.py'
spec = importlib.util.spec_from_file_location('qbo_mcp_server', str(module_path))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Load manifest
manifest_path = repo_root / 'reports' / 'import_manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
periods = manifest.get('imported', [])

results = []
for period in periods:
    start = f"{period}-01"
    end = start  # same day for the whole month query (QuickBooks query uses date range inclusive)
    try:
        entries = mod.query_journal_entries(start, end)
    except Exception as e:
        print(f"Error querying period {period}: {e}")
        entries = []
    ids = [entry.get('Id') or entry.get('id') for entry in entries]
    results.append((period, len(entries), ids))

# Print verification summary
print('Verification of Live QuickBooks JournalEntries:')
for period, count, ids in results:
    print(f"Period {period}: {count} entry(ies) found; IDs: {ids}")

# Check manifest vs live data
missing = [p for p, cnt, _ in results if cnt == 0]
if missing:
    print('Missing entries for periods:', missing)
else:
    print('All manifest periods have at least one matching QuickBooks entry.')
