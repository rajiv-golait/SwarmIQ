# SwarmIQ

Multi-agent research pipeline: **LangGraph**, **Groq**, **LanceDB**, and web search (**DDG** + **Jina Reader** + trafilatura).

**Setup:** `pip install -r requirements.txt`, copy `.env.example` to `.env`, set `GROQ_API_KEY`.

**API (SSE):** from this directory run `python app.py`, then `POST http://localhost:8000/api/run` with JSON `{"query":"..."}` (stream `log` / `complete` / `error` events). Health: `GET /api/health`.

**CLI:** `python main.py`. **Optional UI:** `python ui/gradio_app.py`. **Test:** `pytest tests/test_graph.py -v`.
