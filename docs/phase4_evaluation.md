# Phase 4 Evaluation Guide

This document describes how to run the regression suite for Phase 4 and how to interpret its output.

## Repeatable regression command

```powershell
\.venv-mcp\Scripts\python.exe -m pytest -q tests/test_golden_evals.py
```

Running the test invokes `scripts/run_golden_evals.py`, which:

1. Generates synthetic financial fixtures.
2. Produces a markdown report for each case under `reports/golden_cases/<case_id>/report.md`.
3. Evaluates four dimensions per case (numeric correctness, completeness, evidence support, commentary quality) against expectations defined in `evals/golden_cases.yaml`.
4. Writes `reports/golden_cases/golden_evaluation_results.json` and `reports/golden_cases/golden_evaluation_summary.md`.

## Interpreting the test results

- **`pytest` exit code 0** – All cases matched their expected outcomes; the evaluation suite passes.
- **Non‑zero exit code** – One or more cases did not meet expectations. The failing case(s) will be listed in the pytest output. Inspect the JSON results file for detailed numeric‑comparison diagnostics.

## Quick check of the JSON results

You can also inspect the JSON directly:

```bash
cat reports/golden_cases/golden_evaluation_results.json
```

Each entry contains:

- `id`: case identifier
- `numeric_correctness`, `completeness`, `evidence_support`, `commentary_quality`: actual PASS/FAIL booleans
- `expected`: the booleans defined in the YAML
- `overall_pass`: true when all actual values match the expected ones

Use this information to pinpoint mismatches.
