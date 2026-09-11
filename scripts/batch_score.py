import logging

import joblib

from config import NOTIFY
from db_connectors.postgres_client import PostgresClient
from ml.dropout_risk_model import score_students
from notifications.email_notifier import send_high_risk_alert

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_batch_scoring(model_path: str = "*******************b"):
    pg = PostgresClient()
    pg.init_schema()

    pipeline = joblib.load(model_path)
    dataset = pg.get_training_dataset()
    if dataset.empty:
        logger.warning("No students found — nothing to score.")
        return

    # Which students were already above threshold before this run, so we only
    # alert on newly-crossed cases rather than re-notifying every night.
    previous_scores = pg.get_precomputed_risk_scores(limit=len(dataset))
    previously_high_risk_ids = set(
        previous_scores[previous_scores["dropout_risk_score"] > NOTIFY.high_risk_threshold]["student_id"]
    ) if not previous_scores.empty else set()

    ranked = score_students(pipeline, dataset)
    pg.upsert_risk_scores(ranked[["student_id", "dropout_risk_score"]])

    newly_high_risk = ranked[
        (ranked["dropout_risk_score"] > NOTIFY.high_risk_threshold)
        & (~ranked["student_id"].isin(previously_high_risk_ids))
    ]
    send_high_risk_alert(newly_high_risk)

    logger.info(
        "Batch scoring complete: %d students scored, %d newly high-risk",
        len(ranked), len(newly_high_risk),
    )


if __name__ == "__main__":
    run_batch_scoring()
