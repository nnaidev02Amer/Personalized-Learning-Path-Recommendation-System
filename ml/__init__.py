"""Machine-learning package of the Personalized Learning Path Recommendation System.

Student-profile pipeline (works on the original ``sample_data.csv``):
    preprocessing     -> clean / standardise data
    learning_style    -> K-Means segmentation + Decision Tree classifier
    peer_recommender  -> cosine k-NN similar-student finder
    adaptive_level    -> percentile-based learning-level policy
    evaluation        -> baseline-aware evaluation report

Run everything with ``python -m ml all`` (see ``python -m ml --help``).
"""

__version__ = "2.0.0-dev"
