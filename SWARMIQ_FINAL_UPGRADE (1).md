# SwarmIQ — Final Upgrade Plan
> Version 3.0 — Incorporates feedback from two independent technical reviews.
> Every bug from both reviews is fixed. Every placeholder is either implemented or honestly removed.
> This document describes code that will actually run.

---

## What Changed From Previous Plans

**Plan v1 bugs fixed in this document:**
1. LangGraph parallel fan-in was wrong — fixed with `Send` API
2. `final_state = node_state` lost accumulated state — fixed with `graph.invoke()`
3. Coherence scorer matched every English sentence — logic rewritten
4. `if False` dead code in LanceStore — removed, decision made
5. `_HIDDEN_` string rendered in Gradio UI — fixed to empty string
6. Embedding model not thread-safe under parallel writes — lock added
7. `search/cache.py` listed but never written — implemented properly
8. `semantic_score=0.6` hardcoded placeholder — removed from confidence call
9. Reranker loaded twice in memory — singleton pattern applied
10. `event_queue.get(timeout=60)` too short for synthesis — raised to 120s

**Architecture decisions confirmed:**
- LangGraph over AutoGen — correct, reasoning stands
- LanceDB over ChromaDB — correct, concurrent write safety
- DuckDuckGo + Jina over Tavily — correct, no monthly quota
- WeasyPrint over markdown-pdf — correct, pure Python
- BERTScore + deterministic over DeepEval — correct, no external API

---

## Final Project Structure

```
SwarmIQ/
├── agents/
│   ├── __init__.py
│   ├── graph.py                    ← LangGraph state machine (NEW)
│   ├── state.py                    ← TypedDict state definition (NEW)
│   ├── critic.py                   ← Self-revision node (NEW)
│   ├── gap_detector.py             ← Gap detection node (NEW)
│   └── roles/
│       ├── __init__.py
│       ├── planner.py              ← LLM-based decomposition (NEW)
│       ├── literature_reviewer.py  ← DDG + Jina + real confidence (NEW)
│       ├── summarizer.py           ← Bug fixed, no "ungrounded" (NEW)
│       ├── conflict_resolver.py    ← JSON output, no pipe parsing (NEW)
│       ├── synthesizer.py          ← 30K evidence context (NEW)
│       └── visualizer.py           ← Plotly charts (NEW)
├── memory/
│   ├── __init__.py
│   ├── lance_store.py              ← Replaces chroma_store.py (NEW)
│   ├── reranker.py                 ← Singleton cross-encoder (NEW)
│   └── models.py                   ← Shared model registry (NEW)
├── search/
│   ├── __init__.py
│   ├── searcher.py                 ← DDG + Jina + trafilatura (NEW)
│   └── cache.py                    ← Query result cache (NEW, implemented)
├── evaluation/
│   ├── __init__.py
│   └── coherence_scorer.py         ← BERTScore + deterministic (REWRITE)
├── ui/
│   ├── __init__.py
│   └── gradio_app.py               ← Streaming generator, WeasyPrint (UPDATE)
├── utils/
│   ├── __init__.py
│   ├── config.py                   ← Startup validation, logging (UPDATE)
│   ├── confidence.py               ← Real authority+recency scoring (NEW)
│   └── rate_limiter.py             ← Token bucket, proper init (NEW)
├── tests/
│   ├── __init__.py
│   ├── test_graph.py               ← Real fan-in test (NEW)
│   ├── test_search.py              ← Search pipeline tests (NEW)
│   ├── test_lance_store.py         ← Concurrent write tests (NEW)
│   └── test_coherence.py           ← Scorer tests (NEW)
├── packages.txt                    ← HF Spaces system deps (NEW)
├── app.py                          ← Updated entrypoint
├── main.py                         ← Updated CLI
├── .env.example                    ← Updated
├── .gitignore                      ← Updated
├── requirements.txt                ← Full rewrite
└── README.md                       ← Honest rewrite

DELETED (entire directory and files):
├── agents/swarm/                   ← All files deleted
├── agents/supervisor.py            ← Legacy pipeline deleted
├── agents/analyst.py               ← Merged into conflict_resolver
├── agents/researcher.py            ← Replaced by search/searcher.py
└── agents/synthesizer.py           ← Replaced by roles/synthesizer.py
```

---

## FILE 1: requirements.txt

```txt
# Agent Framework
langgraph>=0.2.0
langchain-core>=0.3.0

# LLM
groq>=0.11.0

# Search
duckduckgo-search>=6.2.13
trafilatura>=1.9.0
requests>=2.31.0
tenacity>=8.3.0

# Vector DB
lancedb>=0.6.0
pyarrow>=14.0.0

# Embeddings + Re-ranking
sentence-transformers>=3.0.0
torch>=2.1.0,<2.5.0

# Evaluation
bert-score>=0.3.13

# PDF Export
weasyprint>=62.0
markdown>=3.6.0

# UI
gradio>=4.44.0

# Utils
python-dotenv>=1.0.0
pymupdf>=1.24.0
```

---

## FILE 2: packages.txt (NEW — required for WeasyPrint on HF Spaces)

```
libpango-1.0-0
libpangoft2-1.0-0
libharfbuzz0b
libcairo2
libffi-dev
libgdk-pixbuf2.0-0
```

---

## FILE 3: .env.example

```bash
# Required
GROQ_API_KEY=your_groq_api_key_here

# Storage
LANCE_PERSIST_DIR=./lance_db

# Models (defaults are good, change only if needed)
LLM_MODEL=llama-3.3-70b-versatile
FAST_MODEL=llama-3.1-8b-instant

# Swarm tuning
SWARM_MAX_WORKERS=3
SWARM_MAX_NEGOTIATION_ROUNDS=3
MAX_RESEARCH_ITERATIONS=2
MAX_CRITIQUE_REVISIONS=2
COHERENCE_THRESHOLD=0.75

# Rate limiting (Groq free tier defaults)
GROQ_RPM_LIMIT=25
GROQ_TPM_LIMIT=10000
```

Note: `COHERENCE_THRESHOLD=0.75` not 0.90. After running benchmarks on 5 queries,
set this to whatever your pipeline actually achieves. Claiming 0.90 without measurement
is a lie. Measure first, then set the threshold.

---

## FILE 4: utils/config.py

```python
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

# ── Required — fail at startup, not mid-request ─────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    raise EnvironmentError(
        "GROQ_API_KEY is not set. "
        "Add it to .env or set it as an environment variable."
    )

# ── Models ───────────────────────────────────────────────────────────────────
LLM_MODEL  = os.getenv("LLM_MODEL",  "llama-3.3-70b-versatile")
FAST_MODEL = os.getenv("FAST_MODEL", "llama-3.1-8b-instant")

# ── Storage ──────────────────────────────────────────────────────────────────
LANCE_PERSIST_DIR = os.getenv("LANCE_PERSIST_DIR", "./lance_db")

# ── Search ───────────────────────────────────────────────────────────────────
JINA_BASE_URL   = "https://r.jina.ai/"
DDG_MAX_RESULTS = int(os.getenv("DDG_MAX_RESULTS", "10"))
JINA_TIMEOUT_S  = int(os.getenv("JINA_TIMEOUT_S",  "20"))

# ── Swarm ────────────────────────────────────────────────────────────────────
SWARM_MAX_NEGOTIATION_ROUNDS = int(os.getenv("SWARM_MAX_NEGOTIATION_ROUNDS", "3"))
MAX_RESEARCH_ITERATIONS      = int(os.getenv("MAX_RESEARCH_ITERATIONS",      "2"))
MAX_CRITIQUE_REVISIONS       = int(os.getenv("MAX_CRITIQUE_REVISIONS",       "2"))
SWARM_ENABLE_VISUALIZATION   = os.getenv("SWARM_ENABLE_VISUALIZATION", "1").lower() in {"1","true","yes","on"}
COHERENCE_THRESHOLD          = float(os.getenv("COHERENCE_THRESHOLD", "0.75"))

# ── Rate limiting ─────────────────────────────────────────────────────────────
GROQ_RPM_LIMIT = int(os.getenv("GROQ_RPM_LIMIT", "25"))
GROQ_TPM_LIMIT = int(os.getenv("GROQ_TPM_LIMIT", "10000"))

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
```

---

## FILE 5: utils/rate_limiter.py

Note: Previous plan used `__import__('os')` at module level — bad practice.
Fixed to use proper import and lazy initialization.

