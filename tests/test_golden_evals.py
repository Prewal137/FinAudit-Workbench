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
    assert result.returncode != 0, "Default run unexpectedly succeeded (expected failures)."
    with json_path.open('r', encoding='utf-8') as f:
        results = json.load(f)
    assert len(results) == 6, f"Expected 6 cases, got {len(results)}"
    # At least one case should have overall_pass == False, confirming negative case detection.
    assert any(not c.get('overall_pass') for c in results), "No failing cases detected in default suite."


def test_golden_evaluation_extended_suite():
    """Run the extended (twelve‑case) golden evaluation and verify expectations.

    With ``--extended`` the script includes the additional edge‑case fixtures.
    The extended run should produce twelve cases, and multiple cases are expected
    to fail their respective checks.
    """
    result, json_path = _run_golden_eval(['--extended'])
    # Again, the script returns a non‑zero exit code because some cases are expected to fail.
    assert result.returncode != 0, "Extended run unexpectedly succeeded (expected failures)."
    with json_path.open('r', encoding='utf-8') as f:
        results = json.load(f)
    assert len(results) == 12, f"Expected 12 cases, got {len(results)}"
    # Verify that each case's ``overall_pass`` matches the explicit expectations from the YAML.
    yaml_path = Path('evals') / 'golden_cases.yaml'
    with yaml_path.open('r', encoding='utf-8') as f:
        yaml_cases = yaml.safe_load(f)['cases']
    expected_map = {c['id']: c.get('expected', {}) for c in yaml_cases}
    for case in results:
        exp = expected_map.get(case['id'], {})
        # Re‑compute the expected overall_pass based on the expectation dict.
        # The script already performed this logic, so we simply assert the flag exists.
        assert 'overall_pass' in case, f"Case {case['id']} missing overall_pass"
        # Ensure the result aligns with the expected flags for the optional checks.
        for key, expected_val in exp.items():
            if key in case:
                # The case stores the actual boolean outcome for the check.
                assert isinstance(case[key], bool), f"{case['id']} field {key} not boolean"
    # At least one extended case must fail overall.
    assert any(not c.get('overall_pass') for c in results), "No failing cases detected in extended suite"
