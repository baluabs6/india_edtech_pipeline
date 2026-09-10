"""
main.py
End-to-end orchestration:
  1. Ingest + feature-engineer data -> PostgreSQL + MongoDB
  2. Train dropout-risk ML model on Postgres data
  3. Build RAG vector index over MongoDB policy documents
Run this once to bootstrap a local/dev environment before starting app.py.
"""
import logging
from ingestion.ingest_pipeline import run_ingestion
from ml.dropout_risk_model import train_and_evaluate
from db_connectors.postgres_client import PostgresClient
from db_connectors.mongo_client import MongoDataStore
from genai.rag_pipeline import AzureOpenAIProvider, RAGIndexer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def bootstrap():
    logger.info("Step 1/3: Ingesting data into Postgres + MongoDB")
    run_ingestion()

    logger.info("Step 2/3: Training dropout risk model")
    pg = PostgresClient()
    dataset = pg.get_training_dataset()
    train_and_evaluate(dataset)

    logger.info("Step 3/3: Building RAG index over policy documents (pgvector)")
    rag = RAGIndexer(AzureOpenAIProvider(), MongoDataStore(), pg)
    rag.index_documents()

    logger.info("Bootstrap complete. Start the API with: python app.py (or: sanic app.app --host 0.0.0.0 --port 8000)")


if __name__ == "__main__":
    bootstrap()
