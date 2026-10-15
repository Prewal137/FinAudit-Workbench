# Architecture Note – FinAudit‑Workbench (AI Solutions Builder Assessment)

**Prepared for RE Financial Services Private Limited**

---

### A. Project Structure and Workflow

- **`src/`** – Core deterministic library. It contains:
  - `ingestion.py` – loads the single Excel workbook (`data/input/*.xlsx`) into strongly‑typed Income‑Statement and Balance‑Sheet objects.
  - `validation.py` – rule‑based checks (formula integrity, balance‑sheet reconciliation, duplicate‑account detection) and produces a `ValidationReport` with a `can_proceed_to_downstream` flag.
  - `metrics.py` – pure functions that compute monthly `MonthlyMetrics` and trailing‑12‑month (`TTM`) metrics (revenue, margins, expense categories, MoM changes).
  - `reporting.py` – utilities for data profiling and markdown‑report generation.

- **`scripts/`** – Orchestration and evaluation utilities:
  - `run_financial_analysis.py` – discovers the workbook, runs ingestion → validation → metrics → markdown report (`reports/financial‑trend‑analysis_report.md`).
  - `run_golden_evals.py` – builds synthetic fixtures, runs the golden‑evaluation driver and writes per‑case markdown reports under `reports/golden_cases/`.
  - `live_qb_financial_trend_report.py` – uses the QuickBooks MCP wrapper to fetch live Profit‑and‑Loss data, builds the same metrics, and writes `reports/financial‑trend‑analysis_live_qb_report.md`.
  - Additional scripts (`post_qbo_journal_entries.py`, `verify_live_entries.py`, etc.) support the stretch‑goal import of workbook‑derived data into the QuickBooks developer sandbox.

- **`.claude/skills/financial-trend-analysis/SKILL.md`** – Version‑controlled Claude skill that encapsulates the end‑to‑end workflow. When the `/financial‑trend‑analysis` slash command is invoked, Claude:
  1. Resolves the repository root.
  2. Locates the workbook.
  3. Calls the deterministic pipeline (`src/` modules) to obtain validated metrics.
  4. Generates the markdown report.
  5. Executes the citation‑verification script and the full pytest suite.
  6. Summarises execution results for the user.
  Claude does **not** perform any numeric computation itself; it orchestrates and presents evidence‑backed commentary.

- **`.claude/commands/`** – Developer‑focused command definitions (e.g., `/run‑golden‑evals`) that invoke the corresponding scripts. They live alongside the skill definitions and are version‑controlled.

- **`integrations/`** – QuickBooks MCP wrapper (`qbo_mcp_server.py`). Provides read‑only tools (`get_company_info`, `get_profit_and_loss`, `query_journal_entries`) that retrieve live sandbox data via OAuth‑2.0.

- **`evals/`** and **`tests/`** –
  - `evals/golden_cases.yaml` defines 13 golden‑evaluation cases with expected boolean outcomes for the five grading dimensions (numeric, completeness, evidence, commentary, plus optional TTM/validation flags).
  - `evals/README.md` explains how to run the suite (`python scripts/run_golden_evals.py`).
  - The pytest suite (`tests/`) exercises ingestion, validation, metrics, the golden‑evaluation driver, and the QBO wrapper, providing regression protection.

- **`data/`** – Holds the single management‑account workbook (`data/input/*.xlsx`).

- **`reports/`** – Runtime artefacts: deterministic workbook report, live QuickBooks report, golden‑case markdown reports, JSON result summaries, and data‑profile artefacts.

**Workflow** – The workbook is ingested → validation gate evaluated → deterministic metrics calculated → markdown report generated. The Claude skill triggers this pipeline, then optionally runs the live‑QBO variant for comparison. Golden‑evaluation cases verify that the deterministic outputs meet the expected grading criteria, and the full pytest suite guards against regressions.

---

### B. QuickBooks Connection and Hosting Choice

The project uses the **QuickBooks Online developer sandbox** in **read‑only** mode. `integrations/qbo_mcp_server.py` implements OAuth 2.0 token refresh (credentials stored locally in a `.env` file) and exposes only `GET` endpoints (`get_company_info`, `get_profit_and_loss`, `query_journal_entries`). This choice provides:

- Rapid, safe development without risk to production accounting data.
- A deterministic data source that can be refreshed on demand.
- No write capability in the analysis path, preserving sandbox integrity.

**Why not production or direct DB access?**
- Production APIs would expose live client ledgers to a prototype environment, violating confidentiality.
- Direct database access is not supported by QuickBooks Online and would bypass the API’s security model.

