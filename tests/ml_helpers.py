from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def new_student(**overrides):
    row = {"Age": 22, "Progress": 0.5, "CompletedCourses": 3, "AverageScore": 75.0,
           "PreferredContent": "Videos", "SessionTime": 60.0, "LearningStyle": "Visual"}
    row.update(overrides)
    return pd.DataFrame([row])
