"""
mongo_client.py
Handles unstructured / semi-structured data: education policy PDFs (as text),
news articles on rural connectivity, parent/teacher feedback forms, and the
vector embeddings used by the RAG pipeline.
"""
import logging
from datetime import datetime, timezone
from pymongo import MongoClient, ASCENDING
from config import MONGO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MongoDataStore:
    def __init__(self, config=MONGO):
        self.client = MongoClient(config.uri)
        self.db = self.client[config.db]
        self.documents = self.db["policy_documents"]   # raw text + metadata
        self.embeddings = self.db["document_embeddings"]  # vector store
        self.feedback = self.db["field_feedback"]       # teacher/parent feedback
        self._ensure_indexes()

    def _ensure_indexes(self):
        self.documents.create_index([("source", ASCENDING)])
        self.embeddings.create_index([("doc_id", ASCENDING)])
        self.feedback.create_index([("school_id", ASCENDING)])

    def insert_document(self, doc_id: str, title: str, text: str, source: str, tags: list[str]):
        record = {
            "doc_id": doc_id,
            "title": title,
            "text": text,
            "source": source,
            "tags": tags,
            "ingested_at": datetime.now(timezone.utc),
        }
        self.documents.update_one({"doc_id": doc_id}, {"$set": record}, upsert=True)
        logger.info("Upserted document %s", doc_id)

    def insert_embedding(self, doc_id: str, chunk_id: str, chunk_text: str, vector: list[float]):
        self.embeddings.update_one(
            {"doc_id": doc_id, "chunk_id": chunk_id},
            {"$set": {"chunk_text": chunk_text, "vector": vector}},
            upsert=True,
        )

    def fetch_all_embeddings(self):
        return list(self.embeddings.find({}, {"_id": 0}))

    def insert_feedback(self, school_id: int, comment: str, sentiment: str | None = None):
        self.feedback.insert_one({
            "school_id": school_id,
            "comment": comment,
            "sentiment": sentiment,
            "created_at": datetime.now(timezone.utc),
        })
