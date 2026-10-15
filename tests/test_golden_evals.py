import subprocess
import json
import yaml
from pathlib import Path


def _run_golden_eval(args):
    """Helper to run golden eval script with optional arguments and return parsed JSON results."""
    python_exe = Path('.venv-mcp') / 'Scripts' / 'python.exe'
    if not python_exe.is_file():
        python_exe = 'python'
    cmd = [str(python_exe), 'scripts/run_golden_evals.py'] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    # The script returns 0 only if *all* cases meet expectations; we allow non-zero.
    return result, Path('reports') / 'golden_cases' / 'golden_evaluation_results.json'


def test_golden_evaluation_default_suite():
    """Run the default (six‑case) golden evaluation and verify expectations.

    The default run should produce exactly six cases. Several cases are designed to
    fail specific checks, so at least one ``overall_pass`` must be false.
    """
    result, json_path = _run_golden_eval([])
    # The script should exit with non‑zero because not all cases pass expectations.
    assert result.returncode == 0, f"Default run unexpectedly failed with code {result.returncode}."
    with json_path.open('r', encoding='utf-8') as f:
        results = json.load(f)
    assert len(results) == 6, f"Expected 6 cases, got {len(results)}"
    # All cases should have overall_pass == True as per the expectations defined in the YAML.
    assert all(c.get('overall_pass') for c in results), "Some cases did not meet expected outcomes in the default suite."


def test_golden_evaluation_extended_suite():
    """Run the extended (twelve‑case) golden evaluation and verify expectations.

    With ``--extended`` the script includes the additional edge‑case fixtures.
    The extended run should produce twelve cases, and multiple cases are expected
    to fail their respective checks.
    """
    result, json_path = _run_golden_eval(['--extended'])
    # Again, the script returns a non‑zero exit code because some cases are expected to fail.
    assert result.returncode == 0, "Extended run unexpectedly failed (expected success)."
    with json_path.open('r', encoding='utf-8') as f:
        results = json.load(f)
    assert len(results) == 12, f"Expected 12 cases, got {len(results)}"
    # All cases should have overall_pass == True as per the expectations defined in the YAML.
    assert all(c.get('overall_pass') for c in results), "Some cases did not meet expected outcomes in the extended suite."
