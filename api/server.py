"""FastAPI server with SSE streaming for SwarmIQ pipeline."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from agents.graph import run_pipeline

logger = logging.getLogger(__name__)

app = FastAPI(title="SwarmIQ API", version="3.0")

_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]
_extra = os.getenv("SWARMIQ_CORS_ORIGINS", "").strip()
if _extra:
    _cors_origins = _default_origins + [o.strip() for o in _extra.split(",") if o.strip()]
else:
    _cors_origins = _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

_executor = ThreadPoolExecutor(max_workers=2)


class RunRequest(BaseModel):
    query: str = Field(..., min_length=1)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post(
    "/api/run",
    summary="Run pipeline (SSE stream)",
    description=(
        "Streams Server-Sent Events: `log` (phase lines), `ping` (keepalive every ~12s), "
        "then `complete` (full JSON result) or `error`. "
        "**Swagger UI usually buffers the entire stream** until the run finishes (often 5–20+ minutes). "
        "Use `curl -N` or browser `EventSource` to see live events."
    ),
)
async def run(request: RunRequest):
    query = (request.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query must be non-empty")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _event_callback(entry: str):
        data = json.dumps({
            "entry": entry,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        loop.call_soon_threadsafe(queue.put_nowait, ("log", data))

    def _run_in_thread():
        try:
            result = run_pipeline(query, event_callback=_event_callback)
            loop.call_soon_threadsafe(
                queue.put_nowait, ("complete", json.dumps(result))
            )
        except Exception as e:
            logger.exception("run_pipeline failed")
            loop.call_soon_threadsafe(
                queue.put_nowait,
                (
                    "error",
                    json.dumps({"message": f"{type(e).__name__}: {e}"}),
                ),
            )

    async def _stream() -> AsyncGenerator[dict, None]:
        _executor.submit(_run_in_thread)
        while True:
            try:
                event_type, data = await asyncio.wait_for(queue.get(), timeout=12.0)
            except asyncio.TimeoutError:
                # Keeps connections alive; Swagger UI may still buffer until `complete`.
                yield {"event": "ping", "data": "{}"}
                continue
            yield {"event": event_type, "data": data}
            if event_type in ("complete", "error"):
                break

    return EventSourceResponse(_stream())