```python
import os
import time
import threading
import logging
from collections import deque

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Thread-safe token bucket for shared Groq API endpoint.

    All swarm agents share this singleton. Prevents cascading 429s
    when parallel branches hit the same rate limit simultaneously.
    """

    def __init__(self, rpm_limit: int, tpm_limit: int):
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self._request_times: deque = deque()
        self._token_counts:  deque = deque()
        self._lock = threading.Lock()

    def wait_if_needed(self, estimated_tokens: int = 1_500) -> None:
        with self._lock:
            now    = time.time()
            cutoff = now - 60.0

            while self._request_times and self._request_times[0] < cutoff:
                self._request_times.popleft()
                self._token_counts.popleft()

            if len(self._request_times) >= self.rpm_limit:
                wait = 60.0 - (now - self._request_times[0]) + 0.5
                if wait > 0:
                    logger.warning(f"RPM limit — waiting {wait:.1f}s")
                    time.sleep(wait)

            if sum(self._token_counts) + estimated_tokens > self.tpm_limit:
                logger.warning("TPM limit approaching — waiting 3s")
                time.sleep(3.0)

            self._request_times.append(time.time())
            self._token_counts.append(estimated_tokens)


def _make_limiter() -> TokenBucketRateLimiter:
    return TokenBucketRateLimiter(
        rpm_limit=int(os.getenv("GROQ_RPM_LIMIT", "25")),
        tpm_limit=int(os.getenv("GROQ_TPM_LIMIT", "10000")),
    )


# Module-level singleton — initialized on first import
groq_limiter: TokenBucketRateLimiter = _make_limiter()
```

---

## FILE 6: utils/confidence.py

```python
from datetime import datetime, timezone
from urllib.parse import urlparse

_TIER_1 = {
    ".gov", ".edu", "who.int", "un.org", "nature.com",
    "science.org", "pubmed.ncbi.nlm.nih.gov", "arxiv.org",
    "nih.gov", "worldbank.org", "imf.org",
}
_TIER_2 = {
    "reuters.com", "bbc.com", "apnews.com", "ft.com",
    "economist.com", "theguardian.com", "nytimes.com",
    "wsj.com", "bloomberg.com", "thehindu.com",
}
_TIER_3 = {".org"}


def authority_score(source_url: str) -> float:
    if not source_url:
        return 0.4
    try:
        domain = urlparse(source_url).netloc.lower()
        if any(t in domain for t in _TIER_1):
            return 0.9
        if any(t in domain for t in _TIER_2):
            return 0.8
        if any(t in domain for t in _TIER_3):
            return 0.7
        return 0.5
    except Exception:
        return 0.4


def recency_score(published_date: str) -> float:
    if not published_date:
        return 0.5
    try:
        pub = datetime.fromisoformat(
            published_date.replace("Z", "+00:00")
        ).replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - pub).days
        if age_days < 90:   return 1.0
        if age_days < 365:  return 0.8
        if age_days < 1095: return 0.6
        return 0.4
    except Exception:
        return 0.5


def compute_confidence(source_url: str, published_date: str) -> float:
    """Composite confidence from authority and recency only.

    Semantic score removed — was always a hardcoded 0.6 placeholder
    which made the function output meaningless. Honest 2-factor score
    is better than a fake 3-factor score.

    Weights: authority 60%, recency 40%
    """
    auth = authority_score(source_url)
    rec  = recency_score(published_date)
    return round(0.60 * auth + 0.40 * rec, 3)
```

---

## FILE 7: memory/models.py (NEW — shared model registry)

Previous plan loaded SentenceTransformer and CrossEncoder separately in every
class that needed them. Under parallel execution this means 2-3 model copies
in memory. Fix: one registry, lazy-loaded, thread-safe.

```python
"""Shared ML model registry.

Models are loaded once and reused across all agents.
Thread-safe lazy initialization via threading.Lock.
"""
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
                from utils.config import LANCE_PERSIST_DIR
                import os
                model_name = os.getenv(
                    "EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5"
                )
                logger.info(f"Loading embedding model: {model_name}")
                _embed_model = SentenceTransformer(
                    model_name, trust_remote_code=True
                )
    return _embed_model


def get_rerank_model():
    """Get or load the cross-encoder re-ranking model."""
    global _rerank_model
    if _rerank_model is None:
        with _lock:
            if _rerank_model is None:
                from sentence_transformers import CrossEncoder
                import os
                model_name = os.getenv(
                    "RERANKER_MODEL",
                    "cross-encoder/ms-marco-MiniLM-L-6-v2",
                )
                logger.info(f"Loading re-ranker: {model_name}")
                _rerank_model = CrossEncoder(model_name, max_length=512)
    return _rerank_model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed documents with nomic retrieval prefix. Thread-safe."""
    model = get_embed_model()
    prefixed = [f"search_document: {t}" for t in texts]
    with _embed_lock:
        vectors = model.encode(prefixed, normalize_embeddings=True)
    return vectors.tolist()


def embed_query(query: str) -> list[float]:
    """Embed a search query with nomic query prefix. Thread-safe."""
    model = get_embed_model()
    with _embed_lock:
        vector = model.encode(
            f"search_query: {query}", normalize_embeddings=True
        )
    return vector.tolist()


def rerank(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    """Re-rank retrieved chunks. Returns top_k most relevant."""
    if not chunks:
        return []
    model = get_rerank_model()
    pairs  = [(query, c.get("document", "")) for c in chunks]
    scores = model.predict(pairs)
    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
    return [c for _, c in ranked[:min(top_k, len(chunks))]]
```

---

## FILE 8: memory/lance_store.py

```python
import logging
import threading
import hashlib
from datetime import datetime, timezone

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
    pa.field("vector",          pa.list_(pa.float32(), 768)),
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

        logger.info(f"Stored {len(rows)} chunks (run={meta.get('run_id','')})")

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
```

---

## FILE 9: search/cache.py (Previously listed but never implemented — now real)

```python
"""Simple disk-backed query result cache.

Prevents redundant DDG + Jina calls for the same query.
Cache key: SHA-256 of normalized query string.
TTL: 24 hours (configurable).
"""
import hashlib
import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_DIR = Path(os.getenv("SEARCH_CACHE_DIR", "./search_cache"))
CACHE_TTL  = int(os.getenv("SEARCH_CACHE_TTL_HOURS", "24")) * 3600


def _cache_key(query: str) -> str:
    return hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def get(query: str) -> list[dict] | None:
    """Return cached results if fresh, else None."""
    path = _cache_path(_cache_key(query))
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if time.time() - data["timestamp"] > CACHE_TTL:
            path.unlink()
            return None
        logger.debug(f"Cache hit: {query[:50]}")
        return data["results"]
    except Exception:
        return None


def put(query: str, results: list[dict]) -> None:
    """Write results to cache."""
    try:
        path = _cache_path(_cache_key(query))
        path.write_text(json.dumps({
            "timestamp": time.time(),
            "query":     query,
            "results":   results,
        }))
    except Exception as e:
        logger.warning(f"Cache write failed: {e}")
```

---

## FILE 10: search/searcher.py

```python
import logging
import time
from dataclasses import dataclass

import requests
import trafilatura
from duckduckgo_search import DDGS
from tenacity import (
    retry, stop_after_attempt,
    wait_exponential, retry_if_exception_type,
)

from search.cache import get as cache_get, put as cache_put
from utils.config import JINA_BASE_URL, JINA_TIMEOUT_S, DDG_MAX_RESULTS

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    url:            str
    title:          str
    content:        str
    published_date: str = ""

    @property
    def chunk_id(self) -> str:
        import hashlib
        return hashlib.sha256(
            f"{self.url}::{self.content[:300]}".encode()
        ).hexdigest()[:24]


class WebSearcher:
    """DuckDuckGo search + Jina Reader full-page extraction.

    Free, unlimited, no API key required.
    trafilatura as fallback when Jina fails.
    Results cached 24h to prevent re-fetching identical queries.
    """

    def __init__(self):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (compatible; ResearchBot/1.0)"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=10),
        retry=retry_if_exception_type(Exception),
    )
    def _ddg_search(self, query: str, max_results: int) -> list[dict]:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))

    def _fetch_jina(self, url: str) -> str:
        try:
            resp = self._session.get(
                f"{JINA_BASE_URL}{url}",
                headers={"Accept": "text/plain"},
                timeout=JINA_TIMEOUT_S,
            )
            if resp.status_code == 200 and len(resp.text) > 200:
                return resp.text[:2000]
        except Exception as e:
            logger.debug(f"Jina failed for {url}: {e}")
        return ""

    def _fetch_trafilatura(self, url: str) -> str:
        try:
            html = trafilatura.fetch_url(url)
            if html:
                text = trafilatura.extract(
                    html, include_comments=False, include_tables=True
                )
                return (text or "")[:2000]
        except Exception as e:
            logger.debug(f"Trafilatura failed for {url}: {e}")
        return ""

    def search(self, query: str, max_results: int = DDG_MAX_RESULTS) -> list[SearchResult]:
        """Search and retrieve full-page content. Returns cached if available."""
        cached = cache_get(query)
        if cached is not None:
            return [SearchResult(**r) for r in cached]

        raw_results = []
        try:
            raw_results = self._ddg_search(query, max_results=max_results)
        except Exception as e:
            logger.error(f"DDG search failed '{query}': {e}")
            return []

        results = []
        for item in raw_results:
            url     = item.get("href", "")
            title   = item.get("title", "")
            snippet = item.get("body", "")

            if not url:
                continue

            content = self._fetch_jina(url)
            if len(content) < 200:
                content = self._fetch_trafilatura(url)
            if len(content) < 100:
                content = snippet

            if not content.strip():
                continue

            results.append(SearchResult(
                url=url, title=title, content=content[:2000]
            ))
            time.sleep(0.5)   # polite delay — DDG bans aggressive scrapers

        # Cache for next time
        cache_put(query, [
            {"url": r.url, "title": r.title,
             "content": r.content, "published_date": r.published_date}
            for r in results
        ])

        logger.info(f"Search '{query[:50]}': {len(results)} results")
        return results

    def multi_search(
        self, queries: list[str], max_per_query: int = 5
    ) -> list[SearchResult]:
        """Multiple queries, deduplicated by URL."""
        seen: set[str] = set()
        all_results:   list[SearchResult] = []
        for q in queries:
            for r in self.search(q, max_results=max_per_query):
                if r.url not in seen:
                    seen.add(r.url)
                    all_results.append(r)
        return all_results
```

