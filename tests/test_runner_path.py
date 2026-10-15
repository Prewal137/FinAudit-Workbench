import importlib.util
import pathlib
import subprocess
import sys
import json
from pathlib import Path

module_path = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'run_golden_evals.py'
spec = importlib.util.spec_from_file_location('run_golden_evals', module_path)
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

def test_runner_respects_paths(tmp_path):
    # Run the golden evaluation script from a different working directory (tmp_path)
    result = subprocess.run([sys.executable, str(module_path)],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, f"Runner failed with exit code {result.returncode}\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    # Verify that the JSON results file was written to the correct location in the repository
    json_path = Path('reports') / 'golden_cases' / 'golden_evaluation_results.json'
    assert json_path.is_file(), f"Results JSON not found at {json_path}"
    data = json.loads(json_path.read_text(encoding='utf-8'))
    # Expect six cases
    assert len(data) == 6, f"Expected 6 cases, found {len(data)}"
    expected_ids = {'normal_movement', 'large_change', 'missing_values', 'high_expense', 'unsupported_causal', 'deliberate_numeric_error'}
    assert {c['id'] for c in data} == expected_ids
