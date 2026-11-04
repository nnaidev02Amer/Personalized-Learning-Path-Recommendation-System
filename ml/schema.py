"""Schema and input validation for student-profile records.

The columns match ``sample_data.csv``. Validation runs on every model input
(training data and new students) so bad data fails fast with a clear message
instead of producing a silent wrong prediction.
"""

from __future__ import annotations

import pandas as pd

LEARNING_STYLES = ("Auditory", "Kinesthetic", "Reading/Writing", "Visual")
CONTENT_TYPES = ("Articles", "Podcasts", "Quizzes", "Videos")

# column -> inclusive (min, max) allowed range
NUMERIC_RANGES = {
    "Age": (10, 100),
    "Progress": (0.0, 1.0),
    "CompletedCourses": (0, 1000),
    "AverageScore": (0.0, 100.0),
    "SessionTime": (0.0, 1440.0),   # minutes per day
}
NUMERIC_FEATURES = list(NUMERIC_RANGES)
CATEGORICAL_FEATURES = ["PreferredContent"]

# Features describing a student (what a model may see).
PROFILE_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


class ValidationError(ValueError):
    """Raised when student data does not match the expected schema."""


def validate_students(
    data: pd.DataFrame,
    *,
    require_id: bool = False,
    require_style: bool = False,
) -> pd.DataFrame:
    """Return a type-coerced copy of ``data`` or raise ``ValidationError``.

    :param require_id: StudentID column must be present.
    :param require_style: LearningStyle column must be present (training data).
    """
    if not isinstance(data, pd.DataFrame):
        raise ValidationError("Student data must be a pandas DataFrame.")
    if data.empty:
        raise ValidationError("Student data is empty.")

    required = list(PROFILE_FEATURES)
    if require_id:
        required.append("StudentID")
    if require_style:
        required.append("LearningStyle")

    missing = [c for c in required if c not in data.columns]
    if missing:
        raise ValidationError(f"Missing required column(s): {', '.join(missing)}")

    data = data.copy()
    errors: list[str] = []

    for column, (low, high) in NUMERIC_RANGES.items():
        values = pd.to_numeric(data[column], errors="coerce")
        if values.isna().any():
            errors.append(f"{column} must be numeric and not empty")
            continue
        out_of_range = (values < low) | (values > high)
        if out_of_range.any():
            errors.append(
                f"{column} must be between {low} and {high} "
                f"(got {values[out_of_range].iloc[0]})"
            )
        data[column] = values.astype(float)

    _check_category(data, "PreferredContent", CONTENT_TYPES, errors)
    if "LearningStyle" in data.columns and (
        require_style or data["LearningStyle"].notna().any()
    ):
        _check_category(data, "LearningStyle", LEARNING_STYLES, errors)

    if "StudentID" in data.columns:
        ids = pd.to_numeric(data["StudentID"], errors="coerce")
        if ids.isna().any() or (ids % 1 != 0).any():
            errors.append("StudentID must be a whole number")
        elif ids.duplicated().any():
            errors.append("StudentID values must be unique")
        else:
            data["StudentID"] = ids.astype(int)

    if errors:
        raise ValidationError("; ".join(errors))
    return data


def _check_category(data, column, allowed, errors):
    values = data[column]
    if values.isna().any():
        errors.append(f"{column} must not be empty")
        return
    invalid = sorted(set(values.astype(str)) - set(allowed))
    if invalid:
        errors.append(
            f"{column} has invalid value(s) {invalid}; allowed: {list(allowed)}"
        )
    data[column] = values.astype(str)
