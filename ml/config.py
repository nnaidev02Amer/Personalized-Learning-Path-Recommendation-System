"""Central configuration: file locations and global constants.

Every path is resolved from the repository root, so scripts work no matter
which directory they are launched from. Each location can be overridden with
an environment variable (used by the tests and by deployments):

    PLRS_DATA_DIR     default: <repo>/data
    PLRS_MODELS_DIR   default: <repo>/models
    PLRS_REPORTS_DIR  default: <repo>/reports
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# The original dataset shipped with the repository. It is read-only input.
SAMPLE_DATA_PATH = ROOT_DIR / "data" / "sample_data.csv"

RANDOM_STATE = 42


def _dir(env_name: str, default: Path) -> Path:
    path = Path(os.environ.get(env_name, default)).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    return _dir("PLRS_DATA_DIR", ROOT_DIR / "data")


def processed_dir() -> Path:
    path = data_dir() / "processed"
    path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir() -> Path:
    return _dir("PLRS_MODELS_DIR", ROOT_DIR / "models")


def reports_dir() -> Path:
    return _dir("PLRS_REPORTS_DIR", ROOT_DIR / "reports")


# File names of the student-profile pipeline (kept identical to the original
# project where a file already existed, so older instructions still apply).
PREPROCESSED_CSV = "preprocessed_student_data.csv"   # scaled, descriptive output
CLEAN_CSV = "clean_student_data.csv"                 # cleaned, original units (model input)
