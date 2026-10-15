import importlib.util
import pathlib

# Load the run_golden_evals module directly from its source file
module_path = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'run_golden_evals.py'
spec = importlib.util.spec_from_file_location('run_golden_evals', module_path)
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

def test_numeric_correctness_pass_and_fail():
    # Obtain a synthetic fixture with correct numbers
    metrics, periods = run.synthetic_normal_fixture()
    # Generate a correct report
    report = run.generate_report(metrics, periods)
    # The numeric evaluator should PASS on the correct report
    assert run.evaluate_numeric_correctness(metrics, report, periods) is True

    # Introduce an intentional numeric error by altering the revenue of the first period
    rev = metrics.monthly_metrics[periods[0]].revenue
    wrong_rev = rev + 10.0  # small deviation beyond tolerance
    correct_str = run.fmt_currency(rev)
    wrong_str = run.fmt_currency(wrong_rev)
    # Replace only the first occurrence of the correctly formatted revenue
    report_err = report.replace(correct_str, wrong_str, 1)
    # The numeric evaluator should now FAIL
    assert run.evaluate_numeric_correctness(metrics, report_err, periods) is False
