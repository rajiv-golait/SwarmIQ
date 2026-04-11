# SwarmIQ

Multi-agent research pipeline: **LangGraph**, **Groq**, **LanceDB**, and web search (**DDG** + **Jina Reader** + trafilatura).

**Setup:** `pip install -r requirements.txt`, copy `.env.example` to `.env`, set `GROQ_API_KEY`.

**API (SSE):** from this directory run `python app.py`, then `POST http://localhost:8000/api/run` with JSON `{"query":"..."}`. Events: `log`, `ping` (~12s keepalive), then `complete` or `error`. **OpenAPI `/docs` buffers the whole response** until the run ends—use `curl -N -H "Content-Type: application/json" -d "{\"query\":\"...\"}" http://localhost:8000/api/run` for live output. Health: `GET /api/health`.

**CLI:** `python main.py`. **Optional UI:** `python ui/gradio_app.py`. **Test:** `pytest tests/test_graph.py -v`.