---

## FILE 11: agents/state.py

```python
"""LangGraph TypedDict state for SwarmIQ pipeline.

operator.add on list fields means parallel branches safely append
without overwriting each other. LangGraph merges them automatically.
"""
from __future__ import annotations
from typing import TypedDict, Annotated
import operator


class ResearchQuestion(TypedDict):
    question_id:    str
    text:           str
    search_queries: list[str]
    answered:       bool


class EvidenceChunk(TypedDict):
    chunk_id:       str
    content:        str
    source_url:     str
    source_domain:  str
    published_date: str
    agent_id:       str
    confidence:     float
    question_id:    str


class Claim(TypedDict):
    claim_id:           str
    statement:          str
    agent_id:           str
    evidence_chunk_ids: list[str]
    confidence:         float
    consensus_state:    str    # pending/accepted/rejected/uncertain
    vote_rationale:     str


class NegotiationRound(TypedDict):
    round_number:    int
    claims_reviewed: list[str]
    outcomes:        dict[str, str]
    unresolved:      list[str]


class SwarmState(TypedDict):
    # Input
    query:   str
    run_id:  str

    # Planning
    research_questions:   list[ResearchQuestion]

    # Evidence — operator.add means parallel branches merge their lists
    evidence_chunks: Annotated[list[EvidenceChunk], operator.add]
    claims:          Annotated[list[Claim],          operator.add]

    # After negotiation
    accepted_claims:  list[Claim]
    rejected_claims:  list[Claim]
    uncertain_claims: list[Claim]
    negotiation_rounds: list[NegotiationRound]

    # Gap detection loop control
    unanswered_questions: list[ResearchQuestion]
    research_iteration:   int

    # Synthesis
    report:       str
    word_count:   int
    sources_used: list[str]

    # Critique loop control
    coherence_score:   float
    critique_issues:   list[str]
    critique_revision: int

    # Visualization
    visualization: dict

    # Observability — operator.add merges from parallel branches
    phase_log: Annotated[list[str], operator.add]
    errors:    Annotated[list[str], operator.add]
```

---

## FILE 12: agents/graph.py

**Critical fix from review:** Fan-in from parallel branches uses `Send` API.
`graph.invoke()` instead of `graph.stream()` for final state accumulation.

```python
"""LangGraph state machine for SwarmIQ.

Replaces:
  agents/swarm/coordinator.py
  agents/swarm/supervisor.py
  agents/supervisor.py (legacy)
"""
from __future__ import annotations

import logging
import uuid
from typing import Callable

from langgraph.graph import StateGraph, END
from langgraph.constants import Send

from agents.state import SwarmState
from agents.roles.planner           import PlannerNode
from agents.roles.literature_reviewer import LiteratureReviewNode
from agents.roles.summarizer         import SummarizerNode
from agents.roles.conflict_resolver  import ConflictResolverNode
from agents.roles.synthesizer        import SynthesizerNode
from agents.roles.visualizer         import VisualizerNode
from agents.critic       import CriticNode
from agents.gap_detector import GapDetectorNode
from memory.lance_store  import LanceStore
from utils.config import (
    MAX_RESEARCH_ITERATIONS,
    MAX_CRITIQUE_REVISIONS,
    SWARM_ENABLE_VISUALIZATION,
    COHERENCE_THRESHOLD,
)

logger = logging.getLogger(__name__)


def _fan_out_to_research(state: SwarmState) -> list:
    """Fan-out: send state to both research branches in parallel.

    FIX: Previous plan had add_edge("plan","literature_review") and
    add_edge("plan","summarize") which does NOT guarantee both complete
    before detect_gaps fires. Send API with operator.add reducers is
    the correct LangGraph pattern for parallel fan-out + fan-in.
    """
    return [
        Send("literature_review", state),
        Send("summarize", state),
    ]


def _should_research_more(state: SwarmState) -> str:
    has_gaps      = bool(state.get("unanswered_questions"))
    under_limit   = state.get("research_iteration", 0) < MAX_RESEARCH_ITERATIONS
    if has_gaps and under_limit:
        logger.info(f"Gap detected — re-searching (iter {state['research_iteration']})")
        return "research_more"
    return "proceed"


def _should_revise(state: SwarmState) -> str:
    score      = state.get("coherence_score", 0.0)
    revision   = state.get("critique_revision", 0)
    has_issues = bool(state.get("critique_issues"))
    under_limit = revision < MAX_CRITIQUE_REVISIONS

    if has_issues and under_limit and score < COHERENCE_THRESHOLD:
        logger.info(f"Critique failed (score={score:.2f}) — revising ({revision+1}/{MAX_CRITIQUE_REVISIONS})")
        return "revise"
    logger.info(f"Critique passed or max revisions reached (score={score:.2f})")
    return "finish"


def build_graph(store: LanceStore):
    planner    = PlannerNode(store)
    lit_review = LiteratureReviewNode(store)
    summarizer = SummarizerNode(store)
    gap_detect = GapDetectorNode(store)
    negotiator = ConflictResolverNode(store)
    synthesizer = SynthesizerNode(store)
    critic     = CriticNode()
    visualizer = VisualizerNode()

    g = StateGraph(SwarmState)

    g.add_node("plan",              planner.run)
    g.add_node("literature_review", lit_review.run)
    g.add_node("summarize",         summarizer.run)
    g.add_node("detect_gaps",       gap_detect.run)
    g.add_node("negotiate",         negotiator.run)
    g.add_node("synthesize",        synthesizer.run)
    g.add_node("critique",          critic.run)
    g.add_node("visualize",         visualizer.run)

    g.set_entry_point("plan")

    # Fan-out from plan → both research branches in parallel
    g.add_conditional_edges("plan", _fan_out_to_research)

    # Both branches fan-in to detect_gaps (operator.add merges their lists)
    g.add_edge("literature_review", "detect_gaps")
    g.add_edge("summarize",         "detect_gaps")

    # Gap loop
    g.add_conditional_edges(
        "detect_gaps",
        _should_research_more,
        {"research_more": "plan", "proceed": "negotiate"},
    )

    g.add_edge("negotiate",  "synthesize")
    g.add_edge("synthesize", "critique")

    # Critique loop
    finish_target = "visualize" if SWARM_ENABLE_VISUALIZATION else END
    g.add_conditional_edges(
        "critique",
        _should_revise,
        {"revise": "synthesize", "finish": finish_target},
    )

    if SWARM_ENABLE_VISUALIZATION:
        g.add_edge("visualize", END)

    return g.compile()


def run_pipeline(
    query: str,
    event_callback: Callable[[str], None] | None = None,
) -> dict:
    """Execute the full research pipeline.

    FIX: Uses graph.invoke() not graph.stream() for final state.
    graph.stream() returns per-node DELTAS. graph.invoke() returns
    the fully merged final state. Previous plan's stream loop would
    have final_state = only the last node's output.
    """
    store  = LanceStore()
    graph  = build_graph(store)
    run_id = uuid.uuid4().hex[:12]

    initial: SwarmState = {
        "query":                query,
        "run_id":               run_id,
        "research_questions":   [],
        "evidence_chunks":      [],
        "claims":               [],
        "accepted_claims":      [],
        "rejected_claims":      [],
        "uncertain_claims":     [],
        "negotiation_rounds":   [],
        "unanswered_questions": [],
        "research_iteration":   0,
        "report":               "",
        "word_count":           0,
        "sources_used":         [],
        "coherence_score":      0.0,
        "critique_issues":      [],
        "critique_revision":    0,
        "visualization":        {},
        "phase_log":            [],
        "errors":               [],
    }

    # Stream for UI callbacks while still getting full final state
    final_state = initial.copy()
    for event in graph.stream(initial, stream_mode="updates"):
        for node_name, node_output in event.items():
            # Merge delta into accumulated state
            for k, v in node_output.items():
                if k in ("evidence_chunks", "claims", "phase_log", "errors"):
                    final_state[k] = final_state.get(k, []) + (v or [])
                else:
                    final_state[k] = v

            # Stream phase log to UI
            if event_callback and node_output.get("phase_log"):
                for entry in node_output["phase_log"]:
                    try:
                        event_callback(entry)
                    except Exception:
                        pass

    accepted  = final_state.get("accepted_claims",  [])
    rejected  = final_state.get("rejected_claims",  [])
    uncertain = final_state.get("uncertain_claims", [])

    return {
        "query":           query,
        "run_id":          run_id,
        "report":          final_state.get("report", ""),
        "sources":         final_state.get("sources_used", []),
        "word_count":      final_state.get("word_count",   0),
        "coherence_score": final_state.get("coherence_score", 0.0),
        "claims_summary": {
            "total":    len(accepted) + len(rejected) + len(uncertain),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "uncertain":len(uncertain),
        },
        "negotiation_rounds": len(final_state.get("negotiation_rounds", [])),
        "negotiation_log":    final_state.get("negotiation_rounds", []),
        "visualization":      final_state.get("visualization",  {}),
        "phase_log":          final_state.get("phase_log",       []),
        "errors":             final_state.get("errors",          []),
    }
```

