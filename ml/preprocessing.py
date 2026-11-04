"""Data preprocessing for the student-profile dataset (``sample_data.csv``).

Fixes compared to the original script:
* ``StudentID`` stays an integer (the numeric imputer used to turn it into 1.0).
* Imputers/scaler are fitted once and can be re-used on new data (``transform``).
* Two outputs are written:
    - ``preprocessed_student_data.csv``: standardised values (same file and
      columns as before, kept for backward compatibility / analysis);
    - ``clean_student_data.csv``: cleaned data in original units. All models
      train from this file and do their own scaling *inside* their pipelines,
      fitted on training rows only. This removes the old leakage where the
      scaler had already seen the test rows, and the double scaling.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from ml import config
from ml.schema import NUMERIC_FEATURES, validate_students

DEFAULT_COLUMNS_TO_NORMALIZE = NUMERIC_FEATURES + ["avg_performance"]


class DataPreprocessing:
    def __init__(self):
        self.scaler = StandardScaler()
        self.numeric_imputer = SimpleImputer(strategy="mean")
        self.category_imputer = SimpleImputer(strategy="most_frequent")
        self.numeric_columns: list[str] = []
        self.category_columns: list[str] = []
        self.normalized_columns: list[str] = []

    def load_data(self, filepath) -> pd.DataFrame:
        return pd.read_csv(filepath)

    def clean_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Drop duplicates and impute missing values (fits the imputers)."""
        data = data.drop_duplicates().reset_index(drop=True).copy()
        self.numeric_columns = [
            c for c in data.select_dtypes(include="number").columns if c != "StudentID"
        ]
        self.category_columns = data.select_dtypes(exclude="number").columns.tolist()
        return self._impute(data, fit=True)

    def _impute(self, data: pd.DataFrame, fit: bool) -> pd.DataFrame:
        data = data.copy()
        if "StudentID" in data.columns and data["StudentID"].isna().any():
            raise ValueError("StudentID must not be missing; it cannot be imputed.")
        for columns, imputer in (
            (self.numeric_columns, self.numeric_imputer),
            (self.category_columns, self.category_imputer),
        ):
            if columns:
                values = imputer.fit_transform(data[columns]) if fit else imputer.transform(data[columns])
                data[columns] = pd.DataFrame(values, columns=columns, index=data.index)
        if "StudentID" in data.columns:
            data["StudentID"] = data["StudentID"].astype(int)
        return data

    def extract_features(self, data: pd.DataFrame) -> pd.DataFrame:
        data = data.copy()
        # Kept for backward compatibility with the original output format. It is
        # an exact copy of AverageScore, so no model uses it as a feature.
        data["avg_performance"] = data["AverageScore"]
        return data

    def normalize_data(self, data: pd.DataFrame, columns) -> pd.DataFrame:
        data = data.copy()
        self.normalized_columns = list(columns)
        data[columns] = self.scaler.fit_transform(data[columns])
        return data

    def preprocess(self, filepath, columns_to_normalize=None) -> pd.DataFrame:
        """Original entry point: returns the standardised dataset."""
        clean = self.clean(filepath)
        return self.normalize_data(clean, columns_to_normalize or DEFAULT_COLUMNS_TO_NORMALIZE)

    def clean(self, filepath) -> pd.DataFrame:
        """Load, clean, validate and add derived features (original units)."""
        data = self.clean_data(self.load_data(filepath))
        data = validate_students(data, require_id=True, require_style=True)
        return self.extract_features(data)

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """Apply the *fitted* imputers and scaler to new rows."""
        data = self.extract_features(self._impute(data, fit=False))
        data[self.normalized_columns] = self.scaler.transform(data[self.normalized_columns])
        return data

    def save(self, path: Path | None = None) -> Path:
        path = path or config.models_dir() / "preprocessor.pkl"
        joblib.dump(self, path)
        return path


def run(input_path=None) -> dict:
    """Write both processed CSVs and the fitted preprocessor."""
    input_path = Path(input_path or config.SAMPLE_DATA_PATH)
    preprocessing = DataPreprocessing()
    clean = preprocessing.clean(input_path)
    scaled = preprocessing.normalize_data(clean, DEFAULT_COLUMNS_TO_NORMALIZE)

    out_dir = config.processed_dir()
    clean_path = out_dir / config.CLEAN_CSV
    scaled_path = out_dir / config.PREPROCESSED_CSV
    clean.to_csv(clean_path, index=False)
    scaled.to_csv(scaled_path, index=False)
    preprocessing.save()

    return {"records": len(clean), "clean_path": clean_path,
            "preprocessed_path": scaled_path, "preview": scaled.head()}
