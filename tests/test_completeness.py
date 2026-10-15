import importlib.util
import pathlib

module_path = pathlib.Path(__file__).resolve().parents[1] / 'scripts' / 'run_golden_evals.py'
spec = importlib.util.spec_from_file_location('run_golden_evals', module_path)
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

def test_check_completeness_pass_and_fail():
    # Generate a correct report
    metrics, periods = run.synthetic_normal_fixture()
    report = run.generate_report(metrics, periods)
    assert run.check_completeness(report, periods) is True

    # Remove a required section heading (e.g., Monthly Financial Performance)
    report_missing_section = report.replace('## 3. Monthly Financial Performance', '')
    assert run.check_completeness(report_missing_section, periods) is False

    # Remove a period row from the Monthly table
    # Assuming periods[0] appears as a row beginning with '| {period} |'
    period_row_marker = f"| {periods[0]} |"
    report_missing_period = report.replace(period_row_marker, '')
    assert run.check_completeness(report_missing_period, periods) is False