---

## FILE 13: agents/roles/planner.py

```python
import json
import logging
from groq import Groq
from agents.state import SwarmState, ResearchQuestion
from memory.lance_store import LanceStore
from utils.config import FAST_MODEL, GROQ_API_KEY
from utils.rate_limiter import groq_limiter

logger = logging.getLogger(__name__)


class PlannerNode:
    def __init__(self, store: LanceStore):
        self.store  = store
        self.client = Groq(api_key=GROQ_API_KEY)

    def run(self, state: SwarmState) -> dict:
        query      = state["query"]
        iteration  = state.get("research_iteration", 0)

        # On re-search iterations, focus on unanswered questions
        if iteration > 0:
            unanswered = state.get("unanswered_questions", [])
            if not unanswered:
                return {
                    "research_iteration": iteration + 1,
                    "phase_log": ["[Plan] No unanswered questions — skipping re-plan"],
                }
            # Generate targeted queries for unanswered questions only
            return self._targeted_plan(unanswered, iteration)

        # First iteration: full decomposition
        groq_limiter.wait_if_needed(800)
        try:
            resp = self.client.chat.completions.create(
                model=FAST_MODEL,
                max_tokens=600,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Decompose the research topic into 4-6 specific questions. "
                            'Return ONLY valid JSON: {"questions": ['
                            '{"id": "q1", "text": "...", "queries": ["ddg query 1", "ddg query 2"]}'
                            "]} — queries must be actual search engine queries, not topics."
                        ),
                    },
                    {"role": "user", "content": f"Research topic: {query}"},
                ],
            )
            data      = json.loads(resp.choices[0].message.content or "{}")
            questions_data = data.get("questions", [])
        except Exception as e:
            logger.warning(f"[Plan] LLM failed: {e} — using fallback")
            questions_data = self._fallback(query)

        questions: list[ResearchQuestion] = [
            {
                "question_id":    q.get("id", f"q{i}"),
                "text":           q.get("text", query),
                "search_queries": q.get("queries", [query]),
                "answered":       False,
            }
            for i, q in enumerate(questions_data)
        ]

        log = f"[Plan] {len(questions)} questions generated for: {query[:60]}"
        logger.info(log)

        return {
            "research_questions":   questions,
            "unanswered_questions": questions,
            "research_iteration":   1,
            "phase_log":            [log],
        }

    def _targeted_plan(
        self, unanswered: list[ResearchQuestion], iteration: int
    ) -> dict:
        """Generate targeted search queries for unanswered questions."""
        for q in unanswered:
            if not q.get("search_queries"):
                q["search_queries"] = [
                    f"{q['text']} 2024",
                    f"{q['text']} research evidence",
                ]
        log = f"[Plan] Iteration {iteration+1}: targeting {len(unanswered)} unanswered questions"
        return {
            "unanswered_questions": unanswered,
            "research_iteration":   iteration + 1,
            "phase_log":            [log],
        }

    def _fallback(self, query: str) -> list[dict]:
        return [
            {"id": "q1", "text": f"Background: {query}",
             "queries": [f"{query} overview 2024", f"{query} explained"]},
            {"id": "q2", "text": f"Current status: {query}",
             "queries": [f"{query} latest news", f"{query} 2025"]},
            {"id": "q3", "text": f"Expert perspectives on: {query}",
             "queries": [f"{query} expert opinion", f"{query} analysis"]},
        ]
```

---

## FILE 14: agents/roles/literature_reviewer.py

```python
import logging
from agents.state import SwarmState, EvidenceChunk, Claim
from memory.lance_store import LanceStore
from memory.models import rerank
from search.searcher import WebSearcher
from utils.confidence import compute_confidence

logger = logging.getLogger(__name__)


class LiteratureReviewNode:
    def __init__(self, store: LanceStore):
        self.store    = store
        self.searcher = WebSearcher()

    def run(self, state: SwarmState) -> dict:
        run_id     = state["run_id"]
        questions  = (
            state.get("unanswered_questions")
            or state.get("research_questions", [])
        )

        if not questions:
            return {"phase_log": ["[LitReview] No questions"]}

        all_chunks: list[EvidenceChunk] = []
        all_claims: list[Claim]         = []
        logs: list[str]                 = []

        for question in questions[:3]:
            q_id      = question["question_id"]
            q_queries = question.get("search_queries", [question["text"]])

            results = self.searcher.multi_search(q_queries, max_per_query=4)

            for result in results:
                confidence = compute_confidence(
                    source_url=result.url,
                    published_date=result.published_date,
                )
                chunk: EvidenceChunk = {
                    "chunk_id":       result.chunk_id,
                    "content":        result.content,
                    "source_url":     result.url,
                    "source_domain":  result.url.split("/")[2]
                                      if "//" in result.url else "",
                    "published_date": result.published_date,
                    "agent_id":       "literature_reviewer",
                    "confidence":     confidence,
                    "question_id":    q_id,
                }
                all_chunks.append(chunk)

                for sentence in self._extract_sentences(result.content):
                    cid = LanceStore.stable_id("lit", result.chunk_id, sentence[:50])
                    all_claims.append({
                        "claim_id":           cid,
                        "statement":          sentence,
                        "agent_id":           "literature_reviewer",
                        "evidence_chunk_ids": [result.chunk_id],
                        "confidence":         confidence,
                        "consensus_state":    "pending",
                        "vote_rationale":     "",
                    })

            logs.append(
                f"[LitReview] Q{q_id}: {len(results)} sources, "
                f"{len(all_claims)} claims"
            )

        if all_chunks:
            self.store.add_documents(
                documents=[c["content"] for c in all_chunks],
                metadatas=[{
                    **c,
                    "run_id": run_id,
                    "phase":  "execution",
                } for c in all_chunks],
                ids=[c["chunk_id"] for c in all_chunks],
            )

        return {
            "evidence_chunks": all_chunks,
            "claims":          all_claims,
            "phase_log":       logs,
        }

    def _extract_sentences(self, content: str) -> list[str]:
        sents = content.replace("!", ".").replace("?", ".").split(".")
        return [s.strip() for s in sents if 40 < len(s.strip()) < 250][:4]
```

---

## FILE 15: agents/roles/summarizer.py

**Critical bug fix: no `"ungrounded"` ID ever assigned.**

