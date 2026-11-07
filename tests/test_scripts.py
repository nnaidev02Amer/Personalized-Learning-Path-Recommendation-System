"""The five original root scripts must still run, in order, from any directory.

Scripts are executed in-process with ``runpy`` (as ``__main__``) after
changing the working directory, which exercises exactly the same code path
as ``python Data-Preprocessing.py`` without spawning child processes.
"""

import runpy
import sys

import pytest

from ml_helpers import ROOT
from ml.cli import main

SCRIPTS = ["Data-Preprocessing.py", "Learning-Style-Classification.py",
           "Recommendation-Algorithm.py", "Adaptive-Learning-System.py", "Evaluation.py"]


def run_script(script, monkeypatch):
    monkeypatch.setattr(sys, "argv", [script])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(ROOT / "ml" / "legacy" / script), run_name="__main__")
    return exit_info.value.code


def test_original_scripts_run_from_another_directory(tmp_path, workdirs, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for script in SCRIPTS:
        assert run_script(script, monkeypatch) == 0, f"{script} failed"
    output = capsys.readouterr().out
    assert "Decision Tree Classifier Results" in output
    assert "Adaptive Learning Recommendation" in output
    assert (workdirs["reports"] / "evaluation_report.json").exists()
    assert not any(tmp_path.glob("*.pkl")), "scripts must not write into the cwd"


def test_cli_reports_missing_models_cleanly(workdirs, capsys):
    assert main(["evaluate"]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_cli_reports_invalid_data_cleanly(tmp_path, workdirs, capsys):
    bad = tmp_path / "bad.csv"
    bad.write_text("StudentID,Age\n1,20\n")
    assert main(["preprocess", "--input", str(bad)]) == 1
    assert "invalid data" in capsys.readouterr().err
