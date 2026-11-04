
import os
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer


class DataPreprocessing:
    def __init__(self):
        self.scaler = StandardScaler()
        self.numeric_imputer = SimpleImputer(strategy="mean")
        self.category_imputer = SimpleImputer(strategy="most_frequent")

    def load_data(self, filepath):
        return pd.read_csv(filepath)

    def clean_data(self, data):
        data = data.drop_duplicates().copy()

        numeric_columns = data.select_dtypes(include="number").columns
        category_columns = data.select_dtypes(exclude="number").columns

        if len(numeric_columns):
            data[numeric_columns] = self.numeric_imputer.fit_transform(
                data[numeric_columns]
            )

        if len(category_columns):
            data[category_columns] = self.category_imputer.fit_transform(
                data[category_columns]
            )

        return data

    def normalize_data(self, data, columns):
        data = data.copy()
        data[columns] = self.scaler.fit_transform(data[columns])
        return data

    def extract_features(self, data):
        data = data.copy()

        # Create a performance feature using the available score.
        data["avg_performance"] = data["AverageScore"]

        return data

    def preprocess(self, filepath, columns_to_normalize):
        data = self.load_data(filepath)
        data = self.clean_data(data)
        data = self.extract_features(data)
        data = self.normalize_data(data, columns_to_normalize)

        return data


if __name__ == "__main__":
    student_data_filepath = "sample_data.csv"

    columns_to_normalize = [
        "Age",
        "Progress",
        "CompletedCourses",
        "AverageScore",
        "SessionTime",
        "avg_performance"
    ]

    preprocessing = DataPreprocessing()

    preprocessed_student_data = preprocessing.preprocess(
        student_data_filepath,
        columns_to_normalize
    )

    os.makedirs("data/processed", exist_ok=True)

    output_path = "data/processed/preprocessed_student_data.csv"

    preprocessed_student_data.to_csv(output_path, index=False)

    print("\nStudent data preprocessing completed successfully!")
    print("Total student records:", len(preprocessed_student_data))
    print("Output saved to:", output_path)
    print("\nProcessed data preview:")
    print(preprocessed_student_data.head())