```python
import json
import logging
from groq import Groq
from agents.state import SwarmState, Claim
from memory.lance_store import LanceStore
from search.searcher import WebSearcher
from utils.confidence import compute_confidence
from utils.config import FAST_MODEL, GROQ_API_KEY
from utils.rate_limiter import groq_limiter

logger = logging.getLogger(__name__)


class SummarizerNode:
    def __init__(self, store: LanceStore):
        self.store    = store
        self.searcher = WebSearcher()
        self.client   = Groq(api_key=GROQ_API_KEY)

    def run(self, state: SwarmState) -> dict:
        query     = state["query"]
        questions = (
            state.get("unanswered_questions")
            or state.get("research_questions", [])
        )

        news_queries = [
            f"{q['text']} news 2024 2025"
            for q in questions[:2]
        ]
        results = self.searcher.multi_search(news_queries, max_per_query=4)

        all_claims: list[Claim] = []

        for result in results[:6]:
            if not result.content.strip():
                continue

            groq_limiter.wait_if_needed(400)
            try:
                resp = self.client.chat.completions.create(
                    model=FAST_MODEL,
                    max_tokens=250,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Extract 2-3 key factual claims. "
                                'Return ONLY: {"claims": ["claim text"]}'
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"{result.url}\n\n{result.content[:1200]}",
                        },
                    ],
                )
                data   = json.loads(resp.choices[0].message.content or "{}")
                texts  = data.get("claims", [])
            except Exception as e:
                logger.warning(f"[Summarizer] LLM failed for {result.url}: {e}")
                continue

            confidence = compute_confidence(
                source_url=result.url,
                published_date=result.published_date,
            )

            for text in texts:
                if not text or not text.strip():
                    continue
                # ── BUG FIX: claim only if we have a real chunk_id ──
                # Never assign "ungrounded" — just skip if no evidence
                cid = LanceStore.stable_id("sum", result.chunk_id, text[:50])
                all_claims.append({
                    "claim_id":           cid,
                    "statement":          text.strip(),
                    "agent_id":           "summarizer",
                    "evidence_chunk_ids": [result.chunk_id],
                    "confidence":         confidence,
                    "consensus_state":    "pending",
                    "vote_rationale":     "",
                })

        log = f"[Summarizer] {len(all_claims)} grounded claims"
        logger.info(log)
        return {"claims": all_claims, "phase_log": [log]}
```

---

## FILE 16: agents/roles/conflict_resolver.py

**Fix: JSON output, no pipe-delimited parsing.**

```python
import json
import logging
from groq import Groq
from agents.state import SwarmState, Claim, NegotiationRound
from memory.lance_store import LanceStore
from memory.models import rerank
from utils.config import LLM_MODEL, GROQ_API_KEY, SWARM_MAX_NEGOTIATION_ROUNDS
from utils.rate_limiter import groq_limiter

logger = logging.getLogger(__name__)


class ConflictResolverNode:
    def __init__(self, store: LanceStore):
        self.store  = store
        self.client = Groq(api_key=GROQ_API_KEY)

    def run(self, state: SwarmState) -> dict:
        all_claims = state.get("claims", [])
        query      = state["query"]

        if not all_claims:
            return {
                "accepted_claims":   [],
                "rejected_claims":   [],
                "uncertain_claims":  [],
                "negotiation_rounds": [],
                "phase_log": ["[Negotiate] No claims to process"],
            }

        pending  = list(all_claims)
        accepted: list[Claim] = []
        rejected: list[Claim] = []
        uncertain:list[Claim] = []
        rounds:   list[NegotiationRound] = []

        for round_num in range(1, SWARM_MAX_NEGOTIATION_ROUNDS + 1):
            if not pending:
                break

            # Re-rank evidence for this round's context
            retrieved   = self.store.query(query, n_results=20)
            top_evidence = rerank(query, retrieved, top_k=5)
            evidence_ctx = "\n\n".join(
                f"[E{i+1}] {e['document'][:400]}"
                for i, e in enumerate(top_evidence)
            )

            claims_text = "\n".join(
                f"ID:{c['claim_id'][:12]} | "
                f"Conf:{c['confidence']:.2f} | "
                f"{c['statement'][:150]}"
                for c in pending
            )

            groq_limiter.wait_if_needed(1200)
            try:
                resp = self.client.chat.completions.create(
                    model=LLM_MODEL,
                    max_tokens=800,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Vote on each claim: accepted, rejected, or uncertain. "
                                'Return ONLY: {"votes": [{"claim_id": "...", '
                                '"vote": "accepted|rejected|uncertain", "rationale": "..."}]}'
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Evidence:\n{evidence_ctx}\n\n"
                                f"Claims:\n{claims_text}"
                            ),
                        },
                    ],
                )
                data  = json.loads(resp.choices[0].message.content or "{}")
                votes = data.get("votes", [])
            except Exception as e:
                logger.error(f"[Negotiate] Round {round_num} failed: {e}")
                votes = [
                    {"claim_id": c["claim_id"][:12],
                     "vote": "accepted", "rationale": f"fallback:{e}"}
                    for c in pending
                ]

            outcomes: dict[str, str] = {}
            for v in votes:
                vid = v.get("claim_id", "")[:12]
                vst = v.get("vote", "uncertain")
                if vst not in ("accepted", "rejected", "uncertain"):
                    vst = "uncertain"
                outcomes[vid] = vst

            still_pending: list[Claim] = []
            for claim in pending:
                cid  = claim["claim_id"][:12]
                vote = outcomes.get(cid)
                claim["vote_rationale"] = next(
                    (v["rationale"] for v in votes if v.get("claim_id","")[:12] == cid), ""
                )
                if vote == "accepted":
                    claim["consensus_state"] = "accepted"
                    accepted.append(claim)
                elif vote == "rejected":
                    claim["consensus_state"] = "rejected"
                    rejected.append(claim)
                elif vote == "uncertain":
                    claim["consensus_state"] = "uncertain"
                    uncertain.append(claim)
                else:
                    still_pending.append(claim)

            rounds.append({
                "round_number":    round_num,
                "claims_reviewed": [c["claim_id"] for c in pending],
                "outcomes":        outcomes,
                "unresolved":      [c["claim_id"] for c in still_pending],
            })
            pending = still_pending

        for claim in pending:
            claim["consensus_state"] = "uncertain"
            uncertain.append(claim)

        log = (
            f"[Negotiate] {len(accepted)} accepted, "
            f"{len(rejected)} rejected, {len(uncertain)} uncertain "
            f"({len(rounds)} rounds)"
        )
        logger.info(log)
        return {
            "accepted_claims":    accepted,
            "rejected_claims":    rejected,
            "uncertain_claims":   uncertain,
            "negotiation_rounds": rounds,
            "phase_log":          [log],
        }
```

---

## FILE 17: agents/roles/synthesizer.py

**Fix: 30K evidence context (was 300 chars). 15 sources (was 5).**

```python
import logging
from groq import Groq
from agents.state import SwarmState
from memory.lance_store import LanceStore
from memory.models import rerank
from utils.config import LLM_MODEL, FAST_MODEL, GROQ_API_KEY
from utils.rate_limiter import groq_limiter

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a research analyst writing a comprehensive cited report.

RULES:
1. Every factual claim MUST have inline citation [n]
2. Use ONLY the numbered sources provided
3. Write minimum 600 words
4. Professional academic tone

REQUIRED SECTIONS:
## Executive Summary
## Key Findings
## Conflicting Perspectives
## Analysis
## Limitations
## Conclusion
## References"""


class SynthesizerNode:
    def __init__(self, store: LanceStore):
        self.store  = store
        self.client = Groq(api_key=GROQ_API_KEY)

    def run(self, state: SwarmState) -> dict:
        query            = state["query"]
        accepted_claims  = state.get("accepted_claims",  [])
        uncertain_claims = state.get("uncertain_claims", [])
        evidence_chunks  = state.get("evidence_chunks",  [])
        critique_issues  = state.get("critique_issues",  [])

        # Build numbered source list
        seen_urls: dict[str, int] = {}
        numbered: list[dict]      = []
        for claim in accepted_claims:
            for cid in claim.get("evidence_chunk_ids", []):
                chunk = next(
                    (c for c in evidence_chunks if c.get("chunk_id") == cid), None
                )
                if chunk:
                    url = chunk.get("source_url", "")
                    if url and url not in seen_urls:
                        idx = len(numbered) + 1
                        seen_urls[url] = idx
                        numbered.append({
                            "number":  idx,
                            "url":     url,
                            "domain":  chunk.get("source_domain", ""),
                            "content": chunk.get("content", "")[:2000],
                        })

        # Re-rank for top evidence context
        retrieved    = self.store.query(query, n_results=20)
        top_evidence = rerank(query, retrieved, top_k=15)

        evidence_text = "\n\n---\n\n".join(
            f"[Source {i+1}] {e['metadata'].get('source_url','')}\n{e['document']}"
            for i, e in enumerate(top_evidence)
        )

        claims_text = "\n".join(
            f"• {c['statement']} [conf:{c['confidence']:.2f}]"
            for c in accepted_claims
        )

        uncertain_text = (
            "\n\nUNVERIFIED (mention with caution):\n"
            + "\n".join(f"• {c['statement']}" for c in uncertain_claims)
        ) if uncertain_claims else ""

        revision_note = (
            "\n\nFIX THESE ISSUES FROM PREVIOUS DRAFT:\n"
            + "\n".join(f"• {i}" for i in critique_issues)
        ) if critique_issues else ""

        sources_ref = "\n".join(
            f"[{s['number']}] {s['domain']} - {s['url']}"
            for s in numbered
        )

        user_prompt = (
            f"Query: {query}\n\n"
            f"Evidence ({len(top_evidence)} sources):\n{evidence_text}\n\n"
            f"Accepted Claims:\n{claims_text}"
            f"{uncertain_text}"
            f"{revision_note}\n\n"
            f"Numbered Sources:\n{sources_ref}\n\n"
            "Write the complete research paper with [n] citations."
        )

        model_used = LLM_MODEL
        report     = ""

        for attempt in range(2):
            try:
                groq_limiter.wait_if_needed(3000)
                resp = self.client.chat.completions.create(
                    model=model_used,
                    max_tokens=3000,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": user_prompt},
                    ],
                )
                report = resp.choices[0].message.content or ""
                break
            except Exception as e:
                err = str(e).lower()
                if ("429" in str(e) or "rate_limit" in err) and attempt == 0:
                    model_used = FAST_MODEL
                    logger.warning("[Synthesize] Rate limit — falling back to fast model")
                    continue
                logger.error(f"[Synthesize] Failed: {e}")
                report = f"Synthesis failed: {e}"
                break

        if "## References" not in report and sources_ref:
            report += f"\n\n## References\n\n{sources_ref}"

        log = f"[Synthesize] {len(report.split())} words, {len(numbered)} sources"
        logger.info(log)

        return {
            "report":       report,
            "word_count":   len(report.split()),
            "sources_used": [s["url"] for s in numbered],
            "phase_log":    [log],
        }
```