**Completed stretch goal** – The workbook‑derived monthly entries for **January 2025 through June 2026** were imported into the developer sandbox (via the import scripts). Verification (`scripts/verify_live_entries.py`) confirmed that all 18 periods exist in QuickBooks. The live‑data pipeline (`live_qb_financial_trend_report.py`) retrieved 18 Profit‑and‑Loss reports and produced `reports/financial‑trend‑analysis_live_qb_report.md`.

- **Comparison** – For January and February 2025 the live and workbook metrics match on revenue, gross profit, and net income (≤ $0.01 tolerance). Total operating expenses and operating income differ by **$112,833.23** (Jan) and **$112,110.19** (Feb); the cause is not established in the code and is reported as a discrepancy.
- **December 2025 anomaly** – Positive net income ($534,551.41) with negative operating income (‑$273,929.07) is flagged for reviewer investigation.

The import scripts are distinct from the read‑only MCP analysis path; they write journal entries to the sandbox, while the live‑report script only reads.

---

### C. Credentials, Hosting, and Security

**Current prototype** –
- OAuth client ID, secret, realm ID, and refresh token are loaded from a local `.env` file (ignored by Git). The wrapper refreshes the access token and rotates the refresh token back to the same file.
- All MCP tools are read‑only; no write‑back to QuickBooks occurs from the analysis pipeline.
- The import scripts that write journal entries operate separately and also rely on the same `.env` credentials.

**Proposed team‑hosted architecture** –
1. **Containerised service** – The deterministic pipeline runs inside a Docker (or Cloud‑Run) container behind an HTTPS/TLS‑terminated reverse proxy.
2. **Managed secret storage** – OAuth credentials stored in a cloud secret manager (AWS Secrets Manager, Azure Key Vault, etc.) and injected at container start; token rotation updates the secret store, not a local file.
3. **Authentication & authorization** – API callers present a signed JWT issued by an internal identity provider; the service validates the token, extracts the tenant ID, and enforces least‑privilege scopes.
4. **Audit logging** – Every request logs tenant ID, endpoint, timestamp, and outcome to a secure log aggregation service.
5. **Secure artefact storage** – Generated reports and temporary files are written to tenant‑scoped prefixes in object storage (e.g., S3, Azure Blob) with server‑side encryption.
6. **Isolation by design** – No shared in‑process memory across tenants; each request works on isolated filesystem or cloud‑storage paths.

The above controls are **proposed**; they are not present in the current local prototype.

---

### D. Scaling to Ten Clients and Data Isolation

To support ten (or more) tenants the system would evolve as follows:

- **Per‑tenant credentials** – Each client receives its own QuickBooks OAuth client/realm identifiers stored securely in the secret manager.
- **Tenant‑scoped API layer** – All MCP calls include the tenant ID; the wrapper validates that the requested realm matches the tenant’s configuration.
- **Isolated uploads and reports** – Workbooks are uploaded to tenant‑specific storage prefixes (e.g., `s3://fin‑audit/tenant‑01/input/`). Generated artefacts (`reports/…`) are stored under the same prefix, preventing cross‑tenant visibility.
- **No cross‑tenant prompting** – Claude’s skill text and the version‑controlled workflow contain no client‑specific data; prompts never contain another client’s identifiers.
- **Concurrent job handling** – A job‑queue (e.g., Cloud Tasks) schedules each tenant’s analysis independently, ensuring CPU/memory isolation.
- **Testing for isolation** – Automated integration tests would assert that a request using tenant‑A’s credentials cannot retrieve tenant‑B’s data, providing regression safety.

These isolation mechanisms are **design proposals**; the current repository demonstrates a single‑tenant prototype.

---

### E. Validation and Operational Status

- The project includes a **golden‑evaluation suite** (`evals/golden_cases.yaml`) with 13 cases covering numeric accuracy, completeness, evidence support, commentary quality, and optional TTM/validation flags. Running `python scripts/run_golden_evals.py` generates per‑case markdown reports and a summary (`reports/golden_cases/golden_evaluation_summary.md`).
- The **pytest suite** (`pytest -q`) currently reports **112 passed, 2 skipped** confirming deterministic ingestion, validation, metric calculation, golden‑evaluation driver, and the QBO wrapper.
- **Limitations** – The live‑vs‑workbook comparison reveals a discrepancy in total operating expenses and operating income for Jan/Feb 2025, and balance‑sheet data is not retrieved from QuickBooks, so liquidity analysis is unavailable.
- All other sections of the generated reports (revenue, gross profit, margins, TTM where complete) satisfy the skill’s evidence‑grounded requirements.

---

*Prepared by the FinAudit‑Workbench team for RE Financial Services Private Limited – architecture note (approximately one page).*