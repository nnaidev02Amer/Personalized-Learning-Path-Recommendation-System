# # adaptive_learning_system.py

# """
# Adaptive Learning System Module for Personalized Learning Path Recommendation System

# This module contains functions for implementing an adaptive learning system that adjusts
# recommendations based on student progress and learning style.

# Techniques Used:
# - Reinforcement Learning
# - Dynamic Adjustment

# Algorithms Used:
# - Deep Q-Learning (DQN)
# - Contextual Bandits

# Libraries/Tools:
# - TensorFlow
# - Keras
# """

# import numpy as np
# import pandas as pd
# import tensorflow as tf
# from tensorflow.keras.models import Sequential
# from tensorflow.keras.layers import Dense
# from sklearn.preprocessing import StandardScaler
# import joblib

# class AdaptiveLearningSystem:
#     def __init__(self, state_size, action_size):
#         """
#         Initialize the AdaptiveLearningSystem class.
        
#         :param state_size: int, size of the state space
#         :param action_size: int, size of the action space
#         """
#         self.state_size = state_size
#         self.action_size = action_size
#         self.model = self._build_model()
#         self.scaler = StandardScaler()

#     def _build_model(self):
#         """
#         Build the DQN model.
        
#         :return: Sequential, the DQN model
#         """
#         model = Sequential()
#         model.add(Dense(24, input_dim=self.state_size, activation='relu'))
#         model.add(Dense(24, activation='relu'))
#         model.add(Dense(self.action_size, activation='linear'))
#         model.compile(loss='mse', optimizer=tf.keras.optimizers.Adam(lr=0.001))
#         return model

#     def preprocess_data(self, data):
#         """
#         Preprocess the data for training and prediction.
        
#         :param data: DataFrame, input data
#         :return: DataFrame, preprocessed data
#         """
#         data = data.fillna(data.mean())
#         data = self.scaler.fit_transform(data)
#         return data

#     def train(self, data, target_column, epochs=10):
#         """
#         Train the adaptive learning system using DQN.
        
#         :param data: DataFrame, input data
#         :param target_column: str, name of the target column
#         :param epochs: int, number of epochs for training
#         """
#         X = data.drop(columns=[target_column])
#         y = data[target_column]

#         for epoch in range(epochs):
#             for i in range(len(X)):
#                 state = X.iloc[i].values.reshape(1, -1)
#                 action = y.iloc[i]
#                 target = self.model.predict(state)
#                 target[0][action] = action
#                 self.model.fit(state, target, epochs=1, verbose=0)

#         joblib.dump(self.scaler, 'models/scaler.pkl')
#         self.model.save('models/adaptive_learning_model.h5')

#     def predict(self, student_data):
#         """
#         Predict the next best action for the student.
        
#         :param student_data: DataFrame, data of the student
#         :return: int, predicted action
#         """
#         scaler = joblib.load('models/scaler.pkl')
#         model = tf.keras.models.load_model('models/adaptive_learning_model.h5')
#         student_data = scaler.transform(student_data)
#         action_values = model.predict(student_data)
#         return np.argmax(action_values[0])

# if __name__ == "__main__":
#     data_filepath = 'data/processed/preprocessed_student_data.csv'
#     student_data_filepath = 'data/processed/new_student_data.csv'
#     target_column = 'learning_path'

#     adaptive_system = AdaptiveLearningSystem(state_size=5, action_size=3)  # Example sizes
#     data = pd.read_csv(data_filepath)
#     data = adaptive_system.preprocess_data(data)

#     # Train the adaptive learning system
#     adaptive_system.train(data, target_column)

#     # Predict the next best action for a new student
#     new_student_data = pd.read_csv(student_data_filepath)
#     new_student_data = adaptive_system.preprocess_data(new_student_data)
#     next_action = adaptive_system.predict(new_student_data)
#     print("Next best action for the student:", next_action)



import os
import joblib
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier


class AdaptiveLearningSystem:

    def __init__(self):
        self.model = None
        self.actions = {
            0: "Beginner - Study basic concepts",
            1: "Practice - Solve quizzes and exercises",
            2: "Advanced - Move to advanced topics"
        }

    def load_data(self, filepath):
        return pd.read_csv(filepath)

    def prepare_data(self, data):
        data = data.copy()

        # Create a performance score from progress and marks.
        progress_rank = data["Progress"].rank(pct=True)
        score_rank = data["AverageScore"].rank(pct=True)

        performance = (progress_rank + score_rank) / 2

        # Create three learning action categories.
        data["LearningAction"] = pd.cut(
            performance,
            bins=[-0.01, 0.33, 0.66, 1.01],
            labels=[0, 1, 2]
        ).astype(int)

        return data

    def train(self, data):
        data = self.prepare_data(data)

        X = data.drop(
            columns=["StudentID", "LearningAction", "avg_performance"],
            errors="ignore"
        )

        y = data["LearningAction"]

        numeric_columns = X.select_dtypes(
            include="number"
        ).columns.tolist()

        categorical_columns = X.select_dtypes(
            exclude="number"
        ).columns.tolist()

        numeric_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler())
        ])

        categorical_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore"))
        ])

        preprocessing = ColumnTransformer([
            ("numeric", numeric_pipeline, numeric_columns),
            ("categorical", categorical_pipeline, categorical_columns)
        ])

        self.model = Pipeline([
            ("preprocessing", preprocessing),
            ("classifier", RandomForestClassifier(
                n_estimators=100,
                random_state=42
            ))
        ])

        self.model.fit(X, y)

        os.makedirs("models", exist_ok=True)

        joblib.dump(
            self.model,
            "models/adaptive_learning_model.pkl"
        )

        print("Adaptive learning model trained successfully!")
        print("Model saved in models folder.")

    def predict(self, student_data):
        self.model = joblib.load(
            "models/adaptive_learning_model.pkl"
        )

        student_data = student_data.drop(
            columns=["StudentID", "avg_performance"],
            errors="ignore"
        )

        prediction = self.model.predict(student_data)[0]

        return self.actions[int(prediction)]


if __name__ == "__main__":

    data_filepath = "sample_data.csv"

    adaptive_system = AdaptiveLearningSystem()

    data = adaptive_system.load_data(data_filepath)

    adaptive_system.train(data)

    # Demonstrate a recommendation for the first student.
    student_data = data.iloc[[0]].copy()

    next_action = adaptive_system.predict(student_data)

    print("\nAdaptive Learning Recommendation")
    print("--------------------------------")
    print(next_action)
