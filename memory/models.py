"""Shared ML model registry.

Models are loaded once and reused across all agents.
Thread-safe lazy initialization via threading.Lock.
No double reranker load — singleton pattern applied.
"""
import os

# Reduce native BLAS/thread contention — avoids sporadic crashes on Windows CPU.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import threading
import logging

logger = logging.getLogger(__name__)

_lock = threading.Lock()

_embed_model  = None
_rerank_model = None
_embed_lock   = threading.Lock()  # separate lock for encode() calls


def get_embed_model():
    """Get or load the sentence-transformer embedding model."""
    global _embed_model
    if _embed_model is None:
        with _lock:
            if _embed_model is None:
                from sentence_transformers import SentenceTransformer
                model_name = os.getenv(
                    "EMBED_MODEL", "all-MiniLM-L6-v2"
                )
                logger.info(f"Loading embedding model: {model_name}")
                _embed_model = SentenceTransformer(model_name)
    return _embed_model


def get_rerank_model():
    """Get or load the cross-encoder re-ranking model."""
    global _rerank_model
    if _rerank_model is None:
        with _lock:
            if _rerank_model is None:
                from sentence_transformers import CrossEncoder
                model_name = os.getenv(
                    "RERANKER_MODEL",
                    "cross-encoder/ms-marco-MiniLM-L-6-v2",
                )
                logger.info(f"Loading re-ranker: {model_name}")
                _rerank_model = CrossEncoder(model_name, max_length=512)
    return _rerank_model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed documents. Thread-safe."""
    model = get_embed_model()
    with _embed_lock:
        vectors = model.encode(texts, normalize_embeddings=True)
    return vectors.tolist()


def embed_query(query: str) -> list[float]:
    """Embed a search query. Thread-safe."""
    model = get_embed_model()
    with _embed_lock:
        vector = model.encode(query, normalize_embeddings=True)
    return vector.tolist()


def rerank(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    """Re-rank retrieved chunks. Returns top_k most relevant."""
    if not chunks:
        return []
    model  = get_rerank_model()
    pairs  = [(query, c.get("document", "")) for c in chunks]
    scores = model.predict(pairs)
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    return [c for _, c in ranked[:min(top_k, len(chunks))]]
