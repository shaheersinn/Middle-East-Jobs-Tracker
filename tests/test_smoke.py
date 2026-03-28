import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_main_list_firms_runs():
    result = subprocess.run(
        [sys.executable, "main.py", "--list-firms"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Tracked US firms:" in result.stdout
    assert "Latham" in result.stdout
    assert result.stderr == ""


def test_main_invalid_firm_fails():
    result = subprocess.run(
        [sys.executable, "main.py", "--firm", "does_not_exist"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Unknown firm" in result.stdout
    assert result.stderr == ""