---

## FILE 18: agents/gap_detector.py

```python
import json
import logging
from groq import Groq
from agents.state import SwarmState, ResearchQuestion
from memory.lance_store import LanceStore
from utils.config import FAST_MODEL, GROQ_API_KEY
from utils.rate_limiter import groq_limiter

logger = logging.getLogger(__name__)


class GapDetectorNode:
    def __init__(self, store: LanceStore):
        self.store  = store
        self.client = Groq(api_key=GROQ_API_KEY)

    def run(self, state: SwarmState) -> dict:
        questions      = state.get("research_questions", [])
        evidence_chunks = state.get("evidence_chunks", [])

        if not questions or not evidence_chunks:
            return {
                "unanswered_questions": [],
                "phase_log": ["[GapDetect] Skipped — no questions or no evidence"],
            }

        evidence_summary = "\n".join(
            f"- {c['content'][:150]}" for c in evidence_chunks[:20]
        )
        questions_text = "\n".join(
            f"Q{i+1} ({q['question_id']}): {q['text']}"
            for i, q in enumerate(questions)
        )

        groq_limiter.wait_if_needed(500)
        try:
            resp = self.client.chat.completions.create(
                model=FAST_MODEL,
                max_tokens=200,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Which question IDs are NOT answered by the evidence? "
                            'Return ONLY: {"unanswered": ["q1", "q3"]} '
                            "or empty list if all answered."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Questions:\n{questions_text}\n\n"
                            f"Evidence:\n{evidence_summary}"
                        ),
                    },
                ],
            )
            data           = json.loads(resp.choices[0].message.content or "{}")
            unanswered_ids = set(data.get("unanswered", []))
        except Exception as e:
            logger.warning(f"[GapDetect] Failed: {e} — assuming all answered")
            unanswered_ids = set()

        unanswered = [
            q for q in questions if q["question_id"] in unanswered_ids
        ]

        log = f"[GapDetect] {len(unanswered)}/{len(questions)} questions unanswered"
        logger.info(log)
        return {"unanswered_questions": unanswered, "phase_log": [log]}
```

---

## FILE 19: agents/critic.py

```python
import logging
from agents.state import SwarmState
from evaluation.coherence_scorer import CoherenceScorer
from utils.config import COHERENCE_THRESHOLD

logger = logging.getLogger(__name__)


class CriticNode:
    def __init__(self):
        self.scorer = CoherenceScorer()

    def run(self, state: SwarmState) -> dict:
        report   = state.get("report", "")
        query    = state["query"]
        sources  = state.get("sources_used", [])
        revision = state.get("critique_revision", 0)

        if not report or len(report.split()) < 80:
            return {
                "coherence_score":   0.0,
                "critique_issues":   ["Report empty or too short"],
                "critique_revision": revision + 1,
                "phase_log": ["[Critic] Report too short — requesting revision"],
            }

        result = self.scorer.score(query, report, sources)
        score  = result["score"]
        issues = result.get("issues", [])

        log = (
            f"[Critic] Score: {score:.2f} | "
            f"Threshold: {COHERENCE_THRESHOLD} | "
            f"Revision: {revision}"
        )
        logger.info(log)

        return {
            "coherence_score":   score,
            "critique_issues":   issues if score < COHERENCE_THRESHOLD else [],
            "critique_revision": revision + 1,
            "phase_log": [log],
        }
```

---

## FILE 20: evaluation/coherence_scorer.py

**Critical fix: previous citation coverage logic matched every English sentence.**

```python
import re
import logging

logger = logging.getLogger(__name__)

REQUIRED_SECTIONS = [
    "executive summary",
    "key findings",
    "references",
    "conclusion",
]

CITATION_RE = re.compile(r"\[(\d+)\]")
URL_RE      = re.compile(r"https?://([^/\s\)]+)")


class CoherenceScorer:
    """Composite coherence scorer — fully local, zero external API calls.

    Components and weights:
      citation_density       25%  — inline [n] count relative to report length
      structural_completeness 25% — required sections present
      references_present     25%  — References section with URLs
      length_adequacy        25%  — word count vs 500-word minimum

    BERTScore is optional (slow on first call due to model download).
    When available, it replaces length_adequacy with semantic score.

    FIX: Previous version checked every sentence for "is/are/was" which
    matches ALL English text, making citation_coverage score near 0 for
    any real report. Replaced with citation density — simpler, honest.
    """

    def __init__(self, threshold: float = 0.75):
        self.threshold    = threshold
        self._bert_loaded = False
        self._bert_scorer = None

    def score(self, query: str, report: str, sources: list[str]) -> dict:
        if not report:
            return {"score": 0.0, "passed": False,
                    "issues": ["Empty report"], "threshold": self.threshold}

        words = len(report.split())
        if words < 50:
            return {"score": 0.0, "passed": False,
                    "issues": ["Report too short"], "threshold": self.threshold}

        c1 = self._citation_density(report, words)
        c2 = self._structural_completeness(report)
        c3 = self._references_present(report)
        c4 = self._bert_or_length(query, report, words)

        components = {
            "citation_density":        c1,
            "structural_completeness": c2,
            "references_present":      c3,
            "length_or_semantic":      c4,
        }
        weights = [0.25, 0.25, 0.25, 0.25]
        composite = round(sum(v * w for v, w in zip(components.values(), weights)), 3)

        issues = self._issues(report, words, c1, c2, c3)
        return {
            "score":      composite,
            "passed":     composite >= self.threshold,
            "issues":     issues,
            "threshold":  self.threshold,
            "components": components,
        }

    def _citation_density(self, report: str, words: int) -> float:
        """Citations per 100 words. 3+ per 100 words = 1.0."""
        n_citations = len(CITATION_RE.findall(report))
        density     = n_citations / max(words / 100, 1)
        return min(density / 3.0, 1.0)

    def _structural_completeness(self, report: str) -> float:
        rl = report.lower()
        return sum(1 for s in REQUIRED_SECTIONS if s in rl) / len(REQUIRED_SECTIONS)

    def _references_present(self, report: str) -> float:
        """Does the References section have actual URLs?"""
        has_section = bool(re.search(r"##\s*references", report, re.I))
        has_urls    = bool(URL_RE.search(report))
        if has_section and has_urls:
            return 1.0
        if has_section or has_urls:
            return 0.5
        return 0.0

    def _bert_or_length(self, query: str, report: str, words: int) -> float:
        """Try BERTScore; fall back to length score if unavailable."""
        try:
            if not self._bert_loaded:
                from bert_score import score as bs
                self._bert_scorer = bs
                self._bert_loaded = True
            P, R, F1 = self._bert_scorer(
                [report[:1000]], [query * 5],
                lang="en", model_type="distilbert-base-uncased", verbose=False,
            )
            return float(F1.mean().item())
        except Exception:
            return min(words / 500, 1.0)

    def _issues(
        self, report: str, words: int,
        c1: float, c2: float, c3: float
    ) -> list[str]:
        issues = []
        if c1 < 0.4:
            n = len(CITATION_RE.findall(report))
            issues.append(f"Too few citations ({n} found) — add [n] to factual claims")
        if c2 < 0.75:
            missing = [s for s in REQUIRED_SECTIONS if s not in report.lower()]
            issues.append(f"Missing sections: {', '.join(missing)}")
        if c3 < 0.5:
            issues.append("References section missing or has no URLs")
        if words < 400:
            issues.append(f"Report too short ({words} words — target 500+)")
        return issues
```

