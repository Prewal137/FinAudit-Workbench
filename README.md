# FinAudit‑Workbench

## Overview
FinAudit‑Workbench is a Python‑based analytics pipeline that processes a single Excel workbook of management‑account financial statements, validates the data, computes deterministic monthly and trailing‑12‑month metrics, and produces an evidence‑backed commentary report.  The repository also provides a **read‑only** QuickBooks Online (QBO) sandbox integration for live‑data reporting and a **golden‑evaluation suite** that validates the pipeline against synthetic edge‑case fixtures.

---

## Assessment Deliverables (actual file paths)
| Deliverable | Path (relative to repository root) |
|-------------|------------------------------------|
| QuickBooks sandbox connection (read‑only) | `integrations/qbo_mcp_server.py` (reads credentials from private `.env`) |
| Placeholder environment file | `.env.example` |
| Claude financial‑trend‑analysis skill | `.claude/skills/financial‑trend‑analysis/SKILL.md` |
| Architecture note (≈1 page) | `docs/architecture_note.md` |
| Workbook analysis runner | `run_financial_analysis.py` |
| Golden‑evaluation driver (default & extended) | `scripts/run_golden_evals.py` |
| Golden‑evaluation case definitions | `evals/golden_cases.yaml` |
| Golden‑evaluation evidence (reports & JSON) | `reports/golden_cases/` |
| Candidate payloads (Phase 5) | `reports/candidate_payloads/` |
| Corrected payloads (sign‑handling) | `reports/corrected_payloads/` |
| Supplied workbook | `data/input/ABC Inc - Financial Statements.xlsx` |
| Test suite | `tests/` (112 passed, 2 skipped) |

---

## Repository Structure (key directories)
```
FinAudit-Workbench/
├─ data/input/                     # Excel workbook (single .xlsx file)
├─ src/                            # Core ingestion, validation, metrics, reporting
├─ integrations/                   # QuickBooks MCP wrapper (read‑only)
├─ scripts/                        # CLI utilities
│   ├─ run_golden_evals.py         # Golden‑evaluation driver (default + --extended)
│   ├─ live_qb_financial_trend_report.py  # Read‑only QBO report generation
│   ├─ post_qbo_journal_entries.py       # Sandbox importer (dry‑run by default; --confirm‑write to POST)
│   └─ … (other helper scripts)
├─ reports/                        # Generated artefacts
│   ├─ financial‑trend‑analysis_report.md   # Workbook‑derived report
│   ├─ financial‑trend‑analysis_live_qb_report.md   # Live QBO report (post‑processed)
│   ├─ qbo_profit_and_loss_2025‑01‑01_to_2025‑01‑31.json
│   ├─ … (one JSON per month Jan 2025 – Jun 2026)
│   ├─ golden_cases/                # Per‑case markdown reports & summary JSON
│   └─ … (payloads, data profiles, validation reports)
├─ docs/                           # Documentation, architecture note
├─ tests/                          # Pytest suite (112 passed, 2 skipped)
├─ .claude/                        # Claude skill definition & command files
├─ .gitignore
├─ .env.example                    # Example keys – real `.env` is private
└─ README.md
```

---

