import subprocess
import shutil
import tempfile
from pathlib import Path
import openpyxl


def _run_verify_workbook():
    """Run the verification script and return its stdout."""
    python_exe = Path('.venv-mcp') / 'Scripts' / 'python.exe'
    if not python_exe.is_file():
        python_exe = 'python'
    cmd = [str(python_exe), 'scripts/verify_workbook.py']
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def test_verification_passes_on_original_workbook():
    """The verification script should report only PASS for the untouched workbook."""
    result = _run_verify_workbook()
    assert result.returncode == 0, f"Verification script exited with {result.returncode}\n{result.stdout}\n{result.stderr}"
    # Ensure no FAIL lines appear in the output
    assert "FAIL" not in result.stdout, "Unexpected FAIL reported in verification output"


def test_verification_detects_intentional_error():
    """Modify a cached numeric cell to a non‑numeric value and ensure the script flags it.

    The test temporarily replaces the workbook with a corrupted copy, runs the verification
    script, checks for a FAIL line, and then restores the original file.
    """
    repo_root = Path(__file__).resolve().parents[2]
    original_path = repo_root / 'data' / 'input' / 'ABC Inc - Financial Statements.xlsx'
    backup_path = repo_root / 'data' / 'input' / 'ABC Inc - Financial Statements.xlsx.bak'
    # Backup the original workbook
    shutil.copy2(original_path, backup_path)
    try:
        # Load the workbook and corrupt a numeric cached cell (e.g., Income Statement!C14)
        wb = openpyxl.load_workbook(original_path, data_only=False)
        ws = wb['Income Statement']
        # Choose a cell that participates in a numeric check, e.g., C14 (row 14, column C)
        ws['C26'].value = "corrupt"
        wb.save(original_path)
        # Run verification script on the corrupted workbook
        result = _run_verify_workbook()
        assert result.returncode == 0, f"Verification script exited with {result.returncode}\n{result.stdout}\n{result.stderr}"
        # The output should contain a FAIL line indicating a non‑numeric value
        assert "FAIL" in result.stdout, "Expected FAIL not reported after corrupting workbook"
    finally:
        # Restore the original workbook
        shutil.move(backup_path, original_path)
