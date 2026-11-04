import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def workdirs(tmp_path, monkeypatch):
    """Redirect all data/model/report output to a temporary directory."""
    dirs = {name: tmp_path / name for name in ("data", "models", "reports")}
    monkeypatch.setenv("PLRS_DATA_DIR", str(dirs["data"]))
    monkeypatch.setenv("PLRS_MODELS_DIR", str(dirs["models"]))
    monkeypatch.setenv("PLRS_REPORTS_DIR", str(dirs["reports"]))
    return dirs


@pytest.fixture
def clean_data(workdirs):
    from ml import preprocessing
    result = preprocessing.run()
    return pd.read_csv(result["clean_path"])


@pytest.fixture
def trained(clean_data):
    """Run the full training pipeline once into the temp directories."""
    from ml import adaptive_level, learning_style, peer_recommender
    learning_style.run()
    peer_recommender.run()
    adaptive_level.run()
    return clean_data


def new_student(**overrides):
    row = {"Age": 22, "Progress": 0.5, "CompletedCourses": 3, "AverageScore": 75.0,
           "PreferredContent": "Videos", "SessionTime": 60.0, "LearningStyle": "Visual"}
    row.update(overrides)
    return pd.DataFrame([row])