## Prerequisites & Clean Setup (Windows PowerShell)
1. **Install Python 3.13** (or any recent 3.x version) and ensure `python` is on your `PATH`.
2. **Create a fresh virtual environment** (do **not** reuse any existing `.venv‑mcp` folder):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1   # activate the env
   ```
3. **Install required third‑party packages**:
   ```powershell
   pip install pyyaml openpyxl httpx python-dotenv
   ```
   * `pyyaml` – YAML parsing for the golden‑evaluation suite.
   * `openpyxl` – Excel workbook ingestion.
   * `httpx` – HTTP client used by the QBO MCP wrapper.
   * `python-dotenv` – Loads the private `.env` file for QuickBooks credentials.
4. **(Optional) Install test dependencies** – the test suite uses only the standard library and the packages above, so no extra steps are needed.

---

## Running the Workbook Analysis
```powershell
python run_financial_analysis.py
```
This script:
* Locates the single workbook under `data/input/`.
* Loads it via `src.ingestion`, validates it, calculates metrics, and writes `reports/financial‑trend‑analysis_report.md`.
* Generates `reports/data_profile.json` and `reports/validation_report.json` for completeness.
* Executes the verification script (`scripts/verify_workbook.py`).
* Runs the full pytest suite and prints its summary.

---

## Golden‑Evaluation Suite
* **Default run (6 cases):**
  ```powershell
  python scripts/run_golden_evals.py
  ```
* **Extended run (12 cases):**
  ```powershell
  python scripts/run_golden_evals.py --extended
  ```
Both commands write:
* `reports/golden_cases/golden_evaluation_results.json` – machine‑readable results.
* `reports/golden_cases/golden_evaluation_summary.md` – human‑readable table.
All cases currently **PASS** (the summary confirms PASS for every required dimension).

---

## Test Suite
```powershell
python -m pytest -q
```
Result (as of the latest verification):
```
112 passed, 2 skipped
```
The suite covers ingestion, validation, metric calculation, the golden‑evaluation driver, and the QuickBooks MCP wrapper.

---

## QuickBooks Sandbox Integration (Read‑Only)
### Reporting (live data)
* `scripts/live_qb_financial_trend_report.py` fetches monthly Profit‑and‑Loss reports from the QBO sandbox via the read‑only MCP wrapper (`integrations/qbo_mcp_server.py`).
* The script generates `reports/financial‑trend‑analysis_live_qb_report.md` and then post‑processes it to embed:
  * Workbook‑comparison validation status (covers Jan 2025 & Feb 2025).
  * Discrepancy details for operating‑expense/operating‑income differences:
    * Jan 2025: **$112,833.23**
    * Feb 2025: **$112,110.19**
  * A December 2025 anomaly (Operating Income = -$273,929.07, Net Income = $534,551.41) flagged for reviewer investigation.
* **Live QBO data**: JSON files for each month (Jan 2025 – Jun 2026) are present under `reports/` (e.g., `qbo_profit_and_loss_2025‑01‑01_to_2025‑01‑31.json`). These confirm that **18 monthly periods** have been retrieved.

### Import Utility (sandbox write‑capable)
* `scripts/post_qbo_journal_entries.py` can import prepared JSON payloads into QuickBooks.
* By default it runs in **dry‑run** mode (no POSTs). Use the `--confirm-write` flag to perform real imports.
* The utility performs extensive validation, duplicate detection (via `is_duplicate_journal_entry`), and maintains an import manifest (`reports/import_manifest.json`).
* It includes a check that the company information reports an environment of "sandbox" before proceeding, but this check relies on a hard‑coded value in the MCP wrapper and does not independently verify that the supplied credentials target a sandbox. Consequently, writes will be sent to whatever company the credentials configure, provided the environment field is "sandbox" (which the wrapper reports unconditionally).
* **Phase 6** of the project used this script to import **18 monthly periods** (Jan 2025 – Jun 2026) into the sandbox; the corresponding manifest (now archived as `reports/import_manifest.bak`) records those periods.
* This import capability is **not** used by the default analysis workflow and is deliberately isolated from the read‑only reporting path.

---

## Security & Limitations
* **Credential handling** – Real credentials live only in a private `.env` file (ignored by Git). Never commit or expose this file.
* The QBO integration is **read‑only** unless `post_qbo_journal_entries.py` is invoked with `--confirm‑write`; even then it will write to whatever company the provided credentials describe, though the script checks that the reported environment is "sandbox" (a hard‑coded value).
* **Balance‑sheet data** is not retrieved by the current QBO wrapper, so liquidity analysis and balance‑sheet reconciliation are unavailable.
* **TTM metrics** are generated only when a full 12‑month consecutive window exists in the source data.
* **Multi‑client isolation** – The architecture note proposes containerised, per‑tenant isolation, but this is **future work only**; the current implementation is single‑tenant.
* All monetary figures are rounded to two decimal places; minor rounding differences may appear.

---

*Prepared for RE Financial Services – AI Solutions Builder assessment.*