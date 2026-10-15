"""Tests for manifest path handling and concurrency (A2 & A3)."""

import os
import json
import threading
import pathlib
import importlib.util
import pytest

module_path = pathlib.Path(__file__).resolve().parents[1] / "integrations" / "qbo_import_preparation.py"
spec = importlib.util.spec_from_file_location("qbo_import_preparation", module_path)
qbo_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qbo_mod)
record_journal_entry_import = qbo_mod.record_journal_entry_import

def _load_manifest(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def test_default_manifest_path(tmp_path, monkeypatch):
    # Ensure default env var is not set.
    monkeypatch.delenv("QBO_JOURNAL_MANIFEST", raising=False)
    # Determine expected default location (repo_root/reports/qbo_journal_manifest.json).
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    expected_path = repo_root / "reports" / "qbo_journal_manifest.json"
    # Remove file if it exists from previous runs.
    if expected_path.exists():
        expected_path.unlink()
    payload = {"TxnDate": "2026-01-01", "Line": []}
    record_journal_entry_import(payload, "2026-01")
    assert expected_path.is_file()
    # Clean up.
    expected_path.unlink()
    lock_path = str(expected_path) + ".lock"
    if os.path.exists(lock_path):
        os.remove(lock_path)

def test_relative_manifest_path(tmp_path, monkeypatch):
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    rel_path = "relative_manifest.json"
    expected_path = repo_root / rel_path
    if expected_path.exists():
        expected_path.unlink()
    payload = {"TxnDate": "2026-01-01", "Line": []}
    record_journal_entry_import(payload, "2026-01", manifest_path=rel_path)
    assert expected_path.is_file()
    # Clean up.
    expected_path.unlink()
    lock_path = str(expected_path) + ".lock"
    if os.path.exists(lock_path):
        os.remove(lock_path)

def test_absolute_manifest_path(tmp_path):
    abs_path = tmp_path / "abs_manifest.json"
    payload = {"TxnDate": "2026-01-01", "Line": []}
    record_journal_entry_import(payload, "2026-01", manifest_path=str(abs_path))
    assert abs_path.is_file()
    lock_path = str(abs_path) + ".lock"
    if os.path.exists(lock_path):
        os.remove(lock_path)

def test_concurrent_writes_different_periods(tmp_path):
    manifest_path = tmp_path / "conc_manifest.json"
    payload_template = {"TxnDate": "2026-01-01", "Line": []}
    periods = ["2026-01", "2026-02", "2026-03", "2026-04"]
    def worker(p):
        payload = payload_template.copy()
        record_journal_entry_import(payload, p, manifest_path=str(manifest_path))
    threads = [threading.Thread(target=worker, args=(p,)) for p in periods]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Load manifest and verify all periods are recorded.
    data = _load_manifest(str(manifest_path))
    entries = data.get("entries", {})
    assert set(entries.keys()) == set(periods)
    # Clean up lock file if any.
    lock_path = str(manifest_path) + ".lock"
    if os.path.exists(lock_path):
        os.remove(lock_path)
