"""
rag_pipeline.py
Retrieval-Augmented Generation over India education-policy documents.
Raw documents live in MongoDB; embeddings now live in PostgreSQL via the
pgvector extension (replacing the earlier in-memory FAISS index), so every
Sanic worker/pod queries the same shared index instead of rebuilding its own
on startup.

Generation is done via Azure OpenAI chat completions, grounded strictly in
retrieved context.
"""
import logging
import numpy as np
from openai import AzureOpenAI

from config import AZURE
from db_connectors.mongo_client import MongoDataStore
from db_connectors.postgres_client import PostgresClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHUNK_SIZE = 400  # characters, kept simple for illustration


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


class AzureOpenAIProvider:
    """Wraps Azure OpenAI for embeddings + chat completion."""

    def __init__(self, config=AZURE):
        self.client = AzureOpenAI(
            api_key=config.openai_key,
            azure_endpoint=config.openai_endpoint,
            api_version="2024-05-01-preview",
        )
        self.embedding_deployment = config.embedding_deployment
        self.chat_deployment = config.openai_deployment

    def embed(self, texts: list[str]) -> np.ndarray:
        response = self.client.embeddings.create(model=self.embedding_deployment, input=texts)
        vectors = [item.embedding for item in response.data]
        return np.array(vectors, dtype="float32")

    def translate_to_english(self, text: str) -> str:
        """Used for cross-lingual retrieval: translate a non-English question
        to English before embedding it, so it matches (mostly English) policy
        document embeddings better. The final answer is still generated in
        the original language via `generate(..., language_name=...)`."""
        response = self.client.chat.completions.create(
            model=self.chat_deployment,
            messages=[
                {"role": "system", "content": "Translate the user's text to English. "
                                               "Reply with ONLY the translation, nothing else."},
                {"role": "user", "content": text},
            ],
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()

    def generate(self, question: str, context_chunks: list[str], language_name: str = "English") -> str:
        context = "\n---\n".join(context_chunks)
        system_prompt = (
            "You are an assistant answering questions about Indian education policy "
            "and rural digital-access programs. Answer ONLY using the provided context. "
            "If the context doesn't contain the answer, say so explicitly. "
            f"Respond in {language_name}, regardless of the language of the context."
        )
        user_prompt = f"Context:\n{context}\n\nQuestion: {question}"
        response = self.client.chat.completions.create(
            model=self.chat_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content


class RAGIndexer:
    """Chunks + embeds MongoDB documents, storing/querying vectors in pgvector."""

    def __init__(self, provider: AzureOpenAIProvider, mongo_store: MongoDataStore,
                 pg_client: PostgresClient):
        self.provider = provider
        self.mongo_store = mongo_store
        self.pg_client = pg_client

    def index_documents(self):
        """Pulls raw docs from Mongo, chunks + embeds them, upserts into pgvector."""
        docs = list(self.mongo_store.documents.find({}))
        for doc in docs:
            chunks = _chunk_text(doc["text"])
            vectors = self.provider.embed(chunks)
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                self.pg_client.upsert_embedding(
                    doc_id=doc["doc_id"], chunk_id=f"{doc['doc_id']}_{i}",
                    chunk_text=chunk, vector=vector.tolist(),
                )
        logger.info("Indexed %d documents into pgvector.", len(docs))

    def is_ready(self) -> bool:
        return self.pg_client.embedding_count() > 0

    @staticmethod
    def _rerank(question: str, candidates: list[tuple[str, float]], top_k: int) -> list[str]:
        """
        Lightweight re-ranking: pgvector's cosine distance is a good first
        pass, but a cheap lexical-overlap boost catches cases where a chunk
        shares the question's specific keywords but scored a bit lower on
        pure vector distance. (A cross-encoder model would do this better
        but adds a heavy extra dependency — this is the pragmatic middle
        ground for a project this size.)
        """
        question_terms = set(question.lower().split())
        scored = []
        for chunk_text, distance in candidates:
            overlap = len(question_terms & set(chunk_text.lower().split()))
            # Lower distance is better; higher overlap is better — combine into one score.
            combined_score = distance - (0.05 * overlap)
            scored.append((combined_score, chunk_text))
        scored.sort(key=lambda pair: pair[0])
        return [chunk for _, chunk in scored[:top_k]]

    def query(self, question: str, top_k: int = 3, language_name: str = "English",
              language_code: str = "en") -> str:
        if not self.is_ready():
            raise RuntimeError("No embeddings found — run index_documents() first.")

        # Cross-lingual retrieval: search using an English translation of the
        # question (embeddings are mostly built from English policy docs),
        # but still generate the final answer in the asker's own language.
        search_text = question
        if language_code != "en":
            try:
                search_text = self.provider.translate_to_english(question)
            except Exception as e:  # noqa: BLE001 - fall back to raw question if translation fails
                logger.warning("Translation for retrieval failed (%s), using original question", e)

        q_vector = self.provider.embed([search_text])[0].tolist()
        candidates = self.pg_client.similarity_search_with_distance(q_vector, top_k=max(top_k * 3, 10))
        top_chunks = self._rerank(search_text, candidates, top_k=top_k)

        return self.provider.generate(question, top_chunks, language_name=language_name)


if __name__ == "__main__":
    provider = AzureOpenAIProvider()
    mongo_store = MongoDataStore()
    pg_client = PostgresClient()
    pg_client.init_schema()

    rag = RAGIndexer(provider, mongo_store, pg_client)
    rag.index_documents()
    answer = rag.query("What is being done to bridge the digital divide in rural schools?")
    print(answer)
