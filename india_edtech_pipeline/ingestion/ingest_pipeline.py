"""
ingest_pipeline.py
Simulates ingesting India school/student datasets (e.g. UDISE+ style extracts),
cleans them with pandas/numpy, computes derived features, and routes:
  - structured rows -> PostgreSQL
  - free-text feedback / reports -> MongoDB
"""
import logging
import numpy as np
import pandas as pd
import pandera as pa
from pandera import Column, Check, DataFrameSchema
from db_connectors.postgres_client import PostgresClient
from db_connectors.mongo_client import MongoDataStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Schema validation gate: a malformed UDISE+/state extract fails loudly here
# instead of silently corrupting the dropout-risk model downstream.
STUDENT_LOAD_SCHEMA = DataFrameSchema({
    "school_id": Column(int, Check.ge(1), nullable=False),
    "age": Column(int, Check.in_range(5, 19), nullable=False),
    "gender": Column(str, Check.isin(["M", "F"]), nullable=False),
    "attendance_pct": Column(float, Check.in_range(0, 100), nullable=False),
    "avg_test_score": Column(float, Check.in_range(0, 100), nullable=False),
    "has_device_home": Column(bool, nullable=False),
    "dropout_flag": Column(bool, nullable=False),
})


def generate_sample_raw_data(n_schools: int = 50, n_students: int = 2000, seed: int = 42):
    """Stand-in for a real UDISE+/state education dept extract."""
    rng = np.random.default_rng(seed)
    states = ["Bihar", "Uttar Pradesh", "Maharashtra", "Tamil Nadu", "Assam", "Rajasthan"]

    schools = pd.DataFrame({
        "school_name": [f"Govt School {i}" for i in range(n_schools)],
        "state": rng.choice(states, n_schools),
        "district": [f"District-{i % 10}" for i in range(n_schools)],
        "is_rural": rng.choice([True, False], n_schools, p=[0.7, 0.3]),
        "has_internet": rng.choice([True, False], n_schools, p=[0.45, 0.55]),
        "has_computers": rng.choice([True, False], n_schools, p=[0.5, 0.5]),
        "student_teacher_ratio": np.round(rng.normal(32, 8, n_schools).clip(15, 60), 1),
    })

    students = pd.DataFrame({
        "school_id": rng.integers(1, n_schools + 1, n_students),
        "age": rng.integers(6, 18, n_students),
        "gender": rng.choice(["M", "F"], n_students),
        "attendance_pct": np.round(rng.normal(75, 15, n_students).clip(0, 100), 1),
        "avg_test_score": np.round(rng.normal(55, 18, n_students).clip(0, 100), 1),
        "has_device_home": rng.choice([True, False], n_students, p=[0.35, 0.65]),
    })
    return schools, students


def engineer_features(schools: pd.DataFrame, students: pd.DataFrame) -> pd.DataFrame:
    """Numpy/pandas feature engineering: build a dropout risk label + composite indices."""
    merged = students.merge(schools.reset_index().rename(columns={"index": "school_id"}),
                             on="school_id", suffixes=("", "_school"))

    # Composite "digital access index" (0-1): weighs school infra + home device
    merged["digital_access_index"] = np.select(
        condlist=[
            merged["has_internet"] & merged["has_computers"] & merged["has_device_home"],
            merged["has_internet"] | merged["has_computers"],
        ],
        choicelist=[1.0, 0.5],
        default=0.1,
    )

    # Synthetic dropout flag driven by attendance, scores, and digital access
    # (in production this comes from historical outcome data, not synthesized)
    dropout_prob = (
        0.5 * (1 - merged["attendance_pct"] / 100)
        + 0.3 * (1 - merged["avg_test_score"] / 100)
        + 0.2 * (1 - merged["digital_access_index"])
    )
    merged["dropout_flag"] = dropout_prob > np.quantile(dropout_prob, 0.75)

    logger.info("Feature engineering complete: %d student records", len(merged))
    return merged


def run_ingestion():
    pg = PostgresClient()
    mongo = MongoDataStore()
    pg.init_schema()

    schools_raw, students_raw = generate_sample_raw_data()

    # Load schools first to get real serial IDs, then re-map student school_ids 1:1
    pg.bulk_load_dataframe(schools_raw, "schools", if_exists="append")
    enriched_students = engineer_features(schools_raw, students_raw)

    load_cols = ["school_id", "age", "gender", "attendance_pct", "avg_test_score",
                 "has_device_home", "dropout_flag"]
    students_to_load = enriched_students[load_cols]

    try:
        STUDENT_LOAD_SCHEMA.validate(students_to_load)
    except pa.errors.SchemaError as e:
        logger.error("Ingestion data failed validation, aborting load: %s", e)
        raise

    pg.bulk_load_dataframe(students_to_load, "students", if_exists="append")

    # Unstructured side: sample policy doc + feedback into Mongo
    mongo.insert_document(
        doc_id="nep2020_digital",
        title="National Education Policy 2020 - Digital Infrastructure Extract",
        text=("The policy calls for bridging the digital divide in rural schools through "
              "shared infrastructure, teacher digital-literacy training, and phased rollout "
              "of internet connectivity under the PM eVidya scheme."),
        source="Ministry of Education",
        tags=["policy", "digital-divide", "rural"],
    )
    mongo.insert_feedback(school_id=1, comment="Internet connection drops daily after 2pm.")

    logger.info("Ingestion pipeline finished.")
    return enriched_students


if __name__ == "__main__":
    run_ingestion()