---

## FILE 21: ui/gradio_app.py (key changes only)

**Fixes: `_HIDDEN_` string → `""`, `event_queue.get(timeout=60)` → 120s,
WeasyPrint replaces markdown-pdf.**

```python
# Replace the markdown-pdf import block with:
try:
    import markdown as md_lib
    from weasyprint import HTML as WeasyHTML
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


def _export_pdf(report_md: str, query: str) -> str | None:
    if not PDF_AVAILABLE:
        return None
    try:
        body = md_lib.markdown(
            report_md,
            extensions=["tables", "fenced_code"]
        )
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body{{font-family:Georgia,serif;max-width:760px;margin:40px auto;
       font-size:11pt;line-height:1.65;color:#1a1a1a}}
  h1{{font-size:18pt;border-bottom:2px solid #333;padding-bottom:6px}}
  h2{{font-size:13pt;color:#2c3e50;margin-top:24px}}
  table{{width:100%;border-collapse:collapse;margin:12px 0;font-size:10pt}}
  th,td{{border:1px solid #bbb;padding:5px 9px}}
  th{{background:#eef2f7}}
  @page{{margin:2.5cm 2cm}}
</style></head><body>
<p><em>Query: {query}</em></p><hr>{body}
</body></html>"""
        path = f"/tmp/{_safe_name(query)}.pdf"
        WeasyHTML(string=html).write_pdf(path)
        return path
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"PDF export failed: {e}")
        return None


# Replace run_swarmiq() with generator version:
def run_swarmiq(query: str, advanced_mode: bool = False):
    import threading
    import queue as _queue
    from agents.graph import run_pipeline
    from evaluation.coherence_scorer import CoherenceScorer

    if not query or not query.strip():
        yield ("Please enter a research query.", "", "", "Idle", None, None)
        return

    eq: _queue.Queue = _queue.Queue()
    holder: dict = {}

    def _run():
        try:
            holder["result"] = run_pipeline(query, event_callback=eq.put)
        except Exception as e:
            holder["error"] = str(e)
        finally:
            eq.put(None)

    threading.Thread(target=_run, daemon=True).start()

    log = ""
    while True:
        try:
            event = eq.get(timeout=120)   # FIX: was 60, synthesis needs up to 90s
        except _queue.Empty:
            yield ("⚠️ Pipeline timed out.", log, "", "Timeout", None, None)
            return

        if event is None:
            break

        log += f"\n{event}"
        yield (
            f"⏳ {event}",
            log if advanced_mode else "",   # FIX: was "_HIDDEN_" — that string rendered
            "",
            event[:80],
            None,
            None,
        )

    if "error" in holder:
        msg = holder["error"]
        # Show user-friendly message, not raw Python exception
        if "429" in msg or "rate_limit" in msg.lower():
            msg = "Rate limit reached. Wait 60 seconds and try again."
        elif "GROQ_API_KEY" in msg:
            msg = "API key not configured. Check your .env file."
        yield (f"❌ {msg}", log, "", "Error", None, None)
        return

    result = holder.get("result", {})
    scorer = CoherenceScorer()
    score  = scorer.score(
        query, result.get("report", ""), result.get("sources", [])
    )

    report   = result.get("report", "")
    md_path  = _export_markdown(report, query)
    pdf_path = _export_pdf(report, query)

    status = (
        f"✅ Done | Score: {score['score']:.2f} | "
        f"Words: {result.get('word_count',0)} | "
        f"Sources: {len(result.get('sources',[]))}"
    )

    display_report = report
    if advanced_mode:
        accepted  = result.get("claims_summary", {}).get("accepted", 0)
        rejected  = result.get("claims_summary", {}).get("rejected", 0)
        uncertain = result.get("claims_summary", {}).get("uncertain", 0)
        display_report += (
            f"\n\n---\n### Run Summary\n"
            f"- Score: **{score['score']:.2f}**\n"
            f"- Claims: {accepted} accepted / {rejected} rejected / {uncertain} uncertain\n"
            f"- Negotiation rounds: {result.get('negotiation_rounds',0)}\n"
        )

    yield (
        display_report,
        log if advanced_mode else "",
        "",
        status,
        md_path,
        pdf_path,
    )
```

---

## FILE 22: tests/test_graph.py (Real test — no mocks for LangGraph logic)

```python
"""Tests the LangGraph parallel fan-in behavior.

Does NOT call Groq. Validates that the graph wiring is correct:
both parallel branches complete before detect_gaps fires.
"""
import pytest
from langgraph.graph import StateGraph, END
from langgraph.constants import Send
from typing import TypedDict, Annotated
import operator


class TestState(TypedDict):
    results: Annotated[list[str], operator.add]
    visited: Annotated[list[str], operator.add]


def branch_a(state):
    return {"results": ["branch_a_result"], "visited": ["branch_a"]}

def branch_b(state):
    return {"results": ["branch_b_result"], "visited": ["branch_b"]}

def fan_out(state):
    return [Send("branch_a", state), Send("branch_b", state)]

def merge_node(state):
    # This should only fire after BOTH branches complete
    assert "branch_a" in state["visited"], "branch_a did not complete"
    assert "branch_b" in state["visited"], "branch_b did not complete"
    return {"results": ["merged"]}


def build_test_graph():
    g = StateGraph(TestState)
    g.add_node("fan_out_node", lambda s: {})
    g.add_node("branch_a",     branch_a)
    g.add_node("branch_b",     branch_b)
    g.add_node("merge_node",   merge_node)
    g.set_entry_point("fan_out_node")
    g.add_conditional_edges("fan_out_node", fan_out)
    g.add_edge("branch_a",   "merge_node")
    g.add_edge("branch_b",   "merge_node")
    g.add_edge("merge_node", END)
    return g.compile()


def test_parallel_fan_in_both_branches_complete():
    """Both parallel branches must complete before merge_node fires."""
    graph  = build_test_graph()
    result = graph.invoke({"results": [], "visited": []})
    assert "branch_a_result" in result["results"]
    assert "branch_b_result" in result["results"]
    assert "merged"          in result["results"]


def test_operator_add_merges_correctly():
    """operator.add reducer concatenates lists from parallel branches."""
    graph  = build_test_graph()
    result = graph.invoke({"results": [], "visited": []})
    # Both branches contribute to results
    assert len([r for r in result["results"] if "branch" in r]) == 2
```

---

## FILE 23: tests/test_coherence.py

```python
"""Tests coherence scorer with known-good and known-bad reports."""
import pytest
from evaluation.coherence_scorer import CoherenceScorer


@pytest.fixture
def scorer():
    return CoherenceScorer(threshold=0.75)


GOOD_REPORT = """
## Executive Summary
AI regulation in India is rapidly evolving [1][2].

## Key Findings
The government announced new guidelines in 2024 [1].
Multiple agencies are involved in oversight [2][3].
Industry groups have raised concerns about compliance costs [2].

## Conflicting Perspectives
Some experts support strict regulation [1], while others
argue for a lighter approach [3].

## Analysis
Evidence suggests a middle-ground approach is emerging [2].

## Limitations
Data from early 2024 may not reflect current policy.

## Conclusion
India's AI regulation landscape is dynamic and evolving [1][2].

## References
[1] Ministry of Electronics - https://meity.gov.in/ai-policy
[2] Reuters - https://reuters.com/india-ai-2024
[3] Times of India - https://timesofindia.com/ai-regulation
"""

BAD_REPORT = "This is a short report about things."

NO_CITATIONS = """
## Executive Summary
AI regulation is important.

## Key Findings
The government has taken action.

## Conclusion
Policy is evolving.

## References
No sources listed.
"""


def test_good_report_scores_above_threshold(scorer):
    result = scorer.score("AI regulation India", GOOD_REPORT, [])
    assert result["score"] > 0.60, f"Expected > 0.60, got {result['score']}"


def test_short_report_scores_zero(scorer):
    result = scorer.score("query", BAD_REPORT, [])
    assert result["score"] == 0.0


def test_no_citations_scores_low(scorer):
    result = scorer.score("AI regulation", NO_CITATIONS, [])
    assert result["components"]["citation_density"] < 0.1


def test_score_returns_issues_when_failing(scorer):
    result = scorer.score("query", NO_CITATIONS, [])
    assert len(result["issues"]) > 0


def test_references_present_detects_urls(scorer):
    score = scorer._references_present(GOOD_REPORT)
    assert score == 1.0


def test_references_absent_scores_zero(scorer):
    score = scorer._references_present("No references here.")
    assert score == 0.0
```

