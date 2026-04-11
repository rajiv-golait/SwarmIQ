# SwarmIQ

Multi-agent research pipeline: **LangGraph**, **Groq**, **LanceDB**, and web search (**DDG** + **Jina Reader** + trafilatura).

**Setup:** `pip install -r requirements.txt`, copy `.env.example` to `.env`, set `GROQ_API_KEY`. Prefer the **`ddgs`** package for search; uninstall legacy **`duckduckgo_search`** if you see rename warnings.

**Low RAM / Windows page file:** If negotiation crashes loading the cross-encoder (`OSError: paging file is too small`, 1455), set **`SWARMIQ_DISABLE_RERANK=1`** in `.env`. The pipeline then keeps **embedding** re-ranking but skips the second HF model and orders hits by vector distance.

**API (SSE):** from this directory run `python app.py`, then `POST http://localhost:8000/api/run` with JSON `{"query":"..."}`. Events: `log`, `ping` (~12s keepalive), then `complete` or `error`. **OpenAPI `/docs` buffers the whole response** until the run ends—use `curl -N -H "Content-Type: application/json" -d "{\"query\":\"...\"}" http://localhost:8000/api/run` for live output. Health: `GET /api/health`.

**CLI:** `python main.py`. **Web UI:** from `frontend/` run `npm install` and `npm run dev` (Vite proxies `/api` to `http://127.0.0.1:8000`; set `VITE_API_PROXY_TARGET` if the API uses another port). For direct browser→API calls, set `VITE_API_BASE_URL` and extend CORS with env `SWARMIQ_CORS_ORIGINS` (comma-separated). **Test:** `pytest tests/ -q`.
