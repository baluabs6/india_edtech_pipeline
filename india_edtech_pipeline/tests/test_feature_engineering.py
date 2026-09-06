"""
test_feature_engineering.py
Fast, dependency-free unit tests — no live Postgres/Mongo/Azure connections.
Run with: pytest tests/
"""
import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ingestion.ingest_pipeline import generate_sample_raw_data, engineer_features
from genai.rag_pipeline import _chunk_text


def test_sample_data_shapes():
    schools, students = generate_sample_raw_data(n_schools=10, n_students=100)
    assert len(schools) == 10
    assert len(students) == 100
    assert set(["school_id", "attendance_pct", "avg_test_score"]).issubset(students.columns)


def test_engineer_features_adds_expected_columns():
    schools, students = generate_sample_raw_data(n_schools=5, n_students=50)
    merged = engineer_features(schools, students)
    assert "digital_access_index" in merged.columns
    assert "dropout_flag" in merged.columns
    assert merged["digital_access_index"].between(0, 1).all()
    assert merged["dropout_flag"].dtype == bool


def test_dropout_flag_is_roughly_top_quartile():
    schools, students = generate_sample_raw_data(n_schools=20, n_students=1000, seed=1)
    merged = engineer_features(schools, students)
    dropout_rate = merged["dropout_flag"].mean()
    # by construction (75th percentile threshold) this should be close to 0.25
    assert 0.15 < dropout_rate < 0.35


def test_chunk_text_respects_chunk_size():
    text = "a" * 1000
    chunks = _chunk_text(text, chunk_size=400)
    assert len(chunks) == 3
    assert all(len(c) <= 400 for c in chunks)
    assert "".join(chunks) == text


def test_chunk_text_handles_short_input():
    chunks = _chunk_text("short text", chunk_size=400)
    assert chunks == ["short text"]


def test_rerank_prefers_keyword_overlap_when_distances_are_close():
    from genai.rag_pipeline import RAGIndexer
    candidates = [
        ("rural internet schools digital access", 0.20),
        ("unrelated text here about weather", 0.19),
    ]
    result = RAGIndexer._rerank("rural internet access", candidates, top_k=1)
    assert result == ["rural internet schools digital access"]