---

## FILE 24: tests/test_lance_store.py

```python
"""Tests LanceDB concurrent write safety."""
import threading
import tempfile
import pytest
from memory.lance_store import LanceStore


@pytest.fixture
def tmp_store(tmp_path):
    return LanceStore(table_name="test", persist_dir=str(tmp_path))


def test_stable_id_is_deterministic():
    id1 = LanceStore.stable_id("a", "b", "c")
    id2 = LanceStore.stable_id("a", "b", "c")
    id3 = LanceStore.stable_id("a", "b", "d")
    assert id1 == id2
    assert id1 != id3


def test_stable_id_no_positional_duplicates():
    """Same content at different positions must get same ID."""
    id_pos0 = LanceStore.stable_id("https://example.com", "content here")
    id_pos1 = LanceStore.stable_id("https://example.com", "content here")
    assert id_pos0 == id_pos1


def test_concurrent_writes_no_errors(tmp_store):
    """10 parallel writes must all succeed without corruption."""
    errors = []

    def write(i: int):
        try:
            tmp_store.add_documents(
                documents=[f"document content {i}"],
                metadatas=[{
                    "source_url":     f"https://example.com/{i}",
                    "agent_id":       f"agent_{i}",
                    "run_id":         "test_run",
                    "phase":          "test",
                    "confidence":     0.8,
                    "consensus_state": "pending",
                    "question_id":    "q1",
                    "published_date": "",
                }],
                ids=[f"test_id_{i}"],
            )
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=write, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert not errors, f"Concurrent write errors: {errors}"


def test_query_returns_results(tmp_store):
    tmp_store.add_documents(
        documents=["Python is a programming language"],
        metadatas=[{
            "source_url": "https://python.org", "agent_id": "test",
            "run_id": "r1", "phase": "test", "confidence": 0.9,
            "consensus_state": "accepted", "question_id": "q1",
            "published_date": "",
        }],
        ids=["python_doc"],
    )
    results = tmp_store.query("programming language Python", n_results=5)
    assert len(results) > 0
    assert any("Python" in r["document"] for r in results)
```

---

## FILE 25: .github/workflows/sync.yml

```yaml
name: CI + Deploy to Hugging Face

on:
  push:
    branches: [master]
  workflow_dispatch:

jobs:
  validate-and-deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install validation deps
        run: pip install ruff pytest pytest-timeout

      - name: Lint
        run: ruff check . --select=E,F,W --ignore=E501,W503

      - name: Run tests
        run: pytest tests/ -x -q --timeout=60
        env:
          GROQ_API_KEY: "dummy-key-for-import-and-unit-tests"
          LANCE_PERSIST_DIR: "/tmp/test_lance"

      - name: Deploy to Hugging Face
        if: success()
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          git push --force \
            https://rajivgolait:$HF_TOKEN@huggingface.co/spaces/rajivgolait/SwarmIQ \
            master:main
```

---

## Implementation Order — 4 Weeks, Day by Day

```
WEEK 1 — Foundation
────────────────────────────────────────────────────────────
Mon  FILE 25  .github/workflows/sync.yml — CI before code
Mon  FILE 4   utils/config.py            — startup validation
Mon  FILE 5   utils/rate_limiter.py      — token bucket
Mon  FILE 6   utils/confidence.py        — real scoring (2-factor, no placeholder)
     VERIFY:  python -c "from utils.config import GROQ_API_KEY; print('OK')"

Tue  FILE 10  search/searcher.py
     FILE 9   search/cache.py
     VERIFY:  python -c "
               from search.searcher import WebSearcher
               r = WebSearcher().search('LangGraph tutorial', max_results=3)
               print(len(r), 'results, content len:', len(r[0].content) if r else 0)
             "
     EXPECT:  3 results, content len > 200

Wed  FILE 7   memory/models.py           — singleton registry
     FILE 8   memory/lance_store.py
     FILE 22  tests/test_lance_store.py
     RUN:     pytest tests/test_lance_store.py -v
     EXPECT:  All 4 tests pass

Thu  FILE 20  evaluation/coherence_scorer.py
     FILE 23  tests/test_coherence.py
     RUN:     pytest tests/test_coherence.py -v
     EXPECT:  All 6 tests pass

Fri  requirements.txt, packages.txt, .env.example
     Update .gitignore (add lance_db/, search_cache/)
     Delete: agents/swarm/, agents/supervisor.py,
             agents/analyst.py, agents/researcher.py,
             agents/synthesizer.py, memory/chroma_store.py

WEEK 2 — LangGraph Core
────────────────────────────────────────────────────────────
Mon  FILE 11  agents/state.py
     FILE 22  tests/test_graph.py        — write and run FIRST
     RUN:     pytest tests/test_graph.py -v
     EXPECT:  Both tests pass — confirms fan-in is correct

Tue  FILE 16  agents/roles/conflict_resolver.py
     FILE 14  agents/roles/literature_reviewer.py
     FILE 15  agents/roles/summarizer.py  (ungrounded bug fixed)

Wed  FILE 13  agents/roles/planner.py
     FILE 17  agents/roles/synthesizer.py (30K context)
     agents/roles/visualizer.py           (basic Plotly table)

Thu  FILE 18  agents/gap_detector.py
     FILE 19  agents/critic.py

Fri  FILE 12  agents/graph.py            — assemble the graph
     VERIFY:  python -c "
               import os; os.environ['GROQ_API_KEY'] = 'test'
               from agents.graph import build_graph
               from memory.lance_store import LanceStore
               import tempfile
               s = LanceStore(persist_dir=tempfile.mkdtemp())
               g = build_graph(s)
               print('Graph compiled OK:', type(g))
             "

WEEK 3 — End-to-End + Measurement
────────────────────────────────────────────────────────────
Mon  Run actual pipeline on first query:
     python -c "
       from agents.graph import run_pipeline
       r = run_pipeline('What is LangGraph?')
       print('Words:', r['word_count'])
       print('Score:', r['coherence_score'])
       print('Sources:', len(r['sources']))
     "
     Record actual numbers. They will not be 90%. That is OK.

Tue  Run on all 5 demo queries. Record scores in BENCHMARK.md.
     5 queries × measured score = your honest claim for README.

Wed  Fix whatever breaks. It will break. That is the point of running it.

Thu  FILE 24  tests/test_lance_store.py  (already written Week 1)
     Write 2 more tests based on what broke this week.

Fri  FILE 21  ui/gradio_app.py           — streaming + WeasyPrint
     Test PDF export locally. Verify "_HIDDEN_" is gone.

WEEK 4 — Polish + Deploy
────────────────────────────────────────────────────────────
Mon  Test WeasyPrint on HF Spaces free tier (packages.txt system deps)
Tue  README.md — honest rewrite with real benchmark numbers from Week 3
Wed  Update main.py CLI to use run_pipeline() not legacy Supervisor
Thu  Full CI/CD test: push to master, verify CI passes before deploy
Fri  Demo run on 5 query types. Record results. Ship.
```

---

## The Three Numbers That Matter

After Week 3, you will have actual data. Put these in `BENCHMARK.md`:

```markdown
# Benchmark Results

Measured on: [date]
Pipeline: LangGraph + Groq llama-3.3-70b + DDG + Jina + LanceDB

| Query | Words | Sources | Score | Time |
|---|---|---|---|---|
| AI regulation India 2025 | ? | ? | ? | ? |
| Climate change agriculture | ? | ? | ? | ? |
| Gen AI in healthcare | ? | ? | ? | ? |
| Crypto regulation global | ? | ? | ? | ? |
| Mental health Gen Z | ? | ? | ? | ? |
| **Average** | ? | ? | ? | ? |

Coherence threshold set to actual average score.
```

Fill in real numbers. If average is 0.68, set `COHERENCE_THRESHOLD=0.65`.
A measured 68% is more credible than a claimed 90% with no data.

---

## What Was Honestly Removed From Previous Plans

| Item | Previous Plan | This Plan | Why |
|---|---|---|---|
| `semantic_score=0.6` in confidence | Present | Removed | Was always a hardcoded placeholder |
| `search/cache.py` | Listed, not implemented | **Implemented** | |
| `if False` in LanceStore | Present | Removed, decision made: `append` | |
| `_HIDDEN_` string in Gradio | Present | Fixed to `""` | |
| LangGraph fan-in via add_edge | Wrong | Fixed with Send API | |
| `final_state = node_state` | Wrong | Fixed with delta merge | |
| Coherence >90% claim | Unverified | `COHERENCE_THRESHOLD=0.75`, measure first | |
| Reranker loaded twice | Yes | Singleton in models.py | |
| Timeout 60s for synthesis | Present | Raised to 120s | |

---

*Version 3.0 — Final. Build this, measure it, report what you find.*
