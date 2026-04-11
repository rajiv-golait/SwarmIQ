# SwarmIQ v3.0 — Full Architecture Upgrade

Complete rewrite from AutoGen/ChromaDB/Tavily to LangGraph/LanceDB/DDG+Jina, implementing every file from the `SWARMIQ_FINAL_UPGRADE (1).md` spec.

## User Review Required

> [!IMPORTANT]
> **Breaking Change — Complete Backend Rewrite**: This replaces the entire agent pipeline (AutoGen → LangGraph), vector store (ChromaDB → LanceDB), search (Tavily → DDG + Jina), PDF export (markdown-pdf → WeasyPrint), and evaluation (DeepEval → BERTScore + deterministic). There is no backward compatibility.

> [!WARNING]
> **Deletions**: The following legacy files/directories will be permanently deleted:
> - `agents/swarm/` (entire directory — 6 files)
> - `agents/supervisor.py`
> - `agents/analyst.py`
> - `agents/researcher.py`
> - `agents/synthesizer.py`
> - `memory/chroma_store.py`

> [!IMPORTANT]
> **Missing from spec**: The upgrade doc references `agents/roles/visualizer.py` ("basic Plotly table") but provides no code. I will implement a minimal Plotly-based visualizer node that generates a claims confidence chart and a source distribution table.

---

## Proposed Changes

### Phase 1: Foundation (Utils + Config)

#### [MODIFY] [config.py](file:///r:/VectorVerse/swarmiq/utils/config.py)
- Complete rewrite: add startup validation (fail-fast GROQ_API_KEY check), remove Tavily/AutoGen/ChromaDB config, add LanceDB/search/rate-limit config, add logging setup.

#### [NEW] [rate_limiter.py](file:///r:/VectorVerse/swarmiq/utils/rate_limiter.py)
- Thread-safe token bucket for shared Groq API. Module-level singleton.

#### [NEW] [confidence.py](file:///r:/VectorVerse/swarmiq/utils/confidence.py)
- 2-factor confidence scoring (authority + recency). No fake semantic_score placeholder.

---

### Phase 2: Search Layer

#### [NEW] [cache.py](file:///r:/VectorVerse/swarmiq/search/__init__.py)
- Empty `__init__.py` for new search package.

#### [NEW] [cache.py](file:///r:/VectorVerse/swarmiq/search/cache.py)
- Disk-backed query result cache with SHA-256 keys and 24h TTL.

#### [NEW] [searcher.py](file:///r:/VectorVerse/swarmiq/search/searcher.py)
- DDG + Jina Reader + trafilatura fallback. No API key required.

---

### Phase 3: Memory Layer

#### [NEW] [models.py](file:///r:/VectorVerse/swarmiq/memory/models.py)
- Shared ML model registry (singleton SentenceTransformer + CrossEncoder). Thread-safe.

#### [NEW] [lance_store.py](file:///r:/VectorVerse/swarmiq/memory/lance_store.py)
- LanceDB vector store with write-lock, PyArrow schema, cosine search.

#### [DELETE] [chroma_store.py](file:///r:/VectorVerse/swarmiq/memory/chroma_store.py)

---

### Phase 4: Evaluation

#### [MODIFY] [coherence_scorer.py](file:///r:/VectorVerse/swarmiq/evaluation/coherence_scorer.py)
- Complete rewrite: 4-component scorer (citation_density, structural_completeness, references_present, BERTScore/length). Fix old "matches every English sentence" bug.

---

### Phase 5: LangGraph Agent Core

#### [NEW] [state.py](file:///r:/VectorVerse/swarmiq/agents/state.py)
- TypedDict state definition with `operator.add` reducers for parallel fan-in.

#### [NEW] [graph.py](file:///r:/VectorVerse/swarmiq/agents/graph.py)
- LangGraph state machine with Send API, gap detection loop, critique loop, visualization. Uses `stream(mode="updates")` with delta merge for UI callbacks.

#### [NEW] [planner.py](file:///r:/VectorVerse/swarmiq/agents/roles/planner.py)
- LLM-based query decomposition into 4-6 research questions with DDG queries.

#### [NEW] [literature_reviewer.py](file:///r:/VectorVerse/swarmiq/agents/roles/literature_reviewer.py)
- Multi-search, real confidence scoring, evidence chunk + claim extraction.

#### [NEW] [summarizer.py](file:///r:/VectorVerse/swarmiq/agents/roles/summarizer.py)
- News-focused LLM claim extraction. Bug fix: no "ungrounded" chunk IDs.

#### [NEW] [conflict_resolver.py](file:///r:/VectorVerse/swarmiq/agents/roles/conflict_resolver.py)
- JSON-based LLM voting across negotiation rounds. No pipe-delimited parsing.

