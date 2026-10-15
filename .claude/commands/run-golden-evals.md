# /run-golden-evals

**Description**: Runs the Phase 4 golden‑evaluation suite and its focused regression test, then reports detailed results.

**Steps**:

```powershell
# 1. Verify we are in the expected project root
$expectedRoot = 'E:\FinAudit-Workbench'
if ((Get-Location).ProviderPath -ne $expectedRoot) {
    Write-Error "Project root mismatch. Expected $expectedRoot but got $((Get-Location).ProviderPath)."
    exit 1
}

# 2. Run the golden‑evaluation script
& ".venv-mcp\Scripts\python.exe" "scripts\run_golden_evals.py"
if (!$?) {
    Write-Error "Golden evaluation runner failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}

# 3. Run the focused regression test
& ".venv-mcp\Scripts\python.exe" "-m" "pytest" "-q" "tests\test_golden_evals.py"
if (!$?) {
    Write-Error "Regression test failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}

# 4. Summarize results
$resultsPath = Join-Path 'reports' 'golden_cases' 'golden_evaluation_results.json'
if (-Not (Test-Path $resultsPath)) {
    Write-Error "Result file not found at $resultsPath."
    exit 1
}
$results = Get-Content $resultsPath -Raw | ConvertFrom-Json

Write-Host "\n=== Golden Evaluation Summary ===\n"
foreach ($case in $results) {
    $id = $case.id
    $expected = $case.expected
    $actual = @{
        numeric      = $case.numeric_correctness
        completeness = $case.completeness
        evidence     = $case.evidence_support
        commentary   = $case.commentary_quality
    }
    $overall = $case.overall_pass
    $status = if ($overall) { 'PASS' } else { 'FAIL' }

    Write-Host "Case: $id"
    Write-Host "  Expected → numeric:$($expected.numeric) completeness:$($expected.completeness) evidence:$($expected.evidence) commentary:$($expected.commentary)"
    Write-Host "  Actual   → numeric:$($actual.numeric) completeness:$($actual.completeness) evidence:$($actual.evidence) commentary:$($actual.commentary)   => $status"
    if (-Not $overall) {
        if ($id -in @('unsupported_causal','deliberate_numeric_error')) {
            Write-Host "  Note: this failure is an expected negative test case."
        } else {
            Write-Host "  Note: unexpected failure – the grader rejected correct output."
        }
    }
    Write-Host ""
}
```

**Safety notes**:
- The command never writes to `reports\financial-trend-analysis_report.md` or `reports\financial_metrics_comparison.json`.
- It does not modify any source files or test definitions.
- It aborts immediately if any step returns a non‑zero exit code.

**Invocation**: In Claude Code, type `/run-golden-evals`.
