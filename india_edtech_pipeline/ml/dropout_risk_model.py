"""
dropout_risk_model.py
Trains a classifier to flag students at risk of dropping out, using
attendance, test scores, and digital-access features pulled from Postgres.
"""
import logging
import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from db_connectors.postgres_client import PostgresClient
from ml import model_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NUMERIC_FEATURES = ["age", "attendance_pct", "avg_test_score", "student_teacher_ratio"]
CATEGORICAL_FEATURES = ["gender", "is_rural", "has_internet", "has_computers", "has_device_home"]
TARGET = "dropout_flag"


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(transformers=[
        ("num", StandardScaler(), NUMERIC_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
    ])
    model = RandomForestClassifier(
        n_estimators=300, max_depth=8, class_weight="balanced", random_state=42
    )
    return Pipeline(steps=[("preprocess", preprocessor), ("model", model)])


def train_and_evaluate(df: pd.DataFrame, model_path: str = "dropout_model.joblib", register: bool = True):
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    preds = pipeline.predict(X_test)
    proba = pipeline.predict_proba(X_test)[:, 1]
    roc_auc = roc_auc_score(y_test, proba)

    logger.info("\n%s", classification_report(y_test, preds))
    logger.info("ROC-AUC: %.3f", roc_auc)

    joblib.dump(pipeline, model_path)
    logger.info("Model saved to %s", model_path)

    if register:
        model_registry.register_version(model_path, metrics={"roc_auc": roc_auc})

    return pipeline


def score_students(pipeline: Pipeline, df: pd.DataFrame) -> pd.DataFrame:
    """Attach a dropout_risk_score column for downstream dashboards / alerts."""
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    df = df.copy()
    df["dropout_risk_score"] = pipeline.predict_proba(X)[:, 1]
    return df.sort_values("dropout_risk_score", ascending=False)


def explain_prediction(pipeline: Pipeline, student_row: pd.DataFrame) -> dict:
    """
    Returns each feature's SHAP contribution to this one student's risk
    score, so a school admin can see *why* a student was flagged — e.g.
    {"attendance_pct": +0.18, "has_internet": -0.05, ...} where positive
    values push the risk score up and negative values push it down.
    """
    preprocessor = pipeline.named_steps["preprocess"]
    model = pipeline.named_steps["model"]

    X = student_row[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    X_transformed = preprocessor.transform(X)
    feature_names = preprocessor.get_feature_names_out()

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_transformed)

    # For a binary RandomForestClassifier, shap_values is [class_0, class_1];
    # we explain the "will drop out" (class 1) direction.
    values_for_positive_class = shap_values[1][0] if isinstance(shap_values, list) else shap_values[0]

    contributions = dict(zip(feature_names, [round(float(v), 4) for v in values_for_positive_class]))
    return dict(sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True))


if __name__ == "__main__":
    pg = PostgresClient()
    dataset = pg.get_training_dataset()
    if dataset.empty:
        raise RuntimeError("No training data found — run ingestion/ingest_pipeline.py first.")
    trained_pipeline = train_and_evaluate(dataset)
    ranked = score_students(trained_pipeline, dataset)
    print(ranked[["student_id", "dropout_risk_score"]].head(10))

