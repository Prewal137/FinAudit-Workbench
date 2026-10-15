# Phase 4 Golden Evaluation

## Running the evaluation

```bash
python scripts/run_golden_evals.py
```

The script generates per‑case markdown reports under `reports/golden_cases/<case_id>/report.md`, a JSON results file `reports/golden_cases/golden_evaluation_results.json`, and a human‑readable summary `reports/golden_cases/golden_evaluation_summary.md`.

## Expected outcomes

Each case defines the expected pass/fail status for the four grading dimensions (numeric correctness, completeness, evidence support, commentary quality) in `evals/golden_cases.yaml`. The suite **passes** when every case's actual results match its expected outcomes, yielding an exit code of 0.

## Interpretation of results

- **PASS** in the summary indicates the case behaved as defined.
- **FAIL** flags a mismatch between actual and expected outcomes and results in a non‑zero exit code.
- Detailed numeric comparison data are available in the JSON results file.
