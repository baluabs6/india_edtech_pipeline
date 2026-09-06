"""
postgres_client.py
Handles structured education data (schools, students, enrollment) AND, since
this project migrated off FAISS, the RAG vector store — using the pgvector
extension so all Sanic worker pods share one index instead of each pod
rebuilding an in-memory FAISS index on startup.
"""
import logging
import pandas as pd
from sqlalchemy import create_engine, text
from config import PG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# EMBEDDING_DIM must match the embedding model in genai/rag_pipeline.py
# (text-embedding-3-small = 1536 dims).
EMBEDDING_DIM = 1536

SCHEMA_DDL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS schools (
    school_id       SERIAL PRIMARY KEY,
    school_name     VARCHAR(255) NOT NULL,
    state           VARCHAR(100) NOT NULL,
    district        VARCHAR(100),
    is_rural        BOOLEAN DEFAULT TRUE,
    has_internet    BOOLEAN DEFAULT FALSE,
    has_computers   BOOLEAN DEFAULT FALSE,
    student_teacher_ratio NUMERIC(5,2)
);

CREATE TABLE IF NOT EXISTS students (
    student_id      SERIAL PRIMARY KEY,
    school_id       INTEGER REFERENCES schools(school_id),
    age             INTEGER,
    gender          VARCHAR(20),
    attendance_pct  NUMERIC(5,2),
    avg_test_score  NUMERIC(5,2),
    has_device_home BOOLEAN DEFAULT FALSE,
    dropout_flag    BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_students_school ON students(school_id);

CREATE TABLE IF NOT EXISTS student_risk_scores (
    student_id          INTEGER PRIMARY KEY REFERENCES students(student_id),
    dropout_risk_score  NUMERIC(6,5) NOT NULL,
    scored_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS document_embeddings (
    id          SERIAL PRIMARY KEY,
    doc_id      VARCHAR(255) NOT NULL,
    chunk_id    VARCHAR(255) UNIQUE NOT NULL,
    chunk_text  TEXT NOT NULL,
    embedding   VECTOR({EMBEDDING_DIM}) NOT NULL
);

-- Approximate nearest-neighbor index; 'lists' should scale with row count
-- (roughly rows/1000, minimum 10). Cosine distance matches OpenAI embeddings.
CREATE INDEX IF NOT EXISTS idx_document_embeddings_ivfflat
    ON document_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
"""


class PostgresClient:
    def __init__(self, config=PG):
        self.engine = create_engine(config.uri, pool_pre_ping=True)

    def init_schema(self):
        with self.engine.begin() as conn:
            conn.execute(text(SCHEMA_DDL))
        logger.info("Postgres schema ensured (schools, students, student_risk_scores, document_embeddings).")

    def bulk_load_dataframe(self, df: pd.DataFrame, table_name: str, if_exists: str = "append"):
        """Load a cleaned pandas DataFrame into a Postgres table."""
        df.to_sql(table_name, con=self.engine, if_exists=if_exists, index=False)
        logger.info("Loaded %d rows into %s", len(df), table_name)

    def query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})

    def get_training_dataset(self, state: str | None = None) -> pd.DataFrame:
        """
        Join students + schools into a feature-ready dataset for ML.
        Passing `state` applies row-level isolation — used when a JWT-scoped
        client (one state education department) queries the API, so they
        only ever see their own state's students.
        """
        sql = """
            SELECT s.student_id, s.age, s.gender, s.attendance_pct, s.avg_test_score,
                   s.has_device_home, s.dropout_flag,
                   sc.school_id, sc.state, sc.district,
                   sc.is_rural, sc.has_internet, sc.has_computers, sc.student_teacher_ratio
            FROM students s
            JOIN schools sc ON s.school_id = sc.school_id
        """
        params = {}
        if state:
            sql += " WHERE sc.state = :state"
            params["state"] = state
        return self.query(sql, params)

    def get_student_by_id(self, student_id: int) -> pd.DataFrame:
        sql = """
            SELECT s.student_id, s.age, s.gender, s.attendance_pct, s.avg_test_score,
                   s.has_device_home, s.dropout_flag,
                   sc.school_id, sc.state, sc.district,
                   sc.is_rural, sc.has_internet, sc.has_computers, sc.student_teacher_ratio
            FROM students s
            JOIN schools sc ON s.school_id = sc.school_id
            WHERE s.student_id = :student_id
        """
        return self.query(sql, {"student_id": student_id})

    def delete_student(self, student_id: int) -> int:
        """Right-to-deletion: removes a student's row and any precomputed score. Returns rows deleted."""
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM student_risk_scores WHERE student_id = :id"), {"id": student_id})
            result = conn.execute(text("DELETE FROM students WHERE student_id = :id"), {"id": student_id})
            return result.rowcount

    # ---- Batch scoring (nightly CronJob writes here; API reads from here) ----
    def upsert_risk_scores(self, df: pd.DataFrame):
        """df must have columns: student_id, dropout_risk_score."""
        sql = """
            INSERT INTO student_risk_scores (student_id, dropout_risk_score, scored_at)
            VALUES (:student_id, :dropout_risk_score, now())
            ON CONFLICT (student_id) DO UPDATE
                SET dropout_risk_score = EXCLUDED.dropout_risk_score, scored_at = now()
        """
        with self.engine.begin() as conn:
            for row in df[["student_id", "dropout_risk_score"]].to_dict(orient="records"):
                conn.execute(text(sql), row)
        logger.info("Upserted %d precomputed risk scores", len(df))

    def get_precomputed_risk_scores(self, limit: int = 10, state: str | None = None) -> pd.DataFrame:
        sql = """
            SELECT r.student_id, r.dropout_risk_score, r.scored_at,
                   s.attendance_pct, s.avg_test_score, sc.state, sc.district, sc.school_id
            FROM student_risk_scores r
            JOIN students s ON r.student_id = s.student_id
            JOIN schools sc ON s.school_id = sc.school_id
        """
        params = {"limit": limit}
        if state:
            sql += " WHERE sc.state = :state"
            params["state"] = state
        sql += " ORDER BY r.dropout_risk_score DESC LIMIT :limit"
        return self.query(sql, params)

    def school_risk_summary(self, school_id: int) -> pd.DataFrame:
        sql = """
            SELECT sc.school_id, sc.school_name, sc.state, sc.district,
                   COUNT(r.student_id) AS scored_students,
                   AVG(r.dropout_risk_score) AS avg_risk_score,
                   SUM(CASE WHEN r.dropout_risk_score > 0.7 THEN 1 ELSE 0 END) AS high_risk_count
            FROM schools sc
            LEFT JOIN students s ON s.school_id = sc.school_id
            LEFT JOIN student_risk_scores r ON r.student_id = s.student_id
            WHERE sc.school_id = :school_id
            GROUP BY sc.school_id, sc.school_name, sc.state, sc.district
        """
        return self.query(sql, {"school_id": school_id})

    def district_risk_summary(self, state: str, district: str) -> pd.DataFrame:
        sql = """
            SELECT sc.state, sc.district,
                   COUNT(DISTINCT sc.school_id) AS school_count,
                   COUNT(r.student_id) AS scored_students,
                   AVG(r.dropout_risk_score) AS avg_risk_score,
                   SUM(CASE WHEN r.dropout_risk_score > 0.7 THEN 1 ELSE 0 END) AS high_risk_count
            FROM schools sc
            LEFT JOIN students s ON s.school_id = sc.school_id
            LEFT JOIN student_risk_scores r ON r.student_id = s.student_id
            WHERE sc.state = :state AND sc.district = :district
            GROUP BY sc.state, sc.district
        """
        return self.query(sql, {"state": state, "district": district})

    # ---- pgvector: RAG embedding storage + similarity search ----
    def upsert_embedding(self, doc_id: str, chunk_id: str, chunk_text: str, vector: list[float]):
        sql = """
            INSERT INTO document_embeddings (doc_id, chunk_id, chunk_text, embedding)
            VALUES (:doc_id, :chunk_id, :chunk_text, :embedding)
            ON CONFLICT (chunk_id) DO UPDATE
                SET chunk_text = EXCLUDED.chunk_text, embedding = EXCLUDED.embedding
        """
        with self.engine.begin() as conn:
            conn.execute(text(sql), {
                "doc_id": doc_id, "chunk_id": chunk_id, "chunk_text": chunk_text,
                "embedding": str(vector),  # pgvector accepts '[0.1,0.2,...]' text literal
            })

    def similarity_search(self, query_vector: list[float], top_k: int = 3) -> list[str]:
        """Cosine-distance nearest-neighbor search; returns the raw chunk texts."""
        sql = """
            SELECT chunk_text
            FROM document_embeddings
            ORDER BY embedding <=> (:query_vector)::vector
            LIMIT :top_k
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {
                "query_vector": str(query_vector), "top_k": top_k,
            }).fetchall()
        return [row[0] for row in rows]

    def similarity_search_with_distance(self, query_vector: list[float], top_k: int = 10) -> list[tuple[str, float]]:
        """Same as similarity_search but also returns cosine distance, for re-ranking."""
        sql = """
            SELECT chunk_text, embedding <=> (:query_vector)::vector AS distance
            FROM document_embeddings
            ORDER BY distance
            LIMIT :top_k
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {
                "query_vector": str(query_vector), "top_k": top_k,
            }).fetchall()
        return [(row[0], float(row[1])) for row in rows]

    def embedding_count(self) -> int:
        with self.engine.connect() as conn:
            return conn.execute(text("SELECT COUNT(*) FROM document_embeddings")).scalar()

    def get_anonymized_export(self, state: str | None = None) -> pd.DataFrame:
        """
        Research/reporting export: student_id is replaced with a salted hash
        so individual students can't be re-identified from the export, while
        still letting analysts group/count records consistently.
        """
        import hashlib
        df = self.get_training_dataset(state=state)
        salt = "edtech-india-export"  # rotate this if you need to invalidate old export hashes
        df["student_ref"] = df["student_id"].apply(
            lambda sid: hashlib.sha256(f"{salt}:{sid}".encode()).hexdigest()[:16]
        )
        return df.drop(columns=["student_id"])

