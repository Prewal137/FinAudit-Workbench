import importlib.util
import pathlib

# Load the run_golden_evals module directly from source
module_path = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'run_golden_evals.py'
spec = importlib.util.spec_from_file_location('run_golden_evals', module_path)
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

def test_supported_causal_claim_detection():
    # Create a narrative with a Fact line immediately preceding a causal Interpretation
    metrics, periods = run.synthetic_normal_fixture()
    narrative = (
        "## 9. Significant Anomalies and Supporting Evidence\n"
        "[Fact] Marketing campaign was launched in Q1.\n"
        "[Interpretation] Revenue increased because the new marketing campaign was launched.\n"
    )
    report = run.generate_report(metrics, periods, narrative)
    evidence_pass, commentary_pass = run.evaluate_narrative(report)
    assert evidence_pass is True
    assert commentary_pass is True

def test_unsupported_causal_claim_detection():
    # Use the fixture that includes a Fact line but inserts a non‑Fact Note before the causal claim
    metrics, periods, narrative = run.synthetic_unsupported_causal_fixture()
    report = run.generate_report(metrics, periods, narrative)
    evidence_pass, commentary_pass = run.evaluate_narrative(report)
    assert evidence_pass is False
    assert commentary_pass is True


