SwarmIQ
=======

SwarmIQ is a multi-agent research assistant that decomposes a user query, retrieves evidence from the web, stores evidence in a shared vector database (Chroma), negotiates claim consensus across agents, and produces a grounded, paper-like research document with numbered URL citations.

## What you get

- Evidence-grounded “research paper” style output (numbered inline citations like `[1]`, `[2]`, …)
- A clean UI by default (agent internals hidden)
- Optional Advanced view (negotiation + stage progress + visualization)
- Export of the research document as:
  - Markdown (`.md`)
  - PDF (`.pdf`)

## Tech stack

- Groq (LLMs)
- Tavily (web search)
- ChromaDB (vector store for shared evidence + citations)
- Gradio (UI)

## Setup

1. Install dependencies:

   `pip install -r requirements.txt`

2. Create/update your `.env` file. Expected variables:

- `GROQ_API_KEY`
- `TAVILY_API_KEY`

Optional swarm/runtime tuning variables are in `utils/config.py`.

## Run the UI

`python ui/gradio_app.py`

Then open the displayed local URL (typically `http://127.0.0.1:7860`).

## CLI (optional)

`python main.py`

## Notes

- If you hit Groq rate limits (HTTP 429), the swarm synthesis includes a fallback model to keep the output non-empty.
- Citations are validated to ensure inline `[n]` references map to URLs listed in the report’s `References` section.

