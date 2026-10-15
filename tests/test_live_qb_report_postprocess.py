"""Tests for the post‑processing of the live QuickBooks report.

The helper ``_update_report`` injected by ``scripts/live_qb_financial_trend_report.py``
adds validation‑status details and a December 2025 anomaly entry.
These tests verify that the function correctly rewrites the markdown sections.
"""

import os
import pathlib
import importlib.util

# Load the script module without executing its ``main`` function.
SCRIPT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "live_qb_financial_trend_report.py"))
_spec = importlib.util.spec_from_file_location("live_qb_financial_trend_report", SCRIPT_PATH)
_live_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_live_mod)


def test_update_report_injects_validation_and_anomaly(tmp_path: pathlib.Path):
    # Minimal report containing the two sections we will replace.
    report_content = """# Sample Report

## 2. Data Coverage and Validation Status

- Old placeholder content

## 9. Significant Anomalies

- No supported anomalies found for QuickBooks source.
"""
    report_file = tmp_path / "report.md"
    report_file.write_text(report_content, encoding="utf-8")

    # Call the private helper to rewrite the sections.
    _live_mod._update_report(report_file)

    updated = report_file.read_text(encoding="utf-8")

    # Validation‑status block should be present.
    assert "Workbook comparison performed for January and February 2025" in updated
    assert "January operating‑expense/operating‑income difference: $112,833.23" in updated
    assert "February operating‑expense/operating‑income difference: $112,110.19" in updated

    # December anomaly entry should be present.
    assert "December 2025" in updated
    assert "Operating Income = -$273,929.07" in updated
    assert "Net Income = $534,551.41" in updated
    assert "Reviewer investigation required" in updated
