import logging
import threading
import hashlib

import lancedb
import pyarrow as pa

from memory.models import embed_documents, embed_query
from utils.config import LANCE_PERSIST_DIR

logger = logging.getLogger(__name__)

SCHEMA = pa.schema([
    pa.field("chunk_id",        pa.string()),
    pa.field("content",         pa.string()),
    pa.field("source_url",      pa.string()),
    pa.field("source_domain",   pa.string()),
    pa.field("published_date",  pa.string()),
    pa.field("agent_id",        pa.string()),
    pa.field("phase",           pa.string()),
    pa.field("confidence",      pa.float32()),
    pa.field("consensus_state", pa.string()),
    pa.field("question_id",     pa.string()),
    pa.field("run_id",          pa.string()),
    pa.field("vector",          pa.list_(pa.float32(), 384)),
])


class LanceStore:
    """Thread-safe vector store backed by LanceDB.

    Write lock serializes concurrent agent writes.
    Embedding is done via shared model registry (memory/models.py).
    """

    def __init__(
        self,
        table_name: str = "swarmiq",
        persist_dir: str = LANCE_PERSIST_DIR,
    ):
        self.table_name  = table_name
        self.persist_dir = persist_dir
        self._write_lock = threading.Lock()
        self._db         = lancedb.connect(persist_dir)
        self._table      = self._init_table()

    def _init_table(self):
        if self.table_name in self._db.table_names():
            return self._db.open_table(self.table_name)
        return self._db.create_table(self.table_name, schema=SCHEMA)

    def add_documents(
        self,
        documents: list[str],
        metadatas: list[dict],
        ids: list[str],
    ) -> None:
        if not documents:
            return

        vectors = embed_documents(documents)

        rows = []
        for doc, meta, chunk_id, vec in zip(documents, metadatas, ids, vectors):
            try:
                from urllib.parse import urlparse
                domain = urlparse(meta.get("source_url", "")).netloc
            except Exception:
                domain = ""

            rows.append({
                "chunk_id":        chunk_id,
                "content":         doc[:2000],
                "source_url":      meta.get("source_url",      ""),
                "source_domain":   domain,
                "published_date":  meta.get("published_date",  ""),
                "agent_id":        meta.get("agent_id",         ""),
                "phase":           meta.get("phase",             ""),
                "confidence":      float(meta.get("confidence", 0.5)),
                "consensus_state": meta.get("consensus_state", "pending"),
                "question_id":     meta.get("question_id",      ""),
                "run_id":          meta.get("run_id",            ""),
                "vector":          vec,
            })

        with self._write_lock:
            self._table.add(rows, mode="append")   # append, not overwrite

        logger.info(f"Stored {len(rows)} chunks (run={meta.get('run_id', '')})")

    def query(self, query_text: str, n_results: int = 20) -> list[dict]:
        vec = embed_query(query_text)
        results = (
            self._table
            .search(vec)
            .metric("cosine")
            .limit(n_results)
            .to_list()
        )
        return [
            {
                "id":       r.get("chunk_id", ""),
                "document": r.get("content",  ""),
                "metadata": {k: v for k, v in r.items()
                             if k not in ("content", "vector")},
                "distance": r.get("_distance", 0.0),
            }
            for r in results
        ]

    def query_by_run(self, run_id: str) -> list[dict]:
        """All chunks for a specific research session."""
        try:
            results = self._table.search().where(
                f"run_id = '{run_id}'"
            ).to_list()
            return results
        except Exception as e:
            logger.error(f"query_by_run failed: {e}")
            return []

    def query_by_ids(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        ids_str = ", ".join(f"'{i}'" for i in ids)
        try:
            results = self._table.search().where(
                f"chunk_id IN ({ids_str})"
            ).to_list()
            return [
                {"id": r["chunk_id"], "document": r["content"], "metadata": r}
                for r in results
            ]
        except Exception as e:
            logger.error(f"query_by_ids failed: {e}")
            return []

    @staticmethod
    def stable_id(*parts: str) -> str:
        """Deterministic ID from content. No positional index, no nonce."""
        normalized = "::".join((p or "").strip().lower() for p in parts)
        return hashlib.sha256(normalized.encode()).hexdigest()[:24]

    def clear(self) -> None:
        self._db.drop_table(self.table_name)
        self._table = self._init_table()
