import hashlib

import numpy as np
import pandas as pd
import pytest

from ml_helpers import new_student
from ml import config
from ml.preprocessing import DataPreprocessing
from ml.schema import ValidationError, validate_students


# SHA-256 of sample_data.csv as committed upstream (3c9a8ae), LF line endings.
ORIGINAL_SAMPLE_SHA256 = "84a338623bb64f69169342f656d56dc5ef26c407e0935dd6138cc68d90747cef"


def test_sample_data_is_unchanged():
    """sample_data.csv must stay identical to the original upstream file."""
    current = config.SAMPLE_DATA_PATH.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(current).hexdigest() == ORIGINAL_SAMPLE_SHA256


@pytest.mark.parametrize("overrides, message", [
    ({"Progress": 1.5}, "Progress must be between"),
    ({"AverageScore": "abc"}, "AverageScore must be numeric"),
    ({"PreferredContent": "TikTok"}, "PreferredContent has invalid value"),
    ({"LearningStyle": "Telepathic"}, "LearningStyle has invalid value"),
    ({"Age": None}, "Age must be numeric"),
])
def test_validation_rejects_bad_input(overrides, message):
    with pytest.raises(ValidationError, match=message):
        validate_students(new_student(**overrides))


def test_validation_rejects_missing_columns_and_duplicate_ids():
    with pytest.raises(ValidationError, match="Missing required column"):
        validate_students(new_student().drop(columns=["SessionTime"]))
    two = pd.concat([new_student(StudentID=1), new_student(StudentID=1)])
    with pytest.raises(ValidationError, match="unique"):
        validate_students(two)


def test_valid_input_passes():
    assert len(validate_students(new_student())) == 1


def test_preprocessing_outputs(clean_data, workdirs):
    scaled = pd.read_csv(workdirs["data"] / "processed" / config.PREPROCESSED_CSV)
    assert clean_data["StudentID"].dtype.kind == "i"          # was float before
    assert scaled["StudentID"].dtype.kind == "i"
    assert clean_data.isna().sum().sum() == 0
    assert clean_data["Progress"].between(0, 1).all()          # original units kept
    assert np.allclose(scaled["AverageScore"].mean(), 0, atol=1e-9)
    assert (workdirs["models"] / "preprocessor.pkl").exists()


def test_missing_values_are_imputed(tmp_path):
    raw = pd.read_csv(config.SAMPLE_DATA_PATH)
    raw.loc[0, "AverageScore"] = np.nan
    raw.loc[1, "PreferredContent"] = np.nan
    path = tmp_path / "with_gaps.csv"
    raw.to_csv(path, index=False)
    clean = DataPreprocessing().clean(path)
    assert clean.isna().sum().sum() == 0
    assert clean.loc[1, "PreferredContent"] in {"Articles", "Podcasts", "Quizzes", "Videos"}


def test_transform_reuses_fitted_scaler():
    prep = DataPreprocessing()
    fitted = prep.preprocess(config.SAMPLE_DATA_PATH)
    raw = pd.read_csv(config.SAMPLE_DATA_PATH).iloc[[0]]
    again = prep.transform(raw)
    assert np.isclose(again["AverageScore"].iloc[0], fitted["AverageScore"].iloc[0])