#### [NEW] [synthesizer.py](file:///r:/VectorVerse/swarmiq/agents/roles/synthesizer.py)
- 30K evidence context, 15 sources, inline [n] citations, retry with fast model fallback.

#### [NEW] [visualizer.py](file:///r:/VectorVerse/swarmiq/agents/roles/visualizer.py)
- Plotly-based claims confidence chart and source distribution table.

#### [NEW] [gap_detector.py](file:///r:/VectorVerse/swarmiq/agents/gap_detector.py)
- LLM-based gap detection against evidence. Returns unanswered question IDs.

#### [NEW] [critic.py](file:///r:/VectorVerse/swarmiq/agents/critic.py)
- Invokes coherence scorer, controls revision loop.

#### [NEW] [\_\_init\_\_.py](file:///r:/VectorVerse/swarmiq/agents/roles/__init__.py)
- Empty init for roles subpackage.

---

### Phase 6: Legacy Cleanup

#### [DELETE] `agents/swarm/` (entire directory)
#### [DELETE] [supervisor.py](file:///r:/VectorVerse/swarmiq/agents/supervisor.py)
#### [DELETE] [analyst.py](file:///r:/VectorVerse/swarmiq/agents/analyst.py)
#### [DELETE] [researcher.py](file:///r:/VectorVerse/swarmiq/agents/researcher.py)
#### [DELETE] [synthesizer.py](file:///r:/VectorVerse/swarmiq/agents/synthesizer.py) (legacy top-level one)

---

### Phase 7: UI + Entrypoints

#### [REMOVED] `ui/gradio_app.py`
- Gradio UI removed; the project uses `Frontend/` (React) against `api/server.py` + `python app.py`.

#### [MODIFY] [main.py](file:///r:/VectorVerse/swarmiq/main.py)
- Rewrite to use `run_pipeline()` instead of legacy `Supervisor`.

#### [MODIFY] [app.py](file:///r:/VectorVerse/swarmiq/app.py)
- Launches uvicorn on `api.server:app` (FastAPI + SSE).

---

### Phase 8: Project Files

#### [MODIFY] [requirements.txt](file:///r:/VectorVerse/swarmiq/requirements.txt)
- Full rewrite: LangGraph, LanceDB, DDG, Jina, trafilatura, WeasyPrint, BERTScore. Remove AutoGen, ChromaDB, Tavily, DeepEval, markdown-pdf.

#### [NEW] [packages.txt](file:///r:/VectorVerse/swarmiq/packages.txt)
- HF Spaces system deps for WeasyPrint (libpango, libcairo, etc.)

#### [MODIFY] [.env.example](file:///r:/VectorVerse/swarmiq/.env.example)
- Remove TAVILY_API_KEY, add all new config knobs.

#### [MODIFY] [.gitignore](file:///r:/VectorVerse/swarmiq/.gitignore)
- Add `lance_db/`, `search_cache/`.

#### [MODIFY] [sync.yml](file:///r:/VectorVerse/swarmiq/.github/workflows/sync.yml)
- Add CI lint + test steps before deploy.

---

### Phase 9: Tests

#### [NEW] [test_graph.py](file:///r:/VectorVerse/swarmiq/tests/test_graph.py)
- LangGraph parallel fan-in validation (no Groq needed).

#### [NEW] [test_coherence.py](file:///r:/VectorVerse/swarmiq/tests/test_coherence.py)
- Good/bad/no-citation report scoring tests.

#### [NEW] [test_lance_store.py](file:///r:/VectorVerse/swarmiq/tests/test_lance_store.py)
- Concurrent write safety, deterministic IDs, query results.

#### [DELETE] Legacy test files:
- `tests/test_supervisor_integration.py`
- `tests/test_swarm_components.py`

---

## Open Questions

> [!IMPORTANT]
> **Visualizer implementation**: The spec mentions "basic Plotly table" but provides no code. I'll implement a node that generates a JSON-serializable Plotly chart (claims by confidence + source domain distribution). Does this approach work?

---

## Verification Plan

### Automated Tests
1. `pytest tests/test_graph.py -v` — Validates LangGraph fan-in wiring
2. `pytest tests/test_coherence.py -v` — Validates scorer on known reports
3. `pytest tests/test_lance_store.py -v` — Validates concurrent writes + queries
4. Import smoke test: `python -c "from agents.graph import build_graph; print('OK')"`

### Manual Verification
- Run a full pipeline on a test query to verify end-to-end flow
- Verify FastAPI `/api/run` streams events correctly from the Frontend (or `curl -N`)
